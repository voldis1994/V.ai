# BUILD_STATUS — Main Brain OS

**Atjaunināts:** 2026-10-25  
**Zars:** `main` (sapludināts no `cursor/main-brain-os-full-impl`)  
**Vide:** Linux CI — WPF/UIA E2E BLOĶĒTS; Python backend TESTĒTS

## Gatavs uz `main`

- [x] Pilna specifikācijas implementācija (50 aģenti × 10 sadaļas)
- [x] WPF Desktop + WinAutomation (UIA/SendInput/Capture) + Named Pipe Bridge
- [x] FastAPI + LangGraph orķestrācija + Policy Engine + STOP
- [x] Focus / Multi-Window režīmi + WebView2
- [x] SQLite WAL + FTS5 atmiņa/mācīšanās
- [x] **Primārā inference: llama.cpp `llama-server` + GGUF** (Ollama izslēgta pēc noklusējuma)
- [x] `START_MAINBRAIN.bat` + `install_llama_server.ps1` + `start_llama_server.ps1` + `download_models.ps1`
- [x] Drošība: nav `/auth/token` noplūdes; WS auth; redaction; execution policy
- [x] `pytest tests/python` — **30 passed**

## Atlikušais tikai Windows mašīnā (ne Linux)

1. `START_MAINBRAIN.bat` → bootstrap + GGUF + llama-server
2. `dotnet build` / `build_release.ps1` un E2E D–H, L
3. Aizpildīt `WINDOWS_VALIDATION.md` / `RELEASE_VERIFICATION.md` ar pierādījumiem

## Svarīgi

- 50 aģentu ID **nav** mainīti.
- Linuxā Windows rīki godīgi atgriež `unavailable` / `performed=false`.
- Netiek apgalvots, ka Notepad/WebView2 E2E ir TESTĒTS Linux vidē.
