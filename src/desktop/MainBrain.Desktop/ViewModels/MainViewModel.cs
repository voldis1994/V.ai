using System.Collections.ObjectModel;
using System.Diagnostics;
using System.IO;
using System.Text.Json;
using System.Windows;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using MainBrain.Contracts;
using MainBrain.Desktop.Services;

namespace MainBrain.Desktop.ViewModels;

public partial class MainViewModel : ObservableObject
{
    private readonly ApiClient _api;

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
                : "Lokāli · llama.cpp · mācās · bez Ollama";
            IsOffline = false;
            ActiveModel = health.Models.FirstOrDefault(m => m.Available)?.ModelName
                          ?? health.Models.FirstOrDefault()?.Details
                          ?? "Nav konfigurēts";
            ResourceText = "GGUF lokāli · atmiņa mācās · Ollama=OFF";
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
        // Iepriekšējā atbilde izgaist — hieroglifi atkal lido brīvi, tad salido jaunajā
        FormedAnswer = "";
        MatrixStatus = "◈ DOMĀ …";
        if (string.IsNullOrWhiteSpace(ChatOutput))
        {
            ChatOutput = $"Tu: {userText}";
        }
        else
        {
            ChatOutput += $"\n\nTu: {userText}";
        }

        // Immersīvā vienmēr paliekam uz Matrix; chrome režīmā — home, ja nav pin
        if (ImmersiveMode || !FocusPinned)
        {
            FocusSource = "home";
        }

        try
        {
            var result = await _api.ChatAsync(new ChatRequestDto
            {
                Message = userText,
                SessionId = ChatSessionId,
                WorkspacePath = string.IsNullOrWhiteSpace(WorkspacePath) ? null : WorkspacePath,
            });
            var reply = result.Reply ?? "";
            ChatOutput += $"\nMain Brain: {reply}";
            // Hieroglifi salido un izveido atbildi ekrāna centrā — VIENS ekrāns
            FormedAnswer = reply;
            MatrixStatus = ImmersiveMode ? "" : "◈ ATBILDE";
            if (result.Mode is "execute" or "act")
            {
                TerminalOutput += $"\n[{DateTime.Now:HH:mm:ss}] {result.Mode}: {result.GoalStatus ?? result.UiAction}";
                InspectorText = $"Darbība: {result.UiAction ?? result.GoalStatus}";
            }

            // Fiziski: pārlūks/fails/kamera — Matrix paliek, chrome paneļi NETiek atvērti immersīvā
            ApplyUiAction(result);
            OnPropertyChanged(nameof(ApprovalsVisibility));
        }
        catch (TaskCanceledException)
        {
            var err =
                "Modelis neatbildēja laikā. Lokālā AI uz CPU ir lēna — " +
                "aizver citas programmas un mēģini īsāku jautājumu.";
            ChatOutput += "\nMain Brain: " + err;
            FormedAnswer = err;
            MatrixStatus = "◈ LĒNI";
        }
        catch (Exception ex)
        {
            var msg = ex.Message ?? "";
            var err = msg.Contains("Timeout", StringComparison.OrdinalIgnoreCase) ||
                      msg.Contains("canceled", StringComparison.OrdinalIgnoreCase)
                ? "Modelis neatbildēja laikā. Aizver citas programmas un mēģini vēlreiz."
                : "Kļūda — " + msg;
            ChatOutput += "\nMain Brain: " + err;
            FormedAnswer = err;
            MatrixStatus = "◈ KĻŪDA";
        }
        finally
        {
            IsThinking = false;
            ActiveJobs = Math.Max(0, ActiveJobs - 1);
            await RefreshApprovalsAsync();
        }
    }

    private void ApplyUiAction(ChatResponseDto result)
    {
        try
        {
            // Immersīvais = VIENS galvenais ekrāns. Fiziskās darbības (pārlūks/fails/kamera)
            // notiek ārā vai Matrix atbildē — UI NEPĀRSLĒDZAS uz chrome paneļiem.
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
                BrowserUrl = result.OpenUrl;
                try
                {
                    Process.Start(new ProcessStartInfo
                    {
                        FileName = result.OpenUrl,
                        UseShellExecute = true,
                    });
                }
                catch
                {
                    // backend jau var būt atvēris sistēmas pārlūku
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
                    EditorText = System.IO.File.ReadAllText(result.OpenPath);
                    if (!stayOnMatrix)
                    {
                        FocusSource = "editor";
                    }
                }

                // Immersīvā: atver failu/attēlu ārēji, Matrix paliek
                try
                {
                    Process.Start(new ProcessStartInfo
                    {
                        FileName = result.OpenPath,
                        UseShellExecute = true,
                    });
                }
                catch
                {
                    // ignore
                }
            }

            if (!string.IsNullOrWhiteSpace(result.SpeakText))
            {
                SpeakLocal(result.SpeakText);
            }

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

    private static void SpeakLocal(string text)
    {
        try
        {
            var safe = text.Replace("'", "''");
            if (safe.Length > 600)
            {
                safe = safe[..600];
            }

            var ps =
                "Add-Type -AssemblyName System.Speech; " +
                "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; " +
                $"$s.Speak('{safe}')";
            Process.Start(new ProcessStartInfo
            {
                FileName = "powershell",
                Arguments = "-NoProfile -WindowStyle Hidden -Command \"" + ps.Replace("\"", "\\\"") + "\"",
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
