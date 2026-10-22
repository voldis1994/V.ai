# Testu pārskats

**Datums:** 2026-10-22  
**Zars:** `cursor/main-brain-os-full-impl`  
**Vide:** Linux x86_64, Python 3.12

## Automatizētie Python testi

```bash
.venv/bin/pytest -q tests/python
```

**Rezultāts: 28 passed**

Jaunie/papildinātie:
- `test_planner_and_security.py` — AI plānotāja fallback, execution policy, bridge unavailable, `/auth/token` noņemts
- Esošie reģistra/API/CSV/STOP/injekcijas testi saglabāti

## Windows E2E (A–L)

| Tests | Statuss | Piezīme |
|-------|---------|---------|
| A 50 aģenti (API) | TESTĒTS | 50 unikāli |
| A 50 aģenti (GUI) | BLOĶĒTS | Nav Windows |
| B Lokālais modelis | BLOĶĒTS | Nav llama-server |
| C Python CSV | TESTĒTS | pytest plūsma |
| D Notepad | BLOĶĒTS | Nav Windows |
| E Capture | BLOĶĒTS | Nav Windows |
| F Focus Mode | IEVIESTS / BLOĶĒTS GUI | Kods ir; nav Windows |
| G Multi-Window | IEVIESTS / BLOĶĒTS GUI | Kods ir; nav Windows |
| H Pārlūks | IEVIESTS / BLOĶĒTS GUI | WebView2 serviss |
| I Drošība | TESTĒTS (API/policy) | Auth token endpoint removed |
| J Atmiņa/layout | TESTĒTS (API) | layout persist |
| K Bez interneta + modelis | BLOĶĒTS | Nav modeļa |
| L Laidiens | BLOĶĒTS | Nav Windows publish |

## Godīguma piezīme

`IEVIESTS` ≠ `TESTĒTS`. Windows GUI testi nav izdomāti kā veiksmīgi.
