using System.IO.Pipes;
using System.Security.AccessControl;
using System.Security.Principal;
using System.Text;
using System.Text.Json;

namespace MainBrain.WinAutomation;

/// <summary>
/// Autentificēts lokālais Named Pipe tilts Python ToolProxy → Windows komponentes.
/// </summary>
public sealed class ToolBridgeServer : IDisposable
{
    public const string DefaultPipeName = "MainBrainToolBridge";

    private readonly string _pipeName;
    private readonly string _token;
    private readonly UiAutomationService _uia;
    private readonly InputService _input;
    private readonly WindowCaptureService _capture;
    private readonly Func<JsonElement, Task<object>>? _browserHandler;
    private CancellationTokenSource? _cts;
    private Task? _loop;
    private readonly JsonSerializerOptions _json = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        PropertyNameCaseInsensitive = true,
    };

    public ToolBridgeServer(
        string token,
        UiAutomationService uia,
        InputService input,
        WindowCaptureService capture,
        Func<JsonElement, Task<object>>? browserHandler = null,
        string pipeName = DefaultPipeName)
    {
        _token = token;
        _uia = uia;
        _input = input;
        _capture = capture;
        _browserHandler = browserHandler;
        _pipeName = pipeName;
    }

    public void Start()
    {
        if (_loop is not null)
        {
            return;
        }

        _cts = new CancellationTokenSource();
        _loop = Task.Run(() => AcceptLoopAsync(_cts.Token));
    }

    public void EmergencyStop()
    {
        _uia.EmergencyStop();
        _input.EmergencyStop();
        _capture.EmergencyStop();
    }

    public void Resume()
    {
        _uia.Resume();
        _input.Resume();
        _capture.Resume();
    }

    private async Task AcceptLoopAsync(CancellationToken ct)
    {
        while (!ct.IsCancellationRequested)
        {
            try
            {
                await using var server = CreatePipe();
                await server.WaitForConnectionAsync(ct);
                _ = HandleClientAsync(server, ct);
            }
            catch (OperationCanceledException)
            {
                break;
            }
            catch
            {
                await Task.Delay(200, ct);
            }
        }
    }

    private NamedPipeServerStream CreatePipe()
    {
        // Tikai pašreizējais Windows lietotājs
        var security = new PipeSecurity();
        var sid = WindowsIdentity.GetCurrent().User
                  ?? new SecurityIdentifier(WellKnownSidType.BuiltinUsersSid, null);
        security.AddAccessRule(new PipeAccessRule(sid, PipeAccessRights.FullControl, AccessControlType.Allow));

        return NamedPipeServerStreamAcl.Create(
            _pipeName,
            PipeDirection.InOut,
            4,
            PipeTransmissionMode.Byte,
            PipeOptions.Asynchronous,
            0,
            0,
            security);
    }

    private async Task HandleClientAsync(NamedPipeServerStream server, CancellationToken ct)
    {
        using var reader = new StreamReader(server, Encoding.UTF8, leaveOpen: true);
        await using var writer = new StreamWriter(server, Encoding.UTF8, leaveOpen: true) { AutoFlush = true };

        while (server.IsConnected && !ct.IsCancellationRequested)
        {
            string? line;
            try
            {
                line = await reader.ReadLineAsync(ct);
            }
            catch
            {
                break;
            }

            if (line is null)
            {
                break;
            }

            object response;
            try
            {
                response = await DispatchAsync(line);
            }
            catch (Exception ex)
            {
                response = new { ok = false, error = ex.Message };
            }

            var payload = JsonSerializer.Serialize(response, _json);
            await writer.WriteLineAsync(payload);
        }
    }

    private async Task<object> DispatchAsync(string line)
    {
        using var doc = JsonDocument.Parse(line);
        var root = doc.RootElement;
        var token = root.TryGetProperty("token", out var t) ? t.GetString() : null;
        if (!string.Equals(token, _token, StringComparison.Ordinal))
        {
            return new { ok = false, error = "Neautorizēts tilta pieprasījums", correlation_id = Get(root, "correlation_id") };
        }

        var tool = Get(root, "tool") ?? "";
        var args = root.TryGetProperty("arguments", out var a) ? a : default;
        var correlationId = Get(root, "correlation_id") ?? Guid.NewGuid().ToString("N");
        var owner = Get(root, "agent_id") ?? correlationId;

        object result = tool switch
        {
            "window.enumerate" => new { status = "ok", windows = _capture.EnumerateWindows() },
            "window.inspect" => _capture.InspectWindow(Hwnd(args)),
            "window.focus" => _capture.FocusWindow(Hwnd(args)),
            "window.resize" => _capture.ResizeWindow(
                Hwnd(args),
                IntArg(args, "x"),
                IntArg(args, "y"),
                IntArg(args, "width", 800),
                IntArg(args, "height", 600)),
            "window.capture" => _capture.CaptureWindow(Hwnd(args), Str(args, "process_name"), Str(args, "session_id")),
            "screen.capture" => _capture.CaptureWindow(Hwnd(args), Str(args, "process_name")),
            "uia.query" => _uia.Query(Str(args, "selector") ?? Str(args, "query") ?? "", LongArg(args, "hwnd"), IntArg(args, "timeout_ms", 5000)),
            "uia.invoke" => _uia.Invoke(Str(args, "selector") ?? "", LongArg(args, "hwnd"), IntArg(args, "timeout_ms", 5000)),
            "uia.set_value" => _uia.SetValue(Str(args, "selector") ?? "", Str(args, "value") ?? "", LongArg(args, "hwnd"), IntArg(args, "timeout_ms", 5000)),
            "uia.tree" => _uia.GetTree(LongArg(args, "hwnd"), IntArg(args, "max_depth", 4)),
            "uia.find_window" => _uia.FindWindow(Str(args, "title"), Str(args, "process_name"), IntNullable(args, "pid")),
            "input.click" => _input.Click(owner, IntArg(args, "x"), IntArg(args, "y"), Str(args, "button") ?? "left", IntArg(args, "clicks", 1)),
            "input.type" => _input.TypeText(owner, Str(args, "text") ?? "", LongArg(args, "hwnd")),
            "input.shortcut" => _input.Shortcut(owner, Str(args, "keys") ?? "", LongArg(args, "hwnd")),
            "input.move" => _input.Move(owner, IntArg(args, "x"), IntArg(args, "y")),
            "bridge.ping" => new { status = "pong", platform = "windows" },
            "bridge.stop" => StopAll(),
            _ when tool.StartsWith("browser.", StringComparison.Ordinal) =>
                _browserHandler is null
                    ? new { status = "unavailable", message = "Pārlūka handler nav reģistrēts" }
                    : await _browserHandler(root),
            _ => new { status = "unknown_tool", tool, performed = false },
        };

        return new
        {
            ok = true,
            tool,
            correlation_id = correlationId,
            result,
            timestamp = DateTime.UtcNow,
        };
    }

    private object StopAll()
    {
        EmergencyStop();
        return new { status = "stopped", performed = true };
    }

    private static string? Get(JsonElement root, string name) =>
        root.TryGetProperty(name, out var p) ? p.GetString() : null;

    private static string? Str(JsonElement args, string name)
    {
        if (args.ValueKind != JsonValueKind.Object || !args.TryGetProperty(name, out var p))
        {
            return null;
        }

        return p.ValueKind == JsonValueKind.String ? p.GetString() : p.ToString();
    }

    private static int IntArg(JsonElement args, string name, int fallback = 0)
    {
        if (args.ValueKind != JsonValueKind.Object || !args.TryGetProperty(name, out var p))
        {
            return fallback;
        }

        return p.TryGetInt32(out var v) ? v : fallback;
    }

    private static int? IntNullable(JsonElement args, string name)
    {
        if (args.ValueKind != JsonValueKind.Object || !args.TryGetProperty(name, out var p))
        {
            return null;
        }

        return p.TryGetInt32(out var v) ? v : null;
    }

    private static long? LongArg(JsonElement args, string name)
    {
        if (args.ValueKind != JsonValueKind.Object || !args.TryGetProperty(name, out var p))
        {
            return null;
        }

        return p.TryGetInt64(out var v) ? v : null;
    }

    private static IntPtr Hwnd(JsonElement args)
    {
        var value = LongArg(args, "hwnd") ?? 0;
        return new IntPtr(value);
    }

    public void Dispose()
    {
        _cts?.Cancel();
        _uia.Dispose();
        _capture.Dispose();
    }
}
