from pathlib import Path

import numpy as np
import soundfile as sf

from app.generators.ace_step import _splice_repaint_region, edit_section


def _write_stereo(path: Path, samples: np.ndarray, sample_rate: int = 8_000) -> None:
    sf.write(str(path), np.column_stack([samples, samples]), sample_rate, format="WAV", subtype="FLOAT")


def test_splice_repaint_changes_only_selected_interval(tmp_path: Path):
    sample_rate = 8_000
    seconds = 4
    timeline = np.arange(sample_rate * seconds, dtype=np.float32) / sample_rate
    source = 0.15 * np.sin(2 * np.pi * 220 * timeline)
    generated = 0.15 * np.sin(2 * np.pi * 440 * timeline)
    source_path = tmp_path / "source.wav"
    generated_path = tmp_path / "generated.wav"
    output_path = tmp_path / "output.wav"
    _write_stereo(source_path, source, sample_rate)
    _write_stereo(generated_path, generated, sample_rate)

    result = _splice_repaint_region(
        source_path=source_path,
        generated_path=generated_path,
        output_path=output_path,
        start_seconds=1.0,
        end_seconds=3.0,
        boundary_crossfade_seconds=0.025,
    )

    original, _ = sf.read(str(source_path), dtype="float32", always_2d=True)
    edited, _ = sf.read(str(output_path), dtype="float32", always_2d=True)
    start = sample_rate
    end = sample_rate * 3
    assert np.array_equal(edited[:start], original[:start])
    assert np.array_equal(edited[end:], original[end:])
    assert not np.array_equal(edited[start:end], original[start:end])
    assert result["preserved_outside_section"] is True
    assert result["section_changed"] is True
    assert result["outside_max_abs_error"] == 0
    assert result["source_frames"] == result["output_frames"] == sample_rate * seconds


def test_edit_section_rejects_range_outside_source(tmp_path: Path):
    source_path = tmp_path / "source.wav"
    samples = np.zeros(8_000, dtype=np.float32)
    _write_stereo(source_path, samples)

    result = edit_section(
        source_audio_path=str(source_path),
        section_name="hook",
        edit_prompt="Add warm strings.",
        output_dir=tmp_path,
        job_id="section_test",
        timeout_seconds=30,
        section_start_seconds=0.5,
        section_end_seconds=2.0,
    )

    assert result.success is False
    assert "Invalid section range" in (result.error_message or "")
    assert not Path(result.output_path or "").exists()
