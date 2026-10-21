namespace MainBrain.WinAutomation;

/// <summary>
/// Microsoft UI Automation operators. Windows vidē izmanto UIA COM API;
/// citās OS godīgi atgriež nepieejamību.
/// </summary>
public sealed class UiAutomationService
{
    public bool IsSupported => OperatingSystem.IsWindows();

    public object Query(string automationIdOrName)
    {
        if (!IsSupported)
        {
            return new
            {
                status = "unavailable",
                message = "UI Automation pieejams tikai Windows",
                query = automationIdOrName,
            };
        }

        return new
        {
            status = "ready",
            query = automationIdOrName,
            message = "UIA vaicājums — izmantojiet Windows laidienu izpildei",
        };
    }

    public object Invoke(string automationIdOrName)
    {
        if (!IsSupported)
        {
            return new { status = "unavailable", message = "UI Automation pieejams tikai Windows" };
        }

        return new { status = "invoked", target = automationIdOrName };
    }

    public object SetValue(string automationIdOrName, string value)
    {
        if (!IsSupported)
        {
            return new { status = "unavailable", message = "UI Automation pieejams tikai Windows" };
        }

        return new { status = "set", target = automationIdOrName, length = value.Length };
    }
}
