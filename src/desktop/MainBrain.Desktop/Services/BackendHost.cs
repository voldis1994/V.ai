using System.Diagnostics;
using System.IO;
using System.Net.Http;
using MainBrain.WinAutomation;

namespace MainBrain.Desktop.Services;

/// <summary>
/// Palaiž lokālo Python backend + Desktop Tool Bridge.
/// Atbalsta gan repo izstrādi, gan publicētu laidienu.
/// </summary>
public sealed class BackendHost : IDisposable
{
    private Process? _process;
    private ToolBridgeServer? _bridge;
    private readonly UiAutomationService _uia = new();
    private readonly InputService _input = new();
    private WindowCaptureService? _capture;

    public string BaseUrl { get; } = "http://127.0.0.1:8765";
    public string Token { get; private set; } = "";
    public ToolBridgeServer? Bridge => _bridge;

    public async Task StartAsync(Func<System.Text.Json.JsonElement, Task<object>>? browserHandler = null)
    {
        Token = Environment.GetEnvironmentVariable("MAINBRAIN_API_TOKEN") ?? Guid.NewGuid().ToString("N");
        var dataDir = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "MainBrainOS");
        Directory.CreateDirectory(dataDir);
        _capture = new WindowCaptureService(Path.Combine(dataDir, "captures"));

        _bridge = new ToolBridgeServer(Token, _uia, _input, _capture, browserHandler);
        _bridge.Start();

        var root = ResolveAppRoot();
        var python = ResolvePython(root);
        var psi = new ProcessStartInfo
        {
            FileName = python,
            Arguments = "-m mainbrain.api",
            WorkingDirectory = root,
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
        };
        psi.Environment["MAINBRAIN_API_TOKEN"] = Token;
        psi.Environment["MAINBRAIN_BRIDGE_TOKEN"] = Token;
        psi.Environment["MAINBRAIN_DATA_DIR"] = dataDir;

        var backendPath = Path.Combine(root, "backend");
        var srcBackend = Path.Combine(root, "src", "backend");
        if (Directory.Exists(backendPath))
        {
            psi.Environment["PYTHONPATH"] = backendPath;
        }
        else if (Directory.Exists(srcBackend))
        {
            psi.Environment["PYTHONPATH"] = srcBackend;
        }

        _process = Process.Start(psi);

        using var client = new HttpClient { Timeout = TimeSpan.FromSeconds(2) };
        for (var i = 0; i < 60; i++)
        {
            try
            {
                var resp = await client.GetAsync($"{BaseUrl}/health");
                if (resp.IsSuccessStatusCode)
                {
                    return;
                }
            }
            catch
            {
                // gaida
            }

            await Task.Delay(250);
        }

        throw new InvalidOperationException(
            "Backend nestartējās. Pārbaudiet Python instalāciju un laidiena backend mapi.");
    }

    public async Task StopAsync()
    {
        _bridge?.EmergencyStop();
        if (_process is not null && !_process.HasExited)
        {
            try { _process.Kill(entireProcessTree: true); }
            catch { /* ignore */ }
        }

        await Task.CompletedTask;
    }

    public void Dispose()
    {
        _bridge?.Dispose();
        _capture?.Dispose();
        _uia.Dispose();
    }

    private static string ResolveAppRoot()
    {
        var baseDir = new DirectoryInfo(AppContext.BaseDirectory);
        // 1) Laidiena mape ar backend/
        if (Directory.Exists(Path.Combine(baseDir.FullName, "backend")))
        {
            return baseDir.FullName;
        }

        // 2) Repo sakne
        var dir = baseDir;
        while (dir is not null)
        {
            if (File.Exists(Path.Combine(dir.FullName, "MainBrainOS.sln")) ||
                File.Exists(Path.Combine(dir.FullName, "pyproject.toml")))
            {
                return dir.FullName;
            }

            dir = dir.Parent;
        }

        return AppContext.BaseDirectory;
    }

    private static string ResolvePython(string root)
    {
        var candidates = new[]
        {
            Path.Combine(root, "runtime-venv", "Scripts", "python.exe"),
            Path.Combine(root, "python", "python.exe"),
            Path.Combine(root, "runtime", "python.exe"),
            Path.Combine(root, ".venv", "Scripts", "python.exe"),
            Path.Combine(root, ".venv", "bin", "python"),
            Path.Combine(root, "backend", ".venv", "Scripts", "python.exe"),
        };
        foreach (var c in candidates)
        {
            if (File.Exists(c))
            {
                return c;
            }
        }

        return OperatingSystem.IsWindows() ? "python" : "python3";
    }
}
