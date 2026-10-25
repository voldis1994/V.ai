using System.Text.Json.Serialization;

namespace MainBrain.Contracts;

public sealed class UserGoalDto
{
    public string Id { get; set; } = "";
    public string Text { get; set; } = "";
    public string Language { get; set; } = "lv";
    public string? WorkspacePath { get; set; }
    public string CorrelationId { get; set; } = "";
}

public sealed class AgentDefinitionDto
{
    public string Id { get; set; } = "";
    public int Number { get; set; }
    public string Name { get; set; } = "";
    public string Section { get; set; } = "";
    public string Description { get; set; } = "";
    public List<string> Responsibilities { get; set; } = new();
    public string ModelRole { get; set; } = "reasoning";
    public List<string> AllowedTools { get; set; } = new();
    public string RiskCategory { get; set; } = "low";
    public List<string> Constraints { get; set; } = new();
}

public sealed class ToolRequestDto
{
    public string Id { get; set; } = "";
    public string Tool { get; set; } = "";
    public Dictionary<string, object?> Arguments { get; set; } = new();
    public string? AgentId { get; set; }
    public string? TaskId { get; set; }
}

public sealed class ToolResultDto
{
    public string RequestId { get; set; } = "";
    public string Tool { get; set; } = "";
    public bool Ok { get; set; }
    public object? Output { get; set; }
    public string? Error { get; set; }
}

public sealed class ProgressEventDto
{
    public string Id { get; set; } = "";
    public string CorrelationId { get; set; } = "";
    public string EventType { get; set; } = "";
    public string Message { get; set; } = "";
    public string? TaskId { get; set; }
    public string? AgentId { get; set; }
    public DateTime Timestamp { get; set; }
}

public sealed class ApprovalRequestDto
{
    public string Id { get; set; } = "";
    public string Action { get; set; } = "";
    public List<string> Paths { get; set; } = new();
    public string? Command { get; set; }
    public string Source { get; set; } = "";
    public string Reason { get; set; } = "";
    public string Impact { get; set; } = "";
    public string Status { get; set; } = "pending";
}

public sealed class ModelHealthDto
{
    public string Role { get; set; } = "";
    public bool Available { get; set; }
    public string? Provider { get; set; }
    public string? ModelName { get; set; }
    public string Details { get; set; } = "";
}

public sealed class CaptureSessionDto
{
    public string Id { get; set; } = "";
    public long? Hwnd { get; set; }
    public string? ProcessName { get; set; }
    public string Status { get; set; } = "unavailable";
    public string? FramePath { get; set; }
    public string? Error { get; set; }
    public DateTime UpdatedAt { get; set; } = DateTime.UtcNow;
}

public sealed class LearningMetricDto
{
    public string AgentId { get; set; } = "";
    public double SuccessRate { get; set; }
    public double AvgDurationMs { get; set; }
    public int RetryCount { get; set; }
    public double TestPassRate { get; set; }
    public int ManualApprovals { get; set; }
    public int Samples { get; set; }
}

public sealed class RunGoalRequestDto
{
    public string Text { get; set; } = "";
    public string? WorkspacePath { get; set; }
    public List<string> Constraints { get; set; } = new();
    public List<string> SuccessCriteria { get; set; } = new();
}

public sealed class ChatRequestDto
{
    public string Message { get; set; } = "";
    public string SessionId { get; set; } = "default";
    public string? WorkspacePath { get; set; }
    public bool? ForceExecute { get; set; }
}

public sealed class ChatResponseDto
{
    public string Reply { get; set; } = "";
    public string Mode { get; set; } = "chat";
    public string SessionId { get; set; } = "default";
    public string? GoalStatus { get; set; }
    public string? UiAction { get; set; }
    public string? OpenUrl { get; set; }
    public string? OpenPath { get; set; }
    public string? Focus { get; set; }
    public string? SpeakText { get; set; }
    public string? ImagePath { get; set; }
}

public sealed class HealthResponseDto
{
    public string Status { get; set; } = "";
    public string Version { get; set; } = "";
    public bool EmergencyStop { get; set; }
    public int Agents { get; set; }
    public List<ModelHealthDto> Models { get; set; } = new();
}
