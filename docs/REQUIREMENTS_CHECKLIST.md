# Prasību kontrolsaraksts

Statusi: `IEVIESTS` / `TESTĒTS` / `BLOĶĒTS` / `NESTRĀDĀ`

| ID | Prasība | Statuss |
|----|---------|---------|
| 0.1 | MainBrain.exe WPF LV UI | IEVIESTS / BLOĶĒTS palaišana Linux |
| 0.2 | Lokāli bez maksas API | IEVIESTS / TESTĒTS (nav cloud fallback) |
| 0.3 | 50 aģenti | IEVIESTS / TESTĒTS |
| 0.4 | DAG + paralēlisms + pārbaude + AI plāns | IEVIESTS / TESTĒTS (fallback+API) |
| 0.5 | Focus Mode īsts | IEVIESTS / BLOĶĒTS GUI |
| 0.6 | Multi-Window īsts | IEVIESTS / BLOĶĒTS GUI |
| 0.7 | Kods + Windows vadība | IEVIESTS; Windows E2E BLOĶĒTS |
| 0.8 | Persistēšana | IEVIESTS / TESTĒTS |
| 0.9 | Politika + STOP | IEVIESTS / TESTĒTS |
| Auth token noplūde | Novērsta (`/auth/token` nav) | IEVIESTS / TESTĒTS |
| UIA/Input/Capture | Īsta implementācija | IEVIESTS / BLOĶĒTS Windows |
| Desktop Tool Bridge | Named Pipe | IEVIESTS / BLOĶĒTS Windows |
| WebView2 vadība | BrowserAutomationService | IEVIESTS / BLOĶĒTS Windows |
| Model inference probe | Īsta īsa atbilde | IEVIESTS / BLOĶĒTS bez servera |
| A–L pieņemšana | Skatīt TEST_REPORT | Daļēji TESTĒTS / daļēji BLOĶĒTS |
