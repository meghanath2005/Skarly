from pathlib import Path

from app.audio_validation import validate_audio_file
from app.generators.procedural_v2 import generate_backing


def generate_style(tmp_path: Path, style: str, duration: int = 4):
    result = generate_backing(
        job_id=f"job_{style.lower().replace(' ', '_').replace('/', '_')}",
        output_dir=tmp_path,
        duration_seconds=duration,
        bpm=88,
        key="A minor",
        genre="Pop",
        production_style=style,
        arrangement_style=None,
        instruments=[],
        mood_tags=[],
        sample_rate=22050,
    )
    assert result.success is True
    assert result.output_path is not None
    return result, validate_audio_file(
        result.output_path,
        expected_duration_seconds=duration,
        generator_name="procedural_v2",
        fallback_used=True,
    )


def test_procedural_v2_generates_valid_wav(tmp_path):
    result, report = generate_style(tmp_path, "Bollywood Ballad")

    path = Path(result.output_path)
    assert path.exists()
    assert path.stat().st_size > 4 * 1024
    assert report.passed is True
    assert report.audio_exists is True
    assert report.channels == 2


def test_procedural_v2_duration_roughly_matches_request(tmp_path):
    _result, report = generate_style(tmp_path, "Lo-fi Cover", duration=5)

    assert report.duration_seconds is not None
    assert 4.8 <= report.duration_seconds <= 5.2


def test_procedural_v2_core_styles_generate_valid_audio(tmp_path):
    for style in ("Bollywood Ballad", "Lo-fi Cover", "Bhajan / Devotional", "Trap Soul"):
        _result, report = generate_style(tmp_path, style)

        assert report.passed is True
        assert report.is_silent is False
        assert report.peak_db is not None


def test_procedural_v2_output_does_not_clip(tmp_path):
    _result, report = generate_style(tmp_path, "Trap Soul")

    assert report.passed is True
    assert report.clipping_detected is False
    assert not any("clipping" in warning.lower() for warning in report.warnings)


def test_procedural_v2_unknown_style_uses_valid_default(tmp_path):
    _result, report = generate_style(tmp_path, "Unknown Neon Folk Debug")

    assert report.passed is True
    assert report.generator_name == "procedural_v2"
    assert report.fallback_used is True
