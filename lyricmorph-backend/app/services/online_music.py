from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import base64
import hashlib
import json
import re
from typing import Any, Callable
from uuid import uuid4

from ..audio_validation import validate_audio_file
from ..generators import ace_step, procedural_v2
from ..mixer import mix_vocal_with_backing
from ..models import (
    AudioUploadResponse,
    MusicCompositionPlan,
    MusicSourcePreparation,
    MusicToMusicRequest,
    OnlineGenerationCandidate,
    OnlineGenerationDiagnostics,
    OnlineGenerationResponse,
    QualityReport,
    RegenerateMusicRequest,
    VocalAnalysisReport,
    VocalToMusicRequest,
)
from . import music_source, safe_paths
from .music_transform_quality import assess_transformation
from .vocal_analysis import analyze_vocal_audio

ProviderOrder = list[str]
UploadLookup = Callable[[str], AudioUploadResponse | None]
UrlForPath = Callable[[str | None], str | None]

FAMOUS_REFERENCE_REPLACEMENTS = {
    r"\btum\s+hi\s+ho\b": "emotional Hindi romantic Bollywood ballad with piano-led cinematic arrangement",
    r"\barijit\s+singh\b": "emotional Hindi playback-style phrasing",
    r"\batif\s+aslam\b": "emotional South Asian pop ballad phrasing",
    r"\bsonu\s+nigam\b": "classic Hindi playback-style phrasing",
    r"\bshreya\s+ghoshal\b": "melodic Hindi playback-style phrasing",
}

PROVIDER_DISPLAY_NAMES = {
    "ace_step": "Local ACE-Step",
    "elevenlabs": "ElevenLabs Music",
    "lyria": "Google Lyria 3 Pro",
    "local_fallback": "local_fallback",
}


@dataclass(frozen=True)
class ProviderGenerationResult:
    success: bool
    provider_name: str
    output_path: str | None = None
    error_message: str | None = None
    logs: list[str] = field(default_factory=list)
    suggested_fix: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class MusicProvider:
    provider_name = "provider"

    def generate(
        self,
        *,
        plan: MusicCompositionPlan,
        candidate_id: str,
        settings: Any,
        output_format: str,
        reference_audio_path: str | None = None,
    ) -> ProviderGenerationResult:
        raise NotImplementedError


class ElevenMusicProvider(MusicProvider):
    provider_name = "elevenlabs"

    def generate(
        self,
        *,
        plan: MusicCompositionPlan,
        candidate_id: str,
        settings: Any,
        output_format: str,
        reference_audio_path: str | None = None,
    ) -> ProviderGenerationResult:
        if not getattr(settings, "online_music_enabled", True):
            return _provider_failure(
                self.provider_name,
                "Online music generation is disabled.",
                "Set ONLINE_MUSIC_ENABLED=true or use local_fallback.",
            )
        api_key = getattr(settings, "elevenlabs_api_key", None)
        if not api_key:
            return _provider_failure(
                self.provider_name,
                "ELEVENLABS_API_KEY is not configured.",
                "Set ELEVENLABS_API_KEY to use ElevenLabs Music, or keep local_fallback for debug previews.",
            )

        try:
            import requests

            output_dir = safe_paths.resolve_output_dir(getattr(settings, "online_music_output_dir", "outputs/online_music"))
            output_dir.mkdir(parents=True, exist_ok=True)
            suffix = "mp3"
            output_path = output_dir / f"{safe_paths.sanitize_filename(candidate_id)}_elevenlabs.{suffix}"
            response = requests.post(
                "https://api.elevenlabs.io/v1/music/stream",
                headers={"xi-api-key": api_key, "Content-Type": "application/json"},
                params={"output_format": "mp3_44100_128" if output_format == "mp3" else "pcm_44100"},
                json=build_elevenlabs_payload(plan, settings),
                timeout=float(getattr(settings, "online_music_timeout_seconds", 900)),
            )
            if response.status_code >= 400:
                return _provider_failure(
                    self.provider_name,
                    f"ElevenLabs Music request failed with HTTP {response.status_code}: {response.text[:500]}",
                    "Check ELEVENLABS_API_KEY, Music API access, quota, and prompt policy details.",
                    logs=[f"HTTP {response.status_code} from ElevenLabs Music stream endpoint."],
                )
            output_path.write_bytes(response.content)
            return ProviderGenerationResult(
                success=True,
                provider_name=self.provider_name,
                output_path=str(output_path),
                logs=[
                    "ElevenLabs Music stream request completed.",
                    f"Saved generated instrumental candidate: {output_path}",
                ],
            )
        except Exception as exc:
            return _provider_failure(
                self.provider_name,
                f"ElevenLabs Music adapter failed: {exc}",
                "Check network connectivity, ELEVENLABS_API_KEY, and provider availability.",
            )


class LyriaProvider(MusicProvider):
    provider_name = "lyria"

    def generate(
        self,
        *,
        plan: MusicCompositionPlan,
        candidate_id: str,
        settings: Any,
        output_format: str,
        reference_audio_path: str | None = None,
    ) -> ProviderGenerationResult:
        if not getattr(settings, "online_music_enabled", True):
            return _provider_failure(
                self.provider_name,
                "Online music generation is disabled.",
                "Set ONLINE_MUSIC_ENABLED=true or use local_fallback.",
            )
        api_key = getattr(settings, "gemini_api_key", None)
        if not api_key:
            return _provider_failure(
                self.provider_name,
                "GEMINI_API_KEY is not configured.",
                "Set GEMINI_API_KEY to use Google Lyria 3 Pro, or keep local_fallback for debug previews.",
            )

        try:
            import requests

            output_dir = safe_paths.resolve_output_dir(getattr(settings, "online_music_output_dir", "outputs/online_music"))
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = output_dir / f"{safe_paths.sanitize_filename(candidate_id)}_lyria.mp3"
            response = requests.post(
                "https://generativelanguage.googleapis.com/v1beta/interactions",
                headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
                json=build_lyria_payload(plan, settings, output_format),
                timeout=float(getattr(settings, "online_music_timeout_seconds", 900)),
            )
            if response.status_code >= 400:
                return _provider_failure(
                    self.provider_name,
                    f"Lyria request failed with HTTP {response.status_code}: {response.text[:500]}",
                    "Check GEMINI_API_KEY, Lyria access, region availability, quota, and prompt policy details.",
                    logs=[f"HTTP {response.status_code} from Google Interactions API."],
                )
            audio_bytes = _extract_lyria_audio_bytes(response)
            if not audio_bytes:
                return _provider_failure(
                    self.provider_name,
                    "Lyria response did not contain an audio block.",
                    "Inspect the response payload and verify the Lyria model has audio output enabled for your account.",
                    logs=[response.text[:1000]],
                )
            output_path.write_bytes(audio_bytes)
            return ProviderGenerationResult(
                success=True,
                provider_name=self.provider_name,
                output_path=str(output_path),
                logs=[
                    "Lyria Interactions API request completed.",
                    f"Saved generated instrumental candidate: {output_path}",
                ],
            )
        except Exception as exc:
            return _provider_failure(
                self.provider_name,
                f"Lyria adapter failed: {exc}",
                "Check network connectivity, GEMINI_API_KEY, and provider availability.",
            )


class LocalFallbackProvider(MusicProvider):
    provider_name = "local_fallback"

    def generate(
        self,
        *,
        plan: MusicCompositionPlan,
        candidate_id: str,
        settings: Any,
        output_format: str,
        reference_audio_path: str | None = None,
    ) -> ProviderGenerationResult:
        result = procedural_v2.generate_backing(
            job_id=f"{candidate_id}_procedural",
            output_dir=getattr(settings, "procedural_output_dir", "outputs/procedural_v2"),
            duration_seconds=int(plan.duration_seconds or 90),
            bpm=int(plan.bpm or 88),
            key=plan.key,
            genre=plan.genre,
            production_style=plan.production_style,
            arrangement_style=plan.arrangement_style,
            instruments=plan.instruments,
            mood_tags=plan.mood_tags,
            sample_rate=44100,
        )
        if not result.success:
            return _provider_failure(
                self.provider_name,
                result.error_message or "procedural_v2 fallback did not produce audio.",
                result.suggested_fix or "Check procedural fallback output permissions.",
                logs=list(result.logs or []),
            )
        return ProviderGenerationResult(
            success=True,
            provider_name=self.provider_name,
            output_path=result.output_path,
            logs=[
                "Online provider unavailable or failed; generated procedural_v2 fallback.",
                *list(result.logs or []),
            ],
            suggested_fix="Use ElevenLabs or Lyria API keys for product-quality online generation.",
        )


class LocalAceStepProvider(MusicProvider):
    provider_name = "ace_step"

    def generate(
        self,
        *,
        plan: MusicCompositionPlan,
        candidate_id: str,
        settings: Any,
        output_format: str,
        reference_audio_path: str | None = None,
    ) -> ProviderGenerationResult:
        if plan.mode != "music_to_music" or not reference_audio_path:
            return _provider_failure(
                self.provider_name,
                "ACE-Step reference conditioning requires a music-to-music reference track.",
                "Upload a reference track or choose another provider.",
            )
        result = ace_step.transform_reference_audio(
            source_audio_path=reference_audio_path,
            prompt=plan.provider_prompt,
            negative_prompt=plan.negative_prompt,
            output_dir=getattr(settings, "online_music_output_dir", "outputs/online_music"),
            job_id=candidate_id,
            timeout_seconds=int(getattr(settings, "ace_step_timeout_seconds", 900)),
            base_url=getattr(settings, "ace_step_base_url", "http://127.0.0.1:8001"),
            api_key=getattr(settings, "ace_step_api_key", None),
            model=getattr(settings, "ace_step_model", None),
            inference_steps=int(getattr(settings, "ace_step_infer_step", 8)),
            guidance_scale=float(getattr(settings, "ace_step_guidance_scale", 1.0)),
            poll_interval_seconds=float(getattr(settings, "ace_step_poll_interval_seconds", 2.0)),
            reference_strength=float(plan.reference_strength or 0.35),
            bpm=plan.bpm,
            key=plan.key,
            duration_seconds=plan.duration_seconds,
        )
        if not result.success:
            return _provider_failure(
                self.provider_name,
                result.error_message or "ACE-Step did not transform the reference track.",
                result.suggested_fix or "Confirm the local ACE-Step API is running.",
                logs=list(result.logs or []),
            )
        return ProviderGenerationResult(
            success=True,
            provider_name=self.provider_name,
            output_path=result.output_path,
            logs=list(result.logs or []),
            metadata=dict(result.metadata or {}),
        )


def run_vocal_to_music(
    request: VocalToMusicRequest,
    *,
    job_id: str,
    settings: Any,
    upload_lookup: UploadLookup,
    url_for_path: UrlForPath,
) -> OnlineGenerationResponse:
    if _rights_required(settings, request.rights_confirmed):
        return _rights_required_response(job_id, "vocal_to_music", upload_id=request.upload_id)

    upload = upload_lookup(request.upload_id)
    if upload is None:
        return _failed_response(
            job_id=job_id,
            mode="vocal_to_music",
            status="failed",
            message="Uploaded vocal was not found.",
            diagnostics=OnlineGenerationDiagnostics(
                status="failed",
                failed_step="upload_lookup",
                rights_confirmed=request.rights_confirmed,
                error_message="upload_id was not found.",
                suggested_fix="Upload the vocal using /uploads/audio, then call /v2/vocal-to-music with that upload_id.",
            ),
            upload_id=request.upload_id,
        )

    analysis = analyze_vocal_audio(
        upload.original_path,
        upload_id=upload.upload_id,
        normalized_output_dir=getattr(settings, "uploads_dir", "outputs/uploads"),
        url_for_path=url_for_path,
        expected_duration_seconds=request.duration_seconds,
    )
    if not _analysis_usable(analysis):
        return _failed_response(
            job_id=job_id,
            mode="vocal_to_music",
            status="analysis_failed",
            message="Vocal analysis failed. Generation was not attempted.",
            diagnostics=OnlineGenerationDiagnostics(
                status="analysis_failed",
                failed_step="vocal_analysis",
                rights_confirmed=request.rights_confirmed,
                error_message=_analysis_failure_summary(analysis),
                suggested_fix="Upload a clear vocal-only WAV or MP3 with audible singing.",
                last_logs=analysis.warnings,
            ),
            upload_id=request.upload_id,
            analysis=analysis,
        )

    plan = build_composition_plan(
        request,
        analysis=analysis,
        mode="vocal_to_music",
        provider_order=_provider_order(request.provider_preference, settings),
    )
    candidates = _generate_candidates(
        plan=plan,
        vocal_path=analysis.normalized_wav_path or upload.original_path,
        reference_audio_path=None,
        settings=settings,
        url_for_path=url_for_path,
        candidate_count=_candidate_count(request.candidate_count, settings),
        output_format=request.output_format,
        provider_order=plan.provider_preferences,
        mix_vocal=True,
        root_job_id=job_id,
    )
    return _response_from_candidates(
        job_id=job_id,
        mode="vocal_to_music",
        upload_id=request.upload_id,
        analysis=analysis,
        plan=plan,
        candidates=candidates,
        rights_confirmed=request.rights_confirmed,
    )


def run_music_to_music(
    request: MusicToMusicRequest,
    *,
    job_id: str,
    settings: Any,
    upload_lookup: UploadLookup,
    url_for_path: UrlForPath,
) -> OnlineGenerationResponse:
    if _rights_required(settings, request.rights_confirmed):
        return _rights_required_response(job_id, "music_to_music", reference_upload_id=request.reference_upload_id)

    reference = upload_lookup(request.reference_upload_id)
    if reference is None:
        return _failed_response(
            job_id=job_id,
            mode="music_to_music",
            status="failed",
            message="Reference audio was not found.",
            diagnostics=OnlineGenerationDiagnostics(
                status="failed",
                failed_step="reference_upload_lookup",
                rights_confirmed=request.rights_confirmed,
                error_message="reference_upload_id was not found.",
                suggested_fix="Upload the reference using /uploads/audio, then call /v2/music-to-music.",
            ),
            reference_upload_id=request.reference_upload_id,
        )

    source_analysis = analyze_vocal_audio(
        reference.original_path,
        upload_id=reference.upload_id,
        normalized_output_dir=getattr(settings, "uploads_dir", "outputs/uploads"),
        url_for_path=url_for_path,
        expected_duration_seconds=request.duration_seconds,
    )
    if not source_analysis.quality_report or not source_analysis.quality_report.audio_exists:
        return _failed_response(
            job_id=job_id,
            mode="music_to_music",
            status="analysis_failed",
            message="Reference analysis failed. Generation was not attempted.",
            diagnostics=OnlineGenerationDiagnostics(
                status="analysis_failed",
                failed_step="reference_analysis",
                rights_confirmed=request.rights_confirmed,
                error_message=_analysis_failure_summary(source_analysis),
                suggested_fix="Upload a decodable reference WAV or MP3.",
                last_logs=source_analysis.warnings,
            ),
            reference_upload_id=request.reference_upload_id,
            reference_analysis=source_analysis,
        )

    preserve_vocal = bool(request.preserve_original_vocal or request.vocal_upload_id)
    source_preparation = music_source.prepare_music_source(
        source_audio_path=source_analysis.normalized_wav_path or reference.original_path,
        requested_mode=request.source_mode,
        preserve_original_vocal=preserve_vocal,
        job_id=job_id,
        settings=settings,
        url_for_path=url_for_path,
    )
    if not source_preparation.instrumental_audio_path:
        return _failed_response(
            job_id=job_id,
            mode="music_to_music",
            status="separation_failed",
            message="The mixed source could not be prepared safely. Generation was not attempted.",
            diagnostics=OnlineGenerationDiagnostics(
                status="separation_failed",
                failed_step="source_separation",
                rights_confirmed=request.rights_confirmed,
                error_message="Automatic source preparation did not produce a clean instrumental stem.",
                suggested_fix="Confirm Demucs is available, retry, or choose instrumental mode only when the upload has no vocals.",
                last_logs=source_preparation.warnings,
            ),
            reference_upload_id=request.reference_upload_id,
            reference_analysis=source_analysis,
            source_preparation=source_preparation,
        )

    prepared_reference_path = source_preparation.instrumental_audio_path
    reference_analysis = (
        source_analysis
        if Path(prepared_reference_path).resolve() == Path(source_analysis.normalized_wav_path or reference.original_path).resolve()
        else analyze_vocal_audio(
            prepared_reference_path,
            upload_id=f"{reference.upload_id}_instrumental",
            normalized_output_dir=getattr(settings, "uploads_dir", "outputs/uploads"),
            url_for_path=url_for_path,
            expected_duration_seconds=request.duration_seconds,
        )
    )
    if not reference_analysis.quality_report or not reference_analysis.quality_report.passed:
        return _failed_response(
            job_id=job_id,
            mode="music_to_music",
            status="analysis_failed",
            message="Prepared instrumental analysis failed. Generation was not attempted.",
            diagnostics=OnlineGenerationDiagnostics(
                status="analysis_failed",
                failed_step="prepared_instrumental_analysis",
                rights_confirmed=request.rights_confirmed,
                error_message=_analysis_failure_summary(reference_analysis),
                suggested_fix="Review the separated instrumental stem and retry the upload.",
                last_logs=reference_analysis.warnings,
            ),
            reference_upload_id=request.reference_upload_id,
            reference_analysis=reference_analysis,
            source_preparation=source_preparation,
        )

    vocal_upload = upload_lookup(request.vocal_upload_id) if request.vocal_upload_id else None
    vocal_analysis: VocalAnalysisReport | None = None
    vocal_path: str | None = None
    if vocal_upload:
        vocal_analysis = analyze_vocal_audio(
            vocal_upload.original_path,
            upload_id=vocal_upload.upload_id,
            normalized_output_dir=getattr(settings, "uploads_dir", "outputs/uploads"),
            url_for_path=url_for_path,
            expected_duration_seconds=request.duration_seconds,
        )
        if _analysis_usable(vocal_analysis):
            vocal_path = vocal_analysis.normalized_wav_path or vocal_upload.original_path
            source_preparation = source_preparation.model_copy(
                update={
                    "vocal_detected": True,
                    "vocal_preserved": True,
                    "vocal_audio_path": vocal_path,
                    "vocal_audio_url": url_for_path(vocal_path),
                }
            )
    elif preserve_vocal and source_preparation.vocal_audio_path:
        vocal_analysis = analyze_vocal_audio(
            source_preparation.vocal_audio_path,
            upload_id=f"{reference.upload_id}_vocal",
            normalized_output_dir=getattr(settings, "uploads_dir", "outputs/uploads"),
            url_for_path=url_for_path,
            expected_duration_seconds=request.duration_seconds,
        )
        if _analysis_usable(vocal_analysis):
            vocal_path = vocal_analysis.normalized_wav_path or source_preparation.vocal_audio_path
        else:
            source_preparation = source_preparation.model_copy(
                update={
                    "vocal_preserved": False,
                    "warnings": _dedupe([*source_preparation.warnings, "Separated vocal was not usable, so output will be instrumental-only."]),
                }
            )

    plan = build_composition_plan(
        request,
        analysis=vocal_analysis or reference_analysis,
        reference_analysis=reference_analysis,
        mode="music_to_music",
        edit_instruction=request.style_instruction,
        provider_order=_provider_order(request.provider_preference, settings, reference_conditioned=True),
    )
    candidates = _generate_candidates(
        plan=plan,
        vocal_path=vocal_path,
        reference_audio_path=reference_analysis.normalized_wav_path or prepared_reference_path,
        settings=settings,
        url_for_path=url_for_path,
        candidate_count=_candidate_count(request.candidate_count, settings),
        output_format=request.output_format,
        provider_order=plan.provider_preferences,
        mix_vocal=bool(vocal_path),
        root_job_id=job_id,
    )
    response = _response_from_candidates(
        job_id=job_id,
        mode="music_to_music",
        reference_upload_id=request.reference_upload_id,
        vocal_upload_id=request.vocal_upload_id,
        analysis=vocal_analysis,
        reference_analysis=reference_analysis,
        plan=plan,
        candidates=candidates,
        rights_confirmed=request.rights_confirmed,
        source_preparation=source_preparation,
    )
    if request.vocal_upload_id and not vocal_path:
        if response.diagnostics:
            response.diagnostics.last_logs.append("Optional vocal upload was not usable, so candidates are backing-only.")
        response.message = f"{response.message or ''} Optional vocal mix was skipped because the vocal upload was not usable.".strip()
    return response


def regenerate_online_job(
    *,
    previous_response: OnlineGenerationResponse,
    request: RegenerateMusicRequest,
    settings: Any,
    upload_lookup: UploadLookup,
    url_for_path: UrlForPath,
    job_id: str,
) -> OnlineGenerationResponse:
    if _rights_required(settings, request.rights_confirmed):
        return _rights_required_response(
            job_id,
            f"{previous_response.mode}_regenerate",
            upload_id=previous_response.upload_id,
            reference_upload_id=previous_response.reference_upload_id,
            vocal_upload_id=previous_response.vocal_upload_id,
        )
    analysis = previous_response.analysis or previous_response.reference_analysis
    if analysis is None:
        return _failed_response(
            job_id=job_id,
            mode=f"{previous_response.mode}_regenerate",
            status="analysis_failed",
            message="Previous job does not contain analysis data for regeneration.",
            diagnostics=OnlineGenerationDiagnostics(
                status="analysis_failed",
                failed_step="regeneration_context",
                error_message="No analysis report was stored on the previous job.",
                suggested_fix="Run /v2/vocal-to-music or /v2/music-to-music again, then regenerate.",
            ),
        )

    plan = previous_response.composition_plan or build_composition_plan(
        VocalToMusicRequest(upload_id=previous_response.upload_id or "regenerate", rights_confirmed=True),
        analysis=analysis,
        mode=previous_response.mode,
    )
    updated_plan = plan.model_copy(
        update={
            "plan_id": f"plan_{uuid4().hex}",
            "provider_prompt": sanitize_generation_text(f"{plan.provider_prompt}\n\nRegeneration edit: {request.edit_instruction}"),
            "provider_preferences": _provider_order(
                request.provider_preference,
                settings,
                reference_conditioned=bool(previous_response.reference_upload_id),
            ),
            "reference_strength": request.reference_strength if request.reference_strength is not None else plan.reference_strength,
            "warnings": _dedupe([*plan.warnings, "Regenerated from previous candidate review instructions."]),
        }
    )

    vocal_path = None
    if (
        previous_response.source_preparation
        and previous_response.source_preparation.vocal_preserved
        and previous_response.source_preparation.vocal_audio_path
    ):
        vocal_path = previous_response.source_preparation.vocal_audio_path
    elif previous_response.upload_id:
        upload = upload_lookup(previous_response.upload_id)
        vocal_path = (analysis.normalized_wav_path or upload.original_path) if upload else analysis.normalized_wav_path
    elif previous_response.vocal_upload_id:
        upload = upload_lookup(previous_response.vocal_upload_id)
        vocal_path = (analysis.normalized_wav_path or upload.original_path) if upload else analysis.normalized_wav_path

    candidates = _generate_candidates(
        plan=updated_plan,
        vocal_path=vocal_path,
        reference_audio_path=_regeneration_reference_path(previous_response, upload_lookup),
        settings=settings,
        url_for_path=url_for_path,
        candidate_count=_candidate_count(request.candidate_count, settings),
        output_format="mp3",
        provider_order=updated_plan.provider_preferences,
        mix_vocal=bool(vocal_path),
        root_job_id=job_id,
    )
    return _response_from_candidates(
        job_id=job_id,
        mode=f"{previous_response.mode}_regenerate",
        upload_id=previous_response.upload_id,
        reference_upload_id=previous_response.reference_upload_id,
        vocal_upload_id=previous_response.vocal_upload_id,
        analysis=previous_response.analysis,
        reference_analysis=previous_response.reference_analysis,
        plan=updated_plan,
        candidates=candidates,
        rights_confirmed=request.rights_confirmed,
        source_preparation=previous_response.source_preparation,
    )


def build_composition_plan(
    request: VocalToMusicRequest | MusicToMusicRequest,
    *,
    analysis: VocalAnalysisReport,
    mode: str,
    reference_analysis: VocalAnalysisReport | None = None,
    edit_instruction: str | None = None,
    provider_order: ProviderOrder | None = None,
) -> MusicCompositionPlan:
    duration = int(
        request.duration_seconds
        or analysis.duration_seconds
        or (reference_analysis.duration_seconds if reference_analysis else 0)
        or 90
    )
    duration = max(3, min(duration, 600))
    bpm = int(request.bpm or analysis.estimated_bpm or (reference_analysis.estimated_bpm if reference_analysis else 0) or 88)
    bpm = max(40, min(bpm, 220))
    key = request.key or analysis.estimated_key or (reference_analysis.estimated_key if reference_analysis else None) or "A minor"
    production_style = request.production_style or _style_from_mood(request.mood_tags, getattr(request, "style_instruction", None))
    arrangement_style = request.arrangement_style or _arrangement_for_style(production_style, request.genre)
    instruments = _dedupe(request.instruments or _instruments_for_style(production_style, arrangement_style, request.genre))
    mood_tags = _dedupe(request.mood_tags or _moods_from_text(" ".join([request.lyrics or "", edit_instruction or ""])))
    if not mood_tags:
        mood_tags = ["emotional", "cinematic", "vocal-forward"]

    sections = analysis.section_candidates or _duration_sections(duration)
    section_text = "; ".join(
        f"{item.get('name', 'section')} {item.get('start_seconds', 0)}-{item.get('end_seconds', duration)}s"
        for item in sections[:8]
    )
    user_intent = sanitize_generation_text(edit_instruction or getattr(request, "style_instruction", "") or "")
    lyrics_note = sanitize_generation_text((request.lyrics or "").strip())
    mode_note = (
        "Create a fresh original instrumental transformation inspired only by broad mood, tempo, and arrangement energy."
        if mode == "music_to_music"
        else "Create an original instrumental backing track that follows the uploaded vocal's phrasing and emotional timing."
    )
    prompt_parts = [
        mode_note,
        f"Language context: {request.language}.",
        f"Genre: {request.genre or 'Pop'}. Production style: {production_style}. Arrangement style: {arrangement_style}.",
        f"Target BPM: {bpm}. Target key: {key}. Target duration: {duration} seconds.",
        f"Sections and phrase map: {section_text}. Keep the hook/mukhda energy clear and support phrase endings.",
        f"Instrumentation: {', '.join(instruments)}.",
        f"Mood curve: {', '.join(mood_tags)}.",
        "Make it vocal-forward, leaving space in the midrange for the uploaded lead vocal.",
        "Generate instrumental music only; do not create new lead vocals or copied lyrics.",
        "Create original melody, harmony, rhythm, and arrangement. Do not copy any existing song, melody, lyrics, arrangement, or artist voice.",
        "Use broad Indian/Bollywood production language only; do not imitate a named living artist.",
    ]
    if lyrics_note:
        prompt_parts.append(f"Lyric emotion to support without copying: {lyrics_note[:600]}.")
    if user_intent:
        prompt_parts.append(f"User direction: {user_intent[:600]}.")
    provider_prompt = sanitize_generation_text(" ".join(prompt_parts))[:4000]
    negative_prompt = (
        "No lead vocals, no artist imitation, no famous-song copying, no karaoke clone, no copyrighted melody reuse, "
        "no clipping, no silence, no muddy low end, no over-busy drums under the vocal."
    )
    warnings = []
    if request.send_source_audio_to_provider:
        warnings.append("Source-audio upload to providers is not enabled by default; this implementation sends derived analysis and prompts only.")
    if _contains_famous_reference((request.lyrics or "") + " " + user_intent):
        warnings.append("Famous song/artist references were translated into broad style language for originality.")

    return MusicCompositionPlan(
        plan_id=f"plan_{uuid4().hex}",
        mode=mode,
        provider_prompt=provider_prompt,
        negative_prompt=negative_prompt,
        bpm=bpm,
        key=key,
        duration_seconds=duration,
        genre=request.genre,
        production_style=production_style,
        arrangement_style=arrangement_style,
        mood_tags=mood_tags,
        instruments=instruments,
        sections=sections,
        mix_direction="vocal-forward, backing slightly below lead, gentle ducking under vocal phrases",
        provider_preferences=provider_order or ["elevenlabs", "lyria", "local_fallback"],
        reference_strength=(request.reference_strength if isinstance(request, MusicToMusicRequest) else None),
        warnings=warnings,
    )


def build_elevenlabs_payload(plan: MusicCompositionPlan, settings: Any) -> dict[str, Any]:
    length_ms = int(max(3, min(int(plan.duration_seconds or 90), 600)) * 1000)
    return {
        "prompt": plan.provider_prompt,
        "music_length_ms": length_ms,
        "model_id": getattr(settings, "elevenlabs_music_model", "music_v2"),
        "force_instrumental": True,
        "store_for_inpainting": False,
    }


def build_lyria_payload(plan: MusicCompositionPlan, settings: Any, output_format: str = "mp3") -> dict[str, Any]:
    prompt = plan.provider_prompt
    if plan.duration_seconds:
        prompt = f"{prompt} Create approximately {int(plan.duration_seconds)} seconds of music."
    payload: dict[str, Any] = {
        "model": getattr(settings, "lyria_pro_model", "lyria-3-pro-preview"),
        "input": prompt,
    }
    if output_format == "wav":
        payload["response_format"] = {"type": "audio"}
    return payload


def sanitize_generation_text(text: str | None) -> str:
    sanitized = str(text or "")
    for pattern, replacement in FAMOUS_REFERENCE_REPLACEMENTS.items():
        sanitized = re.sub(pattern, replacement, sanitized, flags=re.IGNORECASE)
    sanitized = re.sub(r"\bcopy\s+(?:the\s+)?(?:song|melody|voice|style)\b", "use broad original production direction", sanitized, flags=re.IGNORECASE)
    sanitized = re.sub(r"\bexactly\s+like\b", "in the broad style of", sanitized, flags=re.IGNORECASE)
    return sanitized.strip()


def _generate_candidates(
    *,
    plan: MusicCompositionPlan,
    vocal_path: str | None,
    reference_audio_path: str | None,
    settings: Any,
    url_for_path: UrlForPath,
    candidate_count: int,
    output_format: str,
    provider_order: ProviderOrder,
    mix_vocal: bool,
    root_job_id: str,
) -> list[OnlineGenerationCandidate]:
    providers = _providers_for_order(provider_order)
    candidates: list[OnlineGenerationCandidate] = []
    for index in range(1, candidate_count + 1):
        candidate_id = f"{safe_paths.sanitize_filename(root_job_id)}_c{index}"
        attempt_logs: list[str] = []
        candidate: OnlineGenerationCandidate | None = None
        for provider in providers:
            provider_kwargs: dict[str, Any] = {
                "plan": plan,
                "candidate_id": candidate_id,
                "settings": settings,
                "output_format": output_format,
            }
            if reference_audio_path:
                provider_kwargs["reference_audio_path"] = reference_audio_path
            result = provider.generate(
                **provider_kwargs,
            )
            attempt_logs.extend(f"{result.provider_name}: {line}" for line in result.logs)
            if not result.success:
                attempt_logs.append(f"{result.provider_name} failed: {result.error_message}")
                continue
            candidate = _candidate_from_provider_result(
                candidate_id=candidate_id,
                result=result,
                plan=plan,
                vocal_path=vocal_path,
                settings=settings,
                url_for_path=url_for_path,
                output_format=output_format,
                mix_vocal=mix_vocal,
                provider_order=provider_order,
                attempt_logs=attempt_logs,
                reference_audio_path=reference_audio_path,
            )
            break
        if candidate is None:
            candidate = OnlineGenerationCandidate(
                candidate_id=candidate_id,
                provider_name="none",
                status="failed",
                prompt=plan.provider_prompt,
                diagnostics=OnlineGenerationDiagnostics(
                    status="failed",
                    provider_order=provider_order,
                    failed_step="provider_generation",
                    error_message="All configured music providers failed.",
                    suggested_fix="Configure ELEVENLABS_API_KEY or GEMINI_API_KEY, or allow local_fallback.",
                    last_logs=attempt_logs[-40:],
                ),
                warnings=["All configured music providers failed."],
                score=-1.0,
            )
        candidates.append(candidate)
    return candidates


def _candidate_from_provider_result(
    *,
    candidate_id: str,
    result: ProviderGenerationResult,
    plan: MusicCompositionPlan,
    vocal_path: str | None,
    settings: Any,
    url_for_path: UrlForPath,
    output_format: str,
    mix_vocal: bool,
    provider_order: ProviderOrder,
    attempt_logs: list[str],
    reference_audio_path: str | None,
) -> OnlineGenerationCandidate:
    expected = int(plan.duration_seconds or 0) or None
    quality = validate_audio_file(
        result.output_path,
        expected_duration_seconds=expected,
        generator_name=result.provider_name,
        fallback_used=result.provider_name == "local_fallback",
    )
    warnings = [*quality.warnings, *quality.validation_errors]
    status = "generated" if quality.passed else "failed_validation"
    mix_quality: QualityReport | None = None
    mixed_preview_path = None
    final_wav_path = None
    final_mp3_path = None
    if quality.passed and mix_vocal and vocal_path:
        mix_result = mix_vocal_with_backing(
            vocal_path=vocal_path,
            backing_path=result.output_path or "",
            output_dir=getattr(settings, "mix_output_dir", "outputs/mixes"),
            job_id=f"{candidate_id}_{result.provider_name}",
            vocal_gain_db=float(getattr(settings, "mix_default_vocal_gain_db", 2.0)),
            backing_gain_db=float(getattr(settings, "mix_default_backing_gain_db", -3.0)),
            ducking_enabled=bool(getattr(settings, "mix_default_ducking_enabled", True)),
            ducking_amount=float(getattr(settings, "mix_default_ducking_amount", 0.35)),
            output_format=output_format,
            sample_rate=int(getattr(settings, "mix_sample_rate", 44100)),
        )
        mixed_preview_path = mix_result.preview_path
        final_wav_path = mix_result.final_wav_path
        final_mp3_path = mix_result.final_mp3_path
        mix_quality = (
            validate_audio_file(
                mix_result.preview_path or mix_result.final_wav_path,
                expected_duration_seconds=expected,
                generator_name="vocal_backing_mixer",
                fallback_used=result.provider_name == "local_fallback",
            )
            if mix_result.success
            else QualityReport(
                audio_exists=False,
                generator_name="vocal_backing_mixer",
                fallback_used=result.provider_name == "local_fallback",
                warnings=[mix_result.error_message or "Mix failed."],
                validation_errors=[mix_result.error_message or "Mix failed."],
                passed=False,
            )
        )
        warnings.extend(mix_result.warnings)
        if mix_quality and not mix_quality.passed:
            warnings.extend(mix_quality.validation_errors or mix_quality.warnings)
            status = "mix_failed"
        elif mix_result.success:
            status = "mixed"

    duration_close = _duration_close(quality.duration_seconds, plan.duration_seconds)
    if quality.passed and not duration_close:
        warnings.append("Generated duration is not close to the vocal target; review alignment before export.")
        status = "needs_review" if status in {"generated", "mixed"} else status
    if result.provider_name == "local_fallback":
        warnings.append("local_fallback used procedural_v2; quality is for preview/debug, not final online generation.")

    transformation_quality = None
    if plan.mode == "music_to_music" and quality.passed and reference_audio_path and result.output_path:
        transformation_quality = assess_transformation(
            source_audio_path=reference_audio_path,
            output_audio_path=result.output_path,
            expected_duration_seconds=expected,
            candidate_id=candidate_id,
            settings=settings,
            url_for_path=url_for_path,
        )
        warnings.extend(transformation_quality.warnings)
        if not transformation_quality.passed and status in {"generated", "mixed"}:
            status = "needs_review"

    score = _candidate_score(quality, mix_quality, result.provider_name, duration_close)
    if transformation_quality and not transformation_quality.passed:
        score -= 0.75
    diagnostics = OnlineGenerationDiagnostics(
        status=status,
        provider_order=provider_order,
        fallback_used=result.provider_name == "local_fallback",
        failed_step=None if quality.passed else "audio_validation",
        error_message=None if quality.passed else _quality_failure_summary(quality),
        suggested_fix=(
            "Online providers were unavailable, so local_fallback was used. Configure ElevenLabs or Lyria for higher-quality music."
            if result.provider_name == "local_fallback"
            else result.suggested_fix
        ),
        last_logs=[*attempt_logs, *list(result.logs or [])][-40:],
    )
    return OnlineGenerationCandidate(
        candidate_id=candidate_id,
        provider_name=result.provider_name,
        status=status,
        backing_audio_path=result.output_path,
        backing_audio_url=url_for_path(result.output_path),
        mixed_preview_path=mixed_preview_path,
        mixed_preview_url=url_for_path(mixed_preview_path),
        final_mix_wav_path=final_wav_path,
        final_mix_mp3_path=final_mp3_path,
        final_mix_mp3_url=url_for_path(final_mp3_path),
        quality_report=quality,
        mix_quality_report=mix_quality,
        score=round(score, 3),
        reference_conditioned=bool(result.metadata.get("reference_conditioned")),
        reference_strength=result.metadata.get("reference_strength"),
        transformation_quality=transformation_quality,
        diagnostics=diagnostics,
        warnings=_dedupe(warnings),
        prompt=plan.provider_prompt,
    )


def _response_from_candidates(
    *,
    job_id: str,
    mode: str,
    upload_id: str | None = None,
    reference_upload_id: str | None = None,
    vocal_upload_id: str | None = None,
    analysis: VocalAnalysisReport | None = None,
    reference_analysis: VocalAnalysisReport | None = None,
    plan: MusicCompositionPlan,
    candidates: list[OnlineGenerationCandidate],
    rights_confirmed: bool,
    source_preparation: MusicSourcePreparation | None = None,
) -> OnlineGenerationResponse:
    best = max(candidates, key=lambda item: item.score if item.score is not None else -10.0, default=None)
    any_success = any(item.status in {"generated", "mixed", "needs_review"} for item in candidates)
    fallback_used = any(item.provider_name == "local_fallback" and item.status != "failed" for item in candidates)
    needs_review = fallback_used or any(item.status in {"needs_review", "mix_failed", "failed_validation"} for item in candidates)
    status = "completed_needs_review" if any_success and needs_review else "completed" if any_success else "failed"
    message = (
        "Online music candidates generated; review alignment and choose the best mix."
        if status == "completed"
        else "Music candidates generated, but at least one issue needs review."
        if status == "completed_needs_review"
        else "No music candidate could be generated."
    )
    diagnostics = OnlineGenerationDiagnostics(
        status=status,
        provider_order=plan.provider_preferences,
        fallback_used=fallback_used,
        rights_confirmed=rights_confirmed,
        failed_step=None if any_success else "provider_generation",
        error_message=None if any_success else "All candidate generation attempts failed.",
        suggested_fix=(
            "Configure ELEVENLABS_API_KEY or GEMINI_API_KEY for online generation; local_fallback is only a debug preview."
            if fallback_used
            else "Review candidate warnings and regenerate with a clearer style instruction."
            if any_success
            else "Check provider keys, network access, and upload analysis."
        ),
        last_logs=_dedupe(
            [
                log
                for candidate in candidates
                for log in ((candidate.diagnostics.last_logs if candidate.diagnostics else [])[:20])
            ]
        )[-40:],
    )
    return OnlineGenerationResponse(
        job_id=job_id,
        status=status,
        mode=mode,
        upload_id=upload_id,
        reference_upload_id=reference_upload_id,
        vocal_upload_id=vocal_upload_id,
        analysis=analysis,
        reference_analysis=reference_analysis,
        source_preparation=source_preparation,
        composition_plan=plan,
        candidates=candidates,
        best_candidate=best,
        diagnostics=diagnostics,
        message=message,
    )


def _rights_required(settings: Any, confirmed: bool) -> bool:
    return bool(getattr(settings, "require_rights_confirmation", True)) and not confirmed


def _regeneration_reference_path(
    response: OnlineGenerationResponse,
    upload_lookup: UploadLookup,
) -> str | None:
    if response.source_preparation and response.source_preparation.instrumental_audio_path:
        return response.source_preparation.instrumental_audio_path
    if not response.reference_upload_id:
        return None
    upload = upload_lookup(response.reference_upload_id)
    if response.reference_analysis and response.reference_analysis.normalized_wav_path:
        return response.reference_analysis.normalized_wav_path
    return upload.original_path if upload else None


def _rights_required_response(
    job_id: str,
    mode: str,
    *,
    upload_id: str | None = None,
    reference_upload_id: str | None = None,
    vocal_upload_id: str | None = None,
) -> OnlineGenerationResponse:
    return OnlineGenerationResponse(
        job_id=job_id,
        status="rights_required",
        mode=mode,
        upload_id=upload_id,
        reference_upload_id=reference_upload_id,
        vocal_upload_id=vocal_upload_id,
        diagnostics=OnlineGenerationDiagnostics(
            status="rights_required",
            failed_step="rights_confirmation",
            rights_confirmed=False,
            error_message="User-owned/licensed audio confirmation is required before online generation.",
            suggested_fix="Confirm that you own or have rights to use the uploaded audio, then retry.",
        ),
        message="Rights confirmation is required before sending generation requests to online providers.",
    )


def _failed_response(
    *,
    job_id: str,
    mode: str,
    status: str,
    message: str,
    diagnostics: OnlineGenerationDiagnostics,
    upload_id: str | None = None,
    reference_upload_id: str | None = None,
    vocal_upload_id: str | None = None,
    analysis: VocalAnalysisReport | None = None,
    reference_analysis: VocalAnalysisReport | None = None,
    source_preparation: MusicSourcePreparation | None = None,
) -> OnlineGenerationResponse:
    return OnlineGenerationResponse(
        job_id=job_id,
        status=status,
        mode=mode,
        upload_id=upload_id,
        reference_upload_id=reference_upload_id,
        vocal_upload_id=vocal_upload_id,
        analysis=analysis,
        reference_analysis=reference_analysis,
        source_preparation=source_preparation,
        diagnostics=diagnostics,
        message=message,
    )


def _provider_order(
    provider_preference: str | None,
    settings: Any,
    *,
    reference_conditioned: bool = False,
) -> ProviderOrder:
    candidates = [
        provider_preference,
        "ace_step" if reference_conditioned else None,
        getattr(settings, "music_provider_primary", "elevenlabs"),
        getattr(settings, "music_provider_secondary", "lyria"),
        "local_fallback",
    ]
    order: ProviderOrder = []
    for candidate in candidates:
        name = _normalize_provider(candidate)
        if name and name not in order:
            order.append(name)
    return order or ["elevenlabs", "lyria", "local_fallback"]


def _normalize_provider(value: str | None) -> str | None:
    text = (value or "").strip().lower().replace("-", "_")
    aliases = {
        "acestep": "ace_step",
        "local_ace_step": "ace_step",
        "eleven": "elevenlabs",
        "elevenlabs_music": "elevenlabs",
        "google_lyria": "lyria",
        "lyria3": "lyria",
        "lyria_3_pro": "lyria",
        "procedural": "local_fallback",
        "procedural_v2": "local_fallback",
        "local": "local_fallback",
    }
    text = aliases.get(text, text)
    return text if text in {"ace_step", "elevenlabs", "lyria", "local_fallback"} else None


def _providers_for_order(order: ProviderOrder) -> list[MusicProvider]:
    mapping: dict[str, MusicProvider] = {
        "ace_step": LocalAceStepProvider(),
        "elevenlabs": ElevenMusicProvider(),
        "lyria": LyriaProvider(),
        "local_fallback": LocalFallbackProvider(),
    }
    return [mapping[name] for name in order if name in mapping]


def _candidate_count(value: int | None, settings: Any) -> int:
    return max(1, min(int(value or getattr(settings, "generate_candidate_count", 3) or 3), 5))


def _analysis_usable(analysis: VocalAnalysisReport) -> bool:
    report = analysis.quality_report
    return bool(report and report.audio_exists and not report.is_silent and report.duration_seconds and report.duration_seconds >= 1.0)


def _analysis_failure_summary(analysis: VocalAnalysisReport) -> str:
    report = analysis.quality_report
    if not report:
        return "No quality report was produced."
    issues = report.validation_errors or report.warnings
    return "; ".join(issues[:4]) if issues else "Audio could not be analyzed."


def _quality_failure_summary(report: QualityReport) -> str:
    issues = report.validation_errors or report.warnings
    return "; ".join(issues[:4]) if issues else "Generated audio failed validation."


def _provider_failure(
    provider_name: str,
    error_message: str,
    suggested_fix: str,
    logs: list[str] | None = None,
) -> ProviderGenerationResult:
    return ProviderGenerationResult(
        success=False,
        provider_name=provider_name,
        error_message=error_message,
        suggested_fix=suggested_fix,
        logs=logs or [],
    )


def _extract_lyria_audio_bytes(response: Any) -> bytes | None:
    try:
        payload = response.json()
    except Exception:
        try:
            payload = json.loads(response.text)
        except Exception:
            return None
    encoded = _find_audio_base64(payload)
    if not encoded:
        return None
    try:
        return base64.b64decode(encoded)
    except Exception:
        return None


def _find_audio_base64(node: Any) -> str | None:
    if isinstance(node, dict):
        output_audio = node.get("output_audio")
        if isinstance(output_audio, dict) and isinstance(output_audio.get("data"), str):
            return output_audio["data"]
        audio = node.get("audio")
        if isinstance(audio, dict) and isinstance(audio.get("data"), str):
            return audio["data"]
        if node.get("type") == "audio" and isinstance(node.get("data"), str):
            return node["data"]
        for value in node.values():
            found = _find_audio_base64(value)
            if found:
                return found
    if isinstance(node, list):
        for value in node:
            found = _find_audio_base64(value)
            if found:
                return found
    return None


def _duration_close(actual: float | None, expected: int | None) -> bool:
    if not actual or not expected:
        return True
    return expected * 0.75 <= float(actual) <= expected * 1.25


def _candidate_score(
    quality: QualityReport,
    mix_quality: QualityReport | None,
    provider_name: str,
    duration_close: bool,
) -> float:
    score = 0.0
    if quality.passed:
        score += 1.0
    if mix_quality and mix_quality.passed:
        score += 1.0
    if duration_close:
        score += 0.35
    if provider_name == "elevenlabs":
        score += 0.35
    elif provider_name == "lyria":
        score += 0.25
    elif provider_name == "local_fallback":
        score -= 0.2
    if quality.clipping_detected:
        score -= 0.5
    return score


def _style_from_mood(mood_tags: list[str], instruction: str | None = None) -> str:
    text = " ".join([*(mood_tags or []), instruction or ""]).lower()
    if any(token in text for token in ("rock", "guitar", "anthem", "sad rock")):
        return "Sufi Rock"
    if any(token in text for token in ("lo-fi", "lofi", "rain", "late night", "nostalgic")):
        return "Lo-fi Cover"
    if any(token in text for token in ("bhajan", "devotional", "krishna", "ram", "shiv", "mandir")):
        return "Bhajan / Devotional"
    if any(token in text for token in ("trap", "808", "dark", "toxic")):
        return "Trap Soul"
    if any(token in text for token in ("acoustic", "unplugged")):
        return "Acoustic Unplugged"
    return "Bollywood Ballad"


def _arrangement_for_style(production_style: str | None, genre: str | None) -> str:
    text = f"{production_style or ''} {genre or ''}".lower()
    if "rock" in text:
        return "Indie band arrangement"
    if "lo-fi" in text or "lofi" in text:
        return "Lo-fi warm tape"
    if "bhajan" in text or "devotional" in text:
        return "Tabla + strings fusion"
    if "trap" in text:
        return "Trap drums + Indian melody"
    if "acoustic" in text:
        return "Acoustic guitar-led"
    return "Piano-led cinematic"


def _instruments_for_style(production_style: str | None, arrangement_style: str | None, genre: str | None) -> list[str]:
    text = f"{production_style or ''} {arrangement_style or ''} {genre or ''}".lower()
    if "rock" in text:
        return ["piano", "electric guitar", "bass", "drums", "strings", "pads"]
    if "lo-fi" in text or "lofi" in text:
        return ["electric piano", "soft drums", "sub bass", "pads", "tape texture"]
    if "bhajan" in text or "devotional" in text:
        return ["harmonium", "tanpura", "tabla", "flute", "soft strings"]
    if "trap" in text:
        return ["808 bass", "trap drums", "pads", "pluck melody", "Indian flute texture"]
    if "acoustic" in text:
        return ["acoustic guitar", "soft bass", "light percussion", "pads"]
    return ["piano", "strings", "pads", "clean guitar", "soft drums", "bass"]


def _moods_from_text(text: str) -> list[str]:
    lowered = text.lower()
    moods: list[str] = []
    mapping = {
        "heartbreak": ("heartbreak", "yaad", "tanha", "adhoora", "judaai", "aansu", "sad"),
        "romantic": ("romantic", "pyaar", "ishq", "love", "dil"),
        "devotional": ("dua", "maula", "allah", "bhajan", "devotional", "mandir"),
        "nostalgic": ("rain", "memory", "nostalgic", "late night"),
        "intense": ("rock", "anthem", "powerful", "intense"),
    }
    for mood, tokens in mapping.items():
        if any(token in lowered for token in tokens):
            moods.append(mood)
    return moods


def _duration_sections(duration: int) -> list[dict[str, Any]]:
    names = ["intro", "mukhda", "hook", "antara", "final_hook", "outro"]
    weights = [0.1, 0.22, 0.2, 0.24, 0.18, 0.06]
    cursor = 0.0
    sections: list[dict[str, Any]] = []
    for name, weight in zip(names, weights):
        end = float(duration) if name == names[-1] else cursor + duration * weight
        sections.append({"name": name, "start_seconds": round(cursor, 3), "end_seconds": round(end, 3), "source": "duration_fallback"})
        cursor = end
    return sections


def _contains_famous_reference(text: str) -> bool:
    return any(re.search(pattern, text or "", flags=re.IGNORECASE) for pattern in FAMOUS_REFERENCE_REPLACEMENTS)


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in result:
            result.append(text)
    return result
