import math
import wave
from pathlib import Path

import numpy as np

from app.services.uploads import save_audio_upload, get_upload
from app.services import vocal_analysis
from app.services.vocal_analysis import analyze_vocal_audio


def write_wav_bytes(path: Path, seconds: float = 4.0, frequency: float = 330.0, amplitude: float = 0.35, sample_rate: int = 22050) -> bytes:
    t = np.linspace(0, seconds, int(sample_rate * seconds), endpoint=False)
    samples = amplitude * np.sin(2 * math.pi * frequency * t)
    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype(np.int16)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm.tobytes())
    return path.read_bytes()


def test_audio_upload_saves_valid_file_and_metadata(tmp_path):
    data = write_wav_bytes(tmp_path / "source.wav")

    response = save_audio_upload(
        filename="../../Tum Hi Ho vocal.wav",
        content_type="audio/wav",
        data=data,
        uploads_dir=tmp_path / "uploads",
        max_upload_mb=10,
        url_for_path=lambda path: f"/safe/{Path(path).name}",
    )

    assert response.upload_id.startswith("upload_")
    assert Path(response.original_path).exists()
    assert ".." not in response.filename
    assert response.audio_url == "/safe/original.wav"
    assert response.quality_report.passed is True

    loaded = get_upload(response.upload_id, uploads_dir=tmp_path / "uploads")
    assert loaded is not None
    assert loaded.original_path == response.original_path


def test_audio_upload_rejects_unsupported_extension(tmp_path):
    data = b"not audio"

    try:
        save_audio_upload(
            filename="notes.txt",
            content_type="text/plain",
            data=data,
            uploads_dir=tmp_path / "uploads",
            max_upload_mb=10,
            url_for_path=None,
        )
    except ValueError as exc:
        assert "Unsupported audio format" in str(exc)
    else:
        raise AssertionError("Unsupported extension should fail")


def test_vocal_analysis_reports_duration_key_bpm_and_phrases(tmp_path):
    wav_path = tmp_path / "vocal.wav"
    write_wav_bytes(wav_path)

    report = analyze_vocal_audio(
        wav_path,
        upload_id="upload_test",
        normalized_output_dir=tmp_path / "uploads",
        url_for_path=lambda path: f"/outputs/uploads/{Path(path).name}",
    )

    assert report.duration_seconds is not None
    assert 3.8 <= report.duration_seconds <= 4.2
    assert report.estimated_bpm is not None
    assert report.estimated_key
    assert report.phrase_boundaries
    song_map = report.song_intelligence_map
    assert song_map is not None
    assert song_map.analysis_scope == "complete"
    assert song_map.duration_seconds == report.duration_seconds
    assert song_map.tempo.bpm == report.estimated_bpm
    assert song_map.tonality.key in report.estimated_key
    assert song_map.energy_curve
    assert song_map.melody_curve
    assert song_map.stable_notes
    assert len(song_map.chord_compatibility) == 7
    assert song_map.rhythm_analysis["source"]
    assert song_map.structure_analysis["semantic_labels_are_candidates"] is True
    assert song_map.phrases[0]["delivery_source"] == "phrase_pitch_and_onset_candidate"
    assert "rhythmic_density_onsets_per_second" in song_map.sections[0]
    assert song_map.pitch_method == "full_song_sparse_yin"
    assert song_map.vocal_range.lowest_note
    assert song_map.vocal_range.highest_note
    assert Path(report.normalized_wav_path).exists()
    assert report.quality_report.passed is True


def test_section_candidates_align_full_song_sections_to_real_phrase_gaps():
    phrases = [
        {"start_seconds": 0.5, "end_seconds": 10.0},
        {"start_seconds": 13.6, "end_seconds": 20.0},
        {"start_seconds": 22.0, "end_seconds": 35.0},
        {"start_seconds": 40.4, "end_seconds": 50.0},
        {"start_seconds": 52.0, "end_seconds": 60.0},
        {"start_seconds": 65.2, "end_seconds": 73.0},
        {"start_seconds": 75.0, "end_seconds": 90.0},
        {"start_seconds": 92.8, "end_seconds": 102.0},
        {"start_seconds": 104.0, "end_seconds": 112.0},
        {"start_seconds": 113.2, "end_seconds": 119.0},
    ]

    sections = vocal_analysis._section_candidates(120.0, phrases)

    assert [section["name"] for section in sections] == ["intro", "mukhda", "hook", "antara", "final_hook", "outro"]
    assert [section["end_seconds"] for section in sections[:-1]] == [11.8, 37.7, 62.6, 91.4, 112.6]
    assert all(section["source"] == "phrase_aligned" for section in sections)


def test_song_map_marks_inter_phrase_silence_and_breath_regions(tmp_path):
    sample_rate = 16000
    first_t = np.arange(int(1.4 * sample_rate)) / sample_rate
    second_t = np.arange(int(1.4 * sample_rate)) / sample_rate
    samples = np.concatenate(
        [
            np.zeros(int(0.4 * sample_rate)),
            0.32 * np.sin(2 * math.pi * 330 * first_t),
            np.zeros(int(0.65 * sample_rate)),
            0.32 * np.sin(2 * math.pi * 440 * second_t),
            np.zeros(int(0.5 * sample_rate)),
        ]
    )
    path = tmp_path / "phrased-vocal.wav"
    pcm = (samples * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm.tobytes())

    song_map = analyze_vocal_audio(path).song_intelligence_map

    assert song_map is not None
    assert len(song_map.phrases) == 2
    assert any(region["type"] == "intro_silence" for region in song_map.silence_regions)
    assert any(region["type"] == "outro_silence" for region in song_map.silence_regions)
    assert song_map.breath_regions
    assert all(region["source"] == "short_inter_phrase_gap" for region in song_map.breath_regions)
    assert song_map.vocal_range.lowest_midi < song_map.vocal_range.highest_midi


def test_phrase_map_has_no_hidden_32_phrase_cap():
    activity = [
        {
            "start_seconds": index * 2.0,
            "end_seconds": index * 2.0 + 1.1,
            "average_rms": 0.2,
        }
        for index in range(45)
    ]

    phrases = vocal_analysis._phrase_boundaries(activity, 92.0)

    assert len(phrases) == 45
    assert phrases[-1]["phrase"] == 45
    assert phrases[-1]["end_seconds"] == 89.1


def test_melodic_features_preserve_slides_and_find_transposed_repeated_motif():
    first = [60, 60, 60, 60, 60, 60, 61, 62, 63, 64, 64, 64, 64, 64, 64, 64, 64, 64]
    second = [value + 2 for value in first]
    curve = []
    for index, midi in enumerate(first):
        curve.append(
            {
                "time_seconds": round(index * 0.1, 3),
                "midi": float(midi),
                "voiced": True,
                "confidence": 0.9,
            }
        )
    curve.extend(
        [
            {"time_seconds": 1.8, "midi": None, "voiced": False, "confidence": 0.0},
            {"time_seconds": 1.9, "midi": None, "voiced": False, "confidence": 0.0},
        ]
    )
    for index, midi in enumerate(second):
        curve.append(
            {
                "time_seconds": round(2.0 + index * 0.1, 3),
                "midi": float(midi),
                "voiced": True,
                "confidence": 0.9,
            }
        )
    phrases = [
        {"phrase": 1, "start_seconds": 0.0, "end_seconds": 1.7, "duration_seconds": 1.7},
        {"phrase": 2, "start_seconds": 2.0, "end_seconds": 3.7, "duration_seconds": 1.7},
    ]

    stable = vocal_analysis._stable_notes(curve, 3.8)
    transitions, slides = vocal_analysis._note_transitions_and_slides(stable, curve)
    ornaments = vocal_analysis._ornamentation_candidates(curve, slides)
    motifs, phrase_ids = vocal_analysis._melodic_motifs(phrases, curve)

    assert len(stable) >= 4
    assert transitions
    assert any(slide["semitones"] >= 3.5 for slide in slides)
    assert any(item["type"] == "possible_meend" for item in ornaments)
    assert motifs[0]["phrase_numbers"] == [1, 2]
    assert phrase_ids == {1: "motif_1", 2: "motif_1"}


def test_phrase_rhythm_marks_pickup_relative_tempo_and_repeated_melody():
    phrases = [
        {
            "phrase": 1,
            "start_seconds": 0.3,
            "end_seconds": 1.3,
            "duration_seconds": 1.0,
            "preceding_gap_seconds": 0.3,
        }
    ]
    melody = [
        {"time_seconds": round(0.3 + index * 0.1, 3), "midi": 64.0, "voiced": True}
        for index in range(10)
    ]
    stable = [
        {
            "start_seconds": 0.3,
            "end_seconds": 1.3,
            "duration_seconds": 1.0,
        }
    ]
    tempo = vocal_analysis.SongTempoInfo(bpm=120, confidence=0.8, source="test")

    enriched = vocal_analysis._enrich_phrases(
        phrases,
        melody_curve=melody,
        stable_notes=stable,
        onset_times=[0.3, 0.55, 0.8, 1.05],
        tempo=tempo,
        phrase_motif_ids={1: "motif_1"},
    )[0]

    assert enriched["pickup_candidate"] is True
    assert enriched["relative_tempo_bpm"] == 120.0
    assert enriched["rhythmic_density_onsets_per_second"] == 4.0
    assert enriched["sustained_candidate"] is True
    assert enriched["repeated_melody"] is True
    assert enriched["motif_id"] == "motif_1"


def test_key_change_candidates_require_persistent_overlapping_windows():
    windows = [
        {"start_seconds": 0.0, "end_seconds": 10.0, "key": "A minor", "confidence": 0.6},
        {"start_seconds": 5.0, "end_seconds": 15.0, "key": "A minor", "confidence": 0.62},
        {"start_seconds": 15.0, "end_seconds": 25.0, "key": "D minor", "confidence": 0.58},
        {"start_seconds": 20.0, "end_seconds": 30.0, "key": "D minor", "confidence": 0.61},
        {"start_seconds": 30.0, "end_seconds": 40.0, "key": "F major", "confidence": 0.8},
    ]

    changes = vocal_analysis._consolidate_key_windows(windows, "A minor")

    assert len(changes) == 1
    assert changes[0]["previous_key"] == "A minor"
    assert changes[0]["key"] == "D minor"
    assert changes[0]["supporting_windows"] == 2
    assert changes[0]["requires_confirmation"] is True
