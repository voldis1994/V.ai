"""Īss tests: runā ar Everita latviešu balsi."""
from __future__ import annotations

import sys
from pathlib import Path

# repo/src/backend uz PYTHONPATH
_backend = Path(__file__).resolve().parents[1] / "src" / "backend"
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend))

from mainbrain.tools.sense import DEFAULT_LV_VOICE, speak_text  # noqa: E402


def main() -> int:
    print("Balss:", DEFAULT_LV_VOICE)
    result = speak_text("Sveiki! Esmu Main Brain latviešu balsī.", lang="lv")
    print(result)
    if not result.get("ok"):
        print("WARN: atskanosana neizdevas:", result.get("error"), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
