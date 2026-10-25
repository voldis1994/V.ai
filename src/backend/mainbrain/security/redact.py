from __future__ import annotations

import re
from typing import Any

SECRET_PATTERNS = [
    re.compile(
        r"(?i)\b(api[_-]?key|token|secret|password|passwd|authorization)\b\s*[:=]\s*['\"]?([^\s'\"]+)"
    ),
    re.compile(r"(?i)\bbearer\s+[a-z0-9\-._~+/]+=*"),
]


def redact_text(text: str) -> str:
    redacted = text
    for pattern in SECRET_PATTERNS:
        if pattern.pattern.startswith("(?i)\\bbearer"):
            redacted = pattern.sub("Bearer ***", redacted)
        else:
            redacted = pattern.sub(lambda m: f"{m.group(1)}=***", redacted)
    return redacted


def redact_secrets(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {k: ("***" if _is_sensitive_key(k) else redact_secrets(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_secrets(v) for v in value]
    return value


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return any(part in lowered for part in ("password", "secret", "token", "api_key", "authorization"))
