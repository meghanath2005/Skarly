from pathlib import Path

from app.services import musical_compatibility, skarly_studio


def compatible_song_map(seconds: int = 24) -> dict:
    return {
        "phrases": [{"start_seconds": float(value)} for value in range(0, seconds, 2)],
        "tempo": {"downbeats": [float(value) for value in range(0, seconds, 2)]},
        "melody_curve": [
            {"time_seconds": value / 10.0, "midi": 69.0, "voiced": True}
            for value in range(0, seconds * 10)
        ],
    }


def test_vocal_arrangement_gate_accepts_matching_tempo_key_melody_and_grid(monkeypatch, tmp_path: Path):
    backing = tmp_path / "compatible.wav"
    skarly_studio.write_placeholder_backing(
        backing,
        seconds=24,
        bpm=120,
        key="A minor",
        mood="Energetic",
        energy="High",
        version_index=2,
        seed=44,
    )
    monkeypatch.setattr(
        musical_compatibility.vocal_analysis,
        "_estimate_key_and_pitch",
        lambda *_args, **_kwargs: ("A minor", 0.8, "available", None),
    )
    monkeypatch.setattr(
        musical_compatibility.vocal_analysis,
        "_estimate_bpm",
        lambda *_args, **_kwargs: (120.0, None),
    )

    report = musical_compatibility.assess_vocal_arrangement(
        backing_audio_path=backing,
        target_bpm=120,
        target_key="A minor",
        song_map=compatible_song_map(),
    )

    assert report.passed is True
    assert report.tempo_match is True
    assert report.key_match is True
    assert report.melody_match is True
    assert report.phrase_match is True
    assert report.downbeat_match is True


def test_low_confidence_key_label_uses_timed_vocal_melody_support(monkeypatch, tmp_path: Path):
    backing = tmp_path / "compatible-with-unstable-key-label.wav"
    skarly_studio.write_placeholder_backing(
        backing,
        seconds=24,
        bpm=120,
        key="A minor",
        mood="Energetic",
        energy="High",
        version_index=2,
        seed=44,
    )
    monkeypatch.setattr(
        musical_compatibility.vocal_analysis,
        "_estimate_key_and_pitch",
        lambda *_args, **_kwargs: ("A# minor", 0.35, "available", None),
    )
    monkeypatch.setattr(
        musical_compatibility.vocal_analysis,
        "_estimate_bpm",
        lambda *_args, **_kwargs: (120.0, None),
    )

    report = musical_compatibility.assess_vocal_arrangement(
        backing_audio_path=backing,
        target_bpm=120,
        target_key="A minor",
        song_map=compatible_song_map(),
    )

    assert report.passed is True
    assert report.key_match is True
    assert report.key_match_method == "timed_melody_support"
    assert report.output_key == "A# minor"
    assert any("low-confidence" in warning for warning in report.warnings)


def test_vocal_arrangement_gate_fails_closed_for_wrong_music_and_missing_maps(monkeypatch, tmp_path: Path):
    backing = tmp_path / "wrong.wav"
    skarly_studio.write_placeholder_backing(backing, seconds=12, bpm=105, key="F# minor", version_index=3)
    monkeypatch.setattr(
        musical_compatibility.vocal_analysis,
        "_estimate_key_and_pitch",
        lambda *_args, **_kwargs: ("F# minor", 0.8, "available", None),
    )
    monkeypatch.setattr(
        musical_compatibility.vocal_analysis,
        "_estimate_bpm",
        lambda *_args, **_kwargs: (105.0, None),
    )

    report = musical_compatibility.assess_vocal_arrangement(
        backing_audio_path=backing,
        target_bpm=120,
        target_key="A minor",
        song_map={},
    )

    assert report.passed is False
    assert report.tempo_match is False
    assert report.key_match is False
    assert report.melody_match is False
    assert report.phrase_match is False
    assert report.downbeat_match is False
    assert len(report.warnings) >= 5


def test_key_transposition_uses_shortest_same_mode_shift():
    assert musical_compatibility.key_transposition_semitones("F# minor", "F minor") == -1
    assert musical_compatibility.key_transposition_semitones("A minor", "F minor") == -4
    assert musical_compatibility.key_transposition_semitones("B minor", "C minor") == 1
    assert musical_compatibility.key_transposition_semitones("Gb minor", "F# minor") == 0
    assert musical_compatibility.key_transposition_semitones("F# major", "F minor") is None
    assert musical_compatibility.key_transposition_semitones(None, "F minor") is None


def test_rubberband_key_correction_preserves_duration(tmp_path: Path):
    source = tmp_path / "f-sharp-minor.wav"
    corrected = tmp_path / "f-minor.wav"
    skarly_studio.write_placeholder_backing(
        source,
        seconds=8,
        bpm=120,
        key="F# minor",
        mood="Energetic",
        energy="High",
        version_index=2,
        seed=44,
    )

    musical_compatibility.transpose_backing_to_key(
        input_audio_path=source,
        output_audio_path=corrected,
        semitones=-1,
        ffmpeg_path="ffmpeg",
        timeout_seconds=60,
    )

    assert corrected.is_file()
    assert corrected.read_bytes() != source.read_bytes()
    assert skarly_studio.safe_duration_seconds(corrected) == skarly_studio.safe_duration_seconds(source)


def test_full_song_style_diversity_rejects_same_timbre_cluster():
    metrics = {
        "embedding_similarity": 0.92,
        "drum_onset_similarity": 0.20,
        "chord_change_similarity": 0.26,
        "instrumentation_similarity": 0.99,
        "perceptual_similarity": 0.65,
    }

    assert skarly_studio.arrangement_similarity_rejection_reason(metrics) is None
    assert skarly_studio.arrangement_similarity_rejection_reason(metrics, strict_style_diversity=True) is not None


def test_default_mix_uses_each_producer_mode_but_explicit_override_wins():
    assert skarly_studio.resolve_version_mix_preset("balanced", "vocal_forward") == "vocal_forward"
    assert skarly_studio.resolve_version_mix_preset("balanced", "beat_forward") == "beat_forward"
    assert skarly_studio.resolve_version_mix_preset("vocal_up", "beat_forward") == "vocal_up"
