from mainbrain.tools.sense import (
    DEFAULT_LV_VOICE,
    LV_VOICE_FEMALE,
    describe_image_basic,
    face_recognition_app_source,
    opencv_available,
    speak_text,
    _lv_phonetic_for_en_voice,
)


def test_face_app_source_is_runnable_script():
    src = face_recognition_app_source()
    assert "VideoCapture" in src
    assert "haarcascade" in src
    assert "enroll" in src.lower()
    assert "recognize" in src.lower()


def test_describe_without_image_file(tmp_path):
    # Neeksistējošs ceļš — joprojām atgriež struktūru
    info = describe_image_basic(str(tmp_path / "missing.jpg"))
    assert info["ok"] is True
    assert "description" in info


def test_speak_empty():
    assert speak_text("").get("ok") is False


def test_latvian_voice_constants():
    assert DEFAULT_LV_VOICE == "lv-LV-EveritaNeural"
    assert LV_VOICE_FEMALE.startswith("lv-LV-")
    assert "aa" in _lv_phonetic_for_en_voice("mācos")
    assert "sh" in _lv_phonetic_for_en_voice("šis")


def test_opencv_flag_is_bool():
    assert isinstance(opencv_available(), bool)
