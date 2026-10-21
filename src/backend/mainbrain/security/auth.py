from __future__ import annotations

import secrets
from dataclasses import dataclass, field


@dataclass
class AuthGate:
    """Lokālā API autentifikācija ar īslaicīgu noslēpumu."""

    token: str = field(default_factory=lambda: secrets.token_urlsafe(32))

    def issue(self) -> str:
        self.token = secrets.token_urlsafe(32)
        return self.token

    def verify(self, provided: str | None) -> bool:
        if not provided:
            return False
        return secrets.compare_digest(provided, self.token)
