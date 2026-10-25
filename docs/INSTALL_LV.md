# Uzstādīšana (latviešu)

## Viens fails — pilna uzstādīšana + EXE

Lejupielādējiet **jaunāko** main ZIP (ne veco mapi):  
https://github.com/voldis1994/V.ai/archive/refs/heads/main.zip

Izpakojiet un palaidiet **`START_MAINBRAIN.bat`**.

Tas uzstāda atkarības, llama-server, GGUF, uzbūvē **`release\win-x64\MainBrain.exe`**
un izveido darbvirsmas īsceļu **Main Brain OS** ikdienas lietošanai.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_full.ps1
```

## Prasības

- Windows 10/11 x64 (prioritāri Windows 11)
- .NET 8 LTS SDK
- Python 3.12+
- Microsoft Edge WebView2 Runtime
- **llama.cpp `llama-server`** — **primārā** lokālā AI (bootstrap to uzstāda)
- GGUF modeļi — ieteicams lejupielādēt (bat opcijas 4–6)
- Ollama — **NAV** obligāta; tikai rezerve ar `MAINBRAIN_OLLAMA_ENABLED=true`

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

### GGUF AI modeļi

Tos **var** lejupielādēt ar `scripts/download_models.ps1` vai **`UPGRADE_MODEL.bat`**.

| Profils | Modelis | Piezīme |
|---------|---------|---------|
| `light` | Qwen 1.5B | tikai smoke — **nesaprot** uzdevumus |
| `standard` | Qwen 3B | minimums «izskaidro / iemācies / uztaisi» |
| `capable` | Qwen 7B | ieteicams (~10 GB, 16 GB RAM+) |

`light` / 1.5B **nav** derīgs reālai programmu veidošanai. Pēc 1.5B instalācijas palaid `UPGRADE_MODEL.bat`.

Tie **nav** noklusējuma klusā lejupielādē, jo:
- aizņem ~2–10 GB,
- ir licences nosacījumi,
- atkarīgi no RAM/VRAM,
- specifikācija aizliedz klusu gigabaitu lejupielādi bez piekrišanas.

Modeļu mape: `%LOCALAPPDATA%\MainBrainOS\models`  
Katalogs: `models/manifest.json`

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
