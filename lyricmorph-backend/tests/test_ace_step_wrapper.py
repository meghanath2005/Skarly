from pathlib import Path

from app.generators import ace_step


class FakeResponse:
    def __init__(self, payload=None, *, content=b"", status_code=200):
        self._payload = payload or {}
        self.content = content
        self.status_code = status_code
        self.text = ""

    def json(self):
        return self._payload


def test_health_check_with_missing_cli_does_not_crash(tmp_path):
    health = ace_step.health_check(cli_path=str(tmp_path / "missing-acestep.exe"), output_dir=tmp_path)

    assert health["available"] is False
    assert health["mode"] == "cli"
    assert "not found" in health["message"]


def test_build_command_uses_configurable_cli_path(tmp_path):
    output = tmp_path / "song.wav"

    command = ace_step.build_command(
        positive_prompt="positive",
        negative_prompt="negative",
        lyrics="lyrics",
        duration_seconds=90,
        bpm=88,
        key="F minor",
        output_path=output,
        cli_path="python -m custom_acestep.generate",
        device="cuda",
    )

    assert command[:3] == ["python", "-m", "custom_acestep.generate"]
    assert "--prompt" in command
    assert "--negative_prompt" in command
    assert str(output) in command
    assert "lyrics" in command
    assert "88" in command


def test_generate_song_success_with_mocked_subprocess(monkeypatch, tmp_path):
    cli = tmp_path / "acestep.exe"
    cli.write_text("", encoding="utf-8")

    def fake_run(command, **_kwargs):
        output = Path(command[command.index("--output") + 1])
        output.write_bytes(b"wav-bytes")
        return type("Completed", (), {"returncode": 0, "stdout": "rendered", "stderr": ""})()

    monkeypatch.setattr(ace_step.subprocess, "run", fake_run)

    result = ace_step.generate_song(
        positive_prompt="positive",
        negative_prompt="negative",
        lyrics=None,
        duration_seconds=90,
        bpm=88,
        key="F minor",
        output_dir=tmp_path,
        job_id="job_1",
        timeout_seconds=10,
        cli_path=str(cli),
    )

    assert result.success is True
    assert result.output_path is not None
    assert Path(result.output_path).exists()
    assert result.generator_name == "ACE-Step"
    assert result.logs == ["rendered"]


def test_generate_song_failure_with_mocked_subprocess(monkeypatch, tmp_path):
    cli = tmp_path / "acestep.exe"
    cli.write_text("", encoding="utf-8")

    def fake_run(_command, **_kwargs):
        return type("Completed", (), {"returncode": 2, "stdout": "starting", "stderr": "weights missing"})()

    monkeypatch.setattr(ace_step.subprocess, "run", fake_run)

    result = ace_step.generate_song(
        positive_prompt="positive",
        negative_prompt="negative",
        lyrics=None,
        duration_seconds=90,
        bpm=88,
        key="F minor",
        output_dir=tmp_path,
        job_id="job_2",
        timeout_seconds=10,
        cli_path=str(cli),
    )

    assert result.success is False
    assert "exited with code 2" in result.error_message
    assert "weights missing" in result.logs
    assert "Verify ACE-Step environment" in result.suggested_fix


def test_transform_reference_audio_uses_cover_conditioning(monkeypatch, tmp_path):
    source = tmp_path / "reference.wav"
    source.write_bytes(b"reference-audio")
    release_payload = {}

    class FakeRequests:
        @staticmethod
        def post(url, **kwargs):
            if url.endswith("/release_task"):
                release_payload.update(kwargs["data"])
                assert "src_audio" in kwargs["files"]
                return FakeResponse({"data": {"task_id": "task_music_1"}})
            return FakeResponse(
                {
                    "data": [
                        {
                            "task_id": "task_music_1",
                            "status": 1,
                            "result": '[{"file":"/v1/audio?path=transformed.wav"}]',
                        }
                    ]
                }
            )

        @staticmethod
        def get(url, **_kwargs):
            assert "transformed.wav" in url
            return FakeResponse(content=b"transformed-audio")

    monkeypatch.setattr(ace_step, "requests", FakeRequests())

    result = ace_step.transform_reference_audio(
        source_audio_path=source,
        prompt="fresh original instrumental rock arrangement",
        negative_prompt="no vocals, no copied melody",
        output_dir=tmp_path,
        job_id="music_transform_1",
        timeout_seconds=10,
        reference_strength=0.3,
        bpm=92,
        key="D minor",
        duration_seconds=30,
    )

    assert result.success is True
    assert Path(result.output_path).read_bytes() == b"transformed-audio"
    assert release_payload["task_type"] == "cover"
    assert release_payload["lyrics"] == "[Instrumental]"
    assert release_payload["audio_cover_strength"] == 0.3
    assert release_payload["bpm"] == 92
    assert result.metadata["reference_conditioned"] is True
