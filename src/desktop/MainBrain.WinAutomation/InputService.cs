using System.Runtime.InteropServices;

namespace MainBrain.WinAutomation;

/// <summary>
/// SendInput ar ekskluzīvu fiziskās ievades īpašnieku un STOP atbalstu.
/// </summary>
public sealed class InputService
{
    private readonly object _gate = new();
    private string? _owner;
    private volatile bool _stopped;

    public bool IsSupported => OperatingSystem.IsWindows();
    public string? CurrentOwner
    {
        get { lock (_gate) return _owner; }
    }

    public void EmergencyStop()
    {
        _stopped = true;
        lock (_gate)
        {
            _owner = null;
        }
    }

    public void Resume() => _stopped = false;

    public bool TryAcquire(string owner)
    {
        if (_stopped)
        {
            return false;
        }

        lock (_gate)
        {
            if (_owner is not null && _owner != owner)
            {
                return false;
            }

            _owner = owner;
            return true;
        }
    }

    public void Release(string owner)
    {
        lock (_gate)
        {
            if (_owner == owner)
            {
                _owner = null;
            }
        }
    }

    public object Move(string owner, int x, int y, bool absolute = true)
    {
        return WithOwner(owner, () =>
        {
            if (absolute)
            {
                var (ax, ay) = ToAbsolute(x, y);
                SendMouse(ax, ay, NativeMethods.MOUSEEVENTF_MOVE | NativeMethods.MOUSEEVENTF_ABSOLUTE | NativeMethods.MOUSEEVENTF_VIRTUALDESK);
            }
            else
            {
                NativeMethods.SetCursorPos(x, y);
            }

            return new { status = "moved", performed = true, x, y, absolute };
        });
    }

    public object Click(string owner, int x, int y, string button = "left", int clicks = 1)
    {
        return WithOwner(owner, () =>
        {
            var (ax, ay) = ToAbsolute(x, y);
            SendMouse(ax, ay, NativeMethods.MOUSEEVENTF_MOVE | NativeMethods.MOUSEEVENTF_ABSOLUTE | NativeMethods.MOUSEEVENTF_VIRTUALDESK);
            var (down, up) = button.Equals("right", StringComparison.OrdinalIgnoreCase)
                ? (NativeMethods.MOUSEEVENTF_RIGHTDOWN, NativeMethods.MOUSEEVENTF_RIGHTUP)
                : (NativeMethods.MOUSEEVENTF_LEFTDOWN, NativeMethods.MOUSEEVENTF_LEFTUP);

            for (var i = 0; i < Math.Max(1, clicks); i++)
            {
                if (_stopped)
                {
                    return new { status = "stopped", performed = false, completed_clicks = i };
                }

                SendMouse(0, 0, down);
                Thread.Sleep(20);
                SendMouse(0, 0, up);
                Thread.Sleep(40);
            }

            return new { status = "clicked", performed = true, x, y, button, clicks };
        });
    }

    public object TypeText(string owner, string text, long? ensureForegroundHwnd = null)
    {
        return WithOwner(owner, () =>
        {
            if (ensureForegroundHwnd is not null && ensureForegroundHwnd != 0)
            {
                var hwnd = new IntPtr(ensureForegroundHwnd.Value);
                if (!EnsureForeground(hwnd))
                {
                    return new
                    {
                        status = "focus_failed",
                        performed = false,
                        message = "Neizdevās aktivizēt mērķa logu pirms ievades",
                    };
                }
            }

            var sent = 0;
            foreach (var ch in text)
            {
                if (_stopped)
                {
                    return new { status = "stopped", performed = false, chars_sent = sent };
                }

                SendUnicode(ch, keyUp: false);
                SendUnicode(ch, keyUp: true);
                sent++;
            }

            return new { status = "typed", performed = true, chars = sent };
        });
    }

    public object Shortcut(string owner, string keys, long? ensureForegroundHwnd = null)
    {
        return WithOwner(owner, () =>
        {
            if (ensureForegroundHwnd is not null && ensureForegroundHwnd != 0)
            {
                EnsureForeground(new IntPtr(ensureForegroundHwnd.Value));
            }

            var parts = keys.Split('+', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
            var vkList = new List<ushort>();
            foreach (var part in parts)
            {
                vkList.Add(MapKey(part));
            }

            foreach (var vk in vkList)
            {
                SendVk(vk, keyUp: false);
            }

            for (var i = vkList.Count - 1; i >= 0; i--)
            {
                SendVk(vkList[i], keyUp: true);
            }

            return new { status = "shortcut", performed = true, keys };
        });
    }

    private object WithOwner(string owner, Func<object> action)
    {
        if (!IsSupported)
        {
            return new { status = "unavailable", performed = false, message = "SendInput pieejams tikai Windows" };
        }

        if (_stopped)
        {
            return new { status = "stopped", performed = false, message = "STOP aktīvs — ievade aizliegta" };
        }

        if (!TryAcquire(owner))
        {
            return new
            {
                status = "blocked",
                performed = false,
                message = "Ievades fokusu tur cits operators",
                owner = CurrentOwner,
            };
        }

        try
        {
            return action();
        }
        catch (Exception ex)
        {
            return new { status = "error", performed = false, message = ex.Message };
        }
        finally
        {
            Release(owner);
        }
    }

    private static bool EnsureForeground(IntPtr hwnd)
    {
        if (!NativeMethods.IsWindow(hwnd))
        {
            return false;
        }

        if (NativeMethods.IsIconic(hwnd))
        {
            NativeMethods.ShowWindow(hwnd, NativeMethods.SW_RESTORE);
        }

        NativeMethods.SetForegroundWindow(hwnd);
        Thread.Sleep(50);
        return NativeMethods.GetForegroundWindow() == hwnd || NativeMethods.IsWindowVisible(hwnd);
    }

    private static (int x, int y) ToAbsolute(int x, int y)
    {
        var vx = NativeMethods.GetSystemMetrics(NativeMethods.SM_XVIRTUALSCREEN);
        var vy = NativeMethods.GetSystemMetrics(NativeMethods.SM_YVIRTUALSCREEN);
        var vw = Math.Max(1, NativeMethods.GetSystemMetrics(NativeMethods.SM_CXVIRTUALSCREEN));
        var vh = Math.Max(1, NativeMethods.GetSystemMetrics(NativeMethods.SM_CYVIRTUALSCREEN));
        var ax = (int)Math.Round((x - vx) * 65535.0 / vw);
        var ay = (int)Math.Round((y - vy) * 65535.0 / vh);
        return (ax, ay);
    }

    private static void SendMouse(int dx, int dy, uint flags)
    {
        var input = new NativeMethods.INPUT
        {
            type = NativeMethods.INPUT_MOUSE,
            U = new NativeMethods.InputUnion
            {
                mi = new NativeMethods.MOUSEINPUT
                {
                    dx = dx,
                    dy = dy,
                    dwFlags = flags,
                },
            },
        };
        var sent = NativeMethods.SendInput(1, new[] { input }, Marshal.SizeOf<NativeMethods.INPUT>());
        if (sent != 1)
        {
            throw new InvalidOperationException($"SendInput pelei neizdevās (GetLastError={Marshal.GetLastWin32Error()})");
        }
    }

    private static void SendUnicode(char ch, bool keyUp)
    {
        var input = new NativeMethods.INPUT
        {
            type = NativeMethods.INPUT_KEYBOARD,
            U = new NativeMethods.InputUnion
            {
                ki = new NativeMethods.KEYBDINPUT
                {
                    wVk = 0,
                    wScan = ch,
                    dwFlags = NativeMethods.KEYEVENTF_UNICODE | (keyUp ? NativeMethods.KEYEVENTF_KEYUP : 0),
                },
            },
        };
        var sent = NativeMethods.SendInput(1, new[] { input }, Marshal.SizeOf<NativeMethods.INPUT>());
        if (sent != 1)
        {
            throw new InvalidOperationException("SendInput tastatūrai neizdevās");
        }
    }

    private static void SendVk(ushort vk, bool keyUp)
    {
        var input = new NativeMethods.INPUT
        {
            type = NativeMethods.INPUT_KEYBOARD,
            U = new NativeMethods.InputUnion
            {
                ki = new NativeMethods.KEYBDINPUT
                {
                    wVk = vk,
                    wScan = 0,
                    dwFlags = keyUp ? NativeMethods.KEYEVENTF_KEYUP : 0,
                },
            },
        };
        NativeMethods.SendInput(1, new[] { input }, Marshal.SizeOf<NativeMethods.INPUT>());
    }

    private static ushort MapKey(string key)
    {
        return key.ToLowerInvariant() switch
        {
            "ctrl" or "control" => 0x11,
            "alt" => 0x12,
            "shift" => 0x10,
            "win" or "meta" => 0x5B,
            "enter" or "return" => 0x0D,
            "tab" => 0x09,
            "esc" or "escape" => 0x1B,
            "backspace" => 0x08,
            "delete" or "del" => 0x2E,
            "space" => 0x20,
            "f1" => 0x70,
            "f2" => 0x71,
            "f3" => 0x72,
            "f4" => 0x73,
            "f5" => 0x74,
            "a" => 0x41,
            "c" => 0x43,
            "v" => 0x56,
            "x" => 0x58,
            "s" => 0x53,
            "z" => 0x5A,
            _ when key.Length == 1 => (ushort)char.ToUpperInvariant(key[0]),
            _ => throw new ArgumentException($"Nezināms taustiņš: {key}"),
        };
    }
}
