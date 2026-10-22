using System.Drawing;
using System.Drawing.Imaging;
using MainBrain.Contracts;

namespace MainBrain.WinAutomation;

/// <summary>
/// Īsta loga uztveršana ar PrintWindow + BitBlt rezerves ceļu.
/// Atgriež live_image TIKAI ja kadrs ir saglabāts diskā.
/// </summary>
public sealed class WindowCaptureService : IDisposable
{
    private readonly object _gate = new();
    private readonly Dictionary<string, CaptureSession> _sessions = new();
    private readonly string _framesDir;
    private volatile bool _stopped;

    public WindowCaptureService(string? framesDir = null)
    {
        _framesDir = framesDir ?? Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "MainBrainOS",
            "captures");
        Directory.CreateDirectory(_framesDir);
    }

    public bool IsSupported => OperatingSystem.IsWindows();

    public void EmergencyStop()
    {
        _stopped = true;
        lock (_gate)
        {
            foreach (var s in _sessions.Values)
            {
                s.Active = false;
            }
        }
    }

    public void Resume() => _stopped = false;

    public IReadOnlyList<object> EnumerateWindows()
    {
        var result = new List<object>();
        if (!IsSupported)
        {
            return result;
        }

        NativeMethods.EnumWindows((hwnd, _) =>
        {
            if (!NativeMethods.IsWindowVisible(hwnd))
            {
                return true;
            }

            var length = NativeMethods.GetWindowTextLength(hwnd);
            if (length <= 0)
            {
                return true;
            }

            var buffer = new char[length + 1];
            _ = NativeMethods.GetWindowText(hwnd, buffer, buffer.Length);
            NativeMethods.GetWindowThreadProcessId(hwnd, out var pid);
            result.Add(new
            {
                hwnd = hwnd.ToInt64(),
                title = new string(buffer).TrimEnd('\0'),
                process_id = pid,
                minimized = NativeMethods.IsIconic(hwnd),
            });
            return true;
        }, IntPtr.Zero);

        return result;
    }

    public CaptureSessionDto CaptureWindow(IntPtr hwnd, string? processName = null, string? sessionId = null)
    {
        if (!IsSupported)
        {
            return Unavailable(hwnd, processName, "Nav pieejams: logu uztveršana darbojas tikai Windows");
        }

        if (_stopped)
        {
            return Unavailable(hwnd, processName, "STOP aktīvs — uztveršana apturēta");
        }

        if (hwnd == IntPtr.Zero || !NativeMethods.IsWindow(hwnd))
        {
            return Unavailable(hwnd, processName, "Logs nav atrasts");
        }

        if (NativeMethods.IsIconic(hwnd))
        {
            return Unavailable(hwnd, processName, "Logs ir minimizēts — Nav pieejams");
        }

        if (!NativeMethods.GetWindowRect(hwnd, out var rect))
        {
            return Unavailable(hwnd, processName, "Neizdevās nolasīt loga izmēru");
        }

        var width = Math.Max(1, rect.Right - rect.Left);
        var height = Math.Max(1, rect.Bottom - rect.Top);
        if (width < 2 || height < 2)
        {
            return Unavailable(hwnd, processName, "Logs ir pārāk mazs vai aizsargāts");
        }

        try
        {
            using var bitmap = CaptureBitmap(hwnd, width, height);
            if (bitmap is null)
            {
                return Unavailable(hwnd, processName, "Neizdevās iegūt kadru (PrintWindow/BitBlt)");
            }

            // Tukša/melna kadra heuristika — aizsargāti logi bieži atgriež tukšu saturu
            if (IsMostlyEmpty(bitmap))
            {
                return Unavailable(hwnd, processName, "Logs aizsargāts vai saturs nav uztverams");
            }

            var id = sessionId ?? Guid.NewGuid().ToString("N");
            var path = Path.Combine(_framesDir, $"{id}.png");
            bitmap.Save(path, ImageFormat.Png);

            lock (_gate)
            {
                _sessions[id] = new CaptureSession
                {
                    Id = id,
                    Hwnd = hwnd,
                    ProcessName = processName,
                    FramePath = path,
                    Active = true,
                    UpdatedAt = DateTime.UtcNow,
                };
            }

            return new CaptureSessionDto
            {
                Id = id,
                Hwnd = hwnd.ToInt64(),
                ProcessName = processName,
                Status = "live_image",
                FramePath = path,
                Error = null,
                UpdatedAt = DateTime.UtcNow,
            };
        }
        catch (Exception ex)
        {
            return Unavailable(hwnd, processName, ex.Message);
        }
    }

    public CaptureSessionDto? RefreshSession(string sessionId)
    {
        CaptureSession? session;
        lock (_gate)
        {
            _sessions.TryGetValue(sessionId, out session);
        }

        if (session is null || !session.Active)
        {
            return null;
        }

        return CaptureWindow(session.Hwnd, session.ProcessName, session.Id);
    }

    public bool StopSession(string sessionId)
    {
        lock (_gate)
        {
            if (_sessions.TryGetValue(sessionId, out var session))
            {
                session.Active = false;
                return true;
            }
        }

        return false;
    }

    public object FocusWindow(IntPtr hwnd)
    {
        if (!IsSupported)
        {
            return new { status = "unavailable", performed = false };
        }

        if (!NativeMethods.IsWindow(hwnd))
        {
            return new { status = "not_found", performed = false };
        }

        if (NativeMethods.IsIconic(hwnd))
        {
            NativeMethods.ShowWindow(hwnd, NativeMethods.SW_RESTORE);
        }

        var ok = NativeMethods.SetForegroundWindow(hwnd);
        return new { status = ok ? "focused" : "failed", performed = ok, hwnd = hwnd.ToInt64() };
    }

    public object ResizeWindow(IntPtr hwnd, int x, int y, int width, int height)
    {
        if (!IsSupported)
        {
            return new { status = "unavailable", performed = false };
        }

        if (!NativeMethods.IsWindow(hwnd))
        {
            return new { status = "not_found", performed = false };
        }

        var ok = NativeMethods.MoveWindow(hwnd, x, y, width, height, true);
        return new { status = ok ? "resized" : "failed", performed = ok };
    }

    public object InspectWindow(IntPtr hwnd)
    {
        if (!IsSupported || !NativeMethods.IsWindow(hwnd))
        {
            return new { status = "unavailable" };
        }

        NativeMethods.GetWindowRect(hwnd, out var rect);
        NativeMethods.GetWindowThreadProcessId(hwnd, out var pid);
        var len = NativeMethods.GetWindowTextLength(hwnd);
        var buf = new char[Math.Max(1, len + 1)];
        NativeMethods.GetWindowText(hwnd, buf, buf.Length);
        return new
        {
            status = "ok",
            hwnd = hwnd.ToInt64(),
            title = new string(buf).TrimEnd('\0'),
            process_id = pid,
            minimized = NativeMethods.IsIconic(hwnd),
            visible = NativeMethods.IsWindowVisible(hwnd),
            bounds = new { x = rect.Left, y = rect.Top, width = rect.Right - rect.Left, height = rect.Bottom - rect.Top },
        };
    }

    private static Bitmap? CaptureBitmap(IntPtr hwnd, int width, int height)
    {
        var hdcWindow = NativeMethods.GetDC(hwnd);
        if (hdcWindow == IntPtr.Zero)
        {
            return null;
        }

        var hdcMem = NativeMethods.CreateCompatibleDC(hdcWindow);
        var hBitmap = NativeMethods.CreateCompatibleBitmap(hdcWindow, width, height);
        var old = NativeMethods.SelectObject(hdcMem, hBitmap);

        var printed = NativeMethods.PrintWindow(hwnd, hdcMem, NativeMethods.PW_RENDERFULLCONTENT);
        if (!printed)
        {
            // rezerves: BitBlt no loga DC
            NativeMethods.BitBlt(hdcMem, 0, 0, width, height, hdcWindow, 0, 0, NativeMethods.SRCCOPY);
        }

        var bitmap = Image.FromHbitmap(hBitmap);
        NativeMethods.SelectObject(hdcMem, old);
        NativeMethods.DeleteObject(hBitmap);
        NativeMethods.DeleteDC(hdcMem);
        NativeMethods.ReleaseDC(hwnd, hdcWindow);
        return bitmap;
    }

    private static bool IsMostlyEmpty(Bitmap bitmap)
    {
        // paraugs no stūriem un centra — ja visi gandrīz melni, uzskata par tukšu
        var points = new[]
        {
            (1, 1),
            (bitmap.Width - 2, 1),
            (1, bitmap.Height - 2),
            (bitmap.Width - 2, bitmap.Height - 2),
            (bitmap.Width / 2, bitmap.Height / 2),
        };
        var dark = 0;
        foreach (var (x, y) in points)
        {
            if (x < 0 || y < 0 || x >= bitmap.Width || y >= bitmap.Height)
            {
                continue;
            }

            var c = bitmap.GetPixel(x, y);
            if (c.R < 8 && c.G < 8 && c.B < 8)
            {
                dark++;
            }
        }

        return dark >= 4;
    }

    private static CaptureSessionDto Unavailable(IntPtr hwnd, string? processName, string error) =>
        new()
        {
            Id = Guid.NewGuid().ToString("N"),
            Hwnd = hwnd == IntPtr.Zero ? null : hwnd.ToInt64(),
            ProcessName = processName,
            Status = "unavailable",
            FramePath = null,
            Error = error,
            UpdatedAt = DateTime.UtcNow,
        };

    public void Dispose()
    {
        lock (_gate)
        {
            _sessions.Clear();
        }
    }

    private sealed class CaptureSession
    {
        public required string Id { get; init; }
        public IntPtr Hwnd { get; init; }
        public string? ProcessName { get; init; }
        public string? FramePath { get; set; }
        public bool Active { get; set; }
        public DateTime UpdatedAt { get; set; }
    }
}
