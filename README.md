# Main Brain OS

Lokāls Windows AI vadības centrs: **MainBrain.exe**, Main Brain orķestrators, **50 specializēti aģenti**, Focus/Multi-Window režīmi, WebView2, UI Automation un lokāla inference.

## Ātrā sākšana (Windows)

Veiciet dubultklikšķi:

```text
START_MAINBRAIN.bat
```

Tas lejupielādē un uzstāda .NET 8, Python 3.12+, WebView2 un projekta atkarības (GGUF modeļus — manuāli).

```powershell
./scripts/bootstrap_windows.ps1
# vai
./scripts/setup_windows.ps1
./scripts/start_dev.ps1
```

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
