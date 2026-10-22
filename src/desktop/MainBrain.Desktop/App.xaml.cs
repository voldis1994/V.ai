using System.Windows;
using MainBrain.Desktop.Services;

namespace MainBrain.Desktop;

public partial class App : Application
{
    public static BackendHost? Backend { get; private set; }
    public static BrowserAutomationService BrowserAutomation { get; } = new();

    protected override void OnStartup(StartupEventArgs e)
    {
        base.OnStartup(e);
        DispatcherUnhandledException += (_, args) =>
        {
            MessageBox.Show(args.Exception.Message, "Main Brain OS kļūda", MessageBoxButton.OK, MessageBoxImage.Error);
            args.Handled = true;
        };
    }

    protected override async void OnExit(ExitEventArgs e)
    {
        if (Backend is not null)
        {
            await Backend.StopAsync();
            Backend.Dispose();
        }

        base.OnExit(e);
    }

    public static async Task EnsureBackendAsync()
    {
        if (Backend is not null)
        {
            return;
        }

        Backend = new BackendHost();
        await Backend.StartAsync(BrowserAutomation.HandleBridgeRequestAsync);
    }
}
