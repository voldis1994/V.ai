# Lokālie modeļi — llama.cpp (primāri)

Main Brain OS **primārā** AI inference ir **llama.cpp `llama-server`** ar GGUF failiem.

**Ollama nav bāze** — tā ir tikai neobligāta rezerve (`MAINBRAIN_OLLAMA_ENABLED=true`).

## Windows uzstādīšana

```bat
START_MAINBRAIN.bat
```

Ieteicams:
1. Bootstrap uzstāda **llama-server**
2. Opcija **[4]/[5]** lejupielādē GGUF
3. `start_llama_server.ps1` / BackendHost palaiž `http://127.0.0.1:8080/v1`

Manuāli:

```powershell
./scripts/install_llama_server.ps1
./scripts/download_models.ps1 -Profile light
./scripts/start_llama_server.ps1
```

Modeļu mape: `%LOCALAPPDATA%\MainBrainOS\models`  
Serveris: `%LOCALAPPDATA%\MainBrainOS\llama\llama-server.exe`

## Kāpēc GGUF + llama-server?

Specifikācija: lokāla OpenAI saderīga saskarne caur **llama-server**, ne mākonis un ne Ollama kā noklusējums.

## Lomas pēc faila nosaukuma

- `*coder*` / `*code*` → coding  
- `*vision*` / `moondream*` → vision  
- `*embed*` → embedding  
- pārējie → reasoning  

## Ollama (rezerve)

Tikai ja apzināti:

```text
set MAINBRAIN_OLLAMA_ENABLED=true
```

Bez šī karoga Ollama netiek izmantota.
