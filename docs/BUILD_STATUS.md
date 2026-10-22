# BUILD_STATUS — Main Brain OS

**Atjaunināts:** 2026-10-22  
**Zars:** `cursor/main-brain-os-full-impl`  
**Vide:** Linux (WPF/UIA palaišana BLOĶĒTA)

## Šīs sesijas paveiktais (turpinājums, nevis pārrakstīšana)

### Audits
- [x] `docs/IMPLEMENTATION_AUDIT.md`

### Windows vadība (īsta implementācija)
- [x] `UiAutomationService` — FlaUI UIA3 (query/invoke/set_value/tree/find_window), `performed` tikai pēc darbības
- [x] `InputService` — SendInput (move/click/type/shortcut), ekskluzīvs owner, STOP
- [x] `WindowCaptureService` — PrintWindow/BitBlt, PNG kadrs; `live_image` tikai ar failu
- [x] `ToolBridgeServer` (Named Pipe) + Python `DesktopToolBridge`
- [x] ToolProxy Windows/browser rīki caur tiltu (bez fake queued navigācijas)

### Drošība
- [x] Noņemts `/auth/token` (404) — tokens tikai no vides/DesktopHost
- [x] WebSocket auth ar pirmo JSON ziņojumu (nav tokena URL)
- [x] `execution_policy` čaulai/Python kodam
- [x] STOP aptur owned procesus + bridge stop

### Main Brain
- [x] `AiPlanner` — LLM JSON plāns ar shēmas/aģentu validāciju + rezerves DAG
- [x] Atmiņas hinti plānošanā
- [x] Labošanas cikls (test → fix → retest) orķestratorā
- [x] ModelRouter — īsta īsa inference pārbaude (ne tikai `/models`)

### Desktop UI
- [x] Focus/Multi **īsta** Visibility pārslēgšana
- [x] Focus avotu izvēle + fiksēšana
- [x] Layout saglabāšana/ielāde
- [x] WebView2 `BrowserAutomationService`
- [x] BackendHost portatīvie ceļi (`runtime-venv`, `backend/`)

## Testi

| Pārbaude | Statuss |
|----------|---------|
| `pytest tests/python` | **28 passed** |
| Contracts `dotnet test` | OK (iepriekš) |
| WPF/UIA/Notepad/WebView2 E2E | **BLOĶĒTS** |
| Laidiena palaišana ārpus repo | **BLOĶĒTS** |
| Lokāla modeļa inference | **BLOĶĒTS** (nav servera/modeļa) |

## Atlikušais (tikai Windows mašīnā)

1. `./scripts/setup_windows.ps1` + `dotnet build MainBrainOS.sln`
2. Labot jebkuras FlaUI/WPF restore kļūdas
3. `./scripts/build_release.ps1` un E2E D–H, L
4. Pieslēgt llama-server + GGUF → Tests B/J
5. Aizpildīt `WINDOWS_VALIDATION.md` / `RELEASE_VERIFICATION.md` ar pierādījumiem

## Svarīgi

- 50 aģentu ID **nav** mainīti.
- Linuxā Windows rīki godīgi atgriež `unavailable` / `performed=false`.
- Netiek apgalvots, ka Notepad/WebView2 E2E ir TESTĒTS šajā vidē.
