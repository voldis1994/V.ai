# Main Brain OS

Lokāls Windows AI vadības centrs: **MainBrain.exe**, Main Brain orķestrators, **50 specializēti aģenti**, Focus/Multi-Window režīmi, WebView2, UI Automation un lokāla inference.

## Ātrā sākšana (Windows) — VIENS fails

1. Lejupielādējiet **jaunāko** `main`:  
   https://github.com/voldis1994/V.ai/archive/refs/heads/main.zip  
   (vai `git clone https://github.com/voldis1994/V.ai.git`)
2. Izpakojiet un veiciet **dubultklikšķi**:

```text
START_MAINBRAIN.bat
```

Tas **vienā gājienā**:
- uzstāda .NET 8, Python, WebView2
- uzstāda **llama-server** + lejupielādē GGUF (~2 GB)
- **uzbūvē `MainBrain.exe`**
- izveido darbvirsmas īsceļu **Main Brain OS**
- palaiž programmu

### Ikdienas lietošana
Dubultklikšķis uz darbvirsmas **Main Brain OS** (vai `release\win-x64\MainBrain.exe`).  
Ollama **nav** vajadzīga.

## Backend testi (jebkura OS)

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest -q tests/python
```

## Dokumentācija

- [Arhitektūra](docs/ARCHITECTURE.md)
- [Uzstādīšana](docs/INSTALL_LV.md)
- [Lietotāja rokasgrāmata](docs/USER_GUIDE_LV.md)
- [Drošība](docs/SECURITY.md)
- [Prasību kontrolsaraksts](docs/REQUIREMENTS_CHECKLIST.md)
- [Būvēšanas statuss](docs/BUILD_STATUS.md)
- [Testu pārskats](docs/TEST_REPORT.md)

## Licence

MIT (projekta kods). Trešo pušu komponentēm — skatīt to licences. Modeļus Git nereģistrē.
