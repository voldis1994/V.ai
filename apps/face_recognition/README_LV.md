# Sejas atpazīšana — Main Brain OS

Lokāla programma: kamera → sejas noteikšana → enroll ar vārdu → atpazīšana.

## Uzstādīšana (Windows)

```bat
cd apps\face_recognition
python -m pip install -r requirements.txt
RUN_FACE_APP.bat
```

vai no repo saknes:

```bat
START_FACE_RECOGNITION.bat
```

## Vadība

| Taustiņš | Darbība |
|----------|---------|
| **E** | Enroll — ieraksti vārdu terminālī |
| **R** | Recognition ON/OFF |
| **S** | Snapshot |
| **Q** / Esc | Iziet |

Dati: `apps/face_recognition/data/enrolled/` + `people.json`

## Piezīmes

- Darbojas **bez interneta / mākoņa**
- Vairāki paraugi vienam cilvēkam = labāka precizitāte (E vairākas reizes)
- Labāks apgaismojums un skatiens pret kameru
