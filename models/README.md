# Lokālie modeļi

Šajā mapē (vai `%LOCALAPPDATA%\MainBrainOS\models`) ievietojiet GGUF modeļus.

Ieteicamās lomas pēc faila nosaukuma:
- `*code*` / `*coder*` → coding
- `*vision*` / `*vl*` → vision
- `*embed*` → embedding
- pārējie → reasoning

**Neregistrējiet Git repozitorijā** nelicencētus vai lielus modeļu bināros failus.

Palaišana:
1. Palaidiet `llama-server` ar OpenAI saderīgu API uz `http://127.0.0.1:8080`.
2. Vai izmantojiet lokālo Ollama kā rezerves adapteri.
3. Main Brain OS Modeļu pārvaldnieks noskenēs mapes un parādīs veselības statusu.

Bez modeļa sistēma joprojām darbojas ar determinētiem aģentu izpildes ceļiem; LLM papildinājums tiek atzīmēts kā nepieejams.
