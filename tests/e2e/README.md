# E2E testi (Windows)

Šie scenāriji jāizpilda Windows 10/11 vidē ar uzbūvētu `MainBrain.exe`.

## E1 — WebView2 iegults
1. Palaist MainBrain.exe
2. Centra panelī atvērt `https://example.com`
3. Pārliecināties, ka cilne paliek lietotnes iekšienē (nav ārēja Edge loga)

## E2 — Notepad automatizācija
1. Darba mape = testa mape
2. Izsaukt ApplicationLauncher + UIAutomationOperator
3. Ievadīt tekstu, saglabāt failu darba mapē
4. Ja capture atbalstīts — rādās `Dzīvais attēls`, citādi `Nav pieejams`

## E3 — Focus / Multi pārslēgšana
1. Palaist garu uzdevumu
2. Pārslēgt režīmus — uzdevums nedrīkst apstāties
3. Pārstartēt lietotni — layout ielādējas no `/layout/default`
