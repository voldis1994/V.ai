# Lokālie modeļi — llama.cpp (primāri)

Main Brain OS **primārā** AI inference ir **llama.cpp `llama-server`** ar GGUF failiem.

**Ollama nav bāze** — tā ir tikai neobligāta rezerve (`MAINBRAIN_OLLAMA_ENABLED=true`).

## Svarīgi: 1.5B nespēj saprast uzdevumus

`Qwen2.5-1.5B` (`light`) der tikai smoke testam.  
Lai sistēma saprastu **sameklē / iemācies / izskaidro / uztaisi programmu**, vajag:

| Profils | Modelis | Diska | Kad |
|---------|---------|-------|-----|
| `light` | Qwen 1.5B | ~2 GB | tikai pārbaude |
| `standard` | Qwen 3B | ~4 GB | minimums sapratnei |
| `capable` | Qwen 7B | ~10 GB | ieteicams (16 GB RAM+) |

Windows:

```bat
UPGRADE_MODEL.bat
```

vai:

```powershell
./scripts/download_models.ps1 -Profile capable -AcceptDownloads -Force
```

Pēc tam `FIX_BACKEND.bat` / restartē MainBrain — headerī jābūt `3B` vai `7B`, ne `1.5B`.

## Windows uzstādīšana

```bat
START_MAINBRAIN.bat
```

Manuāli:

```powershell
./scripts/install_llama_server.ps1
./scripts/download_models.ps1 -Profile standard
./scripts/start_llama_server.ps1
```

Modeļu mape: `%LOCALAPPDATA%\MainBrainOS\models`  
Serveris: `%LOCALAPPDATA%\MainBrainOS\llama\llama-server.exe`

## Lomas pēc faila nosaukuma

- `*coder*` / `*code*` → coding  
- `*vision*` / `moondream*` → vision  
- `*embed*` → embedding  
- pārējie → reasoning  

## Ollama (rezerve)

```text
set MAINBRAIN_OLLAMA_ENABLED=true
```
