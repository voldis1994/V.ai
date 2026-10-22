# Lietotāja rokasgrāmata — Main Brain OS

## Galvenais logs

- **Augšējā josla:** statuss, modelis, resursi, STOP
- **Kreisā puse:** 50 aģenti 10 nodaļās, darba mape
- **Centrs:** Focus / Multi-Window darba zona, WebView2, redaktors, paneļi
- **Labā puse:** inspektors (aģents, rīki, pierādījumi)
- **Apakša:** saruna latviešu valodā, terminālis, apstiprinājumi

## Kā palaist uzdevumu

1. Norādiet projekta darba mapi.
2. Ievadiet mērķi, piemēram: *Izveido Python programmu, kas nolasa CSV...*
3. Main Brain izveido plānu, izvēlas aģentus, izpilda paralēli un pārbauda rezultātu.
4. Rezultātus skatiet artefaktos, žurnālā un atskaitē.

## Apstiprinājumi

Riskantām darbībām parādās dialogs ar precīzu ceļu/komandu:
- `Atļaut vienreiz`
- `Atļaut šim ierobežotajam uzdevumam`
- `Noraidīt`

## STOP / Pauze / Turpināt

- **STOP** — liedz jaunas darbības un aptur darba bērnprocesus.
- **Pauze/Turpināt** — aptur/atsāk orķestrāciju.

## Modeļi

Atveriet Modeļu pārvaldnieku, ievietojiet GGUF failus un palaidiet `llama-server`. Ja modeļa nav, sistēma to godīgi norāda, bet turpina darboties.
