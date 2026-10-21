# Testu pārskats

**Datums:** 2026-10-21  
**Vide:** Linux x86_64, Python 3.12.3, .NET SDK 8.0.426 (bez WPF workload)

## Automatizētie Python testi

Komanda:

```bash
.venv/bin/pytest -q tests/python
```

**Rezultāts: 21 passed**

| Tests | Segums |
|-------|--------|
| `test_registry.py` | 50 unikāli aģenti, 10 nodaļas, līgumi |
| `test_policy.py` | STOP, apstiprinājumi, ceļi ārpus mapes, redaction |
| `test_tools_and_agents.py` | failu rīki, 50 aģentu izsaukums, CSV plūsma, failu slēdzenes |
| `test_api_and_brain.py` | health, auth, `/goals/run`, layout, metrics, STOP |
| `test_prompt_injection.py` | tīmekļa/uzvednes saturs nav privileģētas komandas |

## .NET

```bash
dotnet build src/desktop/MainBrain.Contracts/MainBrain.Contracts.csproj -c Release
```

**Rezultāts: Build succeeded**

`MainBrain.Desktop` (WPF) un `MainBrain.WinAutomation` (`net8.0-windows`) — **BLOĶĒTS** šajā Linux vidē (nav Windows + WPF workload). Windows komandas:

```powershell
./scripts/setup_windows.ps1
./scripts/run_acceptance.ps1
./scripts/build_release.ps1
```

## Pieņemšanas kritēriji (A–M)

Skatīt `docs/REQUIREMENTS_CHECKLIST.md` un `docs/BUILD_STATUS.md`.

## Smoke pārbaude

- `/health` → `status=ok`, `agents=50`
- `/agents` ar Bearer token → 50 ieraksti
