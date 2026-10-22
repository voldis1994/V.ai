# Uzstādīšana (latviešu)

## Prasības

- Windows 10/11 x64 (prioritāri Windows 11)
- .NET 8 LTS SDK
- Python 3.12+
- Microsoft Edge WebView2 Runtime
- (Neobligāti) llama.cpp `llama-server` vai Ollama
- (Neobligāti) GGUF modeļi

## Ātrā uzstādīšana (ieteicams)

Veiciet dubultklikšķi uz projekta saknes faila:

```text
START_MAINBRAIN.bat
```

Tas automātiski (ar jūsu apstiprinājumu):
1. lejupielādē/instalē **.NET 8 SDK** (ja nav),
2. lejupielādē/instalē **Python 3.12+** (ja nav),
3. lejupielādē/instalē **WebView2 Runtime** (ja nav),
4. izveido `.venv` un instalē Python atkarības,
5. sagatavo `%LOCALAPPDATA%\MainBrainOS`,
6. pēc izvēles palaiž izstrādes vidi.

**Piezīme:** GGUF AI modeļi **netiek** lejupielādēti automātiski (vairāki GB). Tos ievietojiet `%LOCALAPPDATA%\MainBrainOS\models` un palaidiet `llama-server` vai Ollama.

Alternatīvi PowerShell:

```powershell
cd <projekta-sakne>
./scripts/bootstrap_windows.ps1
# vai
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
