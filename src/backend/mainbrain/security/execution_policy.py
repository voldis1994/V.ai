from __future__ import annotations

import shlex
from typing import Any


# Atļautās bāzes komandas ierobežotā režīmā.
ALLOWED_SHELL_PREFIXES = {
    "python",
    "python3",
    "pytest",
    "pip",
    "dotnet",
    "git",
    "pwd",
    "ls",
    "dir",
    "echo",
    "type",
    "cat",
    "where",
    "which",
    "curl",
    "wget",
    "ping",
    "ipconfig",
    "ifconfig",
    "netstat",
    "powershell",
    "pwsh",
    "cmd",
    "notepad",
    "explorer",
    "start",
    "code",
    "npm",
    "node",
    "cargo",
    "go",
    "docker",
    "winget",
    "choco",
}

# Pat full_access režīmā — katastrofālas darbības
DENIED_SHELL_PATTERNS = [
    "rm -rf /",
    "rm -rf /*",
    "del /s /q c:\\",
    "del /f /s /q c:\\",
    "format c:",
    "format d:",
    "mkfs.",
    ":(){:|:&};:",
    "dd if=/dev/zero of=/dev/sd",
]


def assess_shell_command(
    command: str | list[str],
    *,
    full_access: bool = False,
) -> dict[str, Any]:
    if isinstance(command, list):
        text = " ".join(map(str, command))
        tokens = [str(c) for c in command]
    else:
        text = str(command)
        try:
            tokens = shlex.split(text, posix=True)
        except ValueError:
            tokens = text.split()

    lowered = text.lower()
    for bad in DENIED_SHELL_PATTERNS:
        if bad.lower() in lowered:
            return {
                "allowed": False,
                "requires_approval": True,
                "reason": f"Komanda satur aizliegtu katastrofālu šablonu: {bad}",
                "risk": "critical",
            }

    if not tokens:
        return {"allowed": False, "requires_approval": True, "reason": "Tukša komanda", "risk": "high"}

    if full_access:
        return {
            "allowed": True,
            "requires_approval": False,
            "reason": "full_access: atļauta jebkura komanda (izņemot katastrofālus šablonus)",
            "risk": "medium",
        }

    head = tokens[0].lower().rsplit("\\", 1)[-1].rsplit("/", 1)[-1]
    head = head.removesuffix(".exe").removesuffix(".cmd").removesuffix(".bat")
    if head in ALLOWED_SHELL_PREFIXES:
        return {
            "allowed": True,
            "requires_approval": False,
            "reason": "Komanda ir atļauto prefiksu sarakstā",
            "risk": "medium",
        }

    return {
        "allowed": False,
        "requires_approval": True,
        "reason": f"Komanda '{head}' nav noklusētajā atļauju sarakstā",
        "risk": "high",
    }


def assess_python_code(code: str, *, full_access: bool = False) -> dict[str, Any]:
    if full_access:
        return {
            "allowed": True,
            "requires_approval": False,
            "reason": "full_access: Python kods atļauts",
            "risk": "medium",
        }
    lowered = code.lower()
    dangerous = [
        "os.system(",
        "subprocess.",
        "socket.",
        "shutil.rmtree('/'",
        'shutil.rmtree("/"',
        "__import__('ctypes')",
        "winreg",
    ]
    for item in dangerous:
        if item in lowered:
            return {
                "allowed": False,
                "requires_approval": True,
                "reason": f"Python kods satur riskantu konstrukciju: {item}",
                "risk": "high",
            }
    return {"allowed": True, "requires_approval": False, "reason": "Python kods šķietami drošs projektam", "risk": "low"}
