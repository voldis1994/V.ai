from __future__ import annotations

import uuid
from datetime import datetime, timezone


def new_id(prefix: str = "") -> str:
    value = uuid.uuid4().hex
    return f"{prefix}{value}" if prefix else value


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
