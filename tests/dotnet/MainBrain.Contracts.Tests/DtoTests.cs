using MainBrain.Contracts;
using Xunit;

namespace MainBrain.Contracts.Tests;

public class DtoTests
{
    [Fact]
    public void AgentDefinitionDto_Defaults()
    {
        var dto = new AgentDefinitionDto { Id = "Strategist", Number = 1, Name = "Strategist" };
        Assert.Equal("Strategist", dto.Id);
        Assert.Equal(1, dto.Number);
        Assert.Empty(dto.AllowedTools);
    }

    [Fact]
    public void CaptureSession_UnavailableByDefault()
    {
        var capture = new CaptureSessionDto();
        Assert.Equal("unavailable", capture.Status);
    }
}
