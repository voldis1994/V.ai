# Instalators

Ieteicamā pieeja Windows laidienam:

1. Palaist `scripts/build_release.ps1` → `release/win-x64/`.
2. Iepakot mapi ar `MainBrain.exe`, `backend/`, `manifest.json`, `SHA256SUMS.txt`.
3. Pēc izvēles izmantot WiX / MSIX / zip pārnēsājamo versiju.

Instalators **nedrīkst** dzēst `%LOCALAPPDATA%\MainBrainOS` projektus atinstalēšanas laikā.
