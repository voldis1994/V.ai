using System.Text.Json;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.Wpf;

namespace MainBrain.Desktop.Services;

/// <summary>
/// Īsta WebView2 vadība — navigācija/klikšķi/aizpilde tikai pēc apstiprināta rezultāta.
/// </summary>
public sealed class BrowserAutomationService
{
    private WebView2? _webView;
    private string? _lastUrl;
    private bool _navigatedOk;

    public void Attach(WebView2 webView)
    {
        _webView = webView;
        _webView.NavigationCompleted += (_, args) =>
        {
            _navigatedOk = args.IsSuccess;
            if (args.IsSuccess)
            {
                _lastUrl = _webView.Source?.ToString();
            }
        };
    }

    public async Task<object> HandleBridgeRequestAsync(JsonElement root)
    {
        if (_webView is null)
        {
            return new { status = "unavailable", performed = false, message = "WebView2 nav pievienots" };
        }

        var tool = root.TryGetProperty("tool", out var t) ? t.GetString() : "";
        var args = root.TryGetProperty("arguments", out var a) ? a : default;
        return tool switch
        {
            "browser.navigate" => await NavigateAsync(Str(args, "url")),
            "browser.inspect" => await InspectAsync(),
            "browser.click" => await ClickAsync(Str(args, "selector")),
            "browser.fill" => await FillAsync(Str(args, "selector"), Str(args, "value")),
            "browser.screenshot" => await ScreenshotAsync(),
            _ => new { status = "unknown_tool", performed = false, tool },
        };
    }

    private async Task<object> NavigateAsync(string? url)
    {
        if (string.IsNullOrWhiteSpace(url))
        {
            return new { status = "error", performed = false, message = "URL nav norādīts" };
        }

        _navigatedOk = false;
        await _webView!.EnsureCoreWebView2Async();
        var tcs = new TaskCompletionSource<bool>();
        void Handler(object? s, CoreWebView2NavigationCompletedEventArgs e)
        {
            _webView.NavigationCompleted -= Handler;
            tcs.TrySetResult(e.IsSuccess);
        }

        _webView.NavigationCompleted += Handler;
        _webView.Source = new Uri(url);
        var ok = await tcs.Task.WaitAsync(TimeSpan.FromSeconds(30));
        _lastUrl = _webView.Source?.ToString();
        return new
        {
            status = ok ? "navigated" : "failed",
            performed = ok,
            url = _lastUrl,
            message = ok ? "Navigācija apstiprināta WebView2" : "Navigācija neizdevās",
        };
    }

    private async Task<object> InspectAsync()
    {
        await _webView!.EnsureCoreWebView2Async();
        var title = await _webView.ExecuteScriptAsync("document.title");
        return new
        {
            status = "ok",
            performed = true,
            url = _webView.Source?.ToString(),
            title = title?.Trim('"'),
            last_navigation_ok = _navigatedOk,
        };
    }

    private async Task<object> ClickAsync(string? selector)
    {
        if (string.IsNullOrWhiteSpace(selector))
        {
            return new { status = "error", performed = false, message = "Trūkst selektora" };
        }

        await _webView!.EnsureCoreWebView2Async();
        var script =
            $"(function(){{ var el=document.querySelector({JsonSerializer.Serialize(selector)}); " +
            "if(!el) return 'not_found'; el.click(); return 'clicked'; }})()";
        var result = await _webView.ExecuteScriptAsync(script);
        var text = result?.Trim('"');
        return new
        {
            status = text,
            performed = text == "clicked",
            selector,
        };
    }

    private async Task<object> FillAsync(string? selector, string? value)
    {
        if (string.IsNullOrWhiteSpace(selector))
        {
            return new { status = "error", performed = false, message = "Trūkst selektora" };
        }

        await _webView!.EnsureCoreWebView2Async();
        var script =
            $"(function(){{ var el=document.querySelector({JsonSerializer.Serialize(selector)}); " +
            $"if(!el) return 'not_found'; el.value={JsonSerializer.Serialize(value ?? "")}; " +
            "el.dispatchEvent(new Event('input',{bubbles:true})); return 'filled'; }})()";
        var result = await _webView.ExecuteScriptAsync(script);
        var text = result?.Trim('"');
        return new { status = text, performed = text == "filled", selector };
    }

    private async Task<object> ScreenshotAsync()
    {
        await _webView!.EnsureCoreWebView2Async();
        var dir = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "MainBrainOS",
            "browser_shots");
        Directory.CreateDirectory(dir);
        var path = Path.Combine(dir, $"{Guid.NewGuid():N}.png");
        await using var stream = File.Create(path);
        await _webView.CoreWebView2.CapturePreviewAsync(CoreWebView2CapturePreviewImageFormat.Png, stream);
        return new { status = "ok", performed = true, path };
    }

    private static string? Str(JsonElement args, string name)
    {
        if (args.ValueKind != JsonValueKind.Object || !args.TryGetProperty(name, out var p))
        {
            return null;
        }

        return p.ValueKind == JsonValueKind.String ? p.GetString() : p.ToString();
    }
}
