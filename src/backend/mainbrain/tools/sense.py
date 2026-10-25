from __future__ import annotations

import base64
import os
import subprocess
import sys
import wave
from pathlib import Path
from typing import Any


def _captures_dir() -> Path:
    local = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_DATA_HOME")
    if local:
        root = Path(local) / "MainBrainOS" / "captures"
    else:
        root = Path.home() / ".local" / "share" / "MainBrainOS" / "captures"
    root.mkdir(parents=True, exist_ok=True)
    return root


def opencv_available() -> bool:
    try:
        import cv2  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


def camera_capture(*, camera_index: int = 0, filename: str | None = None) -> dict[str, Any]:
    """Uztver kadru no lokālās kameras (OpenCV). Bez kameras — skaidra kļūda."""
    if not opencv_available():
        return {
            "ok": False,
            "error": (
                "OpenCV nav instalēts. Palaid: pip install opencv-python-headless "
                "vai scripts\\install_sense.ps1"
            ),
            "hint": "sense",
        }
    import cv2

    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        return {
            "ok": False,
            "error": f"Kamera #{camera_index} nav pieejama (aizņemta vai nav atļaujas)",
            "camera_index": camera_index,
        }
    try:
        ok, frame = cap.read()
        if not ok or frame is None:
            return {"ok": False, "error": "Neizdevās nolasīt kadru no kameras"}
        out = _captures_dir() / (filename or f"camera_{camera_index}.jpg")
        cv2.imwrite(str(out), frame)
        h, w = frame.shape[:2]
        return {
            "ok": True,
            "performed": True,
            "path": str(out),
            "width": int(w),
            "height": int(h),
            "camera_index": camera_index,
            "opencv": True,
        }
    finally:
        cap.release()


def face_detect(image_path: str | None = None, *, camera_index: int = 0) -> dict[str, Any]:
    """Nosaka sejas lokālā attēlā / kameras kadrā (Haar cascade — bez mākoņa)."""
    if not opencv_available():
        return {
            "ok": False,
            "error": "OpenCV nav instalēts — sejas noteikšana nepieejama",
            "faces": [],
        }
    import cv2

    path = image_path
    captured = None
    if not path:
        captured = camera_capture(camera_index=camera_index)
        if not captured.get("ok"):
            return {**captured, "faces": []}
        path = captured["path"]

    img = cv2.imread(str(path))
    if img is None:
        return {"ok": False, "error": f"Nevar nolasīt attēlu: {path}", "faces": []}

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    cascade = cv2.CascadeClassifier(cascade_path)
    faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(40, 40))
    boxes = [{"x": int(x), "y": int(y), "w": int(w), "h": int(h)} for (x, y, w, h) in faces]

    # Annotēts attēls
    annotated = img.copy()
    for box in boxes:
        cv2.rectangle(
            annotated,
            (box["x"], box["y"]),
            (box["x"] + box["w"], box["y"] + box["h"]),
            (0, 255, 120),
            2,
        )
    out = _captures_dir() / "faces_annotated.jpg"
    cv2.imwrite(str(out), annotated)

    return {
        "ok": True,
        "performed": True,
        "path": path,
        "annotated_path": str(out),
        "face_count": len(boxes),
        "faces": boxes,
        "summary": (
            f"Atrastas {len(boxes)} sejas."
            if boxes
            else "Sejas nav atrastas (vai apgaismojums/leņķis neatbilst)."
        ),
    }


def describe_image_basic(image_path: str, face_info: dict[str, Any] | None = None) -> dict[str, Any]:
    """Pamata apraksts bez vision LLM (izmērs + sejas)."""
    info: dict[str, Any] = {"ok": True, "path": image_path, "method": "basic"}
    if opencv_available():
        import cv2

        img = cv2.imread(image_path)
        if img is not None:
            h, w = img.shape[:2]
            mean = img.mean(axis=(0, 1))
            info["width"] = int(w)
            info["height"] = int(h)
            info["brightness"] = float(mean.mean())
            info["notes"] = (
                "Tumšs kadrs" if info["brightness"] < 50 else
                "Gaišs kadrs" if info["brightness"] > 180 else
                "Normāls apgaismojums"
            )
    if face_info and face_info.get("ok"):
        info["face_count"] = face_info.get("face_count", 0)
        info["faces"] = face_info.get("faces", [])
        info["annotated_path"] = face_info.get("annotated_path")
        info["description"] = (
            f"Kameras kadrs {info.get('width', '?')}x{info.get('height', '?')}. "
            f"{face_info.get('summary', '')} "
            f"{info.get('notes', '')}."
        )
    else:
        info["description"] = (
            f"Saglabāts kadrs: {image_path}. "
            f"{info.get('notes', '')}. "
            "Pilnai ainas saprašanai vajag vision GGUF (moondream) + UPGRADE."
        )
    return info


def image_to_data_url(path: str, *, max_side: int = 768) -> str | None:
    if not opencv_available():
        try:
            raw = Path(path).read_bytes()
            b64 = base64.b64encode(raw).decode("ascii")
            return f"data:image/jpeg;base64,{b64}"
        except OSError:
            return None
    import cv2

    img = cv2.imread(path)
    if img is None:
        return None
    h, w = img.shape[:2]
    scale = min(1.0, max_side / max(h, w))
    if scale < 1.0:
        img = cv2.resize(img, (int(w * scale), int(h * scale)))
    ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
    if not ok:
        return None
    b64 = base64.b64encode(buf.tobytes()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


def speak_text(text: str, *, lang: str = "lv") -> dict[str, Any]:
    """Lokāla runāšana: Windows SAPI, citādi espeak/spd-say."""
    t = (text or "").strip()
    if not t:
        return {"ok": False, "error": "Tukšs teksts"}
    # Saīsina ļoti garas atbildes
    if len(t) > 800:
        t = t[:800] + "…"
    # Viena rinda runāšanai
    t = " ".join(t.split())

    if sys.platform.startswith("win"):
        # -EncodedCommand + Base64 teksts — latviešu burti / pēdiņas nesalūzt
        payload_b64 = base64.b64encode(t.encode("utf-8")).decode("ascii")
        ps = (
            "Add-Type -AssemblyName System.Speech; "
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            "$s.Rate = 0; "
            f"$bytes = [Convert]::FromBase64String('{payload_b64}'); "
            "$msg = [System.Text.Encoding]::UTF8.GetString($bytes); "
            "$s.Speak($msg)"
        )
        encoded = base64.b64encode(ps.encode("utf-16le")).decode("ascii")
        try:
            completed = subprocess.run(
                ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-EncodedCommand", encoded],
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            return {
                "ok": completed.returncode == 0,
                "performed": completed.returncode == 0,
                "engine": "System.Speech",
                "stderr": (completed.stderr or "")[-400:],
            }
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc), "engine": "System.Speech"}

    for cmd in (
        ["espeak", "-v", "lv" if lang.startswith("lv") else "en", t],
        ["spd-say", t],
        ["say", t],
    ):
        try:
            completed = subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=False)
            if completed.returncode == 0:
                return {"ok": True, "performed": True, "engine": cmd[0]}
        except FileNotFoundError:
            continue
        except Exception:  # noqa: BLE001
            continue
    return {
        "ok": False,
        "error": "Nav TTS dzinēja (Windows SAPI / espeak). Audio atbilde nav iespējama.",
    }


def face_recognition_app_source() -> str:
    """Pilna lokālā sejas atpazīšanas programma (enroll + recognize)."""
    # Preferē repo apps/face_recognition/face_app.py
    # sense.py → tools → mainbrain → backend → src → repo root
    repo = Path(__file__).resolve().parents[4]
    candidates = [
        repo / "apps" / "face_recognition" / "face_app.py",
        Path.cwd() / "apps" / "face_recognition" / "face_app.py",
    ]
    for path in candidates:
        if path.is_file():
            return path.read_text(encoding="utf-8")
    return (
        'raise SystemExit("Trūkst apps/face_recognition/face_app.py — git pull")\n'
    )


def copy_face_recognition_app(dest_dir: str | Path) -> dict[str, Any]:
    """Nokopē gatavu face recognition app uz darba mapi."""
    import shutil

    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    src_root = None
    repo = Path(__file__).resolve().parents[4]
    for cand in (
        repo / "apps" / "face_recognition",
        Path.cwd() / "apps" / "face_recognition",
    ):
        if cand.is_dir() and (cand / "face_app.py").is_file():
            src_root = cand
            break
    if src_root is None:
        # fallback — tikai galvenais skripts
        app = dest / "face_app.py"
        app.write_text(face_recognition_app_source(), encoding="utf-8")
        (dest / "requirements.txt").write_text("opencv-python>=4.8\nnumpy>=1.26\n", encoding="utf-8")
        return {"ok": True, "path": str(dest), "files": [str(app)], "mode": "inline"}

    copied: list[str] = []
    for name in ("face_app.py", "requirements.txt", "README_LV.md", "RUN_FACE_APP.bat"):
        src = src_root / name
        if src.is_file():
            target = dest / name
            shutil.copy2(src, target)
            copied.append(str(target))
    return {"ok": True, "path": str(dest), "files": copied, "mode": "copy"}
