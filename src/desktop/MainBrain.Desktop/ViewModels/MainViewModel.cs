using System.Collections.ObjectModel;
using System.Text.Json;
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
    [ObservableProperty] private string _currentPanelKind = "Žurnāls";

    public ObservableCollection<AgentDefinitionDto> Agents { get; } = new();
    public ObservableCollection<string> Sections { get; } = new();
    public ObservableCollection<ApprovalRequestDto> Approvals { get; } = new();
    public ObservableCollection<ProgressEventDto> Timeline { get; } = new();
    public ObservableCollection<WorkPanelViewModel> Panels { get; } = new();

    public MainViewModel(ApiClient api)
    {
        _api = api;
        WorkspacePath = Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments);
        Panels.Add(new WorkPanelViewModel("Žurnāls", "log"));
        Panels.Add(new WorkPanelViewModel("Iegultais pārlūks", "embedded_browser"));
        Panels.Add(new WorkPanelViewModel("Redaktors", "editor"));
        Panels.Add(new WorkPanelViewModel("Terminālis", "terminal"));
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
            ActiveModel = health.Models.FirstOrDefault(m => m.Available)?.ModelName ?? "Nav konfigurēts";
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
            InspectorText = $"Ielādēti {Agents.Count} aģenti.";
        }
        catch (Exception ex)
        {
            StatusText = "Kļūda";
            ChatOutput += "\n" + ex.Message;
        }
    }

    [RelayCommand]
    private void ToggleMode()
    {
        IsFocusMode = !IsFocusMode;
        CurrentPanelKind = IsFocusMode ? "Fokusa darba zona" : "Vairāku logu režīms";
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
            ChatOutput += "\n" + result.GetRawText();
            TerminalOutput += $"\n[{DateTime.Now:HH:mm:ss}] Mērķis pabeigts";
            InspectorText = "Uzdevuma rezultāts saņemts. Skatiet notikumu laika līniju.";
        }
        catch (Exception ex)
        {
            ChatOutput += "\nKļūda: " + ex.Message;
        }
        finally
        {
            ActiveJobs = Math.Max(0, ActiveJobs - 1);
            ChatInput = "";
        }
    }

    [RelayCommand]
    private async Task EmergencyStopAsync()
    {
        await _api.StopAsync();
        StatusText = "STOP aktīvs";
        ChatOutput += "\n[STOP] Jaunas darbības liegtas.";
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
    [ObservableProperty] private string _content = "";
}
