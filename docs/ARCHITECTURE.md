# Main Brain OS — Arhitektūra

## Pārskats

Main Brain OS ir lokāls Windows AI vadības centrs ar:

1. **MainBrain.exe** — vienīgais lietotājam redzamais WPF logs (MVVM, CommunityToolkit.Mvvm, WebView2).
2. **Python FastAPI backend** — loopback API (`127.0.0.1`) ar tipizētiem līgumiem.
3. **Main Brain orķestrators** — LangGraph grafs: analīze → plāns/DAG → izpilde → pārbaude → atmiņa.
4. **Tieši 50 aģenti** — reģistrs ar ID, lomām, rīkiem, līgumiem un izpildītājiem.
5. **Politiku dzinējs ārpus LLM** — atļaujas, apstiprinājumi, STOP, ceļu kanonizācija.
6. **Lokālā inference** — llama.cpp (`llama-server`) / Ollama adapteri; nav mākoņa noklusējuma.

## Procesu modelis

```
MainBrain.exe
  ├─ WPF UI (Focus / Multi-Window)
  ├─ WebView2 iegultā sesija
  ├─ WinAutomation (UIA, SendInput, Window Capture)
  └─ BackendHost → python -m mainbrain.api.app
         ├─ AgentRuntime (50 izpildītāji)
         ├─ ToolProxy + PolicyEngine
         ├─ ModelRouter
         ├─ MemoryStore (SQLite WAL + FTS5)
         └─ LearningEngine
```

## Datu plūsma

`UserGoal → Strategist → RequirementsPlanner(DAG) → paralēla aģentu izpilde → ResultReviewer → KnowledgeCurator`

## Drošības robeža

- Rīku izsaukumi vienmēr iet caur `PolicyEngine` pirms izpildes.
- Tīmekļa/failu saturs ir **dati**, nevis komandas.
- Lokālais API: loopback + Bearer token (`%LOCALAPPDATA%\MainBrainOS\api_token.txt`).
- UAC netiek apiešana; `asInvoker` manifests.

## Paneļu režīmi

- **Focus Mode** — viens liels darba laukums ar automātisku sekošanu (var fiksēt).
- **Multi-Window Mode** — dokojami/cilņu paneļi; pārslēgšana nesāc darbus no jauna.
- Paneļu tipi: `Dzīvais attēls`, `Iegultais pārlūks`, `Redaktors`, `Terminālis`, `Žurnāls`, `Nav pieejams`.

## Tehnoloģiju izvēle

| Slānis | Tehnoloģija | Versija |
|--------|-------------|---------|
| Desktop | .NET WPF | net8.0-windows |
| MVVM | CommunityToolkit.Mvvm | 8.3.2 |
| Pārlūks | WebView2 | 1.0.2849.39 |
| Backend | FastAPI | 0.115.6 |
| Grafs | LangGraph | 0.2.60 |
| Dati | SQLite WAL + FTS5 | stdlib/aiosqlite |
| Modeļi | llama.cpp / Ollama | adapteri |

## Ierobežojumi

- Ārējas programmas **netiek** fiziski iegultas kā WPF bērnlogi; tiek rādīts autentisks attēls (`live_image`) vai `unavailable`.
- WPF/UIA/WGC testi ir **BLOĶĒTI** Linux CI vidē; Python pieņemšanas testi ir izpildāmi visur.
