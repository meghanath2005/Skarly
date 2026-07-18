from pathlib import Path

from app.services import safe_paths


def test_valid_output_path_accepted():
    path = safe_paths.resolve_safe_output_path("outputs/ace_step/song.wav")

    assert path.name == "song.wav"
    assert safe_paths.is_within_allowed_dirs(path)


def test_path_traversal_rejected():
    try:
        safe_paths.resolve_safe_output_path("outputs/ace_step/../../secret.txt")
    except ValueError as exc:
        assert "outside allowed" in str(exc)
    else:
        raise AssertionError("Traversal path should be rejected")


def test_outside_absolute_path_rejected(tmp_path):
    outside = tmp_path / "outside.wav"

    assert safe_paths.is_within_allowed_dirs(outside) is False


def test_safe_url_generation_works():
    path = safe_paths.resolve_output_dir("outputs/mixes/final mix.wav")
    url = safe_paths.safe_url_for_output(path)

    assert url == "/outputs/mixes/final%20mix.wav"


def test_filename_sanitization():
    assert safe_paths.sanitize_filename("../My Song?.wav") == "My_Song_.wav"
    assert safe_paths.sanitize_filename("") == "untitled"
