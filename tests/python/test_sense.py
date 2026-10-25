from mainbrain.tools.sense import (
    describe_image_basic,
    face_recognition_app_source,
    opencv_available,
    speak_text,
)


def test_face_app_source_is_runnable_script():
    src = face_recognition_app_source()
    assert "VideoCapture" in src
    assert "haarcascade" in src
    assert "enrolled_faces" in src


def test_describe_without_image_file(tmp_path):
    # Neeksistējošs ceļš — joprojām atgriež struktūru
    info = describe_image_basic(str(tmp_path / "missing.jpg"))
    assert info["ok"] is True
    assert "description" in info


def test_speak_empty():
    assert speak_text("").get("ok") is False


def test_opencv_flag_is_bool():
    assert isinstance(opencv_available(), bool)
