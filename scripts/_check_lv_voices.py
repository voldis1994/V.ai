"""Pārbauda, ka Microsoft Everita/Nils latviešu balsis ir pieejamas (edge-tts)."""
from __future__ import annotations

import asyncio
import sys


async def main() -> int:
    try:
        import edge_tts
    except ImportError:
        print("edge-tts nav instalēts", file=sys.stderr)
        return 1
    voices = await edge_tts.list_voices()
    lv = [v for v in voices if str(v.get("Locale", "")).startswith("lv")]
    for v in lv:
        print(" ", v["ShortName"], "-", v.get("Gender"))
    if not any(v["ShortName"] == "lv-LV-EveritaNeural" for v in lv):
        print("Trūkst Everita (lv-LV-EveritaNeural)", file=sys.stderr)
        return 1
    print("OK: Everita pieejama")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
