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


# Microsoft latviešu neirālās balsis (Edge Read Aloud — bez Azure atslēgas)
LV_VOICE_FEMALE = "lv-LV-EveritaNeural"
LV_VOICE_MALE = "lv-LV-NilsNeural"
DEFAULT_LV_VOICE = LV_VOICE_FEMALE


def _lv_phonetic_for_en_voice(text: str) -> str:
    """Ja nav latviešu balss — aptuvena fonētika angļu SAPI balsij."""
    repl = (
        ("č", "ch"), ("Č", "Ch"),
        ("š", "sh"), ("Š", "Sh"),
        ("ž", "zh"), ("Ž", "Zh"),
        ("ā", "aa"), ("Ā", "Aa"),
        ("ē", "ee"), ("Ē", "Ee"),
        ("ī", "ii"), ("Ī", "Ii"),
        ("ū", "uu"), ("Ū", "Uu"),
        ("ģ", "gy"), ("Ģ", "Gy"),
        ("ķ", "ky"), ("Ķ", "Ky"),
        ("ļ", "ly"), ("Ļ", "Ly"),
        ("ņ", "ny"), ("Ņ", "Ny"),
    )
    out = text
    for a, b in repl:
        out = out.replace(a, b)
    return out


def _speak_edge_tts(text: str, *, voice: str = DEFAULT_LV_VOICE) -> dict[str, Any]:
    """Īsta latviešu balss (Everita/Nils) caur Microsoft Edge TTS — uzreiz, bez SAPI instalācijas."""
    try:
        import asyncio
        import tempfile

        import edge_tts
    except ImportError:
        return {
            "ok": False,
            "error": "edge-tts nav instalēts — palaid scripts\\install_latvian_voice.ps1",
            "engine": "edge-tts",
            "hint": "install_latvian_voice",
        }

    async def _run(chosen: str) -> Path:
        out = Path(tempfile.gettempdir()) / "mainbrain_tts_lv.mp3"
        communicate = edge_tts.Communicate(text, chosen)
        # stream+write — stabilāks nekā save() dažos tīklos
        audio = bytearray()
        async for message in communicate.stream():
            if message["type"] == "audio":
                audio.extend(message["data"])
        if not audio:
            raise RuntimeError("NoAudioReceived")
        out.write_bytes(bytes(audio))
        return out

    def _synth(chosen: str) -> Path:
        try:
            asyncio.get_running_loop()
            nested = True
        except RuntimeError:
            nested = False
        if nested:
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(lambda: asyncio.run(_run(chosen))).result(timeout=90)
        return asyncio.run(_run(chosen))

    voices = [voice]
    if voice == LV_VOICE_FEMALE:
        voices.append(LV_VOICE_MALE)
    elif voice == LV_VOICE_MALE:
        voices.append(LV_VOICE_FEMALE)

    last_exc: Exception | None = None
    path: Path | None = None
    used_voice = voice
    for v in voices:
        try:
            path = _synth(v)
            used_voice = v
            break
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            continue
    if path is None:
        return {
            "ok": False,
            "error": str(last_exc) if last_exc else "edge-tts failed",
            "engine": "edge-tts",
            "voice": voice,
        }
    voice = used_voice

    if not path.is_file() or path.stat().st_size < 32:
        return {"ok": False, "error": "edge-tts neatgrieza audio", "engine": "edge-tts", "voice": voice}

    played = _play_audio_file(path)
    return {
        "ok": bool(played.get("ok")),
        "performed": bool(played.get("ok")),
        "engine": "edge-tts",
        "voice": voice,
        "path": str(path),
        "play": played,
    }


def _play_audio_file(path: Path) -> dict[str, Any]:
    """Atskaņo mp3/wav Windows / Linux."""
    p = str(path)
    if sys.platform.startswith("win"):
        # Windows Media Player COM — spēlē mp3 bez papildu pip
        ps = (
            f"$p = '{p.replace(chr(39), chr(39)+chr(39))}'; "
            "$player = New-Object -ComObject WMPlayer.OCX; "
            "$media = $player.newMedia($p); "
            "$player.currentMedia = $media; "
            "$player.controls.play(); "
            "while ($player.playState -eq 3) { Start-Sleep -Milliseconds 200 }; "
            "$player.close()"
        )
        try:
            completed = subprocess.run(
                ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps],
                capture_output=True,
                text=True,
                timeout=180,
                check=False,
            )
            if completed.returncode == 0:
                return {"ok": True, "via": "WMPlayer"}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}
        # Fallback: start file (atver ārējo atskaņotāju)
        try:
            os.startfile(p)  # type: ignore[attr-defined]
            return {"ok": True, "via": "startfile"}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}

    for cmd in (
        ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", p],
        ["mpv", "--no-video", p],
        ["paplay", p],
        ["afplay", p],
    ):
        try:
            completed = subprocess.run(cmd, capture_output=True, text=True, timeout=180, check=False)
            if completed.returncode == 0:
                return {"ok": True, "via": cmd[0]}
        except FileNotFoundError:
            continue
        except Exception:  # noqa: BLE001
            continue
    return {"ok": False, "error": "Nav audio atskaņotāja"}


def _speak_sapi_windows(text: str, *, lang: str = "lv") -> dict[str, Any]:
    phonetic = _lv_phonetic_for_en_voice(text) if lang.startswith("lv") else text
    raw_b64 = base64.b64encode(text.encode("utf-8")).decode("ascii")
    pho_b64 = base64.b64encode(phonetic.encode("utf-8")).decode("ascii")
    ps = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        "$s.Rate = -1; "
        "$voices = @($s.GetInstalledVoices() | ForEach-Object { $_.VoiceInfo }); "
        "$lv = $voices | Where-Object { "
        "  $_.Culture.Name -like 'lv*' -or $_.Name -match 'Latvi' "
        "} | Select-Object -First 1; "
        f"$raw = [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{raw_b64}')); "
        f"$pho = [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{pho_b64}')); "
        "if ($lv) { $s.SelectVoice($lv.Name); $s.Speak($raw) } "
        "else { "
        "  $en = $voices | Where-Object { $_.Culture.Name -like 'en*' } | Select-Object -First 1; "
        "  if ($en) { $s.SelectVoice($en.Name) }; "
        "  $s.Speak($pho) "
        "}"
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


def speak_text(text: str, *, lang: str = "lv", voice: str | None = None) -> dict[str, Any]:
    """Runā: 1) latviešu Everita/Nils (edge-tts) 2) lokālā SAPI 3) espeak."""
    t = (text or "").strip()
    if not t:
        return {"ok": False, "error": "Tukšs teksts"}
    if len(t) > 800:
        t = t[:800] + "…"
    t = " ".join(t.split())

    # 1) Īsta latviešu neirālā balss — uzreiz, bez Windows valodas pakotnes
    if lang.startswith("lv"):
        chosen = voice or DEFAULT_LV_VOICE
        edge = _speak_edge_tts(t, voice=chosen)
        if edge.get("ok"):
            return edge

    # 2) Windows SAPI (ja ir LV pakotne / citādi fonētika)
    if sys.platform.startswith("win"):
        sapi = _speak_sapi_windows(t, lang=lang)
        if sapi.get("ok"):
            return sapi

    # 3) espeak u.c.
    for cmd in (
        ["espeak-ng", "-v", "lv" if lang.startswith("lv") else "en", t],
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

    err = "Nav TTS. Palaid scripts\\install_latvian_voice.ps1 (Everita latviešu balss)."
    if lang.startswith("lv"):
        return {"ok": False, "error": err, "engine": "edge-tts", "hint": "install_latvian_voice"}
    return {"ok": False, "error": err}


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
