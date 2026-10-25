import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "apps" / "face_recognition" / "face_app.py"


@pytest.mark.skipif(not APP.is_file(), reason="face_app missing")
def test_face_app_selftest():
    pytest.importorskip("cv2")
    # izolēta data mape caur cwd
    import os
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        env = os.environ.copy()
        # selftest raksta blakus skriptam — palaidam ar --selftest no app mapes
        completed = subprocess.run(
            [sys.executable, str(APP), "--selftest"],
            cwd=tmp,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        # selftest raksta data/ relative to script location, not cwd — OK
        assert completed.returncode == 0, completed.stdout + completed.stderr
        assert "SELFTEST OK" in completed.stdout


def test_copy_face_app(tmp_path: Path):
    from mainbrain.tools.sense import copy_face_recognition_app

    result = copy_face_recognition_app(tmp_path / "out")
    assert result["ok"] is True
    assert (tmp_path / "out" / "face_app.py").is_file()
