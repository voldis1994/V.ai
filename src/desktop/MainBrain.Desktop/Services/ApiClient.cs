using System.Net.Http;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text.Json;
using MainBrain.Contracts;

namespace MainBrain.Desktop.Services;

public sealed class ApiClient
{
    private readonly HttpClient _http;
    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNameCaseInsensitive = true,
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
    };

    public ApiClient(string baseUrl, string token)
    {
        _http = new HttpClient { BaseAddress = new Uri(baseUrl) };
        _http.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", token);
    }

    public async Task<HealthResponseDto?> GetHealthAsync()
    {
        using var client = new HttpClient { BaseAddress = _http.BaseAddress };
        return await client.GetFromJsonAsync<HealthResponseDto>("/health", JsonOptions);
    }

    public async Task<List<AgentDefinitionDto>> GetAgentsAsync()
    {
        return await _http.GetFromJsonAsync<List<AgentDefinitionDto>>("/agents", JsonOptions) ?? new();
    }

    public async Task<JsonElement> RunGoalAsync(RunGoalRequestDto request)
    {
        var resp = await _http.PostAsJsonAsync("/goals/run", request, JsonOptions);
        resp.EnsureSuccessStatusCode();
        await using var stream = await resp.Content.ReadAsStreamAsync();
        return await JsonSerializer.DeserializeAsync<JsonElement>(stream, JsonOptions);
    }

    public async Task<ChatResponseDto> ChatAsync(ChatRequestDto request)
    {
        var resp = await _http.PostAsJsonAsync("/chat", request, JsonOptions);
        resp.EnsureSuccessStatusCode();
        return await resp.Content.ReadFromJsonAsync<ChatResponseDto>(JsonOptions)
               ?? new ChatResponseDto { Reply = "(tukša atbilde)" };
    }

    public async Task StopAsync() => await _http.PostAsync("/control/stop", null);
    public async Task PauseAsync() => await _http.PostAsync("/control/pause", null);
    public async Task ResumeAsync() => await _http.PostAsync("/control/resume", null);

    public async Task<List<ApprovalRequestDto>> GetApprovalsAsync()
    {
        return await _http.GetFromJsonAsync<List<ApprovalRequestDto>>("/approvals", JsonOptions) ?? new();
    }

    public async Task DecideApprovalAsync(string id, string decision)
    {
        await _http.PostAsync($"/approvals/{id}/decide?decision={Uri.EscapeDataString(decision)}", null);
    }

    public async Task SaveLayoutAsync(object layout)
    {
        await _http.PutAsJsonAsync("/layout/default", layout, JsonOptions);
    }

    public async Task<JsonElement> GetLayoutAsync()
    {
        return await _http.GetFromJsonAsync<JsonElement>("/layout/default", JsonOptions);
    }
}
