using System.IO;
using System.Windows;
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
        var token = Environment.GetEnvironmentVariable("MAINBRAIN_API_TOKEN") ?? "";
        var dataDir = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "MainBrainOS");
        var tokenFile = Path.Combine(dataDir, "api_token.txt");
        if (string.IsNullOrWhiteSpace(token) && File.Exists(tokenFile))
        {
            token = await File.ReadAllTextAsync(tokenFile);
        }

        var api = new ApiClient("http://127.0.0.1:8765", token.Trim());
        var vm = new MainViewModel(api);
        DataContext = vm;
        await vm.InitializeAsync();
    }
}
