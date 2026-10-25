using System.IO;
using System.Windows;
using System.Windows.Input;
using System.Windows.Media.Imaging;
using MainBrain.Desktop.Services;
using MainBrain.Desktop.ViewModels;

namespace MainBrain.Desktop;

public partial class MainWindow : Window
{
    private bool _trueFullscreen = true;

    public MainWindow()
    {
        InitializeComponent();
        EnterFullscreen();
        Loaded += OnLoaded;
    }

    private void EnterFullscreen()
    {
        _trueFullscreen = true;
        WindowStyle = WindowStyle.None;
        ResizeMode = ResizeMode.NoResize;
        Topmost = true;
        WindowState = WindowState.Maximized;
        ShowInTaskbar = true;
    }

    private void ExitFullscreen()
    {
        _trueFullscreen = false;
        Topmost = false;
        WindowStyle = WindowStyle.SingleBorderWindow;
        ResizeMode = ResizeMode.CanResize;
        WindowState = WindowState.Maximized;
    }

    /// <summary>
    /// Kritiski: Topmost=true pārklāj pārlūku — lietotājs redz tikai «DOMĀ».
    /// Minimizējam overlay, lai Chrome/Edge/fails būtu REDZAMS priekšā.
    /// </summary>
    private void YieldForExternalAction(string reason)
    {
        try
        {
            Topmost = false;
            WindowState = WindowState.Minimized;
        }
        catch
        {
            // ignore
        }
    }

    private void RestoreMainOverlay()
    {
        try
        {
            if (_trueFullscreen)
            {
                WindowStyle = WindowStyle.None;
                ResizeMode = ResizeMode.NoResize;
                Topmost = true;
            }

            if (WindowState == WindowState.Minimized)
            {
                WindowState = WindowState.Maximized;
            }

            Activate();
            ChatBox?.Focus();
        }
        catch
        {
            // ignore
        }
    }

    private void Window_OnKeyDown(object sender, KeyEventArgs e)
    {
        // Ctrl+Shift+D — rāda/slēpj DEV pogas (immersīvajā režīmā nav opciju)
        if (e.Key == Key.D &&
            Keyboard.Modifiers == (ModifierKeys.Control | ModifierKeys.Shift) &&
            DataContext is MainViewModel vmToggle)
        {
            vmToggle.ToggleImmersiveCommand.Execute(null);
            e.Handled = true;
            return;
        }

        if (e.Key == Key.Escape)
        {
            // Esc: atgriež Matrix overlay (pēc pārlūka) + fokuss
            RestoreMainOverlay();
            if (DataContext is MainViewModel vm)
            {
                if (!vm.ImmersiveMode)
                {
                    vm.ImmersiveMode = true;
                }

                ChatBox?.Focus();
            }

            e.Handled = true;
            return;
        }

        if (e.Key == Key.F11)
        {
            if (_trueFullscreen)
            {
                ExitFullscreen();
            }
            else
            {
                EnterFullscreen();
            }

            e.Handled = true;
        }
    }

    private void ChatBox_OnKeyDown(object sender, KeyEventArgs e)
    {
        if (e.Key != Key.Enter || Keyboard.Modifiers != ModifierKeys.None)
        {
            return;
        }

        e.Handled = true;
        if (DataContext is MainViewModel vm && vm.SendGoalCommand.CanExecute(null))
        {
            vm.SendGoalCommand.Execute(null);
        }
    }

    private async void OnLoaded(object sender, RoutedEventArgs e)
    {
        try
        {
            await App.EnsureBackendAsync();
            var host = App.Backend!;
            // Primāri immersīvais mazais lodziņš — lietotājs REDZ AI darbību tajā pašā ekrānā
            if (ImmersiveBrowser is not null)
            {
                App.BrowserAutomation.Attach(ImmersiveBrowser);
                ImmersiveBrowser.NavigationCompleted += (_, __) =>
                {
                    try
                    {
                        if (ImmersiveBrowser.Source is not null && Browser is not null)
                        {
                            Browser.Source = ImmersiveBrowser.Source;
                        }
                    }
                    catch { /* ignore */ }
                };
            }
            else
            {
                App.BrowserAutomation.Attach(Browser);
            }

            if (BrowserMulti is not null && Browser is not null)
            {
                Browser.NavigationCompleted += (_, __) =>
                {
                    try
                    {
                        if (Browser.Source is not null)
                        {
                            BrowserMulti.Source = Browser.Source;
                        }
                    }
                    catch { /* ignore */ }
                };
            }

            var api = new ApiClient(host.BaseUrl, host.Token);
            var vm = new MainViewModel(api)
            {
                YieldForExternalAction = YieldForExternalAction,
                RestoreMainOverlay = RestoreMainOverlay,
            };
            DataContext = vm;
            await vm.InitializeAsync();
            ChatBox?.Focus();

            vm.PropertyChanged += (_, args) =>
            {
                if (args.PropertyName == nameof(MainViewModel.LiveImagePath) &&
                    !string.IsNullOrWhiteSpace(vm.LiveImagePath) &&
                    File.Exists(vm.LiveImagePath))
                {
                    try
                    {
                        var bmp = new BitmapImage();
                        bmp.BeginInit();
                        bmp.CacheOption = BitmapCacheOption.OnLoad;
                        bmp.UriSource = new Uri(vm.LiveImagePath);
                        bmp.EndInit();
                        if (LiveImage is not null)
                        {
                            LiveImage.Source = bmp;
                        }

                        if (ImmersiveLiveImage is not null)
                        {
                            ImmersiveLiveImage.Source = bmp;
                        }
                    }
                    catch { /* ignore bad image */ }
                }

                if (args.PropertyName == nameof(MainViewModel.BrowserUrl) &&
                    !string.IsNullOrWhiteSpace(vm.BrowserUrl))
                {
                    try
                    {
                        var uri = new Uri(vm.BrowserUrl);
                        if (Browser is not null)
                        {
                            Browser.Source = uri;
                        }

                        // Mazais lodziņš uz Matrix — lietotājs REDZ navigāciju
                        if (ImmersiveBrowser is not null)
                        {
                            ImmersiveBrowser.Source = uri;
                        }
                    }
                    catch { /* ignore bad url */ }
                }
            };
        }
        catch (Exception ex)
        {
            MessageBox.Show(
                "Neizdevās startēt Main Brain OS:\n" + ex.Message,
                "Kļūda",
                MessageBoxButton.OK,
                MessageBoxImage.Error);
        }
    }
}
