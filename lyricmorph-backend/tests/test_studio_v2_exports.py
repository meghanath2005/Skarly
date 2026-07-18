from __future__ import annotations

import math
from pathlib import Path
import wave
import zipfile

import numpy as np

from app.models import StemSeparationResponse
from app.services import studio_v2_exports


def write_wav(path: Path, *, seconds: float = 2.0, frequency: float = 220.0) -> Path:
    sample_rate = 48000
    timeline = np.linspace(0, seconds, int(sample_rate * seconds), endpoint=False)
    samples = (0.2 * np.sin(2 * math.pi * frequency * timeline) * 32767).astype(np.int16)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(np.repeat(samples[:, None], 2, axis=1).tobytes())
    return path


def generation_fixture(tmp_path: Path) -> tuple[dict, Path, Path]:
    skarly_root = tmp_path / "skarly"
    job_dir = skarly_root / "job_1"
    vocal = write_wav(job_dir / "vocal.wav", frequency=330)
    backing = write_wav(job_dir / "backing.wav", frequency=110)
    final_mix = write_wav(job_dir / "final.wav", frequency=220)
    analysis = job_dir / "analysis.json"
    analysis.write_text("{}", encoding="utf-8")
    job = {
        "job_id": "generation_1",
        "analysis_id": "analysis_1",
        "result": {
            "song_intelligence_map": {"duration_seconds": 2.0},
            "analysis_url": "/outputs/skarly/job_1/analysis.json",
            "vocal_url": "/outputs/skarly/job_1/vocal.wav",
            "versions": [
                {
                    "name": "Producer One",
                    "style_family": "bollywood_acoustic",
                    "input_vocal_url": "/outputs/skarly/job_1/vocal.wav",
                    "backing_url": "/outputs/skarly/job_1/backing.wav",
                    "final_mix_url": "/outputs/skarly/job_1/final.wav",
                }
            ],
        },
    }
    assert vocal.is_file() and final_mix.is_file()
    return job, skarly_root, backing


def test_v2_export_generates_exact_duration_optional_stems(tmp_path):
    generation, skarly_root, backing = generation_fixture(tmp_path)
    separated_root = tmp_path / "separated"
    stem_paths = {
        name: str(write_wav(separated_root / f"{name}.wav", frequency=frequency))
        for name, frequency in {"drums": 120, "bass": 70, "other": 440}.items()
    }
    calls: list[tuple[Path, str]] = []

    def separate(source: Path, job_id: str) -> StemSeparationResponse:
        calls.append((source, job_id))
        return StemSeparationResponse(
            status="completed",
            engine="demucs",
            stem_paths=stem_paths,
        )

    exported = studio_v2_exports.create_export_bundle(
        generation,
        version_index=0,
        include_optional_stems=True,
        exports_dir=tmp_path / "exports",
        skarly_output_dir=skarly_root,
        ffmpeg_path="ffmpeg",
        timeout_sec=30,
        stem_separator=separate,
    )

    assert calls == [(backing.resolve(), "generation_1_version_1")]
    assert {"stem_drums", "stem_bass", "stem_other"}.issubset(exported.files)
    assert all(exported.durations_seconds[name] == 2.0 for name in ("stem_drums", "stem_bass", "stem_other"))
    assert not exported.warnings
    bundle = Path(tmp_path / "exports" / exported.export_id / "skarly_export_bundle.zip")
    with zipfile.ZipFile(bundle) as archive:
        assert {"stem_drums.wav", "stem_bass.wav", "stem_other.wav"}.issubset(archive.namelist())


def test_v2_export_preserves_core_files_when_optional_separation_fails(tmp_path):
    generation, skarly_root, _backing = generation_fixture(tmp_path)

    def separate(_source: Path, _job_id: str) -> StemSeparationResponse:
        return StemSeparationResponse(
            status="failed",
            engine="demucs",
            warnings=["Demucs test failure."],
        )

    exported = studio_v2_exports.create_export_bundle(
        generation,
        version_index=0,
        include_optional_stems=True,
        exports_dir=tmp_path / "exports",
        skarly_output_dir=skarly_root,
        ffmpeg_path="ffmpeg",
        timeout_sec=30,
        stem_separator=separate,
    )

    assert {"final_wav", "final_mp3", "instrumental", "processed_vocal"}.issubset(exported.files)
    assert not any(name.startswith("stem_") for name in exported.files)
    assert any("Demucs test failure" in warning for warning in exported.warnings)
    assert any("drums, bass, other" in warning for warning in exported.warnings)
