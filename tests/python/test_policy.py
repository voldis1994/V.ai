from pathlib import Path

from mainbrain.contracts.schemas import ToolRequest
from mainbrain.security.policy import PolicyEngine
from mainbrain.security.redact import redact_text


def test_emergency_stop_blocks_tools(tmp_path: Path):
    policy = PolicyEngine(tmp_path)
    policy.stop()
    decision = policy.decide(ToolRequest(tool="files.read", arguments={"path": str(tmp_path / "a.txt")}))
    assert decision.allowed is False
    assert "STOP" in decision.reason


def test_delete_outside_workspace_requires_approval(tmp_path: Path):
    policy = PolicyEngine(tmp_path)
    decision = policy.decide(
        ToolRequest(tool="files.delete", arguments={"path": "/tmp/not_in_workspace.txt"})
    )
    assert decision.allowed is False
    assert decision.requires_approval is True
    assert decision.approval_id


def test_untrusted_exe_requires_approval(tmp_path: Path):
    policy = PolicyEngine(tmp_path)
    decision = policy.decide(
        ToolRequest(
            tool="process.start",
            arguments={"program": str(tmp_path / "download" / "malware.exe")},
        )
    )
    assert decision.requires_approval is True


def test_approval_task_grant(tmp_path: Path):
    policy = PolicyEngine(tmp_path)
    decision = policy.decide(
        ToolRequest(
            tool="files.delete",
            arguments={"path": "/tmp/x.txt"},
            task_id="task1",
        )
    )
    assert decision.approval_id
    policy.decide_approval(decision.approval_id, "allowed_task")
    decision2 = policy.decide(
        ToolRequest(tool="files.delete", arguments={"path": "/tmp/x.txt"}, task_id="task1")
    )
    assert decision2.allowed is True


def test_redact_secrets():
    text = "api_key=supersecret123"
    assert "supersecret123" not in redact_text(text)
