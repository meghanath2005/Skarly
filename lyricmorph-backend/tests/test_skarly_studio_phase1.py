import json
import math
from dataclasses import replace
import wave
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import unquote

import numpy as np
import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.config import Settings
from app.main import app
from app.models import MusicSourcePreparation, MusicTransformationQuality, MusicalCompatibilityQuality, SkarlyStudioGenerateRequest, StemSeparationResponse, VocalLeakageQuality
from app.repository import InMemoryJobRepository
from app.services import skarly_studio, training_feedback
from app.storage import LocalFileStorageService
from training import download_fleurs


client = TestClient(app)
AUTH_HEADERS = {"Authorization": "Bearer guest:guest-session"}


def phase1_settings(tmp_path: Path) -> Settings:
    return Settings(
        uploads_dir=str(tmp_path / "uploads"),
        skarly_output_dir=str(tmp_path / "skarly"),
        training_feedback_dir=str(tmp_path / "consented_feedback"),
        training_feedback_manifest=str(tmp_path / "manifests" / "user_feedback.jsonl"),
        ffmpeg_path="ffmpeg",
        mixing_timeout_sec=60,
        music_to_music_verify_generated_vocals=False,
    )


def phase23_settings(tmp_path: Path, generator_backend: str = "procedural_v2") -> Settings:
    return Settings(
        uploads_dir=str(tmp_path / "uploads"),
        skarly_output_dir=str(tmp_path / "skarly"),
        training_feedback_dir=str(tmp_path / "consented_feedback"),
        training_feedback_manifest=str(tmp_path / "manifests" / "user_feedback.jsonl"),
        ffmpeg_path="ffmpeg",
        mixing_timeout_sec=60,
        melody_analyzer_backend="basic_pitch",
        skarly_generator_backend=generator_backend,
        stem_separator_backend="off",
        ace_step_fallback_to_procedural=True,
        require_cuda=False,
        allow_cpu_generation_fallback=True,
    )


def write_wav(path: Path, seconds: float = 4.0, frequency: float = 330.0, amplitude: float = 0.35, sample_rate: int = 22050) -> Path:
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


def write_stereo_full_song_like_wav(path: Path, seconds: float = 4.0, sample_rate: int = 22050) -> Path:
    t = np.linspace(0, seconds, int(sample_rate * seconds), endpoint=False)
    vocal = 0.20 * np.sin(2 * math.pi * 330.0 * t)
    left = vocal + 0.28 * np.sin(2 * math.pi * 146.8 * t) + 0.16 * np.sin(2 * math.pi * 880.0 * t)
    right = vocal + 0.24 * np.sin(2 * math.pi * 196.0 * t + 0.7) - 0.13 * np.sin(2 * math.pi * 740.0 * t)
    stereo = np.column_stack([left, right])
    pcm = (np.clip(stereo, -1.0, 1.0) * 32767).astype(np.int16)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm.tobytes())
    return path


def upload_wav(tmp_path: Path, name: str = "sad-vocal.wav") -> dict:
    wav_path = write_wav(tmp_path / name)
    with wav_path.open("rb") as handle:
        response = client.post("/uploads/audio", files={"file": (name, handle, "audio/wav")})
    assert response.status_code == 200
    return response.json()


def output_path_from_skarly_url(output_root: Path, url: str) -> Path:
    assert url.startswith("/outputs/skarly/")
    relative = unquote(url.removeprefix("/outputs/skarly/"))
    return output_root / relative


def test_skarly_analyze_returns_detected_summary(monkeypatch, tmp_path):
    monkeypatch.setattr(main_module, "settings", phase1_settings(tmp_path))
    upload = upload_wav(tmp_path)

    response = client.post("/v1/skarly/analyze", headers=AUTH_HEADERS, json={"upload_id": upload["upload_id"]})

    assert response.status_code == 200
    data = response.json()
    assert data["job_id"].startswith("skarly_job_")
    assert data["status"] == "analysis_ready"
    assert data["detected"]["language"] == "Hindi"
    assert data["detected"]["mood"]
    assert data["detected"]["vocal_type"] in {"Singing", "Vocal"}
    assert data["detected"]["bpm"] is not None
    assert data["detected"]["key"]
    assert data["detected"]["input_quality"] == "Ready"
    assert data["song_intelligence_map"]["duration_seconds"] == pytest.approx(4.0, abs=0.02)
    assert data["song_intelligence_map"]["language"]["primary"] == "hi"
    assert data["detected"]["song_intelligence_map"] == data["song_intelligence_map"]
    assert data["song_intelligence_map"]["genre_probabilities"]
    assert "Vocal level is usable" in data["detected"]["input_quality_note"]


def test_skarly_input_quality_summary_handles_quiet_and_clipped_vocals():
    quiet = SimpleNamespace(is_silent=False, clipping_detected=False, peak_db=-40.0, passed=True)
    clipped = SimpleNamespace(is_silent=False, clipping_detected=True, peak_db=-1.0, passed=False)

    assert skarly_studio.input_quality_summary(quiet)[0] == "Quiet"
    assert skarly_studio.input_quality_summary(clipped)[0] == "Clipping"


def test_fleurs_manifest_uses_only_the_requested_split(tmp_path):
    language_root = tmp_path / "hi_in"
    for split, name in (("dev", "dev-example.wav"), ("train", "train-example.wav")):
        clips = language_root / "clips" / split
        clips.mkdir(parents=True, exist_ok=True)
        (clips / name).write_bytes(b"audio")
        (language_root / f"{split}.tsv").write_text(f"0\t{name}\n", encoding="utf-8")

    rows = download_fleurs.build_manifest(language_root, language="Hindi", split="train")

    assert len(rows) == 1
    assert rows[0]["audio_path"].endswith("train-example.wav")


def test_skarly_analyze_uses_high_confidence_local_cnn_language(monkeypatch, tmp_path):
    monkeypatch.setattr(main_module, "settings", phase1_settings(tmp_path))
    upload = upload_wav(tmp_path)
    monkeypatch.setattr(
        skarly_studio,
        "predict_with_local_audio_classifier",
        lambda *_args, **_kwargs: skarly_studio.AudioClassifierPrediction(language="English", language_confidence=0.91),
    )

    response = client.post("/v1/skarly/analyze", headers=AUTH_HEADERS, json={"upload_id": upload["upload_id"]})

    assert response.status_code == 200
    detected = response.json()["detected"]
    assert detected["language"] == "English"
    assert detected["language_confidence"] == 0.91
    assert detected["classification_source"] == "local_cnn"


def test_skarly_analyze_uses_genre_cnn_only_for_confident_full_song_inputs(monkeypatch, tmp_path):
    monkeypatch.setattr(main_module, "settings", phase1_settings(tmp_path))
    upload = upload_wav(tmp_path)
    monkeypatch.setattr(
        skarly_studio,
        "predict_with_local_audio_classifier",
        lambda *_args, **_kwargs: skarly_studio.AudioClassifierPrediction(genre="classical", genre_confidence=0.70),
    )

    low_confidence = client.post("/v1/skarly/analyze", headers=AUTH_HEADERS, json={"upload_id": upload["upload_id"]})
    assert low_confidence.status_code == 200
    assert low_confidence.json()["detected"]["genre_hint"] != "classical"

    monkeypatch.setattr(
        skarly_studio,
        "predict_with_local_audio_classifier",
        lambda *_args, **_kwargs: skarly_studio.AudioClassifierPrediction(genre="classical", genre_confidence=0.93),
    )
    high_confidence = client.post("/v1/skarly/analyze", headers=AUTH_HEADERS, json={"upload_id": upload["upload_id"]})
    assert high_confidence.status_code == 200
    assert high_confidence.json()["detected"]["genre_hint"] != "classical"
    assert high_confidence.json()["detected"]["genre_source"] == "audio_heuristic"

    full_song_path = write_stereo_full_song_like_wav(tmp_path / "full-song.wav")
    with full_song_path.open("rb") as handle:
        full_song_upload = client.post("/uploads/audio", files={"file": ("full-song.wav", handle, "audio/wav")})
    assert full_song_upload.status_code == 200
    unapproved_full_song = client.post(
        "/v1/skarly/analyze",
        headers=AUTH_HEADERS,
        json={"upload_id": full_song_upload.json()["upload_id"]},
    )
    assert unapproved_full_song.status_code == 200
    assert unapproved_full_song.json()["detected"]["genre_hint"] != "classical"
    assert unapproved_full_song.json()["detected"]["genre_source"] == "audio_heuristic"

    monkeypatch.setattr(
        skarly_studio,
        "predict_with_local_audio_classifier",
        lambda *_args, **_kwargs: skarly_studio.AudioClassifierPrediction(genre="classical", genre_confidence=0.93, genre_approved=True),
    )
    full_song = client.post(
        "/v1/skarly/analyze",
        headers=AUTH_HEADERS,
        json={"upload_id": full_song_upload.json()["upload_id"]},
    )
    assert full_song.status_code == 200
    assert full_song.json()["detected"]["genre_hint"] == "classical"
    assert full_song.json()["detected"]["genre_source"] == "local_cnn"


def test_skarly_analyze_accepts_signed_raw_upload_path(monkeypatch, tmp_path):
    settings = phase1_settings(tmp_path)
    monkeypatch.setattr(main_module, "settings", settings)
    wav_path = write_wav(tmp_path / "signed-vocal.wav")
    signed = client.post(
        "/v1/uploads/sign",
        headers=AUTH_HEADERS,
        json={
            "filename": "signed-vocal.wav",
            "content_type": "audio/wav",
            "size_bytes": wav_path.stat().st_size,
            "source_type": "localUpload",
        },
    )
    assert signed.status_code == 200
    signed_payload = signed.json()
    main_module.storage.upload_bytes(signed_payload["raw_audio_path"], wav_path.read_bytes(), "audio/wav")

    response = client.post(
        "/v1/skarly/analyze",
        headers=AUTH_HEADERS,
        json={
            "upload_id": signed_payload["upload_id"],
            "raw_audio_path": signed_payload["raw_audio_path"],
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["upload_id"].startswith("upload_")
    assert data["detected"]["language"] == "Hindi"
    assert Path(settings.uploads_dir, data["upload_id"], "metadata.json").exists()


def test_skarly_profiles_wide_stereo_upload_as_full_song(tmp_path):
    wav_path = write_stereo_full_song_like_wav(tmp_path / "full-song.wav")

    profile = skarly_studio.profile_input_audio(wav_path)

    assert profile.source_profile == "full_song"
    assert profile.vocal_type == "Singing / Full Song"


def test_skarly_procedural_backings_are_distinct(tmp_path):
    backings = []
    for index in range(1, 6):
        output_path = tmp_path / f"backing_{index}.wav"
        skarly_studio.write_placeholder_backing(output_path, seconds=5.0, bpm=122, version_index=index)
        audio, _sample_rate = skarly_studio.read_wav_float(output_path)
        backings.append(audio[:, 0])

    correlations = []
    for left_index in range(len(backings)):
        for right_index in range(left_index + 1, len(backings)):
            left = backings[left_index]
            right = backings[right_index][: len(left)]
            correlations.append(float(np.corrcoef(left, right)[0, 1]))

    assert max(correlations) < 0.85


def test_skarly_hindi_version_plans_use_distinct_indian_friendly_directions():
    detected = skarly_studio.SkarlyDetected(
        language="Hindi",
        mood="Romantic",
        bpm=96,
        key="D minor",
        timing_summary="4 vocal phrases; keep the first 1.2s sparse, place fills in roughly 0.8s phrase gaps.",
    )

    plans = skarly_studio.build_version_plans(detected=detected, duration=30, lyrics=None)

    assert [plan.name for plan in plans] == list(skarly_studio.HINDI_BOLLYWOOD_VERSION_NAMES)
    assert [plan.style_family for plan in plans] == list(skarly_studio.DEFAULT_HINDI_PRODUCER_PROFILE_IDS)
    assert all("uploaded Hindi vocal" in plan.prompt for plan in plans)
    assert any("acoustic guitar" in plan.prompt for plan in plans)
    assert any("harmonium" in plan.prompt for plan in plans)
    assert any("dhol-led" in plan.prompt for plan in plans)
    assert all("Timing map:" in plan.prompt for plan in plans)
    assert all("between vocal phrases" in plan.prompt for plan in plans)
    assert all("No generated singing" in plan.prompt for plan in plans)
    assert all("Hard producer blueprint:" in plan.prompt for plan in plans)
    assert all(plan.blueprint for plan in plans)
    for left_index, left in enumerate(plans):
        for right in plans[left_index + 1 :]:
            differences = sum(
                left.blueprint[field] != right.blueprint[field]
                for field in left.blueprint
            )
            assert differences >= 4


def test_skarly_hindi_defaults_and_user_replacements_use_exactly_five_profiles():
    bollywood = skarly_studio.SkarlyDetected(
        language="Hindi",
        mood="Romantic",
        genre_hint="Bollywood",
        bpm=96,
        key="D minor",
    )
    bollywood_plans = skarly_studio.build_version_plans(detected=bollywood, duration=120, lyrics=None)
    assert [plan.name for plan in bollywood_plans] == list(skarly_studio.HINDI_BOLLYWOOD_VERSION_NAMES)
    assert [plan.style_family for plan in bollywood_plans] == list(skarly_studio.DEFAULT_HINDI_PRODUCER_PROFILE_IDS)

    replacement_ids = ["ghazal", "rock", "edm", "lofi", "rnb_urban"]
    replacement_plans = skarly_studio.build_version_plans(
        detected=bollywood,
        duration=120,
        lyrics=None,
        producer_profile_ids=replacement_ids,
    )
    assert [plan.name for plan in replacement_plans] == ["Ghazal", "Rock", "EDM", "Lo-fi", "R&B Urban"]
    assert [plan.style_family for plan in replacement_plans] == replacement_ids
    assert all(plan.instruments for plan in replacement_plans)
    assert all("Hard producer blueprint:" in plan.prompt for plan in replacement_plans)

    with pytest.raises(ValueError, match="Exactly five"):
        skarly_studio.resolve_producer_profiles(replacement_ids[:4])
    with pytest.raises(ValueError, match="must be unique"):
        skarly_studio.resolve_producer_profiles(["ghazal", "ghazal", "edm", "lofi", "rock"])
    with pytest.raises(ValueError, match="Unsupported producer profile"):
        skarly_studio.resolve_producer_profiles(["ghazal", "rock", "edm", "lofi", "unknown"])


def test_skarly_non_hindi_version_plans_keep_general_directions():
    detected = skarly_studio.SkarlyDetected(language="English", mood="Romantic", bpm=96, key="D minor")

    plans = skarly_studio.build_version_plans(detected=detected, duration=30, lyrics=None)

    assert [plan.name for plan in plans] == list(skarly_studio.VERSION_NAMES)


def test_skarly_long_song_duration_is_preserved_or_rejected_without_cropping():
    assert skarly_studio.studio_generation_duration(120, 150) == 120
    with pytest.raises(ValueError, match="No audio was cropped"):
        skarly_studio.studio_generation_duration(182, 150)
    assert skarly_studio.studio_generation_duration(None, 150) == 12


def test_skarly_long_confirmation_uses_the_complete_vocal(tmp_path):
    source = write_wav(tmp_path / "two-minute-vocal.wav")

    analysis_source, warning, long_audio = skarly_studio.skarly_analysis_source(
        source,
        upload_id="upload_test",
        uploads_dir=tmp_path / "uploads",
        duration_seconds=120,
        ffmpeg_path="ffmpeg",
    )

    assert analysis_source == source
    assert long_audio is True
    assert warning is not None
    assert "complete vocal" in warning
    assert not (tmp_path / "uploads" / "upload_test" / "skarly_analysis_preview.wav").exists()


def test_long_vocal_detail_windows_cover_the_beginning_middle_and_end():
    sample_rate = 10
    # Each region has a distinct value so the bounded detailed analysis can be
    # checked without running expensive pitch extraction in this unit test.
    mono = np.concatenate([
        np.full(100, 0.1, dtype=np.float32),
        np.full(100, 0.5, dtype=np.float32),
        np.full(100, 0.9, dtype=np.float32),
    ])

    detail, note = skarly_studio.vocal_analysis._representative_detail_audio(mono, sample_rate)

    assert len(detail) == int(skarly_studio.vocal_analysis.MAX_REPRESENTATIVE_DETAIL_SECONDS * sample_rate)
    assert np.isclose(float(detail[0]), 0.1)
    assert np.isclose(float(detail[len(detail) // 2]), 0.5)
    assert np.isclose(float(detail[-1]), 0.9)
    assert note is not None
    assert "beginning, middle, and end" in note


def test_skarly_long_generation_skips_optional_basic_pitch_but_not_song_analysis():
    assert skarly_studio.should_skip_melody_analysis(120, "basic_pitch") is True
    assert skarly_studio.should_skip_melody_analysis(75, "basic_pitch") is False
    assert skarly_studio.should_skip_melody_analysis(120, "off") is False


def test_skarly_version_plans_have_unique_style_families_and_reproducible_seeds():
    detected = skarly_studio.SkarlyDetected(language="Hindi", mood="Romantic", bpm=108, key="Bb minor")

    first = skarly_studio.build_version_plans(detected=detected, duration=120, lyrics="a short lyric")
    second = skarly_studio.build_version_plans(detected=detected, duration=120, lyrics="a short lyric")

    assert len({plan.style_family for plan in first}) == 5
    assert len({plan.seed for plan in first}) == 5
    assert [plan.seed for plan in first] == [plan.seed for plan in second]
    assert all("verse 1, hook, verse 2, bridge, final hook" in plan.prompt for plan in first)


def test_skarly_preferred_style_is_ranked_first_with_a_fresh_generation_seed():
    detected = skarly_studio.SkarlyDetected(language="Hindi", mood="Romantic", bpm=108, key="Bb minor")

    first = skarly_studio.build_version_plans(
        detected=detected,
        duration=120,
        lyrics="a short lyric",
        preferred_style_families=["cinematic_urban"],
        variation_nonce="skarly_job_first",
    )
    second = skarly_studio.build_version_plans(
        detected=detected,
        duration=120,
        lyrics="a short lyric",
        preferred_style_families=["cinematic_urban"],
        variation_nonce="skarly_job_second",
    )

    assert first[0].style_family == "cinematic_urban"
    assert len({plan.style_family for plan in first}) == 5
    assert len({plan.seed for plan in first}) == 5
    assert [plan.seed for plan in first] != [plan.seed for plan in second]
    assert "Creator preference signal" in first[0].prompt


def test_skarly_adaptive_mixer_raises_a_quiet_music_bed(tmp_path):
    vocal_path = write_wav(tmp_path / "vocal.wav", amplitude=0.70)
    backing_path = write_wav(tmp_path / "quiet-backing.wav", amplitude=0.04)

    adaptive = skarly_studio.adaptive_mix_settings(
        vocal_path,
        backing_path,
        skarly_studio.MIXING_PRESETS["vocal_up"],
    )

    assert adaptive.backing_volume > skarly_studio.MIXING_PRESETS["vocal_up"]["backing_volume"]
    assert adaptive.backing_volume >= 0.95
    assert adaptive.vocal_volume < skarly_studio.MIXING_PRESETS["vocal_up"]["vocal_volume"]
    assert adaptive.ducking == "medium"
    assert "quiet relative" in adaptive.note


def test_skarly_vocal_up_preset_keeps_the_music_bed_audible():
    preset = skarly_studio.MIXING_PRESETS["vocal_up"]
    vocal_advantage_db = 20 * math.log10(preset["vocal_volume"] / preset["backing_volume"])

    assert preset["ducking"] == "medium"
    assert vocal_advantage_db < 3.5


def test_skarly_beat_forward_preset_lifts_music_without_burying_the_vocal():
    preset = skarly_studio.MIXING_PRESETS["beat_up"]

    assert preset["backing_volume"] > preset["vocal_volume"]
    assert preset["ducking"] == "light"
    assert 1.5 < 20 * math.log10(preset["backing_volume"] / preset["vocal_volume"]) < 3.0


def test_skarly_beat_forward_recovers_a_quiet_beat_from_a_loud_vocal(tmp_path):
    vocal_path = write_wav(tmp_path / "vocal.wav", amplitude=0.70)
    backing_path = write_wav(tmp_path / "quiet-backing.wav", amplitude=0.04)

    adaptive = skarly_studio.adaptive_mix_settings(
        vocal_path,
        backing_path,
        skarly_studio.MIXING_PRESETS["beat_up"],
    )

    assert adaptive.backing_volume == 1.30
    assert adaptive.vocal_volume == 0.88
    assert adaptive.ducking == "medium"
    assert "raised the music bed" in adaptive.note


def test_frequency_aware_mix_filter_ducks_vocal_bands_without_ducking_bass():
    adaptive = skarly_studio.AdaptiveMix(
        vocal_volume=1.05,
        backing_volume=0.9,
        ducking="medium",
        note="test",
    )
    graph = skarly_studio.frequency_aware_mix_filter(
        adaptive,
        skarly_studio.ducking_parameters("medium"),
    )

    assert "acrossover=split='180 6500':order=8th[back_low][back_presence][back_air]" in graph
    assert "[back_presence][vocal_presence_sc]sidechaincompress" in graph
    assert "[back_air][vocal_air_sc]sidechaincompress" in graph
    assert graph.count("sidechaincompress") == 2
    assert "[back_low][back_presence_ducked][back_air_ducked]amix=inputs=3" in graph
    assert "[back_low][vocal" not in graph


def test_long_song_mixing_timeout_scales_from_decoded_duration(monkeypatch, tmp_path):
    vocal = tmp_path / "vocal.wav"
    backing = tmp_path / "backing.wav"
    monkeypatch.setattr(
        skarly_studio,
        "safe_duration_seconds",
        lambda path: 220.992 if path in {vocal, backing} else None,
    )

    timeout = skarly_studio.effective_mixing_timeout(
        120,
        vocal_path=vocal,
        backing_path=backing,
    )

    assert timeout == 392


def test_short_song_mixing_timeout_keeps_configured_floor(monkeypatch, tmp_path):
    monkeypatch.setattr(skarly_studio, "safe_duration_seconds", lambda _path: 10.0)

    timeout = skarly_studio.effective_mixing_timeout(
        120,
        vocal_path=tmp_path / "vocal.wav",
        backing_path=tmp_path / "backing.wav",
    )

    assert timeout == 120


def test_frequency_aware_air_ducking_is_gentler_than_presence_ducking():
    presence = skarly_studio.ducking_parameters("strong")
    air = skarly_studio.air_ducking_parameters("strong")

    assert float(air["threshold"]) > float(presence["threshold"])
    assert float(air["ratio"]) < float(presence["ratio"])


def test_skarly_api_defaults_to_balanced_mix_for_an_audible_music_bed():
    request = SkarlyStudioGenerateRequest(upload_id="upload-1")

    assert request.mix_preset == "balanced"


def test_skarly_adaptive_mixer_measures_float_wav_from_ace_step(tmp_path):
    import soundfile as sf

    path = tmp_path / "ace-step-float.wav"
    sf.write(path, np.full((22050, 2), 0.10, dtype=np.float32), 22050, subtype="FLOAT")

    assert skarly_studio.audio_rms_db(path) is not None


def test_skarly_duplicate_backing_detector_rerolls_only_the_same_render(tmp_path):
    first = tmp_path / "first.wav"
    skarly_studio.write_placeholder_backing(first, seconds=5.0, bpm=112, version_index=1)
    duplicate = tmp_path / "duplicate.wav"
    duplicate.write_bytes(first.read_bytes())
    distinct = tmp_path / "distinct.wav"
    skarly_studio.write_placeholder_backing(distinct, seconds=5.0, bpm=112, version_index=4)

    is_duplicate, detail = skarly_studio.backing_is_near_duplicate(duplicate, [first])
    is_distinct, _ = skarly_studio.backing_is_near_duplicate(distinct, [first])

    assert is_duplicate is True
    assert "waveform correlation" in str(detail)
    assert is_distinct is False


def test_skarly_duplicate_detector_catches_phase_shifted_arrangement(tmp_path):
    first = write_wav(tmp_path / "first.wav", seconds=4.0, frequency=330.0)
    audio, sample_rate = skarly_studio.read_wav_float(first)
    phase_shift = max(1, int(sample_rate / (4 * 330)))
    shifted = tmp_path / "phase-shifted.wav"
    skarly_studio.write_float_wav(shifted, np.roll(audio, phase_shift, axis=0), sample_rate)

    original = audio[:, 0] - float(np.mean(audio[:, 0]))
    candidate_audio, _ = skarly_studio.read_wav_float(shifted)
    candidate = candidate_audio[:, 0] - float(np.mean(candidate_audio[:, 0]))
    raw_correlation = float(np.dot(original, candidate) / (np.linalg.norm(original) * np.linalg.norm(candidate)))
    is_duplicate, detail = skarly_studio.backing_is_near_duplicate(shifted, [first])

    assert raw_correlation < 0.1
    assert is_duplicate is True
    assert "arrangement fingerprint" in str(detail)


def test_skarly_reroll_plan_changes_seed_and_musical_direction():
    original = skarly_studio.VersionPlan("Indie", "indie arrangement", "no vocals", "indie_pop", 40501)

    rerolled = skarly_studio.reroll_version_plan(original, 1)

    assert rerolled.seed != original.seed
    assert "Diversity reroll" in rerolled.prompt


def test_skarly_timing_summary_uses_phrase_boundaries():
    class Report:
        duration_seconds = 12
        phrase_boundaries = [
            {"start_seconds": 1.2, "end_seconds": 2.0},
            {"start_seconds": 2.8, "end_seconds": 3.9},
            {"start_seconds": 5.0, "end_seconds": 6.4},
        ]

    summary = skarly_studio.timing_summary_from_report(Report())

    assert summary == "3 vocal phrases; keep the first 1.2s sparse, place fills in roughly 0.9s phrase gaps."


def test_trained_audio_head_is_applied_as_a_cautious_phrase_delivery_prior():
    intelligence = skarly_studio.SongAudioIntelligence(
        singing_speech="humming",
        singing_speech_confidence=0.87,
        requires_confirmation=True,
        trained_heads={"singing_speech": True},
    )

    phrases = skarly_studio.apply_global_delivery_prior(
        [{"phrase": 1, "delivery": "sung_candidate"}],
        intelligence,
    )

    assert phrases[0]["delivery"] == "humming_candidate"
    assert phrases[0]["delivery_confidence"] == 0.87
    assert phrases[0]["delivery_source"] == "trained_global_audio_head_prior"
    assert phrases[0]["delivery_requires_confirmation"] is True


def test_arrangement_map_passes_motif_rhythm_and_energy_cues_to_generator():
    result = skarly_studio.arrangement_map(
        [
            {
                "name": "hook",
                "start_seconds": 12.0,
                "end_seconds": 24.0,
                "motif_ids": ["motif_1"],
                "lyric_motif_ids": ["lyric_motif_1"],
                "rhythmic_density_onsets_per_second": 2.8,
                "mean_relative_energy": 0.78,
            }
        ],
        30.0,
    )

    assert "repeated vocal motif" in result
    assert "repeated lyric refrain" in result
    assert "active rhythm" in result
    assert "high energy" in result


def test_timestamped_whisper_repetition_enriches_phrases_and_sections():
    transcription = skarly_studio.TranscriptionResult(
        language="Hindi",
        text="dil mera dil mera naya safar",
        segments=(
            {"start_seconds": 0.2, "end_seconds": 1.2, "text": "dil mera"},
            {"start_seconds": 2.2, "end_seconds": 3.2, "text": "dil mera"},
            {"start_seconds": 4.2, "end_seconds": 5.2, "text": "naya safar"},
        ),
        status="available",
    )
    phrases = [
        {"phrase": 1, "start_seconds": 0.0, "end_seconds": 1.5, "delivery": "sung_candidate"},
        {"phrase": 2, "start_seconds": 2.0, "end_seconds": 3.5, "delivery": "sung_candidate"},
        {"phrase": 3, "start_seconds": 4.0, "end_seconds": 5.5, "delivery": "sung_candidate"},
    ]
    sections = [
        {
            "name": "hook",
            "start_seconds": 0.0,
            "end_seconds": 3.8,
            "label_confidence": 0.7,
            "label_evidence": ["repeated_melodic_motif"],
        },
        {
            "name": "outro",
            "start_seconds": 3.8,
            "end_seconds": 6.0,
            "label_confidence": 0.4,
            "label_evidence": [],
        },
    ]

    motifs, enriched_phrases, enriched_sections, structure = (
        skarly_studio.apply_transcript_structure_evidence(
            phrases,
            sections,
            {"method": "test"},
            transcription,
        )
    )

    assert len(motifs) == 1
    assert motifs[0]["occurrence_count"] == 2
    assert enriched_phrases[0]["lyric_motif_ids"] == ["lyric_motif_1"]
    assert enriched_phrases[1]["repeated_lyrics"] is True
    assert enriched_phrases[2]["repeated_lyrics"] is False
    assert "lyrical_repetition" in enriched_sections[0]["label_evidence"]
    assert enriched_sections[0]["label_confidence"] == 0.8
    assert structure["transcription_timing_available"] is True
    assert structure["lyrical_repetition_group_count"] == 1


def test_skarly_whisper_transcription_uses_utf8_for_hindi_output(monkeypatch, tmp_path):
    audio_path = write_wav(tmp_path / "hindi-vocal.wav")
    captured: dict = {}

    monkeypatch.setattr(skarly_studio, "command_is_available", lambda _command: True)

    class Completed:
        returncode = 0
        stderr = ""

    def fake_run(args, **kwargs):
        captured.update(kwargs)
        output_dir = Path(args[args.index("--output_dir") + 1])
        (output_dir / "hindi-vocal.json").write_text(
            json.dumps({"language": "hi", "text": "नमस्ते दुनिया"}, ensure_ascii=False),
            encoding="utf-8",
        )
        return Completed()

    monkeypatch.setattr(skarly_studio.subprocess, "run", fake_run)

    result = skarly_studio.transcribe_with_whisper(
        audio_path,
        whisper_path="whisper",
        whisper_model="base",
        timeout_sec=10,
    )

    assert captured["encoding"] == "utf-8"
    assert captured["errors"] == "replace"
    assert result.status == "available"
    assert result.language == "Hindi"
    assert result.text == "नमस्ते दुनिया"


def test_skarly_ace_api_adapter_reads_legacy_result_and_preserves_hindi_metas(monkeypatch, tmp_path):
    output = tmp_path / "ace-backing.wav"
    release_payload: dict = {}

    class Response:
        def __init__(self, payload=None, content=b""):
            self.status_code = 200
            self._payload = payload or {}
            self.content = content
            self.text = ""

        def json(self):
            return self._payload

    class Requests:
        def post(self, url, **kwargs):
            if url.endswith("release_task"):
                release_payload.update(kwargs["json"])
                return Response({"data": {"task_id": "task-hindi"}})
            return Response({
                "data": [{
                    "task_id": "task-hindi",
                    "status": 1,
                    "result": json.dumps([{"file": "/v1/audio?path=generated.wav", "status": 1}]),
                }],
            })

        def get(self, url, **_kwargs):
            assert url == "http://127.0.0.1:8001/v1/audio?path=generated.wav"
            return Response(content=b"RIFFfakewav")

    monkeypatch.setattr(skarly_studio, "requests", Requests())
    skarly_studio.generate_ace_step_backing(
        output_path=output,
        plan=skarly_studio.VersionPlan("Hindi test", "instrumental Hindi backing", "no vocals"),
        seconds=12,
        base_url="http://127.0.0.1:8001",
        api_key=None,
        timeout_seconds=5,
        download_timeout_seconds=5,
        poll_interval_seconds=0,
        infer_step=8,
        guidance_scale=1,
        max_duration_seconds=30,
        bpm=115,
        key="Bb minor",
        language="Hindi",
        direct_enabled=False,
        repo_dir=None,
        python_path=None,
    )

    assert output.read_bytes() == b"RIFFfakewav"
    assert release_payload["bpm"] == 115
    assert release_payload["key_scale"] == "Bb minor"
    assert release_payload["vocal_language"] == "hi"
    assert release_payload["inference_steps"] == 8
    assert release_payload["use_cot_caption"] is False
    assert release_payload["batch_size"] == 1
    assert release_payload["use_random_seed"] is False
    assert release_payload["seed"] > 0


def test_skarly_ace_api_adapter_can_condition_an_instrumental_on_the_uploaded_vocal(monkeypatch, tmp_path):
    output = tmp_path / "ace-backing.wav"
    vocal = write_wav(tmp_path / "vocal.wav", seconds=2.0)
    release_payload: dict = {}

    class Response:
        status_code = 200
        text = ""

        def __init__(self, payload=None, content=b""):
            self._payload = payload or {}
            self.content = content

        def json(self):
            return self._payload

    class Requests:
        def post(self, url, **kwargs):
            if url.endswith("release_task"):
                release_payload.update(kwargs["data"])
                name, stream, content_type = kwargs["files"]["ctx_audio"]
                assert name == "vocal.wav"
                assert content_type == "audio/wav"
                assert stream.read(4) == b"RIFF"
                return Response({"data": {"task_id": "task-source"}})
            return Response({"data": [{"task_id": "task-source", "status": 1, "result": {"audio_url": "/v1/audio?path=generated.wav"}}]})

        def get(self, _url, **_kwargs):
            return Response(content=b"RIFFsourcewav")

    monkeypatch.setattr(skarly_studio, "requests", Requests())
    skarly_studio.generate_ace_step_backing(
        output_path=output,
        plan=skarly_studio.VersionPlan("Hindi test", "instrumental Hindi backing", "no vocals"),
        seconds=12,
        base_url="http://127.0.0.1:8001",
        api_key=None,
        timeout_seconds=5,
        download_timeout_seconds=5,
        poll_interval_seconds=0,
        infer_step=8,
        guidance_scale=1,
        max_duration_seconds=30,
        bpm=115,
        key="Bb minor",
        language="Hindi",
        source_audio_path=vocal,
        use_source_audio=True,
        source_task_type="unsupported-task",
        source_audio_strength=1.3,
        direct_enabled=True,
        repo_dir=None,
        python_path=None,
    )

    assert output.read_bytes() == b"RIFFsourcewav"
    assert release_payload["task_type"] == "cover"
    assert release_payload["audio_cover_strength"] == 0.8
    assert release_payload["lyrics"] == "[Instrumental]"


def test_skarly_procedural_backing_changes_with_detected_key(tmp_path):
    first = tmp_path / "a-minor.wav"
    second = tmp_path / "bb-minor.wav"
    skarly_studio.write_placeholder_backing(first, seconds=5.0, bpm=115, version_index=1, key="A minor", mood="Sad / Emotional", energy="Medium")
    skarly_studio.write_placeholder_backing(second, seconds=5.0, bpm=115, version_index=1, key="Bb minor", mood="Sad / Emotional", energy="Medium")
    first_audio, _ = skarly_studio.read_wav_float(first)
    second_audio, _ = skarly_studio.read_wav_float(second)

    correlation = float(np.corrcoef(first_audio[:, 0], second_audio[:, 0])[0, 1])

    assert correlation < 0.95


def test_skarly_generate_returns_five_vocal_forward_versions(monkeypatch, tmp_path):
    settings = phase1_settings(tmp_path)
    monkeypatch.setattr(main_module, "settings", settings)
    upload = upload_wav(tmp_path)

    response = client.post(
        "/v1/skarly/generate",
        headers=AUTH_HEADERS,
        json={
            "upload_id": upload["upload_id"],
            "language": "Hindi",
            "mood": "Sad / Emotional",
            "genre_override": "R&B",
            "training_opt_in": True,
            "mix_preset": "vocal_up",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["job_id"].startswith("skarly_job_")
    assert data["mix_preset"] == "vocal_up"
    assert data["detected"]["language"] == "Hindi"
    assert data["detected"]["mood"] == "Sad / Emotional"
    assert data["detected"]["genre_hint"] == "R&B"
    assert data["detected"]["genre_source"] == "user_confirmed"
    assert [version["name"] for version in data["versions"]] == list(skarly_studio.HINDI_BOLLYWOOD_VERSION_NAMES)
    assert len(data["versions"]) == 5
    assert all("Genre direction: R&B" in version["prompt"] for version in data["versions"])
    feedback_rows = [json.loads(line) for line in Path(settings.training_feedback_manifest).read_text(encoding="utf-8").splitlines()]
    assert len(feedback_rows) == 1
    assert feedback_rows[0]["language"] == "Hindi"
    assert feedback_rows[0]["genre"] == "R&B"
    assert feedback_rows[0]["rights_confirmed"] is True
    assert Path(feedback_rows[0]["audio_path"]).is_file()

    output_root = Path(settings.skarly_output_dir)
    for index, version in enumerate(data["versions"], start=1):
        backing = output_path_from_skarly_url(output_root, version["backing_url"])
        final_mix = output_path_from_skarly_url(output_root, version["final_mix_url"])
        assert backing.name == f"backing_{index}.wav"
        assert final_mix.name in {f"final_mix_{index}.mp3", f"final_mix_{index}.wav"}
        assert backing.exists()
        assert final_mix.exists()
        assert version["input_vocal_url"].startswith("/outputs/skarly/")
        assert len(version["waveforms"]["input_vocal"]) > 20
        assert len(version["waveforms"]["backing"]) > 20
        assert len(version["waveforms"]["final_mix"]) > 20
        assert all(0 <= peak <= 1 for peak in version["waveforms"]["final_mix"])


def test_skarly_music_to_music_mode_returns_instrumental_versions_without_vocal_mix(monkeypatch, tmp_path):
    settings = phase1_settings(tmp_path)
    monkeypatch.setattr(main_module, "settings", settings)
    upload = upload_wav(tmp_path)

    response = client.post(
        "/v1/skarly/generate",
        headers=AUTH_HEADERS,
        json={
            "upload_id": upload["upload_id"],
            "arrangement_mode": "music_to_music",
            "preserve_original_vocal": False,
            "reference_strength": 0.35,
            "language": "Hindi",
            "mood": "Romantic",
        },
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["source_preparation"]["detected_mode"] == "instrumental"
    assert data["source_preparation"]["vocal_preserved"] is False
    assert data["vocal_url"] is None
    assert all(version["final_mix_url"] == version["backing_url"] for version in data["versions"])
    assert all("genuinely new instrumental transformation" in version["prompt"] for version in data["versions"])
    assert all("Instrumental-only output" in version["mix_note"] for version in data["versions"])


def test_music_to_music_full_song_is_separated_before_reference_conditioning(monkeypatch, tmp_path):
    settings = replace(
        phase1_settings(tmp_path),
        stem_separator_backend="demucs",
        skarly_generator_backend="ace_step",
        require_cuda=False,
        allow_cpu_generation_fallback=True,
        ace_step_fallback_to_procedural=False,
        music_to_music_verify_generated_vocals=True,
    )
    monkeypatch.setattr(main_module, "settings", settings)
    upload = upload_wav(tmp_path, name="full-song-used-for-music-to-music.wav")
    prepared_root = Path(settings.skarly_output_dir) / "prepared-music-reference"
    clean_instrumental = write_wav(prepared_root / "no-vocals.wav", frequency=146.8)
    separated_vocal = write_wav(prepared_root / "vocals.wav", frequency=330.0, amplitude=0.2)

    monkeypatch.setattr(
        skarly_studio,
        "profile_input_audio",
        lambda _path: skarly_studio.InputProfile(
            source_profile="full_song",
            vocal_type="sung_vocal",
            energy="medium",
            confidence=0.98,
        ),
    )
    preparation_calls: list[dict] = []

    def fake_prepare_music_source(**kwargs):
        preparation_calls.append(kwargs)
        return MusicSourcePreparation(
            requested_mode=kwargs["requested_mode"],
            detected_mode="full_song",
            separation_status="completed",
            vocal_detected=True,
            vocal_preserved=kwargs["preserve_original_vocal"],
            detection_confidence=0.98,
            source_audio_path=kwargs["source_audio_path"],
            instrumental_audio_path=str(clean_instrumental),
            instrumental_audio_url=kwargs["url_for_path"](str(clean_instrumental)),
            vocal_audio_path=str(separated_vocal),
            vocal_audio_url=kwargs["url_for_path"](str(separated_vocal)),
            vocal_leakage_quality=VocalLeakageQuality(status="passed", passed=True, analysed_frames=8),
        )

    monkeypatch.setattr(skarly_studio.music_source, "prepare_music_source", fake_prepare_music_source)
    conditioned_sources: list[Path] = []

    def fake_ace_step_backing(*, output_path, source_audio_path, seconds, bpm, key, version_index=1, **kwargs):
        conditioned_sources.append(Path(source_audio_path))
        skarly_studio.write_placeholder_backing(
            output_path,
            seconds=seconds,
            bpm=bpm,
            key=key,
            version_index=len(conditioned_sources),
        )

    monkeypatch.setattr(skarly_studio, "generate_ace_step_backing", fake_ace_step_backing)
    cleanup_settings: list[bool] = []

    def passing_transformation_quality(*, settings, **kwargs):
        cleanup_settings.append(settings.music_to_music_clean_generated_vocals)
        return MusicTransformationQuality(
            hashes_differ=True,
            duration_match=True,
            original_enough=True,
            vocal_check_status="removed",
            vocal_leakage_detected=False,
            passed=True,
        )

    monkeypatch.setattr(
        skarly_studio.music_transform_quality,
        "assess_transformation",
        passing_transformation_quality,
    )
    monkeypatch.setattr(skarly_studio, "arrangement_similarity_rejection_reason", lambda *args, **kwargs: None)

    response = client.post(
        "/v1/skarly/generate",
        headers=AUTH_HEADERS,
        json={
            "upload_id": upload["upload_id"],
            "arrangement_mode": "music_to_music",
            "preserve_original_vocal": False,
            "reference_strength": 0.35,
            "language": "Hindi",
            "mood": "Romantic",
        },
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert preparation_calls[0]["requested_mode"] == "full_song"
    assert preparation_calls[0]["preserve_original_vocal"] is False
    assert len(conditioned_sources) == 5
    assert all(path == clean_instrumental for path in conditioned_sources)
    assert cleanup_settings == [True] * 5
    assert data["source_preparation"]["separation_status"] == "completed"
    assert data["source_preparation"]["vocal_preserved"] is False
    assert data["vocal_url"] is None
    assert all(
        version["input_vocal_url"] == data["source_preparation"]["vocal_audio_url"]
        for version in data["versions"]
    )
    assert all(version["waveforms"]["input_vocal"] for version in data["versions"])
    assert all(version["final_mix_url"] == version["backing_url"] for version in data["versions"])


@pytest.mark.parametrize("arrangement_mode", ["full_song", "music_to_music"])
def test_music_modes_generate_from_clean_reference_and_preserve_singer(monkeypatch, tmp_path, arrangement_mode):
    settings = replace(
        phase1_settings(tmp_path),
        stem_separator_backend="demucs",
        skarly_generator_backend="ace_step",
        require_cuda=False,
        allow_cpu_generation_fallback=True,
        ace_step_fallback_to_procedural=False,
        music_to_music_verify_generated_vocals=False,
    )
    monkeypatch.setattr(main_module, "settings", settings)
    upload = upload_wav(tmp_path, name="complete-song.wav")
    prepared_root = Path(settings.skarly_output_dir) / "prepared-source"
    clean_instrumental = write_wav(prepared_root / "prepared-instrumental.wav", frequency=146.8)
    separated_vocal = write_wav(prepared_root / "separated-vocal.wav", frequency=330.0, amplitude=0.2)

    def fake_prepare_music_source(**kwargs):
        return MusicSourcePreparation(
            requested_mode="full_song",
            detected_mode="full_song",
            separation_status="completed",
            vocal_detected=True,
            vocal_preserved=True,
            detection_confidence=0.98,
            source_audio_path=kwargs["source_audio_path"],
            instrumental_audio_path=str(clean_instrumental),
            instrumental_audio_url=kwargs["url_for_path"](str(clean_instrumental)),
                vocal_audio_path=str(separated_vocal),
                vocal_audio_url=kwargs["url_for_path"](str(separated_vocal)),
                vocal_leakage_quality=VocalLeakageQuality(status="passed", passed=True, analysed_frames=8),
                warnings=[],
        )

    monkeypatch.setattr(skarly_studio.music_source, "prepare_music_source", fake_prepare_music_source)
    conditioned_sources: list[Path] = []

    def fake_ace_step_backing(*, output_path, source_audio_path, seconds, bpm, key, version_index=1, **kwargs):
        conditioned_sources.append(Path(source_audio_path))
        skarly_studio.write_placeholder_backing(
            output_path,
            seconds=seconds,
            bpm=bpm,
            key=key,
            version_index=len(conditioned_sources),
        )

    monkeypatch.setattr(skarly_studio, "generate_ace_step_backing", fake_ace_step_backing)
    compatibility_calls = 0

    def compatibility_report(**kwargs):
        nonlocal compatibility_calls
        compatibility_calls += 1
        if compatibility_calls == 1:
            return MusicalCompatibilityQuality(
                target_bpm=88,
                output_bpm=104,
                tempo_delta_bpm=16,
                tempo_tolerance_bpm=3,
                tempo_match=False,
                target_key="F minor",
                output_key="F# minor",
                output_key_confidence=0.8,
                key_match=False,
                passed=False,
                warnings=["mock vocal mismatch"],
            )
        return MusicalCompatibilityQuality(
            target_bpm=88,
            output_bpm=88,
            tempo_delta_bpm=0,
            tempo_tolerance_bpm=3,
            tempo_match=True,
            target_key="F minor",
            output_key="Ab minor",
            output_key_confidence=0.8,
            key_match=False,
            melody_chord_tone_ratio=0.7,
            melody_match=True,
            phrase_beat_alignment_ratio=0.9,
            phrase_match=True,
            downbeat_alignment_ratio=0.9,
            downbeat_match=True,
            analysed_phrase_count=4,
            analysed_downbeat_count=8,
            analysed_melody_points=20,
            passed=False,
            warnings=["Backing key Ab minor does not match preserved vocal key F minor."],
        )

    monkeypatch.setattr(
        skarly_studio.musical_compatibility,
        "assess_vocal_arrangement",
        compatibility_report,
    )
    monkeypatch.setattr(skarly_studio, "arrangement_similarity_rejection_reason", lambda *args, **kwargs: None)
    actual_mix = skarly_studio.mix_vocal_forward
    applied_mix_presets: list[str] = []

    def capture_mix(**kwargs):
        applied_mix_presets.append(kwargs["preset_name"])
        return actual_mix(**kwargs)

    monkeypatch.setattr(skarly_studio, "mix_vocal_forward", capture_mix)
    response = client.post(
        "/v1/skarly/generate",
        headers=AUTH_HEADERS,
        json={
            "upload_id": upload["upload_id"],
            "arrangement_mode": arrangement_mode,
            "preserve_original_vocal": True,
            "reference_strength": 0.35,
        },
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["source_preparation"]["detected_mode"] == "full_song"
    assert data["source_preparation"]["vocal_preserved"] is True
    assert data["vocal_url"]
    assert len(conditioned_sources) == 5
    expected_conditioning_source = separated_vocal if arrangement_mode == "full_song" else clean_instrumental
    assert set(conditioned_sources) == {expected_conditioning_source}
    assert all(version["final_mix_url"] != version["backing_url"] for version in data["versions"])
    assert all(version["transformation_quality"]["passed"] is True for version in data["versions"])
    assert all(version["musical_compatibility"]["passed"] is True for version in data["versions"])
    assert applied_mix_presets == [
        skarly_studio.resolve_version_mix_preset("balanced", version["producer_mix_mode"])
        for version in data["versions"]
    ]
    assert len(set(applied_mix_presets)) >= 2
    corrected_quality = data["versions"][0]["musical_compatibility"]
    assert corrected_quality["key_correction_applied"] is True
    assert corrected_quality["key_correction_semitones"] == -1
    assert corrected_quality["pre_correction_output_key"] == "F# minor"
    assert corrected_quality["post_correction_detected_key"] == "Ab minor"
    assert corrected_quality["output_key"] == "F minor"
    assert corrected_quality["key_match"] is True
    assert any("transposed down 1 semitone" in warning for warning in corrected_quality["warnings"])
    assert not any("did not match the preserved vocal" in warning for warning in data["warnings"])
    if arrangement_mode == "full_song":
        assert all("preserved singer" in version["prompt"] for version in data["versions"])
    else:
        assert all("genuinely new instrumental transformation" in version["prompt"] for version in data["versions"])


def test_detected_full_song_rejects_demucs_failure_without_center_fallback(monkeypatch, tmp_path):
    source = write_wav(tmp_path / "full-song.wav", frequency=220.0)
    monkeypatch.setattr(
        skarly_studio.stems_service,
        "separate_stems",
        lambda **_kwargs: StemSeparationResponse(
            status="failed",
            engine="demucs",
            warnings=["mock Demucs failure"],
        ),
    )

    with pytest.raises(RuntimeError, match="source_separation failed"):
        skarly_studio.prepare_vocal_source(
            source,
            tmp_path / "job",
            input_profile=skarly_studio.InputProfile("full_song", "Singing", "Medium", 0.9),
            stem_separator_backend="demucs",
            demucs_path="fake-demucs",
            demucs_model="htdemucs_ft",
            demucs_two_stems="vocals",
            demucs_device="cuda",
            timeout_sec=1200,
        )

    assert not (tmp_path / "job" / "vocals_center_estimate.wav").exists()


def test_skarly_training_feedback_rejects_unsupported_language_without_retaining_audio(tmp_path):
    source = write_wav(tmp_path / "creator-vocal.wav")
    feedback_dir = tmp_path / "consented_feedback"
    manifest = tmp_path / "manifests" / "user_feedback.jsonl"

    with pytest.raises(ValueError, match="Hindi and English"):
        training_feedback.save_opt_in_vocal_example(
            source,
            feedback_dir=feedback_dir,
            manifest_path=manifest,
            language="Hinglish",
            genre="Bollywood",
            job_id="skarly_job_test",
        )

    assert not feedback_dir.exists()
    assert not manifest.exists()


def test_skarly_best_version_is_saved_to_the_owned_library(monkeypatch, tmp_path):
    settings = phase1_settings(tmp_path)
    monkeypatch.setattr(main_module, "settings", settings)
    monkeypatch.setattr(main_module, "jobs", InMemoryJobRepository())
    monkeypatch.setattr(main_module, "storage", LocalFileStorageService(tmp_path / "library"))
    upload = upload_wav(tmp_path)

    generated = client.post(
        "/v1/skarly/generate",
        headers=AUTH_HEADERS,
        json={"upload_id": upload["upload_id"], "language": "Hindi", "mood": "Romantic"},
    )
    assert generated.status_code == 200, generated.text
    payload = generated.json()

    selected = client.post(
        f"/v1/skarly/jobs/{payload['job_id']}/select",
        headers=AUTH_HEADERS,
        json={"version_index": 3},
    )

    assert selected.status_code == 200
    saved = selected.json()
    assert saved["job"]["job_id"] == payload["job_id"]
    assert saved["job"]["library_status"] == "Selected"
    assert saved["job"]["final_generation_settings"]["skarly_selection"]["style_family"] == "punjabi_rhythm"
    assert "/local-storage/download/" in saved["final_mp3_url"]
    assert main_module.storage.object_exists(saved["job"]["final_mp3_path"])
    assert main_module.storage.object_exists(saved["job"]["backing_audio_path"])

    history = client.get("/v1/history", headers=AUTH_HEADERS)
    assert history.status_code == 200
    assert [track["job_id"] for track in history.json()["tracks"]] == [payload["job_id"]]


def test_skarly_generate_rejects_unknown_mix_preset(monkeypatch, tmp_path):
    monkeypatch.setattr(main_module, "settings", phase1_settings(tmp_path))
    upload = upload_wav(tmp_path)

    response = client.post(
        "/v1/skarly/generate",
        headers=AUTH_HEADERS,
        json={"upload_id": upload["upload_id"], "mix_preset": "bury_the_vocal"},
    )

    assert response.status_code == 400
    assert "Unsupported Skarly mix preset" in response.json()["detail"]


def test_skarly_analyze_surfaces_whisper_and_melody_metadata(monkeypatch, tmp_path):
    monkeypatch.setattr(main_module, "settings", phase23_settings(tmp_path))
    upload = upload_wav(tmp_path)

    def fake_whisper(audio_path, *, whisper_path, whisper_model, timeout_sec):
        return skarly_studio.TranscriptionResult(language="Urdu", text="dil toot gaya", status="available")

    def fake_melody(input_audio_path, job_dir, **kwargs):
        midi = Path(job_dir) / "melody.mid"
        midi.parent.mkdir(parents=True, exist_ok=True)
        midi.write_bytes(b"MThd\x00\x00\x00\x06\x00\x00\x00\x01\x00`MTrk\x00\x00\x00\x04\x00\xff/\x00")
        return skarly_studio.MelodyResult(midi_path=midi, status="available")

    monkeypatch.setattr(skarly_studio, "transcribe_with_whisper", fake_whisper)
    monkeypatch.setattr(skarly_studio, "create_melody_midi", fake_melody)

    response = client.post("/v1/skarly/analyze", headers=AUTH_HEADERS, json={"upload_id": upload["upload_id"]})

    assert response.status_code == 200
    data = response.json()
    assert data["detected"]["language"] == "Urdu"
    assert data["detected"]["lyrics_preview"] == "dil toot gaya"
    assert data["detected"]["melody_midi_status"] == "available"
    assert data["melody_midi_url"].startswith("/outputs/skarly/")
    assert data["analysis_url"].endswith("/analysis.json")
    assert output_path_from_skarly_url(Path(main_module.settings.skarly_output_dir), data["melody_midi_url"]).exists()
    assert output_path_from_skarly_url(Path(main_module.settings.skarly_output_dir), data["analysis_url"]).exists()


def test_skarly_generate_uses_ace_step_for_all_five_versions(monkeypatch, tmp_path):
    settings = phase23_settings(tmp_path, generator_backend="ace_step")
    monkeypatch.setattr(main_module, "settings", settings)
    upload = upload_wav(tmp_path)

    generated_prompts: list[str] = []

    def fake_ace_step_backing(*, output_path, plan, seconds, **kwargs):
        generated_prompts.append(plan.prompt)
        skarly_studio.write_placeholder_backing(output_path, seconds=seconds, bpm=84, version_index=len(generated_prompts))

    monkeypatch.setattr(skarly_studio, "generate_ace_step_backing", fake_ace_step_backing)

    response = client.post("/v1/skarly/generate", headers=AUTH_HEADERS, json={"upload_id": upload["upload_id"], "mix_preset": "vocal_up"})

    assert response.status_code == 200
    data = response.json()
    assert data["generator_backend"] == "ace_step"
    assert len(data["versions"]) == 5
    assert len(generated_prompts) == 5
    assert {version["generator"] for version in data["versions"]} == {"ace_step"}
    assert all(version["fallback_used"] is False for version in data["versions"])
    assert data["generation_telemetry"]["generation_backend"] == "unverified"
    assert data["generation_telemetry"]["cpu_fallback"] is False
    assert all("No generated singing" in version["prompt"] for version in data["versions"])
    assert data["analysis_url"].startswith("/outputs/skarly/")


def test_skarly_generation_fails_closed_when_provider_keeps_returning_duplicate_backings(monkeypatch, tmp_path):
    settings = phase23_settings(tmp_path, generator_backend="ace_step")
    monkeypatch.setattr(main_module, "settings", settings)
    upload = upload_wav(tmp_path)
    generated_seeds: list[int] = []

    def duplicate_ace_step_backing(*, output_path, plan, seconds, **kwargs):
        generated_seeds.append(plan.seed)
        # Deliberately mimic a faulty provider returning the same audio every time.
        skarly_studio.write_placeholder_backing(output_path, seconds=seconds, bpm=84, version_index=1)

    monkeypatch.setattr(skarly_studio, "generate_ace_step_backing", duplicate_ace_step_backing)

    response = client.post("/v1/skarly/generate", headers=AUTH_HEADERS, json={"upload_id": upload["upload_id"]})

    assert response.status_code == 503
    detail = response.json()["detail"]
    # One accepted backing plus three fresh-seed attempts for arrangement two.
    assert len(generated_seeds) == 4
    assert len(set(generated_seeds)) == 4
    assert "Stage checking_arrangement_diversity rejected arrangement 2 of 5" in detail
    assert "1 completed arrangements remain" in detail
    assert "waveform correlation" in detail


def test_skarly_diversity_report_checks_all_ten_instrumental_pairs(tmp_path):
    paths = []
    for index in range(1, 6):
        path = tmp_path / f"backing_{index}.wav"
        skarly_studio.write_placeholder_backing(path, seconds=5.0, bpm=82 + (index * 7), version_index=index)
        paths.append(path)

    report = skarly_studio.build_arrangement_diversity_report(paths)

    assert report.evaluated_pairs == 10
    assert len(report.pairs) == 10
    assert report.rejected_pairs == 0
    assert report.passed is True
    assert all(0 <= pair.embedding_similarity <= 1 for pair in report.pairs)
    assert all(0 <= pair.drum_onset_similarity <= 1 for pair in report.pairs)
    assert all(0 <= pair.chord_change_similarity <= 1 for pair in report.pairs)
    assert all(0 <= pair.instrumentation_similarity <= 1 for pair in report.pairs)


def test_skarly_diversity_report_rejects_duplicate_instrumental_pair(tmp_path):
    paths = []
    for index in range(1, 6):
        path = tmp_path / f"backing_{index}.wav"
        skarly_studio.write_placeholder_backing(path, seconds=5.0, bpm=82 + (index * 7), version_index=index)
        paths.append(path)
    paths[-1].write_bytes(paths[0].read_bytes())

    report = skarly_studio.build_arrangement_diversity_report(paths)

    duplicate_pair = next(pair for pair in report.pairs if pair.left_index == 1 and pair.right_index == 5)
    assert report.evaluated_pairs == 10
    assert report.passed is False
    assert report.rejected_pairs >= 1
    assert duplicate_pair.rejected is True
    assert duplicate_pair.reason is not None
    assert duplicate_pair.embedding_similarity == pytest.approx(1.0)


def test_skarly_generate_falls_back_when_ace_step_fails(monkeypatch, tmp_path):
    settings = phase23_settings(tmp_path, generator_backend="ace_step")
    monkeypatch.setattr(main_module, "settings", settings)
    upload = upload_wav(tmp_path)

    def failing_ace_step_backing(**kwargs):
        raise RuntimeError("ACE server offline")

    monkeypatch.setattr(skarly_studio, "generate_ace_step_backing", failing_ace_step_backing)

    response = client.post("/v1/skarly/generate", headers=AUTH_HEADERS, json={"upload_id": upload["upload_id"]})

    assert response.status_code == 200
    data = response.json()
    assert {version["generator"] for version in data["versions"]} == {"procedural_v2"}
    assert all(version["fallback_used"] is True for version in data["versions"])
    assert any("ACE-Step failed" in warning for warning in data["warnings"])


def test_skarly_retries_only_the_failed_arrangement_without_cpu_fallback(monkeypatch, tmp_path):
    settings = replace(
        phase23_settings(tmp_path, generator_backend="ace_step"),
        ace_step_fallback_to_procedural=False,
        allow_cpu_generation_fallback=False,
    )
    monkeypatch.setattr(main_module, "settings", settings)
    upload = upload_wav(tmp_path)
    order: list[str] = []
    attempts: dict[str, int] = {}

    def transient_failure(*, output_path, plan, seconds, **_kwargs):
        if plan.name not in order:
            order.append(plan.name)
        attempts[plan.name] = attempts.get(plan.name, 0) + 1
        if len(order) == 3 and plan.name == order[2] and attempts[plan.name] == 1:
            raise RuntimeError("temporary CUDA allocation failure")
        write_wav(output_path, seconds=seconds, frequency=180 + order.index(plan.name) * 95)

    monkeypatch.setattr(skarly_studio, "generate_ace_step_backing", transient_failure)

    response = client.post("/v1/skarly/generate", headers=AUTH_HEADERS, json={"upload_id": upload["upload_id"]})

    assert response.status_code == 200
    data = response.json()
    assert len(data["versions"]) == 5
    assert attempts[order[2]] == 2
    assert all(version["fallback_used"] is False for version in data["versions"])
    assert any("kept the completed arrangements and retried this one" in warning for warning in data["warnings"])


def test_skarly_permanent_arrangement_failure_reports_stage_and_keeps_completed_files(monkeypatch, tmp_path):
    settings = replace(
        phase23_settings(tmp_path, generator_backend="ace_step"),
        ace_step_fallback_to_procedural=False,
        allow_cpu_generation_fallback=False,
    )
    monkeypatch.setattr(main_module, "settings", settings)
    upload = upload_wav(tmp_path)
    order: list[str] = []

    def permanent_third_failure(*, output_path, plan, seconds, **_kwargs):
        if plan.name not in order:
            order.append(plan.name)
        if len(order) >= 3 and plan.name == order[2]:
            raise RuntimeError("persistent CUDA worker failure")
        write_wav(output_path, seconds=seconds, frequency=180 + order.index(plan.name) * 95)

    monkeypatch.setattr(skarly_studio, "generate_ace_step_backing", permanent_third_failure)

    response = client.post("/v1/skarly/generate", headers=AUTH_HEADERS, json={"upload_id": upload["upload_id"]})

    assert response.status_code == 503
    detail = response.json()["detail"]
    assert "Stage creating_arrangement failed for arrangement 3 of 5" in detail
    assert "2 completed arrangements remain" in detail
    job_dirs = list(Path(settings.skarly_output_dir).glob("skarly_job_*"))
    assert len(job_dirs) == 1
    assert (job_dirs[0] / "backing_1.wav").exists()
    assert (job_dirs[0] / "final_mix_1.mp3").exists()
    assert (job_dirs[0] / "backing_2.wav").exists()
    assert (job_dirs[0] / "final_mix_2.mp3").exists()


def test_skarly_duration_uses_full_five_minutes_and_never_crops():
    assert skarly_studio.studio_generation_duration(300.0, 300) == 300.0
    assert skarly_studio.studio_generation_duration(119.375, 300) == 119.375
    with pytest.raises(ValueError, match="No audio was cropped"):
        skarly_studio.studio_generation_duration(300.25, 300)


def test_skarly_duration_verification_reads_float_wav(tmp_path):
    import soundfile as sf

    path = tmp_path / "ace-float.wav"
    sf.write(path, np.zeros((48000, 2), dtype=np.float32), 48000, subtype="FLOAT")

    assert skarly_studio.safe_duration_seconds(path) == pytest.approx(1.0)


def test_skarly_cuda_requirement_fails_before_generation(monkeypatch, tmp_path):
    settings = phase23_settings(tmp_path, generator_backend="ace_step")
    settings = Settings(**{
        **settings.__dict__,
        "require_cuda": True,
        "allow_cpu_generation_fallback": False,
        "ace_step_python_path": str(tmp_path / "missing-python.exe"),
    })
    monkeypatch.setattr(main_module, "settings", settings)
    upload = upload_wav(tmp_path)

    response = client.post("/v1/skarly/generate", headers=AUTH_HEADERS, json={"upload_id": upload["upload_id"]})

    assert response.status_code == 503
    assert "CUDA preflight failed" in response.json()["detail"]
