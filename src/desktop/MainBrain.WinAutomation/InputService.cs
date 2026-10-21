using System.Runtime.InteropServices;

namespace MainBrain.WinAutomation;

/// <summary>
/// SendInput rezerves ievade ar ekskluzīvu fokusa bloķēšanu.
/// </summary>
public sealed class InputService
{
    private readonly object _gate = new();
    private string? _owner;

    public bool TryAcquire(string owner)
    {
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

    public object TypeText(string owner, string text)
    {
        if (!TryAcquire(owner))
        {
            return new { status = "blocked", message = "Ievades fokusu tur cits operators" };
        }

        try
        {
            if (!OperatingSystem.IsWindows())
            {
                return new { status = "unavailable", message = "SendInput pieejams tikai Windows" };
            }

            // Windows laidienā šeit tiktu izsaukts SendInput.
            return new { status = "queued", chars = text.Length };
        }
        finally
        {
            Release(owner);
        }
    }

    [DllImport("user32.dll")]
    private static extern uint SendInput(uint nInputs, IntPtr pInputs, int cbSize);
}
