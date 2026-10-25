# RELEASE_VERIFICATION

## Mērķis

Pārbaudīt, ka `release/win-x64/MainBrain.exe` startē **ārpus** Git repozitorija ar komplektā esošo backend.

## Soli

1. `./scripts/build_release.ps1`
2. Nokopēt `release/win-x64` uz citu mapi, piem. `C:\Temp\MainBrainRun`
3. Palaist `MainBrain.exe`
4. Pārbaudīt:
   - Backend health (statusa josla “Lokāli aktīvs”)
   - 50 aģenti kreisajā panelī
   - Focus/Multi pārslēgšana maina izkārtojumu
   - STOP poga
   - CSV uzdevums latviešu valodā
5. (Neobligāti) Palaist `llama-server`, ievietot GGUF, pārbaudīt modeļa statusu ar īstu inferenci

## Šīs sesijas rezultāts

| Solis | Statuss |
|-------|---------|
| Laidiena skripts atjaunināts | IEVIESTS |
| Windows publish/palaišana | BLOĶĒTS (Linux) |

## Diagnostika

- Backend nestartē: pārbaudīt `runtime-venv` / Python PATH, `%LOCALAPPDATA%\MainBrainOS\logs`
- WebView2: instalēt Evergreen Runtime
- Tilts: `MAINBRAIN_API_TOKEN` jābūt kopīgam starp exe un Python
