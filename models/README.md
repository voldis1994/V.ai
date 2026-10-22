# Lokālie modeļi (GGUF)

Ieteicamā mape Windows:

`%LOCALAPPDATA%\MainBrainOS\models`

## Automātiska lejupielāde (ar apstiprinājumu)

```bat
START_MAINBRAIN.bat
```

Izvēlieties:
- **[4]** rīki + GGUF **light** (~2 GB: reasoning, coding, embedding)
- **[5]** rīki + GGUF **standard** (~6–10 GB: + vision)
- **[6]** tikai GGUF light

vai PowerShell:

```powershell
./scripts/download_models.ps1 -Profile light
./scripts/download_models.ps1 -Profile standard
```

Katalogs: `models/manifest.json` (URL, lomas, licences, aptuvenie izmēri).

## Kāpēc tas nav “klusuma” noklusējums?

1. **Izmērs** — vairāki GB; lēns internets / maz diska.
2. **Licences** — jāpiekrīt Hugging Face / modeļa licencei.
3. **Aparatūra** — nekatram datoram der lieli vision/coding modeļi.
4. **Specifikācija** — aizliegts klusām lejupielādēt gigabaitus bez lietotāja piekrišanas.

Ar skaidru izvēli (opcijas 4–6) lejupielāde **ir atļauta un ieviesta**.

## Lomu noteikšana pēc faila nosaukuma

- `*code*` / `*coder*` → coding  
- `*vision*` / `*vl*` / `moondream*` → vision  
- `*embed*` → embedding  
- pārējie → reasoning  

Pēc lejupielādes tiek rakstīts arī `roles.json`.

## Inference

1. Palaidiet `llama-server` ar OpenAI saderīgu API uz `http://127.0.0.1:8080`, **vai**
2. Izmantojiet lokālo Ollama.

**Neregistrējiet Git** lielus `.gguf` failus.
