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
    }

    private void ExitFullscreen()
    {
        _trueFullscreen = false;
        Topmost = false;
        WindowStyle = WindowStyle.SingleBorderWindow;
        ResizeMode = ResizeMode.CanResize;
        WindowState = WindowState.Maximized;
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
            // Esc immersīvā: fokuss uz jautājumu; Chrome režīmā — atpakaļ immersīvā
            if (DataContext is MainViewModel vm)
            {
                if (!vm.ImmersiveMode)
                {
                    vm.ImmersiveMode = true;
                }
                else
                {
                    ChatBox?.Focus();
                }
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
            App.BrowserAutomation.Attach(Browser);
            if (BrowserMulti is not null)
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
            var vm = new MainViewModel(api);
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
                    !string.IsNullOrWhiteSpace(vm.BrowserUrl) &&
                    Browser is not null)
                {
                    try
                    {
                        Browser.Source = new Uri(vm.BrowserUrl);
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
