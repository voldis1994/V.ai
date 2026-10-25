using System.Collections.ObjectModel;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Windows;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using MainBrain.Contracts;
using MainBrain.Desktop.Services;

namespace MainBrain.Desktop.ViewModels;

public partial class MainViewModel : ObservableObject
{
    private readonly ApiClient _api;

    /// <summary>MainWindow: noņem Topmost + minimizē, lai pārlūks/fails BŪTU REDZAMS.</summary>
    public Action<string>? YieldForExternalAction { get; set; }

    /// <summary>MainWindow: atgriež Matrix overlay pēc darbības.</summary>
    public Action? RestoreMainOverlay { get; set; }

    [ObservableProperty] private string _title = "Main Brain OS";
    [ObservableProperty] private string _statusText = "Inicializē...";
    [ObservableProperty] private string _activeModel = "Nav konfigurēts";
    [ObservableProperty] private string _resourceText = "CPU/RAM: —";
    [ObservableProperty] private string _agentCountText = "Aģenti: —";
    [ObservableProperty] private bool _isOffline;
    [ObservableProperty] private int _activeJobs;
    [ObservableProperty] private bool _isFocusMode = true;
    [ObservableProperty] private string _chatInput = "";
    [ObservableProperty] private string _chatOutput = "";
    [ObservableProperty] private string _chatSessionId = "ui";
    [ObservableProperty] private bool _isThinking;
    /// <summary>Immersīvs Matrix režīms — bez pogām (noklusējums).</summary>
    [ObservableProperty] private bool _immersiveMode = true;
    /// <summary>Teksts, ko hieroglifi salido centrā.</summary>
    [ObservableProperty] private string _formedAnswer = "";
    [ObservableProperty] private string _matrixStatus = "◈ MAIN BRAIN · dzīva sistēma";
    /// <summary>Vecais karogs — Matrix vairs nepazūd; paliek saderībai.</summary>
    [ObservableProperty] private bool _showMatrixRain = true;

    public Visibility MatrixRainVisibility => Visibility.Visible;
    public Visibility ImmersiveVisibility => ImmersiveMode ? Visibility.Visible : Visibility.Collapsed;
    public Visibility ChromeVisibility => ImmersiveMode ? Visibility.Collapsed : Visibility.Visible;
    /// <summary>Kameras/attēla priekšskatījums uz paša Matrix ekrāna (bez paneļu maiņas).</summary>
    public Visibility ImmersiveLiveVisibility =>
        ImmersiveMode && !string.IsNullOrWhiteSpace(LiveImagePath) ? Visibility.Visible : Visibility.Collapsed;

    /// <summary>Mazais «ko es daru» pārlūka lodziņš uz Matrix.</summary>
    [ObservableProperty] private bool _showImmersiveActivity;
    [ObservableProperty] private string _activityTitle = "◈ KO ES DARU";

    public Visibility ImmersiveActivityVisibility =>
        ImmersiveMode && ShowImmersiveActivity ? Visibility.Visible : Visibility.Collapsed;
    [ObservableProperty] private string _terminalOutput = "";
    [ObservableProperty] private AgentDefinitionDto? _selectedAgent;
    [ObservableProperty] private string _inspectorText = "Izvēlieties aģentu vai palaidiet uzdevumu.";
    [ObservableProperty] private string _workspacePath = "";
    [ObservableProperty] private string _browserUrl = "https://example.com";
    [ObservableProperty] private string _currentPanelKind = "Sākums — gaida uzdevumu";
    [ObservableProperty] private string _focusSource = "home";
    [ObservableProperty] private bool _focusPinned;
    [ObservableProperty] private string? _liveImagePath;
    [ObservableProperty] private string _editorText = "# Main Brain OS redaktors\n";
    [ObservableProperty] private string _navSection = "Main Brain";
    [ObservableProperty] private bool _showAgents;
    [ObservableProperty] private bool _showInspector;

    public ObservableCollection<AgentDefinitionDto> Agents { get; } = new();
    public ObservableCollection<string> Sections { get; } = new();
    public ObservableCollection<ApprovalRequestDto> Approvals { get; } = new();
    public ObservableCollection<ProgressEventDto> Timeline { get; } = new();
    public ObservableCollection<WorkPanelViewModel> Panels { get; } = new();
    public ObservableCollection<string> NavItems { get; } = new()
    {
        "Main Brain", "Aģenti", "Projekti", "Aktīvie uzdevumi", "Atmiņa", "Modeļu pārvaldība", "Darbību vēsture", "Iestatījumi",
    };

    public Visibility FocusVisibility => IsFocusMode ? Visibility.Visible : Visibility.Collapsed;
    public Visibility MultiVisibility => IsFocusMode ? Visibility.Collapsed : Visibility.Visible;
    public Visibility AgentsVisibility => ShowAgents ? Visibility.Visible : Visibility.Collapsed;
    public Visibility InspectorVisibility => ShowInspector ? Visibility.Visible : Visibility.Collapsed;
    public Visibility ApprovalsVisibility => Approvals.Any(a => a.Status == "pending") ? Visibility.Visible : Visibility.Collapsed;
    public Visibility HomeVisibility => FocusSource == "home" ? Visibility.Visible : Visibility.Collapsed;
    public Visibility BrowserVisibility => FocusSource == "browser" ? Visibility.Visible : Visibility.Collapsed;
    public Visibility EditorVisibility => FocusSource == "editor" ? Visibility.Visible : Visibility.Collapsed;
    public Visibility TerminalVisibility => FocusSource is "terminal" ? Visibility.Visible : Visibility.Collapsed;
    public Visibility LiveVisibility => FocusSource == "live" ? Visibility.Visible : Visibility.Collapsed;
    public Visibility LogVisibility => FocusSource == "log" ? Visibility.Visible : Visibility.Collapsed;

    public MainViewModel(ApiClient api)
    {
        _api = api;
        // full_access: darba sakne = lietotāja profils (viss dators caur absolūtiem ceļiem)
        WorkspacePath = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
        // Multi režīmā paneļi; Focus sākas tukšs (home) — programma parādās tikai kad tiek lietota
        Panels.Add(new WorkPanelViewModel("Iegultais pārlūks", "embedded_browser") { IsVisible = false });
        Panels.Add(new WorkPanelViewModel("Redaktors", "editor") { IsVisible = false });
        Panels.Add(new WorkPanelViewModel("Terminālis", "terminal") { IsVisible = false });
        Panels.Add(new WorkPanelViewModel("Dzīvais attēls", "live_image") { IsVisible = false });
        Panels.Add(new WorkPanelViewModel("Aģentu aktivitāte", "log") { IsVisible = false });
    }

    public async Task InitializeAsync()
    {
        try
        {
            var health = await _api.GetHealthAsync();
            if (health is null)
            {
                StatusText = "Backend nav sasniedzams";
                IsOffline = true;
                return;
            }

            StatusText = health.EmergencyStop
                ? "STOP aktīvs"
                : "BRĪVS · llama.cpp · Ollama OFF";
            IsOffline = false;
            ActiveModel = health.Models.FirstOrDefault(m => m.Available)?.ModelName
                          ?? health.Models.FirstOrDefault()?.Details
                          ?? "Nav konfigurēts";
            ResourceText = "Darbības uzreiz · bez Ollama gaidīšanas";
            var agents = await _api.GetAgentsAsync();
            Agents.Clear();
            Sections.Clear();
            foreach (var section in agents.Select(a => a.Section).Distinct())
            {
                Sections.Add(section);
            }

            foreach (var agent in agents.OrderBy(a => a.Number))
            {
                Agents.Add(agent);
            }

            AgentCountText = $"Aģenti: {Agents.Count}/50";
            await RefreshApprovalsAsync();
            await LoadLayoutAsync();
            InspectorText = $"Aģenti: {Agents.Count}/50";
            // Chat starts empty — no intro wall of text
            ChatOutput = "";
        }
        catch (Exception ex)
        {
            StatusText = "Kļūda";
            AgentCountText = "Aģenti: nav (backend?)";
            ChatOutput += "\n" + ex.Message;
        }
    }

    partial void OnIsFocusModeChanged(bool value)
    {
        NotifyWorkspaceVisibilities();
        CurrentPanelKind = value ? PanelLabel(FocusSource) : "Vairāku logu režīms";
        _ = SaveLayoutAsync();
    }

    partial void OnFocusSourceChanged(string value)
    {
        NotifyWorkspaceVisibilities();
        CurrentPanelKind = PanelLabel(value);
        foreach (var p in Panels)
        {
            p.IsVisible = value != "home" && (
                (value == "browser" && p.Kind == "embedded_browser") ||
                (value == "editor" && p.Kind == "editor") ||
                (value == "terminal" && p.Kind == "terminal") ||
                (value == "live" && p.Kind == "live_image") ||
                (value == "log" && p.Kind == "log"));
        }
    }

    partial void OnShowAgentsChanged(bool value) => OnPropertyChanged(nameof(AgentsVisibility));
    partial void OnShowInspectorChanged(bool value) => OnPropertyChanged(nameof(InspectorVisibility));
    partial void OnShowMatrixRainChanged(bool value) => OnPropertyChanged(nameof(MatrixRainVisibility));
    partial void OnImmersiveModeChanged(bool value)
    {
        OnPropertyChanged(nameof(ImmersiveVisibility));
        OnPropertyChanged(nameof(ChromeVisibility));
        OnPropertyChanged(nameof(ImmersiveLiveVisibility));
        OnPropertyChanged(nameof(ImmersiveActivityVisibility));
        if (value)
        {
            FocusSource = "home";
            ShowAgents = false;
            ShowInspector = false;
            IsFocusMode = true;
            MatrixStatus = "";
        }
        else
        {
            MatrixStatus = "◈ DEV · Ctrl+Shift+D atpakaļ immersīvā";
        }
    }

    partial void OnLiveImagePathChanged(string? value) => OnPropertyChanged(nameof(ImmersiveLiveVisibility));
    partial void OnShowImmersiveActivityChanged(bool value) => OnPropertyChanged(nameof(ImmersiveActivityVisibility));

    private void NotifyWorkspaceVisibilities()
    {
        OnPropertyChanged(nameof(FocusVisibility));
        OnPropertyChanged(nameof(MultiVisibility));
        OnPropertyChanged(nameof(HomeVisibility));
        OnPropertyChanged(nameof(BrowserVisibility));
        OnPropertyChanged(nameof(EditorVisibility));
        OnPropertyChanged(nameof(TerminalVisibility));
        OnPropertyChanged(nameof(LiveVisibility));
        OnPropertyChanged(nameof(LogVisibility));
    }

    private static string PanelLabel(string source) => source switch
    {
        "home" => "Saruna",
        "browser" => "Iegultais pārlūks",
        "editor" => "Redaktors",
        "terminal" => "Terminālis",
        "live" => "Dzīvais attēls",
        "log" => "Žurnāls",
        _ => source,
    };

    [RelayCommand]
    private void ToggleImmersive()
    {
        ImmersiveMode = !ImmersiveMode;
    }

    [RelayCommand]
    private void SetFocusMode()
    {
        IsFocusMode = true;
    }

    [RelayCommand]
    private void SetMultiMode()
    {
        IsFocusMode = false;
    }

    [RelayCommand]
    private void ToggleMode()
    {
        IsFocusMode = !IsFocusMode;
    }

    [RelayCommand]
    private void ToggleAgents()
    {
        ShowAgents = !ShowAgents;
        if (ShowAgents)
        {
            ShowInspector = false;
        }
    }

    [RelayCommand]
    private void ToggleInspector()
    {
        ShowInspector = !ShowInspector;
        if (ShowInspector)
        {
            ShowAgents = false;
        }
    }

    [RelayCommand]
    private void SelectFocusSource(string? source)
    {
        if (string.IsNullOrWhiteSpace(source) || FocusPinned)
        {
            return;
        }

        FocusSource = source;
        _ = SaveLayoutAsync();
    }

    [RelayCommand]
    private void ToggleFocusPin()
    {
        FocusPinned = !FocusPinned;
        _ = SaveLayoutAsync();
    }

    [RelayCommand]
    private async Task SendGoalAsync()
    {
        if (string.IsNullOrWhiteSpace(ChatInput) || IsThinking)
        {
            return;
        }

        var userText = ChatInput.Trim();
        ChatInput = "";
        ActiveJobs++;
        IsThinking = true;
        ShowMatrixRain = true;
        if (string.IsNullOrWhiteSpace(ChatOutput))
        {
            ChatOutput = $"Tu: {userText}";
        }
        else
        {
            ChatOutput += $"\n\nTu: {userText}";
        }

        if (ImmersiveMode || !FocusPinned)
        {
            FocusSource = "home";
        }

        // UZREIZ rādam darbību + atveram logu — NEgaidām backend «DOMĀ»
        var preview = BeginVisibleAction(userText);

        try
        {
            // Meklēšanai — īss timeouts, lai UI NEKAD neiesprūstu uz «Meklēju…»
            var chatTimeout = preview.ShowPip ? TimeSpan.FromSeconds(22) : TimeSpan.FromMinutes(3);
            var result = await _api.ChatAsync(
                new ChatRequestDto
                {
                    Message = userText,
                    SessionId = ChatSessionId,
                    WorkspacePath = string.IsNullOrWhiteSpace(WorkspacePath) ? null : WorkspacePath,
                },
                timeout: chatTimeout);
            var reply = result.Reply ?? "";
            var display = HumanizeReply(reply);
            ChatOutput += $"\nMain Brain: {reply}";
            if (result.Mode is "execute" or "act")
            {
                TerminalOutput += $"\n[{DateTime.Now:HH:mm:ss}] {result.Mode}: {result.GoalStatus ?? result.UiAction}";
                InspectorText = $"Darbība: {result.UiAction ?? result.GoalStatus}";
            }

            ApplyUiAction(result, alreadyOpenedUrl: preview.OpenedUrl);

            // Īss brīdis paskatīties PiP → VIENMĒR aizver → rāda ko atrada
            if (preview.ShowPip)
            {
                await Task.Delay(900);
            }

            // Immersīvajā: PALIEKAM Matrix — rādam faila saturu mazajā logā (ne tikai web)
            if (!string.IsNullOrWhiteSpace(result.OpenPath) && File.Exists(result.OpenPath))
            {
                try
                {
                    var ext = Path.GetExtension(result.OpenPath).ToLowerInvariant();
                    if (ext is ".py" or ".txt" or ".md" or ".cs" or ".json")
                    {
                        var code = File.ReadAllText(result.OpenPath);
                        EditorText = code;
                        ShowImmersiveActivity = true;
                        ActivityTitle = "◈ KO ES DARU · fails " + Path.GetFileName(result.OpenPath);
                        BrowserUrl = MakeActivityHtml(Path.GetFileName(result.OpenPath), code);
                        await Task.Delay(1400);
                    }
                }
                catch
                {
                    // ignore
                }
            }

            FinishVisibleAction(display, reply);

            // Audio TIKAI ja backend atdeva SpeakText (= lietotājs teica pasaki/skaļi/…)
            if (!string.IsNullOrWhiteSpace(result.SpeakText))
            {
                SpeakLocal(HumanizeReply(result.SpeakText!));
            }

            OnPropertyChanged(nameof(ApprovalsVisibility));
        }
        catch (Exception ex)
        {
            var msg = ex.Message ?? "";
            var err = msg.Contains("Timeout", StringComparison.OrdinalIgnoreCase) ||
                      msg.Contains("canceled", StringComparison.OrdinalIgnoreCase)
                ? "Meklēšana ieilga. Rezultāti bija mazajā lodziņā — mēģini vēlreiz."
                : "Kļūda — " + msg;
            ChatOutput += "\nMain Brain: " + err;
            FinishVisibleAction(err, err);
            MatrixStatus = "◈ KĻŪDA";
        }
        finally
        {
            // Garantija: PiP aizveras VIENMĒR
            ShowImmersiveActivity = false;
            IsThinking = false;
            ActiveJobs = Math.Max(0, ActiveJobs - 1);
            await RefreshApprovalsAsync();
        }
    }

    private void FinishVisibleAction(string display, string fallback)
    {
        // AIZVER mazo logu (WebView → about:blank)
        ShowImmersiveActivity = false;
        BrowserUrl = "about:blank";
        MatrixStatus = "";
        FormedAnswer = string.IsNullOrWhiteSpace(display) ? fallback : display;
        RestoreMainOverlay?.Invoke();
    }

    /// <summary>Mazais logs — HTML ar darbību/kodu (ne tikai DuckDuckGo).</summary>
    private static string MakeActivityHtml(string title, string body)
    {
        static string Esc(string s) =>
            (s ?? "")
                .Replace("&", "&amp;")
                .Replace("<", "&lt;")
                .Replace(">", "&gt;")
                .Replace("\"", "&quot;");

        var html =
            "<!DOCTYPE html><html><head><meta charset='utf-8'>" +
            "<style>body{margin:0;background:#08020A;color:#FFB7EC;font:13px/1.45 Consolas,monospace;padding:12px}" +
            "h1{color:#FF2ECB;font-size:14px;margin:0 0 10px}pre{white-space:pre-wrap;word-break:break-word;" +
            "background:#12040F;border:1px solid #44FF2ECB;padding:10px;border-radius:6px}</style></head><body>" +
            "<h1>◈ " + Esc(title) + "</h1><pre>" + Esc(body) + "</pre></body></html>";
        return "data:text/html;charset=utf-8," + Uri.EscapeDataString(html);
    }

    private sealed record ActionPreview(bool ShowPip, string? OpenedUrl);

    /// <summary>
    /// Uzreiz: mazais pārlūka lodziņš LABĀJĀ pusē uz tā paša Matrix ekrāna.
    /// </summary>
    private ActionPreview BeginVisibleAction(string userText)
    {
        var t = userText.Trim();
        var isCamera = Regex.IsMatch(
            t,
            @"(?i)\b(kamer|camera|webcam|seja|face|ko\s+tu\s+redzi|redzi\s+mani|atpazī\w*\s+sej)",
            RegexOptions.IgnoreCase);
        var search = Regex.IsMatch(
            t,
            @"(?i)\b(sameklē|meklē|atrast|search|google|kas\s+ir|who\s+is|pastāsti\s+par|info\s+par|informācij)",
            RegexOptions.IgnoreCase);
        var personName = Regex.IsMatch(t, @"^\s*[A-ZĀČĒĢĪĶĻŅŠŪŽ][\wāčēģīķļņšūž]+\s+[A-ZĀČĒĢĪĶĻŅŠŪŽ][\wāčēģīķļņšūž]+\s*$");
        var looksQuestion = t.Contains('?') || Regex.IsMatch(t, @"(?i)^\s*(kas|kā|kur|kad|kāpēc|who|what|where|when|why|how)\b");
        var openApp = Regex.IsMatch(t, @"(?i)\b(atver|open|palaid)\b");
        var build = Regex.IsMatch(t, @"(?i)\b(uztaisi|izveido|uzraksti|uzprogrammē|build|create)\b");
        if (personName)
        {
            search = true;
        }

        // Kamera / «ko tu redzi» — NAV meklēšana; rādam kameras kadru, nevis DuckDuckGo
        if (isCamera && !build)
        {
            MatrixStatus = "◈ SKATOS KAMERĀ …";
            ActivityTitle = "◈ KO ES DARU · kamera";
            FormedAnswer = "Skatos kamerā… Pēc brīža pastāstīšu, ko redzu.";
            ShowImmersiveActivity = false;
            return new ActionPreview(false, null);
        }

        if (build)
        {
            MatrixStatus = "◈ TAISU …";
            ActivityTitle = "◈ KO ES DARU · rakstu failu (labajā)";
            FormedAnswer =
                "Taisu failu. Labajā — mazais logs (nevis tikai web search). Kodā rādīšu saturu.";
            ShowImmersiveActivity = true;
            BrowserUrl = MakeActivityHtml(
                "Rakstu failu",
                "Veidoju mapi → rakstu kodu → rādīšu šeit. Neizeju uz Notepad/VS Code.");
            return new ActionPreview(true, BrowserUrl);
        }

        if (openApp && !search)
        {
            MatrixStatus = "◈ ATVERU PROGRAMMU …";
            ActivityTitle = "◈ KO ES DARU · programma";
            FormedAnswer = "Atveru programmu no tava datora.";
            // Tikai «atver …» — tad drīkst yield
            YieldForExternalAction?.Invoke("open");
            return new ActionPreview(false, null);
        }

        if (search || looksQuestion)
        {
            var q = ExtractSearchQuery(t);
            var url = "https://duckduckgo.com/?q=" + Uri.EscapeDataString(q);
            MatrixStatus = "◈ MEKLĒJU …";
            ActivityTitle = "◈ KO ES DARU · meklēšana (labajā)";
            FormedAnswer =
                $"Meklēju «{q}».\n\nLabajā pusē — mazais logs (ko es daru). Pēc tam to aizvēršu un uzrakstīšu, ko atrada.";
            ShowImmersiveActivity = true;
            BrowserUrl = url;
            return new ActionPreview(true, url);
        }

        MatrixStatus = "◈ DARU …";
        FormedAnswer = "Strādāju…";
        return new ActionPreview(false, null);
    }

    private static string ExtractSearchQuery(string text)
    {
        var m = Regex.Match(
            text,
            @"(?i)(?:sameklē|meklē|atrast|search|google|pastāsti\s+par|info\s+par|informācij[ua]\s+par|kas\s+ir|who\s+is)\s+(.+)$");
        if (m.Success)
        {
            return m.Groups[1].Value.Trim().TrimEnd('?', '.', '!');
        }

        return text.Trim().TrimEnd('?', '.', '!');
    }

    private void ApplyUiAction(ChatResponseDto result, string? alreadyOpenedUrl = null)
    {
        try
        {
            var stayOnMatrix = ImmersiveMode;

            if (!stayOnMatrix && !string.IsNullOrWhiteSpace(result.Focus))
            {
                if (result.Focus is "browser" or "editor" or "terminal" or "live")
                {
                    IsFocusMode = true;
                    FocusSource = result.Focus;
                }
            }

            if (!string.IsNullOrWhiteSpace(result.OpenUrl))
            {
                // PiP jau rādīts BeginVisibleAction laikā — tikai atjauninam URL, NEATVERAM no jauna pēc atbildes
                if (ShowImmersiveActivity || !stayOnMatrix)
                {
                    BrowserUrl = result.OpenUrl;
                }

                if (!stayOnMatrix)
                {
                    FocusSource = "browser";
                }
            }

            if (!string.IsNullOrWhiteSpace(result.ImagePath) && System.IO.File.Exists(result.ImagePath))
            {
                LiveImagePath = result.ImagePath;
                if (!stayOnMatrix)
                {
                    FocusSource = "live";
                }
            }

            if (!string.IsNullOrWhiteSpace(result.OpenPath) && System.IO.File.Exists(result.OpenPath))
            {
                var ext = System.IO.Path.GetExtension(result.OpenPath).ToLowerInvariant();
                if (ext == ".png" || ext == ".jpg" || ext == ".jpeg" || ext == ".bmp" || ext == ".webp")
                {
                    LiveImagePath = result.OpenPath;
                    if (!stayOnMatrix)
                    {
                        FocusSource = "live";
                    }
                }
                else
                {
                    try
                    {
                        EditorText = System.IO.File.ReadAllText(result.OpenPath);
                    }
                    catch
                    {
                        // ignore
                    }

                    if (!stayOnMatrix)
                    {
                        FocusSource = "editor";
                    }
                }

                // Immersīvā: NEIZEJAM ārā — fails jau ielasīts EditorText / FormedAnswer
                // Ārējo programmu atver TIKAI ja lietotājs teica «atver …» (ne build/search)
            }

            // SpeakLocal — tikai no SendGoalAsync (pēc PiP aizvēršanas), lai nebūtu dubultā

            if (stayOnMatrix)
            {
                ImmersiveMode = true;
                FocusSource = "home";
                ShowAgents = false;
                ShowInspector = false;
            }
        }
        catch
        {
            // UI darbība nedrīkst nogāzt chatu
        }
    }

    /// <summary>Noņem tehniskās piezīmes un muļķīgas frāzes no atbildes.</summary>
    private static string HumanizeReply(string reply)
    {
        if (string.IsNullOrWhiteSpace(reply))
        {
            return "";
        }

        var t = reply.Trim();
        t = Regex.Replace(t, @"\n*\[Darbība\][^\n]*", "", RegexOptions.IgnoreCase);
        t = Regex.Replace(t, @"\n*\[Iemācīts\][^\n]*", "", RegexOptions.IgnoreCase);
        t = Regex.Replace(t, @"\(Lokālais modelis[^\)]*\)", "", RegexOptions.IgnoreCase);
        t = Regex.Replace(t, @"Ollama netiek izmantota\.", "", RegexOptions.IgnoreCase);
        // Atmet rindiņas ar tipisku junk
        var lines = t.Split('\n')
            .Where(l =>
            {
                var x = l.Trim();
                if (x.Length == 0) return true;
                var low = x.ToLowerInvariant();
                return !low.Contains("nezinu, kāds") &&
                       !low.Contains("kuru informāciju meklētu") &&
                       !low.Contains("pasaki audio") &&
                       !low.Contains("sameklē mani");
            });
        t = string.Join("\n", lines);
        t = Regex.Replace(t, @"\n{3,}", "\n\n").Trim();
        return t;
    }

    /// <summary>Latviešu → aptuvena fonētika, ja nav LV balss (tikai SAPI fallback).</summary>
    private static string LatvianPhonetic(string text)
    {
        var map = new (string a, string b)[]
        {
            ("č", "ch"), ("Č", "Ch"), ("š", "sh"), ("Š", "Sh"),
            ("ž", "zh"), ("Ž", "Zh"), ("ā", "aa"), ("Ā", "Aa"),
            ("ē", "ee"), ("Ē", "Ee"), ("ī", "ii"), ("Ī", "Ii"),
            ("ū", "uu"), ("Ū", "Uu"), ("ģ", "gy"), ("Ģ", "Gy"),
            ("ķ", "ky"), ("Ķ", "Ky"), ("ļ", "ly"), ("Ļ", "Ly"),
            ("ņ", "ny"), ("Ņ", "Ny"),
        };
        var t = text;
        foreach (var (a, b) in map)
        {
            t = t.Replace(a, b);
        }

        return t;
    }

    /// <summary>Primāri Everita (backend /speak); SAPI — tikai ja tīkls/edge-tts nav.</summary>
    private void SpeakLocal(string text)
    {
        var t = HumanizeReply(text);
        t = Regex.Replace(t, @"\s+", " ").Trim();
        if (string.IsNullOrWhiteSpace(t))
        {
            return;
        }

        if (t.Length > 500)
        {
            t = t[..500] + "…";
        }

        _ = SpeakViaBackendOrSapiAsync(t);
    }

    private async Task SpeakViaBackendOrSapiAsync(string text)
    {
        try
        {
            // Microsoft Everita — īsta latviešu balss
            if (await _api.SpeakAsync(text, "lv", "lv-LV-EveritaNeural"))
            {
                return;
            }
        }
        catch
        {
            // fall through
        }

        SpeakSapiFallback(text);
    }

    private static void SpeakSapiFallback(string text)
    {
        try
        {
            var rawB64 = Convert.ToBase64String(Encoding.UTF8.GetBytes(text));
            var phoB64 = Convert.ToBase64String(Encoding.UTF8.GetBytes(LatvianPhonetic(text)));
            var script =
                "Add-Type -AssemblyName System.Speech; " +
                "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; " +
                "$s.Rate = -1; " +
                "$voices = @($s.GetInstalledVoices() | ForEach-Object { $_.VoiceInfo }); " +
                "$lv = $voices | Where-Object { $_.Culture.Name -like 'lv*' -or $_.Name -match 'Latvi' } | Select-Object -First 1; " +
                "$raw = [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('" + rawB64 + "')); " +
                "$pho = [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('" + phoB64 + "')); " +
                "if ($lv) { $s.SelectVoice($lv.Name); $s.Speak($raw) } " +
                "else { $en = $voices | Where-Object { $_.Culture.Name -like 'en*' } | Select-Object -First 1; " +
                "if ($en) { $s.SelectVoice($en.Name) }; $s.Speak($pho) }";
            var encoded = Convert.ToBase64String(Encoding.Unicode.GetBytes(script));
            Process.Start(new ProcessStartInfo
            {
                FileName = "powershell",
                Arguments = "-NoProfile -WindowStyle Hidden -EncodedCommand " + encoded,
                UseShellExecute = false,
                CreateNoWindow = true,
            });
        }
        catch
        {
            // TTS nav obligāts
        }
    }

    [RelayCommand]
    private async Task EmergencyStopAsync()
    {
        await _api.StopAsync();
        StatusText = "STOP aktīvs";
        ChatOutput += "\n[STOP] Jaunas darbības liegtas; automatizācija apturēta.";
    }

    [RelayCommand]
    private async Task PauseAsync() => await _api.PauseAsync();

    [RelayCommand]
    private async Task ResumeAsync()
    {
        await _api.ResumeAsync();
        StatusText = "Lokāli aktīvs";
    }

    [RelayCommand]
    private async Task RefreshApprovalsAsync()
    {
        Approvals.Clear();
        foreach (var item in await _api.GetApprovalsAsync())
        {
            Approvals.Add(item);
        }
    }

    [RelayCommand]
    private async Task DecideApprovalAsync(string? decision)
    {
        var pending = Approvals.FirstOrDefault(a => a.Status == "pending");
        if (pending is null || string.IsNullOrWhiteSpace(decision))
        {
            return;
        }

        await _api.DecideApprovalAsync(pending.Id, decision);
        await RefreshApprovalsAsync();
        OnPropertyChanged(nameof(ApprovalsVisibility));
    }

    [RelayCommand]
    private async Task InvokeSelectedAgentAsync()
    {
        if (SelectedAgent is null)
        {
            return;
        }

        InspectorText = $"Izsaucu {SelectedAgent.Name}...";
        ChatInput = $"Izpildi aģenta {SelectedAgent.Name} uzdevumu: {SelectedAgent.Description}";
        await SendGoalAsync();
    }

    [RelayCommand]
    private async Task SaveLayoutAsync()
    {
        var payload = new
        {
            mode = IsFocusMode ? "focus" : "multi",
            focus_source = FocusSource,
            focus_pinned = FocusPinned,
            theme = "dark",
            workspace = WorkspacePath,
            panels = Panels.Select(p => new { p.Title, p.Kind, p.IsVisible, p.IsPinned }).ToList(),
        };
        await _api.SaveLayoutAsync(payload);
    }

    private async Task LoadLayoutAsync()
    {
        try
        {
            var layout = await _api.GetLayoutAsync();
            if (layout.ValueKind != JsonValueKind.Object)
            {
                return;
            }

            if (layout.TryGetProperty("mode", out var mode))
            {
                IsFocusMode = mode.GetString() != "multi";
            }

            if (layout.TryGetProperty("focus_source", out var src))
            {
                FocusSource = src.GetString() ?? FocusSource;
            }

            if (layout.TryGetProperty("focus_pinned", out var pinned) && pinned.ValueKind is JsonValueKind.True or JsonValueKind.False)
            {
                FocusPinned = pinned.GetBoolean();
            }

            if (layout.TryGetProperty("workspace", out var ws) && !string.IsNullOrWhiteSpace(ws.GetString()))
            {
                WorkspacePath = ws.GetString()!;
            }
        }
        catch
        {
            // pirmā palaišana
        }
    }

    partial void OnSelectedAgentChanged(AgentDefinitionDto? value)
    {
        if (value is null)
        {
            return;
        }

        ShowInspector = true;
        InspectorText =
            $"Aģents: {value.Number:00}. {value.Name}\n" +
            $"Nodaļa: {value.Section}\n" +
            $"{value.Description}\n\n" +
            $"Modeļa loma: {value.ModelRole}\n" +
            $"Rīki: {string.Join(", ", value.AllowedTools)}\n" +
            $"Ierobežojumi:\n- {string.Join("\n- ", value.Constraints)}";
    }

    private static string SummarizeGoal(JsonElement result)
    {
        try
        {
            var status = result.TryGetProperty("status", out var s) ? s.GetString() : "?";
            var plan = result.TryGetProperty("plan", out var p) ? p : default;
            var tasks = plan.ValueKind == JsonValueKind.Object && plan.TryGetProperty("tasks", out var t) ? t.GetArrayLength() : 0;
            return $"Statuss: {status}; uzdevumi: {tasks}";
        }
        catch
        {
            return result.GetRawText();
        }
    }
}

public partial class WorkPanelViewModel : ObservableObject
{
    public WorkPanelViewModel(string title, string kind)
    {
        Title = title;
        Kind = kind;
    }

    [ObservableProperty] private string _title;
    [ObservableProperty] private string _kind;
    [ObservableProperty] private bool _isPinned;
    [ObservableProperty] private bool _isVisible = true;
    [ObservableProperty] private string _content = "";
    [ObservableProperty] private string _status = "aktīvs";
}
