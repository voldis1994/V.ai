using System.IO;
using System.Windows;
using System.Windows.Media.Imaging;
using MainBrain.Desktop.Services;
using MainBrain.Desktop.ViewModels;

namespace MainBrain.Desktop;

public partial class MainWindow : Window
{
    public MainWindow()
    {
        InitializeComponent();
        Loaded += OnLoaded;
    }

    private async void OnLoaded(object sender, RoutedEventArgs e)
    {
        try
        {
            await App.EnsureBackendAsync();
            var host = App.Backend!;
            App.BrowserAutomation.Attach(Browser);
            // Multi režīma pārlūks — tā pati sesijas loģika caur tiltu izmanto Focus pārlūku kā primāro
            // (Multi WebView2 ir vizuāls otrais skats; operācijas iet caur primāro Attach)
            if (BrowserMulti is not null)
            {
                // Navigācijas sinhronizācija vizuāli
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

            // Dzīvā attēla ceļa atjauninājums
            vm.PropertyChanged += (_, args) =>
            {
                if (args.PropertyName == nameof(MainViewModel.LiveImagePath) &&
                    !string.IsNullOrWhiteSpace(vm.LiveImagePath) &&
                    File.Exists(vm.LiveImagePath))
                {
                    var bmp = new BitmapImage();
                    bmp.BeginInit();
                    bmp.CacheOption = BitmapCacheOption.OnLoad;
                    bmp.UriSource = new Uri(vm.LiveImagePath);
                    bmp.EndInit();
                    LiveImage.Source = bmp;
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
