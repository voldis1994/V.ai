# Drošība

## Principi

1. Politika darbojas **ārpus LLM** (`PolicyEngine`).
2. Nav automātiskas privileģiju paaugstināšanas / UAC apiešanas.
3. Nav slēptas taustiņu reģistrēšanas vai slēptas ekrāna uztveršanas.
4. Paroļu lauki netiek lasīti.
5. Neuzticami `.exe` un darbības ārpus darba mapes prasa apstiprinājumu.
6. Tīmekļa saturs = dati, nevis komandas.
7. Lokālais API tikai uz `127.0.0.1` ar Bearer token.
8. Žurnālos sensitīvie lauki tiek aizklāti.

## STOP

`POST /control/stop` iestata `emergency_stop`, bloķējot rīku izpildi.

## Licences

Skatīt trešo pušu pakotņu licences `pyproject.toml` un NuGet atsaucēs. Modeļu licences jāpārbauda pirms importēšanas.
