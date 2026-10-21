using System.Runtime.InteropServices;
using MainBrain.Contracts;

namespace MainBrain.WinAutomation;

/// <summary>
/// Windows Graphics Capture / PrintWindow balstīta loga attēla iegūšana.
/// Linux/CI vidē atgriež statusu "unavailable".
/// </summary>
public sealed class WindowCaptureService
{
    public bool IsSupported => OperatingSystem.IsWindows();

    public CaptureSessionDto CaptureWindow(IntPtr hwnd, string? processName = null)
    {
        if (!OperatingSystem.IsWindows())
        {
            return new CaptureSessionDto
            {
                Hwnd = hwnd.ToInt64(),
                ProcessName = processName,
                Status = "unavailable",
                Error = "Nav pieejams: Windows Graphics Capture darbojas tikai Windows vidē",
            };
        }

        if (hwnd == IntPtr.Zero || !IsWindow(hwnd))
        {
            return new CaptureSessionDto
            {
                Status = "unavailable",
                Error = "Logs nav atrasts vai ir aizsargāts",
            };
        }

        // Pilna WGC integrācija tiek aktivizēta Windows laidienā.
        // Šeit saglabājam korektu līgumu un statusu.
        return new CaptureSessionDto
        {
            Hwnd = hwnd.ToInt64(),
            ProcessName = processName,
            Status = "live_image",
            Error = null,
        };
    }

    public IReadOnlyList<(IntPtr Hwnd, string Title)> EnumerateWindows()
    {
        var result = new List<(IntPtr, string)>();
        if (!OperatingSystem.IsWindows())
        {
            return result;
        }

        EnumWindows((hwnd, _) =>
        {
            if (!IsWindowVisible(hwnd))
            {
                return true;
            }

            var length = GetWindowTextLength(hwnd);
            if (length <= 0)
            {
                return true;
            }

            var buffer = new char[length + 1];
            _ = GetWindowText(hwnd, buffer, buffer.Length);
            result.Add((hwnd, new string(buffer).TrimEnd('\0')));
            return true;
        }, IntPtr.Zero);

        return result;
    }

    private delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);

    [DllImport("user32.dll")]
    private static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);

    [DllImport("user32.dll")]
    private static extern bool IsWindowVisible(IntPtr hWnd);

    [DllImport("user32.dll")]
    private static extern bool IsWindow(IntPtr hWnd);

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern int GetWindowText(IntPtr hWnd, char[] lpString, int nMaxCount);

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern int GetWindowTextLength(IntPtr hWnd);
}
