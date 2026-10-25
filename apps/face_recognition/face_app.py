#!/usr/bin/env python3
"""
Main Brain OS — lokāla sejas atpazīšanas programma (bez mākoņa).

Funkcijas:
  - reāllaika kamera + sejas noteikšana (OpenCV Haar)
  - enroll: saglabā seju ar vārdu
  - atpazīšana: salīdzina ar enrollētajām sejām (kosinusa līdzība)

Vadība:
  E = enroll (ievadi vārdu terminālī)
  R = recognition on/off
  S = snapshot
  Q / Esc = iziet
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
ENROLL = DATA / "enrolled"
META = DATA / "people.json"
SIZE = (100, 100)
THRESHOLD = 0.55  # jo augstāks, jo stingrāka atbilstība (0..1)


def ensure_dirs() -> None:
    ENROLL.mkdir(parents=True, exist_ok=True)
    if not META.exists():
        META.write_text("{}", encoding="utf-8")


def load_meta() -> dict:
    ensure_dirs()
    try:
        return json.loads(META.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_meta(meta: dict) -> None:
    ensure_dirs()
    META.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def face_vector(gray_face: np.ndarray) -> np.ndarray:
    face = cv2.resize(gray_face, SIZE)
    face = cv2.equalizeHist(face)
    vec = face.astype(np.float32).ravel()
    n = np.linalg.norm(vec) + 1e-6
    return vec / n


def detect_faces(gray: np.ndarray, cascade: cv2.CascadeClassifier):
    return cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60))


def enroll_face(name: str, gray_face: np.ndarray) -> Path:
    ensure_dirs()
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in name.strip()) or "person"
    person_dir = ENROLL / safe
    person_dir.mkdir(parents=True, exist_ok=True)
    path = person_dir / f"{int(time.time() * 1000)}.png"
    face = cv2.resize(gray_face, SIZE)
    face = cv2.equalizeHist(face)
    cv2.imwrite(str(path), face)
    meta = load_meta()
    meta.setdefault(safe, {"name": name.strip(), "samples": []})
    meta[safe]["name"] = name.strip()
    meta[safe]["samples"].append(str(path.relative_to(DATA)))
    save_meta(meta)
    return path


def build_gallery() -> list[tuple[str, np.ndarray]]:
    """Atgriež [(display_name, vector), ...]."""
    gallery: list[tuple[str, np.ndarray]] = []
    meta = load_meta()
    for key, info in meta.items():
        name = info.get("name") or key
        for rel in info.get("samples") or []:
            p = DATA / rel
            if not p.exists():
                continue
            img = cv2.imread(str(p), cv2.IMREAD_GRAYSCALE)
            if img is None:
                continue
            gallery.append((name, face_vector(img)))
    # arī skenē mapes bez meta
    if ENROLL.exists():
        for person_dir in ENROLL.iterdir():
            if not person_dir.is_dir():
                continue
            name = (meta.get(person_dir.name) or {}).get("name") or person_dir.name
            for img_path in person_dir.glob("*.png"):
                img = cv2.imread(str(img_path), cv2.IMREAD_GRAYSCALE)
                if img is None:
                    continue
                gallery.append((name, face_vector(img)))
    return gallery


def recognize(gray_face: np.ndarray, gallery: list[tuple[str, np.ndarray]]) -> tuple[str, float]:
    if not gallery:
        return ("nezināms", 0.0)
    vec = face_vector(gray_face)
    best_name = "nezināms"
    best_score = -1.0
    for name, gvec in gallery:
        score = float(np.dot(vec, gvec))
        if score > best_score:
            best_score = score
            best_name = name
    if best_score < THRESHOLD:
        return ("nezināms", best_score)
    return (best_name, best_score)


def selftest() -> None:
    """Bez kameras — pārbauda enroll/recognize loģiku."""
    ensure_dirs()
    # sintētiska «seja»
    face_a = np.zeros(SIZE, dtype=np.uint8)
    cv2.rectangle(face_a, (20, 20), (80, 80), 200, -1)
    cv2.circle(face_a, (40, 45), 5, 40, -1)
    cv2.circle(face_a, (60, 45), 5, 40, -1)
    face_b = np.zeros(SIZE, dtype=np.uint8)
    cv2.rectangle(face_b, (10, 10), (90, 90), 180, -1)
    cv2.line(face_b, (30, 70), (70, 70), 30, 2)

    enroll_face("TestA", face_a)
    enroll_face("TestB", face_b)
    gallery = build_gallery()
    assert len(gallery) >= 2, gallery
    name, score = recognize(face_a, gallery)
    assert name == "TestA", (name, score)
    name2, score2 = recognize(face_b, gallery)
    assert name2 == "TestB", (name2, score2)
    print(f"SELFTEST OK  A={score:.3f} B={score2:.3f}  gallery={len(gallery)}")


def main() -> None:
    import sys

    if "--selftest" in sys.argv:
        selftest()
        return

    ensure_dirs()
    cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )
    if cascade.empty():
        raise SystemExit("Haar cascade nav ielādēts")

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        raise SystemExit(
            "Kamera #0 nav pieejama. Aizver citas programmas, kas lieto kameru, "
            "un pārbaudi Windows kameras atļaujas."
        )

    recognize_on = True
    gallery = build_gallery()
    print("=== Main Brain — Face Recognition ===")
    print(f"Enrollētās sejas: {len(gallery)} paraugi  |  data: {DATA}")
    print("E=enroll  R=recognition  S=snapshot  Q=iziet")

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = detect_faces(gray, cascade)

        for (x, y, w, h) in faces:
            crop = gray[y : y + h, x : x + w]
            label = "seja"
            color = (0, 255, 120)
            if recognize_on and crop.size:
                name, score = recognize(crop, gallery)
                if name != "nezināms":
                    label = f"{name} ({score:.2f})"
                    color = (0, 220, 255)
                else:
                    label = f"nezināms ({score:.2f})"
                    color = (0, 140, 255)
            cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
            cv2.putText(
                frame,
                label,
                (x, max(20, y - 10)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                color,
                2,
            )

        status = (
            f"Faces:{len(faces)}  Gallery:{len(gallery)}  "
            f"Rec:{'ON' if recognize_on else 'OFF'}  [E]nroll [R]ec [Q]uit"
        )
        cv2.putText(
            frame,
            status,
            (10, 28),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (0, 255, 160),
            2,
        )
        cv2.imshow("Main Brain — Face Recognition", frame)
        key = cv2.waitKey(1) & 0xFF

        if key in (ord("q"), ord("Q"), 27):
            break
        if key in (ord("r"), ord("R")):
            recognize_on = not recognize_on
            print("Recognition:", "ON" if recognize_on else "OFF")
        if key in (ord("s"), ord("S")):
            snap = DATA / f"snap_{int(time.time())}.jpg"
            cv2.imwrite(str(snap), frame)
            print("Snapshot:", snap)
        if key in (ord("e"), ord("E")):
            if not len(faces):
                print("Nav sejas enrollēšanai — stāvies pret kameru.")
                continue
            x, y, w, h = faces[0]
            crop = gray[y : y + h, x : x + w]
            print("Ieraksti vārdu terminālī un Enter:")
            try:
                name = input("Vārds: ").strip()
            except EOFError:
                name = ""
            if not name:
                print("Atcelts.")
                continue
            path = enroll_face(name, crop)
            gallery = build_gallery()
            print(f"Enroll OK: {name} -> {path}  (kopā {len(gallery)} paraugi)")

    cap.release()
    cv2.destroyAllWindows()
    print("Beigas.")


if __name__ == "__main__":
    main()
