from __future__ import annotations

import json
import logging
import math
import os
import re
import shlex
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import wave
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from .config import settings
from .models import ArrangementMode, Genre, JobRecord, JobStatus, ProductionStyle, SongAnalysis, SongBlueprint, SongSection, SourceType
from .repository import InMemoryJobRepository
from .services import music_source, stems as stems_service
from .storage import storage

try:
    import requests
except Exception:  # pragma: no cover - ACE-Step reports a clear dependency error.
    requests = None


logger = logging.getLogger(__name__)


STYLE_PRESETS: dict[str, dict[str, Any]] = {
    ProductionStyle.bollywood_ballad.value: {
        "compatible_genres": [Genre.pop, Genre.cinematic],
        "arrangement_style": "Piano-led cinematic",
        "instruments": ["piano", "strings", "pads", "soft drums", "bass"],
        "mood_tags": ["romantic", "emotional", "melancholic"],
    },
    ProductionStyle.romantic_pop.value: {
        "compatible_genres": [Genre.pop],
        "arrangement_style": "warm pop ballad",
        "instruments": ["piano", "soft drums", "bass", "pads", "guitar"],
        "mood_tags": ["romantic", "warm", "emotional"],
    },
    ProductionStyle.acoustic_unplugged.value: {
        "compatible_genres": [Genre.acoustic],
        "arrangement_style": "intimate acoustic",
        "instruments": ["acoustic guitar", "soft piano", "light percussion", "bass"],
        "mood_tags": ["intimate", "organic", "warm"],
    },
    ProductionStyle.piano_ballad.value: {
        "compatible_genres": [Genre.piano],
        "arrangement_style": "piano-led ballad",
        "instruments": ["piano", "pads", "strings", "soft bass"],
        "mood_tags": ["emotional", "intimate", "ballad"],
    },
    ProductionStyle.cinematic_strings.value: {
        "compatible_genres": [Genre.cinematic],
        "arrangement_style": "orchestral cinematic",
        "instruments": ["strings", "piano", "pads", "low drums"],
        "mood_tags": ["cinematic", "dramatic", "emotional"],
    },
    ProductionStyle.indie_pop.value: {
        "compatible_genres": [Genre.pop],
        "arrangement_style": "indie band arrangement",
        "instruments": ["guitar", "bass", "drums", "keys"],
        "mood_tags": ["focused", "warm", "band-driven"],
    },
    ProductionStyle.lofi_cover.value: {
        "compatible_genres": [Genre.lofi],
        "arrangement_style": "relaxed lo-fi",
        "instruments": ["dusty drums", "warm keys", "soft bass", "vinyl texture"],
        "mood_tags": ["relaxed", "nostalgic", "warm"],
    },
    ProductionStyle.edm_rework.value: {
        "compatible_genres": [Genre.pop],
        "arrangement_style": "electronic rework",
        "instruments": ["synths", "electronic drums", "bass", "pads"],
        "mood_tags": ["driving", "bright", "electronic"],
    },
    ProductionStyle.rock_cover.value: {
        "compatible_genres": [Genre.rock],
        "arrangement_style": "band-style rock cover",
        "instruments": ["electric guitar", "bass", "drums", "keys"],
        "mood_tags": ["driving", "band-driven", "energetic"],
    },
    ProductionStyle.trap_soul.value: {
        "compatible_genres": [Genre.rnb, Genre.hiphop],
        "arrangement_style": "dark modern R&B",
        "instruments": ["808 bass", "trap drums", "pads", "keys"],
        "mood_tags": ["romantic", "dark", "nocturnal"],
    },
    ProductionStyle.ambient.value: {
        "compatible_genres": [Genre.cinematic],
        "arrangement_style": "atmospheric ambient",
        "instruments": ["pads", "textures", "soft piano", "drones"],
        "mood_tags": ["ambient", "spacious", "cinematic"],
    },
    ProductionStyle.orchestral_pop.value: {
        "compatible_genres": [Genre.cinematic, Genre.pop],
        "arrangement_style": "pop with orchestral build",
        "instruments": ["piano", "strings", "drums", "bass", "pads"],
        "mood_tags": ["emotional", "cinematic", "building"],
    },
    ProductionStyle.qawwali_fusion.value: {
        "compatible_genres": [Genre.cinematic],
        "arrangement_style": "Qawwali harmonium + claps",
        "instruments": ["harmonium", "claps", "tabla", "dholak", "bass", "strings", "chorus vocals"],
        "mood_tags": ["devotional", "powerful", "spiritual", "rising energy"],
    },
    ProductionStyle.ghazal_pop.value: {
        "compatible_genres": [Genre.pop, Genre.acoustic],
        "arrangement_style": "Minimal vocal piano",
        "instruments": ["piano", "tabla brush", "strings", "soft bass"],
        "mood_tags": ["poetic", "romantic", "intimate"],
    },
    ProductionStyle.bhajan_devotional.value: {
        "compatible_genres": [Genre.acoustic],
        "arrangement_style": "Tabla + strings fusion",
        "instruments": ["harmonium", "tabla", "tanpura", "flute", "soft strings"],
        "mood_tags": ["peaceful", "devotional", "warm", "spiritual"],
    },
    ProductionStyle.folk_fusion.value: {
        "compatible_genres": [Genre.acoustic, Genre.pop],
        "arrangement_style": "Folk acoustic arrangement",
        "instruments": ["acoustic guitar", "dholak", "flute", "bass", "hand percussion"],
        "mood_tags": ["earthy", "warm", "melodic"],
    },
    ProductionStyle.sufi_rock.value: {
        "compatible_genres": [Genre.rock, Genre.pop],
        "arrangement_style": "Indie band arrangement",
        "instruments": ["electric guitar", "bass", "drums", "harmonium texture", "strings", "backing vocals"],
        "mood_tags": ["spiritual", "intense", "emotional", "anthemic"],
    },
    ProductionStyle.punjabi_pop.value: {
        "compatible_genres": [Genre.pop, Genre.hiphop],
        "arrangement_style": "Electronic pop arrangement",
        "instruments": ["dhol", "tumbi texture", "pop drums", "bass", "synths"],
        "mood_tags": ["bright", "confident", "celebratory"],
    },
    ProductionStyle.south_indian_cinematic.value: {
        "compatible_genres": [Genre.cinematic, Genre.pop],
        "arrangement_style": "Cinematic strings build",
        "instruments": ["strings", "cinematic drums", "pads", "flute texture", "bass"],
        "mood_tags": ["cinematic", "emotional", "grand"],
    },
}


class MockAIWorker:
    def __init__(self, repository: InMemoryJobRepository) -> None:
        self.repository = repository

    def run_job(self, job_id: str):
        job = self.repository.get(job_id)
        if job is None:
            raise KeyError(job_id)

        if job.raw_audio_path is None:
            return self.repository.update_status(job_id, JobStatus.failed, "failed", "Raw audio is missing")

        self.repository.update_status(job_id, JobStatus.analyzing, "analyzing")
        self.repository.update_status(job_id, JobStatus.generating, "generating")
        self.repository.update_status(job_id, JobStatus.mixing, "mixing")
        final_path = final_mp3_path(job.user_id, job.job_id, job.track_name, job.raw_audio_path)
        analysis = fallback_song_analysis(
            job.genre,
            {
                "duration": 30.0,
                "tempo_bpm": 92.0,
                "production_style": job.production_style.value if job.production_style else None,
                "arrangement_style": job.arrangement_style,
                "main_instruments": job.main_instruments,
            },
        )
        blueprint = build_song_blueprint(analysis, job.genre)
        self.repository.set_worker_artifacts(
            job_id,
            worker_notes="mock demo project",
            export_paths={"mp3": final_path},
            analysis=analysis,
            blueprint=blueprint,
        )
        self.repository.set_final_mp3(job_id, final_path)
        ready = self.repository.update_status(job_id, JobStatus.ready, "ready")

        if ready.delete_raw_after_mix:
            ready = self.repository.delete_raw(job_id)

        return ready


class MvpAudioWorker:
    def __init__(self, repository: InMemoryJobRepository, storage_service=storage, ffmpeg_path: str | None = None) -> None:
        self.repository = repository
        self.storage = storage_service
        self.ffmpeg_path = ffmpeg_path or settings.ffmpeg_path

    def run_job(self, job_id: str):
        job = self.repository.get(job_id)
        if job is None:
            raise KeyError(job_id)

        if job.raw_audio_path is None:
            return self.repository.update_status(job_id, JobStatus.failed, "failed", "Raw audio is missing")

        if shutil.which(self.ffmpeg_path) is None and not Path(self.ffmpeg_path).exists():
            return self.repository.update_status(job_id, JobStatus.failed, "failed", "FFmpeg is not available")

        raw_audio_path = job.raw_audio_path
        arrangement_mode = job.arrangement_mode or ArrangementMode.vocal_to_song
        isolated_path: str | None = None
        backing_path: str | None = None
        final_path: str | None = None
        export_paths: dict[str, str] = {}
        analysis: SongAnalysis | None = None
        blueprint: SongBlueprint | None = None
        final_generation_settings: dict[str, Any] = {}
        generation_diagnostics: dict[str, Any] = {
            "selected_generator": settings.music_generator_backend,
            "arrangement_mode": arrangement_mode.value,
            "source_type": job.source_type.value,
            "timeout_seconds": timeout_snapshot(),
            "generation_start_time": utc_now_iso(),
            "last_known_worker_step": "starting",
        }
        job_logs: list[str] = []
        quality_report: dict[str, Any] | None = None
        current_step = "starting"

        def mark(status: JobStatus, stage: str, message: str | None = None):
            nonlocal current_step
            current_step = stage
            generation_diagnostics["last_known_worker_step"] = stage
            if message:
                add_job_log(job_logs, message)
            return self.repository.update_status(job_id, status, stage)

        def fail_job(message: str, stage: str | None = None):
            failed_stage = stage or current_step or "failed"
            generation_diagnostics["last_known_worker_step"] = failed_stage
            generation_diagnostics["error"] = message
            generation_diagnostics["failed_at"] = utc_now_iso()
            add_job_log(job_logs, message)
            try:
                self.repository.set_worker_artifacts(
                    job_id,
                    isolated_vocal_path=isolated_path,
                    backing_audio_path=backing_path,
                    worker_notes=f"failed_at={failed_stage}; generator={settings.music_generator_backend}; error={message[:180]}",
                    export_paths=export_paths,
                    analysis=analysis,
                    blueprint=blueprint,
                    final_generation_settings=final_generation_settings,
                    generation_diagnostics=generation_diagnostics,
                    job_logs=job_logs,
                    quality_report=quality_report,
                )
            except Exception:
                pass
            return self.repository.update_status(job_id, JobStatus.failed, failed_stage, message[:240])

        try:
            mark(JobStatus.analyzing, "normalizing input", "Normalizing input audio.")
            raw_bytes = self.storage.download_bytes(raw_audio_path)
            with tempfile.TemporaryDirectory(prefix=f"skarly-{job_id}-") as temp_dir:
                temp = Path(temp_dir)
                raw_input = temp / f"raw-input{input_suffix(raw_audio_path)}"
                normalized_wav = temp / "normalized.wav"
                vocal_wav = temp / "vocal-isolated.wav"
                vocal_clean_wav = temp / "vocal-clean.wav"
                bed_wav = temp / "genre-bed.wav"
                final_wav = temp / "final.wav"
                final_mp3 = temp / "final.mp3"
                midi_file = temp / "chords.mid"
                melody_midi = temp / "melody.mid"
                melody_notes = temp / "melody-notes.csv"
                chord_sheet = temp / "chord-sheet.txt"
                blueprint_json = temp / "song_blueprint.json"
                analysis_json = temp / "analysis.json"
                producer_prompt_txt = temp / "producer_prompt.txt"
                quality_report_json = temp / "quality_report.json"
                producer_pack = temp / "producer-pack.zip"
                instrument_stem_dir = temp / "instrument-stems"
                preview_vocal_mp3 = temp / "preview_vocal_only.mp3"
                preview_backing_mp3 = temp / "preview_backing_only.mp3"
                preview_final_mp3 = temp / "preview_final_mix.mp3"
                raw_input.write_bytes(raw_bytes)
                target_duration = requested_output_duration(job)
                user_overrides = dict(job.user_overrides or {})
                generation_diagnostics["requested_duration"] = target_duration
                generation_diagnostics["user_overrides"] = user_overrides

                self._run_ffmpeg([
                    "-y",
                    "-i",
                    str(raw_input),
                    "-t",
                    str(target_duration),
                    "-ac",
                    "2",
                    "-ar",
                    "44100",
                    "-af",
                    "loudnorm",
                    str(normalized_wav),
                ], timeout=settings.analysis_timeout_sec)

                wants_lead_vocal = arrangement_mode != ArrangementMode.music_to_music
                isolate_vocals = wants_lead_vocal and should_isolate_vocals(job.source_type, arrangement_mode)
                vocal_isolation_status = "not_required"
                vocal_isolation_error: str | None = None
                if isolate_vocals:
                    mark(JobStatus.analyzing, "vocal isolation", "Isolating lead vocal.")
                    try:
                        vocal_wav, leakage_quality = self._isolate_vocals(normalized_wav, temp / "stems")
                        vocal_isolation_status = "demucs"
                        generation_diagnostics["vocal_isolation"] = {
                            "status": vocal_isolation_status,
                            "model": settings.demucs_model,
                            "device": settings.demucs_device,
                            "leakage_quality": leakage_quality,
                        }
                    except VocalIsolationError as exc:
                        vocal_isolation_error = str(exc)
                        vocal_isolation_status = "failed"
                        add_job_log(
                            job_logs,
                            "Full-song generation stopped because a validated isolated vocal was not produced.",
                        )
                        generation_diagnostics["vocal_isolation"] = {
                            "status": vocal_isolation_status,
                            "error": vocal_isolation_error[:240],
                        }
                        return fail_job(
                            f"Full-song vocal isolation failed: {vocal_isolation_error[:220]}",
                            "vocal isolation",
                        )
                else:
                    vocal_wav = normalized_wav
                if "vocal_isolation" not in generation_diagnostics:
                    generation_diagnostics["vocal_isolation"] = {"status": vocal_isolation_status}

                if wants_lead_vocal and settings.vocal_cleanup_enabled:
                    mark(JobStatus.analyzing, "vocal cleanup", "Cleaning vocal preview.")
                    cleanup_filter = (
                        "highpass=f=120,lowpass=f=11000,afftdn=nf=-24,"
                        "agate=threshold=0.018:ratio=2.2:attack=8:release=180,"
                        "acompressor=threshold=-20dB:ratio=2.4:attack=10:release=140,loudnorm"
                        if isolate_vocals
                        else "highpass=f=90,lowpass=f=14500,afftdn=nf=-24,loudnorm"
                    )
                    self._run_ffmpeg([
                        "-y",
                        "-i",
                        str(vocal_wav),
                        "-af",
                        cleanup_filter,
                        str(vocal_clean_wav),
                    ], timeout=settings.separation_timeout_sec)
                else:
                    vocal_clean_wav = vocal_wav

                mark(JobStatus.generating, "analyzing timing", "Analyzing timing, tempo, key, and style.")
                timing_source_wav = vocal_clean_wav if wants_lead_vocal else normalized_wav
                duration = audio_duration_seconds(timing_source_wav, self.ffmpeg_path)
                timing = analyze_vocal_timing(timing_source_wav, self.ffmpeg_path)
                generation_timing = {
                    **timing,
                    "arrangement_mode": arrangement_mode.value,
                    "source_type": job.source_type.value,
                    "language": clean_language(user_overrides.get("language")),
                    "lyrics": clean_prompt_text(user_overrides.get("lyrics"), 2000),
                    "mood_tags": clean_mood_tags(user_overrides.get("mood_tags")),
                    "production_style": job.production_style.value if job.production_style else None,
                    "arrangement_style": job.arrangement_style,
                    "main_instruments": job.main_instruments,
                }
                analysis = analyze_demo_idea(timing_source_wav, job.genre, generation_timing, self.ffmpeg_path)
                auto_analysis = analysis.model_dump(mode="json")
                analysis = apply_user_overrides_to_analysis(analysis, user_overrides)
                generation_timing["auto_analysis"] = auto_analysis
                generation_timing["user_overrides"] = user_overrides
                generation_timing.update(analysis_timing_metadata(analysis))
                blueprint = build_song_blueprint(analysis, job.genre, generation_timing)
                producer_prompt = build_producer_prompt(job.genre, analysis, blueprint, arrangement_mode, generation_timing)
                producer_negative_prompt = build_producer_negative_prompt(job.genre, analysis)
                generation_timing["producer_prompt"] = producer_prompt
                generation_timing["producer_negative_prompt"] = producer_negative_prompt
                mix_settings = build_mix_settings(user_overrides, arrangement_mode)
                generation_timing["mix_settings"] = mix_settings
                final_generation_settings = build_final_generation_settings(
                    job.genre,
                    analysis,
                    arrangement_mode,
                    generation_timing,
                )
                producer_prompt_txt.write_text(
                    producer_prompt + "\n\nNegative prompt:\n" + producer_negative_prompt + "\n",
                    encoding="utf-8",
                )
                mark(JobStatus.generating, "backing generation", "Generating backing track.")
                generation_report = create_music_bed_with_report(
                    bed_wav,
                    job.genre,
                    job_id,
                    seconds=duration,
                    source_audio_path=timing_source_wav,
                    timing=generation_timing,
                    ffmpeg_path=self.ffmpeg_path,
                )
                generation_diagnostics["backing_generation"] = generation_report
                generation_timing["generation_report"] = generation_report
                for warning in generation_report.get("warnings", []):
                    append_warning(analysis, warning)
                final_generation_settings.update({
                    "selected_generator": generation_report.get("selected_generator"),
                    "final_generator_used": generation_report.get("final_generator_used"),
                    "fallback_attempted": generation_report.get("fallback_attempted"),
                    "fallback_result": generation_report.get("fallback_result"),
                    "mix": mix_settings,
                    "auto_analysis": auto_analysis,
                    "user_overrides": user_overrides,
                })
                mark(JobStatus.generating, "backing cleanup", "Validating and preparing backing audio.")
                bed_mix_wav = self._prepare_backing_bed(bed_wav, temp / "backing-clean.wav", temp / "backing-stems")
                instrument_stems = self._derive_backing_stems(bed_mix_wav, instrument_stem_dir)

                mark(JobStatus.mixing, "mixing", "Mixing vocal and backing.")
                if arrangement_mode == ArrangementMode.music_to_music:
                    self._finalize_instrumental_mix(bed_mix_wav, final_wav)
                else:
                    self._mix_vocal_with_backing(vocal_clean_wav, bed_mix_wav, final_wav, mix_settings)
                mark(JobStatus.mixing, "exporting mp3", "Exporting final MP3.")
                self._run_ffmpeg([
                    "-y",
                    "-i",
                    str(final_wav),
                    "-codec:a",
                    "libmp3lame",
                    "-b:a",
                    "192k",
                    str(final_mp3),
                ], timeout=settings.export_timeout_sec)

                write_midi_chords(midi_file, blueprint, analysis)
                melody_midi_file: Path | None = None
                melody_notes_file: Path | None = None
                melody_status = "unavailable"
                melody_note_count = 0
                fallback_used = False
                source_loudness = audio_rms(timing_source_wav)
                logger.info("Melody extraction source=%s loudness=%s", timing_source_wav, source_loudness)
                mark(JobStatus.mixing, "melody analysis", "Creating melody MIDI and chord assets.")
                if settings.melody_analyzer_backend == "off":
                    analysis.melody_midi_status = "unavailable"
                    append_warning(analysis, "Melody MIDI unavailable because the melody analyzer is disabled.")
                    melody_status = "unavailable:disabled"
                else:
                    try:
                        melody_midi_file, melody_notes_file = self._create_melody_midi(
                            timing_source_wav,
                            temp / "basic-pitch",
                            melody_midi,
                            melody_notes,
                            analysis,
                        )
                        if melody_midi_file:
                            melody_note_count = count_midi_notes(melody_midi_file)
                            analysis.pitch_contour_status = "available"
                            analysis.melody_midi_status = "available"
                            analysis.pitch_summary = "Pitch contour extracted from isolated vocal."
                            melody_status = "available"
                            logger.info(
                                "Basic Pitch melody output=%s notes=%s fallback_used=false",
                                melody_midi_file,
                                melody_note_count,
                            )
                    except MelodyAnalysisError as exc:
                        basic_pitch_error = str(exc)
                        logger.info("Basic Pitch melody failed: %s", basic_pitch_error)
                        try:
                            melody_midi_file, melody_notes_file = create_fallback_pitch_melody(
                                timing_source_wav,
                                melody_midi,
                                melody_notes,
                                analysis,
                                reason=basic_pitch_error,
                            )
                            melody_note_count = count_midi_notes(melody_midi_file)
                            fallback_used = True
                            analysis.pitch_contour_status = "fallback_used"
                            analysis.melody_midi_status = "fallback_used"
                            analysis.pitch_summary = "Fallback pitch contour used because Basic Pitch was unavailable or too weak."
                            append_warning(analysis, "Fallback pitch contour used because Basic Pitch was unavailable or returned low-confidence output.")
                            melody_status = "fallback_used"
                            logger.info(
                                "Fallback melody output=%s notes=%s fallback_used=true",
                                melody_midi_file,
                                melody_note_count,
                            )
                        except MelodyAnalysisError as fallback_exc:
                            analysis.melody_midi_status = "unavailable"
                            if analysis.pitch_contour_status == "unavailable":
                                analysis.pitch_summary = "Pitch contour could not be extracted because the vocal was too weak or noisy."
                            append_warning(
                                analysis,
                                f"Melody MIDI unavailable: {str(fallback_exc)[:140]}",
                            )
                            melody_status = f"unavailable:{str(fallback_exc)[:90]}"
                            logger.info("Fallback melody failed: %s", fallback_exc)
                write_chord_sheet(chord_sheet, job.track_name, job.genre, analysis, blueprint, arrangement_mode)
                preview_files = self._create_preview_exports(
                    vocal_clean_wav if wants_lead_vocal else None,
                    bed_mix_wav,
                    final_wav,
                    preview_vocal_mp3,
                    preview_backing_mp3,
                    preview_final_mp3,
                )
                analysis_json.write_text(json.dumps(analysis.model_dump(mode="json"), indent=2), encoding="utf-8")
                blueprint_json.write_text(
                    json.dumps(
                        {
                            "arrangement_mode": arrangement_mode.value,
                            "melody_analyzer_backend": settings.melody_analyzer_backend,
                            "auto_analysis": auto_analysis,
                            "user_overrides": user_overrides,
                            "final_generation_settings": final_generation_settings,
                            "generation_diagnostics": generation_diagnostics,
                            "producer_prompt": producer_prompt,
                            "producer_negative_prompt": producer_negative_prompt,
                            "analysis": analysis.model_dump(mode="json"),
                            "blueprint": blueprint.model_dump(mode="json"),
                        },
                        indent=2,
                    ),
                    encoding="utf-8",
                )
                producer_pack_files = {
                    "final-demo.mp3": final_mp3,
                    "final-demo.wav": final_wav,
                    "source-reference.wav": normalized_wav,
                    "backing-stem.wav": bed_mix_wav,
                    "chords.mid": midi_file,
                    "chord-sheet.txt": chord_sheet,
                    "song_blueprint.json": blueprint_json,
                    "analysis.json": analysis_json,
                    "producer_prompt.txt": producer_prompt_txt,
                }
                if melody_midi_file:
                    producer_pack_files["melody.mid"] = melody_midi_file
                if melody_notes_file:
                    producer_pack_files["melody-notes.csv"] = melody_notes_file
                if wants_lead_vocal:
                    producer_pack_files["vocal-stem.wav"] = vocal_clean_wav
                for stem_name, stem_file in instrument_stems.items():
                    producer_pack_files[f"stems/{stem_name}.wav"] = stem_file
                for pack_name, preview_file in preview_files.items():
                    producer_pack_files[pack_name] = preview_file
                quality_report = build_quality_report(
                    raw_input=raw_input,
                    normalized_wav=normalized_wav,
                    vocal_wav=vocal_clean_wav if wants_lead_vocal else None,
                    backing_wav=bed_mix_wav,
                    final_wav=final_wav,
                    final_mp3=final_mp3,
                    melody_midi=melody_midi_file,
                    chords_midi=midi_file,
                    chord_sheet=chord_sheet,
                    producer_pack=producer_pack,
                    analysis=analysis,
                    target_duration=duration,
                    melody_status=melody_status,
                    melody_note_count=melody_note_count,
                    fallback_used=fallback_used,
                    expected_pack_files=[*producer_pack_files.keys(), "quality_report.json"],
                    final_generation_settings=final_generation_settings,
                    generation_diagnostics=generation_diagnostics,
                    job_logs=job_logs,
                    preview_files=preview_files,
                    ffmpeg_path=self.ffmpeg_path,
                )
                quality_report_json.write_text(json.dumps(quality_report, indent=2), encoding="utf-8")
                producer_pack_files["quality_report.json"] = quality_report_json
                mark(JobStatus.mixing, "packaging", "Writing Producer Pack.")
                write_producer_pack(
                    producer_pack,
                    producer_pack_files,
                )
                quality_report = build_quality_report(
                    raw_input=raw_input,
                    normalized_wav=normalized_wav,
                    vocal_wav=vocal_clean_wav if wants_lead_vocal else None,
                    backing_wav=bed_mix_wav,
                    final_wav=final_wav,
                    final_mp3=final_mp3,
                    melody_midi=melody_midi_file,
                    chords_midi=midi_file,
                    chord_sheet=chord_sheet,
                    producer_pack=producer_pack,
                    analysis=analysis,
                    target_duration=duration,
                    melody_status=melody_status,
                    melody_note_count=melody_note_count,
                    fallback_used=fallback_used,
                    expected_pack_files=list(producer_pack_files.keys()),
                    final_generation_settings=final_generation_settings,
                    generation_diagnostics=generation_diagnostics,
                    job_logs=job_logs,
                    preview_files=preview_files,
                    ffmpeg_path=self.ffmpeg_path,
                )
                quality_report_json.write_text(json.dumps(quality_report, indent=2), encoding="utf-8")
                write_producer_pack(
                    producer_pack,
                    producer_pack_files,
                )

                final_path = final_mp3_path_for_job(job.user_id, job.job_id, job.track_name, job.raw_audio_path)
                isolated_path = debug_audio_path_for_job(job.user_id, job.job_id, "isolated-vocal.wav", job.raw_audio_path) if wants_lead_vocal else None
                backing_path = debug_audio_path_for_job(job.user_id, job.job_id, "backing-only.wav", job.raw_audio_path)
                final_wav_path = demo_export_path_for_job(job.user_id, job.job_id, "final-demo.wav", job.raw_audio_path)
                midi_path = demo_export_path_for_job(job.user_id, job.job_id, "chords.mid", job.raw_audio_path)
                melody_midi_path = demo_export_path_for_job(job.user_id, job.job_id, "melody.mid", job.raw_audio_path)
                chord_sheet_path = demo_export_path_for_job(job.user_id, job.job_id, "chord-sheet.txt", job.raw_audio_path)
                producer_pack_path = demo_export_path_for_job(job.user_id, job.job_id, "producer-pack.zip", job.raw_audio_path)
                reference_path = demo_export_path_for_job(job.user_id, job.job_id, "source-reference.wav", job.raw_audio_path)
                export_paths = {
                    "mp3": final_path,
                    "wav": final_wav_path,
                    "midi": midi_path,
                    "chord_sheet": chord_sheet_path,
                    "producer_pack": producer_pack_path,
                    "backing_stem": backing_path,
                    "reference_stem": reference_path,
                }
                if melody_midi_file:
                    export_paths["melody_midi"] = melody_midi_path
                if isolated_path:
                    export_paths["vocal_stem"] = isolated_path
                    self.storage.upload_bytes(isolated_path, vocal_clean_wav.read_bytes(), "audio/wav")
                for preview_name, preview_file in preview_files.items():
                    preview_path = demo_export_path_for_job(job.user_id, job.job_id, preview_name, job.raw_audio_path)
                    export_paths[preview_name.removesuffix(".mp3")] = preview_path
                    self.storage.upload_bytes(preview_path, preview_file.read_bytes(), "audio/mpeg")
                self.storage.upload_bytes(backing_path, bed_mix_wav.read_bytes(), "audio/wav")
                self.storage.upload_bytes(reference_path, normalized_wav.read_bytes(), "audio/wav")
                for stem_name, stem_file in instrument_stems.items():
                    stem_path = demo_export_path_for_job(job.user_id, job.job_id, f"{stem_name}.wav", job.raw_audio_path)
                    export_paths[f"{stem_name.replace('-', '_')}_stem"] = stem_path
                    self.storage.upload_bytes(stem_path, stem_file.read_bytes(), "audio/wav")
                self.storage.upload_bytes(final_path, final_mp3.read_bytes(), "audio/mpeg")
                self.storage.upload_bytes(final_wav_path, final_wav.read_bytes(), "audio/wav")
                self.storage.upload_bytes(midi_path, midi_file.read_bytes(), "audio/midi")
                if melody_midi_file:
                    self.storage.upload_bytes(melody_midi_path, melody_midi_file.read_bytes(), "audio/midi")
                self.storage.upload_bytes(chord_sheet_path, chord_sheet.read_bytes(), "text/plain")
                self.storage.upload_bytes(producer_pack_path, producer_pack.read_bytes(), "application/zip")

            self.repository.set_worker_artifacts(
                job_id,
                isolated_vocal_path=isolated_path,
                backing_audio_path=backing_path,
                worker_notes=(
                    f"mode={arrangement_mode.value}; source={job.source_type.value}; "
                    f"style={analysis.production_style or job.genre.value}; arrangement={analysis.arrangement_style or 'unknown'}; "
                    f"isolation={vocal_isolation_status}; generator={final_generation_settings.get('final_generator_used') or settings.music_generator_backend}; "
                    f"fallback={final_generation_settings.get('fallback_result') or 'not_attempted'}; "
                    f"melody={melody_status}; "
                    f"detected_tempo={analysis.detected_bpm or analysis.bpm or timing.get('tempo_bpm', 'unknown')}; "
                    f"production_tempo={analysis.production_bpm or analysis.bpm or 'unknown'}; key={analysis.primary_key or analysis.key or 'unknown'}; "
                    f"vocal_gain_db={mix_settings.get('vocal_gain_db')}; backing_gain_db={mix_settings.get('backing_gain_db')}; "
                    f"ducking={mix_settings.get('ducking_strength')}; instrumental_gain={settings.instrumental_mix_gain}; "
                    f"stems={','.join(sorted(instrument_stems)) or 'none'}"
                ),
                export_paths=export_paths,
                analysis=analysis,
                blueprint=blueprint,
                final_generation_settings=final_generation_settings,
                generation_diagnostics=generation_diagnostics,
                job_logs=job_logs,
                quality_report=quality_report,
            )
            self.repository.set_final_mp3(job_id, final_path)
            ready = self.repository.update_status(job_id, JobStatus.ready, "ready")
            if ready.delete_raw_after_mix:
                self.storage.delete_object(raw_audio_path)
                ready = self.repository.delete_raw(job_id)
            return ready
        except FileNotFoundError:
            return fail_job("Raw audio is missing", "failed")
        except VocalIsolationError as exc:
            return fail_job(f"Vocal isolation failed: {exc}", "vocal isolation")
        except BackingGenerationError as exc:
            return fail_job(str(exc), "backing generation")
        except GeneratedBackingCleanupError as exc:
            return fail_job(f"Generated backing cleanup failed: {exc}", "backing cleanup")
        except subprocess.TimeoutExpired as exc:
            return fail_job(f"{readable_step(current_step)} timed out after {exc.timeout} seconds.", current_step)
        except subprocess.CalledProcessError as exc:
            message = useful_subprocess_error(exc.stderr.decode("utf-8", errors="ignore") if exc.stderr else "")
            return fail_job(message[:240], current_step)
        except Exception as exc:
            return fail_job(f"Audio worker failed during {readable_step(current_step)}: {exc}", current_step)

    def _run_ffmpeg(self, args: list[str], timeout: int | None = None) -> None:
        subprocess.run(
            [self.ffmpeg_path, *args],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout or settings.export_timeout_sec,
        )

    def _isolate_vocals(self, input_wav: Path, output_dir: Path) -> tuple[Path, dict[str, Any]]:
        if settings.stem_separator_backend == "off":
            raise VocalIsolationError("Demucs is disabled for a full-song upload")
        separated = stems_service.separate_stems(
            audio_path=input_wav,
            output_dir=output_dir,
            job_id="lead-vocal",
            stems=["vocals", "no_vocals"],
            engine="demucs",
            timeout_seconds=settings.separation_timeout_sec,
            enabled=True,
            demucs_cli_path=settings.demucs_path,
            demucs_model=settings.demucs_model,
            demucs_device=settings.demucs_device,
        )
        vocal_path = separated.stem_paths.get("vocals")
        instrumental_path = separated.stem_paths.get("no_vocals")
        if separated.status not in {"completed", "completed_partial"} or not vocal_path or not instrumental_path:
            logs = separated.diagnostics.last_logs[-3:] if separated.diagnostics else []
            detail = " | ".join([*separated.warnings[:3], *logs])[:500]
            raise VocalIsolationError(detail or "Demucs did not produce validated vocal stems")
        leakage_quality = music_source.assess_vocal_leakage(vocal_path, instrumental_path)
        if not leakage_quality.passed:
            raise VocalIsolationError(" ".join(leakage_quality.warnings[:2]) or "Vocal leakage quality gate failed")
        return Path(vocal_path), leakage_quality.model_dump(mode="json")

    def _prepare_backing_bed(self, bed_wav: Path, cleaned_bed_wav: Path, output_dir: Path) -> Path:
        if settings.music_generator_backend != "ace_step" or not settings.backing_vocal_cleanup_enabled or settings.stem_separator_backend == "off":
            return bed_wav
        try:
            no_vocals = self._separate_stem(bed_wav, output_dir, "no_vocals.wav")
        except VocalIsolationError as exc:
            logger.info("Generated backing cleanup skipped: %s", exc)
            return bed_wav
        self._run_ffmpeg([
            "-y",
            "-i",
            str(no_vocals),
            "-af",
            "highpass=f=35,lowpass=f=13500,loudnorm",
            str(cleaned_bed_wav),
        ], timeout=settings.separation_timeout_sec)
        return cleaned_bed_wav

    def _mix_vocal_with_backing(self, vocal_wav: Path, bed_wav: Path, final_wav: Path, mix_settings: dict[str, Any] | None = None) -> None:
        mix = mix_settings or build_mix_settings({}, ArrangementMode.vocal_to_song)
        vocal_gain = db_to_linear(float(mix.get("vocal_gain_db", settings.default_vocal_gain_db)))
        backing_gain = db_to_linear(float(mix.get("backing_gain_db", settings.default_backing_gain_db)))
        ducking = str(mix.get("ducking_strength") or settings.default_ducking_strength).lower()
        if ducking == "off":
            vocal_chain = f"[0:a]volume={vocal_gain:.4f},acompressor=threshold=-18dB:ratio=2.0:attack=10:release=140,aformat=channel_layouts=stereo[vocalmix];"
            bed_chain = "[bedraw]anull[bed];"
        else:
            vocal_chain = (
                f"[0:a]volume={vocal_gain:.4f},acompressor=threshold=-18dB:ratio=2.0:attack=10:release=140,"
                "aformat=channel_layouts=stereo[vocalmain];[vocalmain]asplit=2[vocalduck][vocalmix];"
            )
            duck = ducking_parameters(ducking)
            bed_chain = (
                f"[bedraw][vocalduck]sidechaincompress=threshold={duck['threshold']}:"
                f"ratio={duck['ratio']}:attack={duck['attack']}:release={duck['release']}[bed];"
            )
        self._run_ffmpeg([
            "-y",
            "-i",
            str(vocal_wav),
            "-i",
            str(bed_wav),
            "-filter_complex",
            (
                vocal_chain
                +
                f"[1:a]volume={backing_gain:.4f},lowpass=f=13000,aformat=channel_layouts=stereo[bedraw];"
                f"{bed_chain}"
                "[vocalmix][bed]amix=inputs=2:duration=first:dropout_transition=2,alimiter=limit=0.94"
            ),
            "-ac",
            "2",
            "-ar",
            "44100",
            "-c:a",
            "pcm_s16le",
            str(final_wav),
        ], timeout=settings.mixing_timeout_sec)

    def _finalize_instrumental_mix(self, bed_wav: Path, final_wav: Path) -> None:
        self._run_ffmpeg([
            "-y",
            "-i",
            str(bed_wav),
            "-af",
            f"volume={settings.instrumental_mix_gain},acompressor=threshold=-16dB:ratio=1.6:attack=8:release=160,alimiter=limit=0.94",
            "-ac",
            "2",
            "-ar",
            "44100",
            "-c:a",
            "pcm_s16le",
            str(final_wav),
        ], timeout=settings.mixing_timeout_sec)

    def _derive_backing_stems(self, bed_wav: Path, output_dir: Path) -> dict[str, Path]:
        output_dir.mkdir(parents=True, exist_ok=True)
        filters = {
            "drums": "highpass=f=80,lowpass=f=14000,acompressor=threshold=-22dB:ratio=2.4:attack=3:release=90,loudnorm",
            "bass": "lowpass=f=240,acompressor=threshold=-24dB:ratio=2.8:attack=8:release=160,volume=1.25,loudnorm",
            "guitar": "highpass=f=150,lowpass=f=5200,acompressor=threshold=-23dB:ratio=2.0:attack=5:release=120,volume=1.1,loudnorm",
            "keys": "highpass=f=220,lowpass=f=11000,acompressor=threshold=-24dB:ratio=1.8:attack=12:release=180,loudnorm",
        }
        stems: dict[str, Path] = {}
        for stem_name, audio_filter in filters.items():
            stem_path = output_dir / f"{stem_name}.wav"
            self._run_ffmpeg([
                "-y",
                "-i",
                str(bed_wav),
                "-af",
                audio_filter,
                "-ac",
                "2",
                "-ar",
                "44100",
                "-c:a",
                "pcm_s16le",
                str(stem_path),
            ], timeout=settings.export_timeout_sec)
            stems[stem_name] = stem_path
        return stems

    def _create_preview_exports(
        self,
        vocal_wav: Path | None,
        backing_wav: Path,
        final_wav: Path,
        preview_vocal_mp3: Path,
        preview_backing_mp3: Path,
        preview_final_mp3: Path,
    ) -> dict[str, Path]:
        previews: dict[str, Path] = {}
        sources = {
            "preview_backing_only.mp3": (backing_wav, preview_backing_mp3),
            "preview_final_mix.mp3": (final_wav, preview_final_mp3),
        }
        if vocal_wav is not None:
            sources["preview_vocal_only.mp3"] = (vocal_wav, preview_vocal_mp3)
        for name, (source, output) in sources.items():
            if not source.exists():
                continue
            try:
                self._run_ffmpeg([
                    "-y",
                    "-i",
                    str(source),
                    "-t",
                    "30",
                    "-codec:a",
                    "libmp3lame",
                    "-b:a",
                    "160k",
                    str(output),
                ], timeout=settings.export_timeout_sec)
            except Exception as exc:
                logger.info("Preview export skipped for %s: %s", name, exc)
                continue
            if output.exists() and output.stat().st_size > 0:
                previews[name] = output
        return previews

    def _separate_stem(self, input_wav: Path, output_dir: Path, stem_name: str) -> Path:
        if settings.stem_separator_backend != "demucs":
            raise VocalIsolationError(f"Unsupported stem separator: {settings.stem_separator_backend}")
        separated = stems_service.separate_stems(
            audio_path=input_wav,
            output_dir=output_dir,
            job_id=f"{input_wav.stem}-{Path(stem_name).stem}",
            stems=["vocals", "no_vocals"],
            engine="demucs",
            timeout_seconds=settings.separation_timeout_sec,
            enabled=True,
            demucs_cli_path=settings.demucs_path,
            demucs_model=settings.demucs_model,
            demucs_device=settings.demucs_device,
        )
        requested = Path(stem_name).stem
        candidate = separated.stem_paths.get(requested)
        if separated.status not in {"completed", "completed_partial"} or not candidate:
            logs = separated.diagnostics.last_logs[-3:] if separated.diagnostics else []
            detail = " | ".join([*separated.warnings[:3], *logs])[:500]
            raise VocalIsolationError(detail or f"Demucs did not produce {stem_name}")
        return Path(candidate)

    def _create_melody_midi(
        self,
        input_wav: Path,
        output_dir: Path,
        output_midi: Path,
        output_notes: Path,
        analysis: SongAnalysis,
    ) -> tuple[Path | None, Path | None]:
        if settings.melody_analyzer_backend == "off":
            return None, None
        if settings.melody_analyzer_backend != "basic_pitch":
            raise MelodyAnalysisError(f"Unsupported melody analyzer: {settings.melody_analyzer_backend}")
        return create_basic_pitch_melody(input_wav, output_dir, output_midi, output_notes, analysis)


class VocalIsolationError(RuntimeError):
    pass


class GeneratedBackingCleanupError(RuntimeError):
    pass


class MelodyAnalysisError(RuntimeError):
    pass


class BackingGenerationError(RuntimeError):
    pass


def input_suffix(raw_audio_path: str) -> str:
    suffix = Path(raw_audio_path).suffix.lower()
    return suffix if suffix in {".mp3", ".wav", ".m4a", ".webm", ".aac", ".ogg", ".flac"} else ".audio"


def should_isolate_vocals(source_type: SourceType, arrangement_mode: ArrangementMode = ArrangementMode.vocal_to_song) -> bool:
    if arrangement_mode != ArrangementMode.full_song:
        return False
    return settings.stem_separator_backend != "off" and source_type in {SourceType.local_upload, SourceType.sample_upload}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def add_job_log(job_logs: list[str], message: str) -> None:
    job_logs.append(f"{utc_now_iso()} {message}")


def readable_step(value: str | None) -> str:
    return str(value or "worker step").replace("_", " ").replace("-", " ")


def timeout_snapshot() -> dict[str, int | float]:
    return {
        "analysis_timeout_sec": settings.analysis_timeout_sec,
        "separation_timeout_sec": settings.separation_timeout_sec,
        "melody_timeout_sec": settings.melody_timeout_sec,
        "backing_generation_timeout_sec": settings.backing_generation_timeout_sec,
        "mixing_timeout_sec": settings.mixing_timeout_sec,
        "export_timeout_sec": settings.export_timeout_sec,
        "studio_poll_timeout_sec": settings.studio_poll_timeout_sec,
        "ace_step_timeout_seconds": settings.ace_step_timeout_seconds,
        "ace_step_download_timeout_seconds": settings.ace_step_download_timeout_seconds,
    }


def requested_output_duration(job: JobRecord) -> int:
    overrides = job.user_overrides or {}
    requested = coerce_float(overrides.get("output_duration_seconds"))
    if requested:
        return int(max(10, min(settings.max_demo_duration_seconds, requested)))
    return settings.max_demo_duration_seconds


def apply_user_overrides_to_analysis(analysis: SongAnalysis, overrides: dict[str, Any]) -> SongAnalysis:
    if not overrides:
        return analysis
    updated = analysis.model_copy(deep=True)
    bpm = coerce_float(overrides.get("production_bpm"))
    if bpm:
        updated.production_bpm = round(bpm, 2)
        updated.bpm = round(bpm, 2)
        updated.tempo_feel = "manual_override"
        append_warning(updated, f"Production BPM manually overridden to {bpm:g}.")
    key = str(overrides.get("key") or "").strip()
    if key:
        updated.key = key[:40]
        updated.primary_key = key[:40]
        updated.alternative_key = relative_key(key[:40])
        updated.key_candidates = merge_unique([key[:40], *(updated.key_candidates or [])])[:5]
        updated.key_confidence = 1.0
        append_warning(updated, f"Key manually overridden to {key[:40]}.")
    energy = str(overrides.get("energy") or "").strip().lower()
    if energy:
        updated.energy = energy[:40]
        append_warning(updated, f"Energy manually overridden to {energy[:40]}.")
    style = normalize_production_style(overrides.get("production_style"))
    if style:
        updated.production_style = style
    arrangement = str(overrides.get("arrangement_style") or "").strip()
    if arrangement:
        updated.arrangement_style = arrangement[:80]
    instruments = clean_instrument_list(overrides.get("main_instruments"))
    if instruments:
        updated.main_instruments = instruments
        updated.detected_instruments = instruments
    mood_tags = clean_mood_tags(overrides.get("mood_tags"))
    if mood_tags:
        updated.mood_tags = merge_unique([*mood_tags, *updated.mood_tags])
    duration = coerce_float(overrides.get("output_duration_seconds"))
    if duration:
        updated.duration_seconds = round(float(max(10, min(settings.max_demo_duration_seconds, duration))), 2)
    return updated


def db_to_linear(db_value: float) -> float:
    return round(10 ** (db_value / 20), 4)


def coerce_number(value: Any) -> float | None:
    try:
        if value is None:
            return None
        parsed = float(value)
        return parsed if math.isfinite(parsed) else None
    except (TypeError, ValueError):
        return None


def normalize_ducking_strength(value: Any, arrangement_mode: ArrangementMode) -> str:
    if arrangement_mode == ArrangementMode.music_to_music:
        return "off"
    text = str(value or settings.default_ducking_strength or "medium").strip().lower()
    return text if text in {"off", "light", "medium", "strong"} else "medium"


def build_mix_settings(overrides: dict[str, Any], arrangement_mode: ArrangementMode) -> dict[str, Any]:
    vocal_db = coerce_number(overrides.get("vocal_gain_db"))
    backing_db = coerce_number(overrides.get("backing_gain_db"))
    vocal_gain_db = settings.default_vocal_gain_db if vocal_db is None else round(vocal_db, 2)
    backing_gain_db = settings.default_backing_gain_db if backing_db is None else round(backing_db, 2)
    ducking = normalize_ducking_strength(overrides.get("ducking_strength"), arrangement_mode)
    return {
        "vocal_gain_db": vocal_gain_db,
        "backing_gain_db": backing_gain_db,
        "vocal_gain_linear": db_to_linear(vocal_gain_db),
        "backing_gain_linear": db_to_linear(backing_gain_db),
        "ducking_strength": ducking,
    }


def ducking_parameters(strength: str) -> dict[str, float]:
    profiles = {
        "light": {"threshold": 0.052, "ratio": 2.2, "attack": 14, "release": 220},
        "medium": {"threshold": 0.036, "ratio": 3.8, "attack": 12, "release": 260},
        "strong": {"threshold": 0.024, "ratio": 6.0, "attack": 8, "release": 320},
    }
    return profiles.get(strength, profiles["medium"])


def audio_duration_seconds(path: Path, ffmpeg_path: str) -> float:
    ffprobe = ffprobe_path(ffmpeg_path)
    if ffprobe:
        try:
            result = subprocess.run(
                [
                    ffprobe,
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    str(path),
                ],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            duration = float(result.stdout.strip())
            if duration > 0:
                return min(float(settings.max_demo_duration_seconds), max(10.0, duration))
        except Exception:
            pass
    return float(settings.max_demo_duration_seconds)


def analyze_vocal_timing(path: Path, ffmpeg_path: str) -> dict[str, float]:
    duration = audio_duration_seconds(path, ffmpeg_path)
    try:
        with wave.open(str(path), "rb") as wav:
            frame_rate = wav.getframerate()
            channels = max(1, wav.getnchannels())
            sample_width = wav.getsampwidth()
            if sample_width != 2:
                return {"duration": duration}

            window_seconds = 0.12
            window_frames = max(1, int(frame_rate * window_seconds))
            energies: list[float] = []
            while True:
                data = wav.readframes(window_frames)
                if not data:
                    break
                samples = struct.unpack("<" + "h" * (len(data) // 2), data)
                if channels > 1:
                    samples = samples[::channels]
                if not samples:
                    continue
                rms = math.sqrt(sum(sample * sample for sample in samples) / len(samples)) / 32768
                energies.append(rms)
    except Exception:
        return {"duration": duration}

    if len(energies) < 6:
        return {"duration": duration}

    average = sum(energies) / len(energies)
    second_map: dict[str, float] = {}
    windows_per_second = max(1, round(1 / window_seconds))
    for offset in range(0, len(energies), windows_per_second):
        second = offset // windows_per_second
        chunk = energies[offset:offset + windows_per_second]
        if chunk:
            second_map[str(second)] = round(sum(chunk) / len(chunk), 4)
    threshold = max(average * 1.25, 0.015)
    peaks: list[int] = []
    for index in range(1, len(energies) - 1):
        if energies[index] >= threshold and energies[index] >= energies[index - 1] and energies[index] >= energies[index + 1]:
            if not peaks or index - peaks[-1] >= 2:
                peaks.append(index)

    if len(peaks) < 3:
        return {"duration": duration, "energy": average, "activity_map": second_map}

    intervals = [(peaks[i] - peaks[i - 1]) * 0.12 for i in range(1, len(peaks))]
    intervals = [interval for interval in intervals if 0.25 <= interval <= 1.4]
    if not intervals:
        return {"duration": duration, "energy": average, "activity_map": second_map}

    intervals.sort()
    median_interval = intervals[len(intervals) // 2]
    tempo = 60 / median_interval
    while tempo < 68:
        tempo *= 2
    while tempo > 160:
        tempo /= 2
    return {"duration": duration, "energy": average, "tempo_bpm": round(tempo, 2), "activity_map": second_map}


def analyze_demo_idea(path: Path, genre: Genre, timing: dict[str, Any] | None, ffmpeg_path: str) -> SongAnalysis:
    duration = float((timing or {}).get("duration") or audio_duration_seconds(path, ffmpeg_path))
    vocal_energy = float((timing or {}).get("energy") or 0.0)
    detected_bpm = coerce_float((timing or {}).get("tempo_bpm"))
    bpm_confidence = 0.62 if detected_bpm else 0.0
    primary_key = None
    key_candidates: list[str] = []
    key_confidence = 0.0
    warnings: list[str] = []
    pitch_summary = "Pitch contour could not be extracted because the vocal was too weak or noisy."
    pitch_contour_status = "unavailable"

    try:
        import librosa
        import numpy as np

        samples, sample_rate = librosa.load(str(path), sr=22050, mono=True, duration=settings.max_demo_duration_seconds)
        if len(samples):
            rms = librosa.feature.rms(y=samples)
            vocal_energy = max(vocal_energy, float(np.mean(rms)))
            if not detected_bpm:
                tempo_result = librosa.beat.tempo(y=samples, sr=sample_rate)
                if len(tempo_result):
                    detected_bpm = float(tempo_result[0])
                    bpm_confidence = 0.72
            chroma = librosa.feature.chroma_stft(y=samples, sr=sample_rate)
            key_scores = estimate_key_candidates_from_chroma(np.mean(chroma, axis=1).tolist())
            if key_scores:
                primary_key = key_scores[0][0]
                key_candidates = [candidate for candidate, _score in key_scores[:5]]
                key_confidence = key_confidence_from_scores([score for _candidate, score in key_scores])
            pitches, _magnitudes = librosa.piptrack(y=samples, sr=sample_rate)
            active_pitches = pitches[pitches > 0]
            if active_pitches.size:
                low = hz_to_note_name(float(np.percentile(active_pitches, 20)))
                high = hz_to_note_name(float(np.percentile(active_pitches, 85)))
                pitch_summary = f"Fallback pitch contour estimated from vocal movement between {low} and {high}."
                pitch_contour_status = "fallback_used"
    except Exception:
        pass

    if not detected_bpm:
        detected_bpm = float(arranged_genre_profile(genre)["bpm"])
        bpm_confidence = 0.35
        warnings.append("Tempo was estimated from the selected genre because beat analysis was inconclusive.")
    if not primary_key:
        primary_key = default_key_for_genre(genre)
        key_candidates = [primary_key]
        key_confidence = 0.35
        warnings.append("Key was estimated from the selected genre because chroma analysis was inconclusive.")
    energy = vocal_energy_label(vocal_energy)
    mood = mood_label(primary_key, energy, genre)
    mood_tags = mood_tags_for_analysis(primary_key, energy, genre, mood)
    mood_tags = merge_unique([*mood_tags, *clean_mood_tags((timing or {}).get("mood_tags"))])
    style_settings = resolve_production_settings(genre, timing, mood_tags)
    mood_tags = merge_unique([*mood_tags, *style_settings["mood_tags"]])
    warnings.extend(style_settings["warnings"])
    production_bpm, tempo_feel, tempo_warning = corrected_production_bpm(detected_bpm, genre, energy, mood_tags)
    if tempo_warning:
        warnings.append(tempo_warning)
    if key_confidence < 0.68:
        warnings.append("Key confidence is moderate. Manual override recommended before generation.")
    alternative_key = relative_key(primary_key)
    arrangement_style = style_settings["arrangement_style"]
    main_instruments = style_settings["main_instruments"]
    return SongAnalysis(
        bpm=production_bpm,
        key=primary_key,
        detected_bpm=round(float(detected_bpm), 2) if detected_bpm else None,
        production_bpm=production_bpm,
        tempo_feel=tempo_feel,
        bpm_confidence=round(bpm_confidence, 2),
        primary_key=primary_key,
        alternative_key=alternative_key,
        key_candidates=key_candidates,
        key_confidence=round(key_confidence, 2),
        duration_seconds=round(duration, 2),
        energy=energy,
        mood=mood,
        mood_tags=mood_tags,
        genre=genre.value,
        production_style=style_settings["production_style"],
        arrangement_style=arrangement_style,
        compatible_genre=style_settings["compatible_genre"].value,
        main_instruments=main_instruments,
        detected_instruments=main_instruments,
        recommended_production=recommended_production_for_genre(genre, style_settings["production_style"], arrangement_style, production_bpm),
        pitch_contour_status=pitch_contour_status,
        melody_midi_status="unavailable",
        warnings=warnings,
        vocal_energy=round(vocal_energy, 4),
        suggested_genre=genre,
        pitch_summary=pitch_summary,
    )


def fallback_song_analysis(genre: Genre, timing: dict[str, Any] | None = None) -> SongAnalysis:
    detected_bpm = float((timing or {}).get("tempo_bpm") or arranged_genre_profile(genre)["bpm"])
    energy = "medium"
    primary_key = default_key_for_genre(genre)
    mood = mood_label(primary_key, energy, genre)
    mood_tags = mood_tags_for_analysis(primary_key, energy, genre, mood)
    mood_tags = merge_unique([*mood_tags, *clean_mood_tags((timing or {}).get("mood_tags"))])
    style_settings = resolve_production_settings(genre, timing, mood_tags)
    mood_tags = merge_unique([*mood_tags, *style_settings["mood_tags"]])
    production_bpm, tempo_feel, tempo_warning = corrected_production_bpm(detected_bpm, genre, energy, mood_tags)
    warnings = ["Detailed audio analysis was unavailable; using conservative genre defaults.", *style_settings["warnings"]]
    if tempo_warning:
        warnings.append(tempo_warning)
    return SongAnalysis(
        bpm=production_bpm,
        key=primary_key,
        detected_bpm=round(detected_bpm, 2),
        production_bpm=production_bpm,
        tempo_feel=tempo_feel,
        bpm_confidence=0.35,
        primary_key=primary_key,
        alternative_key=relative_key(primary_key),
        key_candidates=[primary_key],
        key_confidence=0.35,
        duration_seconds=float((timing or {}).get("duration") or 30.0),
        energy=energy,
        mood=mood,
        mood_tags=mood_tags,
        genre=genre.value,
        production_style=style_settings["production_style"],
        arrangement_style=style_settings["arrangement_style"],
        compatible_genre=style_settings["compatible_genre"].value,
        main_instruments=style_settings["main_instruments"],
        detected_instruments=style_settings["main_instruments"],
        recommended_production=recommended_production_for_genre(
            genre,
            style_settings["production_style"],
            style_settings["arrangement_style"],
            production_bpm,
        ),
        pitch_contour_status="unavailable",
        melody_midi_status="unavailable",
        warnings=warnings,
        vocal_energy=0.05,
        suggested_genre=genre,
        pitch_summary="Pitch contour could not be extracted because only fallback genre analysis was available.",
    )


def estimate_key_from_chroma(chroma: list[float]) -> str | None:
    candidates = estimate_key_candidates_from_chroma(chroma)
    return candidates[0][0] if candidates else None


def estimate_key_candidates_from_chroma(chroma: list[float]) -> list[tuple[str, float]]:
    if len(chroma) != 12:
        return []
    major_profile = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
    minor_profile = [6.33, 2.68, 3.52, 5.38, 2.6, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]
    names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    candidates: list[tuple[str, float]] = []
    for offset, name in enumerate(names):
        major_score = sum(chroma[(index + offset) % 12] * weight for index, weight in enumerate(major_profile))
        minor_score = sum(chroma[(index + offset) % 12] * weight for index, weight in enumerate(minor_profile))
        candidates.append((f"{name} major", float(major_score)))
        candidates.append((f"{name} minor", float(minor_score)))
    return sorted(candidates, key=lambda item: item[1], reverse=True)


def key_confidence_from_scores(scores: list[float]) -> float:
    if not scores or scores[0] <= 0:
        return 0.25
    if len(scores) == 1:
        return 0.65
    margin = max(0.0, (scores[0] - scores[1]) / max(scores[0], 1e-6))
    return min(0.95, max(0.35, 0.45 + margin * 2.2))


def hz_to_note_name(frequency: float) -> str:
    if frequency <= 0:
        return "unknown"
    names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    midi = round(69 + 12 * math.log2(frequency / 440.0))
    return f"{names[midi % 12]}{(midi // 12) - 1}"


def default_key_for_genre(genre: Genre) -> str:
    defaults = {
        Genre.lofi: "A minor",
        Genre.piano: "C major",
        Genre.pop: "C major",
        Genre.rock: "E minor",
        Genre.rnb: "A minor",
        Genre.hiphop: "A minor",
        Genre.acoustic: "G major",
        Genre.cinematic: "D minor",
    }
    return defaults[genre]


def vocal_energy_label(value: float) -> str:
    if value >= 0.16:
        return "high"
    if value >= 0.095:
        return "medium-high"
    if value >= 0.035:
        return "medium"
    if value >= 0.014:
        return "medium-low"
    return "low"


def mood_label(key: str | None, energy: str, genre: Genre) -> str:
    key_text = (key or "").lower()
    energy_text = energy.lower()
    if genre in {Genre.hiphop, Genre.rnb, Genre.cinematic} or "minor" in key_text:
        return "Dark / emotional" if energy_text != "high" else "Intense / dramatic"
    if energy_text in {"high", "medium-high"}:
        return "Bright / driving"
    if energy_text in {"low", "medium-low"}:
        return "Soft / intimate"
    return "Warm / focused"


def coerce_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        parsed = float(value)
        if math.isfinite(parsed) and parsed > 0:
            return parsed
    except (TypeError, ValueError):
        return None
    return None


def corrected_production_bpm(
    detected_bpm: float | None,
    genre: Genre,
    energy: str,
    mood_tags: list[str],
) -> tuple[float | None, str, str | None]:
    if not detected_bpm:
        return None, "original", None
    production_bpm = round(float(detected_bpm), 2)
    emotional_terms = {
        "emotional",
        "ballad",
        "piano",
        "acoustic",
        "cinematic",
        "romantic",
        "bollywood ballad",
        "slow song",
        "intimate",
        "soft",
    }
    genre_is_ballad_like = genre in {Genre.piano, Genre.acoustic, Genre.cinematic, Genre.rnb}
    tags_are_ballad_like = any(tag.lower() in emotional_terms for tag in mood_tags)
    if detected_bpm > 110 and (genre_is_ballad_like or tags_are_ballad_like):
        return (
            round(production_bpm / 2, 2),
            "half-time",
            "Song feels like a slow emotional ballad, so half-time BPM is better for production.",
        )
    if detected_bpm < 55 and energy.lower() in {"medium-high", "high"}:
        return (
            round(production_bpm * 2, 2),
            "double-time",
            "Detected BPM is very low for the source energy, so double-time BPM is better for production.",
        )
    return production_bpm, "original", None


def mood_tags_for_analysis(key: str | None, energy: str, genre: Genre, mood: str) -> list[str]:
    tags: list[str] = []
    mood_text = mood.lower()
    if "minor" in (key or "").lower() or "dark" in mood_text:
        tags.append("emotional")
    if "intimate" in mood_text or genre in {Genre.piano, Genre.acoustic}:
        tags.append("intimate")
    if genre == Genre.cinematic:
        tags.extend(["cinematic", "dramatic"])
    if genre == Genre.rnb:
        tags.extend(["romantic", "nocturnal"])
    if genre == Genre.lofi:
        tags.append("relaxed")
    if energy.lower() in {"medium-high", "high"}:
        tags.append("driving")
    if not tags:
        tags.append("focused")
    return list(dict.fromkeys(tags))


def merge_unique(values: list[str]) -> list[str]:
    return [value for value in dict.fromkeys(value.strip() for value in values if value and value.strip())]


def normalize_production_style(value: Any) -> str | None:
    if value is None:
        return None
    text = getattr(value, "value", value)
    normalized = str(text).strip()
    if not normalized:
        return None
    for style_label in STYLE_PRESETS:
        if style_label.lower() == normalized.lower():
            return style_label
    return None


def clean_instrument_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    cleaned: list[str] = []
    for value in values:
        item = str(value).strip()
        if item:
            cleaned.append(item[:48])
    return merge_unique(cleaned)[:12]


def clean_mood_tags(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    cleaned: list[str] = []
    for value in values:
        item = str(value).strip()
        if item:
            cleaned.append(item[:40])
    return merge_unique(cleaned)[:12]


def clean_prompt_text(value: Any, limit: int = 600) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit]


def clean_language(value: Any) -> str:
    return clean_prompt_text(value or "Hindi", 40) or "Hindi"


def default_production_style_for_genre(genre: Genre, mood_tags: list[str] | None = None) -> str:
    tags = {tag.lower() for tag in (mood_tags or [])}
    if genre == Genre.piano:
        return ProductionStyle.piano_ballad.value
    if genre == Genre.acoustic:
        return ProductionStyle.acoustic_unplugged.value
    if genre == Genre.cinematic:
        return ProductionStyle.cinematic_strings.value
    if genre == Genre.rnb:
        return ProductionStyle.trap_soul.value
    if genre == Genre.hiphop:
        return ProductionStyle.trap_soul.value
    if genre == Genre.lofi:
        return ProductionStyle.lofi_cover.value
    if genre == Genre.rock:
        return ProductionStyle.rock_cover.value
    if "romantic" in tags or "emotional" in tags:
        return ProductionStyle.romantic_pop.value
    return ProductionStyle.indie_pop.value


def resolve_production_settings(
    genre: Genre,
    timing: dict[str, Any] | None = None,
    mood_tags: list[str] | None = None,
) -> dict[str, Any]:
    style_label = normalize_production_style((timing or {}).get("production_style")) or default_production_style_for_genre(genre, mood_tags)
    preset = STYLE_PRESETS[style_label]
    compatible_genres = preset["compatible_genres"]
    compatible_genre = genre if genre in compatible_genres else compatible_genres[0]
    user_arrangement = str((timing or {}).get("arrangement_style") or "").strip()
    user_instruments = clean_instrument_list((timing or {}).get("main_instruments"))
    warnings: list[str] = []
    if genre not in compatible_genres and (timing or {}).get("production_style"):
        compatible_labels = " or ".join(item.value for item in compatible_genres)
        warnings.append(
            f"{style_label} is usually produced as {compatible_labels}; keeping {genre.value} as the compatible API genre."
        )
    return {
        "production_style": style_label,
        "compatible_genre": compatible_genre,
        "arrangement_style": user_arrangement[:80] or preset["arrangement_style"],
        "main_instruments": user_instruments or list(preset["instruments"]),
        "mood_tags": list(preset["mood_tags"]),
        "warnings": warnings,
    }


def relative_key(key: str | None) -> str | None:
    if not key:
        return None
    notes = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    root, mode = parse_key_name(key)
    if root not in notes:
        return None
    index = notes.index(root)
    if mode == "major":
        return f"{notes[(index + 9) % 12]} minor"
    return f"{notes[(index + 3) % 12]} major"


def arrangement_style_for_genre(genre: Genre, mood_tags: list[str]) -> str:
    style_label = default_production_style_for_genre(genre, mood_tags)
    return str(STYLE_PRESETS[style_label]["arrangement_style"])


def instruments_for_genre(genre: Genre) -> list[str]:
    instruments = {
        Genre.lofi: ["dusty drums", "electric piano", "soft bass", "vinyl texture"],
        Genre.piano: ["felt piano", "warm bass", "room ambience"],
        Genre.pop: ["clean drums", "bass", "synth stabs", "pads"],
        Genre.rock: ["drums", "electric bass", "rhythm guitar"],
        Genre.rnb: ["half-time drums", "sub bass", "airy keys", "pads"],
        Genre.hiphop: ["808 bass", "hi-hats", "clap", "dark keys"],
        Genre.acoustic: ["acoustic guitar", "soft percussion", "warm bass"],
        Genre.cinematic: ["piano", "strings", "pads", "subtle percussion"],
    }
    return instruments[genre]


def recommended_production_for_genre(
    genre: Genre,
    production_style: str,
    arrangement_style: str,
    production_bpm: float | None,
) -> list[str]:
    bpm_text = f"Produce around {production_bpm:g} BPM." if production_bpm else "Confirm tempo against the lead vocal before generation."
    base = {
        Genre.lofi: "Keep drums dusty, warm, and relaxed.",
        Genre.piano: "Lead with sparse piano and leave long vocal breaths.",
        Genre.pop: "Use a clear chorus lift without crowding the lead.",
        Genre.rock: "Keep guitars rhythmic and avoid masking the vocal midrange.",
        Genre.rnb: "Use half-time pocket, deep sub, and open upper mids.",
        Genre.hiphop: "Keep the melodic motif sparse and let the cadence drive.",
        Genre.acoustic: "Use organic strums or fingerpicking with soft percussion.",
        Genre.cinematic: "Use strings and pads as emotional support, not lead melodies.",
    }
    return [
        bpm_text,
        f"Genre / Style: {production_style}.",
        f"Arrangement style: {arrangement_style}.",
        base[genre],
        "Keep the vocal slightly forward in the mix.",
    ]


def build_song_blueprint(analysis: SongAnalysis, genre: Genre, timing: dict[str, Any] | None = None) -> SongBlueprint:
    duration = analysis.duration_seconds
    if duration <= 24:
        sections = [
            SongSection(name="Intro", bars=2, note="Establish the key and leave space for the first phrase."),
            SongSection(name="Verse", bars=8, note="Follow the rough vocal cadence closely."),
            SongSection(name="Hook", bars=4, note="Lift the chords and drums without overpowering the vocal."),
            SongSection(name="Outro", bars=2, note="Resolve quickly so the idea stays demo-length."),
        ]
    else:
        sections = [
            SongSection(name="Intro", bars=4, note="Start sparse and let the vocal idea lead."),
            SongSection(name="Verse 1", bars=16, note="Build around the strongest melodic or rap cadence."),
            SongSection(name="Chorus", bars=8, note="Open the chords and repeat the most memorable phrase."),
            SongSection(name="Verse 2", bars=16, note="Vary drums or bass while keeping the same harmony."),
            SongSection(name="Chorus", bars=8, note="Return to the hook with more energy."),
            SongSection(name="Outro", bars=4, note="Strip back to chords or texture for producer handoff."),
        ]

    return SongBlueprint(
        structure=sections,
        chords=chord_progression_for_key(analysis.primary_key or analysis.key or default_key_for_genre(genre)),
        production_notes=production_notes_for_genre(genre, analysis, timing),
        lyric_suggestions=lyric_suggestions_for_genre(genre, analysis),
        production_style=analysis.production_style,
        arrangement_style=analysis.arrangement_style,
        main_instruments=analysis.main_instruments,
    )


def chord_progression_for_key(key: str) -> list[str]:
    root_name, mode = parse_key_name(key)
    notes = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    root = notes.index(root_name) if root_name in notes else 0

    def note(offset: int) -> str:
        return notes[(root + offset) % 12]

    if mode == "minor":
        return [f"{note(0)}m", note(8), note(3), note(10)]
    return [note(0), note(7), f"{note(9)}m", note(5)]


def parse_key_name(key: str) -> tuple[str, str]:
    parts = key.strip().replace("♯", "#").replace("♭", "b").split()
    root = parts[0] if parts else "C"
    flats = {"Db": "C#", "Eb": "D#", "Gb": "F#", "Ab": "G#", "Bb": "A#"}
    root = flats.get(root, root)
    mode = "minor" if any(part.lower().startswith("min") for part in parts[1:]) else "major"
    return root, mode


def production_notes_for_genre(genre: Genre, analysis: SongAnalysis, timing: dict[str, Any] | None) -> list[str]:
    arrangement_mode = arrangement_mode_from_timing(timing)
    base = {
        Genre.lofi: "Use dusty drums, mellow keys, vinyl texture, and a relaxed bass pocket.",
        Genre.piano: "Lead with felt piano chords, light bass, and room ambience.",
        Genre.pop: "Use clean drums, short synth stabs, and a clear chorus lift.",
        Genre.rock: "Use tight kick/snare, bass movement, and restrained rhythm guitar texture.",
        Genre.rnb: "Use half-time drums, airy keys, deep sub, and open midrange.",
        Genre.hiphop: "Use 808-style bass movement, crisp hats, and a sparse melodic motif.",
        Genre.acoustic: "Use fingerpicked guitar feel, soft percussion, and warm bass.",
        Genre.cinematic: "Use low strings, piano pulses, and subtle phrase-ending drums.",
    }
    tempo_value = analysis.production_bpm or analysis.bpm
    tempo = f"Target around {tempo_value:.0f} BPM." if tempo_value else "Let the producer confirm tempo from the vocal."
    activity = "Build around the active vocal phrases; leave simpler space in gaps."
    if timing and isinstance(timing.get("activity_map"), dict):
        activity = "Use the vocal activity map to place fills only around phrase endings."
    mode_note = {
        ArrangementMode.vocal_to_song: "Mode: build a complete backing tune around the lead vocal, with audible drums, bass, guitar or keys.",
        ArrangementMode.music_to_music: "Mode: create a new instrumental arrangement from the uploaded music reference; do not layer the old instrumental back into the final.",
        ArrangementMode.full_song: "Mode: re-arrange the full song while preserving the lead source as the focus when separation is available.",
    }[arrangement_mode]
    return [
        mode_note,
        tempo,
        f"Genre / Style: {analysis.production_style or genre.value}.",
        f"Arrangement: {analysis.arrangement_style or arrangement_style_for_genre(genre, analysis.mood_tags)}.",
        f"Main instruments: {', '.join(analysis.main_instruments or instruments_for_genre(genre))}.",
        f"Estimated key is {analysis.primary_key or analysis.key}; treat it as a starting point, not a final musicology claim.",
        base[genre],
        activity,
    ]


def arrangement_mode_from_timing(timing: dict[str, Any] | None) -> ArrangementMode:
    value = (timing or {}).get("arrangement_mode")
    try:
        return ArrangementMode(str(value))
    except ValueError:
        return ArrangementMode.vocal_to_song


def lyric_suggestions_for_genre(genre: Genre, analysis: SongAnalysis) -> list[str]:
    if genre == Genre.hiphop:
        return [
            "Tighten the strongest bar into the hook phrase.",
            "Vary the second verse cadence instead of adding more words.",
            "Leave two-beat gaps where ad-libs or producer drops can land.",
        ]
    if genre in {Genre.rnb, Genre.pop}:
        return [
            "Repeat the most singable line at the top of the chorus.",
            "Use fewer words in high notes so the melody can breathe.",
            "Mark one emotional phrase as the demo title candidate.",
        ]
    return [
        "Circle the most memorable phrase and make it the hook anchor.",
        "Keep verse lines conversational until the chorus opens up.",
        "Note any unfinished lyric spots before sending the pack to a producer.",
    ]


def analysis_timing_metadata(analysis: SongAnalysis) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "detected_bpm": analysis.detected_bpm,
        "production_bpm": analysis.production_bpm,
        "tempo_feel": analysis.tempo_feel,
        "primary_key": analysis.primary_key or analysis.key,
        "alternative_key": analysis.alternative_key,
        "key_confidence": analysis.key_confidence,
        "bpm_confidence": analysis.bpm_confidence,
        "mood_tags": analysis.mood_tags,
        "genre": analysis.genre,
        "production_style": analysis.production_style,
        "arrangement_style": analysis.arrangement_style,
        "compatible_genre": analysis.compatible_genre,
        "main_instruments": analysis.main_instruments,
        "energy": analysis.energy,
    }
    if analysis.production_bpm:
        metadata["tempo_bpm"] = analysis.production_bpm
    return metadata


def build_final_generation_settings(
    genre: Genre,
    analysis: SongAnalysis,
    arrangement_mode: ArrangementMode,
    timing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    lyrics = clean_prompt_text((timing or {}).get("lyrics"), 2000)
    return {
        "genre": genre.value,
        "compatible_genre": analysis.compatible_genre or genre.value,
        "language": clean_language((timing or {}).get("language")),
        "lyrics_provided": bool(lyrics),
        "lyrics_excerpt": clean_prompt_text(lyrics, 180) if lyrics else None,
        "production_style": analysis.production_style,
        "arrangement_style": analysis.arrangement_style,
        "main_instruments": analysis.main_instruments,
        "arrangement_mode": arrangement_mode.value,
        "detected_bpm": analysis.detected_bpm,
        "production_bpm": analysis.production_bpm or analysis.bpm,
        "tempo_feel": analysis.tempo_feel,
        "primary_key": analysis.primary_key or analysis.key,
        "alternative_key": analysis.alternative_key,
        "mood_tags": analysis.mood_tags,
        "energy": analysis.energy,
        "output_duration_seconds": analysis.duration_seconds,
        "generator_backend": settings.music_generator_backend,
        "melody_analyzer_backend": settings.melody_analyzer_backend,
        "source_type": (timing or {}).get("source_type"),
        "user_overrides": (timing or {}).get("user_overrides", {}),
    }


def build_producer_prompt(
    genre: Genre,
    analysis: SongAnalysis,
    blueprint: SongBlueprint,
    arrangement_mode: ArrangementMode,
    timing: dict[str, Any] | None = None,
) -> str:
    production_bpm = analysis.production_bpm or analysis.bpm
    bpm_text = f"at {production_bpm:g} BPM" if production_bpm else "at a stable tempo matched to the source"
    key_text = analysis.primary_key or analysis.key or "the estimated key"
    if analysis.alternative_key:
        key_text = f"{key_text} / {analysis.alternative_key}"
    mood_text = ", ".join(analysis.mood_tags or [analysis.mood])
    production_style = analysis.production_style or genre.value
    arrangement_style = analysis.arrangement_style or arrangement_style_for_genre(genre, analysis.mood_tags)
    instruments = ", ".join(analysis.main_instruments or analysis.detected_instruments or instruments_for_genre(genre))
    sections = ", ".join(section.name.lower() for section in blueprint.structure)
    language = clean_language((timing or {}).get("language"))
    lyrics = clean_prompt_text((timing or {}).get("lyrics"), 600)
    source_text = {
        ArrangementMode.vocal_to_song: "for an isolated original vocal stem",
        ArrangementMode.music_to_music: "from an uploaded music reference, without copying the old instrumental",
        ArrangementMode.full_song: "for an uploaded full song, preserving room for the original lead source",
    }[arrangement_mode]
    activity_text = vocal_activity_prompt(timing).strip()
    if activity_text:
        activity_text = f" {activity_text}"
    lyric_text = (
        f" Language and lyric context: {language}; support this lyric emotion without generating new sung words: {lyrics}. "
        if lyrics
        else f" Language context: {language}; follow the phrasing and emotional contour of the uploaded lead. "
    )
    return (
        f"Create an original {production_style} backing track {source_text} {bpm_text} in {key_text} emotional feel. "
        f"{lyric_text}"
        f"Use a {arrangement_style} arrangement with {instruments}. "
        f"Keep it {mood_text}, spacious, and vocal-friendly; energy should feel {analysis.energy}. "
        f"Follow a clear structure: {sections}. "
        "Keep the arrangement spacious, stable, and vocal-friendly. Leave space in the midrange for the singer. "
        "Let verses stay minimal and let hooks build with fuller harmony, bass, or drums only where the vocal leaves room. "
        "Do not overpower the vocal, do not create random tempo changes, and do not add busy lead melodies. "
        "Make it suitable for mixing with the isolated vocal."
        f"{activity_text}"
    )


def build_producer_negative_prompt(genre: Genre, analysis: SongAnalysis) -> str:
    negatives = [
        "Do not overpower the vocal.",
        "Do not create random tempo changes.",
        "Do not add harsh EDM drops unless explicitly selected.",
        "Do not make the arrangement too busy for ballads or emotional songs.",
        "Do not use distorted lead instruments unless the selected genre needs them.",
        "No generated lead vocals, lyric vocals, ad-libs, spoken words, copyrighted melodies, or artist imitation.",
    ]
    if genre in {Genre.piano, Genre.acoustic, Genre.cinematic} or "emotional" in analysis.mood_tags:
        negatives.append("Avoid aggressive drums, bright synth leads, and dense fills.")
    return " ".join(negatives)


def append_warning(analysis: SongAnalysis, message: str) -> None:
    if message and message not in analysis.warnings:
        analysis.warnings.append(message)


def create_fallback_pitch_melody(
    input_audio_path: Path,
    output_midi: Path,
    output_notes: Path,
    analysis: SongAnalysis,
    reason: str,
) -> tuple[Path, Path]:
    try:
        import librosa
        import numpy as np
    except Exception as exc:
        raise MelodyAnalysisError("librosa fallback is not available") from exc

    try:
        samples, sample_rate = librosa.load(str(input_audio_path), sr=22050, mono=True, duration=settings.max_demo_duration_seconds)
        if len(samples) < sample_rate:
            raise MelodyAnalysisError("fallback pitch tracker needs at least one second of audio")
        f0, voiced_flag, voiced_prob = librosa.pyin(
            samples,
            fmin=librosa.note_to_hz("C2"),
            fmax=librosa.note_to_hz("C6"),
            sr=sample_rate,
        )
    except MelodyAnalysisError:
        raise
    except Exception as exc:
        raise MelodyAnalysisError(f"fallback pitch tracker failed after Basic Pitch error: {reason[:90]}") from exc

    frame_times = librosa.frames_to_time(range(len(f0)), sr=sample_rate)
    raw_notes: list[tuple[float, int, float]] = []
    for time_seconds, frequency, is_voiced, probability in zip(frame_times, f0, voiced_flag, voiced_prob):
        if not is_voiced or not np.isfinite(frequency) or float(probability or 0) < 0.55:
            continue
        midi_note = int(round(69 + 12 * math.log2(float(frequency) / 440.0)))
        if 36 <= midi_note <= 96:
            raw_notes.append((float(time_seconds), midi_note, float(probability or 0)))
    if len(raw_notes) < 4:
        raise MelodyAnalysisError("fallback pitch contour could not find enough confident notes")

    note_events = compact_pitch_frames(raw_notes)
    if not note_events:
        raise MelodyAnalysisError("fallback pitch contour did not produce usable melody notes")

    write_monophonic_midi(output_midi, note_events, analysis.production_bpm or analysis.bpm or 92)
    lines = ["start,end,pitch,confidence"]
    for start, end, midi_note, confidence in note_events:
        lines.append(f"{start:.3f},{end:.3f},{midi_note},{confidence:.3f}")
    output_notes.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output_midi, output_notes


def compact_pitch_frames(raw_notes: list[tuple[float, int, float]]) -> list[tuple[float, float, int, float]]:
    events: list[tuple[float, float, int, float]] = []
    start, previous_time, note, confidence_sum, count = raw_notes[0][0], raw_notes[0][0], raw_notes[0][1], raw_notes[0][2], 1
    for time_seconds, midi_note, confidence in raw_notes[1:]:
        if midi_note == note and time_seconds - previous_time <= 0.16:
            previous_time = time_seconds
            confidence_sum += confidence
            count += 1
            continue
        end = previous_time + 0.12
        if end - start >= 0.08:
            events.append((start, end, note, confidence_sum / max(1, count)))
        start, previous_time, note, confidence_sum, count = time_seconds, time_seconds, midi_note, confidence, 1
    end = previous_time + 0.12
    if end - start >= 0.08:
        events.append((start, end, note, confidence_sum / max(1, count)))
    return events[:160]


def write_monophonic_midi(path: Path, notes: list[tuple[float, float, int, float]], bpm: float) -> None:
    ticks_per_beat = 480
    seconds_per_beat = 60 / max(30, min(220, float(bpm)))
    microseconds_per_quarter = max(1, int(60_000_000 / max(30, min(220, float(bpm)))))
    events: list[tuple[int, int, int, int]] = []
    for start, end, midi_note, confidence in notes:
        velocity = int(max(42, min(96, 48 + confidence * 42)))
        start_tick = int(start / seconds_per_beat * ticks_per_beat)
        end_tick = max(start_tick + 24, int(end / seconds_per_beat * ticks_per_beat))
        events.append((start_tick, 0x90, midi_note, velocity))
        events.append((end_tick, 0x80, midi_note, 0))
    events.sort(key=lambda item: (item[0], item[1]))

    track = bytearray()
    track.extend(b"\x00\xff\x51\x03" + microseconds_per_quarter.to_bytes(3, "big"))
    previous_tick = 0
    for tick, status, midi_note, velocity in events:
        delta = max(0, tick - previous_tick)
        track.extend(varlen(delta) + bytes([status, midi_note, velocity]))
        previous_tick = tick
    track.extend(b"\x00\xff\x2f\x00")
    header = b"MThd" + (6).to_bytes(4, "big") + (0).to_bytes(2, "big") + (1).to_bytes(2, "big") + ticks_per_beat.to_bytes(2, "big")
    chunk = b"MTrk" + len(track).to_bytes(4, "big") + bytes(track)
    path.write_bytes(header + chunk)


def count_midi_notes(path: Path) -> int:
    try:
        data = path.read_bytes()
    except OSError:
        return 0
    count = 0
    for index in range(0, max(0, len(data) - 2)):
        status = data[index]
        if 0x90 <= status <= 0x9F and data[index + 2] > 0:
            count += 1
    return count


def count_csv_note_rows(path: Path | None) -> int:
    if path is None or not path.exists():
        return 0
    try:
        return max(0, len(path.read_text(encoding="utf-8").splitlines()) - 1)
    except OSError:
        return 0


def audio_rms(path: Path | None) -> float | None:
    if path is None or not path.exists():
        return None
    try:
        with wave.open(str(path), "rb") as wav:
            channels = max(1, wav.getnchannels())
            sample_width = wav.getsampwidth()
            if sample_width != 2:
                return None
            frames = wav.readframes(wav.getnframes())
            if not frames:
                return None
            samples = struct.unpack("<" + "h" * (len(frames) // 2), frames)
            if channels > 1:
                samples = samples[::channels]
            return round(math.sqrt(sum(sample * sample for sample in samples) / max(1, len(samples))) / 32768, 4)
    except Exception:
        return None


def audio_peak(path: Path | None) -> float | None:
    if path is None or not path.exists():
        return None
    try:
        with wave.open(str(path), "rb") as wav:
            sample_width = wav.getsampwidth()
            if sample_width != 2:
                return None
            frames = wav.readframes(wav.getnframes())
            if not frames:
                return None
            samples = struct.unpack("<" + "h" * (len(frames) // 2), frames)
            return round(max(abs(sample) for sample in samples) / 32768, 4)
    except Exception:
        return None


def simple_wav_duration(path: Path | None) -> float | None:
    if path is None or not path.exists():
        return None
    try:
        with wave.open(str(path), "rb") as wav:
            return round(wav.getnframes() / max(1, wav.getframerate()), 2)
    except Exception:
        return None


def file_status(path: Path | None) -> str:
    return "present" if path is not None and path.exists() and path.stat().st_size > 0 else "missing"


def build_quality_report(
    raw_input: Path,
    normalized_wav: Path,
    vocal_wav: Path | None,
    backing_wav: Path,
    final_wav: Path,
    final_mp3: Path,
    melody_midi: Path | None,
    chords_midi: Path | None,
    chord_sheet: Path | None,
    producer_pack: Path,
    analysis: SongAnalysis,
    target_duration: float,
    melody_status: str,
    melody_note_count: int,
    fallback_used: bool,
    expected_pack_files: list[str],
    final_generation_settings: dict[str, Any] | None = None,
    generation_diagnostics: dict[str, Any] | None = None,
    job_logs: list[str] | None = None,
    preview_files: dict[str, Path] | None = None,
    ffmpeg_path: str | None = None,
) -> dict[str, Any]:
    backing_duration = simple_wav_duration(backing_wav)
    backing_duration = backing_duration or media_duration_seconds(backing_wav, ffmpeg_path or settings.ffmpeg_path)
    input_duration = media_duration_seconds(raw_input, ffmpeg_path or settings.ffmpeg_path)
    normalized_duration = media_duration_seconds(normalized_wav, ffmpeg_path or settings.ffmpeg_path)
    vocal_duration = media_duration_seconds(vocal_wav, ffmpeg_path or settings.ffmpeg_path) if vocal_wav else None
    final_duration = media_duration_seconds(final_wav, ffmpeg_path or settings.ffmpeg_path)
    duration_delta = abs(backing_duration - target_duration) if backing_duration is not None else None
    final_peak = audio_peak(final_wav)
    final_rms = audio_rms(final_wav)
    backing_rms = audio_rms(backing_wav)
    vocal_loudness = audio_rms(vocal_wav)
    diagnostics = generation_diagnostics or {}
    generation_report = diagnostics.get("backing_generation") if isinstance(diagnostics.get("backing_generation"), dict) else {}
    final_settings = final_generation_settings or {}
    preview_files = preview_files or {}
    missing_files = [
        name
        for name, path in {
            "input_audio": raw_input,
            "normalized_audio": normalized_wav,
            "backing_audio": backing_wav,
            "final_mix_wav": final_wav,
            "final_mix_mp3": final_mp3,
            "chords_midi": chords_midi,
            "chord_sheet": chord_sheet,
        }.items()
        if file_status(path) == "missing"
    ]
    missing_previews = [name for name, path in preview_files.items() if file_status(path) == "missing"]
    missing_files.extend(missing_previews)
    if vocal_wav is not None and file_status(vocal_wav) == "missing":
        missing_files.append("isolated_vocal")
    if melody_status.startswith("available") or melody_status == "fallback_used":
        if file_status(melody_midi) == "missing":
            missing_files.append("melody_midi")

    report_warnings = list(analysis.warnings)
    if missing_files:
        report_warnings.append("Missing expected export files: " + ", ".join(missing_files))
    if final_peak is not None and final_peak >= 0.99:
        report_warnings.append("Possible clipping detected in final WAV.")
    for warning in generation_report.get("warnings") or []:
        report_warnings.append(str(warning))

    return {
        "input_audio": file_status(raw_input),
        "input_duration_seconds": input_duration,
        "input_file_size": raw_input.stat().st_size if raw_input.exists() else 0,
        "normalized_audio": file_status(normalized_wav),
        "normalized_duration_seconds": normalized_duration,
        "genre": analysis.genre,
        "production_style": analysis.production_style,
        "arrangement_style": analysis.arrangement_style,
        "main_instruments": analysis.main_instruments,
        "vocal_isolation": "not_requested" if vocal_wav is None else ("good" if file_status(vocal_wav) == "present" else "missing"),
        "isolated_vocal_loudness": vocal_loudness,
        "isolated_vocal_duration_seconds": vocal_duration,
        "isolated_vocal_file_size": vocal_wav.stat().st_size if vocal_wav is not None and vocal_wav.exists() else 0,
        "backing_generation_status": "ready" if file_status(backing_wav) == "present" else "missing",
        "selected_generator": generation_report.get("selected_generator") or final_settings.get("selected_generator") or settings.music_generator_backend,
        "generator_used": generation_report.get("final_generator_used") or final_settings.get("final_generator_used") or settings.music_generator_backend,
        "fallback_used": bool(generation_report.get("fallback_result") == "succeeded"),
        "fallback_attempted": bool(generation_report.get("fallback_attempted")),
        "fallback_result": generation_report.get("fallback_result") or "not_attempted",
        "generator_failure_reason": generation_report.get("ace_step_error"),
        "ace_step_endpoint": generation_report.get("ace_step_endpoint"),
        "ace_step_health": generation_report.get("ace_step_health"),
        "backing_audio": file_status(backing_wav),
        "backing_duration_matches_target": "unknown" if duration_delta is None else ("good" if duration_delta <= 2.0 else "check"),
        "target_duration_seconds": round(target_duration, 2),
        "backing_duration_seconds": backing_duration,
        "backing_file_size": backing_wav.stat().st_size if backing_wav.exists() else 0,
        "backing_rms": backing_rms,
        "backing_silence_percentage": silence_percentage(backing_wav),
        "vocal_backing_duration_mismatch": None if vocal_duration is None or backing_duration is None else round(abs(vocal_duration - backing_duration), 2),
        "final_mix_wav": file_status(final_wav),
        "final_mix_mp3": file_status(final_mp3),
        "final_mix_duration_seconds": final_duration,
        "final_mix_file_size": final_mp3.stat().st_size if final_mp3.exists() else 0,
        "melody_midi": analysis.melody_midi_status,
        "melody_note_count": melody_note_count,
        "melody_fallback_used": fallback_used,
        "chord_midi": file_status(chords_midi),
        "chord_sheet": file_status(chord_sheet),
        "producer_pack_zip": file_status(producer_pack),
        "clipping": "unknown" if final_peak is None else ("possible" if final_peak >= 0.99 else "none"),
        "clipping_detected": bool(final_peak is not None and final_peak >= 0.99),
        "final_peak": final_peak,
        "final_rms": final_rms,
        "final_silence_percentage": silence_percentage(final_wav),
        "vocal_gain_db": (final_settings.get("mix") or {}).get("vocal_gain_db", settings.default_vocal_gain_db),
        "backing_gain_db": (final_settings.get("mix") or {}).get("backing_gain_db", settings.default_backing_gain_db),
        "ducking_strength": (final_settings.get("mix") or {}).get("ducking_strength", settings.default_ducking_strength),
        "vocal_gain": (final_settings.get("mix") or {}).get("vocal_gain_linear", settings.vocal_mix_gain),
        "backing_gain": (final_settings.get("mix") or {}).get("backing_gain_linear", settings.backing_mix_gain),
        "key_confidence": confidence_bucket(analysis.key_confidence),
        "bpm_confidence": confidence_bucket(analysis.bpm_confidence),
        "tempo_match": "unknown" if duration_delta is None else ("good" if duration_delta <= 2.0 else "check"),
        "mix_loudness": "unknown" if final_peak is None else "good",
        "export_status": "ready" if not missing_files and file_status(final_mp3) == "present" else "check",
        "preview_exports": {name: file_status(path) for name, path in preview_files.items()},
        "final_generation_settings": final_settings,
        "generation_diagnostics": diagnostics,
        "last_logs": (job_logs or [])[-12:],
        "expected_pack_files": expected_pack_files,
        "missing_files": missing_files,
        "warnings": list(dict.fromkeys(report_warnings)),
    }


def confidence_bucket(value: float) -> str:
    if value >= 0.78:
        return "high"
    if value >= 0.5:
        return "medium"
    return "low"


def write_chord_sheet(
    path: Path,
    track_name: str,
    genre: Genre,
    analysis: SongAnalysis,
    blueprint: SongBlueprint,
    arrangement_mode: ArrangementMode = ArrangementMode.vocal_to_song,
) -> None:
    lines = [
        f"Skarly Demo: {track_name}",
        f"Genre: {genre.value}",
        f"Mode: {arrangement_mode_label(arrangement_mode)}",
        f"Detected BPM: {analysis.detected_bpm or analysis.bpm or 'Unknown'}",
        f"Production BPM: {analysis.production_bpm or analysis.bpm or 'Unknown'}",
        f"Tempo feel: {analysis.tempo_feel}",
        f"Key: {analysis.primary_key or analysis.key or 'Unknown'}",
        f"Alternative key: {analysis.alternative_key or 'Unknown'}",
        f"Mood: {analysis.mood}",
        f"Genre / Style: {analysis.production_style or genre.value}",
        f"Arrangement style: {analysis.arrangement_style or 'Unknown'}",
        f"Main instruments: {', '.join(analysis.main_instruments) if analysis.main_instruments else 'Unknown'}",
        "",
        "Structure:",
    ]
    lines.extend(f"- {section.name}: {section.bars} bars - {section.note}" for section in blueprint.structure)
    lines.extend(["", "Chords:", " - ".join(blueprint.chords), "", "Production Notes:"])
    lines.extend(f"- {note}" for note in blueprint.production_notes)
    lines.extend(["", "Lyric / Rap Notes:"])
    lines.extend(f"- {note}" for note in blueprint.lyric_suggestions)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def arrangement_mode_label(mode: ArrangementMode) -> str:
    labels = {
        ArrangementMode.vocal_to_song: "Vocal to Full Song",
        ArrangementMode.music_to_music: "Music to New Music",
        ArrangementMode.full_song: "Full Song Re-Arrange",
    }
    return labels[mode]


def write_producer_pack(path: Path, files: dict[str, Path]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for arcname, file_path in files.items():
            if file_path.exists():
                archive.write(file_path, arcname)


def write_midi_chords(path: Path, blueprint: SongBlueprint, analysis: SongAnalysis) -> None:
    bpm = int(analysis.production_bpm or analysis.bpm or 92)
    ticks_per_beat = 480
    microseconds_per_quarter = max(1, int(60_000_000 / max(30, min(220, bpm))))
    track = bytearray()
    track.extend(b"\x00\xff\x51\x03" + microseconds_per_quarter.to_bytes(3, "big"))
    track.extend(b"\x00\xc0\x00")
    for chord in blueprint.chords:
        notes = chord_to_midi_notes(chord)
        for note in notes:
            track.extend(b"\x00" + bytes([0x90, note, 70]))
        duration = ticks_per_beat * 4
        for index, note in enumerate(notes):
            track.extend(varlen(duration if index == 0 else 0) + bytes([0x80, note, 0]))
    track.extend(b"\x00\xff\x2f\x00")
    header = b"MThd" + (6).to_bytes(4, "big") + (0).to_bytes(2, "big") + (1).to_bytes(2, "big") + ticks_per_beat.to_bytes(2, "big")
    chunk = b"MTrk" + len(track).to_bytes(4, "big") + bytes(track)
    path.write_bytes(header + chunk)


def chord_to_midi_notes(chord: str) -> list[int]:
    root_name = chord.strip().replace("m", "")
    notes = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    root = notes.index(root_name) if root_name in notes else 0
    base = 60 + root
    intervals = [0, 3, 7] if chord.endswith("m") else [0, 4, 7]
    return [base + interval for interval in intervals]


def varlen(value: int) -> bytes:
    buffer = value & 0x7F
    value >>= 7
    bytes_out = [buffer]
    while value:
        buffer = (value & 0x7F) | 0x80
        bytes_out.insert(0, buffer)
        value >>= 7
    return bytes(bytes_out)


def ffprobe_path(ffmpeg_path: str) -> str | None:
    explicit = Path(ffmpeg_path)
    if explicit.name.lower().startswith("ffmpeg"):
        candidate = explicit.with_name(explicit.name.lower().replace("ffmpeg", "ffprobe", 1))
        if candidate.exists():
            return str(candidate)
    return shutil.which("ffprobe")


def command_parts(value: str) -> list[str]:
    parts = shlex.split(value, posix=os.name != "nt")
    if parts and parts[0].lower() in {"python", "python.exe", "py"}:
        parts[0] = sys.executable
    return parts or [value]


def local_dependency_env(include_backend_deps: bool = True) -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUTF8", "1")
    if not include_backend_deps:
        env.pop("PYTHONPATH", None)
        return env
    backend_root = Path(__file__).resolve().parent.parent
    local_paths = [backend_root / ".demucsdeps", backend_root / ".pydeps"]
    pythonpath_parts = [str(path) for path in local_paths if path.exists()]
    pythonpath_parts.extend(part for part in env.get("PYTHONPATH", "").split(os.pathsep) if part)
    if pythonpath_parts:
        env["PYTHONPATH"] = os.pathsep.join(dict.fromkeys(pythonpath_parts))
    return env


def command_uses_current_python(parts: list[str]) -> bool:
    if not parts:
        return True
    executable = parts[0]
    if executable.lower() in {"python", "python.exe", "py"}:
        return True
    resolved_executable = shutil.which(executable) or executable
    try:
        return Path(resolved_executable).resolve() == Path(sys.executable).resolve()
    except OSError:
        return False


def tool_dependency_env(parts: list[str]) -> dict[str, str]:
    return local_dependency_env(include_backend_deps=command_uses_current_python(parts))


def command_is_available(parts: list[str]) -> bool:
    if not parts:
        return False
    executable = parts[0]
    try:
        executable_exists = Path(executable).exists()
    except OSError:
        executable_exists = False
    if shutil.which(executable) is None and not executable_exists:
        return False
    if len(parts) >= 3 and parts[1] == "-m" and parts[2].startswith("demucs"):
        probe = subprocess.run(
            [executable, "-c", f"import {parts[2]}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=tool_dependency_env(parts),
            timeout=10,
        )
        return probe.returncode == 0
    return True


def create_basic_pitch_melody(
    input_audio_path: Path,
    output_dir: Path,
    output_midi: Path,
    output_notes: Path,
    analysis: SongAnalysis,
) -> tuple[Path, Path | None]:
    command = command_parts(settings.basic_pitch_path)
    if not command_is_available(command):
        raise MelodyAnalysisError("Basic Pitch is not available")

    output_dir.mkdir(parents=True, exist_ok=True)
    args = [
        *command,
        str(output_dir),
        str(input_audio_path),
        "--save-midi",
        "--model-serialization",
        settings.basic_pitch_model_serialization,
    ]
    if settings.basic_pitch_save_note_events:
        args.append("--save-note-events")
    if analysis.production_bpm or analysis.bpm:
        tempo = int(max(40, min(220, round(float(analysis.production_bpm or analysis.bpm)))))
        args.extend(["--midi-tempo", str(tempo)])

    try:
        subprocess.run(
            args,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=tool_dependency_env(command),
            timeout=settings.melody_timeout_sec,
        )
    except subprocess.TimeoutExpired as exc:
        raise MelodyAnalysisError(f"Basic Pitch timed out after {exc.timeout} seconds") from exc
    except subprocess.CalledProcessError as exc:
        message = exc.stderr.decode("utf-8", errors="ignore").strip() if exc.stderr else "Basic Pitch processing failed"
        raise MelodyAnalysisError(message[:220]) from exc

    midi_candidates = sorted([*output_dir.rglob("*.mid"), *output_dir.rglob("*.midi")])
    if not midi_candidates:
        raise MelodyAnalysisError("Basic Pitch did not produce a MIDI file")
    shutil.copyfile(midi_candidates[0], output_midi)

    notes_file: Path | None = None
    if settings.basic_pitch_save_note_events:
        note_candidates = sorted(output_dir.rglob("*.csv"))
        if note_candidates:
            shutil.copyfile(note_candidates[0], output_notes)
            notes_file = output_notes
    return output_midi, notes_file


def useful_subprocess_error(stderr: str) -> str:
    lines = [line.strip() for line in stderr.splitlines() if line.strip()]
    useful_markers = (
        "error",
        "failed",
        "invalid",
        "out of range",
        "not found",
        "unable",
        "conversion failed",
    )
    useful = [line for line in lines if any(marker in line.lower() for marker in useful_markers)]
    return " | ".join(useful[-3:]) if useful else "FFmpeg processing failed"


def useful_tool_error(stderr: str, fallback: str) -> str:
    lines = [line.strip() for line in stderr.splitlines() if line.strip()]
    progress_markers = ("|", "seconds/s", "it/s", "%")
    cleaned = [
        line
        for line in lines
        if not (line.startswith("0%") or all(marker in line for marker in progress_markers[:2]))
    ]
    useful_markers = (
        "error",
        "failed",
        "exception",
        "traceback",
        "runtimeerror",
        "cuda",
        "memory",
        "not found",
        "no such file",
        "unable",
        "timed out",
    )
    useful = [line for line in cleaned if any(marker in line.lower() for marker in useful_markers)]
    if useful:
        return " | ".join(useful[-3:])
    if cleaned:
        return " | ".join(cleaned[-3:])
    return fallback


def final_mp3_path(user_id: str, job_id: str, track_name: str, raw_audio_path: str | None = None) -> str:
    return final_mp3_path_for_job(user_id, job_id, track_name, raw_audio_path)


def final_mp3_path_for_job(user_id: str, job_id: str, track_name: str, raw_audio_path: str | None = None) -> str:
    owner_prefix = owner_prefix_from_raw_path(raw_audio_path) or f"users/{user_id}"
    return f"{owner_prefix}/final/{job_id}/{safe_audio_slug(track_name)}.mp3"


def debug_audio_path_for_job(user_id: str, job_id: str, filename: str, raw_audio_path: str | None = None) -> str:
    owner_prefix = owner_prefix_from_raw_path(raw_audio_path) or f"users/{user_id}"
    return f"{owner_prefix}/debug/{job_id}/{filename}"


def demo_export_path_for_job(user_id: str, job_id: str, filename: str, raw_audio_path: str | None = None) -> str:
    owner_prefix = owner_prefix_from_raw_path(raw_audio_path) or f"users/{user_id}"
    return f"{owner_prefix}/exports/{job_id}/{filename}"


def safe_audio_slug(value: str) -> str:
    cleaned = "".join(char.lower() if char.isalnum() else "-" for char in value.strip())
    cleaned = "-".join(part for part in cleaned.split("-") if part)
    return cleaned[:64] or "skarly-mix"


def owner_prefix_from_raw_path(raw_audio_path: str | None) -> str | None:
    if not raw_audio_path or "/raw/" not in raw_audio_path:
        return None
    return raw_audio_path.split("/raw/", 1)[0]


def create_music_bed_with_report(
    path: Path,
    genre: Genre,
    job_id: str,
    seconds: float = 62.0,
    sample_rate: int = 44100,
    source_audio_path: Path | None = None,
    timing: dict[str, Any] | None = None,
    ffmpeg_path: str | None = None,
) -> dict[str, Any]:
    selected_generator = settings.music_generator_backend
    report: dict[str, Any] = {
        "selected_generator": selected_generator,
        "final_generator_used": None,
        "requested_duration": round(float(seconds), 2),
        "detected_bpm": (timing or {}).get("detected_bpm") or (timing or {}).get("tempo_bpm"),
        "production_bpm": (timing or {}).get("production_bpm"),
        "selected_genre": genre.value,
        "language": clean_language((timing or {}).get("language")),
        "lyrics_provided": bool(clean_prompt_text((timing or {}).get("lyrics"), 2000)),
        "production_style": (timing or {}).get("production_style"),
        "arrangement_style": (timing or {}).get("arrangement_style"),
        "arrangement_mode": arrangement_mode_from_timing(timing).value,
        "reference_conditioned": False,
        "selected_key": (timing or {}).get("primary_key"),
        "generation_start_time": utc_now_iso(),
        "timeout_seconds": settings.backing_generation_timeout_sec,
        "expected_output_path": str(path),
        "fallback_attempted": False,
        "fallback_result": "not_attempted",
        "warnings": [],
    }

    def use_procedural(reason: str) -> None:
        report["fallback_attempted"] = True
        report["fallback_reason"] = reason
        report["fallback_result"] = "attempted"
        create_arranged_genre_bed(path, genre, seconds, sample_rate, timing)
        validation = validate_backing_output(path, seconds, ffmpeg_path or settings.ffmpeg_path)
        report["procedural_v2_validation"] = validation
        if not validation["valid"]:
            report["fallback_result"] = "failed"
            raise BackingGenerationError(
                "Backing generation failed: ACE-Step failed and procedural_v2 fallback did not create valid audio. "
                + "; ".join(validation.get("errors") or [reason])
            )
        report["fallback_result"] = "succeeded"
        report["final_generator_used"] = "procedural_v2"
        warning = "ACE-Step generation failed or timed out, so Skarly used procedural_v2 fallback backing."
        report["warnings"].append(warning)

    if selected_generator == "ace_step":
        report["ace_step_endpoint"] = settings.ace_step_base_url
        health = ace_step_health_check()
        report["ace_step_health"] = health
        if not health.get("success"):
            reason = f"ACE-Step is not reachable. Falling back to procedural_v2. {health.get('error') or ''}".strip()
            report["ace_step_error"] = reason
            if not settings.ace_step_fallback_to_procedural:
                raise BackingGenerationError("Backing generation failed: ACE-Step is not reachable and fallback is disabled.")
            use_procedural(reason)
            report["completed_at"] = utc_now_iso()
            report.update(output_file_metadata(path, ffmpeg_path or settings.ffmpeg_path))
            return report
        try:
            create_ace_step_bed(path, genre, seconds, source_audio_path, timing)
            validation = validate_backing_output(path, seconds, ffmpeg_path or settings.ffmpeg_path)
            report["ace_step_validation"] = validation
            if not validation["valid"]:
                raise BackingGenerationError(
                    "ACE-Step did not create a valid backing audio file: "
                    + "; ".join(validation.get("errors") or ["unknown validation error"])
                )
            report["final_generator_used"] = "ace_step"
            if arrangement_mode_from_timing(timing) == ArrangementMode.music_to_music:
                report["reference_conditioned"] = bool(source_audio_path and source_audio_path.exists())
                report["reference_strength"] = max(0.05, min(0.95, settings.ace_step_source_audio_strength))
        except Exception as exc:
            reason = f"ACE-Step generation failed: {exc}"
            report["ace_step_error"] = reason
            if not settings.ace_step_fallback_to_procedural:
                raise BackingGenerationError(reason) from exc
            use_procedural(reason)
        report["completed_at"] = utc_now_iso()
        report.update(output_file_metadata(path, ffmpeg_path or settings.ffmpeg_path))
        return report

    create_genre_bed(path, genre, seconds, sample_rate, timing)
    validation = validate_backing_output(path, seconds, ffmpeg_path or settings.ffmpeg_path)
    report["procedural_v2_validation"] = validation
    if not validation["valid"]:
        raise BackingGenerationError(
            "procedural_v2 did not create a valid backing audio file: "
            + "; ".join(validation.get("errors") or ["unknown validation error"])
        )
    report["final_generator_used"] = settings.music_generator_backend
    report["completed_at"] = utc_now_iso()
    report.update(output_file_metadata(path, ffmpeg_path or settings.ffmpeg_path))
    return report


def create_music_bed(
    path: Path,
    genre: Genre,
    job_id: str,
    seconds: float = 62.0,
    sample_rate: int = 44100,
    source_audio_path: Path | None = None,
    timing: dict[str, float] | None = None,
) -> None:
    create_music_bed_with_report(path, genre, job_id, seconds, sample_rate, source_audio_path, timing)


def ace_step_health_check() -> dict[str, Any]:
    base_url = settings.ace_step_base_url.rstrip("/") + "/"
    result: dict[str, Any] = {
        "endpoint": base_url,
        "success": False,
        "response_time_ms": None,
        "error": None,
    }
    if requests is None:
        result["error"] = "requests is not installed"
        return result
    if settings.app_env == "test":
        result["success"] = True
        result["skipped_in_test"] = True
        return result
    started = time.monotonic()
    for endpoint in ("health", ""):
        url = urljoin(base_url, endpoint)
        try:
            response = requests.get(url, timeout=3)
            result["response_time_ms"] = round((time.monotonic() - started) * 1000, 1)
            result["status_code"] = response.status_code
            result["checked_url"] = url
            if response.status_code < 500:
                result["success"] = True
                return result
            result["error"] = f"HTTP {response.status_code}"
        except Exception as exc:
            result["response_time_ms"] = round((time.monotonic() - started) * 1000, 1)
            result["checked_url"] = url
            result["error"] = ace_step_request_error("health check", exc)
    return result


def validate_backing_output(path: Path, requested_seconds: float, ffmpeg_path: str) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    exists = path.exists()
    size = path.stat().st_size if exists else 0
    duration = media_duration_seconds(path, ffmpeg_path) if exists else None
    rms = audio_rms(path)
    silence_pct = silence_percentage(path)
    min_size = 512
    min_duration = max(0.1, min(1.0, requested_seconds * 0.2))
    requested = max(0.0, float(requested_seconds))

    if not exists:
        errors.append("expected backing output file does not exist")
    elif size < min_size:
        errors.append(f"backing output file is too small ({size} bytes)")
    if duration is None:
        errors.append("ffprobe could not detect valid audio duration")
    elif duration < min_duration:
        errors.append(f"backing audio is too short ({duration:.2f}s)")
    elif requested >= 10 and duration < requested * 0.75:
        errors.append(f"backing audio is shorter than expected ({duration:.2f}s for requested {requested:.2f}s)")
    elif requested >= 10 and abs(duration - requested) > max(4.0, requested * 0.25):
        warnings.append(f"backing duration differs from requested duration ({duration:.2f}s vs {requested:.2f}s)")
    if requested >= 1 and rms is not None and rms <= 0.0002:
        errors.append("backing audio appears silent or nearly silent")
    if requested >= 1 and silence_pct is not None and silence_pct >= 95:
        errors.append(f"backing audio is mostly silent ({silence_pct:.1f}% silence)")

    return {
        "valid": not errors,
        "exists": exists,
        "file_size": size,
        "ffprobe_duration": duration,
        "requested_duration": round(requested, 2),
        "rms": rms,
        "silence_percentage": silence_pct,
        "errors": errors,
        "warnings": warnings,
    }


def output_file_metadata(path: Path, ffmpeg_path: str) -> dict[str, Any]:
    exists = path.exists()
    return {
        "output_file_exists": exists,
        "output_file_size": path.stat().st_size if exists else 0,
        "output_ffprobe_duration": media_duration_seconds(path, ffmpeg_path) if exists else None,
    }


def media_duration_seconds(path: Path | None, ffmpeg_path: str) -> float | None:
    if path is None or not path.exists():
        return None
    ffprobe = ffprobe_path(ffmpeg_path)
    if ffprobe:
        try:
            result = subprocess.run(
                [
                    ffprobe,
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    str(path),
                ],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=10,
            )
            duration = float(result.stdout.strip())
            if math.isfinite(duration) and duration > 0:
                return round(duration, 2)
        except Exception:
            pass
    return simple_wav_duration(path)


def silence_percentage(path: Path | None, threshold: float = 0.001) -> float | None:
    if path is None or not path.exists():
        return None
    try:
        with wave.open(str(path), "rb") as wav:
            sample_width = wav.getsampwidth()
            if sample_width != 2:
                return None
            frames = wav.readframes(wav.getnframes())
            if not frames:
                return None
            samples = struct.unpack("<" + "h" * (len(frames) // 2), frames)
            if not samples:
                return None
            silent = sum(1 for sample in samples if abs(sample) / 32768 <= threshold)
            return round((silent / len(samples)) * 100, 2)
    except Exception:
        return None


def create_ace_step_bed(path: Path, genre: Genre, seconds: float = 62.0, source_audio_path: Path | None = None, timing: dict[str, float] | None = None) -> None:
    if requests is None:
        raise RuntimeError("ACE-Step dependencies are not installed")

    base_url = settings.ace_step_base_url.rstrip("/") + "/"
    headers = ace_step_headers()
    payload = ace_step_payload(genre, seconds, timing)

    files = None
    opened = None
    try:
        arrangement_mode = arrangement_mode_from_timing(timing)
        reference_conditioning = arrangement_mode == ArrangementMode.music_to_music
        use_source_audio = settings.ace_step_use_source_audio or reference_conditioning
        if use_source_audio and source_audio_path and source_audio_path.exists():
            opened = source_audio_path.open("rb")
            files = {"src_audio": (source_audio_path.name, opened, "audio/wav")}
            if reference_conditioning:
                payload["task_type"] = "cover"
                payload["audio_cover_strength"] = max(
                    0.05,
                    min(0.95, float(settings.ace_step_source_audio_strength)),
                )
                payload["lyrics"] = "[Instrumental]"
                payload["thinking"] = False
            elif settings.ace_step_source_task_type:
                payload["task_type"] = settings.ace_step_source_task_type

        response = requests.post(
            urljoin(base_url, "release_task"),
            headers=headers,
            data=payload if files else None,
            json=None if files else payload,
            files=files,
            timeout=min(600, max(120, int(settings.ace_step_timeout_seconds))),
        )
    except Exception as exc:
        raise RuntimeError(ace_step_request_error("release_task", exc)) from exc
    finally:
        if opened is not None:
            opened.close()

    if response.status_code >= 400:
        raise RuntimeError(f"ACE-Step release failed: {response.status_code} {response.text[:220]}")

    task_id = extract_ace_task_id(response.json())
    if not task_id:
        raise RuntimeError("ACE-Step response did not include a task id")

    result = poll_ace_step_task(base_url, task_id, headers)
    audio_url = extract_ace_audio_url(result)
    if not audio_url:
        raise RuntimeError("ACE-Step result did not include an audio URL")

    audio_endpoint = ace_step_audio_endpoint(base_url, audio_url)
    audio_response = None
    last_download_error: Exception | None = None
    for _ in range(2):
        try:
            audio_response = requests.get(audio_endpoint, headers=headers, timeout=settings.ace_step_download_timeout_seconds)
            break
        except Exception as exc:
            last_download_error = exc
    if audio_response is None:
        raise RuntimeError(ace_step_request_error("audio download", last_download_error or RuntimeError("download failed")))
    if audio_response.status_code >= 400:
        raise RuntimeError(f"ACE-Step audio download failed: {audio_response.status_code} {audio_response.text[:220]}")
    if not audio_response.content:
        raise RuntimeError("ACE-Step audio download was empty")
    path.write_bytes(audio_response.content)


def ace_step_headers() -> dict[str, str]:
    headers: dict[str, str] = {}
    if settings.ace_step_api_key:
        headers["Authorization"] = f"Bearer {settings.ace_step_api_key}"
    return headers


def ace_step_payload(genre: Genre, seconds: float, timing: dict[str, float] | None = None) -> dict[str, Any]:
    duration = min(settings.ace_step_max_duration_seconds, max(10, int(seconds)))
    lyrics = clean_prompt_text((timing or {}).get("lyrics"), 2000)
    payload: dict[str, Any] = {
        "prompt": ace_step_prompt(genre, duration, timing),
        "lyrics": lyrics if settings.ace_step_send_lyrics else "",
        "audio_duration": duration,
        "audio_format": "wav",
        "infer_step": settings.ace_step_infer_step,
        "guidance_scale": settings.ace_step_guidance_scale,
        "scheduler_type": "euler",
        "cfg_type": "apg",
        "omega_scale": 10,
        "manual_seeds": "",
        "thinking": settings.ace_step_thinking,
    }
    negative_prompt = (timing or {}).get("producer_negative_prompt") if timing else None
    if negative_prompt:
        payload["negative_prompt"] = negative_prompt
    if settings.ace_step_model:
        payload["checkpoint_path"] = settings.ace_step_model
    return payload


def ace_step_prompt(genre: Genre, seconds: int, timing: dict[str, float] | None = None) -> str:
    producer_prompt = (timing or {}).get("producer_prompt") if timing else None
    if isinstance(producer_prompt, str) and producer_prompt.strip():
        return producer_prompt.strip()
    prompt = backing_prompt(genre, seconds, timing)
    arrangement_mode = arrangement_mode_from_timing(timing)
    language = clean_language((timing or {}).get("language"))
    lyrics = clean_prompt_text((timing or {}).get("lyrics"), 500)
    tempo = (timing or {}).get("production_bpm") or ((timing or {}).get("tempo_bpm") if timing else None)
    tempo_text = f" Lock the instrumental grid near {tempo:.0f} BPM and follow the vocal phrase spacing." if tempo else " Follow the vocal phrase spacing and natural cadence."
    activity_text = vocal_activity_prompt(timing)
    language_text = (
        f" Language context: {language}. Support the lyric emotion without creating new sung words: {lyrics}. "
        if lyrics
        else f" Language context: {language}. "
    )
    if arrangement_mode == ArrangementMode.music_to_music:
        reference_text = (
            " Use the uploaded music only as a tempo, section, and energy reference. "
            "Replace the old instrumental rather than copying or layering over it. "
            "Instrumental output only: no generated singing, no humming, no choirs, no background vocals, no ad-libs, no spoken words, no chorus lyrics. "
        )
        tempo_text = f" Lock the instrumental grid near {tempo:.0f} BPM and create new section changes." if tempo else " Infer the reference groove and create new section changes."
    elif arrangement_mode == ArrangementMode.full_song:
        reference_text = (
            " Use the uploaded full song as timing, phrasing, energy, and emotional reference. "
            "Replace the old beat where possible while leaving room for the original lead source. "
            "Backing-focused output: no generated lead singing, no lyric vocals, no ad-libs, no spoken words. "
        )
    else:
        reference_text = (
            " Use the uploaded vocal only as timing, phrasing, energy, and emotional reference. "
            "Replace the old beat rather than copying or layering over it. Build a supportive groove that leaves room for the original lead vocal and any existing backing vocals/ad-libs in the vocal stem. "
            "Instrumental backing only: no generated singing, no humming, no choirs, no background vocals, no ad-libs, no spoken words, no chorus lyrics. "
        )
    return (
        prompt
        + language_text
        + reference_text
        + tempo_text
        + activity_text
        + " Use clear downbeats, stable tempo, and open midrange pockets so the source phrasing sits naturally. Avoid busy lead melodies and avoid artist imitation."
    )


def extract_ace_task_id(data: dict[str, Any]) -> str | None:
    for key in ("task_id", "taskId", "id"):
        value = data.get(key)
        if isinstance(value, str) and value:
            return value
    nested = data.get("data") or data.get("result")
    if isinstance(nested, dict):
        return extract_ace_task_id(nested)
    return None


def poll_ace_step_task(base_url: str, task_id: str, headers: dict[str, str]) -> dict[str, Any]:
    deadline = time.monotonic() + settings.ace_step_timeout_seconds
    last_result: dict[str, Any] = {}
    while time.monotonic() < deadline:
        try:
            response = requests.post(
                urljoin(base_url, "query_result"),
                headers=headers,
                json={"task_id_list": [task_id]},
                timeout=30,
            )
        except Exception as exc:
            raise RuntimeError(ace_step_request_error("query_result", exc)) from exc
        if response.status_code >= 400:
            raise RuntimeError(f"ACE-Step query failed: {response.status_code} {response.text[:220]}")
        data = response.json()
        last_result = data
        task = extract_ace_task_result(data, task_id)
        status = ace_task_status(task or data)
        if status in {"failed", "error", "canceled", "cancelled"}:
            raise RuntimeError(f"ACE-Step task failed: {data}")
        if status in {"completed", "complete", "done", "succeeded", "success", "finished"} or extract_ace_audio_url(task or data):
            return task or data
        time.sleep(settings.ace_step_poll_interval_seconds)
    raise RuntimeError(f"ACE-Step task timed out after {settings.ace_step_timeout_seconds} seconds while waiting for backing generation: {last_result}")


def extract_ace_task_result(data: dict[str, Any], task_id: str) -> dict[str, Any] | None:
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


def ace_task_status(data: dict[str, Any]) -> str:
    status = data.get("status") or data.get("state") or data.get("task_status")
    if status == 0:
        return "queued"
    if status == 1:
        return "running"
    if status == 2:
        return "completed"
    if status == 3:
        return "failed"
    return str(status or "").lower()


def extract_ace_audio_url(data: Any) -> str | None:
    if isinstance(data, dict):
        for key in ("audio_url", "audioUrl", "url", "path", "file", "wave", "output_path", "file_url", "download_url"):
            value = data.get(key)
            if isinstance(value, str) and value:
                return value
        result_value = data.get("result")
        if isinstance(result_value, str):
            parsed = parse_ace_result_json(result_value)
            if parsed is not None:
                found = extract_ace_audio_url(parsed)
                if found:
                    return found
        for key in ("result", "data", "output", "outputs"):
            found = extract_ace_audio_url(data.get(key))
            if found:
                return found
        for value in data.values():
            found = extract_ace_audio_url(value)
            if found:
                return found
    if isinstance(data, list):
        for item in data:
            found = extract_ace_audio_url(item)
            if found:
                return found
    if isinstance(data, str) and (data.startswith("/v1/audio") or data.startswith("http") or data.endswith((".wav", ".mp3", ".flac"))):
        return data
    return None


def parse_ace_result_json(value: str) -> Any | None:
    text = value.strip()
    if not text.startswith(("{", "[")):
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def ace_step_audio_endpoint(base_url: str, audio_url: str) -> str:
    if audio_url.startswith("http"):
        return audio_url
    if audio_url.startswith("/v1/audio"):
        return urljoin(base_url, audio_url.lstrip("/"))
    return urljoin(base_url, f"v1/audio/{audio_url.lstrip('/')}")


def ace_step_request_error(operation: str, exc: Exception) -> str:
    if requests is not None:
        timeout_error = getattr(requests, "Timeout", None)
        connection_error = getattr(requests, "ConnectionError", None)
        if timeout_error is not None and isinstance(exc, timeout_error):
            return f"ACE-Step {operation} timed out. Make sure the ACE server is fully loaded at {settings.ace_step_base_url}."
        if connection_error is not None and isinstance(exc, connection_error):
            return f"ACE-Step {operation} could not connect to {settings.ace_step_base_url}. Start ACE-Step before generating."
    return f"ACE-Step {operation} failed: {exc}"


def backing_prompt(genre: Genre, seconds: float, timing: dict[str, float] | None = None) -> str:
    producer_prompt = (timing or {}).get("producer_prompt") if timing else None
    if isinstance(producer_prompt, str) and producer_prompt.strip():
        return producer_prompt.strip()
    arrangement_mode = arrangement_mode_from_timing(timing)
    details = {
        Genre.lofi: "Production style: late-night lo-fi only. Instrument limits: dusty swung drums, vinyl noise, mellow electric piano, soft sidechain chords, muted sub. Do not use trap 808s, rock guitars, orchestral brass, or pop synth hooks. Improvisation: convert the uploaded song's groove into a calmer hazy loop while keeping vocal timing intact",
        Genre.piano: "Production style: intimate jazz-pop piano only. Instrument limits: felt piano, brushed rhythm, warm upright bass, soft room ambience. Do not use trap hats, big drums, synth leads, or guitars. Improvisation: reshape the uploaded groove into a tasteful piano-led arrangement that follows vocal phrasing",
        Genre.pop: "Production style: crisp classic dance-pop and funk-pop. Instrument limits: tight four-on-the-floor drums, bright bass movement, claps, glossy short synth stabs, clean hook rhythm. Do not use cinematic drums, trap 808 patterns, or rock guitars. Improvisation: replace the uploaded beat with a cleaner dance-pop rhythm that supports the vocal",
        Genre.rock: "Production style: heavy arena rock rhythm section. Instrument limits: distorted rhythm guitar, electric bass, tight kick/snare/toms, restrained guitar accents. Do not use trap hats, orchestral pads, or soft piano ballad patterns. Improvisation: transform the uploaded rhythm into a hard rock backing without covering the vocal",
        Genre.rnb: "Production style: dark modern R&B. Instrument limits: slow half-time drums, deep sub bass, airy synth pads, soft keys, sparse plucks. Do not use busy pop hooks, rock guitars, or huge cinematic drums. Improvisation: rebuild the uploaded beat into a spacious nocturnal pocket that leaves room for lead and backing vocals",
        Genre.hiphop: "Production style: dark modern hip-hop and trap. Instrument limits: bouncing 808s, crisp triplet hi-hats, punchy clap/snare, sparse bells, dark synth motif. Do not use acoustic strumming, orchestral brass, or dance-pop four-on-floor. Improvisation: reinterpret the uploaded groove into a modern hip-hop bounce around the vocal cadence",
        Genre.acoustic: "Production style: polished acoustic-pop ballad. Instrument limits: fingerpicked acoustic guitar, gentle percussion, warm strings, soft bass. Do not use 808s, synth leads, rock distortion, or cinematic impacts. Improvisation: soften the uploaded beat into an organic acoustic backing that follows the lyrics and breath",
        Genre.cinematic: "Production style: restrained cinematic score. Instrument limits: soft low strings, subtle piano pulses, distant low brass, sparse drums only on phrase endings, optional wordless choir pad very low in the background. Do not use loud trailer drums, busy melodies, or pop/trap drum loops. Improvisation: turn the uploaded rhythm into an emotional score bed that follows the vocal breath instead of overpowering it",
    }
    duration = min(30, max(10, int(seconds)))
    tempo = (timing or {}).get("production_bpm") or ((timing or {}).get("tempo_bpm") if timing else None)
    timing_text = f" Target the groove around {tempo:.0f} BPM based on the isolated vocal timing." if tempo else " Infer the groove from the isolated vocal timing."
    activity_text = vocal_activity_prompt(timing)
    if arrangement_mode == ArrangementMode.music_to_music:
        source_text = (
            f"Create a {duration}-second {genre.value} instrumental-only remake from an uploaded music reference. "
            "Use the reference only for tempo, broad energy, and section pacing; compose a new groove, chord movement, drums, bass, guitar or keys. "
        )
        source_usage_text = "Use the uploaded music reference for tempo feel, section energy, and broad groove only. "
        mix_text = (
            "Do not layer the original music back into the final. No vocals, no humming, no ad-libs, no spoken words, "
            "no copyrighted melody, no imitation of any artist or song. Make the arrangement feel like fresh music, not a repeated loop."
        )
        timing_text = f" Target the groove around {tempo:.0f} BPM from the reference." if tempo else " Infer the groove from the uploaded music reference."
    elif arrangement_mode == ArrangementMode.full_song:
        source_text = (
            f"Create a {duration}-second {genre.value} re-arranged backing for an uploaded full song. "
            "Use source separation when available and preserve room for the original lead vocal. "
        )
        source_usage_text = "Use the separated or original lead source for tempo feel, phrasing, emotional intensity, and section energy. "
        mix_text = (
            "Do not keep or recreate the uploaded song's old instrumental; generate a new genre-appropriate arrangement that fits the lead source. "
            "No generated lead vocals, no lyric vocals, no humming, no ad-libs, no spoken words, no copyrighted melody, no imitation of any artist or song. "
            "Leave clear midrange space for the original lead vocal and keep the beat lower than the vocal."
        )
    else:
        source_text = f"Create a {duration}-second {genre.value} backing instrumental for an isolated original vocal stem. "
        source_usage_text = "Use the vocal stem as the source for tempo feel, phrasing, emotional intensity, and section energy. "
        mix_text = (
            "Do not keep or recreate the uploaded song's old instrumental; generate a new genre-appropriate beat that fits the vocal. "
            "No lead vocals, no lyric vocals, no humming, no ad-libs, no spoken words, no copyrighted melody, no imitation of any artist or song. "
            "Choir textures are allowed only for cinematic and must be wordless, distant, low-volume, and behind the lead vocal. "
            "Leave clear midrange space for the lead vocal and existing backing vocals from the user's stem. Keep the beat lower than the vocal and make the arrangement loop-friendly."
        )
    return (
        source_text
        + f"{details[genre]}. "
        + f"{timing_text} {source_usage_text}"
        + f"{activity_text}"
        + f"{mix_text}"
    )


def vocal_activity_prompt(timing: dict[str, float] | None) -> str:
    activity = timing.get("activity_map") if timing else None
    if not isinstance(activity, dict) or not activity:
        return " "
    values = [float(value) for value in activity.values()]
    if not values:
        return " "
    average = sum(values) / len(values)
    active_seconds = [int(second) for second, value in activity.items() if float(value) >= average * 0.85]
    if not active_seconds:
        return " "
    ranges = compact_second_ranges(active_seconds[:40])
    return f" Vocal activity map: vocals are active around seconds {ranges}; keep drums and chord changes aligned to those moments, and leave lighter space in the gaps. "


def compact_second_ranges(seconds: list[int]) -> str:
    if not seconds:
        return ""
    seconds = sorted(set(seconds))
    ranges: list[str] = []
    start = previous = seconds[0]
    for second in seconds[1:]:
        if second == previous + 1:
            previous = second
            continue
        ranges.append(f"{start}-{previous}" if start != previous else str(start))
        start = previous = second
    ranges.append(f"{start}-{previous}" if start != previous else str(start))
    return ", ".join(ranges)


def create_genre_bed(path: Path, genre: Genre, seconds: float = 62.0, sample_rate: int = 44100, timing: dict[str, float] | None = None) -> None:
    if settings.music_generator_backend not in {"procedural", "procedural_v2"}:
        raise RuntimeError(f"Unsupported SKARLY_MUSIC_GENERATOR_BACKEND: {settings.music_generator_backend}")
    if settings.music_generator_backend == "procedural":
        create_basic_genre_bed(path, genre, seconds, sample_rate, timing)
        return
    create_arranged_genre_bed(path, genre, seconds, sample_rate, timing)


def create_basic_genre_bed(path: Path, genre: Genre, seconds: float = 62.0, sample_rate: int = 44100, timing: dict[str, float] | None = None) -> None:
    profile = timed_genre_profile(genre, timing)
    total_frames = int(seconds * sample_rate)
    beat_interval = max(1, int(sample_rate * 60 / profile["bpm"]))
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        for index in range(total_frames):
            beat = 1.0 if index % beat_interval < int(sample_rate * 0.035) else 0.0
            phrase = (index // beat_interval) % len(profile["notes"])
            frequency = profile["notes"][phrase]
            t = index / sample_rate
            tone = math.sin(2 * math.pi * frequency * t) * profile["tone"]
            sub = math.sin(2 * math.pi * (frequency / 2) * t) * profile["sub"]
            noise = math.sin(2 * math.pi * 63 * t) * beat * profile["kick"]
            envelope = min(1.0, index / (sample_rate * 1.2)) * min(1.0, (total_frames - index) / (sample_rate * 1.8))
            sample = max(-0.92, min(0.92, (tone + sub + noise) * envelope))
            packed = struct.pack("<h", int(sample * 32767))
            wav.writeframesraw(packed + packed)


def create_arranged_genre_bed(path: Path, genre: Genre, seconds: float = 62.0, sample_rate: int = 44100, timing: dict[str, float] | None = None) -> None:
    profile = timed_genre_profile(genre, timing)
    total_frames = int(seconds * sample_rate)
    beat_frames = max(1, int(sample_rate * 60 / profile["bpm"]))
    bar_frames = beat_frames * 4
    fade_in = sample_rate * 1.1
    fade_out = sample_rate * 1.8
    sections = arrangement_sections(seconds)

    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        for index in range(total_frames):
            t = index / sample_rate
            section = arrangement_section_at(sections, t)
            section_mix = arrangement_section_mix(section["role"])
            vocal_activity = vocal_activity_at_second(timing, int(t))
            beat_position = index % beat_frames
            beat = (index // beat_frames) % 4
            absolute_bar = index // bar_frames
            section_bar = max(0, int((t - float(section["start"])) * sample_rate) // bar_frames)
            roots = arranged_section_roots(profile["roots"], int(section["index"]), section["role"])
            root = roots[(absolute_bar + int(section["index"])) % len(roots)]
            chord = [root * ratio for ratio in arranged_section_chord(profile["chord"], section["role"], section_bar)]
            bar_position = (index % bar_frames) / bar_frames
            bar_phrase = (section_bar % 8) / 8
            phrase_lift = 0.85 + 0.15 * math.sin(2 * math.pi * bar_phrase)
            gate = (0.50 + 0.50 * (0.5 + 0.5 * math.sin(2 * math.pi * bar_position))) * phrase_lift

            pad = sum(soft_sine(freq, t, profile["pad_shape"]) for freq in chord) / len(chord)
            pad *= profile["pad"] * gate * section_mix["pad"] * (0.72 + vocal_activity * 0.28)

            bass_ratio = bass_motion_ratio(beat, section_bar, section["role"], float(profile["bass_walk"]))
            bass_note = root * bass_ratio / 2
            bass = soft_sine(bass_note, t, 0.72) * profile["bass"] * section_mix["bass"] * pulse_envelope(beat_position, beat_frames, 0.45) * (0.65 + vocal_activity * 0.35)

            lead_index = ((index // (beat_frames // 2 or 1)) + section_bar + int(section["index"])) % len(profile["lead"])
            lead_freq = root * profile["lead"][lead_index]
            lead = soft_sine(lead_freq, t, 0.38) * profile["lead_level"] * section_mix["lead"] * pulse_envelope(index % (beat_frames // 2 or 1), beat_frames // 2 or 1, 0.35) * (0.35 + vocal_activity * 0.25)

            guitar = 0.0
            if profile.get("guitar"):
                strum_rate = section_strum_rate(int(profile.get("guitar_rate", 2)), section["role"], section_bar)
                strum_frames = max(1, beat_frames // strum_rate)
                strum_position = index % strum_frames
                strum_index = ((index // strum_frames) + section_bar) % len(chord)
                strum_freq = chord[strum_index]
                guitar_tone = guitar_strum(strum_freq, t, strum_position, strum_frames, sample_rate, float(profile.get("guitar_brightness", 0.6)))
                guitar = guitar_tone * float(profile["guitar"]) * section_mix["guitar"] * (0.55 + vocal_activity * 0.35)

            drum_energy = (0.55 + vocal_activity * 0.45) * section_mix["drums"]
            kick_beats = set(profile["kick_beats"])
            if section["role"] in {"chorus", "final_chorus"} and section_bar % 4 in {1, 3}:
                kick_beats.add(3)
            kick = drum_hit(beat_position, sample_rate, profile["kick_decay"], 58.0) * profile["kick"] * drum_energy if beat in kick_beats else 0.0
            snare = noise_hit(index, beat_position, sample_rate, profile["snare_decay"]) * profile["snare"] * drum_energy if beat in profile["snare_beats"] else 0.0
            hat_position = index % max(1, beat_frames // profile["hat_rate"])
            hat = noise_hit(index + 19, hat_position, sample_rate, 0.018) * profile["hat"] * section_mix["hats"] * (0.45 + vocal_activity * 0.55)
            fill = arrangement_fill(index, beat_position, beat_frames, section_bar, section["role"], sample_rate, profile) * drum_energy

            groove = pad + bass + lead + guitar + kick + snare + hat + fill
            envelope = min(1.0, index / fade_in) * min(1.0, (total_frames - index) / fade_out)
            width = profile["width"] * math.sin(2 * math.pi * profile["pan_rate"] * t)
            left = clamp_audio(groove * (1.0 - width * 0.22) * envelope)
            right = clamp_audio(groove * (1.0 + width * 0.22) * envelope)
            wav.writeframesraw(struct.pack("<h", int(left * 32767)) + struct.pack("<h", int(right * 32767)))


def arrangement_sections(seconds: float) -> list[dict[str, float | int | str]]:
    duration = max(8.0, float(seconds))
    intro = min(10.0, max(4.0, duration * 0.08))
    outro = min(12.0, max(4.0, duration * 0.08))
    cursor = 0.0
    sections: list[dict[str, float | int | str]] = []

    def add(name: str, role: str, length: float) -> None:
        nonlocal cursor
        if length <= 0.5:
            return
        start = cursor
        end = min(duration, cursor + length)
        sections.append({"name": name, "role": role, "start": start, "end": end, "index": len(sections)})
        cursor = end

    add("Intro", "intro", intro)
    remaining = max(0.0, duration - intro - outro)
    cycle = [
        ("Verse 1", "verse", 24.0),
        ("Chorus", "chorus", 22.0),
        ("Verse 2", "verse", 24.0),
        ("Chorus 2", "chorus", 22.0),
        ("Bridge", "bridge", 18.0),
        ("Final Chorus", "final_chorus", 24.0),
    ]
    cycle_index = 0
    while remaining > 0.5:
        name, role, preferred = cycle[cycle_index % len(cycle)]
        length = min(preferred, remaining)
        add(name, role, length)
        remaining -= length
        cycle_index += 1
    add("Outro", "outro", duration - cursor)
    if sections:
        sections[-1]["end"] = duration
    return sections


def arrangement_section_at(sections: list[dict[str, float | int | str]], t: float) -> dict[str, float | int | str]:
    for section in sections:
        if float(section["start"]) <= t < float(section["end"]):
            return section
    return sections[-1]


def arrangement_section_mix(role: str) -> dict[str, float]:
    mixes = {
        "intro": {"pad": 0.8, "bass": 0.35, "lead": 0.2, "guitar": 0.45, "drums": 0.2, "hats": 0.35},
        "verse": {"pad": 0.95, "bass": 0.78, "lead": 0.38, "guitar": 0.78, "drums": 0.74, "hats": 0.78},
        "chorus": {"pad": 1.18, "bass": 1.0, "lead": 0.55, "guitar": 1.12, "drums": 1.08, "hats": 1.0},
        "bridge": {"pad": 0.82, "bass": 0.6, "lead": 0.28, "guitar": 0.58, "drums": 0.46, "hats": 0.5},
        "final_chorus": {"pad": 1.22, "bass": 1.05, "lead": 0.62, "guitar": 1.18, "drums": 1.15, "hats": 1.08},
        "outro": {"pad": 0.72, "bass": 0.42, "lead": 0.2, "guitar": 0.38, "drums": 0.24, "hats": 0.3},
    }
    return mixes.get(role, mixes["verse"])


def arranged_section_roots(roots: list[float], section_index: int, role: str) -> list[float]:
    if not roots:
        return [220.0]
    rotation = section_index % len(roots)
    arranged = roots[rotation:] + roots[:rotation]
    if role == "bridge":
        return [value * 1.125 for value in arranged]
    if role == "final_chorus":
        return [value * (2.0 if index == 0 else 1.0) for index, value in enumerate(arranged)]
    return arranged


def arranged_section_chord(chord: list[float], role: str, section_bar: int) -> list[float]:
    if role == "bridge" and section_bar % 4 >= 2:
        return [1.0, 1.2, 1.5, 1.887]
    if role in {"chorus", "final_chorus"} and section_bar % 8 >= 4:
        return [1.0, 1.25, 1.498, 1.875]
    return chord


def bass_motion_ratio(beat: int, section_bar: int, role: str, bass_walk: float) -> float:
    if role in {"chorus", "final_chorus"}:
        pattern = [1.0, bass_walk, 1.5, bass_walk]
    elif role == "bridge":
        pattern = [1.0, 1.125, bass_walk, 0.875]
    else:
        pattern = [1.0, 1.0, bass_walk, 1.125 if section_bar % 4 == 3 else 1.0]
    return pattern[beat % len(pattern)]


def section_strum_rate(base_rate: int, role: str, section_bar: int) -> int:
    if role in {"chorus", "final_chorus"}:
        return max(base_rate, 4)
    if role == "bridge" and section_bar % 2 == 1:
        return 1
    return max(1, base_rate)


def arrangement_fill(index: int, beat_position: int, beat_frames: int, section_bar: int, role: str, sample_rate: int, profile: dict[str, Any]) -> float:
    if role in {"intro", "outro"}:
        return 0.0
    is_fill_bar = section_bar % 8 == 7 or (role in {"chorus", "final_chorus"} and section_bar % 4 == 3)
    if not is_fill_bar:
        return 0.0
    beat = (index // beat_frames) % 4
    if beat < 2:
        return 0.0
    position = beat_position % max(1, beat_frames // 2)
    snare = noise_hit(index + 101, position, sample_rate, 0.045) * float(profile["snare"]) * 0.85
    tom = drum_hit(position, sample_rate, 0.09, 96.0 + (beat * 18.0)) * float(profile["kick"]) * 0.28
    return snare + tom


def soft_sine(frequency: float, t: float, shape: float) -> float:
    base = math.sin(2 * math.pi * frequency * t)
    overtone = math.sin(2 * math.pi * frequency * 2 * t) * 0.22
    return (base * (1 - shape * 0.25)) + (overtone * shape)


def guitar_strum(frequency: float, t: float, position: int, length: int, sample_rate: int, brightness: float) -> float:
    envelope = pulse_envelope(position, length, 0.72)
    shimmer = math.sin(2 * math.pi * frequency * t)
    shimmer += math.sin(2 * math.pi * frequency * 2.01 * t) * 0.42
    shimmer += math.sin(2 * math.pi * frequency * 3.02 * t) * 0.22
    pick = noise_hit(int(frequency * 11), position, sample_rate, 0.018) * 0.16
    return math.tanh((shimmer * (0.65 + brightness * 0.35) + pick) * 1.8) * envelope


def pulse_envelope(position: int, length: int, release: float) -> float:
    if length <= 0:
        return 0.0
    phase = position / length
    if phase < 0.08:
        return phase / 0.08
    return max(0.0, 1.0 - ((phase - 0.08) / max(0.01, release)))


def drum_hit(position: int, sample_rate: int, decay: float, frequency: float) -> float:
    age = position / sample_rate
    return math.sin(2 * math.pi * frequency * age) * math.exp(-age / decay)


def noise_hit(seed: int, position: int, sample_rate: int, decay: float) -> float:
    age = position / sample_rate
    value = math.sin(seed * 12.9898 + position * 78.233) * 43758.5453
    noise = (value - math.floor(value)) * 2 - 1
    return noise * math.exp(-age / decay)


def clamp_audio(value: float) -> float:
    return max(-0.92, min(0.92, value))


def vocal_activity_at_second(timing: dict[str, float] | None, second: int) -> float:
    activity = timing.get("activity_map") if timing else None
    if not isinstance(activity, dict):
        return 0.75
    values = [float(value) for value in activity.values()]
    if not values:
        return 0.75
    current = float(activity.get(str(second), sum(values) / len(values)))
    low = min(values)
    high = max(values)
    if high <= low:
        return 0.75
    return max(0.0, min(1.0, (current - low) / (high - low)))


def genre_profile(genre: Genre) -> dict[str, float | list[float]]:
    profile = timed_genre_profile(genre, None)
    return {
        "bpm": profile["bpm"],
        "tone": profile["pad"],
        "sub": profile["bass"],
        "kick": profile["kick"],
        "notes": profile["roots"],
    }


def arranged_genre_profile(genre: Genre) -> dict[str, float | list[float] | tuple[int, ...]]:
    profiles: dict[Genre, dict[str, float | list[float] | tuple[int, ...]]] = {
        Genre.lofi: {"bpm": 74, "pad": 0.115, "bass": 0.085, "lead_level": 0.032, "guitar": 0.032, "guitar_rate": 2, "guitar_brightness": 0.42, "kick": 0.15, "snare": 0.026, "hat": 0.014, "width": 0.78, "pan_rate": 0.045, "pad_shape": 0.68, "bass_walk": 1.125, "kick_decay": 0.12, "snare_decay": 0.05, "hat_rate": 2, "roots": [220.0, 246.94, 261.63, 196.0], "chord": [1.0, 1.189, 1.498, 1.782], "lead": [1.0, 1.125, 1.189, 1.498], "kick_beats": (0, 2), "snare_beats": (1, 3)},
        Genre.piano: {"bpm": 72, "pad": 0.16, "bass": 0.04, "lead_level": 0.025, "kick": 0.025, "snare": 0.008, "hat": 0.004, "width": 0.6, "pan_rate": 0.03, "pad_shape": 0.14, "bass_walk": 1.25, "kick_decay": 0.08, "snare_decay": 0.035, "hat_rate": 1, "roots": [261.63, 329.63, 392.0, 349.23], "chord": [1.0, 1.25, 1.498, 1.875], "lead": [1.0, 1.25, 1.498, 2.0], "kick_beats": (0,), "snare_beats": (2,)},
        Genre.pop: {"bpm": 112, "pad": 0.10, "bass": 0.105, "lead_level": 0.038, "guitar": 0.07, "guitar_rate": 4, "guitar_brightness": 0.7, "kick": 0.24, "snare": 0.052, "hat": 0.026, "width": 0.64, "pan_rate": 0.08, "pad_shape": 0.38, "bass_walk": 1.125, "kick_decay": 0.075, "snare_decay": 0.04, "hat_rate": 2, "roots": [261.63, 392.0, 440.0, 329.63], "chord": [1.0, 1.25, 1.498], "lead": [1.0, 1.125, 1.25, 1.498], "kick_beats": (0, 1, 2, 3), "snare_beats": (1, 3)},
        Genre.rock: {"bpm": 124, "pad": 0.075, "bass": 0.165, "lead_level": 0.026, "guitar": 0.18, "guitar_rate": 2, "guitar_brightness": 0.94, "kick": 0.32, "snare": 0.09, "hat": 0.038, "width": 0.56, "pan_rate": 0.055, "pad_shape": 0.82, "bass_walk": 1.189, "kick_decay": 0.075, "snare_decay": 0.05, "hat_rate": 2, "roots": [164.81, 196.0, 220.0, 146.83], "chord": [1.0, 1.189, 1.498], "lead": [1.0, 1.189, 1.334, 1.498], "kick_beats": (0, 2), "snare_beats": (1, 3)},
        Genre.rnb: {"bpm": 78, "pad": 0.145, "bass": 0.17, "lead_level": 0.028, "guitar": 0.045, "guitar_rate": 2, "guitar_brightness": 0.54, "kick": 0.14, "snare": 0.035, "hat": 0.014, "width": 0.82, "pan_rate": 0.04, "pad_shape": 0.6, "bass_walk": 1.125, "kick_decay": 0.13, "snare_decay": 0.06, "hat_rate": 2, "roots": [220.0, 277.18, 329.63, 246.94], "chord": [1.0, 1.189, 1.498, 1.782], "lead": [1.0, 1.125, 1.334, 1.498], "kick_beats": (0, 2), "snare_beats": (1, 3)},
        Genre.hiphop: {"bpm": 146, "pad": 0.075, "bass": 0.22, "lead_level": 0.025, "kick": 0.25, "snare": 0.052, "hat": 0.04, "width": 0.48, "pan_rate": 0.055, "pad_shape": 0.72, "bass_walk": 1.189, "kick_decay": 0.14, "snare_decay": 0.045, "hat_rate": 4, "roots": [110.0, 130.81, 146.83, 98.0], "chord": [1.0, 1.189, 1.498], "lead": [1.0, 1.125, 1.189, 1.498], "kick_beats": (0, 2, 3), "snare_beats": (1, 3)},
        Genre.acoustic: {"bpm": 82, "pad": 0.105, "bass": 0.06, "lead_level": 0.018, "guitar": 0.135, "guitar_rate": 4, "guitar_brightness": 0.62, "kick": 0.06, "snare": 0.018, "hat": 0.012, "width": 0.72, "pan_rate": 0.04, "pad_shape": 0.22, "bass_walk": 1.25, "kick_decay": 0.08, "snare_decay": 0.035, "hat_rate": 2, "roots": [196.0, 246.94, 293.66, 220.0], "chord": [1.0, 1.25, 1.498, 1.875], "lead": [1.0, 1.125, 1.25, 1.498], "kick_beats": (0,), "snare_beats": (2,)},
        Genre.cinematic: {"bpm": 68, "pad": 0.13, "bass": 0.075, "lead_level": 0.006, "kick": 0.045, "snare": 0.006, "hat": 0.0, "width": 0.86, "pan_rate": 0.014, "pad_shape": 0.78, "bass_walk": 1.189, "kick_decay": 0.24, "snare_decay": 0.08, "hat_rate": 1, "roots": [130.81, 196.0, 174.61, 146.83], "chord": [1.0, 1.189, 1.498, 2.0], "lead": [1.0, 1.189, 1.498, 2.0], "kick_beats": (0,), "snare_beats": (3,)},
    }
    return profiles[genre]


def timed_genre_profile(genre: Genre, timing: dict[str, float] | None) -> dict[str, float | list[float] | tuple[int, ...]]:
    profile = dict(arranged_genre_profile(genre))
    detected = coerce_float((timing or {}).get("production_bpm") or ((timing or {}).get("tempo_bpm") if timing else None))
    if not detected:
        return profile

    base = float(profile["bpm"])
    candidates = [detected, detected / 2, detected * 2]
    usable = [candidate for candidate in candidates if 62 <= candidate <= 164]
    if not usable:
        return profile
    closest = min(usable, key=lambda candidate: abs(candidate - base))
    profile["bpm"] = round((base * 0.45) + (closest * 0.55), 2)
    return profile


def build_worker(repository: InMemoryJobRepository):
    if settings.worker_backend == "mock":
        return MockAIWorker(repository)
    if settings.worker_backend == "mvp_audio":
        return MvpAudioWorker(repository)
    raise ValueError(f"Unsupported SKARLY_WORKER_BACKEND: {settings.worker_backend}")
