# Uzstādīšana (latviešu)

## Prasības

- Windows 10/11 x64 (prioritāri Windows 11)
- .NET 8 LTS SDK
- Python 3.12+
- Microsoft Edge WebView2 Runtime
- (Neobligāti) llama.cpp `llama-server` vai Ollama
- (Neobligāti) GGUF modeļi

## Soļi

```powershell
cd MainBrainOS
./scripts/setup_windows.ps1
./scripts/start_dev.ps1
```

Laidiena būvēšana:

```powershell
./scripts/build_release.ps1
# rezultāts: release/win-x64/MainBrain.exe
```

## Datu mape

`%LOCALAPPDATA%\MainBrainOS` — datubāze, žurnāli, modeļi, tokeni. Atinstalēšana **nedzēš** lietotāja projektus.

## Bezsaistes režīms

Pēc modeļu un atkarību uzstādīšanas lokālie uzdevumi (faili, kods, testi, inference) strādā bez interneta. Tīmekļa izpētei internets nepieciešams.

## Linux/macOS izstrāde

Backend un Python testus var palaist jebkurā OS:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest -q tests/python
```

WPF `MainBrain.exe` būvēšana un UI Automation testi šajās OS ir **BLOĶĒTI**.
