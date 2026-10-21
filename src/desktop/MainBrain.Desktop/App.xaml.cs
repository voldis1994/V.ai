using System.Diagnostics;
using System.IO;
using System.Windows;
using MainBrain.Desktop.Services;

namespace MainBrain.Desktop;

public partial class App : Application
{
    private BackendHost? _backend;

    protected override async void OnStartup(StartupEventArgs e)
    {
        base.OnStartup(e);
        DispatcherUnhandledException += (_, args) =>
        {
            MessageBox.Show(args.Exception.Message, "Main Brain OS kļūda", MessageBoxButton.OK, MessageBoxImage.Error);
            args.Handled = true;
        };

        _backend = new BackendHost();
        await _backend.StartAsync();
    }

    protected override async void OnExit(ExitEventArgs e)
    {
        if (_backend is not null)
        {
            await _backend.StopAsync();
        }

        base.OnExit(e);
    }
}
