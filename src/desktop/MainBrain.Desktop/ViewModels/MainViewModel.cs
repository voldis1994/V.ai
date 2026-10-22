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
    [ObservableProperty] private string _chatOutput = "Sveicināti! Ievadiet mērķi latviešu valodā.";
    [ObservableProperty] private string _terminalOutput = "";
    [ObservableProperty] private AgentDefinitionDto? _selectedAgent;
    [ObservableProperty] private string _inspectorText = "Izvēlieties aģentu vai palaidiet uzdevumu.";
    [ObservableProperty] private string _workspacePath = "";
    [ObservableProperty] private string _browserUrl = "https://example.com";
    [ObservableProperty] private string _currentPanelKind = "Iegultais pārlūks";
    [ObservableProperty] private string _focusSource = "browser";
    [ObservableProperty] private bool _focusPinned;
    [ObservableProperty] private string? _liveImagePath;
    [ObservableProperty] private string _editorText = "# Main Brain OS redaktors\n";
    [ObservableProperty] private string _navSection = "Main Brain";

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

    public MainViewModel(ApiClient api)
    {
        _api = api;
        WorkspacePath = Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments);
        Panels.Add(new WorkPanelViewModel("Iegultais pārlūks", "embedded_browser") { IsVisible = true });
        Panels.Add(new WorkPanelViewModel("Redaktors", "editor") { IsVisible = true });
        Panels.Add(new WorkPanelViewModel("Terminālis", "terminal") { IsVisible = true });
        Panels.Add(new WorkPanelViewModel("Dzīvais attēls", "live_image") { IsVisible = true });
        Panels.Add(new WorkPanelViewModel("Aģentu aktivitāte", "log") { IsVisible = true });
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
        OnPropertyChanged(nameof(FocusVisibility));
        OnPropertyChanged(nameof(MultiVisibility));
        CurrentPanelKind = value ? $"Focus: {FocusSource}" : "Vairāku logu režīms";
        _ = SaveLayoutAsync();
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
    private void SelectFocusSource(string? source)
    {
        if (string.IsNullOrWhiteSpace(source) || FocusPinned)
        {
            return;
        }

        FocusSource = source;
        CurrentPanelKind = $"Focus: {source}";
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
        if (string.IsNullOrWhiteSpace(ChatInput))
        {
            return;
        }

        ActiveJobs++;
        ChatOutput += $"\n\n> {ChatInput}";
        try
        {
            var result = await _api.RunGoalAsync(new RunGoalRequestDto
            {
                Text = ChatInput,
                WorkspacePath = string.IsNullOrWhiteSpace(WorkspacePath) ? null : WorkspacePath,
            });
            ChatOutput += "\n" + SummarizeGoal(result);
            TerminalOutput += $"\n[{DateTime.Now:HH:mm:ss}] Mērķis pabeigts";
            InspectorText = "Uzdevuma rezultāts saņemts.";
            if (!FocusPinned)
            {
                FocusSource = "log";
            }
        }
        catch (Exception ex)
        {
            ChatOutput += "\nKļūda: " + ex.Message;
        }
        finally
        {
            ActiveJobs = Math.Max(0, ActiveJobs - 1);
            ChatInput = "";
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
