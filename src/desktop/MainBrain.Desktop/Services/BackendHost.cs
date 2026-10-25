using System.Diagnostics;
using System.IO;
using System.Net.Http;
using System.Text;
using MainBrain.WinAutomation;

namespace MainBrain.Desktop.Services;

/// <summary>
/// Palaiž lokālo Python backend + Desktop Tool Bridge.
/// </summary>
public sealed class BackendHost : IDisposable
{
    private Process? _process;
    private Process? _llamaProcess;
    private ToolBridgeServer? _bridge;
    private readonly UiAutomationService _uia = new();
    private readonly InputService _input = new();
    private WindowCaptureService? _capture;
    private readonly string _logPath;

    public string BaseUrl { get; } = "http://127.0.0.1:8765";
    public string Token { get; private set; } = "";
    public ToolBridgeServer? Bridge => _bridge;

    public BackendHost()
    {
        var dataDir = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "MainBrainOS");
        Directory.CreateDirectory(Path.Combine(dataDir, "logs"));
        _logPath = Path.Combine(dataDir, "logs", "backend.log");
    }

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

        TryStartLlamaServer(dataDir);

        var root = ResolveAppRoot();
        var pythonPath = ResolvePythonPath(root);
        SyncBackendPackage(root);

        Log($"root={root}");
        Log($"python={ResolvePython(root)}");
        Log($"PYTHONPATH={pythonPath}");

        await FreePortAsync(8765);

        var python = ResolvePython(root);
        if (string.IsNullOrWhiteSpace(pythonPath) || !Directory.Exists(pythonPath))
        {
            throw new InvalidOperationException(
                "Nav atrasts Python backend (src\\backend vai backend). " +
                "Palaidiet FIX_BACKEND.bat no projekta mapes.");
        }

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
        psi.Environment["PYTHONPATH"] = pythonPath;
        psi.Environment["MAINBRAIN_API_TOKEN"] = Token;
        psi.Environment["MAINBRAIN_BRIDGE_TOKEN"] = Token;
        psi.Environment["MAINBRAIN_DATA_DIR"] = dataDir;
        psi.Environment["MAINBRAIN_OLLAMA_ENABLED"] = "false";
        psi.Environment["MAINBRAIN_PRIMARY_PROVIDER"] = "llama.cpp";
        psi.Environment["MAINBRAIN_LLAMA_BASE_URL"] = "http://127.0.0.1:8080/v1";
        // Lietotājs atļāvis: viss dators + internets (STOP joprojām pārtrauc)
        psi.Environment["MAINBRAIN_FULL_ACCESS"] = "true";
        psi.Environment["MAINBRAIN_OFFLINE_MODE"] = "false";

        _process = Process.Start(psi) ?? throw new InvalidOperationException("Neizdevās palaist Python.");
        _process.OutputDataReceived += (_, e) => { if (e.Data is not null) Log(e.Data); };
        _process.ErrorDataReceived += (_, e) => { if (e.Data is not null) Log(e.Data); };
        _process.BeginOutputReadLine();
        _process.BeginErrorReadLine();

        using var client = new HttpClient { Timeout = TimeSpan.FromSeconds(3) };
        Exception? last = null;
        for (var i = 0; i < 60; i++)
        {
            if (_process.HasExited)
            {
                var tail = ReadLogTail();
                throw new InvalidOperationException(
                    "Python backend aizvērās. Žurnāls:\n" + tail +
                    "\n\nPalaidiet FIX_BACKEND.bat");
            }

            try
            {
                var resp = await client.GetAsync($"{BaseUrl}/health");
                if (resp.IsSuccessStatusCode)
                {
                    Log("health OK");
                    return;
                }

                last = new Exception($"health {(int)resp.StatusCode}");
            }
            catch (Exception ex)
            {
                last = ex;
            }

            await Task.Delay(500);
        }

        throw new InvalidOperationException(
            "Backend nestartējās 30s laikā. " + (last?.Message ?? "") +
            "\nŽurnāls: " + _logPath + "\n" + ReadLogTail() +
            "\n\nPalaidiet FIX_BACKEND.bat no V.ai mapes.");
    }

    private void Log(string line)
    {
        try
        {
            File.AppendAllText(_logPath, $"[{DateTime.Now:HH:mm:ss}] {line}{Environment.NewLine}", Encoding.UTF8);
        }
        catch
        {
            // ignore
        }
    }

    private string ReadLogTail()
    {
        try
        {
            if (!File.Exists(_logPath))
            {
                return "(nav žurnāla)";
            }

            var lines = File.ReadAllLines(_logPath);
            return string.Join("\n", lines.TakeLast(30));
        }
        catch
        {
            return "(neizdevās nolasīt žurnālu)";
        }
    }

    /// <summary>Repo sakne (ar src) vai release mape.</summary>
    private static string ResolveAppRoot()
    {
        var baseDir = new DirectoryInfo(AppContext.BaseDirectory);

        // Vispirms meklē repo ar src\backend\mainbrain (īsto kodu)
        for (var dir = baseDir; dir is not null; dir = dir.Parent)
        {
            var srcBackend = Path.Combine(dir.FullName, "src", "backend", "mainbrain");
            if (Directory.Exists(srcBackend) &&
                File.Exists(Path.Combine(dir.FullName, "MainBrainOS.sln")))
            {
                return dir.FullName;
            }
        }

        for (var dir = baseDir; dir is not null; dir = dir.Parent)
        {
            if (Directory.Exists(Path.Combine(dir.FullName, "backend", "mainbrain")) ||
                File.Exists(Path.Combine(dir.FullName, "pyproject.toml")))
            {
                return dir.FullName;
            }
        }

        return AppContext.BaseDirectory;
    }

    private static string ResolvePythonPath(string root)
    {
        var src = Path.Combine(root, "src", "backend");
        var rel = Path.Combine(root, "backend");
        if (File.Exists(Path.Combine(src, "mainbrain", "brain", "chat.py")))
        {
            return src;
        }

        if (File.Exists(Path.Combine(rel, "mainbrain", "brain", "chat.py")))
        {
            return rel;
        }

        if (Directory.Exists(src))
        {
            return src;
        }

        if (Directory.Exists(rel))
        {
            return rel;
        }

        return "";
    }

    private static void SyncBackendPackage(string root)
    {
        var srcPkg = Path.Combine(root, "src", "backend", "mainbrain");
        var dstPkg = Path.Combine(root, "backend", "mainbrain");
        if (!Directory.Exists(srcPkg))
        {
            return;
        }

        try
        {
            CopyDirectory(srcPkg, dstPkg);
        }
        catch
        {
            // best effort
        }
    }

    private static void CopyDirectory(string src, string dst)
    {
        Directory.CreateDirectory(dst);
        foreach (var file in Directory.GetFiles(src, "*", SearchOption.AllDirectories))
        {
            var rel = Path.GetRelativePath(src, file);
            var target = Path.Combine(dst, rel);
            Directory.CreateDirectory(Path.GetDirectoryName(target)!);
            File.Copy(file, target, overwrite: true);
        }
    }

    private static async Task FreePortAsync(int port)
    {
        try
        {
            var psi = new ProcessStartInfo
            {
                FileName = "powershell",
                Arguments =
                    $"-NoProfile -Command \"Get-NetTCPConnection -LocalPort {port} -State Listen -ErrorAction SilentlyContinue | ForEach-Object {{ Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }}\"",
                UseShellExecute = false,
                CreateNoWindow = true,
            };
            using var p = Process.Start(psi);
            if (p is not null)
            {
                await p.WaitForExitAsync();
            }
        }
        catch
        {
            // ignore
        }

        await Task.Delay(500);
    }

    public async Task StopAsync()
    {
        _bridge?.EmergencyStop();
        if (_process is not null && !_process.HasExited)
        {
            try { _process.Kill(entireProcessTree: true); }
            catch { /* ignore */ }
        }

        if (_llamaProcess is not null && !_llamaProcess.HasExited)
        {
            try { _llamaProcess.Kill(entireProcessTree: true); }
            catch { /* ignore */ }
        }

        await Task.CompletedTask;
    }

    private void TryStartLlamaServer(string dataDir)
    {
        try
        {
            using var probe = new HttpClient { Timeout = TimeSpan.FromSeconds(1) };
            var existing = probe.GetAsync("http://127.0.0.1:8080/v1/models").GetAwaiter().GetResult();
            if ((int)existing.StatusCode < 500)
            {
                return;
            }
        }
        catch
        {
            // start
        }

        var exe = Path.Combine(dataDir, "llama", "llama-server.exe");
        if (!File.Exists(exe))
        {
            return;
        }

        var model = ResolveGguf(Path.Combine(dataDir, "models"));
        if (model is null)
        {
            return;
        }

        var psi = new ProcessStartInfo
        {
            FileName = exe,
            Arguments = $"-m \"{model}\" --host 127.0.0.1 --port 8080 -c 4096",
            WorkingDirectory = Path.GetDirectoryName(exe)!,
            UseShellExecute = false,
            CreateNoWindow = true,
        };
        _llamaProcess = Process.Start(psi);
    }

    private static string? ResolveGguf(string modelsDir)
    {
        var roles = Path.Combine(modelsDir, "roles.json");
        if (File.Exists(roles))
        {
            var json = File.ReadAllText(roles);
            foreach (var key in new[] { "reasoning", "coding" })
            {
                var marker = $"\"{key}\":\"";
                var idx = json.IndexOf(marker, StringComparison.OrdinalIgnoreCase);
                if (idx < 0)
                {
                    continue;
                }

                var start = idx + marker.Length;
                var end = json.IndexOf('"', start);
                if (end > start)
                {
                    var path = json[start..end].Replace("\\\\", "\\");
                    if (File.Exists(path))
                    {
                        return path;
                    }
                }
            }
        }

        if (!Directory.Exists(modelsDir))
        {
            return null;
        }

        return Directory.EnumerateFiles(modelsDir, "*.gguf")
            .OrderByDescending(f => new FileInfo(f).Length)
            .FirstOrDefault();
    }

    public void Dispose()
    {
        try { StopAsync().GetAwaiter().GetResult(); } catch { /* ignore */ }
        _bridge?.Dispose();
        _capture?.Dispose();
        _uia.Dispose();
    }

    private static string ResolvePython(string root)
    {
        var candidates = new[]
        {
            Path.Combine(root, "runtime-venv", "Scripts", "python.exe"),
            Path.Combine(root, "release", "win-x64", "runtime-venv", "Scripts", "python.exe"),
            Path.Combine(root, ".venv", "Scripts", "python.exe"),
            Path.Combine(root, "python", "python.exe"),
        };
        foreach (var c in candidates)
        {
            if (File.Exists(c))
            {
                return c;
            }
        }

        // py -3.12 launcher
        try
        {
            var psi = new ProcessStartInfo
            {
                FileName = "py",
                Arguments = "-3.12 -c \"import sys; print(sys.executable)\"",
                UseShellExecute = false,
                RedirectStandardOutput = true,
                CreateNoWindow = true,
            };
            using var p = Process.Start(psi);
            if (p is not null)
            {
                var path = p.StandardOutput.ReadToEnd().Trim();
                p.WaitForExit(3000);
                if (File.Exists(path))
                {
                    return path;
                }
            }
        }
        catch
        {
            // fall through
        }

        return OperatingSystem.IsWindows() ? "python" : "python3";
    }
}
