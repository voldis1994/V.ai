using System.Collections.ObjectModel;
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
    [ObservableProperty] private bool _isOffline;
    [ObservableProperty] private int _activeJobs;
    [ObservableProperty] private bool _isFocusMode = true;
    [ObservableProperty] private string _chatInput = "";
    [ObservableProperty] private string _chatOutput =
        "Sveiki! Esmu Main Brain — varam brīvi sarunāties latviešu valodā.\n" +
        "Jautā, plāno, vai lūdz izpildīt (piem. «Izveido Python skriptu…»).\n" +
        "Padoms: «Izpildi: …» piespiedīs aģentu orķestrāciju.";
    [ObservableProperty] private string _chatSessionId = "ui";
    [ObservableProperty] private bool _isThinking;
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
        WorkspacePath = Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments);
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

            StatusText = health.EmergencyStop ? "STOP aktīvs" : "Lokāli aktīvs";
            IsOffline = false;
            ActiveModel = health.Models.FirstOrDefault(m => m.Available)?.ModelName
                          ?? health.Models.FirstOrDefault()?.Details
                          ?? "Nav konfigurēts";
            ResourceText = "Resursi: skatīt diagnostiku";
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

            await RefreshApprovalsAsync();
            await LoadLayoutAsync();
            InspectorText = $"Ielādēti {Agents.Count} aģenti. Režīms: {(IsFocusMode ? "Focus" : "Multi")}.";
        }
        catch (Exception ex)
        {
            StatusText = "Kļūda";
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
        ChatOutput += $"\n\nTu: {userText}";
        // Saruna ir galvenā virsma — paliekam chat/home, ja nav fiksēts cits panelis
        if (!FocusPinned && FocusSource is "home" or "log")
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
            ChatOutput += $"\n\nMain Brain: {result.Reply}";
            if (result.Mode == "execute")
            {
                TerminalOutput += $"\n[{DateTime.Now:HH:mm:ss}] Izpilde: {result.GoalStatus}";
                InspectorText = $"Uzdevums izpildīts. Statuss: {result.GoalStatus}";
                ShowInspector = true;
                if (!FocusPinned)
                {
                    FocusSource = "log";
                }
            }
            OnPropertyChanged(nameof(ApprovalsVisibility));
        }
        catch (Exception ex)
        {
            ChatOutput += "\n\nMain Brain: Kļūda — " + ex.Message;
        }
        finally
        {
            IsThinking = false;
            ActiveJobs = Math.Max(0, ActiveJobs - 1);
            await RefreshApprovalsAsync();
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
