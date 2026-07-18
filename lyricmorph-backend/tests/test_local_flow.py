from app.models import ArrangementMode, CreatorMode, Genre, JobRecord, JobStatus, ProductionStyle, SongAnalysis, SourceType, now_utc
from app.repository import InMemoryJobRepository
from app.storage import MockStorageService

from app.config import Settings
from app.worker import (
    MockAIWorker,
    MvpAudioWorker,
    VocalIsolationError,
    ace_step_payload,
    command_parts,
    create_ace_step_bed,
    create_basic_pitch_melody,
    create_genre_bed,
    create_music_bed,
    create_music_bed_with_report,
    extract_ace_audio_url,
    fallback_song_analysis,
    backing_prompt,
    tool_dependency_env,
)
import io
import json
import os
from pathlib import Path
import struct
import wave
import zipfile


def write_test_wav(path: Path, seconds: float = 1.2, sample_rate: int = 8000) -> None:
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        for index in range(int(seconds * sample_rate)):
            sample = int(0.15 * 32767) if index % 32 < 16 else int(-0.15 * 32767)
            packed = struct.pack("<h", sample)
            wav.writeframesraw(packed + packed)


def fake_generation_report(path: Path, generator: str = "procedural_v2") -> dict:
    return {
        "selected_generator": generator,
        "final_generator_used": generator,
        "fallback_attempted": False,
        "fallback_result": "not_attempted",
        "warnings": [],
        "expected_output_path": str(path),
        "output_file_exists": True,
        "output_file_size": path.stat().st_size if path.exists() else 0,
        "output_ffprobe_duration": 1.2,
    }


def test_external_python_tool_env_strips_backend_pythonpath(tmp_path, monkeypatch):
    monkeypatch.setenv("PYTHONPATH", f".{os.pathsep}.pydeps{os.pathsep}custom-path")

    external_python = tmp_path / "venv" / "Scripts" / "python.exe"
    env = tool_dependency_env([str(external_python), "-m", "demucs.separate"])

    assert "PYTHONPATH" not in env
    assert env["PYTHONIOENCODING"] == "utf-8"
    assert env["PYTHONUTF8"] == "1"


def test_current_python_tool_env_keeps_backend_pythonpath(monkeypatch):
    monkeypatch.setenv("PYTHONPATH", "backend-path")

    env = tool_dependency_env(command_parts("python -m demucs.separate"))

    assert "backend-path" in env.get("PYTHONPATH", "")


def test_mock_worker_completes_job_and_deletes_raw_audio():
    repository = InMemoryJobRepository()
    timestamp = now_utc()
    job = JobRecord(
        job_id="job_test",
        user_id="user_test",
        creator_mode=CreatorMode.guest,
        genre=Genre.lofi,
        track_name="Ocean Demo",
        source_type=SourceType.local_upload,
        raw_audio_path="raw/user_test/upload/file.mp3",
        status=JobStatus.queued,
        stage="queued",
        delete_raw_after_mix=True,
        created_at=timestamp,
        updated_at=timestamp,
    )
    repository.create(job)

    completed = MockAIWorker(repository).run_job("job_test")

    assert completed.status == JobStatus.ready
    assert completed.stage == "ready"
    assert completed.final_mp3_path == "users/user_test/final/job_test/ocean-demo.mp3"
    assert completed.raw_audio_path is None


def test_history_excludes_deleted_jobs():
    repository = InMemoryJobRepository()
    timestamp = now_utc()
    repository.create(
        JobRecord(
            job_id="job_deleted",
            user_id="user_test",
            creator_mode=CreatorMode.guest,
            genre=Genre.pop,
            track_name="Deleted",
            source_type=SourceType.recording,
            raw_audio_path="raw/user_test/upload/file.mp3",
            status=JobStatus.queued,
            stage="queued",
            created_at=timestamp,
            updated_at=timestamp,
        )
    )

    repository.mark_deleted("job_deleted")

    assert repository.list_for_user("user_test") == []


def test_mvp_audio_worker_outputs_real_mp3_bytes(monkeypatch):
    monkeypatch.setattr("app.worker.settings", Settings(music_generator_backend="procedural_v2", melody_analyzer_backend="basic_pitch"))
    repository = InMemoryJobRepository()
    storage = MockStorageService()
    raw_path = "users/user_test/raw/upload/file.webm"
    storage.upload_bytes(raw_path, b"raw-audio", "audio/webm")
    timestamp = now_utc()
    repository.create(
        JobRecord(
            job_id="job_audio",
            user_id="user_test",
            creator_mode=CreatorMode.guest,
            genre=Genre.hiphop,
            production_style=ProductionStyle.bollywood_ballad,
            arrangement_style="Piano-led cinematic",
            main_instruments=["piano", "strings", "pads", "soft drums", "bass"],
            user_overrides={
                "production_bpm": 62.5,
                "key": "C major",
                "energy": "medium-low",
                "output_duration_seconds": 30,
                "vocal_gain_db": 2.0,
                "backing_gain_db": -4.0,
                "ducking_strength": "strong",
            },
            track_name="Street Demo",
            source_type=SourceType.recording,
            raw_audio_path=raw_path,
            status=JobStatus.queued,
            stage="queued",
            delete_raw_after_mix=True,
            created_at=timestamp,
            updated_at=timestamp,
        )
    )

    monkeypatch.setattr("app.worker.shutil.which", lambda path: path)

    def fake_ffmpeg(args, timeout=None):
        output = args[-1]
        with open(output, "wb") as handle:
            handle.write(b"real-mp3" if output.endswith(".mp3") else b"wav")

    worker = MvpAudioWorker(repository, storage_service=storage, ffmpeg_path="ffmpeg")
    monkeypatch.setattr(worker, "_run_ffmpeg", fake_ffmpeg)

    def fake_melody(_input_wav, _output_dir, output_midi, output_notes, _analysis):
        output_midi.write_bytes(b"MThdmelody")
        output_notes.write_text("start,end,pitch\n", encoding="utf-8")
        return output_midi, output_notes

    monkeypatch.setattr(worker, "_create_melody_midi", fake_melody)
    monkeypatch.setattr("app.worker.create_music_bed_with_report", lambda path, *args, **kwargs: (write_test_wav(path), fake_generation_report(path))[1])

    completed = worker.run_job("job_audio")

    assert completed.status == JobStatus.ready
    assert completed.stage == "ready"
    assert completed.raw_audio_path is None
    assert completed.final_mp3_path == "users/user_test/final/job_audio/street-demo.mp3"
    assert storage.download_bytes(completed.final_mp3_path) == b"real-mp3"
    assert completed.isolated_vocal_path == "users/user_test/debug/job_audio/isolated-vocal.wav"
    assert completed.backing_audio_path == "users/user_test/debug/job_audio/backing-only.wav"
    assert completed.analysis is not None
    assert completed.analysis.detected_bpm is not None
    assert completed.analysis.production_bpm is not None
    assert completed.analysis.primary_key
    assert completed.analysis.alternative_key
    assert completed.analysis.mood_tags
    assert completed.analysis.arrangement_style
    assert completed.analysis.production_style == "Bollywood Ballad"
    assert completed.analysis.arrangement_style == "Piano-led cinematic"
    assert completed.analysis.main_instruments == ["piano", "strings", "pads", "soft drums", "bass"]
    assert completed.analysis.production_bpm == 62.5
    assert completed.analysis.primary_key == "C major"
    assert completed.analysis.energy == "medium-low"
    assert completed.analysis.pitch_contour_status in {"available", "fallback_used", "unavailable"}
    assert completed.analysis.melody_midi_status == "available"
    assert completed.blueprint is not None
    assert completed.final_generation_settings["user_overrides"]["production_bpm"] == 62.5
    assert completed.final_generation_settings["mix"]["ducking_strength"] == "strong"
    assert completed.quality_report is not None
    assert completed.quality_report["generator_used"] == "procedural_v2"
    assert completed.export_paths["producer_pack"].endswith("/producer-pack.zip")
    assert storage.download_bytes(completed.export_paths["wav"]) == b"wav"
    assert storage.download_bytes(completed.export_paths["midi"]).startswith(b"MThd")
    assert storage.download_bytes(completed.export_paths["melody_midi"]) == b"MThdmelody"
    assert b"Skarly Demo: Street Demo" in storage.download_bytes(completed.export_paths["chord_sheet"])
    assert completed.export_paths["drums_stem"].endswith("/drums.wav")
    assert completed.export_paths["bass_stem"].endswith("/bass.wav")
    assert completed.export_paths["guitar_stem"].endswith("/guitar.wav")
    assert completed.export_paths["keys_stem"].endswith("/keys.wav")
    assert completed.export_paths["reference_stem"].endswith("/source-reference.wav")
    pack_path = completed.export_paths["producer_pack"]
    with zipfile.ZipFile(io.BytesIO(storage.download_bytes(pack_path))) as archive:
        assert "song_blueprint.json" in archive.namelist()
        assert "analysis.json" in archive.namelist()
        assert "producer_prompt.txt" in archive.namelist()
        assert "quality_report.json" in archive.namelist()
        assert "preview_final_mix.mp3" in archive.namelist()
        assert "preview_backing_only.mp3" in archive.namelist()
        assert "preview_vocal_only.mp3" in archive.namelist()
        assert "chords.mid" in archive.namelist()
        assert "melody.mid" in archive.namelist()
        assert "melody-notes.csv" in archive.namelist()
        assert "stems/drums.wav" in archive.namelist()
        assert "stems/guitar.wav" in archive.namelist()
        analysis_json = json.loads(archive.read("analysis.json"))
        quality_report = json.loads(archive.read("quality_report.json"))
        producer_prompt = archive.read("producer_prompt.txt").decode("utf-8")
        assert "production_bpm" in analysis_json
        blueprint_json = json.loads(archive.read("song_blueprint.json"))
        assert blueprint_json["final_generation_settings"]["production_style"] == "Bollywood Ballad"
        assert blueprint_json["final_generation_settings"]["production_bpm"] == 62.5
        assert blueprint_json["final_generation_settings"]["user_overrides"]["key"] == "C major"
        assert blueprint_json["blueprint"]["production_style"] == "Bollywood Ballad"
        assert "expected_pack_files" in quality_report
        assert quality_report["production_style"] == "Bollywood Ballad"
        assert quality_report["generator_used"] == "procedural_v2"
        assert quality_report["ducking_strength"] == "strong"
        assert "Create an original Bollywood Ballad" in producer_prompt
        assert "62.5 BPM" in producer_prompt
        assert "Piano-led cinematic" in producer_prompt


def test_half_time_bpm_correction_for_emotional_ballads():
    analysis = fallback_song_analysis(Genre.piano, {"duration": 45, "tempo_bpm": 126})

    assert analysis.detected_bpm == 126
    assert analysis.production_bpm == 63
    assert analysis.tempo_feel == "half-time"
    assert any("half-time BPM" in warning for warning in analysis.warnings)


def test_basic_pitch_melody_adapter_writes_midi_and_notes(tmp_path, monkeypatch):
    tool = tmp_path / "basic-pitch.exe"
    tool.write_text("", encoding="utf-8")
    source = tmp_path / "vocal.wav"
    source.write_bytes(b"wav")
    output_midi = tmp_path / "melody.mid"
    output_notes = tmp_path / "melody-notes.csv"
    analysis = SongAnalysis(
        bpm=104,
        key="E minor",
        duration_seconds=12,
        energy="Medium",
        mood="Focused",
        vocal_energy=0.4,
        suggested_genre=Genre.rock,
        pitch_summary="melody present",
    )

    monkeypatch.setattr(
        "app.worker.settings",
        Settings(
            melody_analyzer_backend="basic_pitch",
            basic_pitch_path=str(tool),
            basic_pitch_model_serialization="onnx",
            basic_pitch_save_note_events=True,
        ),
    )

    def fake_run(args, **kwargs):
        out_dir = Path(args[1])
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "vocal_basic_pitch.mid").write_bytes(b"MThdbasicpitch")
        (out_dir / "vocal_basic_pitch.csv").write_text("start,end,pitch\n", encoding="utf-8")
        return type("Completed", (), {"returncode": 0})()

    monkeypatch.setattr("app.worker.subprocess.run", fake_run)

    midi_file, notes_file = create_basic_pitch_melody(source, tmp_path / "bp-out", output_midi, output_notes, analysis)

    assert midi_file.read_bytes() == b"MThdbasicpitch"
    assert notes_file is not None
    assert notes_file.read_text(encoding="utf-8").startswith("start,end,pitch")


def test_full_song_upload_runs_vocal_isolation_before_generation(monkeypatch):
    monkeypatch.setattr("app.worker.settings", Settings(music_generator_backend="procedural_v2", stem_separator_backend="demucs"))
    repository = InMemoryJobRepository()
    storage = MockStorageService()
    raw_path = "users/user_test/raw/upload/full_mix.mp3"
    storage.upload_bytes(raw_path, b"raw-audio", "audio/mpeg")
    timestamp = now_utc()
    repository.create(
        JobRecord(
            job_id="job_upload_mix",
            user_id="user_test",
            creator_mode=CreatorMode.guest,
            genre=Genre.rnb,
            track_name="Isolated Demo",
            source_type=SourceType.local_upload,
            arrangement_mode=ArrangementMode.full_song,
            raw_audio_path=raw_path,
            status=JobStatus.queued,
            stage="queued",
            delete_raw_after_mix=False,
            created_at=timestamp,
            updated_at=timestamp,
        )
    )

    used_sources = []
    monkeypatch.setattr("app.worker.shutil.which", lambda path: path)
    monkeypatch.setattr("app.worker.audio_duration_seconds", lambda *args, **kwargs: 12.0)

    def fake_ffmpeg(args, timeout=None):
        output = args[-1]
        with open(output, "wb") as handle:
            handle.write(b"real-mp3" if output.endswith(".mp3") else b"wav")

    def fake_bed(path, genre, job_id, seconds=62.0, sample_rate=44100, source_audio_path=None, timing=None, ffmpeg_path=None):
        used_sources.append(str(source_audio_path))
        write_test_wav(path)
        return fake_generation_report(path)

    worker = MvpAudioWorker(repository, storage_service=storage, ffmpeg_path="ffmpeg")
    monkeypatch.setattr(worker, "_run_ffmpeg", fake_ffmpeg)
    monkeypatch.setattr(
        worker,
        "_isolate_vocals",
        lambda input_wav, output_dir: (
            output_dir.parent / "isolated-vocals.wav",
            {"status": "passed", "passed": True, "waveform_correlation": 0.02},
        ),
    )
    monkeypatch.setattr("app.worker.create_music_bed_with_report", fake_bed)

    completed = worker.run_job("job_upload_mix")

    assert completed.status == JobStatus.ready
    assert used_sources
    assert "vocal-clean.wav" in used_sources[0]


def test_vocal_upload_skips_demucs_in_vocal_to_song_mode(monkeypatch):
    monkeypatch.setattr("app.worker.settings", Settings(music_generator_backend="procedural_v2", stem_separator_backend="demucs"))
    repository = InMemoryJobRepository()
    storage = MockStorageService()
    raw_path = "users/user_test/raw/upload/lead_vocal.mp3"
    storage.upload_bytes(raw_path, b"raw-audio", "audio/mpeg")
    timestamp = now_utc()
    repository.create(
        JobRecord(
            job_id="job_vocal_upload",
            user_id="user_test",
            creator_mode=CreatorMode.guest,
            genre=Genre.pop,
            track_name="Vocal Upload Demo",
            source_type=SourceType.local_upload,
            arrangement_mode=ArrangementMode.vocal_to_song,
            raw_audio_path=raw_path,
            status=JobStatus.queued,
            stage="queued",
            delete_raw_after_mix=False,
            created_at=timestamp,
            updated_at=timestamp,
        )
    )

    monkeypatch.setattr("app.worker.shutil.which", lambda path: path)
    monkeypatch.setattr("app.worker.audio_duration_seconds", lambda *args, **kwargs: 12.0)

    def fake_ffmpeg(args, timeout=None):
        output = args[-1]
        with open(output, "wb") as handle:
            handle.write(b"real-mp3" if output.endswith(".mp3") else b"wav")

    worker = MvpAudioWorker(repository, storage_service=storage, ffmpeg_path="ffmpeg")
    monkeypatch.setattr(worker, "_run_ffmpeg", fake_ffmpeg)
    monkeypatch.setattr(worker, "_isolate_vocals", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("vocal uploads should not require Demucs")))
    monkeypatch.setattr("app.worker.create_music_bed_with_report", lambda path, *args, **kwargs: (write_test_wav(path), fake_generation_report(path))[1])

    completed = worker.run_job("job_vocal_upload")

    assert completed.status == JobStatus.ready
    assert "isolation=not_required" in completed.worker_notes


def test_recording_skips_vocal_isolation(monkeypatch):
    monkeypatch.setattr("app.worker.settings", Settings(music_generator_backend="procedural_v2", stem_separator_backend="demucs"))
    repository = InMemoryJobRepository()
    storage = MockStorageService()
    raw_path = "users/user_test/raw/upload/voice.webm"
    storage.upload_bytes(raw_path, b"raw-audio", "audio/webm")
    timestamp = now_utc()
    repository.create(
        JobRecord(
            job_id="job_recording",
            user_id="user_test",
            creator_mode=CreatorMode.guest,
            genre=Genre.pop,
            track_name="Recorded Demo",
            source_type=SourceType.recording,
            raw_audio_path=raw_path,
            status=JobStatus.queued,
            stage="queued",
            delete_raw_after_mix=False,
            created_at=timestamp,
            updated_at=timestamp,
        )
    )

    monkeypatch.setattr("app.worker.shutil.which", lambda path: path)
    monkeypatch.setattr("app.worker.audio_duration_seconds", lambda *args, **kwargs: 12.0)

    def fake_ffmpeg(args, timeout=None):
        output = args[-1]
        with open(output, "wb") as handle:
            handle.write(b"real-mp3" if output.endswith(".mp3") else b"wav")

    worker = MvpAudioWorker(repository, storage_service=storage, ffmpeg_path="ffmpeg")
    monkeypatch.setattr(worker, "_run_ffmpeg", fake_ffmpeg)
    monkeypatch.setattr(worker, "_isolate_vocals", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("recordings should skip Demucs")))

    completed = worker.run_job("job_recording")

    assert completed.status == JobStatus.ready


def test_music_to_music_generates_new_instrumental_without_vocal_isolation(monkeypatch):
    monkeypatch.setattr("app.worker.settings", Settings(music_generator_backend="procedural_v2", stem_separator_backend="demucs"))
    repository = InMemoryJobRepository()
    storage = MockStorageService()
    raw_path = "users/user_test/raw/upload/instrumental.mp3"
    storage.upload_bytes(raw_path, b"raw-audio", "audio/mpeg")
    timestamp = now_utc()
    repository.create(
        JobRecord(
            job_id="job_music_only",
            user_id="user_test",
            creator_mode=CreatorMode.guest,
            genre=Genre.rock,
            track_name="Music Remake",
            source_type=SourceType.local_upload,
            arrangement_mode=ArrangementMode.music_to_music,
            raw_audio_path=raw_path,
            status=JobStatus.queued,
            stage="queued",
            delete_raw_after_mix=False,
            created_at=timestamp,
            updated_at=timestamp,
        )
    )

    used_sources = []
    monkeypatch.setattr("app.worker.shutil.which", lambda path: path)
    monkeypatch.setattr("app.worker.audio_duration_seconds", lambda *args, **kwargs: 12.0)

    def fake_ffmpeg(args, timeout=None):
        output = args[-1]
        with open(output, "wb") as handle:
            handle.write(b"real-mp3" if output.endswith(".mp3") else b"wav")

    def fake_bed(path, genre, job_id, seconds=62.0, sample_rate=44100, source_audio_path=None, timing=None, ffmpeg_path=None):
        used_sources.append((str(source_audio_path), dict(timing or {})))
        write_test_wav(path)
        return fake_generation_report(path)

    worker = MvpAudioWorker(repository, storage_service=storage, ffmpeg_path="ffmpeg")
    monkeypatch.setattr(worker, "_run_ffmpeg", fake_ffmpeg)
    monkeypatch.setattr(worker, "_isolate_vocals", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("music-only mode should not isolate vocals")))
    monkeypatch.setattr("app.worker.create_music_bed_with_report", fake_bed)

    completed = worker.run_job("job_music_only")

    assert completed.status == JobStatus.ready
    assert completed.isolated_vocal_path is None
    assert completed.export_paths["reference_stem"].endswith("/source-reference.wav")
    assert completed.export_paths["drums_stem"].endswith("/drums.wav")
    assert "mode=music_to_music" in completed.worker_notes
    assert used_sources[0][0].endswith("normalized.wav")
    assert used_sources[0][1]["arrangement_mode"] == "music_to_music"


def test_full_song_vocal_isolation_failure_stops_generation(monkeypatch):
    monkeypatch.setattr("app.worker.settings", Settings(music_generator_backend="procedural_v2", stem_separator_backend="demucs"))
    repository = InMemoryJobRepository()
    storage = MockStorageService()
    raw_path = "users/user_test/raw/upload/full_mix.mp3"
    storage.upload_bytes(raw_path, b"raw-audio", "audio/mpeg")
    timestamp = now_utc()
    repository.create(
        JobRecord(
            job_id="job_failed_isolation",
            user_id="user_test",
            creator_mode=CreatorMode.guest,
            genre=Genre.rock,
            track_name="Failed Demo",
            source_type=SourceType.local_upload,
            arrangement_mode=ArrangementMode.full_song,
            raw_audio_path=raw_path,
            status=JobStatus.queued,
            stage="queued",
            delete_raw_after_mix=False,
            created_at=timestamp,
            updated_at=timestamp,
        )
    )

    monkeypatch.setattr("app.worker.shutil.which", lambda path: path)
    monkeypatch.setattr("app.worker.audio_duration_seconds", lambda *args, **kwargs: 12.0)

    def fake_ffmpeg(args, timeout=None):
        output = args[-1]
        with open(args[-1], "wb") as handle:
            handle.write(b"real-mp3" if output.endswith(".mp3") else b"wav")

    worker = MvpAudioWorker(repository, storage_service=storage, ffmpeg_path="ffmpeg")
    monkeypatch.setattr(worker, "_run_ffmpeg", fake_ffmpeg)
    monkeypatch.setattr(worker, "_isolate_vocals", lambda *args, **kwargs: (_ for _ in ()).throw(VocalIsolationError("bad split")))
    generation_calls: list[str] = []

    def unexpected_generation(path, *args, **kwargs):
        generation_calls.append(str(path))
        return (write_test_wav(path), fake_generation_report(path))[1]

    monkeypatch.setattr("app.worker.create_music_bed_with_report", unexpected_generation)

    completed = worker.run_job("job_failed_isolation")

    assert completed.status == JobStatus.failed
    assert completed.final_mp3_path is None
    assert generation_calls == []
    assert completed.generation_diagnostics["vocal_isolation"]["status"] == "failed"
    assert "bad split" in completed.generation_diagnostics["vocal_isolation"]["error"]


def test_ace_backing_cleanup_failure_continues_with_uncleaned_bed(monkeypatch):
    monkeypatch.setattr(
        "app.worker.settings",
        Settings(music_generator_backend="ace_step", stem_separator_backend="demucs", backing_vocal_cleanup_enabled=True),
    )
    repository = InMemoryJobRepository()
    storage = MockStorageService()
    raw_path = "users/user_test/raw/upload/voice.webm"
    storage.upload_bytes(raw_path, b"raw-audio", "audio/webm")
    timestamp = now_utc()
    repository.create(
        JobRecord(
            job_id="job_backing_cleanup",
            user_id="user_test",
            creator_mode=CreatorMode.guest,
            genre=Genre.hiphop,
            track_name="Cleanup Demo",
            source_type=SourceType.recording,
            raw_audio_path=raw_path,
            status=JobStatus.queued,
            stage="queued",
            delete_raw_after_mix=False,
            created_at=timestamp,
            updated_at=timestamp,
        )
    )

    monkeypatch.setattr("app.worker.shutil.which", lambda path: path)
    monkeypatch.setattr("app.worker.audio_duration_seconds", lambda *args, **kwargs: 12.0)

    def fake_ffmpeg(args, timeout=None):
        with open(args[-1], "wb") as handle:
            handle.write(b"wav")

    def fake_bed(path, *args, **kwargs):
        write_test_wav(path)
        return fake_generation_report(path, "ace_step")

    worker = MvpAudioWorker(repository, storage_service=storage, ffmpeg_path="ffmpeg")
    monkeypatch.setattr(worker, "_run_ffmpeg", fake_ffmpeg)
    monkeypatch.setattr(worker, "_separate_stem", lambda *args, **kwargs: (_ for _ in ()).throw(VocalIsolationError("no no_vocals stem")))
    monkeypatch.setattr("app.worker.create_music_bed_with_report", fake_bed)

    completed = worker.run_job("job_backing_cleanup")

    assert completed.status == JobStatus.ready
    assert completed.backing_audio_path == "users/user_test/debug/job_backing_cleanup/backing-only.wav"
    assert storage.download_bytes(completed.backing_audio_path).startswith(b"RIFF")


def test_mvp_audio_worker_fails_when_ffmpeg_is_missing(monkeypatch):
    repository = InMemoryJobRepository()
    storage = MockStorageService()
    raw_path = "users/user_test/raw/upload/file.webm"
    storage.upload_bytes(raw_path, b"raw-audio", "audio/webm")
    timestamp = now_utc()
    repository.create(
        JobRecord(
            job_id="job_audio",
            user_id="user_test",
            creator_mode=CreatorMode.guest,
            genre=Genre.rnb,
            track_name="Smooth Demo",
            source_type=SourceType.recording,
            raw_audio_path=raw_path,
            status=JobStatus.queued,
            stage="queued",
            delete_raw_after_mix=True,
            created_at=timestamp,
            updated_at=timestamp,
        )
    )

    monkeypatch.setattr("app.worker.shutil.which", lambda path: None)
    monkeypatch.setattr("app.worker.Path.exists", lambda path: False)

    completed = MvpAudioWorker(repository, storage_service=storage, ffmpeg_path="missing-ffmpeg").run_job("job_audio")

    assert completed.status == JobStatus.failed
    assert completed.error == "FFmpeg is not available"


def test_current_genres_accept_rnb_and_hiphop():
    assert Genre("R&B") == Genre.rnb
    assert Genre("Hip-hop") == Genre.hiphop


def test_procedural_v2_generator_creates_stereo_wav(tmp_path):
    output = tmp_path / "bed.wav"
    from app import worker as worker_module
    original_settings = worker_module.settings
    worker_module.settings = Settings(music_generator_backend="procedural_v2")

    try:
        create_genre_bed(output, Genre.rnb, seconds=0.2, sample_rate=8000)
    finally:
        worker_module.settings = original_settings

    with wave.open(str(output), "rb") as wav:
        assert wav.getnchannels() == 2
        assert wav.getframerate() == 8000
        assert wav.getnframes() > 0


def test_backing_prompt_is_instrumental_and_genre_specific():
    prompt = backing_prompt(Genre.hiphop, 30, {"tempo_bpm": 92})

    assert "Hip-hop" in prompt
    assert "No lead vocals" in prompt
    assert "808s" in prompt
    assert "Keep the beat lower than the vocal" in prompt


def test_genre_prompts_are_style_specific_without_artist_names():
    prompts = {
        genre: backing_prompt(genre, 30)
        for genre in (Genre.pop, Genre.hiphop, Genre.rnb, Genre.acoustic, Genre.cinematic, Genre.rock, Genre.lofi, Genre.piano)
    }

    assert "four-on-the-floor" in prompts[Genre.pop]
    assert "triplet hi-hats" in prompts[Genre.hiphop]
    assert "dark modern R&B" in prompts[Genre.rnb]
    assert "fingerpicked acoustic guitar" in prompts[Genre.acoustic]
    assert "soft low strings" in prompts[Genre.cinematic]
    assert "distorted rhythm guitar" in prompts[Genre.rock]
    assert "vinyl noise" in prompts[Genre.lofi]
    assert "jazz-pop piano" in prompts[Genre.piano]
    forbidden = ("michael", "jackson", "metro", "carti", "weeknd", "ariana", "hans", "zimmer", "metallica", "laufey")
    for prompt in prompts.values():
        assert all(name not in prompt.lower() for name in forbidden)


class StubAceResponse:
    def __init__(self, status_code=200, data=None, content=b"") -> None:
        self.status_code = status_code
        self._data = data or {}
        self.content = content
        self.text = str(self._data)

    def json(self):
        return self._data


def test_ace_step_generator_submits_polls_and_downloads(tmp_path, monkeypatch):
    calls = []

    def fake_post(url, **kwargs):
        calls.append(("post", url, kwargs))
        if "query_result" in url:
            return StubAceResponse(data={"data": [{"task_id": "task_1", "status": 2, "result": "{\"file\":\"task_1.wav\"}"}]})
        return StubAceResponse(data={"task_id": "task_1"})

    def fake_get(url, **kwargs):
        calls.append(("get", url, kwargs))
        return StubAceResponse(content=b"RIFFace-step-audio")

    monkeypatch.setattr(
        "app.worker.settings",
        Settings(
            music_generator_backend="ace_step",
            ace_step_base_url="http://ace.local:8001",
            ace_step_api_key="secret",
            ace_step_timeout_seconds=5,
            ace_step_poll_interval_seconds=0.01,
        ),
    )
    monkeypatch.setattr("app.worker.requests.post", fake_post)
    monkeypatch.setattr("app.worker.requests.get", fake_get)

    output = tmp_path / "bed.wav"
    create_ace_step_bed(output, Genre.rnb, 15)

    assert output.read_bytes() == b"RIFFace-step-audio"
    assert calls[0][0] == "post"
    assert calls[0][2]["headers"]["Authorization"] == "Bearer secret"
    assert calls[0][2]["json"]["audio_format"] == "wav"
    assert any(call[0] == "post" and "query_result" in call[1] for call in calls)
    assert any(call[0] == "get" and "/v1/audio/task_1.wav" in call[1] for call in calls)


def test_music_to_music_forces_ace_step_reference_conditioning(tmp_path, monkeypatch):
    calls = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        if "query_result" in url:
            return StubAceResponse(
                data={"data": [{"task_id": "task_music", "status": 2, "result": '{"file":"task_music.wav"}'}]}
            )
        return StubAceResponse(data={"task_id": "task_music"})

    monkeypatch.setattr(
        "app.worker.settings",
        Settings(
            music_generator_backend="ace_step",
            ace_step_use_source_audio=False,
            ace_step_source_audio_strength=0.3,
            ace_step_timeout_seconds=5,
            ace_step_poll_interval_seconds=0.01,
        ),
    )
    monkeypatch.setattr("app.worker.requests.post", fake_post)
    monkeypatch.setattr(
        "app.worker.requests.get",
        lambda *_args, **_kwargs: StubAceResponse(content=b"RIFFmusic-to-new-music"),
    )
    source = tmp_path / "reference.wav"
    source.write_bytes(b"RIFFreference")
    output = tmp_path / "transformed.wav"

    create_ace_step_bed(
        output,
        Genre.rock,
        15,
        source_audio_path=source,
        timing={"arrangement_mode": "music_to_music", "production_bpm": 96},
    )

    release = calls[0][1]
    assert "src_audio" in release["files"]
    assert release["data"]["task_type"] == "cover"
    assert release["data"]["audio_cover_strength"] == 0.3
    assert release["data"]["lyrics"] == "[Instrumental]"
    assert release["data"]["thinking"] is False
    assert output.read_bytes() == b"RIFFmusic-to-new-music"


def test_ace_step_audio_url_extractor_handles_nested_result():
    data = {"data": [{"status": 2, "result": "{\"file\":\"final.mp3\"}"}]}
    assert extract_ace_audio_url(data) == "final.mp3"


def test_ace_step_payload_uses_language_context_and_guarded_lyrics(monkeypatch):
    timing = {
        "language": "Hinglish",
        "lyrics": "mera dil tumhare bina adhoora hai",
        "production_bpm": 88,
    }
    monkeypatch.setattr(
        "app.worker.settings",
        Settings(music_generator_backend="ace_step", ace_step_send_lyrics=False),
    )

    payload = ace_step_payload(Genre.pop, 30, timing)

    assert "Hinglish" in payload["prompt"]
    assert "mera dil" in payload["prompt"]
    assert payload["lyrics"] == ""

    monkeypatch.setattr(
        "app.worker.settings",
        Settings(music_generator_backend="ace_step", ace_step_send_lyrics=True),
    )

    assert ace_step_payload(Genre.pop, 30, timing)["lyrics"] == "mera dil tumhare bina adhoora hai"


def test_ace_step_failure_can_fallback_to_procedural(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.worker.settings",
        Settings(music_generator_backend="ace_step", ace_step_fallback_to_procedural=True),
    )
    monkeypatch.setattr("app.worker.create_ace_step_bed", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("ACE offline")))

    output = tmp_path / "fallback.wav"
    create_music_bed(output, Genre.pop, "job_ace", seconds=1.0, sample_rate=8000)

    assert output.exists()
    assert output.stat().st_size > 100


def test_ace_step_missing_output_records_fallback_report(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.worker.settings",
        Settings(music_generator_backend="ace_step", ace_step_fallback_to_procedural=True),
    )
    monkeypatch.setattr("app.worker.create_ace_step_bed", lambda *args, **kwargs: None)

    output = tmp_path / "fallback-report.wav"
    report = create_music_bed_with_report(output, Genre.pop, "job_ace_report", seconds=1.0, sample_rate=8000)

    assert output.exists()
    assert report["selected_generator"] == "ace_step"
    assert report["fallback_attempted"] is True
    assert report["fallback_result"] == "succeeded"
    assert report["final_generator_used"] == "procedural_v2"
    assert "ACE-Step" in report["fallback_reason"]
    assert any("procedural_v2 fallback" in warning for warning in report["warnings"])
