using System.Diagnostics;
using FlaUI.Core;
using FlaUI.Core.AutomationElements;
using FlaUI.Core.Conditions;
using FlaUI.Core.Definitions;
using FlaUI.UIA3;

namespace MainBrain.WinAutomation;

/// <summary>
/// Īsta Microsoft UI Automation (UIA3 caur FlaUI) — bez fake invoked/set.
/// </summary>
public sealed class UiAutomationService : IDisposable
{
    private readonly object _gate = new();
    private UIA3Automation? _automation;
    private bool _stopped;

    public bool IsSupported => OperatingSystem.IsWindows();

    public void EmergencyStop()
    {
        _stopped = true;
    }

    public void Resume()
    {
        _stopped = false;
    }

    public object FindWindow(string? titleContains = null, string? processName = null, int? pid = null)
    {
        if (!EnsureReady(out var err))
        {
            return err;
        }

        try
        {
            using var automation = GetAutomation();
            var desktop = automation.GetDesktop();
            var windows = desktop.FindAllChildren(cf => cf.ByControlType(ControlType.Window));
            var matches = new List<object>();
            foreach (var w in windows)
            {
                string title;
                try { title = w.Name ?? ""; }
                catch { continue; }

                var procId = 0;
                try { procId = w.Properties.ProcessId.ValueOrDefault; }
                catch { /* ignore */ }

                string? pname = null;
                try
                {
                    if (procId > 0)
                    {
                        pname = Process.GetProcessById(procId).ProcessName;
                    }
                }
                catch { /* ignore */ }

                if (!string.IsNullOrWhiteSpace(titleContains) &&
                    title.IndexOf(titleContains, StringComparison.OrdinalIgnoreCase) < 0)
                {
                    continue;
                }

                if (!string.IsNullOrWhiteSpace(processName) &&
                    (pname is null || !pname.Equals(processName, StringComparison.OrdinalIgnoreCase)))
                {
                    continue;
                }

                if (pid is not null && procId != pid.Value)
                {
                    continue;
                }

                matches.Add(new
                {
                    hwnd = w.Properties.NativeWindowHandle.ValueOrDefault.ToInt64(),
                    title,
                    process_id = procId,
                    process_name = pname,
                    automation_id = Safe(() => w.AutomationId),
                    class_name = Safe(() => w.ClassName),
                });
            }

            return new { status = "ok", count = matches.Count, windows = matches };
        }
        catch (Exception ex)
        {
            return Fail(ex.Message);
        }
    }

    public object Query(string selector, long? hwnd = null, int timeoutMs = 5000)
    {
        if (!EnsureReady(out var err))
        {
            return err;
        }

        try
        {
            using var automation = GetAutomation();
            var root = ResolveRoot(automation, hwnd);
            var element = FindElement(root, selector, timeoutMs);
            if (element is null)
            {
                return new { status = "not_found", query = selector, message = "Elements nav atrasts" };
            }

            return new
            {
                status = "ok",
                query = selector,
                name = Safe(() => element.Name),
                automation_id = Safe(() => element.AutomationId),
                control_type = Safe(() => element.ControlType.ToString()),
                class_name = Safe(() => element.ClassName),
                is_enabled = SafeBool(() => element.IsEnabled),
                is_offscreen = SafeBool(() => element.IsOffscreen),
                bounding_rectangle = DescribeRect(element),
            };
        }
        catch (Exception ex)
        {
            return Fail(ex.Message);
        }
    }

    public object GetTree(long? hwnd = null, int maxDepth = 4)
    {
        if (!EnsureReady(out var err))
        {
            return err;
        }

        try
        {
            using var automation = GetAutomation();
            var root = ResolveRoot(automation, hwnd);
            return new { status = "ok", tree = BuildTree(root, 0, maxDepth) };
        }
        catch (Exception ex)
        {
            return Fail(ex.Message);
        }
    }

    public object Invoke(string selector, long? hwnd = null, int timeoutMs = 5000)
    {
        if (!EnsureReady(out var err))
        {
            return err;
        }

        try
        {
            using var automation = GetAutomation();
            var root = ResolveRoot(automation, hwnd);
            var element = FindElement(root, selector, timeoutMs);
            if (element is null)
            {
                return new { status = "not_found", target = selector, performed = false };
            }

            if (!element.IsEnabled)
            {
                return new { status = "disabled", target = selector, performed = false };
            }

            var invoke = element.Patterns.Invoke.PatternOrDefault;
            if (invoke is null)
            {
                // mēģina klikšķi kā rezerves UIA ceļu
                element.Click();
                return new { status = "clicked", target = selector, performed = true, method = "click" };
            }

            invoke.Invoke();
            return new { status = "invoked", target = selector, performed = true, method = "invoke_pattern" };
        }
        catch (Exception ex)
        {
            return new { status = "error", target = selector, performed = false, message = ex.Message };
        }
    }

    public object SetValue(string selector, string value, long? hwnd = null, int timeoutMs = 5000)
    {
        if (!EnsureReady(out var err))
        {
            return err;
        }

        try
        {
            using var automation = GetAutomation();
            var root = ResolveRoot(automation, hwnd);
            var element = FindElement(root, selector, timeoutMs);
            if (element is null)
            {
                return new { status = "not_found", target = selector, performed = false };
            }

            var valuePattern = element.Patterns.Value.PatternOrDefault;
            if (valuePattern is not null && !valuePattern.IsReadOnly)
            {
                valuePattern.SetValue(value);
                var readBack = valuePattern.Value;
                var ok = string.Equals(readBack, value, StringComparison.Ordinal);
                return new
                {
                    status = ok ? "set" : "mismatch",
                    target = selector,
                    performed = true,
                    method = "value_pattern",
                    verified = ok,
                    length = value.Length,
                };
            }

            element.Focus();
            element.AsTextBox()?.Enter(value);
            return new
            {
                status = "entered",
                target = selector,
                performed = true,
                method = "textbox_enter",
                length = value.Length,
            };
        }
        catch (Exception ex)
        {
            return new { status = "error", target = selector, performed = false, message = ex.Message };
        }
    }

    private bool EnsureReady(out object error)
    {
        if (!IsSupported)
        {
            error = new { status = "unavailable", message = "UI Automation pieejams tikai Windows", performed = false };
            return false;
        }

        if (_stopped)
        {
            error = new { status = "stopped", message = "STOP aktīvs — UIA apturēta", performed = false };
            return false;
        }

        error = new { };
        return true;
    }

    private UIA3Automation GetAutomation()
    {
        lock (_gate)
        {
            _automation ??= new UIA3Automation();
            return _automation;
        }
    }

    private static AutomationElement ResolveRoot(UIA3Automation automation, long? hwnd)
    {
        if (hwnd is null || hwnd == 0)
        {
            return automation.GetDesktop();
        }

        var handle = new IntPtr(hwnd.Value);
        return automation.FromHandle(handle);
    }

    private static AutomationElement? FindElement(AutomationElement root, string selector, int timeoutMs)
    {
        if (string.IsNullOrWhiteSpace(selector))
        {
            return null;
        }

        // Formāti: "id:OkButton" | "name:Save" | "OkButton"
        string mode = "auto";
        string value = selector;
        var idx = selector.IndexOf(':');
        if (idx > 0)
        {
            mode = selector[..idx].Trim().ToLowerInvariant();
            value = selector[(idx + 1)..].Trim();
        }

        var cf = root.ConditionFactory;
        ConditionBase condition = mode switch
        {
            "id" or "automationid" => cf.ByAutomationId(value),
            "name" => cf.ByName(value),
            "class" => cf.ByClassName(value),
            _ => cf.ByAutomationId(value).Or(cf.ByName(value)),
        };

        var sw = Stopwatch.StartNew();
        while (sw.ElapsedMilliseconds < timeoutMs)
        {
            var found = root.FindFirstDescendant(condition);
            if (found is not null)
            {
                return found;
            }

            Thread.Sleep(100);
        }

        return null;
    }

    private static object BuildTree(AutomationElement element, int depth, int maxDepth)
    {
        var node = new Dictionary<string, object?>
        {
            ["name"] = Safe(() => element.Name),
            ["automation_id"] = Safe(() => element.AutomationId),
            ["control_type"] = Safe(() => element.ControlType.ToString()),
            ["class_name"] = Safe(() => element.ClassName),
        };

        if (depth >= maxDepth)
        {
            return node;
        }

        try
        {
            var children = element.FindAllChildren();
            node["children"] = children.Select(c => BuildTree(c, depth + 1, maxDepth)).ToList();
        }
        catch
        {
            node["children"] = Array.Empty<object>();
        }

        return node;
    }

    private static object DescribeRect(AutomationElement element)
    {
        try
        {
            var r = element.BoundingRectangle;
            return new { x = r.X, y = r.Y, width = r.Width, height = r.Height };
        }
        catch
        {
            return new { };
        }
    }

    private static string? Safe(Func<string?> fn)
    {
        try { return fn(); }
        catch { return null; }
    }

    private static bool SafeBool(Func<bool> fn)
    {
        try { return fn(); }
        catch { return false; }
    }

    private static object Fail(string message) =>
        new { status = "error", performed = false, message };

    public void Dispose()
    {
        lock (_gate)
        {
            _automation?.Dispose();
            _automation = null;
        }
    }
}
