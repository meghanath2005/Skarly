import math
import subprocess
import wave
from pathlib import Path

import numpy as np

from app.services import stems as stems_service


def write_wav(path: Path, seconds: float = 4.0, frequency: float = 220.0, amplitude: float = 0.3, sample_rate: int = 22050) -> Path:
    t = np.linspace(0, seconds, int(sample_rate * seconds), endpoint=False)
    samples = amplitude * np.sin(2 * math.pi * frequency * t)
    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype(np.int16)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm.tobytes())
    return path


def test_missing_audio_path_returns_not_found(tmp_path):
    response = stems_service.separate_stems(
        audio_path=tmp_path / "missing.wav",
        output_dir=tmp_path / "stems",
        enabled=True,
    )

    assert response.status == "not_found"
    assert response.diagnostics is not None
    assert response.diagnostics.failed_step == "stem_separation"
    assert any("does not exist" in warning for warning in response.warnings)


def test_disabled_stems_returns_not_enabled(tmp_path):
    response = stems_service.separate_stems(
        audio_path=tmp_path / "missing.wav",
        output_dir=tmp_path / "stems",
        enabled=False,
    )

    assert response.status == "not_enabled"
    assert response.diagnostics is not None
    assert response.diagnostics.suggested_fix


def test_mock_demucs_success_returns_valid_stems(monkeypatch, tmp_path):
    source = write_wav(tmp_path / "source.wav")

    monkeypatch.setattr(stems_service, "_command_available", lambda _command_head: True)

    def fake_run(command, capture_output, text, timeout, check, env):
        assert "PYTHONPATH" not in {key.upper() for key in env}
        assert "PYTHONHOME" not in {key.upper() for key in env}
        output_dir = Path(command[command.index("-o") + 1])
        for stem, frequency in {"vocals": 330.0, "drums": 120.0, "bass": 80.0, "other": 440.0}.items():
            write_wav(output_dir / "htdemucs" / source.stem / f"{stem}.wav", frequency=frequency)
        return subprocess.CompletedProcess(command, 0, stdout="demucs ok", stderr="")

    monkeypatch.setattr(stems_service.subprocess, "run", fake_run)

    response = stems_service.separate_stems(
        audio_path=source,
        output_dir=tmp_path / "stems",
        job_id="job123",
        enabled=True,
        demucs_cli_path="fake-demucs",
    )

    assert response.status == "completed"
    assert set(response.stem_paths) == {"vocals", "drums", "bass", "other"}
    assert all(Path(path).exists() for path in response.stem_paths.values())
    assert response.quality_reports
    assert all(report.passed for report in response.quality_reports.values())


def test_mock_demucs_failure_returns_diagnostics(monkeypatch, tmp_path):
    source = write_wav(tmp_path / "source.wav")
    monkeypatch.setattr(stems_service, "_command_available", lambda _command_head: True)

    def fake_run(command, capture_output, text, timeout, check, env):
        return subprocess.CompletedProcess(command, 2, stdout="", stderr="demucs import failed")

    monkeypatch.setattr(stems_service.subprocess, "run", fake_run)

    response = stems_service.separate_stems(
        audio_path=source,
        output_dir=tmp_path / "stems",
        enabled=True,
        demucs_cli_path="fake-demucs",
    )

    assert response.status == "failed"
    assert response.diagnostics is not None
    assert response.diagnostics.failed_step == "stem_separation"
    assert "code 2" in response.diagnostics.error_message
    assert any("Demucs exited" in warning for warning in response.warnings)


def test_demucs_command_preserves_windows_python_path_with_module_arguments(tmp_path):
    source = tmp_path / "source.wav"
    command = stems_service.build_demucs_command(
        demucs_cli_path=r"D:\intern\skarly-ai-repos\_envs\demucs\Scripts\python.exe -m demucs.separate",
        source_audio_path=source,
        output_dir=tmp_path / "stems",
        stems=["drums", "bass", "other"],
        model="htdemucs_ft",
        device="cuda",
    )

    assert command[:3] == [
        r"D:\intern\skarly-ai-repos\_envs\demucs\Scripts\python.exe",
        "-m",
        "demucs.separate",
    ]
    assert command[command.index("-n") + 1] == "htdemucs_ft"
    assert command[command.index("-d") + 1] == "cuda"
    assert command[-1] == str(source)


def test_demucs_two_stem_command_returns_vocals_and_no_vocals(tmp_path):
    source = tmp_path / "source.wav"
    command = stems_service.build_demucs_command(
        demucs_cli_path="python -m demucs",
        source_audio_path=source,
        output_dir=tmp_path / "stems",
        stems=["vocals", "no_vocals"],
    )

    assert "--two-stems=vocals" in command
    assert command[command.index("-n") + 1] == "htdemucs_ft"
    assert command[command.index("-d") + 1] == "cuda"


def test_demucs_subprocess_environment_removes_parent_python_overrides(monkeypatch):
    monkeypatch.setenv("PYTHONPATH", "backend/.pydeps")
    monkeypatch.setenv("PYTHONHOME", "backend/python")
    monkeypatch.setenv("SKARLY_TEST_ENV", "preserved")

    environment = stems_service._isolated_python_environment()

    assert "PYTHONPATH" not in {key.upper() for key in environment}
    assert "PYTHONHOME" not in {key.upper() for key in environment}
    assert environment["SKARLY_TEST_ENV"] == "preserved"
