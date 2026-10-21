# Prasību kontrolsaraksts

Statusi: `IEVIESTS` / `TESTĒTS` / `BLOĶĒTS` / `NESTRĀDĀ`

| ID | Prasība | Statuss |
|----|---------|---------|
| 0.1 | MainBrain.exe WPF galvenais logs LV UI | IEVIESTS (būvēšana Windows) / BLOĶĒTS (Linux palaišana) |
| 0.2 | Pilnībā lokāli, bez maksas API | IEVIESTS |
| 0.3 | Tieši 50 aģentu konfigurācijas | IEVIESTS / TESTĒTS |
| 0.4 | Main Brain DAG + paralēlisms + pārbaude | IEVIESTS / TESTĒTS |
| 0.5 | Focus Mode | IEVIESTS (UI) / BLOĶĒTS (Windows GUI tests) |
| 0.6 | Multi-Window Mode | IEVIESTS (UI) / BLOĶĒTS (Windows GUI tests) |
| 0.7 | Koda izveide/testēšana/programmu vadība | IEVIESTS (kods/testi) / BLOĶĒTS (UIA Windows) |
| 0.8 | Persistēšana starp palaišanām | IEVIESTS / TESTĒTS (layout/memory) |
| 0.9 | Politika ārpus LLM + STOP | IEVIESTS / TESTĒTS |
| 0.10 | Būvēšanas/pieņemšanas skripti | IEVIESTS |
| A | 50 aģentu ID/līgumi/GUI | IEVIESTS / TESTĒTS (API); GUI BLOĶĒTS Linux |
| B | Start/stop + veselība | IEVIESTS / TESTĒTS |
| C | Abi vizuālie režīmi | IEVIESTS / BLOĶĒTS GUI |
| D | WebView2 iegults | IEVIESTS / BLOĶĒTS Linux |
| E | Notepad + UIA + capture | IEVIESTS (kods) / BLOĶĒTS Linux |
| F | CSV Python atskaite | IEVIESTS / TESTĒTS |
| G | Paralēli uzdevumi + failu slēdzenes | IEVIESTS / TESTĒTS |
| H | Apstiprinājumi + STOP | IEVIESTS / TESTĒTS |
| I | Restart persistēšana | IEVIESTS / TESTĒTS (layout/events) |
| J | Bezsaistes inference | IEVIESTS (adapteri) / BLOĶĒTS bez modeļa |
| K | Nepieejamu funkciju godīgs statuss | IEVIESTS / TESTĒTS |
| L | Kļūdu/injekciju robežas | IEVIESTS / TESTĒTS |
| M | Laidiena artefakts | IEVIESTS (skripts) / BLOĶĒTS Linux WPF publish |
