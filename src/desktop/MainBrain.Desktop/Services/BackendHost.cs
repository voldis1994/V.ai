using System.Diagnostics;
using System.IO;
using System.Net.Http;

namespace MainBrain.Desktop.Services;

/// <summary>
/// Palaiž lokālo Python FastAPI backend kā atbalsta procesu bez konsoles loga.
/// </summary>
public sealed class BackendHost
{
    private Process? _process;
    public string BaseUrl { get; } = "http://127.0.0.1:8765";
    public string? Token { get; private set; }

    public async Task StartAsync()
    {
        var root = FindRepoRoot();
        var python = ResolvePython(root);
        var env = Environment.GetEnvironmentVariable("MAINBRAIN_API_TOKEN") ?? Guid.NewGuid().ToString("N");
        Token = env;

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
        psi.Environment["MAINBRAIN_API_TOKEN"] = env;
        psi.Environment["PYTHONPATH"] = Path.Combine(root, "src", "backend");
        // Windows: pythonw preferējams, ja pieejams
        _process = Process.Start(psi);

        using var client = new HttpClient { Timeout = TimeSpan.FromSeconds(2) };
        for (var i = 0; i < 40; i++)
        {
            try
            {
                var resp = await client.GetAsync($"{BaseUrl}/health");
                if (resp.IsSuccessStatusCode)
                {
                    // pārliecinās par tokenu
                    var tokenResp = await client.GetAsync($"{BaseUrl}/auth/token");
                    if (tokenResp.IsSuccessStatusCode)
                    {
                        var json = await tokenResp.Content.ReadAsStringAsync();
                        var marker = "\"token\":\"";
                        var idx = json.IndexOf(marker, StringComparison.Ordinal);
                        if (idx >= 0)
                        {
                            var start = idx + marker.Length;
                            var end = json.IndexOf('"', start);
                            Token = json[start..end];
                        }
                    }
                    return;
                }
            }
            catch
            {
                // gaida startu
            }

            await Task.Delay(250);
        }
    }

    public async Task StopAsync()
    {
        if (_process is null || _process.HasExited)
        {
            return;
        }

        try
        {
            _process.Kill(entireProcessTree: true);
        }
        catch
        {
            // ignore
        }

        await Task.CompletedTask;
    }

    private static string FindRepoRoot()
    {
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
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
        var venvUnix = Path.Combine(root, ".venv", "bin", "python");
        var venvWin = Path.Combine(root, ".venv", "Scripts", "python.exe");
        if (File.Exists(venvWin))
        {
            return venvWin;
        }

        if (File.Exists(venvUnix))
        {
            return venvUnix;
        }

        return OperatingSystem.IsWindows() ? "python" : "python3";
    }
}
