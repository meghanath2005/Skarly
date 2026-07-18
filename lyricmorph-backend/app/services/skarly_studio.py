from __future__ import annotations

import csv
from dataclasses import dataclass, field, replace
from pathlib import Path
import json
import math
import os
import shlex
import shutil
import subprocess
import tempfile
import time
from types import SimpleNamespace
import wave
from urllib.parse import quote
from urllib.parse import urljoin
from uuid import uuid4
from typing import Any, Callable

import numpy as np

from ..models import (
    ArrangementDiversityPair,
    ArrangementDiversityReport,
    GenerationTelemetry,
    MusicalCompatibilityQuality,
    SongAudioIntelligence,
    SongIntelligenceMap,
    SongLanguageInfo,
    SkarlyDetected,
    SkarlyStudioAnalyzeResponse,
    SkarlyStudioResponse,
    SkarlyVersion,
    SkarlyWaveforms,
    VocalLeakageQuality,
)
from . import cuda_runtime, diversity_calibration, music_source, music_transform_quality, musical_compatibility, safe_paths, stems as stems_service, training_feedback, uploads as upload_service, vocal_analysis

try:
    import requests
except Exception:  # pragma: no cover
    requests = None

_BASIC_PITCH_PREFLIGHT_WARNINGS: dict[str, str | None] = {}

VERSION_NAMES = (
    "Original Mood Match",
    "Piano Heartbreak",
    "Guitar Ballad",
    "Lo-fi Sad Version",
    "Cinematic Emotional",
)

HINDI_VERSION_NAMES = (
    "Hindi Pop Mood Match",
    "Acoustic Hindi Ballad",
    "Hindi Indie Pop",
    "Lo-fi Hindi Nights",
    "Cinematic Hindi Score",
)

HINDI_DEVOTIONAL_VERSION_NAMES = (
    "Harmonium Bhajan",
    "Sufi Acoustic",
    "Qawwali Pulse",
    "Meditative Folk",
    "Cinematic Devotional",
)

HINDI_PUNJABI_VERSION_NAMES = (
    "Punjabi Pop Lift",
    "Punjabi Folk Acoustic",
    "Punjabi Urban Bounce",
    "Punjabi Lo-fi Nights",
    "Punjabi Cinematic Anthem",
)

HINDI_URBAN_VERSION_NAMES = (
    "Hindi R&B Glow",
    "Hindi Hip-hop Pulse",
    "Hindi Trap Soul",
    "Hindi Neo-soul",
    "Hindi Cinematic Urban",
)

HINDI_BOLLYWOOD_VERSION_NAMES = (
    "Bollywood Acoustic",
    "Modern Bollywood Pop",
    "Sufi Live",
    "Punjabi Rhythm",
    "Cinematic Urban",
)

MIXING_PRESETS = {
    "balanced": {
        "vocal_volume": 1.0,
        "backing_volume": 0.90,
        "ducking": "medium",
    },
    "vocal_up": {
        "vocal_volume": 1.10,
        "backing_volume": 0.75,
        "ducking": "medium",
    },
    "vocal_forward": {
        "vocal_volume": 1.10,
        "backing_volume": 0.75,
        "ducking": "medium",
    },
    "soft_bed": {
        "vocal_volume": 1.05,
        "backing_volume": 0.6,
        "ducking": "light",
    },
    "beat_up": {
        "vocal_volume": 0.92,
        "backing_volume": 1.20,
        "ducking": "light",
    },
    "beat_forward": {
        "vocal_volume": 0.92,
        "backing_volume": 1.20,
        "ducking": "light",
    },
}

DEFAULT_MIX_PRESET = "balanced"
MIN_LANGUAGE_CLASSIFIER_CONFIDENCE = 0.70
# The first broad genre checkpoint is deliberately conservative: vocal-only
# audio is not enough evidence for a strong genre claim unless the classifier
# is notably confident.
MIN_GENRE_CLASSIFIER_CONFIDENCE = 0.78
MAX_BASIC_PITCH_GENERATION_SECONDS = 75.0
MAX_DIVERSITY_GENERATION_ATTEMPTS = 3
DIVERSITY_THRESHOLDS = diversity_calibration.DEFAULT_THRESHOLDS
STYLE_CLUSTER_THRESHOLDS = {
    "style_embedding": 0.90,
    "style_instrumentation": 0.985,
    "style_perceptual": 0.78,
    "style_perceptual_embedding_floor": 0.88,
    "style_perceptual_instrumentation_floor": 0.975,
}


@dataclass(frozen=True)
class StudioPaths:
    output_root: Path
    job_dir: Path


@dataclass(frozen=True)
class TranscriptionResult:
    language: str | None = None
    text: str | None = None
    segments: tuple[dict[str, Any], ...] = ()
    status: str = "unavailable"
    warning: str | None = None


@dataclass(frozen=True)
class InputProfile:
    source_profile: str
    vocal_type: str
    energy: str
    confidence: float
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class VocalPrepResult:
    vocal_path: Path
    source_profile: str
    warnings: tuple[str, ...] = ()
    vocal_leakage_quality: VocalLeakageQuality | None = None


@dataclass(frozen=True)
class MelodyResult:
    midi_path: Path | None
    status: str
    warning: str | None = None


@dataclass(frozen=True)
class ArrangementAudioFeatures:
    embedding: np.ndarray
    drum_onsets: np.ndarray
    chord_changes: np.ndarray
    instrumentation: np.ndarray


@dataclass(frozen=True)
class VersionPlan:
    name: str
    prompt: str
    negative_prompt: str
    style_family: str = "custom"
    seed: int = 0
    instruments: tuple[str, ...] = ()
    energy: str = "adaptive"
    rhythm_character: str = "vocal-following"
    mix_mode: str = "balanced"
    blueprint: dict[str, str] | None = None


@dataclass(frozen=True)
class ProducerProfile:
    profile_id: str
    name: str
    instruments: tuple[str, ...]
    energy: str
    rhythm_character: str
    bass_movement: str
    harmonic_rhythm: str
    intro_treatment: str
    chorus_density: str
    transition_style: str
    stereo_character: str
    mix_mode: str
    direction: str

    def blueprint(self) -> dict[str, str]:
        return {
            "instrument_family": ", ".join(self.instruments),
            "energy_curve": self.energy,
            "rhythm_character": self.rhythm_character,
            "bass_movement": self.bass_movement,
            "harmonic_rhythm": self.harmonic_rhythm,
            "intro_treatment": self.intro_treatment,
            "chorus_density": self.chorus_density,
            "transition_style": self.transition_style,
            "stereo_character": self.stereo_character,
        }


PRODUCER_PROFILE_CATALOG: dict[str, ProducerProfile] = {
    profile.profile_id: profile
    for profile in (
        ProducerProfile(
            "bollywood_acoustic", "Bollywood Acoustic",
            ("acoustic guitar", "piano", "light tabla", "warm bass", "hook strings"),
            "intimate verse to expanded chorus", "light tabla pocket with phrase-gap fills",
            "warm sustained roots with melodic turnarounds", "two-bar changes with held verse chords",
            "solo guitar and piano pickup", "strings and wider percussion enter at the hook",
            "organic drum fills between lyrics", "natural room width with centered vocal space", "vocal_forward",
            "Bollywood acoustic instrumental with acoustic guitar, expressive piano, light tabla, warm bass, and strings entering only for the hook",
        ),
        ProducerProfile(
            "modern_bollywood", "Modern Bollywood Pop",
            ("electronic drums", "synth bass", "wide pads", "plucked synth", "transition effects"),
            "controlled verse with a strong modern chorus lift", "syncopated electronic kick-clap groove",
            "short syncopated synth-bass figures", "one-bar pop movement with pre-hook suspension",
            "filtered pad and pluck pulse", "dense wide pads, layered drums, and plucked hook",
            "risers, reverse impacts, and clean stop transitions", "wide polished pop image with mono-compatible low end", "balanced",
            "modern Bollywood-pop instrumental with punchy electronic drums, synth bass, wide pads, plucked synth, and contemporary chorus transitions",
        ),
        ProducerProfile(
            "sufi_live", "Sufi Live",
            ("harmonium", "tabla", "dholak", "hand claps", "live bass", "sarangi"),
            "patient live build toward an ecstatic final refrain", "human tabla-dholak cycle with hand-clap lift",
            "live bass pedal tones opening into walking responses", "slow devotional changes and tonic drones",
            "solo harmonium drone with room ambience", "claps, sarangi responses, and fuller live percussion",
            "live ensemble pickups and call-response instrumental fills", "stage-like center image with organic side ambience", "vocal_forward",
            "Sufi live instrumental with harmonium, tabla or dholak, hand claps, live bass, sarangi responses, and a gradual energy build",
        ),
        ProducerProfile(
            "punjabi_rhythm", "Punjabi Rhythm",
            ("dhol", "tumbi", "punch bass", "hand percussion", "bright synth accents"),
            "rhythmic verse gaps to festival-sized chorus energy", "dhol-led bhangra groove with deliberate vocal gaps",
            "punchy octave bass answering the dhol", "fast two-beat harmonic turns in the hook",
            "dry tumbi pickup and solo dhol call", "festival dhol layers, brighter tumbi, and chant-free instrumental lift",
            "dhol rolls, tumbi answers, and hard rhythmic stops", "wide festive percussion with focused central bass", "beat_forward",
            "Punjabi rhythm instrumental with a dhol-led groove, bright tumbi lead, punchier bass, rhythmic vocal gaps, and festival-style chorus energy",
        ),
        ProducerProfile(
            "cinematic_urban", "Cinematic Urban",
            ("felt piano", "atmospheric texture", "deep percussion", "cinematic strings", "sub bass"),
            "sparse opening, restrained middle, and very large final section", "half-time deep percussion with cinematic pulses",
            "minimal sub pedal growing into long low-end swells", "slow four-bar movement with tension chords",
            "isolated felt-piano motif in atmosphere", "large strings, deep percussion, and sub-bass final section",
            "sub drops, orchestral swells, and long-tail impacts", "very wide atmosphere with a dry protected vocal center", "balanced",
            "cinematic urban instrumental with felt piano, atmospheric intro, deep percussion, cinematic strings, sub-bass, sparse verse, and a large finale",
        ),
        ProducerProfile(
            "lofi", "Lo-fi",
            ("dusty breakbeat", "Rhodes", "mellow sub bass", "tape texture", "soft flute fills"),
            "low steady late-night energy", "half-time swung breakbeat", "simple soft sub roots",
            "slow looped jazz-pop changes", "tape-noise and filtered keys", "slightly fuller drums without a large lift",
            "tape stops and muted fills", "narrow vintage image with soft edges", "vocal_forward",
            "late-night lo-fi instrumental with half-time dusty drums, tape-warm Rhodes, mellow sub bass, and sparse soft fills",
        ),
        ProducerProfile(
            "rock", "Rock",
            ("live drums", "electric guitars", "bass guitar", "piano", "ambient guitar"),
            "restrained verse to anthemic live chorus", "live kick-snare groove with tom builds", "driving picked bass",
            "bar-level guitar chord movement", "clean ambient guitar and floor tom", "double guitars and open cymbals",
            "tom fills and feedback swells", "wide guitars with centered rhythm section", "balanced",
            "original vocal-safe rock arrangement with live drums, electric guitars, bass guitar, and an anthemic chorus without imitating an artist",
        ),
        ProducerProfile(
            "edm", "EDM",
            ("four-on-floor drums", "sidechained synths", "sub bass", "arp", "effects"),
            "progressive build and instrumental drop around vocal sections", "four-on-floor pulse with lyric-safe breakdowns",
            "sub pulse and offbeat bass", "one-bar dance harmony", "filtered arp and atmosphere",
            "wide synth stack and energetic drums", "noise risers, fills, and impact drops", "very wide highs with mono sub", "beat_forward",
            "EDM instrumental with four-on-floor drums, sidechained synths, sub bass, arpeggios, and drops placed outside important vocal phrases",
        ),
        ProducerProfile(
            "ghazal", "Ghazal",
            ("harmonium", "tabla", "sarangi", "acoustic bass", "soft strings"),
            "poetic and restrained throughout", "slow tabla theka with long phrase releases", "gentle acoustic bass pedals",
            "slow tonic-led changes", "harmonium and sarangi prelude", "subtle strings without dense drums",
            "sarangi replies between couplets", "intimate chamber image", "vocal_forward",
            "restrained ghazal instrumental with harmonium, slow tabla, sarangi replies, acoustic bass, and generous space around every lyric",
        ),
        ProducerProfile(
            "orchestral", "Orchestral",
            ("piano", "string orchestra", "woodwinds", "timpani", "orchestral bass"),
            "long symphonic arc with a controlled climax", "rubato orchestral pulse and restrained timpani", "orchestral bass pedal movement",
            "slow cinematic modulations", "solo piano and woodwind", "full strings and brass-free climax",
            "orchestral swells and cadential pauses", "concert-hall depth with clear center", "balanced",
            "orchestral instrumental with piano, strings, woodwinds, restrained timpani, a long emotional arc, and vocal-safe dynamics",
        ),
        ProducerProfile(
            "indie", "Indie",
            ("clean electric guitar", "live drums", "muted bass", "analog pad", "percussion"),
            "understated verse and bright human chorus", "loose live backbeat", "melodic muted bass guitar",
            "two-bar indie-pop changes", "delayed guitar motif", "open drums and layered clean guitars",
            "human fills and guitar reverses", "asymmetric guitar width with centered vocal", "balanced",
            "indie-pop instrumental with delayed clean guitar, loose live drums, muted bass, analog pads, and a bright organic chorus",
        ),
        ProducerProfile(
            "rnb_urban", "R&B Urban",
            ("electric piano", "tight drums", "rounded bass", "guitar textures", "atmospheric pads"),
            "laid-back pocket with a smooth hook lift", "behind-the-beat kick and rim pocket", "rounded syncopated bass movement",
            "extended seventh chords changing every two bars", "electric-piano voicings and texture", "richer pads and layered pocket",
            "reverse guitar tails and drum dropouts", "wide silk-like pads with close vocal center", "vocal_forward",
            "R&B urban instrumental with electric piano, a tight behind-the-beat pocket, rounded bass, sparse guitar texture, and smooth hook lift",
        ),
    )
}

DEFAULT_HINDI_PRODUCER_PROFILE_IDS = (
    "bollywood_acoustic",
    "modern_bollywood",
    "sufi_live",
    "punjabi_rhythm",
    "cinematic_urban",
)


@dataclass(frozen=True)
class AdaptiveMix:
    vocal_volume: float
    backing_volume: float
    ducking: str
    note: str


@dataclass(frozen=True)
class AudioClassifierPrediction:
    language: str | None = None
    language_confidence: float = 0.0
    genre: str | None = None
    genre_confidence: float = 0.0
    genre_approved: bool = False
    genre_probabilities: dict[str, float] = field(default_factory=dict)
    mood_probabilities: dict[str, float] = field(default_factory=dict)
    vocal_technique_probabilities: dict[str, float] = field(default_factory=dict)
    singing_speech: str | None = None
    singing_speech_confidence: float | None = None
    tempo_family: str | None = None
    melodic_character: str | None = None
    in_distribution_probability: float | None = None
    requires_confirmation: bool = True
    architecture: str | None = None
    device: str | None = None
    windows_analysed: int = 0
    trained_heads: dict[str, bool] = field(default_factory=dict)
    warning: str | None = None


@dataclass(frozen=True)
class BackingResult:
    output_path: Path
    generator: str
    generation_engine: str
    fallback_used: bool = False
    warning: str | None = None


def analyze_upload(
    *,
    upload_id: str,
    uploads_dir: str | Path,
    output_dir: str | Path | None = None,
    ffmpeg_path: str = "ffmpeg",
    whisper_path: str = "whisper",
    whisper_model: str = "base",
    whisper_timeout_sec: int = 180,
    melody_analyzer_backend: str = "off",
    basic_pitch_path: str = "basic-pitch",
    basic_pitch_model_serialization: str = "onnx",
    basic_pitch_save_note_events: bool = True,
    melody_timeout_sec: int = 120,
    audio_classifier_checkpoint: str | Path | None = None,
    audio_classifier_python_path: str | Path | None = None,
    audio_classifier_timeout_sec: int = 30,
    language_override: str | None = None,
    mood_override: str | None = None,
    url_for_path=None,
) -> SkarlyStudioAnalyzeResponse:
    upload = upload_service.get_upload(upload_id, uploads_dir=uploads_dir, url_for_path=url_for_path)
    if upload is None:
        raise FileNotFoundError("Upload not found")

    analysis_source, source_warning, long_audio = skarly_analysis_source(
        Path(upload.original_path),
        upload_id=upload.upload_id,
        uploads_dir=uploads_dir,
        duration_seconds=upload.duration_seconds,
        ffmpeg_path=ffmpeg_path,
    )
    report = vocal_analysis.analyze_vocal_audio(
        analysis_source,
        upload_id=upload.upload_id,
        normalized_output_dir=uploads_dir,
        url_for_path=url_for_path,
    )
    input_profile = profile_input_audio(Path(report.normalized_wav_path or upload.original_path))
    transcription = transcribe_with_whisper(
        Path(report.normalized_wav_path or upload.original_path),
        whisper_path=whisper_path,
        whisper_model=whisper_model,
        timeout_sec=whisper_timeout_sec,
    )
    classifier = predict_with_local_audio_classifier(
        Path(report.normalized_wav_path or analysis_source),
        checkpoint_path=audio_classifier_checkpoint,
        python_path=audio_classifier_python_path,
        timeout_sec=audio_classifier_timeout_sec,
    )
    melody = MelodyResult(None, "unavailable")
    analysis_url = None
    analysis_path: Path | None = None
    analysis_root: Path | None = None
    if output_dir is not None:
        analysis_job_id = new_skarly_job_id()
        paths = studio_paths(output_dir, analysis_job_id)
        paths.job_dir.mkdir(parents=True, exist_ok=True)
        analysis_root = paths.output_root
        if long_audio and (melody_analyzer_backend or "off").strip().lower() == "basic_pitch":
            melody = MelodyResult(None, "unavailable", "Basic Pitch MIDI was skipped for this long vocal; full-song timing and key analysis are still ready.")
        else:
            melody = create_melody_midi(
                Path(report.normalized_wav_path or analysis_source),
                paths.job_dir,
                bpm=int(round(float(report.estimated_bpm or 84))),
                analyzer_backend=melody_analyzer_backend,
                basic_pitch_path=basic_pitch_path,
                model_serialization=basic_pitch_model_serialization,
                save_note_events=basic_pitch_save_note_events,
                timeout_sec=melody_timeout_sec,
            )
        analysis_path = paths.job_dir / "analysis.json"
        analysis_url = skarly_output_url(analysis_path, paths.output_root)
    genre_hint, genre_confidence = infer_genre_hint(
        bpm=report.estimated_bpm,
        energy=input_profile.energy,
        mood=mood_override,
        source_profile=input_profile.source_profile,
    )
    genre_source = "audio_heuristic"
    if (
        (input_profile.source_profile == "full_song" or bool(classifier.architecture))
        and classifier.genre
        and classifier.genre_approved
        and classifier.genre_confidence >= MIN_GENRE_CLASSIFIER_CONFIDENCE
    ):
        genre_hint, genre_confidence = classifier.genre, classifier.genre_confidence
        genre_source = "shared_audio_encoder" if classifier.architecture else "local_cnn"
    predicted_language = classifier.language if classifier.language_confidence >= MIN_LANGUAGE_CLASSIFIER_CONFIDENCE else None
    classifier_source = "shared_audio_encoder" if classifier.architecture else "local_cnn"
    classification_source = "user_confirmed" if language_override else classifier_source if predicted_language else "whisper_audio"
    language_confidence = 1.0 if language_override else classifier.language_confidence if predicted_language else None
    detected = detected_from_analysis(
        report.estimated_bpm,
        report.estimated_key,
        report.pitch_contour_status,
        input_profile=input_profile,
        transcription=transcription,
        melody=melody,
        timing_summary=timing_summary_from_report(report),
        phrase_count=len(report.phrase_boundaries),
        song_structure=report.section_candidates,
        genre_hint=genre_hint,
        genre_confidence=genre_confidence,
        genre_source=genre_source,
        language_confidence=language_confidence,
        classification_source=classification_source,
        analysis_scope_seconds=report.duration_seconds,
        input_quality=input_quality_summary(report.quality_report),
        language_override=language_override or predicted_language,
        mood_override=mood_override,
    )
    detected = detected.model_copy(
        update={
            "genre_probabilities": classifier.genre_probabilities,
            "audio_intelligence": classifier_song_intelligence(classifier),
        }
    )
    song_map = enrich_song_intelligence_map(report.song_intelligence_map, detected, transcription)
    detected = detected.model_copy(update={"song_intelligence_map": song_map})
    warnings = [
        *report.warnings,
        *input_profile.warnings,
        *([source_warning] if source_warning else []),
        *([transcription.warning] if transcription.warning else []),
        *([classifier.warning] if classifier.warning else []),
        *([melody.warning] if melody.warning else []),
    ]
    if analysis_path is not None:
        write_analysis_manifest(
            analysis_path,
            upload_id=upload.upload_id,
            detected=detected,
            input_profile=input_profile,
            transcription=transcription,
            melody=melody,
            prompts=[],
            song_intelligence_map=song_map,
            warnings=warnings,
        )
    return SkarlyStudioAnalyzeResponse(
        job_id=analysis_url.split("/")[-2] if analysis_url else new_skarly_job_id(),
        upload_id=upload.upload_id,
        detected=detected,
        normalized_wav_url=report.normalized_wav_url,
        melody_midi_url=skarly_output_url(melody.midi_path, analysis_root) if analysis_root and melody.midi_path else None,
        analysis_url=analysis_url,
        song_intelligence_map=song_map,
        warnings=dedupe(warnings),
    )


def generate_versions(
    *,
    upload_id: str,
    uploads_dir: str | Path,
    output_dir: str | Path,
    ffmpeg_path: str = "ffmpeg",
    mixing_timeout_sec: int = 120,
    generator_backend: str = "procedural_v2",
    ace_step_base_url: str = "http://127.0.0.1:8001",
    ace_step_api_key: str | None = None,
    ace_step_timeout_seconds: int = 600,
    ace_step_download_timeout_seconds: int = 600,
    ace_step_poll_interval_seconds: float = 2.0,
    ace_step_infer_step: int = 20,
    ace_step_guidance_scale: float = 15.0,
    ace_step_max_duration_seconds: int = 300,
    ace_step_use_source_audio: bool = False,
    ace_step_source_task_type: str | None = None,
    ace_step_source_audio_strength: float = 0.45,
    ace_step_direct_enabled: bool = False,
    ace_step_repo_dir: str | Path | None = None,
    ace_step_python_path: str | Path | None = None,
    ace_step_fallback_to_procedural: bool = False,
    require_cuda: bool = False,
    allow_cpu_generation_fallback: bool = False,
    whisper_path: str = "whisper",
    whisper_model: str = "base",
    whisper_timeout_sec: int = 180,
    melody_analyzer_backend: str = "off",
    basic_pitch_path: str = "basic-pitch",
    basic_pitch_model_serialization: str = "onnx",
    basic_pitch_save_note_events: bool = True,
    melody_timeout_sec: int = 120,
    audio_classifier_checkpoint: str | Path | None = None,
    audio_classifier_python_path: str | Path | None = None,
    audio_classifier_timeout_sec: int = 30,
    stem_separator_backend: str = "off",
    demucs_path: str = "demucs",
    demucs_model: str = "htdemucs_ft",
    demucs_two_stems: str = "vocals",
    demucs_device: str = "cuda",
    separation_timeout_sec: int = 1200,
    language: str | None = None,
    mood: str | None = None,
    genre_override: str | None = None,
    bpm_override: float | None = None,
    key_override: str | None = None,
    training_opt_in: bool = False,
    training_feedback_enabled: bool = False,
    training_feedback_dir: str | Path = "data/consented_feedback",
    training_feedback_manifest: str | Path = "data/manifests/user_feedback.jsonl",
    mix_preset: str = DEFAULT_MIX_PRESET,
    arrangement_mode: str = "vocal_to_song",
    preserve_original_vocal: bool = True,
    reference_strength: float = 0.35,
    verify_music_transform_vocals: bool = False,
    music_transform_vocal_threshold_db: float = -24.0,
    music_transform_min_vocal_activity: float = 0.04,
    owner_id: str | None = None,
    preferred_style_families: list[str] | None = None,
    producer_profile_ids: list[str] | None = None,
    progress_callback: Callable[..., None] | None = None,
    url_for_path=None,
) -> SkarlyStudioResponse:
    emit_generation_progress(progress_callback, stage="validating_input", progress=1)
    preset_name = normalize_mix_preset(mix_preset)
    upload = upload_service.get_upload(upload_id, uploads_dir=uploads_dir, url_for_path=url_for_path)
    if upload is None:
        raise FileNotFoundError("Upload not found")

    backend = (generator_backend or "procedural_v2").strip().lower()
    cuda_info: dict[str, Any] | None = None
    if backend == "ace_step" and require_cuda:
        emit_generation_progress(progress_callback, stage="verifying_cuda", progress=3, model="acestep-v15-turbo")
        if allow_cpu_generation_fallback:
            raise RuntimeError("Invalid generation configuration: REQUIRE_CUDA=true cannot be combined with ALLOW_CPU_GENERATION_FALLBACK=true.")
        cuda_info = cuda_runtime.verify_cuda_runtime(str(ace_step_python_path or ""))
        emit_generation_progress(
            progress_callback,
            stage="verifying_cuda",
            progress=5,
            cuda_device=cuda_info.get("device"),
            model="acestep-v15-turbo",
        )
    effective_procedural_fallback = bool(ace_step_fallback_to_procedural and allow_cpu_generation_fallback)

    emit_generation_progress(progress_callback, stage="analysing_complete_vocal", progress=7)
    analysis_response = analyze_upload(
        upload_id=upload_id,
        uploads_dir=uploads_dir,
        output_dir=None,
        ffmpeg_path=ffmpeg_path,
        whisper_path=whisper_path,
        whisper_model=whisper_model,
        whisper_timeout_sec=whisper_timeout_sec,
        melody_analyzer_backend="off",
        audio_classifier_checkpoint=audio_classifier_checkpoint,
        audio_classifier_python_path=audio_classifier_python_path,
        audio_classifier_timeout_sec=audio_classifier_timeout_sec,
        language_override=language,
        mood_override=mood,
        url_for_path=url_for_path,
    )
    emit_generation_progress(progress_callback, stage="building_song_map", progress=18)
    job_id = analysis_response.job_id
    paths = studio_paths(output_dir, job_id)
    paths.job_dir.mkdir(parents=True, exist_ok=True)

    normalized_mode = str(arrangement_mode or "vocal_to_song").strip().lower().replace("-", "_")
    if normalized_mode not in {"vocal_to_song", "music_to_music", "full_song"}:
        raise ValueError(f"Unsupported arrangement mode: {arrangement_mode}")
    source_vocal = Path(upload.original_path)
    normalized_vocal = paths.job_dir / "source.wav"
    emit_generation_progress(progress_callback, stage="preparing_vocal", progress=20)
    normalize_vocal(source_vocal, normalized_vocal, ffmpeg_path=ffmpeg_path, timeout_sec=mixing_timeout_sec)
    input_profile = profile_input_audio(normalized_vocal)
    source_preparation = None
    music_reference_path: Path | None = None
    processed_vocal_path: Path | None = None
    should_mix_original_vocal = normalized_mode == "vocal_to_song" or (
        normalized_mode in {"music_to_music", "full_song"} and preserve_original_vocal
    )
    if normalized_mode in {"music_to_music", "full_song"}:
        # Music-to-music may receive either an actual instrumental or a full
        # commercial-style mix. Never assume a detected full song is already
        # clean: isolate its accompaniment before it becomes ACE context.
        source_requested_mode = (
            "full_song"
            if normalized_mode == "full_song" or input_profile.source_profile == "full_song"
            else "instrumental"
        )
        source_preparation = music_source.prepare_music_source(
            source_audio_path=str(normalized_vocal),
            requested_mode=source_requested_mode,
            preserve_original_vocal=should_mix_original_vocal,
            job_id=job_id,
            settings=SimpleNamespace(
                stems_output_dir=str(paths.job_dir / "source_stems"),
                stems_engine="demucs",
                stems_timeout_seconds=separation_timeout_sec,
                stems_enabled=(stem_separator_backend or "off").strip().lower() == "demucs",
                demucs_cli_path=demucs_path,
                demucs_model=demucs_model,
                demucs_device=demucs_device,
                music_to_music_vocal_threshold_db=-24.0,
                music_to_music_min_vocal_activity=0.04,
            ),
            url_for_path=url_for_path or (lambda _value: None),
        )
        if not source_preparation.instrumental_audio_path:
            raise RuntimeError(
                "Stage source_separation failed: a clean instrumental stem was not produced. "
                + " ".join(source_preparation.warnings[:3])
            )
        music_reference_path = Path(source_preparation.instrumental_audio_path)
        vocal_candidate = Path(source_preparation.vocal_audio_path) if source_preparation.vocal_audio_path else None
        if source_requested_mode == "full_song" and should_mix_original_vocal:
            leakage_quality = source_preparation.vocal_leakage_quality
            if vocal_candidate is None:
                raise RuntimeError("Stage source_separation failed: full-song preservation requires a validated vocal stem.")
            if leakage_quality is None or not leakage_quality.passed:
                detail = " ".join((leakage_quality.warnings if leakage_quality else ["No leakage report was produced."])[:2])
                raise RuntimeError(
                    "Stage vocal_leakage_check failed: Skarly will not mix a separated singer without a passing leakage report. "
                    + detail
                )
        analysis_audio = vocal_candidate if should_mix_original_vocal and vocal_candidate else music_reference_path
        vocal_for_mix = vocal_candidate if should_mix_original_vocal and vocal_candidate else None
        # Keep the exported/displayed vocal stem distinct from the audio used
        # to analyse or condition generation.  In music-to-music mode the
        # latter is deliberately no_vocals.wav, while "Processed Vocal" must
        # always resolve to the actual Demucs vocals.wav stem.
        processed_vocal_path = vocal_candidate if source_preparation.vocal_detected else None
        vocal_prep = VocalPrepResult(
            analysis_audio,
            source_preparation.detected_mode,
            tuple(source_preparation.warnings),
        )
    else:
        vocal_prep = prepare_vocal_source(
            normalized_vocal,
            paths.job_dir,
            input_profile=input_profile,
            stem_separator_backend=stem_separator_backend,
            demucs_path=demucs_path,
            demucs_model=demucs_model,
            demucs_two_stems=demucs_two_stems,
            demucs_device=demucs_device,
            timeout_sec=separation_timeout_sec,
        )
        analysis_audio = vocal_prep.vocal_path
        vocal_for_mix = vocal_prep.vocal_path
        processed_vocal_path = vocal_prep.vocal_path

    transcription = (
        TranscriptionResult(status="skipped")
        if normalized_mode == "music_to_music" and vocal_for_mix is None
        else transcribe_with_whisper(
            analysis_audio,
            whisper_path=whisper_path,
            whisper_model=whisper_model,
            timeout_sec=whisper_timeout_sec,
        )
    )

    versions: list[SkarlyVersion] = []
    warnings = [*analysis_response.warnings, *input_profile.warnings, *vocal_prep.warnings]
    if transcription.warning:
        warnings.append(transcription.warning)
    # Confirmation can use a short preview, but the final arrangement must read
    # the complete vocal so a two-minute song is not planned from its first 30s.
    full_report = vocal_analysis.analyze_vocal_audio(analysis_audio)
    duration = full_report.duration_seconds or safe_duration_seconds(analysis_audio) or safe_duration_seconds(normalized_vocal) or 12.0
    duration = studio_generation_duration(duration, ace_step_max_duration_seconds)
    if bpm_override is not None and not 40 <= float(bpm_override) <= 220:
        raise ValueError("Confirmed BPM must be between 40 and 220")
    bpm = float(bpm_override if bpm_override is not None else (full_report.estimated_bpm or analysis_response.detected.bpm or 84))
    confirmed_key = str(key_override or "").strip() or full_report.estimated_key or analysis_response.detected.key
    if key_override:
        key_name, scale_name = vocal_analysis._split_key_scale(confirmed_key)
        if scale_name not in {"major", "minor"}:
            raise ValueError("Confirmed key must include major or minor, for example D minor")
        confirmed_key = f"{key_name} {scale_name}"
    if bpm_override is not None:
        warnings.append(f"Creator-confirmed BPM override applied: {bpm:.2f} BPM.")
    if key_override:
        warnings.append(f"Creator-confirmed key override applied: {confirmed_key}.")
    if should_skip_melody_analysis(duration, melody_analyzer_backend):
        melody = MelodyResult(
            None,
            "skipped_long_audio",
            "Basic Pitch MIDI was skipped for this long vocal so full-song generation can proceed; timing and key analysis are still used.",
        )
    else:
        melody = create_melody_midi(
            analysis_audio,
            paths.job_dir,
            bpm=int(round(bpm)),
            analyzer_backend=melody_analyzer_backend,
            basic_pitch_path=basic_pitch_path,
            model_serialization=basic_pitch_model_serialization,
            save_note_events=basic_pitch_save_note_events,
            timeout_sec=melody_timeout_sec,
        )
    if melody.warning:
        warnings.append(melody.warning)
    classifier = predict_with_local_audio_classifier(
        analysis_audio,
        checkpoint_path=audio_classifier_checkpoint,
        python_path=audio_classifier_python_path,
        timeout_sec=audio_classifier_timeout_sec,
    )
    if classifier.warning:
        warnings.append(classifier.warning)
    genre_hint, genre_confidence = infer_genre_hint(
        bpm=bpm,
        energy=input_profile.energy,
        mood=mood or analysis_response.detected.mood,
        source_profile=input_profile.source_profile,
    )
    genre_source = "audio_heuristic"
    if (
        (input_profile.source_profile == "full_song" or bool(classifier.architecture))
        and classifier.genre
        and classifier.genre_approved
        and classifier.genre_confidence >= MIN_GENRE_CLASSIFIER_CONFIDENCE
    ):
        genre_hint, genre_confidence = classifier.genre, classifier.genre_confidence
        genre_source = "shared_audio_encoder" if classifier.architecture else "local_cnn"
    confirmed_genre = str(genre_override or "").strip()
    if confirmed_genre:
        genre_hint, genre_confidence, genre_source = confirmed_genre, 1.0, "user_confirmed"
    predicted_language = classifier.language if classifier.language_confidence >= MIN_LANGUAGE_CLASSIFIER_CONFIDENCE else None
    classifier_source = "shared_audio_encoder" if classifier.architecture else "local_cnn"
    classification_source = "user_confirmed" if language else classifier_source if predicted_language else analysis_response.detected.classification_source or "whisper_audio"
    language_confidence = 1.0 if language else classifier.language_confidence if predicted_language else analysis_response.detected.language_confidence
    detected = detected_from_analysis(
        bpm,
        confirmed_key,
        full_report.pitch_contour_status or ("available" if analysis_response.detected.vocal_type == "Singing" else "fallback"),
        input_profile=input_profile,
        transcription=transcription,
        melody=melody,
        timing_summary=timing_summary_from_report(full_report) or analysis_response.detected.timing_summary,
        phrase_count=len(full_report.phrase_boundaries) or analysis_response.detected.phrase_count,
        song_structure=full_report.section_candidates or analysis_response.detected.song_structure,
        genre_hint=genre_hint,
        genre_confidence=genre_confidence,
        genre_source=genre_source,
        language_confidence=language_confidence,
        classification_source=classification_source,
        analysis_scope_seconds=full_report.duration_seconds or duration,
        input_quality=input_quality_summary(full_report.quality_report),
        language_override=language or predicted_language,
        mood_override=mood,
    )
    detected = detected.model_copy(
        update={
            "genre_probabilities": classifier.genre_probabilities,
            "audio_intelligence": classifier_song_intelligence(classifier),
            "source_profile": (
                "full_song"
                if normalized_mode in {"music_to_music", "full_song"} and vocal_for_mix is not None
                else "instrumental"
                if normalized_mode == "music_to_music"
                else "full_song"
                if normalized_mode == "full_song"
                else detected.source_profile
            ),
        }
    )
    song_map = enrich_song_intelligence_map(full_report.song_intelligence_map, detected, transcription)
    song_map = apply_confirmed_musical_corrections(
        song_map,
        bpm_override=bpm_override,
        key_override=confirmed_key if key_override else None,
    )
    detected = detected.model_copy(update={"song_intelligence_map": song_map})
    emit_generation_progress(progress_callback, stage="building_song_map", progress=28)
    if training_opt_in and vocal_for_mix is not None:
        if not confirmed_genre:
            warnings.append("Training opt-in was not saved because a creator-confirmed genre is required.")
        elif not training_feedback_enabled:
            warnings.append("Training opt-in is disabled in this Skarly environment; no vocal was retained.")
        else:
            try:
                saved_example = training_feedback.save_opt_in_vocal_example(
                    vocal_for_mix,
                    feedback_dir=training_feedback_dir,
                    manifest_path=training_feedback_manifest,
                    language=detected.language,
                    genre=confirmed_genre,
                    job_id=job_id,
                )
                warnings.append(
                    f"Creator-consented {detected.language} genre example saved for the next local CNN training run: {saved_example.audio_path.name}."
                )
            except (FileNotFoundError, ValueError, OSError) as exc:
                warnings.append(f"Training opt-in could not be saved: {str(exc)[:160]}")
    version_plans = build_version_plans(
        detected=detected,
        duration=duration,
        lyrics=transcription.text,
        song_structure=full_report.section_candidates,
        preferred_style_families=preferred_style_families,
        producer_profile_ids=producer_profile_ids,
        variation_nonce=job_id,
        arrangement_mode=normalized_mode,
    )
    emit_generation_progress(progress_callback, stage="planning_arrangements", progress=30, total_arrangements=5)
    input_vocal_url = (
        skarly_output_url(processed_vocal_path, paths.output_root)
        if processed_vocal_path is not None
        else None
    )
    input_vocal_waveform = (
        build_waveform_peaks(processed_vocal_path, points=600, ffmpeg_path=ffmpeg_path)
        if processed_vocal_path is not None
        else []
    )

    previous_backings: list[Path] = []
    generation_seconds = 0.0
    peak_vram_mb = float((cuda_info or {}).get("peak_memory_mb") or 0)
    cpu_fallback = False
    for index, plan in enumerate(version_plans, start=1):
        arrangement_progress = 30 + ((index - 1) * 12)
        emit_generation_progress(
            progress_callback,
            stage="creating_arrangement",
            progress=arrangement_progress,
            current_arrangement=index,
            completed_arrangements=index - 1,
            total_arrangements=5,
        )
        backing = paths.job_dir / f"backing_{index}.wav"
        final_mp3 = paths.job_dir / f"final_mix_{index}.mp3"
        final_fallback_wav = paths.job_dir / f"final_mix_{index}.wav"
        backing_result: BackingResult | None = None
        similarity_note: str | None = None
        transformation_quality = None
        for reroll_attempt in range(MAX_DIVERSITY_GENERATION_ATTEMPTS):
            generation_started = time.perf_counter()
            try:
                with cuda_runtime.GpuMemorySampler(enabled=bool(cuda_info)) as memory_sampler:
                    backing_result = generate_backing(
                        output_path=backing,
                        plan=plan,
                        seconds=duration,
                        bpm=bpm,
                        key=detected.key,
                        language=detected.language,
                        mood=detected.mood,
                        energy=detected.energy,
                        version_index=index,
                        generator_backend=generator_backend,
                        ace_step_base_url=ace_step_base_url,
                        ace_step_api_key=ace_step_api_key,
                        ace_step_timeout_seconds=ace_step_timeout_seconds,
                        ace_step_download_timeout_seconds=ace_step_download_timeout_seconds,
                        ace_step_poll_interval_seconds=ace_step_poll_interval_seconds,
                        ace_step_infer_step=ace_step_infer_step,
                        ace_step_guidance_scale=ace_step_guidance_scale,
                        ace_step_max_duration_seconds=ace_step_max_duration_seconds,
                        # A full-song remix is intentionally routed through the
                        # vocal-to-music path after Demucs. The separated old
                        # instrumental remains available for diagnostics only;
                        # it must not condition the replacement arrangement.
                        source_audio_path=analysis_audio if normalized_mode == "full_song" else music_reference_path or analysis_audio,
                        use_source_audio=True if normalized_mode in {"music_to_music", "full_song"} else ace_step_use_source_audio,
                        source_task_type="cover" if normalized_mode in {"music_to_music", "full_song"} else ace_step_source_task_type,
                        source_audio_strength=reference_strength if normalized_mode in {"music_to_music", "full_song"} else ace_step_source_audio_strength,
                        ace_step_direct_enabled=ace_step_direct_enabled,
                        ace_step_repo_dir=ace_step_repo_dir,
                        ace_step_python_path=ace_step_python_path,
                        ace_step_fallback_to_procedural=effective_procedural_fallback,
                        ffmpeg_path=ffmpeg_path,
                        duration_conform_timeout_sec=mixing_timeout_sec,
                    )
            except Exception as exc:
                generation_seconds += time.perf_counter() - generation_started
                peak_vram_mb = max(peak_vram_mb, memory_sampler.peak_vram_mb)
                backing.unlink(missing_ok=True)
                if reroll_attempt == 0:
                    warnings.append(
                        f"{plan.name} failed during generation; Skarly kept the completed arrangements and retried this one with a fresh seed: {str(exc)[:140]}"
                    )
                    plan = reroll_version_plan(plan, reroll_attempt + 1)
                    version_plans[index - 1] = plan
                    continue
                raise RuntimeError(
                    f"Stage creating_arrangement failed for arrangement {index} of 5 ({plan.name}) after {reroll_attempt + 1} generation attempts. "
                    f"The {len(versions)} completed arrangements remain in job {job_id}. Error: {str(exc)[:240]}"
                ) from exc
            generation_seconds += time.perf_counter() - generation_started
            peak_vram_mb = max(peak_vram_mb, memory_sampler.peak_vram_mb)
            cpu_fallback = cpu_fallback or backing_result.fallback_used
            quality_reference_path = (
                analysis_audio if normalized_mode == "full_song" else music_reference_path
            )
            if quality_reference_path is not None:
                transformation_quality = music_transform_quality.assess_transformation(
                    source_audio_path=str(quality_reference_path),
                    output_audio_path=str(backing),
                    expected_duration_seconds=duration,
                    candidate_id=f"{job_id}_{index}_{reroll_attempt + 1}",
                    settings=SimpleNamespace(
                        music_to_music_verify_generated_vocals=verify_music_transform_vocals,
                        music_to_music_clean_generated_vocals=normalized_mode in {"music_to_music", "full_song"},
                        stems_output_dir=str(paths.job_dir / "quality_stems"),
                        stems_engine="demucs",
                        stems_timeout_seconds=separation_timeout_sec,
                        stems_enabled=(stem_separator_backend or "off").strip().lower() == "demucs",
                        demucs_cli_path=demucs_path,
                        music_to_music_vocal_threshold_db=music_transform_vocal_threshold_db,
                        music_to_music_min_vocal_activity=music_transform_min_vocal_activity,
                    ),
                    url_for_path=url_for_path or (lambda _value: None),
                )
                if not transformation_quality.passed:
                    quality_reason = "; ".join(transformation_quality.warnings[:3]) or "quality requirements were not met"
                    if reroll_attempt < MAX_DIVERSITY_GENERATION_ATTEMPTS - 1:
                        warnings.append(f"{plan.name} failed the music transformation check ({quality_reason}); Skarly rerolled it.")
                        backing.unlink(missing_ok=True)
                        plan = reroll_version_plan(plan, reroll_attempt + 1)
                        version_plans[index - 1] = plan
                        continue
                    backing.unlink(missing_ok=True)
                    raise RuntimeError(
                        f"Stage checking_music_transformation rejected arrangement {index} of 5 ({plan.name}) "
                        f"after {MAX_DIVERSITY_GENERATION_ATTEMPTS} attempts: {quality_reason}"
                    )
            musical_quality: MusicalCompatibilityQuality | None = None
            if vocal_for_mix is not None and normalized_mode in {"music_to_music", "full_song"}:
                musical_quality = musical_compatibility.assess_vocal_arrangement(
                    backing_audio_path=backing,
                    target_bpm=bpm,
                    target_key=detected.key or confirmed_key or "A minor",
                    song_map=song_map,
                )
                if not musical_quality.passed and not musical_quality.key_match:
                    target_key = musical_quality.target_key or detected.key or confirmed_key or "A minor"
                    correction_semitones = musical_compatibility.key_transposition_semitones(
                        musical_quality.output_key,
                        target_key,
                    )
                    if correction_semitones:
                        pre_correction_key = musical_quality.output_key
                        corrected_backing = paths.job_dir / f"backing_{index}_key_corrected.wav"
                        try:
                            musical_compatibility.transpose_backing_to_key(
                                input_audio_path=backing,
                                output_audio_path=corrected_backing,
                                semitones=correction_semitones,
                                ffmpeg_path=ffmpeg_path,
                                timeout_seconds=effective_mixing_timeout(
                                    mixing_timeout_sec,
                                    vocal_path=vocal_for_mix,
                                    backing_path=backing,
                                ),
                            )
                            corrected_quality = musical_compatibility.assess_vocal_arrangement(
                                backing_audio_path=corrected_backing,
                                target_bpm=bpm,
                                target_key=target_key,
                                song_map=song_map,
                            )
                            corrected_non_key_checks_passed = bool(
                                corrected_quality.tempo_match
                                and corrected_quality.melody_match
                                and corrected_quality.phrase_match
                                and corrected_quality.downbeat_match
                            )
                            if corrected_non_key_checks_passed:
                                corrected_backing.replace(backing)
                                direction = "up" if correction_semitones > 0 else "down"
                                post_correction_detected_key = corrected_quality.output_key
                                corrected_warnings = [
                                    warning
                                    for warning in corrected_quality.warnings
                                    if not warning.startswith("Backing key ")
                                ]
                                if not corrected_quality.key_match:
                                    corrected_warnings.append(
                                        f"The post-shift global key estimator reported {post_correction_detected_key or 'unknown'}, "
                                        "but timed vocal melody, tempo, phrase, and downbeat checks passed after the exact transposition."
                                    )
                                musical_quality = corrected_quality.model_copy(
                                    update={
                                        "output_key": target_key,
                                        "key_match": True,
                                        "key_match_method": "transposed_and_revalidated",
                                        "key_correction_applied": True,
                                        "key_correction_semitones": correction_semitones,
                                        "pre_correction_output_key": pre_correction_key,
                                        "post_correction_detected_key": post_correction_detected_key,
                                        "passed": True,
                                        "warnings": [
                                            *corrected_warnings,
                                            f"Backing was transposed {direction} {abs(correction_semitones)} semitone(s) "
                                            f"from {pre_correction_key} to match the preserved vocal key {target_key}.",
                                        ],
                                    }
                                )
                            else:
                                corrected_backing.unlink(missing_ok=True)
                                musical_quality = corrected_quality.model_copy(
                                    update={
                                        "pre_correction_output_key": pre_correction_key,
                                        "warnings": [
                                            *corrected_quality.warnings,
                                            f"Automatic {correction_semitones:+d}-semitone key correction did not pass revalidation.",
                                        ],
                                    }
                                )
                        except Exception as exc:
                            corrected_backing.unlink(missing_ok=True)
                            musical_quality = musical_quality.model_copy(
                                update={
                                    "warnings": [
                                        *musical_quality.warnings,
                                        f"Automatic key correction could not complete: {str(exc)[:180]}",
                                    ]
                                }
                            )
                if not musical_quality.passed:
                    quality_reason = "; ".join(musical_quality.warnings[:4]) or "musical compatibility requirements were not met"
                    if reroll_attempt < MAX_DIVERSITY_GENERATION_ATTEMPTS - 1:
                        warnings.append(
                            f"{plan.name} did not match the preserved vocal ({quality_reason}); Skarly rerolled it."
                        )
                        backing.unlink(missing_ok=True)
                        plan = reroll_version_plan(plan, reroll_attempt + 1, reason=quality_reason)
                        version_plans[index - 1] = plan
                        continue
                    backing.unlink(missing_ok=True)
                    raise RuntimeError(
                        f"Stage checking_vocal_compatibility rejected arrangement {index} of 5 ({plan.name}) "
                        f"after {MAX_DIVERSITY_GENERATION_ATTEMPTS} attempts: {quality_reason}"
                    )
            duplicate, similarity_note = backing_is_near_duplicate(
                backing,
                previous_backings,
                strict_style_diversity=vocal_for_mix is not None and normalized_mode in {"music_to_music", "full_song"},
            )
            if not duplicate:
                break
            if reroll_attempt < MAX_DIVERSITY_GENERATION_ATTEMPTS - 1:
                warnings.append(f"{plan.name} was too similar to an earlier backing ({similarity_note}); Skarly rerolled it with a new arrangement seed.")
                plan = reroll_version_plan(plan, reroll_attempt + 1)
                version_plans[index - 1] = plan
            else:
                backing.unlink(missing_ok=True)
                raise RuntimeError(
                    f"Stage checking_arrangement_diversity rejected arrangement {index} of 5 ({plan.name}) "
                    f"after {MAX_DIVERSITY_GENERATION_ATTEMPTS} fresh seeds. The {len(versions)} completed arrangements remain "
                    f"in job {job_id}. Similarity evidence: {similarity_note}"
                )
        assert backing_result is not None
        if backing_result.warning:
            warnings.append(backing_result.warning)
        previous_backings.append(backing)
        final_path = backing if vocal_for_mix is None else final_mp3
        adaptive_mix: AdaptiveMix | None = None
        emit_generation_progress(
            progress_callback,
            stage="mixing_vocals" if vocal_for_mix is not None else "validating_instrumental",
            progress=arrangement_progress + 8,
            current_arrangement=index,
            completed_arrangements=index - 1,
            total_arrangements=5,
        )
        if vocal_for_mix is not None:
            try:
                version_mix_preset = resolve_version_mix_preset(preset_name, plan.mix_mode)
                adaptive_mix = mix_vocal_forward(
                    vocal_path=vocal_for_mix,
                    backing_path=backing,
                    output_path=final_mp3,
                    preset_name=version_mix_preset,
                    ffmpeg_path=ffmpeg_path,
                    timeout_sec=mixing_timeout_sec,
                )
            except Exception as exc:
                warnings.append(f"{plan.name} MP3 mix fell back to WAV: {str(exc)[:160]}")
                mix_vocal_forward_wav_fallback(vocal_for_mix, backing, final_fallback_wav)
                final_path = final_fallback_wav

        versions.append(
            SkarlyVersion(
                name=plan.name,
                input_vocal_url=input_vocal_url,
                melody_midi_url=skarly_output_url(melody.midi_path, paths.output_root) if melody.midi_path else None,
                backing_url=skarly_output_url(backing, paths.output_root),
                final_mix_url=skarly_output_url(final_path, paths.output_root),
                waveforms=SkarlyWaveforms(
                    input_vocal=input_vocal_waveform,
                    backing=build_waveform_peaks(backing, points=600, ffmpeg_path=ffmpeg_path),
                    final_mix=build_waveform_peaks(final_path, points=600, ffmpeg_path=ffmpeg_path),
                ),
                prompt=plan.prompt,
                generator=backing_result.generator,
                generation_engine=backing_result.generation_engine,
                style_family=plan.style_family,
                instruments=list(plan.instruments),
                energy=plan.energy,
                rhythm_character=plan.rhythm_character,
                producer_mix_mode=plan.mix_mode,
                blueprint=plan.blueprint or {},
                seed=plan.seed,
                mix_note=(
                    adaptive_mix.note
                    if adaptive_mix
                    else "WAV fallback mix used."
                    if vocal_for_mix is not None
                    else "Instrumental-only output; no source vocal was mixed."
                ),
                fallback_used=backing_result.fallback_used,
                is_fallback=backing_result.fallback_used,
                transformation_quality=(
                    transformation_quality.model_dump(mode="json")
                    if transformation_quality is not None
                    else None
                ),
                musical_compatibility=musical_quality,
            )
        )
        emit_generation_progress(
            progress_callback,
            stage="creating_arrangement",
            progress=30 + (index * 12),
            current_arrangement=index,
            completed_arrangements=index,
            total_arrangements=5,
            completed_duration_seconds=float(duration),
            completed_outputs=[
                {
                    "index": output_index,
                    "name": version.name,
                    "style_family": version.style_family,
                    "backing_url": version.backing_url,
                    "final_mix_url": version.final_mix_url,
                }
                for output_index, version in enumerate(versions, start=1)
            ],
        )

    try:
        diversity_report = build_arrangement_diversity_report(
            previous_backings,
            strict_style_diversity=vocal_for_mix is not None and normalized_mode in {"music_to_music", "full_song"},
        )
    except Exception as exc:
        raise RuntimeError(f"Stage checking_arrangement_diversity could not evaluate all ten backing-track pairs: {str(exc)[:240]}") from exc
    if diversity_report.evaluated_pairs != 10 or not diversity_report.passed:
        raise RuntimeError(
            "Stage checking_arrangement_diversity did not pass all ten backing-track pairs. "
            f"Evaluated {diversity_report.evaluated_pairs}; rejected {diversity_report.rejected_pairs}."
        )
    emit_generation_progress(
        progress_callback,
        stage="checking_arrangement_diversity",
        progress=92,
        completed_arrangements=5,
        total_arrangements=5,
        completed_duration_seconds=float(duration),
    )
    generation_telemetry = GenerationTelemetry(
        cuda_available=bool((cuda_info or {}).get("cuda_available")),
        device=(cuda_info or {}).get("device"),
        device_capability=(cuda_info or {}).get("device_capability"),
        torch_version=(cuda_info or {}).get("torch_version"),
        torch_cuda_runtime=(cuda_info or {}).get("torch_cuda_runtime"),
        compiled_architectures=list((cuda_info or {}).get("compiled_architectures") or []),
        generation_backend="cuda" if cuda_info else ("unverified" if backend == "ace_step" else "cpu"),
        model="acestep-v15-turbo" if backend == "ace_step" else "procedural_v2",
        peak_vram_mb=round(peak_vram_mb, 2),
        generation_seconds=round(generation_seconds, 3),
        cpu_fallback=cpu_fallback,
    )
    analysis_path = paths.job_dir / "analysis.json"
    emit_generation_progress(
        progress_callback,
        stage="preparing_exports",
        progress=97,
        cuda_device=generation_telemetry.device,
        model=generation_telemetry.model,
    )
    write_analysis_manifest(
        analysis_path,
        upload_id=upload.upload_id,
        owner_id=owner_id,
        detected=detected,
        input_profile=input_profile,
        transcription=transcription,
        melody=melody,
        prompts=version_plans,
        generation_telemetry=generation_telemetry,
        arrangement_diversity=diversity_report,
        song_intelligence_map=song_map,
        warnings=warnings,
    )

    return SkarlyStudioResponse(
        job_id=job_id,
        detected=detected,
        versions=versions,
        mix_preset=preset_name,
        generator_backend=generator_backend,
        vocal_url=skarly_output_url(vocal_for_mix, paths.output_root) if vocal_for_mix is not None else None,
        melody_midi_url=skarly_output_url(melody.midi_path, paths.output_root) if melody.midi_path else None,
        analysis_url=skarly_output_url(analysis_path, paths.output_root),
        generation_telemetry=generation_telemetry,
        arrangement_diversity=diversity_report,
        song_intelligence_map=song_map,
        source_preparation=source_preparation.model_dump(mode="json") if source_preparation else None,
        warnings=dedupe(warnings),
    )


def emit_generation_progress(
    callback: Callable[..., None] | None,
    *,
    stage: str,
    progress: float,
    **fields: Any,
) -> None:
    if callback is not None:
        callback(stage=stage, progress=progress, **fields)


def detected_from_analysis(
    estimated_bpm: float | None,
    estimated_key: str | None,
    pitch_contour_status: str,
    *,
    input_profile: InputProfile | None = None,
    transcription: TranscriptionResult | None = None,
    melody: MelodyResult | None = None,
    timing_summary: str | None = None,
    phrase_count: int | None = None,
    song_structure: list[dict[str, Any]] | None = None,
    genre_hint: str | None = None,
    genre_confidence: float | None = None,
    genre_source: str | None = None,
    language_confidence: float | None = None,
    classification_source: str | None = None,
    analysis_scope_seconds: float | None = None,
    input_quality: tuple[str, str] | None = None,
    language_override: str | None,
    mood_override: str | None,
) -> SkarlyDetected:
    key = estimated_key or "A minor"
    energy = input_profile.energy if input_profile else "Medium"
    mood = mood_override or infer_mood(key=key, energy=energy)
    vocal_type = input_profile.vocal_type if input_profile else ("Singing" if pitch_contour_status in {"available", "fallback", "fallback_used"} else "Vocal")
    bpm = int(round(float(estimated_bpm or 84)))
    language_value = language_override or (transcription.language if transcription else None) or "Hindi"
    return SkarlyDetected(
        language=str(language_value).strip() or "Hindi",
        language_confidence=language_confidence,
        classification_source=classification_source,
        mood=mood.strip() or "Sad / Emotional",
        vocal_type=vocal_type,
        bpm=max(40, min(220, bpm)),
        key=key,
        timing_summary=timing_summary,
        phrase_count=phrase_count,
        song_structure=list(song_structure or []),
        genre_hint=genre_hint,
        genre_confidence=genre_confidence,
        genre_source=genre_source,
        analysis_scope_seconds=analysis_scope_seconds,
        lyrics_preview=short_text(transcription.text, 220) if transcription and transcription.text else None,
        source_profile=input_profile.source_profile if input_profile else None,
        energy=energy,
        input_quality=input_quality[0] if input_quality else None,
        input_quality_note=input_quality[1] if input_quality else None,
        melody_midi_status=melody.status if melody else "unavailable",
    )


def enrich_song_intelligence_map(
    song_map: SongIntelligenceMap | None,
    detected: SkarlyDetected,
    transcription: TranscriptionResult | None,
) -> SongIntelligenceMap | None:
    """Combine signal analysis with transparent language, mood, and genre context."""
    if song_map is None:
        return None
    primary = song_language_code(detected.language)
    transcript_language = song_language_code(transcription.language) if transcription and transcription.language else None
    secondary = transcript_language if transcript_language and transcript_language != primary else None
    language = SongLanguageInfo(
        primary=primary,
        secondary=secondary,
        confidence=max(0.0, min(1.0, float(detected.language_confidence or 0))),
    )
    moods = [
        token.strip().lower().replace(" ", "_")
        for token in str(detected.mood or "").replace("/", ",").split(",")
        if token.strip()
    ]
    genre_probabilities = detected.genre_probabilities or genre_probability_map(detected)
    confirmed = detected.genre_source == "user_confirmed"
    phrases = apply_global_delivery_prior(song_map.phrases, detected.audio_intelligence)
    lyrical_motifs, phrases, sections, structure_analysis = apply_transcript_structure_evidence(
        phrases,
        song_map.sections,
        song_map.structure_analysis,
        transcription,
    )
    return song_map.model_copy(
        update={
            "language": language,
            "mood": list(dict.fromkeys(moods)),
            "genre_probabilities": genre_probabilities,
            "genre_source": detected.genre_source or "unavailable",
            "genre_requires_confirmation": not confirmed,
            "audio_intelligence": detected.audio_intelligence,
            "phrases": phrases,
            "sections": sections,
            "lyrical_motifs": lyrical_motifs,
            "structure_analysis": structure_analysis,
        }
    )


def apply_confirmed_musical_corrections(
    song_map: SongIntelligenceMap | None,
    *,
    bpm_override: float | None,
    key_override: str | None,
) -> SongIntelligenceMap | None:
    """Apply creator-confirmed planning values while retaining measured timing evidence."""
    if song_map is None or (bpm_override is None and not key_override):
        return song_map
    tempo = song_map.tempo
    tonality = song_map.tonality
    chord_compatibility = song_map.chord_compatibility
    corrections = dict(song_map.confirmed_corrections)
    if bpm_override is not None:
        bpm = float(bpm_override)
        if not 40 <= bpm <= 220:
            raise ValueError("Confirmed BPM must be between 40 and 220")
        corrections["bpm"] = {
            "detected": tempo.bpm,
            "confirmed": round(bpm, 2),
            "source": "creator_confirmation",
        }
        bar_seconds = 4.0 * 60.0 / bpm
        tempo = tempo.model_copy(
            update={
                "bpm": round(bpm, 2),
                "confidence": 1.0,
                "half_time_bpm": round(bpm / 2.0, 2) if bpm / 2.0 >= 40 else None,
                "double_time_bpm": round(bpm * 2.0, 2) if bpm * 2.0 <= 220 else None,
                "downbeats": [
                    round(float(point), 3)
                    for point in np.arange(0.0, max(0.0, song_map.duration_seconds), bar_seconds)[:300]
                ],
                "source": "creator_confirmed_global_bpm",
            }
        )
    if key_override:
        key_name, scale_name = vocal_analysis._split_key_scale(key_override)
        if scale_name not in {"major", "minor"}:
            raise ValueError("Confirmed key must include major or minor, for example D minor")
        corrections["key"] = {
            "detected": f"{tonality.key} {tonality.scale}",
            "confirmed": f"{key_name} {scale_name}",
            "source": "creator_confirmation",
        }
        tonality = tonality.model_copy(
            update={
                "key": key_name,
                "scale": scale_name,
                "confidence": 1.0,
                "source": "creator_confirmed_key",
            }
        )
        chord_compatibility = vocal_analysis._chord_compatibility(
            key_name,
            scale_name,
            song_map.melody_curve,
        )
    return song_map.model_copy(
        update={
            "tempo": tempo,
            "tonality": tonality,
            "chord_compatibility": chord_compatibility,
            "confirmed_corrections": corrections,
        }
    )


def apply_global_delivery_prior(
    phrases: list[dict[str, Any]],
    audio_intelligence: SongAudioIntelligence | None,
) -> list[dict[str, Any]]:
    """Use a trained global head as a prior without claiming phrase-level certainty."""
    if audio_intelligence is None:
        return [dict(phrase) for phrase in phrases]
    label = str(audio_intelligence.singing_speech or "").strip().lower()
    confidence = float(audio_intelligence.singing_speech_confidence or 0.0)
    trained = bool(audio_intelligence.trained_heads.get("singing_speech"))
    if label not in {"singing", "speaking", "rap", "humming"} or confidence < 0.5 or not trained:
        return [dict(phrase) for phrase in phrases]
    normalized_label = "spoken" if label == "speaking" else label
    delivery = f"{normalized_label}_candidate" if audio_intelligence.requires_confirmation else normalized_label
    enriched: list[dict[str, Any]] = []
    for item in phrases:
        phrase = dict(item)
        phrase.update(
            {
                "delivery": delivery,
                "delivery_confidence": round(min(0.95, confidence), 3),
                "delivery_source": "trained_global_audio_head_prior",
                "delivery_requires_confirmation": bool(audio_intelligence.requires_confirmation),
            }
        )
        enriched.append(phrase)
    return enriched


def normalize_lyric_evidence(value: str | None) -> str:
    """Normalize Unicode lyrics for repetition matching without transliteration."""
    text = "".join(character if character.isalnum() else " " for character in str(value or "").casefold())
    return " ".join(text.split())


def apply_transcript_structure_evidence(
    phrases: list[dict[str, Any]],
    sections: list[dict[str, Any]],
    structure_analysis: dict[str, Any],
    transcription: TranscriptionResult | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Align timestamped Whisper segments and expose repeated lyric evidence.

    Whisper text without segment timestamps is not used to invent section
    timing. Repetition matches remain candidates because ASR errors and Hindi
    inflection can make two sung lines appear more or less similar than they are.
    """
    segment_rows = [
        dict(segment)
        for segment in (transcription.segments if transcription else ())
        if isinstance(segment, dict)
    ]
    structure = dict(structure_analysis or {})
    structure["transcription_text_available"] = bool(transcription and transcription.text)
    structure["transcription_timing_available"] = bool(segment_rows)
    if not segment_rows:
        structure["lyrical_repetition_group_count"] = 0
        structure["lyrical_motifs"] = []
        return [], [dict(phrase) for phrase in phrases], [dict(section) for section in sections], structure

    normalized_rows: list[dict[str, Any]] = []
    for index, segment in enumerate(segment_rows):
        normalized = normalize_lyric_evidence(segment.get("text"))
        try:
            start = max(0.0, float(segment.get("start_seconds") or 0.0))
            end = max(start, float(segment.get("end_seconds") or start))
        except (TypeError, ValueError):
            continue
        if not normalized or end <= start:
            continue
        normalized_rows.append(
            {
                "index": index,
                "start_seconds": start,
                "end_seconds": end,
                "text": str(segment.get("text") or "").strip(),
                "normalized": normalized,
                "tokens": set(normalized.split()),
            }
        )

    parent = {row["index"]: row["index"] for row in normalized_rows}

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for left_position, left in enumerate(normalized_rows):
        for right in normalized_rows[left_position + 1 :]:
            if left["normalized"] == right["normalized"]:
                union(left["index"], right["index"])
                continue
            left_tokens, right_tokens = left["tokens"], right["tokens"]
            if min(len(left_tokens), len(right_tokens)) < 3:
                continue
            union_size = len(left_tokens | right_tokens)
            similarity = len(left_tokens & right_tokens) / max(1, union_size)
            if similarity >= 0.82:
                union(left["index"], right["index"])

    grouped: dict[int, list[dict[str, Any]]] = {}
    for row in normalized_rows:
        grouped.setdefault(find(row["index"]), []).append(row)
    repeated_groups = sorted(
        (items for items in grouped.values() if len(items) >= 2),
        key=lambda items: float(items[0]["start_seconds"]),
    )
    motif_by_segment: dict[int, str] = {}
    lyrical_motifs: list[dict[str, Any]] = []
    for items in repeated_groups:
        motif_id = f"lyric_motif_{len(lyrical_motifs) + 1}"
        for row in items:
            motif_by_segment[int(row["index"])] = motif_id
        lyrical_motifs.append(
            {
                "motif_id": motif_id,
                "normalized_text": items[0]["normalized"],
                "occurrence_count": len(items),
                "occurrences": [
                    {
                        "start_seconds": round(float(row["start_seconds"]), 3),
                        "end_seconds": round(float(row["end_seconds"]), 3),
                        "text": row["text"],
                    }
                    for row in items
                ],
                "source": "timestamped_whisper_lyric_repetition",
                "candidate": True,
                "requires_confirmation": True,
            }
        )

    enriched_phrases: list[dict[str, Any]] = []
    for item in phrases:
        phrase = dict(item)
        start = float(phrase.get("start_seconds") or 0.0)
        end = float(phrase.get("end_seconds") or start)
        overlapping = [
            row
            for row in normalized_rows
            if float(row["end_seconds"]) > start and float(row["start_seconds"]) < end
        ]
        lyric_ids = sorted(
            {
                motif_by_segment[int(row["index"])]
                for row in overlapping
                if int(row["index"]) in motif_by_segment
            }
        )
        phrase["transcript_text"] = " ".join(dict.fromkeys(row["text"] for row in overlapping)) or None
        phrase["lexical_content_detected"] = bool(overlapping)
        phrase["lyric_motif_ids"] = lyric_ids
        phrase["repeated_lyrics"] = bool(lyric_ids)
        delivery = str(phrase.get("delivery") or "").lower()
        phrase["non_lexical_candidate"] = bool(
            not overlapping
            and any(token in delivery for token in ("sing", "sung", "humming"))
        )
        phrase["transcript_evidence_requires_confirmation"] = True
        enriched_phrases.append(phrase)

    enriched_sections: list[dict[str, Any]] = []
    for item in sections:
        section = dict(item)
        start = float(section.get("start_seconds") or 0.0)
        end = float(section.get("end_seconds") or start)
        overlapping_phrases = [
            phrase
            for phrase in enriched_phrases
            if float(phrase.get("end_seconds") or 0.0) > start
            and float(phrase.get("start_seconds") or 0.0) < end
        ]
        lyric_ids = sorted(
            {
                str(motif_id)
                for phrase in overlapping_phrases
                for motif_id in phrase.get("lyric_motif_ids") or []
            }
        )
        evidence = list(section.get("label_evidence") or [])
        if lyric_ids and "lyrical_repetition" not in evidence:
            evidence.append("lyrical_repetition")
        section["lyric_motif_ids"] = lyric_ids
        section["label_evidence"] = evidence
        if lyric_ids:
            section["label_confidence"] = round(
                min(0.9, float(section.get("label_confidence") or 0.0) + 0.1),
                3,
            )
        enriched_sections.append(section)

    structure["lyrical_repetition_group_count"] = len(lyrical_motifs)
    structure["lyrical_motifs"] = [motif["motif_id"] for motif in lyrical_motifs]
    structure["lyric_repetition_bearing_sections"] = [
        section.get("name")
        for section in enriched_sections
        if section.get("lyric_motif_ids")
    ]
    return lyrical_motifs, enriched_phrases, enriched_sections, structure


def classifier_song_intelligence(classifier: AudioClassifierPrediction) -> SongAudioIntelligence | None:
    if not classifier.architecture and not classifier.trained_heads:
        return None
    return SongAudioIntelligence(
        architecture=classifier.architecture,
        device=classifier.device,
        analysis_scope="complete",
        windows_analysed=max(0, classifier.windows_analysed),
        singing_speech=classifier.singing_speech,
        singing_speech_confidence=classifier.singing_speech_confidence,
        vocal_technique_probabilities=classifier.vocal_technique_probabilities,
        mood_probabilities=classifier.mood_probabilities,
        tempo_family=classifier.tempo_family,
        melodic_character=classifier.melodic_character,
        in_distribution_probability=classifier.in_distribution_probability,
        requires_confirmation=classifier.requires_confirmation,
        trained_heads=classifier.trained_heads,
    )


def song_language_code(value: str | None) -> str:
    normalized = " ".join(str(value or "").lower().replace("-", " ").split())
    codes = {
        "hindi": "hi",
        "hinglish": "hi",
        "hi": "hi",
        "english": "en",
        "en": "en",
        "urdu": "ur",
        "ur": "ur",
        "punjabi": "pa",
        "pa": "pa",
        "bengali": "bn",
        "bn": "bn",
        "tamil": "ta",
        "ta": "ta",
        "telugu": "te",
        "te": "te",
    }
    return codes.get(normalized, "unknown")


def genre_probability_map(detected: SkarlyDetected) -> dict[str, float]:
    if detected.genre_probabilities:
        return dict(sorted(detected.genre_probabilities.items(), key=lambda item: item[1], reverse=True))
    if not detected.genre_hint:
        return {}
    primary = genre_slug(detected.genre_hint)
    if detected.genre_source == "user_confirmed":
        return {primary: 1.0}
    confidence = max(0.05, min(0.95, float(detected.genre_confidence or 0.45)))
    hindi = song_language_code(detected.language) in {"hi", "ur", "pa"}
    alternates = (
        ["bollywood_ballad", "indian_acoustic_indie", "sufi"]
        if hindi
        else ["western_pop", "rnb_urban", "indie_acoustic"]
    )
    alternates = [candidate for candidate in alternates if candidate != primary][:2]
    remaining = max(0.0, 1.0 - confidence)
    probabilities = {primary: round(confidence, 3)}
    if alternates:
        weights = [0.6, 0.4] if len(alternates) == 2 else [1.0]
        for candidate, weight in zip(alternates, weights):
            probabilities[candidate] = round(remaining * weight, 3)
    return dict(sorted(probabilities.items(), key=lambda item: item[1], reverse=True))


def genre_slug(value: str) -> str:
    normalized = str(value).strip().lower().replace("&", " and ")
    slug = "".join(character if character.isalnum() else "_" for character in normalized)
    return "_".join(part for part in slug.split("_") if part) or "unknown"


def input_quality_summary(quality_report: Any | None) -> tuple[str, str]:
    """Turn raw input-level checks into a short, actionable studio message."""
    if quality_report is None:
        return "Checking", "Skarly will normalize the vocal and check the input level before mixing."
    if bool(getattr(quality_report, "is_silent", False)):
        return "Needs re-record", "No clear vocal signal was found. Record again in a quiet room with the microphone closer."
    if bool(getattr(quality_report, "clipping_detected", False)):
        return "Clipping", "This vocal is distorting. Lower the microphone gain and record again so Skarly can keep the music clean."
    peak_db = getattr(quality_report, "peak_db", None)
    if peak_db is not None and float(peak_db) < -35.0:
        return "Quiet", "The vocal is quite soft. Skarly can raise it, but a stronger dry recording will preserve more detail."
    if not bool(getattr(quality_report, "passed", True)):
        return "Needs attention", "Skarly found an input issue. Review the upload notes before generating."
    return "Ready", "Vocal level is usable. Skarly will keep the singer clear and duck the backing only during vocal phrases."


def normalize_mix_preset(value: str | None) -> str:
    normalized = (value or DEFAULT_MIX_PRESET).strip().lower()
    if normalized not in MIXING_PRESETS:
        raise ValueError(f"Unsupported Skarly mix preset: {value}")
    return normalized


def resolve_version_mix_preset(global_preset: str, producer_mix_mode: str | None) -> str:
    """Use each producer blueprint by default while preserving an explicit global override."""
    normalized_global = normalize_mix_preset(global_preset)
    if normalized_global != DEFAULT_MIX_PRESET:
        return normalized_global
    return normalize_mix_preset(producer_mix_mode or DEFAULT_MIX_PRESET)


def profile_input_audio(path: Path) -> InputProfile:
    warnings: list[str] = []
    try:
        samples, sample_rate = load_audio_for_profile(path)
    except Exception as exc:
        return InputProfile(
            source_profile="unknown",
            vocal_type="Vocal",
            energy="Medium",
            confidence=0.0,
            warnings=(f"Input profile fallback used: {str(exc)[:120]}",),
        )
    if samples.size == 0:
        return InputProfile("unknown", "Vocal", "Low", 0.0, ("Audio appears empty during profile analysis.",))

    mono = samples.mean(axis=1) if samples.ndim == 2 else samples
    rms = float(np.sqrt(np.mean(np.square(mono)))) if mono.size else 0.0
    energy = "Low" if rms < 0.04 else "High" if rms > 0.18 else "Medium"
    stereo_width = 0.0
    if samples.ndim == 2 and samples.shape[1] >= 2:
        left = samples[:, 0]
        right = samples[:, 1]
        stereo_width = float(np.sqrt(np.mean(np.square(left - right)))) / max(0.001, float(np.sqrt(np.mean(np.square(mono)))))

    bass_ratio = spectral_band_ratio(mono, sample_rate, high_hz=180)
    percussive_ratio = rough_percussive_ratio(mono, sample_rate)
    full_song_score = 0
    if stereo_width > 0.45:
        full_song_score += 2
    elif stereo_width > 0.18:
        full_song_score += 1
    if stereo_width > 0.25 and rms > 0.20:
        full_song_score += 1
    if bass_ratio > 0.16:
        full_song_score += 1
    if percussive_ratio > 0.26:
        full_song_score += 1

    if full_song_score >= 2:
        source_profile = "full_song"
        vocal_type = "Singing / Full Song"
        confidence = min(0.92, 0.55 + full_song_score * 0.13)
    else:
        source_profile = "vocal_only"
        vocal_type = "Singing"
        confidence = 0.72
    return InputProfile(
        source_profile=source_profile,
        vocal_type=vocal_type,
        energy=energy,
        confidence=confidence,
        warnings=tuple(warnings),
    )


def load_audio_for_profile(path: Path) -> tuple[np.ndarray, int]:
    try:
        import soundfile as sf

        samples, sample_rate = sf.read(str(path), always_2d=True, dtype="float32")
        return np.asarray(samples, dtype=np.float32), int(sample_rate)
    except Exception:
        return read_wav_float(path)


def spectral_band_ratio(mono: np.ndarray, sample_rate: int, *, high_hz: float) -> float:
    if mono.size == 0 or sample_rate <= 0:
        return 0.0
    window = mono[: min(len(mono), sample_rate * 8)]
    if window.size < 512:
        return 0.0
    spectrum = np.abs(np.fft.rfft(window * np.hanning(len(window))))
    freqs = np.fft.rfftfreq(len(window), d=1.0 / sample_rate)
    total = float(np.sum(spectrum)) or 1.0
    band = float(np.sum(spectrum[freqs <= high_hz]))
    return band / total


def rough_percussive_ratio(mono: np.ndarray, sample_rate: int) -> float:
    if mono.size == 0 or sample_rate <= 0:
        return 0.0
    hop = max(256, int(sample_rate * 0.02))
    frame = max(hop * 2, int(sample_rate * 0.06))
    energies: list[float] = []
    for start in range(0, max(1, len(mono) - frame), hop):
        chunk = mono[start : start + frame]
        energies.append(float(np.sqrt(np.mean(np.square(chunk)))) if chunk.size else 0.0)
    if len(energies) < 3:
        return 0.0
    diff = np.maximum(0.0, np.diff(np.asarray(energies, dtype=np.float32)))
    return float(np.percentile(diff, 90) / max(0.001, np.percentile(energies, 75)))


def transcribe_with_whisper(
    audio_path: Path,
    *,
    whisper_path: str,
    whisper_model: str,
    timeout_sec: int,
) -> TranscriptionResult:
    command = command_parts(whisper_path or "whisper")
    if not command_is_available(command):
        return TranscriptionResult(
            status="unavailable",
            warning="Language could not be identified automatically because Whisper is unavailable; Hindi was selected as the fallback.",
        )
    output_dir = audio_path.parent / "whisper"
    output_dir.mkdir(parents=True, exist_ok=True)
    args = [
        *command,
        str(audio_path),
        "--model",
        whisper_model or "base",
        "--output_format",
        "json",
        "--output_dir",
        str(output_dir),
    ]
    try:
            completed = subprocess.run(
                args,
                check=False,
                cwd=str(output_dir),
                env=skarly_subprocess_env(),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_sec,
            )
    except subprocess.TimeoutExpired:
        return TranscriptionResult(status="timeout", warning=f"Whisper timed out after {timeout_sec} seconds.")
    except Exception as exc:
        return TranscriptionResult(status="failed", warning=f"Whisper could not start: {str(exc)[:120]}")
    if completed.returncode != 0:
        return TranscriptionResult(status="failed", warning=f"Whisper failed: {useful_process_error(completed.stderr)}")
    json_files = sorted(output_dir.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
    if not json_files:
        return TranscriptionResult(status="unavailable", warning="Whisper completed but did not write JSON.")
    try:
        data = json.loads(json_files[0].read_text(encoding="utf-8"))
    except Exception as exc:
        return TranscriptionResult(status="failed", warning=f"Whisper JSON could not be parsed: {str(exc)[:120]}")
    language = normalize_language(data.get("language"))
    text = str(data.get("text") or "").strip() or None
    segments: list[dict[str, Any]] = []
    for item in data.get("segments") or []:
        if not isinstance(item, dict):
            continue
        try:
            start = max(0.0, float(item.get("start") or 0.0))
            end = max(start, float(item.get("end") or start))
        except (TypeError, ValueError):
            continue
        segment_text = str(item.get("text") or "").strip()
        if end <= start:
            continue
        segments.append(
            {
                "start_seconds": round(start, 3),
                "end_seconds": round(end, 3),
                "text": segment_text,
            }
        )
    return TranscriptionResult(
        language=language,
        text=text,
        segments=tuple(segments),
        status="available",
    )


def create_melody_midi(
    input_audio_path: Path,
    job_dir: Path,
    *,
    bpm: int,
    analyzer_backend: str,
    basic_pitch_path: str,
    model_serialization: str,
    save_note_events: bool,
    timeout_sec: int,
) -> MelodyResult:
    backend = (analyzer_backend or "off").strip().lower()
    if backend == "off":
        return MelodyResult(None, "unavailable")
    if backend != "basic_pitch":
        return MelodyResult(None, "unavailable", f"Unsupported melody analyzer: {analyzer_backend}")
    duration = safe_duration_seconds(input_audio_path)
    if duration and duration > 150:
        return MelodyResult(None, "unavailable", "Basic Pitch supports analysis up to 150 seconds in studio mode; the input is longer and melody MIDI was skipped.")
    command = command_parts(basic_pitch_path or "basic-pitch")
    if not command_is_available(command):
        return MelodyResult(None, "unavailable", "Basic Pitch unavailable; melody MIDI was skipped.")
    command = normalize_basic_pitch_command(command)
    preflight_warning = basic_pitch_preflight_warning(command)
    if preflight_warning:
        return MelodyResult(None, "unavailable", preflight_warning)

    output_dir = job_dir / "basic-pitch"
    output_dir.mkdir(parents=True, exist_ok=True)
    args = [
        *command,
        str(output_dir),
        str(input_audio_path),
        "--save-midi",
        "--model-serialization",
        model_serialization or "onnx",
        "--midi-tempo",
        str(max(40, min(220, int(bpm or 84)))),
    ]
    if save_note_events:
        args.append("--save-note-events")
    try:
        completed = subprocess.run(
            args,
            check=False,
            cwd=str(output_dir),
            env=skarly_subprocess_env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_sec,
        )
    except subprocess.TimeoutExpired:
        return MelodyResult(None, "timeout", f"Basic Pitch timed out after {timeout_sec} seconds.")
    except Exception as exc:
        return MelodyResult(None, "failed", f"Basic Pitch could not start: {str(exc)[:120]}")
    if completed.returncode != 0:
        return MelodyResult(None, "failed", f"Basic Pitch failed: {useful_process_error(completed.stderr)}")
    midi_candidates = sorted([*output_dir.rglob("*.mid"), *output_dir.rglob("*.midi")])
    if not midi_candidates:
        return MelodyResult(None, "unavailable", "Basic Pitch did not produce a MIDI file.")
    target = job_dir / "melody.mid"
    shutil.copyfile(midi_candidates[0], target)
    note_candidates = sorted(output_dir.rglob("*.csv"))
    if note_candidates:
        notes_target = job_dir / "notes.json"
        notes_target.write_text(csv_note_events_to_json(note_candidates[0]), encoding="utf-8")
    return MelodyResult(target, "available")


def prepare_vocal_source(
    normalized_vocal: Path,
    job_dir: Path,
    *,
    input_profile: InputProfile,
    stem_separator_backend: str,
    demucs_path: str,
    demucs_model: str,
    demucs_two_stems: str,
    demucs_device: str,
    timeout_sec: int,
) -> VocalPrepResult:
    if input_profile.source_profile != "full_song":
        return VocalPrepResult(normalized_vocal, input_profile.source_profile)
    if (stem_separator_backend or "off").strip().lower() != "demucs":
        raise RuntimeError(
            "Stage source_separation failed: a full song was detected but Demucs is disabled. "
            "Skarly will not mix an unseparated or center-estimated vocal into new music."
        )
    if str(demucs_two_stems or "vocals").strip().lower() != "vocals":
        raise RuntimeError(
            "Stage source_separation failed: SKARLY_DEMUCS_TWO_STEMS must be 'vocals' for full-song preservation."
        )
    separation = stems_service.separate_stems(
        audio_path=normalized_vocal,
        output_dir=job_dir / "demucs",
        job_id="lead_vocal",
        stems=["vocals", "no_vocals"],
        engine="demucs",
        timeout_seconds=max(1, int(timeout_sec)),
        enabled=True,
        demucs_cli_path=demucs_path or "python -m demucs",
        demucs_model=demucs_model or "htdemucs_ft",
        demucs_device=demucs_device or "cuda",
    )
    vocal_candidate = separation.stem_paths.get("vocals")
    instrumental_candidate = separation.stem_paths.get("no_vocals")
    separation_ok = separation.status in {"completed", "completed_partial"} and vocal_candidate and instrumental_candidate
    if not separation_ok:
        diagnostic_logs = separation.diagnostics.last_logs[-3:] if separation.diagnostics else []
        detail = " | ".join([*separation.warnings[:3], *diagnostic_logs])[:600]
        raise RuntimeError(
            "Stage source_separation failed: Demucs did not produce validated vocals and no_vocals stems. "
            f"{detail or separation.status}"
        )

    leakage_quality = music_source.assess_vocal_leakage(vocal_candidate, instrumental_candidate)
    if not leakage_quality.passed:
        detail = " ".join(leakage_quality.warnings[:2])
        raise RuntimeError(
            "Stage vocal_leakage_check failed: the separated vocal contains probable music leakage. "
            f"{detail}"
        )
    target = job_dir / "vocals_isolated.wav"
    shutil.copyfile(vocal_candidate, target)
    return VocalPrepResult(
        target,
        "full_song_demucs",
        ("Demucs htdemucs_ft separation passed the pre-mix vocal leakage gate.",),
        leakage_quality,
    )


def build_version_plans(
    *,
    detected: SkarlyDetected,
    duration: float,
    lyrics: str | None,
    song_structure: list[dict[str, Any]] | None = None,
    preferred_style_families: list[str] | None = None,
    producer_profile_ids: list[str] | None = None,
    variation_nonce: str | None = None,
    arrangement_mode: str = "vocal_to_song",
) -> list[VersionPlan]:
    bpm = detected.bpm or 84
    key = detected.key or "A minor"
    language = detected.language or "Hindi"
    mood = detected.mood or "Sad / Emotional"
    genre = detected.genre_hint or "vocal-led pop"
    lyric_context = f" Lyric context: {short_text(lyrics, 300)}." if lyrics else ""
    timing_context = f" Timing map: {detected.timing_summary}." if detected.timing_summary else ""
    structure_context = arrangement_map(song_structure or detected.song_structure, duration)
    mode = str(arrangement_mode or "vocal_to_song").strip().lower()
    source_direction = (
        "Create a genuinely new instrumental transformation from the uploaded music reference. Preserve only broad timing, harmony, and energy; replace the melody, rhythm details, instrumentation, and arrangement. "
        if mode == "music_to_music"
        else "Create a new instrumental replacement around the preserved singer (the separated original lead vocal). Keep the vocal timing synchronized and leave clear midrange space for the preserved lead. "
        if mode == "full_song"
        else f"Create an instrumental backing for the uploaded {language} vocal. "
    )
    common = (
        source_direction
        + f"Mood: {mood}. Genre direction: {genre}. Tempo around {bpm} BPM. Key: {key}. Duration about {int(duration)} seconds."
        + f"{lyric_context}{timing_context} Song map: {structure_context}. Place arrangement changes between vocal phrases when a vocal map exists. Use stable downbeats, warm low mids, and producer-style dynamics. "
        + "No generated singing, no lyric vocals, no humming, no ad-libs, no spoken words, and no copied melody."
    )
    requested_profiles = list(producer_profile_ids or (DEFAULT_HINDI_PRODUCER_PROFILE_IDS if is_hindi_language(language) else ()))
    selected_profiles = resolve_producer_profiles(requested_profiles) if requested_profiles else []
    if selected_profiles:
        styles = tuple((profile.name, profile.profile_id, profile.direction) for profile in selected_profiles)
    elif is_hindi_language(language):
        style_signal = f"{genre} {mood}".casefold()
        if any(token in style_signal for token in ("bollywood", "filmi")):
            styles = (
                ("Bollywood Romance", "bollywood_romance", "Bollywood romance instrumental: expressive piano motif, warm string ensemble, tabla-dholak pulse, melodic bass, and a spacious vocal-first chorus lift"),
                ("Filmi Acoustic", "filmi_acoustic", "Filmi acoustic instrumental: nylon guitar arpeggios, soft dholak, bansuri answers between vocal phrases, restrained bass, and an intimate cinematic bridge"),
                ("Retro Hindi Pop", "retro_hindi_pop", "retro Hindi-pop instrumental: lively dholak groove, bright electric piano, vintage-style synth accents, melodic bass, and a joyful instrumental hook without quoting any existing song"),
                ("Contemporary Bollywood Lift", "contemporary_bollywood", "contemporary Bollywood-pop instrumental: punchy kick and clap rhythm, lush modern pads, clean plucked hook, round sub bass, and a clear final-chorus lift"),
                ("Cinematic Hindi Finale", "cinematic_hindi", "cinematic Hindi instrumental: felt piano, low strings, restrained tabla pulse, wide orchestral swells, sparse opening, and a dramatic but vocal-safe outro"),
            )
        elif any(token in style_signal for token in ("devotional", "bhajan", "sufi", "qawwali", "spiritual")):
            styles = (
                ("Harmonium Bhajan", "bhajan", "devotional bhajan instrumental: harmonium, tabla, tanpura drone, gentle manjira, calm verse space, and a warm uplifting final refrain without any generated singing"),
                ("Sufi Acoustic", "sufi_acoustic", "Sufi-acoustic instrumental: expressive nylon guitar, restrained dholak, harmonium color, hand percussion, spacious dynamics, and a gradual emotional lift"),
                ("Qawwali Pulse", "qawwali_pulse", "qawwali-inspired instrumental: rhythmic tabla and handclap pulse, harmonium motifs, melodic bass, and energetic instrumental call-and-response with no choir or vocals"),
                ("Meditative Folk", "meditative_folk", "meditative Indian folk instrumental: bansuri phrases between vocal lines, soft tanpura, brushed frame drum, earthy acoustic strings, and generous breathing room"),
                ("Cinematic Devotional", "cinematic_devotional", "cinematic devotional instrumental: piano motif, low strings, tabla-inspired pulse, temple-bell texture used sparingly, and a wide emotional outro"),
            )
        elif "punjabi" in style_signal:
            styles = (
                ("Punjabi Pop Lift", "punjabi_pop", "modern Punjabi-pop instrumental: punchy dhol groove, bright tumbi accents, synth bass, clipped claps, and a celebratory final hook lift"),
                ("Punjabi Folk Acoustic", "punjabi_folk", "Punjabi folk-acoustic instrumental: tumbi and acoustic guitar motifs, dholak, warm bass, open verse space, and organic instrumental fills"),
                ("Punjabi Urban Bounce", "punjabi_urban", "Punjabi urban instrumental: tight dhol-sampled rhythm, deep 808 bass, sparse synth plucks, modern percussion, and a clean club-ready hook"),
                ("Punjabi Lo-fi Nights", "punjabi_lofi", "Punjabi lo-fi instrumental: half-time breakbeat, tape-warm keys, soft tumbi fragments, mellow sub bass, and a late-night spacious mix"),
                ("Punjabi Cinematic Anthem", "punjabi_cinematic", "Punjabi cinematic instrumental: folk-string motif, wide drums, low strings, dhol pulse, and a dramatic instrumental outro"),
            )
        elif any(token in style_signal for token in ("r&b", "rnb", "hip-hop", "hiphop", "trap", "urban")):
            styles = (
                ("Hindi R&B Glow", "hindi_rnb", "Hindi R&B instrumental: warm electric piano, rounded bass, tight drum pocket, sparse guitar textures, and smooth chorus lift"),
                ("Hindi Hip-hop Pulse", "hindi_hiphop", "Hindi hip-hop instrumental: crisp kick and snare pattern, melodic bass, restrained synth hook, rhythmic breaks between phrases, and no generated rap vocal"),
                ("Hindi Trap Soul", "hindi_trap_soul", "Hindi trap-soul instrumental: soft 808 bass, controlled hi-hat rolls, moody keys, atmospheric pads, and an emotional hook lift"),
                ("Hindi Neo-soul", "hindi_neo_soul", "Hindi neo-soul instrumental: jazzy electric piano chords, laid-back live-feel drums, warm bass guitar, and rich but uncluttered harmony"),
                ("Hindi Cinematic Urban", "hindi_cinematic_urban", "Hindi cinematic-urban instrumental: piano motif, sub bass, restrained trap percussion, low strings, and a wide final instrumental rise"),
            )
        else:
            styles = (
                ("Hindi Pop Mood Match", "hindi_pop", "modern Hindi-pop: syncopated electronic kick and clap groove, warm electric piano, round melodic bass, short hook synth, and a clean final chorus lift"),
                ("Acoustic Hindi Ballad", "acoustic_ballad", "unplugged acoustic ballad: nylon guitar arpeggios, felt piano, hand percussion, soft bass, open breathing room in verses, and no electronic drum kit"),
                ("Hindi Indie Pop", "indie_pop", "Hindi indie-pop: clean electric guitar delay, live-style snare and toms, muted bass guitar, airy analog pads, and a brighter rhythmic chorus"),
                ("Lo-fi Hindi Nights", "lofi", "late-night lo-fi: half-time dusty breakbeat, tape-warm Rhodes, mellow sub bass, restrained vinyl texture, and occasional bansuri-like instrumental fills"),
                ("Cinematic Hindi Score", "cinematic", "cinematic Hindi score: piano motif, low strings, tabla-inspired pulse, wide orchestral swells, sparse opening, and a dramatic instrumental outro"),
            )
    else:
        styles = (
            ("Original Mood Match", "modern_pop", "modern pop: restrained electronic drums, warm keys, melodic bass, and subtle phrase lifts"),
            ("Piano Heartbreak", "piano_ballad", "intimate piano ballad: felt piano, soft sub bass, sparse percussion, close-room reverb, and emotional chord movement"),
            ("Guitar Ballad", "guitar_ballad", "acoustic ballad: guitar arpeggios, gentle bass, brushed percussion, and a wide but simple chorus lift"),
            ("Lo-fi Sad Version", "lofi", "lo-fi version: half-time drums, tape keys, mellow bass, vinyl texture, and a late-night emotional atmosphere"),
            ("Cinematic Emotional", "cinematic", "cinematic version: piano motif, low strings, restrained percussion, soft orchestral swells, and a dramatic outro"),
        )
    style_by_family = {family: (name, family, direction) for name, family, direction in styles}
    preferred_families = [
        family
        for family in (preferred_style_families or [])
        if family in style_by_family
    ]
    preferred_families = list(dict.fromkeys(preferred_families))
    if preferred_families:
        preferred_styles = [style_by_family[family] for family in preferred_families]
        remaining_styles = [style for style in styles if style[1] not in preferred_families]
        styles = tuple([*preferred_styles, *remaining_styles])
    negative = "lead vocals, lyric vocals, humming, ad-libs, spoken words, artist imitation, copyrighted melody, clipping, muddy mix"
    plans: list[VersionPlan] = []
    for index, (name, family, direction) in enumerate(styles, start=1):
        profile = PRODUCER_PROFILE_CATALOG.get(family)
        seed = stable_plan_seed(
            language=language,
            mood=mood,
            key=key,
            bpm=bpm,
            family=family,
            index=index,
            variation_nonce=variation_nonce,
        )
        preference_context = (
            " Creator preference signal: this style family was selected in a previous song; give it extra musical care while still using a fresh groove, harmonic rhythm, and instrument entrances."
            if preferred_families and family == preferred_families[0]
            else ""
        )
        prompt = (
            f"{common} Version direction: {direction}. This must be clearly different from a generic pop backing: "
            f"use the {family.replace('_', ' ')} groove, instrument palette, harmonic rhythm, and arrangement arc."
            f"{profile_blueprint_prompt(profile) if profile else ''}"
            f"{preference_context}"
        )
        plans.append(
            VersionPlan(
                name=name,
                prompt=prompt,
                negative_prompt=negative,
                style_family=family,
                seed=seed,
                instruments=profile.instruments if profile else (),
                energy=profile.energy if profile else "adaptive",
                rhythm_character=profile.rhythm_character if profile else "vocal-following",
                mix_mode=profile.mix_mode if profile else "balanced",
                blueprint=profile.blueprint() if profile else None,
            )
        )
    return plans


def resolve_producer_profiles(profile_ids: list[str] | tuple[str, ...]) -> list[ProducerProfile]:
    normalized = [str(profile_id).strip().lower().replace("-", "_") for profile_id in profile_ids]
    if len(normalized) != 5:
        raise ValueError("Exactly five producer profile IDs are required.")
    if len(set(normalized)) != 5:
        raise ValueError("Producer profile IDs must be unique so all five arrangements use different blueprints.")
    unknown = [profile_id for profile_id in normalized if profile_id not in PRODUCER_PROFILE_CATALOG]
    if unknown:
        supported = ", ".join(PRODUCER_PROFILE_CATALOG)
        raise ValueError(f"Unsupported producer profile: {unknown[0]}. Supported profiles: {supported}")
    return [PRODUCER_PROFILE_CATALOG[profile_id] for profile_id in normalized]


def profile_blueprint_prompt(profile: ProducerProfile) -> str:
    blueprint = profile.blueprint()
    constraints = "; ".join(f"{key.replace('_', ' ')}={value}" for key, value in blueprint.items())
    return f" Hard producer blueprint: {constraints}."


def arrangement_map(sections: list[dict[str, Any]], duration: float) -> str:
    if sections:
        labels = []
        for item in sections[:8]:
            name = str(item.get("name") or item.get("section") or "section")
            start = item.get("start_seconds", item.get("start", None))
            end = item.get("end_seconds", item.get("end", None))
            cues: list[str] = []
            if item.get("motif_ids"):
                cues.append("repeated vocal motif")
            if item.get("lyric_motif_ids"):
                cues.append("repeated lyric refrain")
            density = item.get("rhythmic_density_onsets_per_second")
            if density is not None:
                density_value = float(density)
                cues.append("sparse rhythm" if density_value < 1.0 else "active rhythm" if density_value >= 2.5 else "medium rhythm")
            energy = item.get("mean_relative_energy")
            if energy is not None:
                energy_value = float(energy)
                cues.append("low energy" if energy_value < 0.3 else "high energy" if energy_value >= 0.7 else "mid energy")
            cue_text = f" ({', '.join(cues)})" if cues else ""
            if start is not None and end is not None:
                labels.append(f"{name} {float(start):.0f}-{float(end):.0f}s{cue_text}")
            else:
                labels.append(f"{name}{cue_text}")
        if labels:
            return ", ".join(labels)
    if duration >= 100:
        return "intro, verse 1, hook, verse 2, bridge, final hook, outro"
    if duration >= 45:
        return "intro, verse, hook, verse variation, final hook, outro"
    return "brief intro, vocal section, hook lift, outro"


def stable_plan_seed(
    *,
    language: str,
    mood: str,
    key: str,
    bpm: int,
    family: str,
    index: int,
    variation_nonce: str | None = None,
) -> int:
    source = f"{language}|{mood}|{key}|{bpm}|{family}|{index}|{variation_nonce or ''}"
    return 10_000 + sum((position + 1) * ord(char) for position, char in enumerate(source)) % 900_000


def reroll_version_plan(plan: VersionPlan, attempt: int, *, reason: str | None = None) -> VersionPlan:
    """Change both the latent seed and prompt when a generated backing is a duplicate."""
    seed = ((int(plan.seed or 10_000) + 79_189 * max(1, attempt)) % 900_000) + 10_000
    correction = f" Correct the rejected render: {short_text(reason, 320)}." if reason else ""
    prompt = (
        f"{plan.prompt} Diversity reroll {attempt}: make a clearly fresh arrangement within the same "
        f"{plan.style_family.replace('_', ' ')} family; change the groove, instrument entrances, fills, "
        f"and harmonic rhythm. Do not repeat an earlier backing.{correction}"
    )
    return replace(plan, prompt=prompt, seed=seed)


def backing_is_near_duplicate(
    candidate_path: Path,
    earlier_paths: list[Path],
    *,
    strict_style_diversity: bool = False,
) -> tuple[bool, str | None]:
    """Reject renders that are waveform- or arrangement-level duplicates.

    A byte-for-byte or lightly altered duplicate is caught with waveform
    correlation.  Generators can also return the same arrangement with a phase
    shift, mild remaster, or different container encoding; those versions need
    an independent, strict frequency-profile check before they use one of the
    five valuable producer slots.
    """
    if not earlier_paths:
        return False, None
    try:
        candidate, sample_rate = load_audio_for_profile(candidate_path)
        candidate_mono = np.asarray(candidate, dtype=np.float32).mean(axis=1)
    except Exception:
        return False, None
    if candidate_mono.size < 2:
        return False, None
    # A 24-second excerpt is long enough to reject an identical rendered tune,
    # but short enough to keep five-version generation responsive.
    excerpt_samples = min(candidate_mono.size, max(2, int(sample_rate * 24)))
    candidate_excerpt = candidate_mono[:excerpt_samples]
    candidate_fingerprint = arrangement_spectral_fingerprint(candidate_excerpt, sample_rate)
    try:
        candidate_features = extract_arrangement_audio_features(candidate_mono, sample_rate)
    except Exception:
        candidate_features = None
    for earlier_path in earlier_paths:
        try:
            earlier, earlier_rate = load_audio_for_profile(earlier_path)
            earlier_mono = np.asarray(earlier, dtype=np.float32).mean(axis=1)
        except Exception:
            continue
        if earlier_mono.size < 2:
            continue
        if earlier_rate == sample_rate:
            length = min(len(candidate_excerpt), len(earlier_mono))
            if length >= sample_rate * 3:
                left = candidate_excerpt[:length]
                right = earlier_mono[:length]
                left = left - float(np.mean(left))
                right = right - float(np.mean(right))
                denominator = float(np.linalg.norm(left) * np.linalg.norm(right))
                if denominator > 1e-8:
                    correlation = float(np.dot(left, right) / denominator)
                    mean_absolute_error = float(np.mean(np.abs(left - right)))
                    if correlation >= 0.965 and mean_absolute_error <= 0.035:
                        return True, f"waveform correlation {correlation:.3f}, difference {mean_absolute_error:.3f} against {earlier_path.name}"
        earlier_fingerprint = arrangement_spectral_fingerprint(earlier_mono, earlier_rate)
        if candidate_fingerprint is None or earlier_fingerprint is None:
            continue
        fingerprint_length = min(candidate_fingerprint.size, earlier_fingerprint.size)
        if fingerprint_length < 8:
            continue
        left_fingerprint = candidate_fingerprint[:fingerprint_length]
        right_fingerprint = earlier_fingerprint[:fingerprint_length]
        fingerprint_correlation = float(np.dot(left_fingerprint, right_fingerprint))
        fingerprint_error = float(np.mean(np.abs(left_fingerprint - right_fingerprint)))
        # This threshold is intentionally much stricter than the waveform gate:
        # versions in the same key and tempo are allowed, but a phase-shifted or
        # lightly remastered copy is rerolled.
        if fingerprint_correlation >= 0.995 and fingerprint_error <= 0.020:
            return True, f"arrangement fingerprint correlation {fingerprint_correlation:.3f}, difference {fingerprint_error:.3f} against {earlier_path.name}"
        if candidate_features is not None:
            try:
                earlier_features = extract_arrangement_audio_features(earlier_mono, earlier_rate)
                metrics = arrangement_similarity_metrics(candidate_features, earlier_features)
                reason = arrangement_similarity_rejection_reason(
                    metrics,
                    strict_style_diversity=strict_style_diversity,
                )
            except Exception:
                reason = None
            if reason:
                return True, f"{reason} against {earlier_path.name}"
    return False, None


def arrangement_spectral_fingerprint(mono: np.ndarray, sample_rate: int) -> np.ndarray | None:
    """Return a compact, amplitude-invariant profile for duplicate detection."""
    if sample_rate <= 0:
        return None
    samples = np.asarray(mono, dtype=np.float32).reshape(-1)
    excerpt = samples[: min(samples.size, int(sample_rate * 24))]
    if excerpt.size < sample_rate * 3:
        return None
    excerpt = excerpt - float(np.mean(excerpt))
    # Do not apply a time-domain window here. A window changes the magnitude
    # spectrum of a circularly phase-shifted render, exactly the alternate
    # duplicate form this guard is meant to catch.
    spectrum = np.abs(np.fft.rfft(excerpt))
    frequencies = np.fft.rfftfreq(excerpt.size, d=1.0 / sample_rate)
    upper_hz = min(3_800.0, sample_rate * 0.47)
    if upper_hz <= 50.0:
        return None
    edges = np.geomspace(50.0, upper_hz, num=33)
    bands: list[float] = []
    for start, end in zip(edges[:-1], edges[1:]):
        mask = (frequencies >= start) & (frequencies < end)
        bands.append(float(np.log(np.mean(spectrum[mask]) + 1e-7)) if np.any(mask) else -16.0)
    fingerprint = np.asarray(bands, dtype=np.float32)
    fingerprint -= float(np.mean(fingerprint))
    norm = float(np.linalg.norm(fingerprint))
    return fingerprint / norm if norm > 1e-7 else None


def extract_arrangement_audio_features(mono: np.ndarray, sample_rate: int) -> ArrangementAudioFeatures:
    """Build a compact perceptual embedding plus rhythm/harmony/timbre views.

    The complete backing remains the source. For long songs, equal windows from
    the beginning, middle, and end are used so the gate does not silently judge
    only the intro. The embedding is intentionally model-independent and is
    stable across gain changes and common container encodings.
    """
    samples = representative_diversity_audio(mono, sample_rate)
    target_rate = 16_000
    frame_size = 1024
    hop_size = 512
    if samples.size < frame_size:
        samples = np.pad(samples, (0, frame_size - samples.size))
    frame_count = 1 + max(0, (samples.size - frame_size) // hop_size)
    starts = np.arange(frame_count, dtype=np.int64) * hop_size
    window = np.hanning(frame_size).astype(np.float32)
    frames = np.stack([samples[start : start + frame_size] * window for start in starts])
    magnitudes = np.abs(np.fft.rfft(frames, axis=1)).astype(np.float32) + 1e-8
    powers = np.square(magnitudes)
    frequencies = np.fft.rfftfreq(frame_size, d=1.0 / target_rate)

    edges = np.geomspace(40.0, min(7_600.0, target_rate * 0.47), num=33)
    band_energy = np.zeros((frame_count, 32), dtype=np.float32)
    for band_index, (start_hz, end_hz) in enumerate(zip(edges[:-1], edges[1:])):
        mask = (frequencies >= start_hz) & (frequencies < end_hz)
        if np.any(mask):
            band_energy[:, band_index] = np.mean(powers[:, mask], axis=1)
    band_energy = np.log1p(band_energy)
    band_distribution = band_energy / np.maximum(np.sum(band_energy, axis=1, keepdims=True), 1e-8)
    band_mean = np.mean(band_distribution, axis=0)
    band_std = np.std(band_distribution, axis=0)

    # Preserve section-to-section timbre movement in eight bounded pools.
    pooled_sections: list[np.ndarray] = []
    for section in np.array_split(band_distribution, 8):
        section_mean = np.mean(section, axis=0) if section.size else band_mean
        pooled_sections.append(section_mean.reshape(8, 4).sum(axis=1))
    section_profile = np.concatenate(pooled_sections)

    magnitude_total = np.maximum(np.sum(magnitudes, axis=1), 1e-8)
    centroid = np.sum(magnitudes * frequencies[None, :], axis=1) / magnitude_total
    bandwidth = np.sqrt(
        np.sum(magnitudes * np.square(frequencies[None, :] - centroid[:, None]), axis=1) / magnitude_total
    )
    flatness = np.exp(np.mean(np.log(magnitudes), axis=1)) / np.maximum(np.mean(magnitudes, axis=1), 1e-8)
    descriptors = np.asarray(
        [
            np.mean(centroid) / (target_rate / 2),
            np.std(centroid) / (target_rate / 2),
            np.mean(bandwidth) / (target_rate / 2),
            np.std(bandwidth) / (target_rate / 2),
            np.mean(flatness),
            np.std(flatness),
        ],
        dtype=np.float32,
    )
    embedding = unit_feature_vector(np.concatenate([band_mean, band_std, section_profile, descriptors]))

    normalized_magnitudes = magnitudes / magnitude_total[:, None]
    spectral_flux = np.maximum(0.0, np.diff(normalized_magnitudes, axis=0)).sum(axis=1)
    drum_onsets = resample_feature_pattern(spectral_flux, 128)

    chroma = np.zeros((frame_count, 12), dtype=np.float32)
    valid_frequency = frequencies >= 50.0
    valid_bins = np.flatnonzero(valid_frequency)
    if valid_bins.size:
        midi = np.rint(69.0 + (12.0 * np.log2(frequencies[valid_bins] / 440.0))).astype(int)
        pitch_classes = np.mod(midi, 12)
        for pitch_class in range(12):
            bins = valid_bins[pitch_classes == pitch_class]
            if bins.size:
                chroma[:, pitch_class] = np.sum(powers[:, bins], axis=1)
    chroma /= np.maximum(np.sum(chroma, axis=1, keepdims=True), 1e-8)
    chord_change_strength = np.sum(np.abs(np.diff(chroma, axis=0)), axis=1) * 0.5
    chord_changes = resample_feature_pattern(chord_change_strength, 128)

    broad_bands = band_mean.reshape(8, 4).sum(axis=1)
    transient_density = float(np.mean(spectral_flux > (np.median(spectral_flux) + np.std(spectral_flux)))) if spectral_flux.size else 0.0
    instrumentation = unit_feature_vector(
        np.concatenate(
        [
            broad_bands,
            descriptors,
            np.asarray([transient_density, rough_percussive_ratio(samples, target_rate)], dtype=np.float32),
        ]
        )
    )
    return ArrangementAudioFeatures(
        embedding=embedding,
        drum_onsets=drum_onsets,
        chord_changes=chord_changes,
        instrumentation=instrumentation,
    )


def representative_diversity_audio(mono: np.ndarray, sample_rate: int) -> np.ndarray:
    if sample_rate <= 0:
        raise ValueError("A valid sample rate is required for diversity analysis")
    samples = np.nan_to_num(np.asarray(mono, dtype=np.float32).reshape(-1))
    if samples.size < max(256, sample_rate // 2):
        raise ValueError("The backing is too short for diversity analysis")
    max_seconds = 30
    if samples.size > sample_rate * max_seconds:
        window = sample_rate * (max_seconds // 3)
        middle = max(0, (samples.size // 2) - (window // 2))
        samples = np.concatenate([samples[:window], samples[middle : middle + window], samples[-window:]])
    target_rate = 16_000
    if sample_rate != target_rate:
        target_size = max(1, int(round(samples.size * target_rate / sample_rate)))
        old_positions = np.linspace(0.0, 1.0, num=samples.size, endpoint=True)
        new_positions = np.linspace(0.0, 1.0, num=target_size, endpoint=True)
        samples = np.interp(new_positions, old_positions, samples).astype(np.float32)
    samples -= float(np.mean(samples))
    scale = float(np.percentile(np.abs(samples), 99.5))
    if scale > 1e-7:
        samples /= scale
    return samples


def resample_feature_pattern(values: np.ndarray, size: int) -> np.ndarray:
    pattern = np.nan_to_num(np.asarray(values, dtype=np.float32).reshape(-1))
    if pattern.size == 0:
        return np.zeros(size, dtype=np.float32)
    if pattern.size == 1:
        return np.full(size, float(pattern[0]), dtype=np.float32)
    source = np.linspace(0.0, 1.0, num=pattern.size, endpoint=True)
    target = np.linspace(0.0, 1.0, num=size, endpoint=True)
    pattern = np.interp(target, source, pattern).astype(np.float32)
    pattern = np.maximum(0.0, pattern - float(np.median(pattern)))
    return unit_feature_vector(pattern)


def unit_feature_vector(values: np.ndarray) -> np.ndarray:
    vector = np.nan_to_num(np.asarray(values, dtype=np.float32).reshape(-1), nan=0.0, posinf=0.0, neginf=0.0)
    norm = float(np.linalg.norm(vector))
    return vector / norm if norm > 1e-8 else np.zeros_like(vector)


def feature_cosine_similarity(left: np.ndarray, right: np.ndarray, *, empty_matches: bool = False) -> float:
    length = min(left.size, right.size)
    if length == 0:
        return 1.0 if empty_matches else 0.0
    left_vector = np.asarray(left[:length], dtype=np.float32)
    right_vector = np.asarray(right[:length], dtype=np.float32)
    left_norm = float(np.linalg.norm(left_vector))
    right_norm = float(np.linalg.norm(right_vector))
    if left_norm <= 1e-8 or right_norm <= 1e-8:
        return 1.0 if empty_matches and left_norm <= 1e-8 and right_norm <= 1e-8 else 0.0
    return float(np.clip(np.dot(left_vector, right_vector) / (left_norm * right_norm), 0.0, 1.0))


def arrangement_similarity_metrics(
    left: ArrangementAudioFeatures,
    right: ArrangementAudioFeatures,
) -> dict[str, float]:
    embedding = feature_cosine_similarity(left.embedding, right.embedding)
    onset = feature_cosine_similarity(left.drum_onsets, right.drum_onsets, empty_matches=True)
    chord = feature_cosine_similarity(left.chord_changes, right.chord_changes, empty_matches=True)
    instrumentation = feature_cosine_similarity(left.instrumentation, right.instrumentation)
    perceptual = (0.45 * embedding) + (0.25 * onset) + (0.15 * chord) + (0.15 * instrumentation)
    return {
        "embedding_similarity": round(embedding, 6),
        "drum_onset_similarity": round(onset, 6),
        "chord_change_similarity": round(chord, 6),
        "instrumentation_similarity": round(instrumentation, 6),
        "perceptual_similarity": round(float(np.clip(perceptual, 0.0, 1.0)), 6),
    }


def arrangement_similarity_rejection_reason(
    metrics: dict[str, float],
    *,
    thresholds: dict[str, float] | None = None,
    strict_style_diversity: bool = False,
) -> str | None:
    active_thresholds = {
        **(thresholds or diversity_calibration.active_diversity_calibration().thresholds),
        **{
            key: float((thresholds or {}).get(key, value))
            for key, value in STYLE_CLUSTER_THRESHOLDS.items()
        },
    }
    embedding = metrics["embedding_similarity"]
    onset = metrics["drum_onset_similarity"]
    chord = metrics["chord_change_similarity"]
    instrumentation = metrics["instrumentation_similarity"]
    perceptual = metrics["perceptual_similarity"]
    near_identical = (
        embedding >= active_thresholds["near_identical_embedding"]
        and instrumentation >= active_thresholds["near_identical_instrumentation"]
    )
    all_views_match = (
        embedding >= active_thresholds["embedding"]
        and onset >= active_thresholds["drum_onset"]
        and chord >= active_thresholds["chord_change"]
        and instrumentation >= active_thresholds["instrumentation"]
    )
    matching_views = sum(
        (
            embedding >= active_thresholds["embedding"],
            onset >= active_thresholds["drum_onset"],
            chord >= active_thresholds["chord_change"],
            instrumentation >= active_thresholds["instrumentation"],
        )
    )
    style_clustered = (
        embedding >= active_thresholds["style_embedding"]
        and instrumentation >= active_thresholds["style_instrumentation"]
    )
    perceptually_clustered = (
        perceptual >= active_thresholds["style_perceptual"]
        and embedding >= active_thresholds["style_perceptual_embedding_floor"]
        and instrumentation >= active_thresholds["style_perceptual_instrumentation_floor"]
    )
    if near_identical or all_views_match or (strict_style_diversity and (style_clustered or perceptually_clustered)) or (
        perceptual >= active_thresholds["perceptual"]
        and embedding >= active_thresholds["perceptual_embedding_floor"]
        and matching_views >= 3
    ):
        return (
            "perceptual embedding gate rejected the backing "
            f"(embedding {embedding:.3f}, onsets {onset:.3f}, chord changes {chord:.3f}, "
            f"instrumentation {instrumentation:.3f}, combined {perceptual:.3f})"
        )
    return None


def build_arrangement_diversity_report(
    backing_paths: list[Path],
    *,
    strict_style_diversity: bool = False,
) -> ArrangementDiversityReport:
    """Evaluate every pair of accepted instrumental backings (ten for five)."""
    calibration = diversity_calibration.active_diversity_calibration()
    features: list[ArrangementAudioFeatures] = []
    for path in backing_paths:
        audio, sample_rate = load_audio_for_profile(path)
        mono = np.asarray(audio, dtype=np.float32).mean(axis=1)
        features.append(extract_arrangement_audio_features(mono, sample_rate))
    pairs: list[ArrangementDiversityPair] = []
    for left_index, left in enumerate(features):
        for right_index in range(left_index + 1, len(features)):
            metrics = arrangement_similarity_metrics(left, features[right_index])
            reason = arrangement_similarity_rejection_reason(
                metrics,
                thresholds=calibration.thresholds,
                strict_style_diversity=strict_style_diversity,
            )
            pairs.append(
                ArrangementDiversityPair(
                    left_index=left_index + 1,
                    right_index=right_index + 1,
                    left_file=backing_paths[left_index].name,
                    right_file=backing_paths[right_index].name,
                    rejected=reason is not None,
                    reason=reason,
                    **metrics,
                )
            )
    rejected = sum(pair.rejected for pair in pairs)
    return ArrangementDiversityReport(
        passed=rejected == 0,
        evaluated_pairs=len(pairs),
        rejected_pairs=rejected,
        calibration=calibration.calibration_id,
        calibration_approved=calibration.approved,
        calibration_sample_count=calibration.sample_count,
        calibration_rater_count=calibration.rater_count,
        calibration_manifest_sha256=calibration.manifest_sha256,
        calibration_note=calibration.note,
        thresholds={**calibration.thresholds, **STYLE_CLUSTER_THRESHOLDS},
        pairs=pairs,
    )


def infer_genre_hint(*, bpm: float | None, energy: str | None, mood: str | None, source_profile: str | None) -> tuple[str, float]:
    """Provide a transparent pre-training genre hint, not a falsely certain classifier label."""
    normalized_mood = str(mood or "").lower()
    normalized_energy = str(energy or "").lower()
    tempo = float(bpm or 84)
    if source_profile == "full_song":
        return "Full-song vocal rework", 0.45
    if "devotional" in normalized_mood:
        return "Devotional / acoustic", 0.46
    if tempo <= 78:
        return "Slow acoustic / ballad", 0.42
    if tempo >= 125 or normalized_energy == "high":
        return "Up-tempo pop", 0.42
    if "sad" in normalized_mood or "heartbreak" in normalized_mood:
        return "Emotional pop / ballad", 0.45
    return "Vocal-led pop", 0.40


def predict_with_local_audio_classifier(
    audio_path: Path,
    *,
    checkpoint_path: str | Path | None,
    python_path: str | Path | None,
    timeout_sec: int,
) -> AudioClassifierPrediction:
    """Run a reviewed legacy CNN or shared-encoder checkpoint when configured."""
    if not checkpoint_path:
        return AudioClassifierPrediction()
    checkpoint = Path(checkpoint_path)
    python = Path(python_path) if python_path else None
    runner = Path(__file__).parents[2] / "training" / "infer_audio_classifier.py"
    if not checkpoint.is_file():
        return AudioClassifierPrediction(warning="Configured audio-classifier checkpoint was not found; Skarly used its analysis fallback.")
    if python is None or not python.is_file() or not runner.is_file():
        return AudioClassifierPrediction(warning="Local audio classifier is configured incompletely; Skarly used its analysis fallback.")
    try:
        completed = subprocess.run(
            [str(python), str(runner), "--checkpoint", str(checkpoint), "--audio", str(audio_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=max(5, timeout_sec),
            check=False,
        )
    except Exception as exc:
        return AudioClassifierPrediction(warning=f"Local audio classifier unavailable: {str(exc)[:120]}")
    if completed.returncode != 0:
        return AudioClassifierPrediction(warning=f"Local audio classifier failed: {useful_process_error(completed.stderr)[:120]}")
    try:
        data = json.loads([line for line in completed.stdout.splitlines() if line.strip()][-1])
        heads = data.get("heads") if isinstance(data.get("heads"), dict) else {}
        singing_head = heads.get("singing_speech") if isinstance(heads.get("singing_speech"), dict) else {}
        ood_head = heads.get("in_distribution") if isinstance(heads.get("in_distribution"), dict) else {}
        def probability_map(value: object) -> dict[str, float]:
            if not isinstance(value, dict):
                return {}
            result: dict[str, float] = {}
            for key, probability in value.items():
                try:
                    result[str(key)] = max(0.0, min(1.0, float(probability)))
                except (TypeError, ValueError):
                    continue
            return result

        return AudioClassifierPrediction(
            language=normalize_language(data.get("language")),
            language_confidence=float(data.get("language_confidence") or 0),
            genre=str(data.get("genre") or "").replace("_", " ").strip() or None,
            genre_confidence=float(data.get("genre_confidence") or 0),
            genre_approved=bool(data.get("genre_approved", False)),
            genre_probabilities=probability_map(data.get("genre_probabilities")),
            mood_probabilities=probability_map(data.get("mood_probabilities")),
            vocal_technique_probabilities=probability_map(data.get("vocal_technique_probabilities")),
            singing_speech=str(data.get("singing_speech") or "").strip() or None,
            singing_speech_confidence=float(singing_head.get("confidence")) if singing_head.get("confidence") is not None else None,
            tempo_family=str(data.get("tempo_family") or "").strip() or None,
            melodic_character=str(data.get("melodic_character") or "").strip() or None,
            in_distribution_probability=float(ood_head.get("in_distribution_probability")) if ood_head.get("in_distribution_probability") is not None else None,
            requires_confirmation=bool(data.get("requires_confirmation", True)),
            architecture=str(data.get("architecture") or "").strip() or None,
            device=str(data.get("device") or "").strip() or None,
            windows_analysed=max(0, int(data.get("windows_analysed") or 0)),
            trained_heads={str(key): bool(value) for key, value in (data.get("trained_heads") or {}).items()},
        )
    except Exception:
        return AudioClassifierPrediction(warning="Local audio classifier returned an unreadable result; Skarly used its analysis fallback.")


def studio_generation_duration(input_seconds: float | None, maximum_seconds: int | float | None) -> float:
    """Use decoded vocal length exactly and reject, rather than crop, over-limit audio."""
    ceiling = max(10.0, float(maximum_seconds or 300))
    duration = max(0.001, float(input_seconds or 12.0))
    if duration > ceiling + 0.02:
        raise ValueError(
            f"The decoded vocal is {duration:.2f} seconds, above this studio's {ceiling:.0f}-second limit. No audio was cropped."
        )
    return duration


def should_skip_melody_analysis(duration_seconds: float, analyzer_backend: str | None) -> bool:
    """Avoid a slow optional MIDI extractor from blocking long vocal-to-music jobs."""
    return (
        str(analyzer_backend or "off").strip().lower() == "basic_pitch"
        and float(duration_seconds or 0) > MAX_BASIC_PITCH_GENERATION_SECONDS
    )


def is_hindi_language(language: str | None) -> bool:
    normalized = " ".join(str(language or "").lower().replace("-", " ").split())
    return normalized in {"hindi", "hinglish", "hi", "hi in"}


def timing_summary_from_report(report: Any) -> str | None:
    """Turn voice-activity analysis into a compact, generator-safe arrangement cue."""
    phrases = list(getattr(report, "phrase_boundaries", None) or [])
    duration = float(getattr(report, "duration_seconds", 0) or 0)
    if not phrases or duration <= 0:
        return None

    starts: list[float] = []
    gaps: list[float] = []
    pickup_count = 0
    repeated_motif_ids: set[str] = set()
    delivery_candidates: set[str] = set()
    previous_end: float | None = None
    for phrase in phrases:
        try:
            start = max(0.0, float(phrase.get("start", phrase.get("start_seconds", 0))))
            end = min(duration, float(phrase.get("end", phrase.get("end_seconds", start))))
        except (AttributeError, TypeError, ValueError):
            continue
        if end <= start:
            continue
        starts.append(start)
        if phrase.get("pickup_candidate"):
            pickup_count += 1
        if phrase.get("motif_id"):
            repeated_motif_ids.add(str(phrase["motif_id"]))
        delivery = str(phrase.get("delivery") or "").strip()
        if delivery and delivery != "unclassified_vocal":
            delivery_candidates.add(delivery)
        if previous_end is not None and start > previous_end:
            gaps.append(start - previous_end)
        previous_end = end

    if not starts:
        return None
    intro = starts[0]
    average_gap = sum(gaps) / len(gaps) if gaps else 0.0
    phrase_label = "phrase" if len(starts) == 1 else "phrases"
    guidance = f"{len(starts)} vocal {phrase_label}; keep the first {intro:.1f}s sparse"
    if average_gap >= 0.35:
        guidance += f", place fills in roughly {average_gap:.1f}s phrase gaps"
    if pickup_count:
        guidance += f", leave space before {pickup_count} pickup candidate{'s' if pickup_count != 1 else ''}"
    if repeated_motif_ids:
        guidance += f", lift {len(repeated_motif_ids)} repeated melodic motif{'s' if len(repeated_motif_ids) != 1 else ''} consistently"
    if any("rap" in delivery or "spoken" in delivery for delivery in delivery_candidates):
        guidance += ", keep percussion responsive to speech/rap cadence"
    return guidance + "."


def generate_backing(
    *,
    output_path: Path,
    plan: VersionPlan,
    seconds: float,
    bpm: float,
    key: str | None,
    language: str | None,
    mood: str | None,
    energy: str | None,
    version_index: int,
    generator_backend: str,
    ace_step_base_url: str,
    ace_step_api_key: str | None,
    ace_step_timeout_seconds: int,
    ace_step_download_timeout_seconds: int,
    ace_step_poll_interval_seconds: float,
    ace_step_infer_step: int,
    ace_step_guidance_scale: float,
    ace_step_max_duration_seconds: int,
    source_audio_path: Path | None,
    use_source_audio: bool,
    source_task_type: str | None,
    source_audio_strength: float,
    ace_step_direct_enabled: bool,
    ace_step_repo_dir: str | Path | None,
    ace_step_python_path: str | Path | None,
    ace_step_fallback_to_procedural: bool,
    ffmpeg_path: str = "ffmpeg",
    duration_conform_timeout_sec: int = 120,
) -> BackingResult:
    backend = (generator_backend or "procedural_v2").strip().lower()
    if backend == "ace_step":
        try:
            source_conditioned = bool(use_source_audio and source_audio_path and Path(source_audio_path).is_file())
            generate_ace_step_backing(
                output_path=output_path,
                plan=plan,
                seconds=seconds,
                base_url=ace_step_base_url,
                api_key=ace_step_api_key,
                timeout_seconds=ace_step_timeout_seconds,
                download_timeout_seconds=ace_step_download_timeout_seconds,
                poll_interval_seconds=ace_step_poll_interval_seconds,
                infer_step=ace_step_infer_step,
                guidance_scale=ace_step_guidance_scale,
                max_duration_seconds=ace_step_max_duration_seconds,
                bpm=bpm,
                key=key,
                language=language,
                source_audio_path=source_audio_path,
                use_source_audio=use_source_audio,
                source_task_type=source_task_type,
                source_audio_strength=source_audio_strength,
                direct_enabled=ace_step_direct_enabled,
                repo_dir=ace_step_repo_dir,
                python_path=ace_step_python_path,
            )
            conform_audio_duration(
                output_path,
                seconds,
                ffmpeg_path=ffmpeg_path,
                timeout_sec=duration_conform_timeout_sec,
            )
            engine = "ace_step_1_5_cover" if source_conditioned else "ace_step_1_5"
            return BackingResult(output_path, "ace_step", engine)
        except Exception as exc:
            if not ace_step_fallback_to_procedural:
                raise
            write_placeholder_backing(output_path, seconds=seconds, bpm=bpm, key=key, mood=mood, energy=energy, version_index=version_index, seed=plan.seed)
            return BackingResult(
                output_path,
                "procedural_v2",
                "local_fallback",
                fallback_used=True,
                warning=f"ACE-Step failed for {plan.name}; procedural backing used: {str(exc)[:160]}",
            )

    write_placeholder_backing(output_path, seconds=seconds, bpm=bpm, key=key, mood=mood, energy=energy, version_index=version_index, seed=plan.seed)
    return BackingResult(output_path, "procedural_v2", "local_fallback", fallback_used=True)


def generate_ace_step_backing(
    *,
    output_path: Path,
    plan: VersionPlan,
    seconds: float,
    base_url: str,
    api_key: str | None,
    timeout_seconds: int,
    download_timeout_seconds: int,
    poll_interval_seconds: float,
    infer_step: int,
    guidance_scale: float,
    max_duration_seconds: int,
    bpm: float,
    key: str | None,
    language: str | None,
    source_audio_path: Path | None = None,
    use_source_audio: bool = False,
    source_task_type: str | None = None,
    source_audio_strength: float = 0.45,
    direct_enabled: bool,
    repo_dir: str | Path | None,
    python_path: str | Path | None,
) -> None:
    source_audio = Path(source_audio_path) if source_audio_path else None
    use_audio_context = bool(use_source_audio and source_audio and source_audio.is_file())
    # The resident API accepts the vocal as multipart source context.  The
    # direct runner only supports text-to-music, so do not discard the vocal
    # alignment signal just because direct recovery is enabled.
    if direct_enabled and not use_audio_context:
        try:
            generate_ace_step_direct_backing(
                output_path=output_path,
                plan=plan,
                seconds=seconds,
                bpm=bpm,
                key=key,
                language=language,
                infer_step=infer_step,
                guidance_scale=guidance_scale,
                max_duration_seconds=max_duration_seconds,
                repo_dir=repo_dir,
                python_path=python_path,
            )
            return
        except Exception:
            if not base_url:
                raise
    if requests is None:
        raise RuntimeError("requests is not installed")
    root = base_url.rstrip("/") + "/"
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    payload: dict[str, Any] = {
        "prompt": plan.prompt,
        "negative_prompt": plan.negative_prompt,
        "lyrics": "",
        "audio_duration": min(max_duration_seconds, max(10, int(math.ceil(seconds)))),
        "audio_format": "wav",
        "bpm": int(round(float(bpm or 84))),
        "key_scale": key or "A minor",
        "time_signature": "4",
        "vocal_language": ace_step_language_code(language),
        "inference_steps": max(1, int(infer_step or 8)),
        "guidance_scale": guidance_scale,
        "batch_size": 1,
        "use_random_seed": False,
        "seed": int(plan.seed or stable_plan_seed(language=language or "English", mood="auto", key=key or "A minor", bpm=int(round(float(bpm or 84))), family=plan.style_family, index=1)),
        # The source analysis is already authoritative. Avoid ACE-Step's
        # optional language-model CoT pass rewriting BPM, key, or the
        # instrumental-only direction supplied by Skarly.
        "thinking": False,
        "use_cot_caption": False,
        "use_cot_language": False,
        "use_cot_metas": False,
    }
    request_timeout_seconds = min(600, max(120, int(timeout_seconds)))
    if use_audio_context:
        task_type = normalize_ace_source_task_type(source_task_type)
        payload.update(
            {
                "task_type": task_type,
                "audio_cover_strength": clamp_ace_source_audio_strength(source_audio_strength),
                "lyrics": "[Instrumental]",
            }
        )
        with source_audio.open("rb") as handle:
            release = requests.post(
                urljoin(root, "release_task"),
                headers=headers,
                data=payload,
                files={"ctx_audio": (source_audio.name, handle, "audio/wav")},
                timeout=request_timeout_seconds,
            )
    else:
        release = requests.post(
            urljoin(root, "release_task"),
            headers=headers,
            json=payload,
            timeout=request_timeout_seconds,
        )
    if release.status_code >= 400:
        raise RuntimeError(f"ACE-Step release failed: {release.status_code} {release.text[:180]}")
    task_id = extract_task_id(release.json())
    if not task_id:
        raise RuntimeError("ACE-Step response did not include a task id")
    result = poll_ace_step(root, task_id, headers, timeout_seconds=timeout_seconds, poll_interval_seconds=poll_interval_seconds)
    audio_url = extract_audio_url(result)
    if not audio_url:
        raise RuntimeError("ACE-Step result did not include an audio URL")
    audio_endpoint = urljoin(root, audio_url.lstrip("/")) if not audio_url.startswith("http") else audio_url
    audio_response = requests.get(audio_endpoint, headers=headers, timeout=download_timeout_seconds)
    if audio_response.status_code >= 400:
        raise RuntimeError(f"ACE-Step audio download failed: {audio_response.status_code} {audio_response.text[:180]}")
    if not audio_response.content:
        raise RuntimeError("ACE-Step audio download was empty")
    output_path.write_bytes(audio_response.content)


def generate_ace_step_direct_backing(
    *,
    output_path: Path,
    plan: VersionPlan,
    seconds: float,
    bpm: float,
    key: str | None,
    language: str | None,
    infer_step: int,
    guidance_scale: float,
    max_duration_seconds: int,
    repo_dir: str | Path | None,
    python_path: str | Path | None,
) -> None:
    repo = Path(repo_dir) if repo_dir else default_ace_step_repo_dir()
    python = Path(python_path) if python_path else repo / ".venv" / "Scripts" / "python.exe"
    if not repo.exists():
        raise RuntimeError(f"ACE-Step repo not found: {repo}")
    if not python.exists():
        raise RuntimeError(f"ACE-Step Python not found: {python}")
    runner = Path(__file__).with_name("ace_step_direct_runner.py")
    if not runner.exists():
        raise RuntimeError(f"ACE-Step direct runner not found: {runner}")

    duration = min(max_duration_seconds, max(10, int(math.ceil(seconds))))
    request_path = output_path.with_suffix(".ace_step_request.json")
    status_path = output_path.with_suffix(".ace_step_status.json")
    seed = int(plan.seed or (18000 + (sum(ord(ch) for ch in f"{plan.name}|{plan.prompt}") % 70000)))
    payload = {
        "project_root": str(repo),
        "output_path": str(output_path),
        "status_path": str(status_path),
        "save_dir": str(output_path.parent / "ace_step_raw"),
        "prompt": plan.prompt,
        "negative_prompt": plan.negative_prompt,
        "duration": duration,
        "bpm": int(round(float(bpm or 84))),
        "key": key or "A minor",
        "timesignature": "4",
        "vocal_language": ace_step_language_code(language),
        "inference_steps": max(1, int(infer_step or 8)),
        "guidance_scale": float(guidance_scale or 1.0),
        "seed": seed,
        "model": "acestep-v15-turbo",
        "device": "cuda",
        "offload_to_cpu": False,
        "quantization": None,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    request_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    completed = subprocess.run(
        [str(python), str(runner), str(request_path)],
        check=False,
        cwd=str(repo),
        env=skarly_subprocess_env(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=max(120, int(duration * 12) + 240),
    )
    if completed.returncode != 0:
        detail = ace_step_status_message(status_path) or useful_process_error(completed.stderr or completed.stdout)
        raise RuntimeError(f"ACE-Step direct generation failed: {detail}")
    if not output_path.exists() or output_path.stat().st_size == 0:
        detail = ace_step_status_message(status_path) or "direct runner completed without a backing WAV"
        raise RuntimeError(f"ACE-Step direct generation failed: {detail}")


def default_ace_step_repo_dir() -> Path:
    return Path(__file__).resolve().parents[4] / "skarly-ai-repos" / "ACE-Step-1.5"


def ace_step_status_message(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    message = data.get("message")
    return str(message)[:240] if message else None


def poll_ace_step(root: str, task_id: str, headers: dict[str, str], *, timeout_seconds: int, poll_interval_seconds: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        response = requests.post(urljoin(root, "query_result"), headers=headers, json={"task_id_list": [task_id]}, timeout=30)
        if response.status_code >= 400:
            raise RuntimeError(f"ACE-Step query failed: {response.status_code} {response.text[:180]}")
        data = response.json()
        last = data
        task = extract_task_result(data, task_id)
        task_or_data = task or data
        status = str(task_or_data.get("status") or task_or_data.get("state") or task_or_data.get("task_status") or "").lower()
        if status in {"2", "failed", "error", "canceled", "cancelled"}:
            raise RuntimeError(f"ACE-Step task failed: {data}")
        decoded_result = decode_ace_step_result(task_or_data)
        if status in {"1", "completed", "complete", "done", "succeeded", "success", "finished"} or extract_audio_url(decoded_result):
            return decoded_result
        time.sleep(max(0.25, float(poll_interval_seconds or 2.0)))
    raise RuntimeError(f"ACE-Step task timed out after {timeout_seconds} seconds: {last}")


def extract_task_id(data: dict[str, Any]) -> str | None:
    for key in ("task_id", "taskId", "id"):
        value = data.get(key)
        if isinstance(value, str) and value:
            return value
    nested = data.get("data") or data.get("result")
    if isinstance(nested, dict):
        return extract_task_id(nested)
    return None


def extract_task_result(data: dict[str, Any], task_id: str) -> dict[str, Any] | None:
    candidates = data.get("data")
    if isinstance(candidates, list):
        for item in candidates:
            if isinstance(item, dict) and item.get("task_id") == task_id:
                return item
        for item in candidates:
            if isinstance(item, dict):
                return item
    if isinstance(candidates, dict):
        return candidates
    return None


def decode_ace_step_result(data: Any) -> Any:
    """Decode ACE-Step's legacy JSON-string result field when it is present."""
    if not isinstance(data, dict):
        return data
    embedded = data.get("result")
    if not isinstance(embedded, str):
        return data
    try:
        decoded = json.loads(embedded)
    except (TypeError, json.JSONDecodeError):
        return data
    return decoded


def extract_audio_url(data: Any) -> str | None:
    if isinstance(data, dict):
        for key in ("audio_url", "audioUrl", "url", "path", "file", "wave", "output_path", "file_url", "download_url"):
            value = data.get(key)
            if isinstance(value, str) and value:
                return value
        for value in data.values():
            found = extract_audio_url(value)
            if found:
                return found
    if isinstance(data, list):
        for item in data:
            found = extract_audio_url(item)
            if found:
                return found
    if isinstance(data, str):
        text = data.strip()
        if text.startswith(("{", "[")):
            try:
                return extract_audio_url(json.loads(text))
            except (TypeError, json.JSONDecodeError):
                pass
        if text.startswith("http") or text.startswith("/") or text.endswith((".wav", ".mp3", ".flac")):
            return text
    return None


def ace_step_language_code(language: str | None) -> str:
    normalized = " ".join(str(language or "").lower().replace("-", " ").split())
    if normalized in {"hindi", "hinglish", "hi", "hi in"}:
        return "hi"
    if normalized in {"urdu", "ur"}:
        return "ur"
    if normalized in {"punjabi", "pa"}:
        return "pa"
    if normalized in {"tamil", "ta"}:
        return "ta"
    if normalized in {"telugu", "te"}:
        return "te"
    if normalized in {"bengali", "bn"}:
        return "bn"
    return "en"


def normalize_ace_source_task_type(value: str | None) -> str:
    """Return a source-aware task supported by the resident turbo model."""
    normalized = str(value or "cover").strip().lower()
    return normalized if normalized in {"cover", "cover-nofsq"} else "cover"


def clamp_ace_source_audio_strength(value: float | int | str | None) -> float:
    """Keep audio conditioning musical without reproducing the singer verbatim."""
    try:
        strength = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        strength = 0.45
    return max(0.10, min(0.80, strength))


def write_analysis_manifest(
    path: Path,
    *,
    upload_id: str,
    owner_id: str | None = None,
    detected: SkarlyDetected | None,
    input_profile: InputProfile,
    transcription: TranscriptionResult,
    melody: MelodyResult,
    prompts: list[VersionPlan],
    generation_telemetry: GenerationTelemetry | None = None,
    arrangement_diversity: ArrangementDiversityReport | None = None,
    song_intelligence_map: SongIntelligenceMap | None = None,
    warnings: list[str],
) -> None:
    payload = {
        "upload_id": upload_id,
        "owner_id": owner_id,
        "detected": detected.model_dump(mode="json") if detected else None,
        "source_profile": input_profile.source_profile,
        "vocal_type": input_profile.vocal_type,
        "energy": input_profile.energy,
        "profile_confidence": input_profile.confidence,
        "whisper": {
            "status": transcription.status,
            "language": transcription.language,
            "text": transcription.text,
            "segments": list(transcription.segments),
        },
        "melody": {
            "status": melody.status,
            "midi_path": str(melody.midi_path) if melody.midi_path else None,
        },
        "versions": [
            {
                "name": plan.name,
                "style_family": plan.style_family,
                "seed": plan.seed,
                "prompt": plan.prompt,
                "negative_prompt": plan.negative_prompt,
                "instruments": list(plan.instruments),
                "energy": plan.energy,
                "rhythm_character": plan.rhythm_character,
                "mix_mode": plan.mix_mode,
                "blueprint": plan.blueprint or {},
            }
            for plan in prompts
        ],
        "generation_telemetry": generation_telemetry.model_dump(mode="json") if generation_telemetry else None,
        "arrangement_diversity": arrangement_diversity.model_dump(mode="json") if arrangement_diversity else None,
        "song_intelligence_map": song_intelligence_map.model_dump(mode="json") if song_intelligence_map else None,
        "warnings": dedupe(warnings),
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def infer_mood(*, key: str, energy: str) -> str:
    if "minor" in (key or "").lower():
        return "Sad / Emotional" if energy != "High" else "Emotional / Intense"
    if energy == "Low":
        return "Soft / Emotional"
    if energy == "High":
        return "Energetic / Emotional"
    return "Emotional"


def normalize_language(value: Any) -> str | None:
    if not value:
        return None
    text = str(value).strip().lower()
    mapping = {
        "hi": "Hindi",
        "hindi": "Hindi",
        "en": "English",
        "english": "English",
        "ur": "Urdu",
        "urdu": "Urdu",
        "pa": "Punjabi",
        "punjabi": "Punjabi",
        "bn": "Bengali",
        "bengali": "Bengali",
        "ta": "Tamil",
        "tamil": "Tamil",
        "te": "Telugu",
        "telugu": "Telugu",
    }
    return mapping.get(text, text[:1].upper() + text[1:])


def short_text(value: str | None, limit: int) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    return text if len(text) <= limit else text[: max(0, limit - 3)].rstrip() + "..."


def studio_paths(output_dir: str | Path, job_id: str) -> StudioPaths:
    output_root = safe_paths.resolve_output_dir(output_dir)
    return StudioPaths(output_root=output_root, job_dir=output_root / safe_paths.sanitize_filename(job_id))


def skarly_analysis_source(
    source: Path,
    *,
    upload_id: str,
    uploads_dir: str | Path,
    duration_seconds: float | None,
    ffmpeg_path: str,
) -> tuple[Path, str | None, bool]:
    """Return the complete source for analysis and flag long recordings.

    The confirmation screen is the creator's chance to correct Skarly before
    generation.  It therefore needs the same full-song timing map, key, and
    section structure that the generator will use.  A 30-second preview made
    confirmation fast, but it caused two-minute uploads to show a misleading
    song map.  Optional heavyweight MIDI extraction is handled separately.
    """
    del upload_id, uploads_dir, ffmpeg_path
    long_audio = bool(duration_seconds and duration_seconds > 90)
    if not long_audio:
        return source, None, False
    return source, "Long audio detected; Skarly analyzed the complete vocal before planning the five versions.", True


def normalize_vocal(source: Path, target: Path, *, ffmpeg_path: str, timeout_sec: int) -> None:
    if command_available(ffmpeg_path):
        subprocess.run(
            [
                ffmpeg_path,
                "-y",
                "-i",
                str(source),
                "-ac",
                "2",
                "-ar",
                "48000",
                "-af",
                "loudnorm=I=-18:TP=-2:LRA=9",
                str(target),
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout_sec,
        )
        return
    copy_audio_as_wav(source, target)


def mix_vocal_forward(
    *,
    vocal_path: Path,
    backing_path: Path,
    output_path: Path,
    preset_name: str,
    ffmpeg_path: str,
    timeout_sec: int,
    vocal_music_balance: float = 0.0,
) -> AdaptiveMix:
    if not command_available(ffmpeg_path):
        raise RuntimeError("FFmpeg is not available")
    preset = dict(MIXING_PRESETS[preset_name])
    balance = max(-1.0, min(1.0, float(vocal_music_balance)))
    # Positive values move toward the singer; negative values add beat energy
    # while retaining at least 85% of the preset vocal level.
    preset["vocal_volume"] = max(0.85, float(preset["vocal_volume"]) * (1.0 + (0.20 * balance)))
    preset["backing_volume"] = max(0.35, float(preset["backing_volume"]) * (1.0 - (0.25 * balance)))
    adaptive = adaptive_mix_settings(vocal_path, backing_path, preset)
    duck = ducking_parameters(adaptive.ducking)
    filter_complex = frequency_aware_mix_filter(adaptive, duck)
    process_timeout = effective_mixing_timeout(
        timeout_sec,
        vocal_path=vocal_path,
        backing_path=backing_path,
    )
    subprocess.run(
        [
            ffmpeg_path,
            "-y",
            "-i",
            str(vocal_path),
            "-i",
            str(backing_path),
            "-filter_complex",
            filter_complex,
            "-map",
            "[out]",
            "-c:a",
            "libmp3lame",
            "-b:a",
            "320k",
            str(output_path),
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=process_timeout,
    )
    return AdaptiveMix(
        vocal_volume=adaptive.vocal_volume,
        backing_volume=adaptive.backing_volume,
        ducking=adaptive.ducking,
        note=(
            f"{adaptive.note} Vocal-triggered multiband ducking protects the presence range "
            "while leaving bass and kick unducked."
        ),
    )


def effective_mixing_timeout(
    configured_timeout_sec: int | float,
    *,
    vocal_path: Path,
    backing_path: Path,
) -> float:
    """Give long-song FFmpeg filters time proportional to decoded audio length.

    Multiband sidechain compression plus two loudness-normalization passes can
    run slower than real time when other jobs share the CPU.  A fixed 120-second
    timeout therefore made otherwise valid 3-5 minute remixes fail.  The
    configured timeout remains the floor; queue time is never charged against
    the FFmpeg process.
    """

    configured = max(1.0, float(configured_timeout_sec))
    durations = [
        float(duration)
        for duration in (safe_duration_seconds(vocal_path), safe_duration_seconds(backing_path))
        if duration is not None and math.isfinite(float(duration)) and float(duration) > 0
    ]
    if not durations:
        return configured
    return max(configured, float(math.ceil((max(durations) * 1.5) + 60.0)))


def frequency_aware_mix_filter(adaptive: AdaptiveMix, duck: dict[str, str]) -> str:
    """Build vocal-triggered multiband ducking that preserves the backing's low end."""
    air = air_ducking_parameters(adaptive.ducking)
    return (
        "[0:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,"
        "highpass=f=80,lowpass=f=16000,"
        "acompressor=threshold=-18dB:ratio=3:attack=5:release=80:makeup=2,"
        f"loudnorm=I=-18:TP=-2:LRA=9,volume={adaptive.vocal_volume:.4f},"
        "asplit=3[vocal_mix][vocal_presence_source][vocal_air_source];"
        "[vocal_presence_source]highpass=f=120,lowpass=f=6500[vocal_presence_sc];"
        "[vocal_air_source]highpass=f=3500[vocal_air_sc];"
        "[1:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,"
        f"loudnorm=I=-20:TP=-3:LRA=11,volume={adaptive.backing_volume:.4f},"
        "acrossover=split='180 6500':order=8th[back_low][back_presence][back_air];"
        f"[back_presence][vocal_presence_sc]sidechaincompress=threshold={duck['threshold']}:"
        f"ratio={duck['ratio']}:attack={duck['attack']}:release={duck['release']}[back_presence_ducked];"
        f"[back_air][vocal_air_sc]sidechaincompress=threshold={air['threshold']}:"
        f"ratio={air['ratio']}:attack={air['attack']}:release={air['release']}[back_air_ducked];"
        "[back_low][back_presence_ducked][back_air_ducked]"
        "amix=inputs=3:duration=longest:dropout_transition=0:normalize=0[ducked];"
        "[ducked]volume=0.98[backing_down];"
        "[vocal_mix][backing_down]amix=inputs=2:duration=longest:dropout_transition=2:normalize=0,"
        "alimiter=limit=0.95,loudnorm=I=-14:TP=-1.5:LRA=10[out]"
    )


def adaptive_mix_settings(vocal_path: Path, backing_path: Path, preset: dict[str, Any]) -> AdaptiveMix:
    """Adapt relative levels for unusually quiet backing or an unusually dominant vocal."""
    vocal_db = audio_rms_db(vocal_path)
    backing_db = audio_rms_db(backing_path)
    vocal_volume = float(preset["vocal_volume"])
    backing_volume = float(preset["backing_volume"])
    ducking = str(preset["ducking"])
    if vocal_db is None or backing_db is None:
        return AdaptiveMix(vocal_volume, backing_volume, ducking, "Standard vocal-forward balance used because source levels could not be measured.")

    difference = vocal_db - backing_db
    if difference >= 9:
        backing_volume = min(1.30, backing_volume * 1.38)
        vocal_volume = max(0.88, vocal_volume * 0.92)
        ducking = "medium"
        note = "Backing was quiet relative to the vocal, so Skarly raised the music bed and eased vocal priority to keep the beat audible."
    elif difference <= -7:
        backing_volume = max(0.38, backing_volume * 0.72)
        vocal_volume = min(1.30, vocal_volume * 1.08)
        ducking = "strong"
        note = "Backing was loud relative to the vocal, so Skarly increased vocal priority and stronger ducking."
    else:
        note = "Adaptive balance found the vocal and backing within the target range."
    return AdaptiveMix(vocal_volume, backing_volume, ducking, note)


def audio_rms_db(path: Path) -> float | None:
    try:
        # ACE-Step returns 32-bit float WAV. The legacy WAV fallback only reads
        # 16-bit PCM, while the profile loader supports both through soundfile.
        samples, _sample_rate = load_audio_for_profile(path)
    except Exception:
        return None
    mono = samples.mean(axis=1).astype(np.float32) if samples.ndim == 2 else np.asarray(samples, dtype=np.float32)
    if mono.size == 0:
        return None
    rms = float(np.sqrt(np.mean(np.square(mono))))
    if rms <= 1e-7:
        return -120.0
    return 20.0 * math.log10(rms)


def ducking_parameters(strength: str) -> dict[str, str]:
    if strength == "light":
        return {"threshold": "0.035", "ratio": "2.5", "attack": "25", "release": "220"}
    if strength == "strong":
        return {"threshold": "0.018", "ratio": "5", "attack": "15", "release": "280"}
    return {"threshold": "0.02", "ratio": "4", "attack": "20", "release": "250"}


def air_ducking_parameters(strength: str) -> dict[str, str]:
    """Return gentler high-band controls so consonants stay clear without dulling the mix."""
    if strength == "light":
        return {"threshold": "0.05", "ratio": "1.5", "attack": "35", "release": "260"}
    if strength == "strong":
        return {"threshold": "0.03", "ratio": "2.5", "attack": "25", "release": "320"}
    return {"threshold": "0.04", "ratio": "2", "attack": "30", "release": "280"}


def write_placeholder_backing(
    path: Path,
    *,
    seconds: float,
    bpm: float,
    version_index: int,
    key: str | None = None,
    mood: str | None = None,
    energy: str | None = None,
    seed: int | None = None,
) -> None:
    sample_rate = 48000
    safe_bpm = max(58.0, min(160.0, float(bpm or 84.0)))
    frames = max(1, int(sample_rate * seconds))
    stereo = np.zeros((frames, 2), dtype=np.float32)
    beat = 60.0 / safe_bpm
    rng = np.random.default_rng(int(seed) if seed is not None else 3400 + int(version_index))
    root = key_to_root_hz(key)
    mood_scale = 0.88 if "sad" in str(mood or "").lower() or "emotional" in str(mood or "").lower() else 1.0
    energy_scale = 1.18 if str(energy or "").lower() == "high" else 0.86 if str(energy or "").lower() == "low" else 1.0
    style = ((version_index - 1) % 5) + 1

    add_chord_pad(stereo, sample_rate, seconds, beat, root, style, scale=mood_scale * energy_scale)
    if style == 1:
        add_bassline(stereo, sample_rate, seconds, beat, root, pattern=(0, 0, -5, -7), amp=0.105 * energy_scale)
        add_soft_drums(stereo, sample_rate, seconds, beat, rng, kick_amp=0.20 * energy_scale, snare_amp=0.055 * energy_scale, hat_amp=0.018 * energy_scale)
        add_piano_pattern(stereo, sample_rate, seconds, beat, root, amp=0.050 * mood_scale, step=1.0, pan=-0.12)
    elif style == 2:
        add_bassline(stereo, sample_rate, seconds, beat, root, pattern=(0, -5, -7, -2), amp=0.070 * energy_scale)
        add_piano_pattern(stereo, sample_rate, seconds, beat, root, amp=0.115 * mood_scale, step=0.5, pan=-0.08)
        add_soft_drums(stereo, sample_rate, seconds, beat, rng, kick_amp=0.08 * energy_scale, snare_amp=0.018 * energy_scale, hat_amp=0.0)
    elif style == 3:
        add_bassline(stereo, sample_rate, seconds, beat, root * 0.5, pattern=(0, 0, -5, -2), amp=0.085 * energy_scale)
        add_guitar_pattern(stereo, sample_rate, seconds, beat, root, amp=0.105 * mood_scale)
        add_brush_noise(stereo, sample_rate, seconds, beat, rng, amp=0.035 * energy_scale)
    elif style == 4:
        add_bassline(stereo, sample_rate, seconds, beat, root * 0.5, pattern=(0, -7, -5, -2), amp=0.120 * energy_scale)
        add_piano_pattern(stereo, sample_rate, seconds, beat, root * 0.5, amp=0.060 * mood_scale, step=1.0, pan=0.10)
        add_soft_drums(stereo, sample_rate, seconds, beat, rng, kick_amp=0.24 * energy_scale, snare_amp=0.09 * energy_scale, hat_amp=0.045 * energy_scale)
        add_vinyl_texture(stereo, rng, amp=0.012)
    else:
        add_bassline(stereo, sample_rate, seconds, beat, root * 0.5, pattern=(0, -5, -7, -12), amp=0.095 * energy_scale)
        add_cinematic_pulses(stereo, sample_rate, seconds, beat, root)
        add_piano_pattern(stereo, sample_rate, seconds, beat, root, amp=0.052 * mood_scale, step=2.0, pan=0.0)

    fade_samples = min(frames // 3, int(sample_rate * 1.5))
    if fade_samples > 0:
        fade_in = np.linspace(0.0, 1.0, fade_samples, dtype=np.float32)
        fade_out = np.linspace(1.0, 0.0, fade_samples, dtype=np.float32)
        stereo[:fade_samples] *= fade_in[:, None]
        stereo[-fade_samples:] *= fade_out[:, None]
    peak = float(np.max(np.abs(stereo))) if stereo.size else 0.0
    if peak > 0:
        stereo = stereo / max(peak, 0.42) * 0.42
    write_float_wav(path, stereo, sample_rate)


def key_to_root_hz(key: str | None) -> float:
    text = str(key or "A minor").strip().replace("♭", "b").replace("♯", "#")
    root_name = (text.split() or ["A"])[0]
    semitones = {
        "C": 0,
        "C#": 1,
        "Db": 1,
        "D": 2,
        "D#": 3,
        "Eb": 3,
        "E": 4,
        "F": 5,
        "F#": 6,
        "Gb": 6,
        "G": 7,
        "G#": 8,
        "Ab": 8,
        "A": 9,
        "A#": 10,
        "Bb": 10,
        "B": 11,
    }
    note = semitones.get(root_name[:1].upper() + root_name[1:], 9)
    c3 = 130.8128
    root = c3 * (2 ** (note / 12.0))
    while root > 164.82:
        root *= 0.5
    while root < 82.41:
        root *= 2.0
    return float(root)


def add_chord_pad(stereo: np.ndarray, sample_rate: int, seconds: float, beat: float, root: float, style: int, *, scale: float = 1.0) -> None:
    progression = (
        (0, 3, 7, 12),
        (-5, -2, 2, 7),
        (-7, -4, 0, 5),
        (-2, 1, 5, 10),
    )
    section = beat * 4.0
    pad_amp = {1: 0.045, 2: 0.030, 3: 0.024, 4: 0.035, 5: 0.075}.get(style, 0.04) * scale
    for index, start in enumerate(np.arange(0.0, seconds, section)):
        chord = progression[index % len(progression)]
        duration = min(section * 1.08, seconds - float(start))
        for offset in chord:
            freq = root * (2 ** (offset / 12.0))
            add_tone(stereo, sample_rate, float(start), duration, freq, amp=pad_amp / len(chord), decay=0.08, pan=-0.25)
            add_tone(stereo, sample_rate, float(start), duration, freq * 2.0, amp=pad_amp / (len(chord) * 2.8), decay=0.06, pan=0.25)


def add_bassline(
    stereo: np.ndarray,
    sample_rate: int,
    seconds: float,
    beat: float,
    root: float,
    *,
    pattern: tuple[int, ...],
    amp: float,
) -> None:
    total_beats = int(seconds / beat) + 2
    for beat_index in range(total_beats):
        if beat_index % 2 == 1:
            continue
        offset = pattern[(beat_index // 4) % len(pattern)]
        freq = root * (2 ** (offset / 12.0))
        add_tone(stereo, sample_rate, beat_index * beat, beat * 0.82, freq, amp=amp, decay=2.6, pan=0.0)


def add_piano_pattern(
    stereo: np.ndarray,
    sample_rate: int,
    seconds: float,
    beat: float,
    root: float,
    *,
    amp: float,
    step: float,
    pan: float,
) -> None:
    arpeggio = (0, 7, 12, 15, 12, 7, 3, 7)
    total_steps = int(seconds / (beat * step)) + 2
    for index in range(total_steps):
        offset = arpeggio[index % len(arpeggio)]
        section_shift = (index // max(1, int(4 / step))) % 4
        chord_shift = (0, -5, -7, -2)[section_shift]
        freq = root * (2 ** ((offset + chord_shift) / 12.0))
        add_tone(stereo, sample_rate, index * beat * step, beat * min(1.2, step * 1.7), freq, amp=amp, decay=5.8, pan=pan)


def add_guitar_pattern(stereo: np.ndarray, sample_rate: int, seconds: float, beat: float, root: float, *, amp: float) -> None:
    pattern = (0, 7, 12, 7, 3, 7, 12, 7)
    total_steps = int(seconds / (beat * 0.5)) + 2
    for index in range(total_steps):
        offset = pattern[index % len(pattern)] + (0, -5, -7, -2)[(index // 8) % 4]
        freq = root * (2 ** (offset / 12.0))
        pan = -0.35 if index % 2 == 0 else 0.35
        add_tone(stereo, sample_rate, index * beat * 0.5, beat * 0.52, freq, amp=amp, decay=9.0, pan=pan, brightness=0.55)


def add_soft_drums(
    stereo: np.ndarray,
    sample_rate: int,
    seconds: float,
    beat: float,
    rng: np.random.Generator,
    *,
    kick_amp: float,
    snare_amp: float,
    hat_amp: float,
) -> None:
    total_beats = int(seconds / beat) + 2
    for beat_index in range(total_beats):
        start = beat_index * beat
        add_kick(stereo, sample_rate, start, amp=kick_amp if beat_index % 4 in {0, 2} else kick_amp * 0.55)
        if beat_index % 4 in {1, 3} and snare_amp > 0:
            add_noise(stereo, sample_rate, start + beat * 0.02, beat * 0.22, rng, amp=snare_amp, pan=0.06)
        if hat_amp > 0:
            add_noise(stereo, sample_rate, start + beat * 0.50, beat * 0.08, rng, amp=hat_amp, pan=-0.18)


def add_brush_noise(stereo: np.ndarray, sample_rate: int, seconds: float, beat: float, rng: np.random.Generator, *, amp: float) -> None:
    total_beats = int(seconds / beat) + 2
    for beat_index in range(total_beats):
        if beat_index % 2 == 1:
            add_noise(stereo, sample_rate, beat_index * beat, beat * 0.35, rng, amp=amp, pan=0.18)


def add_cinematic_pulses(stereo: np.ndarray, sample_rate: int, seconds: float, beat: float, root: float) -> None:
    section = beat * 4.0
    for start in np.arange(0.0, seconds, section):
        add_tone(stereo, sample_rate, float(start), beat * 1.8, root * 0.25, amp=0.18, decay=2.2, pan=0.0)
        add_tone(stereo, sample_rate, float(start) + beat * 2.0, beat * 1.2, root * 2.0, amp=0.060, decay=4.2, pan=-0.22)
        add_tone(stereo, sample_rate, float(start) + beat * 2.5, beat * 1.2, root * 2.0 * (2 ** (7 / 12.0)), amp=0.050, decay=4.2, pan=0.22)


def add_vinyl_texture(stereo: np.ndarray, rng: np.random.Generator, *, amp: float) -> None:
    if stereo.size == 0:
        return
    noise = rng.normal(0.0, amp, size=len(stereo)).astype(np.float32)
    stereo[:, 0] += noise
    stereo[:, 1] += np.roll(noise, 19) * 0.8


def add_kick(stereo: np.ndarray, sample_rate: int, start: float, *, amp: float) -> None:
    duration = 0.22
    start_frame = max(0, int(start * sample_rate))
    end_frame = min(len(stereo), start_frame + int(duration * sample_rate))
    if end_frame <= start_frame:
        return
    local_t = np.arange(end_frame - start_frame, dtype=np.float32) / sample_rate
    phase = 2 * math.pi * (45.0 * local_t + 42.0 * (1.0 - np.exp(-18.0 * local_t)) / 18.0)
    env = np.exp(-15.0 * local_t)
    tone = np.sin(phase).astype(np.float32) * env * amp
    stereo[start_frame:end_frame, 0] += tone
    stereo[start_frame:end_frame, 1] += tone


def add_noise(
    stereo: np.ndarray,
    sample_rate: int,
    start: float,
    duration: float,
    rng: np.random.Generator,
    *,
    amp: float,
    pan: float,
) -> None:
    start_frame = max(0, int(start * sample_rate))
    end_frame = min(len(stereo), start_frame + max(1, int(duration * sample_rate)))
    if end_frame <= start_frame:
        return
    local_t = np.arange(end_frame - start_frame, dtype=np.float32) / sample_rate
    env = np.exp(-18.0 * local_t)
    noise = rng.normal(0.0, 1.0, size=end_frame - start_frame).astype(np.float32)
    noise = noise - np.concatenate(([0.0], noise[:-1])) * 0.82
    add_stereo(stereo, start_frame, np.clip(noise * env * amp, -0.5, 0.5), pan)


def add_tone(
    stereo: np.ndarray,
    sample_rate: int,
    start: float,
    duration: float,
    freq: float,
    *,
    amp: float,
    decay: float,
    pan: float,
    brightness: float = 0.25,
) -> None:
    start_frame = max(0, int(start * sample_rate))
    end_frame = min(len(stereo), start_frame + max(1, int(duration * sample_rate)))
    if end_frame <= start_frame or freq <= 0:
        return
    local_t = np.arange(end_frame - start_frame, dtype=np.float32) / sample_rate
    env = np.exp(-decay * local_t).astype(np.float32) if decay > 0 else np.ones_like(local_t)
    attack = min(len(env), max(1, int(sample_rate * 0.012)))
    env[:attack] *= np.linspace(0.0, 1.0, attack, dtype=np.float32)
    wave_body = (
        np.sin(2 * math.pi * freq * local_t)
        + brightness * np.sin(2 * math.pi * freq * 2.01 * local_t)
        + brightness * 0.35 * np.sin(2 * math.pi * freq * 3.0 * local_t)
    ).astype(np.float32)
    add_stereo(stereo, start_frame, wave_body * env * amp, pan)


def add_stereo(stereo: np.ndarray, start_frame: int, signal: np.ndarray, pan: float) -> None:
    end_frame = min(len(stereo), start_frame + len(signal))
    if end_frame <= start_frame:
        return
    clipped = signal[: end_frame - start_frame]
    left_gain = max(0.0, min(1.0, 0.72 - pan * 0.35))
    right_gain = max(0.0, min(1.0, 0.72 + pan * 0.35))
    stereo[start_frame:end_frame, 0] += clipped * left_gain
    stereo[start_frame:end_frame, 1] += clipped * right_gain


def mix_vocal_forward_wav_fallback(vocal_path: Path, backing_path: Path, output_path: Path) -> None:
    vocal, rate = read_wav_float(vocal_path)
    backing, backing_rate = read_wav_float(backing_path)
    if backing_rate != rate:
        rate = backing_rate
    frames = max(len(vocal), len(backing))
    vocal = match_frames(vocal, frames) * 1.05
    backing = match_frames(backing, frames) * 0.55
    mixed = np.clip(vocal + backing, -0.95, 0.95)
    write_float_wav(output_path, mixed, rate)


def copy_audio_as_wav(source: Path, target: Path) -> None:
    if source.suffix.lower() == ".wav":
        shutil.copyfile(source, target)
        return
    raise RuntimeError("FFmpeg is required to normalize non-WAV uploads")


def safe_duration_seconds(path: Path) -> float | None:
    try:
        with wave.open(str(path), "rb") as handle:
            return handle.getnframes() / float(handle.getframerate())
    except Exception:
        pass
    try:
        import soundfile as sf

        info = sf.info(str(path))
        if info.frames > 0 and info.samplerate > 0:
            return info.frames / float(info.samplerate)
    except Exception:
        pass
    return None


def conform_audio_duration(
    path: Path,
    target_seconds: float,
    *,
    ffmpeg_path: str,
    timeout_sec: int,
) -> None:
    """Trim or minimally pad a valid backing to the decoded vocal duration."""
    target = max(0.001, float(target_seconds))
    actual = safe_duration_seconds(path)
    if actual is None:
        raise RuntimeError("Generated backing is corrupt or has no decodable WAV duration.")
    shortfall_limit = max(1.25, target * 0.015)
    excess_limit = max(2.0, target * 0.02)
    if actual < target - shortfall_limit:
        raise RuntimeError(
            f"Generated backing was truncated ({actual:.2f}s; expected {target:.2f}s)."
        )
    if actual > target + excess_limit:
        raise RuntimeError(
            f"Generated backing has the wrong duration ({actual:.2f}s; expected {target:.2f}s)."
        )
    if abs(actual - target) <= 0.02:
        return
    if not command_available(ffmpeg_path):
        raise RuntimeError(
            f"Generated backing duration is {actual:.2f}s instead of {target:.2f}s, and FFmpeg is unavailable to conform it."
        )

    conformed = path.with_name(f"{path.stem}.duration-{uuid4().hex[:8]}.wav")
    try:
        subprocess.run(
            [
                ffmpeg_path,
                "-y",
                "-i",
                str(path),
                "-af",
                f"apad,atrim=start=0:end={target:.6f}",
                "-ac",
                "2",
                "-ar",
                "48000",
                "-c:a",
                "pcm_s16le",
                str(conformed),
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=max(30, int(timeout_sec)),
        )
        verified = safe_duration_seconds(conformed)
        if verified is None or abs(verified - target) > 0.03:
            raise RuntimeError(
                f"Backing duration verification failed after conforming ({verified!r}s; expected {target:.2f}s)."
            )
        conformed.replace(path)
    finally:
        conformed.unlink(missing_ok=True)


def build_waveform_peaks(audio_path: str | Path, *, points: int = 600, ffmpeg_path: str = "ffmpeg") -> list[float]:
    path = Path(audio_path)
    if not path.exists() or points <= 0:
        return []
    try:
        audio, _sample_rate = read_wav_float(path)
    except Exception:
        if not command_available(ffmpeg_path):
            return []
        try:
            with tempfile.TemporaryDirectory(prefix="skarly-waveform-") as temp_dir:
                waveform_wav = Path(temp_dir) / "waveform.wav"
                decoded_seconds = safe_duration_seconds(path) or 0.0
                waveform_timeout_seconds = max(120, int(decoded_seconds * 2.0) + 120)
                subprocess.run(
                    [
                        ffmpeg_path,
                        "-y",
                        "-i",
                        str(path),
                        "-ac",
                        "1",
                        "-ar",
                        "44100",
                        str(waveform_wav),
                    ],
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=waveform_timeout_seconds,
                )
                audio, _sample_rate = read_wav_float(waveform_wav)
        except Exception:
            return []
    mono = audio.mean(axis=1).astype(np.float32) if audio.ndim == 2 else np.asarray(audio, dtype=np.float32)
    if mono.size == 0:
        return []
    chunk_size = max(1, int(math.ceil(len(mono) / float(points))))
    peaks: list[float] = []
    for start in range(0, len(mono), chunk_size):
        chunk = mono[start : start + chunk_size]
        if chunk.size:
            peaks.append(float(np.max(np.abs(chunk))))
    max_peak = max(peaks) if peaks else 0.0
    if max_peak <= 0:
        return [0.0 for _ in peaks[:points]]
    return [round(float(peak / max_peak), 4) for peak in peaks[:points]]


def read_wav_float(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as handle:
        channels = handle.getnchannels()
        rate = handle.getframerate()
        width = handle.getsampwidth()
        frames = handle.readframes(handle.getnframes())
    if width != 2:
        raise RuntimeError("WAV fallback only supports 16-bit PCM")
    raw = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0
    audio = raw.reshape((-1, channels)) if channels > 1 else raw.reshape((-1, 1))
    if audio.shape[1] == 1:
        audio = np.repeat(audio, 2, axis=1)
    return audio[:, :2].astype(np.float32), int(rate)


def write_float_wav(path: Path, samples: np.ndarray, sample_rate: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    audio = np.asarray(samples, dtype=np.float32)
    if audio.ndim == 1:
        audio = audio.reshape((-1, 1))
    if audio.shape[1] == 1:
        audio = np.repeat(audio, 2, axis=1)
    pcm = (np.clip(audio[:, :2], -0.98, 0.98) * 32767.0).astype("<i2")
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(int(sample_rate))
        handle.writeframes(pcm.tobytes())


def match_frames(audio: np.ndarray, frames: int) -> np.ndarray:
    if len(audio) >= frames:
        return audio[:frames]
    padding = np.zeros((frames - len(audio), audio.shape[1]), dtype=np.float32)
    return np.vstack([audio, padding])


def command_available(command: str) -> bool:
    parts = command_parts(command)
    return command_is_available(parts)


def command_parts(command: str | None) -> list[str]:
    raw = str(command or "").strip()
    if not raw:
        return []
    path_candidate = Path(raw.strip("\"'"))
    if path_candidate.exists():
        return [str(path_candidate)]
    return shlex.split(raw, posix=False if "\\" in raw else True)


def command_is_available(parts: list[str]) -> bool:
    if not parts:
        return False
    head = parts[0]
    return shutil.which(head) is not None or Path(head).is_file()


def normalize_basic_pitch_command(parts: list[str]) -> list[str]:
    if len(parts) != 1:
        return parts
    executable = Path(parts[0])
    if executable.name.lower() not in {"basic-pitch", "basic-pitch.exe"}:
        return parts
    python = executable.with_name("python.exe")
    if python.exists():
        return [str(python), "-m", "basic_pitch.predict"]
    return parts


def skarly_subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    for key in list(env):
        if key.upper() in {"PYTHONPATH", "PYTHONHOME"}:
            env.pop(key, None)
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("TOKENIZERS_PARALLELISM", "false")
    return env


def csv_note_events_to_json(path: Path) -> str:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    converted: list[dict[str, Any]] = []
    for row in rows:
        item: dict[str, Any] = {}
        for key, value in row.items():
            if value is None:
                item[str(key)] = value
                continue
            text = str(value).strip()
            try:
                item[str(key)] = float(text)
            except ValueError:
                item[str(key)] = text
        converted.append(item)
    return json.dumps(converted, indent=2)


def basic_pitch_preflight_warning(command: list[str]) -> str | None:
    key = "\0".join(command)
    if key in _BASIC_PITCH_PREFLIGHT_WARNINGS:
        return _BASIC_PITCH_PREFLIGHT_WARNINGS[key]
    try:
        with tempfile.TemporaryDirectory(prefix="skarly-basic-pitch-check-") as temp_dir:
            temp_path = Path(temp_dir)
            sample_rate = 16000
            t = np.linspace(0, 0.35, int(sample_rate * 0.35), endpoint=False, dtype=np.float32)
            smoke_audio = np.sin(2 * math.pi * 440.0 * t).reshape((-1, 1)) * 0.12
            smoke_wav = temp_path / "smoke.wav"
            output_dir = temp_path / "out"
            output_dir.mkdir(parents=True, exist_ok=True)
            write_float_wav(smoke_wav, smoke_audio, sample_rate)
            completed = subprocess.run(
                [
                    *command,
                    str(output_dir),
                    str(smoke_wav),
                    "--save-midi",
                    "--model-serialization",
                    "onnx",
                    "--midi-tempo",
                    "84",
                ],
                check=False,
                cwd=str(output_dir),
                env=skarly_subprocess_env(),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
            )
    except subprocess.TimeoutExpired:
        warning = "Basic Pitch smoke test timed out; melody MIDI was skipped."
        _BASIC_PITCH_PREFLIGHT_WARNINGS[key] = warning
        return warning
    except Exception as exc:
        warning = f"Basic Pitch could not start; melody MIDI was skipped: {str(exc)[:120]}"
        _BASIC_PITCH_PREFLIGHT_WARNINGS[key] = warning
        return warning
    if completed.returncode == 0:
        _BASIC_PITCH_PREFLIGHT_WARNINGS[key] = None
        return None
    warning = f"Basic Pitch unavailable; melody MIDI was skipped: {useful_process_error(completed.stderr or completed.stdout)}"
    _BASIC_PITCH_PREFLIGHT_WARNINGS[key] = warning
    return warning


def useful_process_error(stderr: str | None) -> str:
    lines = [line.strip() for line in str(stderr or "").splitlines() if line.strip()]
    if not lines:
        return "tool failed"
    markers = ("error", "failed", "not found", "unable", "traceback", "exception", "cuda", "memory")
    useful = [line for line in lines if any(marker in line.lower() for marker in markers)]
    return " | ".join((useful or lines)[-3:])[:220]


def skarly_output_url(path: Path, output_root: Path) -> str:
    relative = path.resolve().relative_to(output_root.resolve())
    return f"/outputs/skarly/{quote(relative.as_posix(), safe='/')}"


def new_skarly_job_id() -> str:
    return f"skarly_job_{uuid4().hex[:12]}"


def dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result
