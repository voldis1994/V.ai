# BUILD_STATUS — Main Brain OS

**Atjaunināts:** 2026-10-21  
**Sesijas mērķis:** pilna specifikācijas implementācija  
**Vide:** Linux CI/dev (WPF palaišana bloķēta)

## Paveikts

### Backend (Python) — funkcionē
- [x] Tipizētie līgumi (`UserGoal`, `Plan`, `TaskNode`, …)
- [x] FastAPI lokālais API + WebSocket + Bearer auth
- [x] PolicyEngine ārpus LLM (STOP, apstiprinājumi, ceļu kanonizācija)
- [x] ToolProxy ar visiem specifikācijas rīkiem
- [x] ModelRouter (llama.cpp / Ollama) ar godīgu health
- [x] MemoryStore SQLite WAL + FTS5 + layout persistēšana
- [x] LearningEngine (metrikas, ranžēšana, LoRA eksporta vārti)
- [x] ResourceScheduler (aģentu/LLM/browser semafori, failu slēdzenes)
- [x] MainBrain LangGraph orķestrators (DAG, paralēlisms, verify, memory)
- [x] **Visi 50 aģenti** reģistrā ar līgumiem, rīkiem un izpildītājiem
- [x] CSV inventāra pieņemšanas plūsma (F)

### Desktop (C# WPF) — pirmkods ieviests
- [x] `MainBrain.Desktop` WPF MVVM (LV UI, Focus/Multi, WebView2, STOP)
- [x] `MainBrain.WinAutomation` (UIA/Input/Capture līgumi + Windows P/Invoke)
- [x] `MainBrain.Contracts` DTO
- [x] BackendHost + ApiClient
- [ ] Windows kompilācija/palaišana šajā vidē — **BLOĶĒTS**

### Skripti / docs / fixtures
- [x] `scripts/setup_windows.ps1`, `start_dev.ps1`, `build_release.ps1`, `run_acceptance.ps1`
- [x] docs: ARCHITECTURE, INSTALL_LV, USER_GUIDE_LV, SECURITY, REQUIREMENTS, TEST_REPORT
- [x] fixtures/sample_inventory_task
- [x] models/README.md, installer/README.md

## Pārbaudes rezultāti

| Pārbaude | Statuss |
|----------|---------|
| `pytest tests/python` | **21 passed** |
| `dotnet build MainBrain.Contracts` | **OK** |
| API smoke `/health` + `/agents` | **OK (50)** |
| `dotnet build MainBrain.Desktop` | **BLOĶĒTS** (nav Windows/WPF) |
| WebView2 / UIA / Notepad E2E | **BLOĶĒTS** (nav Windows) |
| llama-server inference | **BLOĶĒTS** (modelis/serveris nav uzstādīts) |

## Atlikušais darbs nākamajai sesijai (Windows mašīnā)

1. Palaist `./scripts/setup_windows.ps1`
2. `dotnet build MainBrainOS.sln -c Release` un labot jebkuras WPF/WebView2 kļūdas
3. `./scripts/build_release.ps1` → pārbaudīt `release/win-x64/MainBrain.exe`
4. Manuāli izpildīt pieņemšanas E, D, C (Notepad UIA, WebView2, paneļu režīmi)
5. Uzstādīt GGUF + `llama-server`, pārbaudīt J (bezsaistes inference)
6. Papildināt `docs/TEST_REPORT.md` ar Windows pierādījumiem

## Kā turpināt nekavējoties

```powershell
cd <repo>
./scripts/setup_windows.ps1
./scripts/run_acceptance.ps1
./scripts/start_dev.ps1
```

Linux turpinājumam:

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest -q tests/python
```

## Svarīgi ierobežojumi (godīgi)

- Šī sesija **neapgalvo**, ka WPF GUI ir palaists šajā Linux vidē.
- Windows Graphics Capture / UIA atgriež `unavailable` ārpus Windows — tas ir paredzēts.
- Bez lokāla modeļa LLM papildinājums ir nepieejams; aģentu determinētie ceļi darbojas.
