# IMPLEMENTATION_AUDIT — Main Brain OS

**Datums:** 2026-10-22  
**Zars:** `cursor/main-brain-os-full-impl`  
**Vide:** Linux (WPF/UIA palaišana BLOĶĒTA; pirmkods tiek pabeigts Windows izpildei)

## Metodika

1. Izlasīti `docs/SPEC_LV.md`, `BUILD_STATUS.md`, `TEST_REPORT.md`, `REQUIREMENTS_CHECKLIST.md`.
2. Pārbaudīti `src/backend/mainbrain/**`, `src/desktop/**`, skripti un testi.
3. Meklēti stub/placeholder/unavailable/fake-success indikatori.
4. Atšķirti: (A) apzināti platformas atzari, (B) īstas implementācijas nepilnības.

## Komponenšu audits

| Komponente | Statuss | Piezīme |
|------------|---------|---------|
| 50 aģentu reģistrs (`catalog.py`) | OK | Saglabājams; unikāli ID 1–50 |
| AgentRuntime specializētie ceļi | DAĻĒJI | Daudzi ceļi reāli; Windows/browser daļa caur stub |
| ToolProxy faili/git/python/tests | OK | Darbojas; testi izturēti |
| ToolProxy window/uia/input/screen/browser | **NEPILNĪGS** | Stubi; jāsavieno ar Desktop Bridge |
| PolicyEngine | DAĻĒJI | Apstiprinājumi OK; shell/python pārāk atļaujošs |
| `/auth/token` | **DROŠĪBAS CAURUMS** | Neautentificēts tokens |
| WebSocket auth caur query | **RISKS** | Tokens URL |
| ModelRouter | DAĻĒJI | Veselība pēc `/models`; nav īstas inference pārbaudes |
| MainBrain orķestrators | DAĻĒJI | Statiskas CSV darbplūsmas; trūkst shēmas validēta LLM plāna |
| LearningEngine | DAĻĒJI | Metrikas OK; atmiņa vāji ietekmē plānošanu |
| UiAutomationService | **STUB** | Atgriež `invoked`/`set` bez darbības |
| InputService | **STUB** | Atgriež `queued` bez SendInput |
| WindowCaptureService | **STUB** | Atgriež `live_image` bez kadra |
| MainWindow Focus/Multi | **NEPILNĪGS** | Toggle maina tekstu, ne izkārtojumu |
| WebView2 paneļa vadība | **NEPILNĪGS** | Nav rīku tilta no backend |
| BackendHost laidiena ceļi | **NEPILNĪGS** | Meklē repo sakni; neportatīvs |
| Python testi | OK | 21 passed (iepriekšējā sesijā) |
| Windows E2E A–L | BLOĶĒTS | Nav Windows vides šajā sesijā |

## Prioritātes šajā sesijā — izpilde

1. [x] WinAutomation īstā implementācija (UIA, SendInput, PrintWindow/BitBlt capture).
2. [x] Desktop Tool Bridge + ToolProxy savienošana.
3. [x] Auth/token/WebSocket drošības labojumi + izpildes politika.
4. [x] Focus/Multi režīmu īsta UI pārslēgšana + layout.
5. [x] LLM plānošana ar shēmas validāciju + labošanas cikls.
6. [x] ModelRouter īsta inference pārbaude.
7. [x] Laidiena/BackendHost uzlabojumi + dokumentācija.

## Atlikušais (Windows runtime)

- Dotnet restore/build ar FlaUI uz Windows
- E2E D–H, L ar pierādījumiem
- Lokāla modeļa B/J testi

## Saglabājamie līgumi

- 50 aģentu ID un numuri nemainās.
- Esošie Pydantic/C# DTO līgumi tiek paplašināti, neiznīcināti.
- Esošie Python testi jāsaglabā un jāpapildina.
