import json
import os
from copy import deepcopy
from pathlib import Path
import time
from urllib.parse import quote, unquote

from fastapi import BackgroundTasks, Depends, FastAPI, File, Header, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .auth import get_current_user
from .audio_validation import validate_audio_file
from .config import settings
from .generators import ace_step, procedural_v2
from .local_ai import agent_generation_plan, local_capabilities
from .mixer import MIXER_NAME, MixResult, mix_vocal_with_backing, resolve_output_dir as resolve_mix_output_dir
from .models import (
    AdminSummaryResponse,
    ArrangementMode,
    AppHealthResponse,
    AudioExport,
    AudioUploadResponse,
    CloudRuntimeSnapshot,
    CleanupRequest,
    CleanupResponse,
    CreateJobRequest,
    ExportRequest,
    ExportResponse,
    GenerationTelemetry,
    GenerationDiagnostics,
    HistoryResponse,
    JobRecord,
    JobResponse,
    JobStatus,
    JobStatusResponse,
    LibraryRecoveryResponse,
    LyricsImproveRequest,
    LyricsImproveResponse,
    MixDiagnostics,
    MixRequest,
    MixResponse,
    MusicToMusicRequest,
    OnlineGenerationResponse,
    PromptPreviewRequest,
    ProjectCreateRequest,
    ProjectListResponse,
    ProjectResponse,
    ProjectUpdateRequest,
    ProducerSuggestionRequest,
    ProducerSuggestionResponse,
    QualityReport,
    QualityExplanationRequest,
    QualityExplanationResponse,
    CloudCostSnapshot,
    RecycleBinResponse,
    RegenerateMusicRequest,
    SignedUploadRequest,
    SignedUploadResponse,
    SkarlyStudioAnalyzeRequest,
    SkarlyStudioAnalyzeResponse,
    SkarlyStudioGenerateRequest,
    SkarlyStudioResponse,
    SkarlyProducerProfileResponse,
    SkarlyV2AnalyzeRequest,
    SkarlyV2ExportRequest,
    SkarlyV2ExportResponse,
    SkarlyV2FeedbackRequest,
    SkarlyV2GenerationRequest,
    SkarlyV2JobResponse,
    SkarlyV2MixRequest,
    SkarlyV2RegenerateRequest,
    SkarlyV2SectionRegenerateRequest,
    SkarlyVersionSelectionRequest,
    SongAnalysis,
    SongGenerateRequest,
    SectionEditRequest,
    SectionEditResponse,
    StemSeparationRequest,
    StemSeparationResponse,
    UploadVerificationRequest,
    UploadVerificationResponse,
    UpdateJobLibraryRequest,
    UserContext,
    UserProfileRequest,
    UserProfileResponse,
    VoiceTakeListResponse,
    VoiceTakePlaybackResponse,
    VoiceTakeRequest,
    VoiceTakeResponse,
    VocalAnalysisReport,
    VocalToMusicRequest,
    Genre,
    SourceType,
    new_id,
    now_utc,
)
from .presets import (
    AVAILABLE_ARRANGEMENT_STYLES,
    AVAILABLE_GENRES,
    AVAILABLE_PRODUCTION_STYLES,
    get_all_presets,
    get_default_preset,
    get_preset_by_id,
)
from .prompt_builder import build_generation_prompt
from .repository import DuplicateEmailError, jobs, usage, users, voice_takes
from .services import jobs as producer_jobs
from .services import cleanup as cleanup_service
from .services import exports as export_service
from .services import health as health_service
from .services import projects as project_service
from .services import benchmark_evidence, diversity_calibration, human_validation as human_validation_service, online_job_store, online_music, safe_paths, section_editor, skarly_studio, stems as stems_service, studio_v2_exports, studio_v2_jobs, training_feedback, uploads as upload_service, vocal_analysis
from .services.producer_assistant import (
    analyze_request_placeholder,
    compile_producer_prompt,
    explain_quality_report_placeholder_or_rules,
    explain_quality_report_placeholder,
    improve_lyrics_rules,
    suggest_producer_settings,
)
from .storage import (
    content_type_from_path,
    storage,
    storage_owner_id,
    user_final_prefixes,
    user_raw_prefixes,
    user_storage_prefix,
)
from .tasks import task_queue
from .worker import build_worker

app = FastAPI(title="Skarly Backend", version="0.6.0")


@app.on_event("startup")
def recover_interrupted_v2_jobs() -> None:
    studio_v2_jobs.recover_interrupted_jobs(settings.skarly_output_dir)


app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_origin_regex=r"^http://(localhost|127\.0\.0\.1):\d+$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
static_dir = Path(__file__).resolve().parent / "static"
if static_dir.exists():
    app.mount("/studio-assets", StaticFiles(directory=static_dir), name="studio-assets")
ace_step_output_dir = ace_step.resolve_output_dir(settings.ace_step_output_dir)
ace_step_output_dir.mkdir(parents=True, exist_ok=True)
app.mount("/outputs/ace_step", StaticFiles(directory=ace_step_output_dir), name="ace-step-outputs")
procedural_output_dir = procedural_v2.resolve_output_dir(settings.procedural_output_dir)
procedural_output_dir.mkdir(parents=True, exist_ok=True)
app.mount("/outputs/procedural_v2", StaticFiles(directory=procedural_output_dir), name="procedural-v2-outputs")
mix_output_dir = resolve_mix_output_dir(settings.mix_output_dir)
mix_output_dir.mkdir(parents=True, exist_ok=True)
app.mount("/outputs/mixes", StaticFiles(directory=mix_output_dir), name="mix-outputs")
stems_output_dir = stems_service.resolve_output_dir(settings.stems_output_dir)
stems_output_dir.mkdir(parents=True, exist_ok=True)
app.mount("/outputs/stems", StaticFiles(directory=stems_output_dir), name="stem-outputs")
section_output_dir = section_editor.resolve_output_dir(settings.section_output_dir)
section_output_dir.mkdir(parents=True, exist_ok=True)
app.mount("/outputs/sections", StaticFiles(directory=section_output_dir), name="section-outputs")
projects_output_dir = safe_paths.resolve_output_dir(settings.projects_dir)
projects_output_dir.mkdir(parents=True, exist_ok=True)
app.mount("/outputs/projects", StaticFiles(directory=projects_output_dir), name="project-outputs")
exports_output_dir = safe_paths.resolve_output_dir(settings.exports_dir)
exports_output_dir.mkdir(parents=True, exist_ok=True)
app.mount("/outputs/exports", StaticFiles(directory=exports_output_dir), name="export-outputs")
uploads_output_dir = safe_paths.resolve_output_dir(settings.uploads_dir)
uploads_output_dir.mkdir(parents=True, exist_ok=True)
app.mount("/outputs/uploads", StaticFiles(directory=uploads_output_dir), name="upload-outputs")
online_music_output_dir = safe_paths.resolve_output_dir(settings.online_music_output_dir)
online_music_output_dir.mkdir(parents=True, exist_ok=True)
app.mount("/outputs/online_music", StaticFiles(directory=online_music_output_dir), name="online-music-outputs")
skarly_output_dir = safe_paths.resolve_output_dir(settings.skarly_output_dir)
skarly_output_dir.mkdir(parents=True, exist_ok=True)
app.mount("/outputs/skarly", StaticFiles(directory=skarly_output_dir), name="skarly-outputs")
worker = build_worker(jobs)


def require_admin_user(user: UserContext = Depends(get_current_user)) -> UserContext:
    email = (user.email or "").strip().lower()
    uid = user.user_id.strip()
    if settings.admin_emails or settings.admin_uids:
        if (email and email in settings.admin_emails) or (uid and uid in settings.admin_uids):
            return user
        raise HTTPException(status_code=403, detail="Admin access required")
    if settings.app_env == "local":
        return user
    raise HTTPException(status_code=403, detail="Admin access required")


@app.get("/health")
def health():
    return {
        "ok": True,
        "service": "skarly-backend",
        "phase": 12,
        "repository_backend": settings.repository_backend,
        "storage_backend": settings.storage_backend,
        "worker_backend": settings.worker_backend,
        "music_generator_backend": settings.music_generator_backend,
        "melody_analyzer_backend": settings.melody_analyzer_backend,
        "stem_separator_backend": settings.stem_separator_backend,
        "ace_step_base_url": settings.ace_step_base_url,
        "ace_step_enabled": settings.ace_step_enabled,
        "require_cuda": settings.require_cuda,
        "allow_cpu_generation_fallback": settings.allow_cpu_generation_fallback,
        "ace_step_max_duration_seconds": settings.ace_step_max_duration_seconds,
        "ace_step_mode": settings.ace_step_mode,
        "ace_step_output_dir": str(ace_step.resolve_output_dir(settings.ace_step_output_dir)),
        "procedural_fallback_enabled": settings.procedural_fallback_enabled,
        "procedural_output_dir": str(procedural_v2.resolve_output_dir(settings.procedural_output_dir)),
        "procedural_default_format": settings.procedural_default_format,
        "mix_output_dir": str(resolve_mix_output_dir(settings.mix_output_dir)),
        "mix_default_format": settings.mix_default_format,
        "mix_preview_format": settings.mix_preview_format,
        "mix_sample_rate": settings.mix_sample_rate,
        "producer_assistant_enabled": settings.producer_assistant_enabled,
        "producer_assistant_mode": settings.producer_assistant_mode,
        "projects_enabled": settings.projects_enabled,
        "projects_dir": str(safe_paths.resolve_output_dir(settings.projects_dir)),
        "exports_dir": str(safe_paths.resolve_output_dir(settings.exports_dir)),
        "uploads_dir": str(safe_paths.resolve_output_dir(settings.uploads_dir)),
        "output_retention_days": settings.output_retention_days,
        "online_music_enabled": settings.online_music_enabled,
        "music_provider_primary": settings.music_provider_primary,
        "music_provider_secondary": settings.music_provider_secondary,
        "online_music_output_dir": str(safe_paths.resolve_output_dir(settings.online_music_output_dir)),
        "generate_candidate_count": settings.generate_candidate_count,
        "require_rights_confirmation": settings.require_rights_confirmation,
        "stems_enabled": settings.stems_enabled,
        "stems_engine": settings.stems_engine,
        "stems_output_dir": str(stems_service.resolve_output_dir(settings.stems_output_dir)),
        "music_to_music_source_modes": ["auto", "instrumental", "full_song"],
        "music_to_music_vocal_threshold_db": settings.music_to_music_vocal_threshold_db,
        "music_to_music_min_vocal_activity": settings.music_to_music_min_vocal_activity,
        "music_to_music_verify_generated_vocals": settings.music_to_music_verify_generated_vocals,
        "section_editing_enabled": settings.section_editing_enabled,
        "section_editing_mode": settings.section_editing_mode,
        "section_output_dir": str(section_editor.resolve_output_dir(settings.section_output_dir)),
        "arrangement_modes": [mode.value for mode in ArrangementMode],
        "diversity_calibration": diversity_calibration.active_diversity_calibration().public_status(),
        "ace_step_profile_benchmark": benchmark_evidence.public_status(
            settings.ace_step_benchmark_evidence_path
        ),
        "timeouts": {
            "analysis_timeout_sec": settings.analysis_timeout_sec,
            "separation_timeout_sec": settings.separation_timeout_sec,
            "melody_timeout_sec": settings.melody_timeout_sec,
            "backing_generation_timeout_sec": settings.backing_generation_timeout_sec,
            "mixing_timeout_sec": settings.mixing_timeout_sec,
            "export_timeout_sec": settings.export_timeout_sec,
            "studio_poll_timeout_sec": settings.studio_poll_timeout_sec,
        },
        "task_backend": settings.task_backend,
        "cloud_runtime": _cloud_runtime_snapshot().model_dump(),
    }


@app.get("/health/full", response_model=AppHealthResponse)
def full_health():
    return health_service.build_full_health(
        settings,
        output_dirs=_configured_output_dirs(),
        version=app.version,
    )


@app.get("/studio")
def studio():
    return FileResponse(static_dir / "studio.html")


@app.get("/ace-step/health")
def ace_step_health():
    health = ace_step.health_check(
        mode=settings.ace_step_mode,
        cli_path=settings.ace_step_cli_path,
        output_dir=settings.ace_step_output_dir,
    )
    return {
        "enabled": settings.ace_step_enabled,
        "procedural_fallback_enabled": settings.procedural_fallback_enabled,
        "procedural_output_dir": str(procedural_v2.resolve_output_dir(settings.procedural_output_dir)),
        **health,
    }


@app.get("/presets")
def list_producer_presets():
    default_preset = get_default_preset()
    return {
        "presets": get_all_presets(),
        "default_preset_id": default_preset["id"],
        "available_genres": AVAILABLE_GENRES,
        "available_production_styles": AVAILABLE_PRODUCTION_STYLES,
        "available_arrangement_styles": AVAILABLE_ARRANGEMENT_STYLES,
    }


@app.get("/presets/{preset_id}")
def get_producer_preset(preset_id: str):
    return _require_preset(preset_id)


@app.post("/prompt/preview")
def preview_prompt(request: PromptPreviewRequest):
    preset = _optional_preset(request.preset_id)
    preview = build_generation_prompt(request, preset)
    if settings.producer_assistant_enabled:
        suggestion = suggest_producer_settings(
            ProducerSuggestionRequest(
                lyrics=request.lyrics,
                language=request.language,
                mood_tags=request.mood_tags,
                genre=request.genre,
                production_style=request.production_style,
                arrangement_style=request.arrangement_style,
                instruments=request.instruments,
                bpm=request.bpm,
                key=request.key,
                duration_seconds=request.duration_seconds,
            )
        )
        preview["assistant_reasoning"] = suggestion.reasoning
        preview["assistant_suggestion"] = suggestion.model_dump()
    return preview


@app.post("/generate", response_model=JobStatusResponse)
def generate_mock_song(request: PromptPreviewRequest):
    preset = _optional_preset(request.preset_id)
    preview = build_generation_prompt(request, preset)
    if not settings.ace_step_enabled:
        return _create_mock_generation_job(preview)

    return _create_ace_step_generation_job(request, preview)


def _create_mock_generation_job(preview: dict) -> JobStatusResponse:
    started_at = now_utc()
    diagnostics = GenerationDiagnostics(
        generator_name="mock_prompt_builder",
        status="completed_mock",
        started_at=started_at,
        finished_at=now_utc(),
        duration_seconds=0.0,
        fallback_used=False,
        last_logs=[
            "Preset and producer settings resolved.",
            "Generation prompt built.",
            "Real audio generation is disabled.",
        ],
        suggested_fix="Set ACE_STEP_ENABLED=true to attempt ACE-Step generation.",
    )
    quality_report = explain_quality_report_placeholder()
    audio_export = AudioExport(quality_report=quality_report)
    message = "Prompt generated successfully. Real audio generation is disabled."

    created = producer_jobs.create_job(
        {
            "status": "queued",
            "progress": 0.05,
            "message": message,
            "positive_prompt": preview["positive_prompt"],
            "negative_prompt": preview["negative_prompt"],
            "structured_summary": preview["structured_summary"],
            "recommended_settings": preview["recommended_settings"],
            "generation_mode": "mock",
            "audio_export": audio_export.model_dump(),
            "diagnostics": diagnostics.model_dump(),
            "quality_report": quality_report.model_dump(),
            "warnings": preview["warnings"],
        }
    )
    completed = producer_jobs.update_job(
        created["job_id"],
        {
            "status": "completed_mock",
            "progress": 1.0,
            "diagnostics": diagnostics.model_dump(),
            "quality_report": quality_report.model_dump(),
            "audio_export": audio_export.model_dump(),
        },
    )
    return _producer_job_response(completed)


def _create_ace_step_generation_job(request: PromptPreviewRequest, preview: dict) -> JobStatusResponse:
    created = producer_jobs.create_job(
        {
            "status": "generating",
            "progress": 0.25,
            "message": "ACE-Step generation started.",
            "positive_prompt": preview["positive_prompt"],
            "negative_prompt": preview["negative_prompt"],
            "structured_summary": preview["structured_summary"],
            "recommended_settings": preview["recommended_settings"],
            "generation_mode": "ace_step",
            "warnings": preview["warnings"],
        }
    )
    job_id = created["job_id"]
    summary = preview.get("structured_summary") or {}

    try:
        result = ace_step.generate_song(
            positive_prompt=preview["positive_prompt"],
            negative_prompt=preview["negative_prompt"],
            lyrics=request.lyrics,
            duration_seconds=summary.get("duration_seconds"),
            bpm=summary.get("bpm"),
            key=summary.get("key"),
            output_dir=settings.ace_step_output_dir,
            job_id=job_id,
            timeout_seconds=settings.ace_step_timeout_seconds,
            mode=settings.ace_step_mode,
            cli_path=settings.ace_step_cli_path,
            device=settings.ace_step_device,
            output_format=settings.ace_step_default_format,
        )
    except Exception as exc:
        now = now_utc()
        result = ace_step.GenerationResult(
            success=False,
            output_path=None,
            generator_name="ACE-Step",
            started_at=now,
            finished_at=now,
            duration_seconds=0.0,
            error_message=f"ACE-Step wrapper crashed safely: {exc}",
            logs=[],
            suggested_fix="Set ACE_STEP_ENABLED=false to return to mock mode, then inspect the backend logs.",
        )

    if result.success:
        quality_report = validate_audio_file(
            result.output_path,
            expected_duration_seconds=summary.get("duration_seconds"),
            generator_name="ACE-Step",
            fallback_used=False,
        )
        diagnostics = (
            _diagnostics_from_ace_result(result)
            if quality_report.passed
            else _diagnostics_for_validation_failure(result, quality_report)
        )
        audio_url = _ace_step_output_url(result.output_path) if _safe_existing_output(result.output_path) else None
        audio_export = _audio_export_for_output(result.output_path, quality_report)
        if not quality_report.passed:
            if settings.procedural_fallback_enabled:
                fallback_reason = f"ACE-Step audio failed validation during audio_validation: {_validation_failure_summary(quality_report)}"
                return _attempt_procedural_fallback(
                    job_id=job_id,
                    request=request,
                    preview=preview,
                    summary=summary,
                    fallback_reason=fallback_reason,
                    original_diagnostics=diagnostics,
                    original_quality_report=quality_report,
                )

            failed_validation = producer_jobs.update_job(
                job_id,
                {
                    "status": "failed_validation",
                    "progress": 1.0,
                    "message": "Audio was generated but failed validation.",
                    "generated_audio_path": result.output_path,
                    "audio_url": audio_url,
                    "preview_url": audio_url,
                    "audio_export": audio_export.model_dump(),
                    "diagnostics": diagnostics.model_dump(),
                    "quality_report": quality_report.model_dump(),
                },
            )
            return _producer_job_response(failed_validation)

        return _complete_generated_backing(
            job_id=job_id,
            request=request,
            status="completed",
            message="Audio generated and validated successfully.",
            generation_mode="ace_step",
            backing_path=result.output_path,
            backing_url=audio_url,
            backing_quality_report=quality_report,
            generation_diagnostics=diagnostics,
        )

    diagnostics = _diagnostics_from_ace_result(result)
    quality_report = _basic_ace_quality_report(result)
    if settings.procedural_fallback_enabled:
        fallback_reason = f"ACE-Step generation failed: {result.error_message or 'No output was produced.'}"
        return _attempt_procedural_fallback(
            job_id=job_id,
            request=request,
            preview=preview,
            summary=summary,
            fallback_reason=fallback_reason,
            original_diagnostics=diagnostics,
            original_quality_report=quality_report,
        )

    audio_export = _audio_export_for_output(result.output_path, quality_report)
    failed = producer_jobs.update_job(
        job_id,
        {
            "status": "failed",
            "progress": 1.0,
            "message": "ACE-Step generation failed. See diagnostics.",
            "generated_audio_path": result.output_path,
            "audio_export": audio_export.model_dump(),
            "diagnostics": diagnostics.model_dump(),
            "quality_report": quality_report.model_dump(),
        },
    )
    return _producer_job_response(failed)


@app.get("/jobs/{job_id}", response_model=JobStatusResponse)
def get_mock_job(job_id: str):
    job = producer_jobs.get_job(job_id)
    if job is None:
        online_payload = online_job_store.load(settings.online_music_output_dir, job_id)
        if online_payload:
            response = OnlineGenerationResponse.model_validate(online_payload)
            best = response.best_candidate
            job = {
                "job_id": job_id,
                "status": response.status,
                "progress": 1.0,
                "message": response.message,
                "generation_mode": response.mode,
                "generated_audio_path": best.backing_audio_path if best else None,
                "audio_url": (best.mixed_preview_url or best.backing_audio_url) if best else None,
                "preview_url": (best.mixed_preview_url or best.backing_audio_url) if best else None,
                "backing_audio_path": best.backing_audio_path if best else None,
                "backing_audio_url": best.backing_audio_url if best else None,
                "mixed_preview_path": best.mixed_preview_path if best else None,
                "mixed_preview_url": best.mixed_preview_url if best else None,
                "online_response": online_payload,
            }
        else:
            raise HTTPException(status_code=404, detail="Job not found")
    return _producer_job_response(job)


@app.post("/analyze", response_model=SongAnalysis)
def analyze_song_request(request: PromptPreviewRequest):
    preset = _optional_preset(request.preset_id)
    return analyze_request_placeholder(request, preset)


@app.post("/improve-lyrics", response_model=LyricsImproveResponse)
def improve_lyrics(request: LyricsImproveRequest):
    return improve_lyrics_rules(request, assistant_mode=settings.producer_assistant_mode or "rules")


@app.post("/producer/suggest", response_model=ProducerSuggestionResponse)
def producer_suggest(request: ProducerSuggestionRequest):
    return suggest_producer_settings(request)


@app.post("/producer/compile-prompt")
def producer_compile_prompt(request: ProducerSuggestionRequest):
    return compile_producer_prompt(request)


@app.post("/producer/explain-quality", response_model=QualityExplanationResponse)
def producer_explain_quality(request: QualityExplanationRequest):
    return explain_quality_report_placeholder_or_rules(
        quality_report=request.quality_report,
        diagnostics=request.diagnostics,
        mix_diagnostics=request.mix_diagnostics,
    )


@app.post("/uploads/audio", response_model=AudioUploadResponse)
async def upload_audio(file: UploadFile = File(...)):
    try:
        data = await file.read()
        return upload_service.save_audio_upload(
            filename=file.filename or "audio.wav",
            content_type=file.content_type,
            data=data,
            uploads_dir=settings.uploads_dir,
            max_upload_mb=settings.max_upload_mb,
            url_for_path=_known_output_url,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/uploads/{upload_id}", response_model=AudioUploadResponse)
def get_audio_upload(upload_id: str):
    upload = upload_service.get_upload(upload_id, uploads_dir=settings.uploads_dir, url_for_path=_known_output_url)
    if upload is None:
        raise HTTPException(status_code=404, detail="Upload not found")
    return upload


@app.post("/uploads/{upload_id}/analyze", response_model=VocalAnalysisReport)
def analyze_audio_upload(upload_id: str):
    upload = upload_service.get_upload(upload_id, uploads_dir=settings.uploads_dir, url_for_path=_known_output_url)
    if upload is None:
        raise HTTPException(status_code=404, detail="Upload not found")
    return vocal_analysis.analyze_vocal_audio(
        upload.original_path,
        upload_id=upload.upload_id,
        normalized_output_dir=settings.uploads_dir,
        url_for_path=_known_output_url,
    )


@app.get("/api/v2/producer-profiles", response_model=list[SkarlyProducerProfileResponse])
def list_skarly_v2_producer_profiles(user: UserContext = Depends(get_current_user)):
    del user
    defaults = set(skarly_studio.DEFAULT_HINDI_PRODUCER_PROFILE_IDS)
    return [
        SkarlyProducerProfileResponse(
            profile_id=profile.profile_id,
            name=profile.name,
            instruments=list(profile.instruments),
            energy=profile.energy,
            rhythm_character=profile.rhythm_character,
            mix_mode=profile.mix_mode,
            blueprint=profile.blueprint(),
            is_default=profile.profile_id in defaults,
        )
        for profile in skarly_studio.PRODUCER_PROFILE_CATALOG.values()
    ]


def _human_validation_file_response(panel_id: str, asset_path: str) -> FileResponse:
    try:
        path = human_validation_service.public_panel_file(
            skarly_output_dir=settings.skarly_output_dir,
            panel_id=panel_id,
            asset_path=asset_path,
        )
    except (ValueError, PermissionError, FileNotFoundError):
        raise HTTPException(status_code=404, detail="Validation panel asset not found")
    return FileResponse(
        path,
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@app.get("/api/v2/validation-panels/{panel_id}")
def open_human_validation_panel(panel_id: str):
    return _human_validation_file_response(panel_id, "index.html")


@app.get("/api/v2/validation-panels/{panel_id}/{asset_path:path}")
def get_human_validation_panel_asset(panel_id: str, asset_path: str):
    return _human_validation_file_response(panel_id, asset_path)


@app.post("/api/v2/analyse", response_model=SkarlyV2JobResponse, status_code=202)
def create_skarly_v2_analysis(
    request: SkarlyV2AnalyzeRequest,
    user: UserContext = Depends(get_current_user),
):
    runtime_settings = settings
    try:
        upload_id = _resolve_skarly_upload_id(
            request.upload_id,
            raw_audio_path=request.raw_audio_path,
            user=user,
        )
        if upload_service.get_upload(upload_id, uploads_dir=runtime_settings.uploads_dir) is None:
            raise FileNotFoundError("Upload not found")
        job = studio_v2_jobs.create_job(
            runtime_settings.skarly_output_dir,
            job_type="analysis",
            owner_id=user.user_id,
            upload_id=upload_id,
            request=request.model_dump(mode="json"),
        )
        studio_v2_jobs.submit(
            job["job_id"],
            lambda: _run_skarly_v2_analysis_job(
                job["job_id"],
                upload_id=upload_id,
                owner_id=user.user_id,
                request=request,
                runtime_settings=runtime_settings,
            ),
        )
        return job
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Upload not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/v2/generations", response_model=SkarlyV2JobResponse, status_code=202)
def create_skarly_v2_generation(
    request: SkarlyV2GenerationRequest,
    user: UserContext = Depends(get_current_user),
):
    runtime_settings = settings
    analysis_job = studio_v2_jobs.get_job(runtime_settings.skarly_output_dir, request.analysis_id)
    if analysis_job is None or analysis_job.get("job_type") != "analysis":
        raise HTTPException(status_code=404, detail="Analysis job not found")
    if analysis_job.get("owner_id") != user.user_id:
        raise HTTPException(status_code=403, detail="Analysis job belongs to another user")
    if analysis_job.get("status") != "ready" or not isinstance(analysis_job.get("result"), dict):
        raise HTTPException(status_code=409, detail="Analysis must be ready before creating arrangements")

    try:
        skarly_studio.resolve_producer_profiles(request.arrangement_profiles)
        skarly_studio.normalize_mix_preset(request.mix_profile)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    result = analysis_job["result"]
    song_map = result.get("song_intelligence_map") or {}
    decoded_duration = float(song_map.get("duration_seconds") or 0)
    if request.duration_seconds is not None and decoded_duration > 0:
        tolerance = max(0.25, decoded_duration * 0.001)
        if abs(float(request.duration_seconds) - decoded_duration) > tolerance:
            raise HTTPException(
                status_code=400,
                detail=f"Requested duration must match the decoded vocal duration ({decoded_duration:.3f}s).",
            )
    if decoded_duration > float(runtime_settings.ace_step_max_duration_seconds):
        raise HTTPException(
            status_code=400,
            detail=f"Decoded vocal exceeds the configured {runtime_settings.ace_step_max_duration_seconds}-second generation limit.",
        )
    if request.require_cuda and runtime_settings.skarly_generator_backend != "ace_step":
        raise HTTPException(status_code=503, detail="CUDA generation was requested, but the active generator is not ACE-Step.")

    job = studio_v2_jobs.create_job(
        runtime_settings.skarly_output_dir,
        job_type="generation",
        owner_id=user.user_id,
        upload_id=analysis_job.get("upload_id"),
        analysis_id=analysis_job["job_id"],
        total_arrangements=5,
        request=request.model_dump(mode="json"),
    )
    studio_v2_jobs.submit(
        job["job_id"],
        lambda: _run_skarly_v2_generation_job(
            job["job_id"],
            analysis_job=analysis_job,
            owner_id=user.user_id,
            request=request,
            runtime_settings=runtime_settings,
        ),
    )
    return job


@app.post("/api/v2/generations/regenerate", response_model=SkarlyV2JobResponse, status_code=202)
def regenerate_skarly_v2_arrangement(
    request: SkarlyV2RegenerateRequest,
    user: UserContext = Depends(get_current_user),
):
    runtime_settings = settings
    generation_job = _owned_ready_v2_generation(request.generation_id, user, runtime_settings.skarly_output_dir)
    versions = (generation_job.get("result") or {}).get("versions") or []
    if request.version_index >= len(versions):
        raise HTTPException(status_code=400, detail="Selected arrangement is unavailable")
    profile_id = str(request.producer_profile_id or versions[request.version_index].get("style_family") or "").strip().lower().replace("-", "_")
    if profile_id not in skarly_studio.PRODUCER_PROFILE_CATALOG:
        raise HTTPException(status_code=400, detail="Choose a supported producer profile for regeneration")
    other_profiles = {
        str(version.get("style_family") or "").strip().lower()
        for index, version in enumerate(versions)
        if index != request.version_index
    }
    if profile_id in other_profiles:
        raise HTTPException(status_code=400, detail="That producer profile is already used by another version")
    job = studio_v2_jobs.create_job(
        runtime_settings.skarly_output_dir,
        job_type="generation",
        owner_id=user.user_id,
        upload_id=generation_job.get("upload_id"),
        analysis_id=generation_job.get("analysis_id"),
        total_arrangements=1,
        request=request.model_dump(mode="json"),
    )
    studio_v2_jobs.submit(
        job["job_id"],
        lambda: _run_skarly_v2_regeneration_job(
            job["job_id"],
            generation_job=generation_job,
            request=request,
            runtime_settings=runtime_settings,
        ),
    )
    return job


@app.post("/api/v2/generations/regenerate-section", response_model=SkarlyV2JobResponse, status_code=202)
def regenerate_skarly_v2_section(
    request: SkarlyV2SectionRegenerateRequest,
    user: UserContext = Depends(get_current_user),
):
    runtime_settings = settings
    generation_job = _owned_ready_v2_generation(request.generation_id, user, runtime_settings.skarly_output_dir)
    versions = (generation_job.get("result") or {}).get("versions") or []
    if request.version_index >= len(versions):
        raise HTTPException(status_code=400, detail="Selected arrangement is unavailable")
    duration = float(
        ((generation_job.get("result") or {}).get("song_intelligence_map") or {}).get("duration_seconds") or 0
    )
    if duration <= 0:
        raise HTTPException(status_code=409, detail="Generation is missing its decoded vocal duration")
    if request.section_end_seconds <= request.section_start_seconds:
        raise HTTPException(status_code=400, detail="Section end must be later than section start")
    if request.section_end_seconds - request.section_start_seconds < 0.5:
        raise HTTPException(status_code=400, detail="Choose a section of at least 0.5 seconds")
    if request.section_end_seconds > duration + 0.01:
        raise HTTPException(status_code=400, detail=f"Section must end within the {duration:.3f}-second song")
    if runtime_settings.skarly_generator_backend != "ace_step":
        raise HTTPException(status_code=503, detail="Section regeneration requires the ACE-Step generator")
    if not runtime_settings.require_cuda:
        raise HTTPException(status_code=503, detail="Section regeneration requires CUDA enforcement")

    job = studio_v2_jobs.create_job(
        runtime_settings.skarly_output_dir,
        job_type="section",
        owner_id=user.user_id,
        upload_id=generation_job.get("upload_id"),
        analysis_id=generation_job.get("analysis_id"),
        total_arrangements=1,
        request=request.model_dump(mode="json"),
    )
    studio_v2_jobs.submit(
        job["job_id"],
        lambda: _run_skarly_v2_section_regeneration_job(
            job["job_id"],
            generation_job=generation_job,
            request=request,
            runtime_settings=runtime_settings,
        ),
    )
    return job


@app.get("/api/v2/jobs/{job_id}", response_model=SkarlyV2JobResponse)
def get_skarly_v2_job(job_id: str, user: UserContext = Depends(get_current_user)):
    job = studio_v2_jobs.get_job(settings.skarly_output_dir, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="V2 job not found")
    if job.get("owner_id") != user.user_id:
        raise HTTPException(status_code=403, detail="V2 job belongs to another user")
    return job


@app.post("/api/v2/mixes", response_model=SkarlyV2JobResponse, status_code=202)
def create_skarly_v2_mix(
    request: SkarlyV2MixRequest,
    user: UserContext = Depends(get_current_user),
):
    runtime_settings = settings
    generation_job = _owned_ready_v2_generation(request.generation_id, user, runtime_settings.skarly_output_dir)
    versions = (generation_job.get("result") or {}).get("versions") or []
    if request.version_index >= len(versions):
        raise HTTPException(status_code=400, detail="Selected arrangement is unavailable")
    try:
        skarly_studio.normalize_mix_preset(request.mix_profile)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    job = studio_v2_jobs.create_job(
        runtime_settings.skarly_output_dir,
        job_type="mix",
        owner_id=user.user_id,
        upload_id=generation_job.get("upload_id"),
        analysis_id=generation_job.get("analysis_id"),
        request=request.model_dump(mode="json"),
    )
    studio_v2_jobs.submit(
        job["job_id"],
        lambda: _run_skarly_v2_mix_job(
            job["job_id"],
            generation_job=generation_job,
            request=request,
            runtime_settings=runtime_settings,
        ),
    )
    return job


@app.post("/api/v2/exports", response_model=SkarlyV2ExportResponse, status_code=201)
def create_skarly_v2_export(
    request: SkarlyV2ExportRequest,
    user: UserContext = Depends(get_current_user),
):
    runtime_settings = settings
    generation_job = _owned_ready_v2_generation(request.generation_id, user, runtime_settings.skarly_output_dir)
    versions = (generation_job.get("result") or {}).get("versions") or []
    if request.version_index >= len(versions):
        raise HTTPException(status_code=400, detail="Selected arrangement is unavailable")
    try:
        return studio_v2_exports.create_export_bundle(
            generation_job,
            version_index=request.version_index,
            include_optional_stems=request.include_optional_stems,
            exports_dir=runtime_settings.exports_dir,
            skarly_output_dir=runtime_settings.skarly_output_dir,
            ffmpeg_path=runtime_settings.ffmpeg_path,
            timeout_sec=runtime_settings.export_timeout_sec,
            stem_separator=(
                (
                    lambda source, job_id: stems_service.separate_stems(
                        audio_path=source,
                        output_dir=runtime_settings.stems_output_dir,
                        job_id=job_id,
                        stems=["drums", "bass", "other"],
                        engine=runtime_settings.stems_engine,
                        timeout_seconds=runtime_settings.stems_timeout_seconds,
                        enabled=True,
                        demucs_cli_path=runtime_settings.demucs_path or runtime_settings.demucs_cli_path,
                        demucs_model=runtime_settings.demucs_model,
                        demucs_device=runtime_settings.demucs_device,
                    )
                )
                if runtime_settings.stems_enabled
                and runtime_settings.stem_separator_backend == "demucs"
                else None
            ),
        )
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Skarly export failed: {str(exc)[:400]}")


@app.post("/api/v2/feedback", response_model=SkarlyV2JobResponse, status_code=201)
def save_skarly_v2_feedback(
    request: SkarlyV2FeedbackRequest,
    user: UserContext = Depends(get_current_user),
):
    runtime_settings = settings
    generation_job = _owned_ready_v2_generation(request.generation_id, user, runtime_settings.skarly_output_dir)
    if request.mix_preference:
        try:
            skarly_studio.normalize_mix_preset(request.mix_preference)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
    if request.corrected_language and request.corrected_language.strip().title() not in {"Hindi", "English"}:
        raise HTTPException(status_code=400, detail="Corrected language must be Hindi or English")
    allowed_single_labels = {
        "confirmed_singing_speech": ({"singing", "speaking", "rap", "humming"}, request.confirmed_singing_speech),
        "confirmed_tempo_family": ({"free", "slow", "medium", "fast"}, request.confirmed_tempo_family),
        "confirmed_melodic_character": ({"indian", "western", "mixed"}, request.confirmed_melodic_character),
    }
    for field_name, (allowed, value) in allowed_single_labels.items():
        if value and value.strip().lower() not in allowed:
            raise HTTPException(status_code=400, detail=f"{field_name} must be one of: {', '.join(sorted(allowed))}")
    allowed_techniques = {"straight", "vibrato", "breathy", "belting", "melismatic", "ornamented", "spoken", "rap"}
    invalid_techniques = sorted({value.strip().lower() for value in request.confirmed_vocal_techniques} - allowed_techniques)
    if invalid_techniques:
        raise HTTPException(status_code=400, detail=f"Unsupported confirmed vocal techniques: {', '.join(invalid_techniques)}")
    allowed_moods = {"romantic", "emotional", "intimate", "devotional", "uplifting", "energetic", "dark", "melancholic"}
    invalid_moods = sorted({value.strip().lower() for value in request.confirmed_moods} - allowed_moods)
    if invalid_moods:
        raise HTTPException(status_code=400, detail=f"Unsupported confirmed moods: {', '.join(invalid_moods)}")
    if request.explicit_training_consent:
        missing = []
        if not request.rights_confirmed:
            missing.append("rights_confirmed")
        if not request.corrected_language:
            missing.append("corrected_language")
        if not request.corrected_genre:
            missing.append("corrected_genre")
        if not request.dataset_usage_permission_version:
            missing.append("dataset_usage_permission_version")
        if not request.copyright_owner:
            missing.append("copyright_owner")
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"Training consent requires: {', '.join(missing)}.",
            )

    job = studio_v2_jobs.create_job(
        runtime_settings.skarly_output_dir,
        job_type="feedback",
        owner_id=user.user_id,
        upload_id=generation_job.get("upload_id"),
        analysis_id=generation_job.get("analysis_id"),
        request=request.model_dump(mode="json"),
    )
    warnings: list[str] = []
    retained_audio_path = None
    if request.explicit_training_consent:
        if not runtime_settings.training_feedback_enabled:
            warnings.append("Training collection is disabled in this environment; consent was recorded but no audio was retained.")
        else:
            try:
                vocal_path = _skarly_path_from_url(
                    str((generation_job.get("result") or {}).get("vocal_url") or ""),
                    runtime_settings.skarly_output_dir,
                )
                saved = training_feedback.save_opt_in_vocal_example(
                    vocal_path,
                    feedback_dir=runtime_settings.training_feedback_dir,
                    manifest_path=runtime_settings.training_feedback_manifest,
                    language=str(request.corrected_language),
                    genre=str(request.corrected_genre),
                    job_id=job["job_id"],
                    consent_metadata={
                        "contributor_id": user.user_id,
                        "consent_record_id": job["job_id"],
                        "copyright_owner": request.copyright_owner,
                        "permitted_training_use": "Skarly audio-classifier training",
                        "commercial_use_permission": request.commercial_use_permission,
                        "revocation_policy": request.revocation_policy or "Contact Skarly support to revoke future dataset use.",
                        "recording_conditions": request.recording_conditions,
                        "singer_id": request.singer_id or user.user_id,
                        "dataset_version": "creator-feedback-v2",
                        "dataset_usage_permission_version": request.dataset_usage_permission_version,
                        "quality_review_status": "pending",
                        "singing_speech": request.confirmed_singing_speech,
                        "vocal_techniques": request.confirmed_vocal_techniques,
                        "moods": request.confirmed_moods,
                        "tempo_family": request.confirmed_tempo_family,
                        "melodic_character": request.confirmed_melodic_character,
                        "in_distribution": request.confirmed_in_distribution,
                    },
                )
                retained_audio_path = str(saved.audio_path)
            except Exception as exc:
                warnings.append(f"Consent was recorded, but the training copy could not be retained: {str(exc)[:240]}")

    feedback_record = {
        **request.model_dump(mode="json"),
        "feedback_id": job["job_id"],
        "creator_id": user.user_id,
        "label_source": "human_confirmed",
        "retained_audio_path": retained_audio_path,
    }
    return studio_v2_jobs.update_job(
        runtime_settings.skarly_output_dir,
        job["job_id"],
        status="ready",
        stage="feedback_recorded",
        progress=100,
        warnings=warnings,
        result=feedback_record,
    )


@app.post("/v1/skarly/analyze", response_model=SkarlyStudioAnalyzeResponse)
def analyze_skarly_upload(request: SkarlyStudioAnalyzeRequest, user: UserContext = Depends(get_current_user)):
    try:
        upload_id = _resolve_skarly_upload_id(
            request.upload_id,
            raw_audio_path=request.raw_audio_path,
            user=user,
        )
        return skarly_studio.analyze_upload(
            upload_id=upload_id,
            uploads_dir=settings.uploads_dir,
            output_dir=settings.skarly_output_dir,
            ffmpeg_path=settings.ffmpeg_path,
            whisper_path=settings.whisper_path,
            whisper_model=settings.whisper_model,
            whisper_timeout_sec=settings.whisper_timeout_sec,
            melody_analyzer_backend=settings.melody_analyzer_backend,
            basic_pitch_path=settings.basic_pitch_path,
            basic_pitch_model_serialization=settings.basic_pitch_model_serialization,
            basic_pitch_save_note_events=settings.basic_pitch_save_note_events,
            melody_timeout_sec=settings.melody_timeout_sec,
            audio_classifier_checkpoint=settings.audio_classifier_checkpoint,
            audio_classifier_python_path=settings.audio_classifier_python_path,
            audio_classifier_timeout_sec=settings.audio_classifier_timeout_sec,
            language_override=request.language_override,
            mood_override=request.mood_override,
            url_for_path=_known_output_url,
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Upload not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/v1/skarly/generate", response_model=SkarlyStudioResponse)
def generate_skarly_versions(request: SkarlyStudioGenerateRequest, user: UserContext = Depends(get_current_user)):
    try:
        upload_id = _resolve_skarly_upload_id(
            request.upload_id,
            raw_audio_path=request.raw_audio_path,
            user=user,
        )
        return skarly_studio.generate_versions(
            upload_id=upload_id,
            uploads_dir=settings.uploads_dir,
            output_dir=settings.skarly_output_dir,
            ffmpeg_path=settings.ffmpeg_path,
            mixing_timeout_sec=settings.mixing_timeout_sec,
            generator_backend=settings.skarly_generator_backend,
            ace_step_base_url=settings.ace_step_base_url,
            ace_step_api_key=settings.ace_step_api_key,
            ace_step_timeout_seconds=settings.ace_step_timeout_seconds,
            ace_step_download_timeout_seconds=settings.ace_step_download_timeout_seconds,
            ace_step_poll_interval_seconds=settings.ace_step_poll_interval_seconds,
            ace_step_infer_step=settings.ace_step_infer_step,
            ace_step_guidance_scale=settings.ace_step_guidance_scale,
            ace_step_max_duration_seconds=settings.ace_step_max_duration_seconds,
            ace_step_use_source_audio=settings.ace_step_use_source_audio,
            ace_step_source_task_type=settings.ace_step_source_task_type,
            ace_step_source_audio_strength=settings.ace_step_source_audio_strength,
            ace_step_direct_enabled=settings.ace_step_direct_enabled,
            ace_step_repo_dir=settings.ace_step_repo_dir,
            ace_step_python_path=settings.ace_step_python_path,
            ace_step_fallback_to_procedural=settings.ace_step_fallback_to_procedural,
            require_cuda=settings.require_cuda,
            allow_cpu_generation_fallback=settings.allow_cpu_generation_fallback,
            whisper_path=settings.whisper_path,
            whisper_model=settings.whisper_model,
            whisper_timeout_sec=settings.whisper_timeout_sec,
            melody_analyzer_backend=settings.melody_analyzer_backend,
            basic_pitch_path=settings.basic_pitch_path,
            basic_pitch_model_serialization=settings.basic_pitch_model_serialization,
            basic_pitch_save_note_events=settings.basic_pitch_save_note_events,
            melody_timeout_sec=settings.melody_timeout_sec,
            audio_classifier_checkpoint=settings.audio_classifier_checkpoint,
            audio_classifier_python_path=settings.audio_classifier_python_path,
            audio_classifier_timeout_sec=settings.audio_classifier_timeout_sec,
            stem_separator_backend=settings.stem_separator_backend,
            demucs_path=settings.demucs_path,
            demucs_model=settings.demucs_model,
            demucs_two_stems=settings.demucs_two_stems,
            demucs_device=settings.demucs_device,
            separation_timeout_sec=settings.separation_timeout_sec,
            language=request.language,
            mood=request.mood,
            genre_override=request.genre_override,
            training_opt_in=request.training_opt_in,
            training_feedback_enabled=settings.training_feedback_enabled,
            training_feedback_dir=settings.training_feedback_dir,
            training_feedback_manifest=settings.training_feedback_manifest,
            mix_preset=request.mix_preset,
            arrangement_mode=request.arrangement_mode.value,
            preserve_original_vocal=request.preserve_original_vocal,
            reference_strength=request.reference_strength,
            verify_music_transform_vocals=settings.music_to_music_verify_generated_vocals,
            music_transform_vocal_threshold_db=settings.music_to_music_vocal_threshold_db,
            music_transform_min_vocal_activity=settings.music_to_music_min_vocal_activity,
            owner_id=user.user_id,
            preferred_style_families=_preferred_skarly_style_families(user, request.language),
            url_for_path=_known_output_url,
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Upload not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@app.post("/v1/skarly/jobs/{job_id}/select", response_model=JobResponse)
def select_skarly_version(
    job_id: str,
    request: SkarlyVersionSelectionRequest,
    user: UserContext = Depends(get_current_user),
):
    try:
        return _job_response(_save_selected_skarly_version(job_id, request.version_index, user))
    except PermissionError:
        raise HTTPException(status_code=403, detail="Skarly version belongs to another user")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Generated Skarly version was not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/v2/vocal-to-music", response_model=OnlineGenerationResponse)
def vocal_to_music(request: VocalToMusicRequest):
    created = producer_jobs.create_job(
        {
            "status": "generating",
            "progress": 0.15,
            "message": "Vocal-to-music generation started.",
            "generation_mode": "online_vocal_to_music",
            "online_request": request.model_dump(mode="json"),
        }
    )
    response = online_music.run_vocal_to_music(
        request,
        job_id=created["job_id"],
        settings=settings,
        upload_lookup=_lookup_upload,
        url_for_path=_known_output_url,
    )
    _store_online_generation_response(response)
    return response


@app.post("/v2/music-to-music", response_model=OnlineGenerationResponse)
def music_to_music(request: MusicToMusicRequest):
    created = producer_jobs.create_job(
        {
            "status": "generating",
            "progress": 0.15,
            "message": "Music-to-music generation started.",
            "generation_mode": "online_music_to_music",
            "online_request": request.model_dump(mode="json"),
        }
    )
    response = online_music.run_music_to_music(
        request,
        job_id=created["job_id"],
        settings=settings,
        upload_lookup=_lookup_upload,
        url_for_path=_known_output_url,
    )
    _store_online_generation_response(response)
    return response


@app.post("/v2/jobs/{job_id}/regenerate", response_model=OnlineGenerationResponse)
def regenerate_online_candidate(job_id: str, request: RegenerateMusicRequest):
    previous = producer_jobs.get_job(job_id)
    online_payload = previous.get("online_response") if previous else None
    if not online_payload:
        online_payload = online_job_store.load(settings.online_music_output_dir, job_id)
    if not online_payload:
        raise HTTPException(status_code=404, detail="Online generation job not found")
    previous_response = OnlineGenerationResponse.model_validate(online_payload)
    created = producer_jobs.create_job(
        {
            "status": "regenerating",
            "progress": 0.15,
            "message": "Candidate regeneration started.",
            "generation_mode": f"{previous_response.mode}_regenerate",
            "source_online_job_id": job_id,
            "online_request": request.model_dump(mode="json"),
        }
    )
    response = online_music.regenerate_online_job(
        previous_response=previous_response,
        request=request,
        settings=settings,
        upload_lookup=_lookup_upload,
        url_for_path=_known_output_url,
        job_id=created["job_id"],
    )
    _store_online_generation_response(response)
    return response


@app.post("/projects", response_model=ProjectResponse)
def create_project(request: ProjectCreateRequest):
    if not settings.projects_enabled:
        raise HTTPException(status_code=503, detail="Project saving is disabled.")
    try:
        return project_service.create_project(
            request,
            projects_dir=settings.projects_dir,
            allowed_dirs=_allowed_output_dirs(),
            url_for_path=_known_output_url,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/projects", response_model=ProjectListResponse)
def list_projects():
    if not settings.projects_enabled:
        return ProjectListResponse(projects=[], count=0)
    return project_service.list_projects(
        projects_dir=settings.projects_dir,
        limit=settings.max_projects_list,
        url_for_path=_known_output_url,
    )


@app.get("/projects/{project_id}", response_model=ProjectResponse)
def get_project(project_id: str):
    project = project_service.get_project(project_id, projects_dir=settings.projects_dir, url_for_path=_known_output_url)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@app.patch("/projects/{project_id}", response_model=ProjectResponse)
def update_project(project_id: str, request: ProjectUpdateRequest):
    try:
        project = project_service.update_project(
            project_id,
            request,
            projects_dir=settings.projects_dir,
            allowed_dirs=_allowed_output_dirs(),
            url_for_path=_known_output_url,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@app.delete("/projects/{project_id}")
def delete_project(project_id: str):
    deleted = project_service.delete_project(project_id, projects_dir=settings.projects_dir)
    if not deleted:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"status": "deleted", "project_id": project_id}


@app.post("/projects/from-job/{job_id}", response_model=ProjectResponse)
def create_project_from_job(job_id: str, name: str | None = Query(default=None, max_length=120)):
    if not settings.projects_enabled:
        raise HTTPException(status_code=503, detail="Project saving is disabled.")
    try:
        return project_service.create_project_from_job(
            job_id,
            job_lookup=producer_jobs.get_job,
            projects_dir=settings.projects_dir,
            allowed_dirs=_allowed_output_dirs(),
            url_for_path=_known_output_url,
            name=name,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Job not found")


@app.post("/exports", response_model=ExportResponse)
def create_export(request: ExportRequest):
    return export_service.create_export_manifest(
        request,
        exports_dir=settings.exports_dir,
        projects_dir=settings.projects_dir,
        project_lookup=lambda project_id: project_service.get_project(project_id, projects_dir=settings.projects_dir, url_for_path=_known_output_url),
        job_lookup=producer_jobs.get_job,
        url_for_path=_known_output_url,
        allowed_dirs=_allowed_output_dirs(),
        app_summary=_app_export_summary(),
    )


@app.get("/exports/{export_id}/manifest")
def get_export_manifest(export_id: str):
    manifest = export_service.get_export_manifest(export_id, exports_dir=settings.exports_dir)
    if manifest is None:
        raise HTTPException(status_code=404, detail="Export manifest not found")
    return manifest


@app.post("/cleanup", response_model=CleanupResponse)
def cleanup_outputs(request: CleanupRequest | None = None):
    cleanup_request = request or CleanupRequest()
    response = cleanup_service.cleanup_outputs(
        cleanup_request,
        allowed_dirs=_allowed_output_dirs(),
        default_retention_days=settings.output_retention_days,
    )
    if cleanup_request.include_mock_jobs:
        if cleanup_request.dry_run:
            response.warnings.append("Mock jobs would be cleared if dry_run=false.")
        else:
            producer_jobs.clear_jobs()
            response.warnings.append("Mock jobs cleared.")
    return response


@app.post("/mix", response_model=MixResponse)
def mix_vocal_backing(request: MixRequest | None = None):
    if request is None:
        quality_report = QualityReport(
            audio_exists=False,
            generator_name=MIXER_NAME,
            warnings=["vocal_audio_path and backing_audio_path are required."],
            validation_errors=["vocal_audio_path and backing_audio_path are required."],
            passed=False,
        )
        diagnostics = MixDiagnostics(
            status="mix_failed",
            warnings=["vocal_audio_path and backing_audio_path are required."],
            error_message="vocal_audio_path and backing_audio_path are required.",
            suggested_fix="Provide vocal_audio_path and backing_audio_path.",
        )
        return MixResponse(
            status="mix_failed",
            audio_export=AudioExport(quality_report=quality_report),
            quality_report=quality_report,
            diagnostics=diagnostics,
        )

    result = mix_vocal_with_backing(
        vocal_path=request.vocal_audio_path,
        backing_path=request.backing_audio_path,
        output_dir=settings.mix_output_dir,
        job_id=new_id("manual_mix"),
        vocal_gain_db=_float_or_default(request.vocal_gain_db, settings.mix_default_vocal_gain_db),
        backing_gain_db=_float_or_default(request.backing_gain_db, settings.mix_default_backing_gain_db),
        ducking_enabled=settings.mix_default_ducking_enabled if request.ducking_enabled is None else request.ducking_enabled,
        ducking_amount=_float_or_default(request.ducking_amount, settings.mix_default_ducking_amount),
        output_format=request.output_format or settings.mix_default_format,
        sample_rate=settings.mix_sample_rate,
    )
    backing_report = validate_audio_file(
        request.backing_audio_path,
        generator_name="manual_backing",
        fallback_used=False,
    )
    response = _mix_response_from_result(
        result=result,
        vocal_path=request.vocal_audio_path,
        backing_path=request.backing_audio_path,
        backing_url=_known_output_url(request.backing_audio_path),
        backing_quality_report=backing_report,
        vocal_gain_db=_float_or_default(request.vocal_gain_db, settings.mix_default_vocal_gain_db),
        backing_gain_db=_float_or_default(request.backing_gain_db, settings.mix_default_backing_gain_db),
        ducking_enabled=settings.mix_default_ducking_enabled if request.ducking_enabled is None else request.ducking_enabled,
        ducking_amount=_float_or_default(request.ducking_amount, settings.mix_default_ducking_amount),
    )
    return response


@app.post("/stems/separate", response_model=StemSeparationResponse)
def separate_stems_endpoint(request: StemSeparationRequest):
    return stems_service.separate_stems(
        audio_path=request.audio_path,
        output_dir=settings.stems_output_dir,
        job_id=new_id("stems"),
        stems=request.stems,
        engine=request.engine or settings.stems_engine,
        timeout_seconds=settings.stems_timeout_seconds,
        enabled=settings.stems_enabled,
        demucs_cli_path=settings.demucs_cli_path,
        demucs_model=settings.demucs_model,
        demucs_device=settings.demucs_device,
        url_for_path=_stem_output_url,
    )


@app.get("/stems/{job_id}", response_model=StemSeparationResponse)
def get_stems_for_job(job_id: str):
    safe_job_id = _safe_route_segment(job_id)
    stems_dir = stems_service.resolve_output_dir(settings.stems_output_dir) / safe_job_id
    if not stems_dir.exists() or not stems_dir.is_dir():
        return StemSeparationResponse(
            status="not_found",
            engine=settings.stems_engine,
            stems_dir=str(stems_dir),
            warnings=["No stored stems were found for this job."],
            diagnostics=GenerationDiagnostics(
                generator_name=settings.stems_engine,
                status="not_found",
                failed_step="stem_lookup",
                error_message="No stored stems were found for this job.",
                suggested_fix="Run /stems/separate for this audio first.",
            ),
        )

    discovered = stems_service.discover_stem_files(stems_dir, ["vocals", "drums", "bass", "other", "piano", "guitar"])
    stem_paths = {stem: str(path) for stem, path in discovered.items()}
    stem_urls = {stem: url for stem, path in discovered.items() if (url := _stem_output_url(str(path)))}
    quality_reports = {stem: validate_audio_file(path, generator_name=f"{settings.stems_engine}:{stem}") for stem, path in discovered.items()}
    warnings = _dedupe_strings(
        [
            f"{stem}: {warning}"
            for stem, report in quality_reports.items()
            for warning in [*report.validation_errors, *report.warnings]
        ]
    )
    return StemSeparationResponse(
        status="completed" if discovered else "not_found",
        engine=settings.stems_engine,
        stems_dir=str(stems_dir),
        stem_paths=stem_paths,
        stem_urls=stem_urls,
        quality_reports=quality_reports,
        warnings=warnings,
        diagnostics=GenerationDiagnostics(
            generator_name=settings.stems_engine,
            status="completed" if discovered else "not_found",
            failed_step=None if discovered else "stem_lookup",
            error_message=None if discovered else "No stem files were found in the stored folder.",
        ),
    )


@app.post("/sections/edit", response_model=SectionEditResponse)
def edit_section_endpoint(request: SectionEditRequest):
    return section_editor.edit_section(
        request,
        mode=settings.section_editing_mode,
        enabled=settings.section_editing_enabled,
        output_dir=settings.section_output_dir,
        timeout_seconds=settings.section_edit_timeout_seconds,
        ace_step_editor=lambda **kwargs: ace_step.edit_section(
            **kwargs,
            base_url=settings.ace_step_base_url,
            api_key=settings.ace_step_api_key,
            model=settings.ace_step_model,
            inference_steps=settings.ace_step_infer_step,
            guidance_scale=settings.ace_step_guidance_scale,
            poll_interval_seconds=settings.ace_step_poll_interval_seconds,
        ),
        url_for_path=_section_output_url,
    )


@app.post("/sections/prompt", response_model=SectionEditResponse)
def section_prompt_endpoint(request: SectionEditRequest):
    return section_editor.edit_section(
        request,
        mode="prompt_only",
        enabled=settings.section_editing_enabled,
        output_dir=settings.section_output_dir,
        timeout_seconds=settings.section_edit_timeout_seconds,
        url_for_path=_section_output_url,
    )


@app.post("/export")
def export_mock():
    return {"status": "not_implemented", "message": "Audio export will be added in a later phase."}


@app.get("/v1/local/capabilities")
def get_local_capabilities():
    return local_capabilities()


@app.post("/v1/local/agent")
async def local_agent(request: Request):
    return agent_generation_plan(await request.json())


@app.get("/v1/admin/summary", response_model=AdminSummaryResponse)
def admin_summary(user: UserContext = Depends(require_admin_user)):
    recent_jobs = jobs.list_recent(30)
    recent_voice_takes = voice_takes.list_recent(30)
    deleted_jobs = jobs.list_deleted_recent(30)
    deleted_voice_takes = voice_takes.list_deleted_recent(30)
    users_snapshot = users.list_recent(30)
    failed_jobs = [job for job in recent_jobs if job.status == JobStatus.failed]
    ready_jobs = [job for job in recent_jobs if job.status == JobStatus.ready]
    uploaded_takes = [take for take in recent_voice_takes if take.raw_audio_path]
    usage_key = _current_lyria_usage_key()
    generation_count = usage.get(usage_key)
    return AdminSummaryResponse(
        environment=settings.app_env,
        repository_backend=settings.repository_backend,
        storage_backend=settings.storage_backend,
        worker_backend=settings.worker_backend,
        music_generator_backend=settings.music_generator_backend,
        task_backend=settings.task_backend,
        bucket=settings.storage_bucket,
        users=users_snapshot,
        recent_jobs=recent_jobs,
        recent_voice_takes=recent_voice_takes,
        deleted_jobs=deleted_jobs,
        deleted_voice_takes=deleted_voice_takes,
        counts={
            "users": len(users_snapshot),
            "recent_jobs": len(recent_jobs),
            "ready_jobs": len(ready_jobs),
            "failed_jobs": len(failed_jobs),
            "voice_takes": len(recent_voice_takes),
            "uploaded_voice_takes": len(uploaded_takes),
            "deleted_jobs": len(deleted_jobs),
            "deleted_voice_takes": len(deleted_voice_takes),
        },
        cloud_cost=CloudCostSnapshot(
            period=usage_key.removeprefix("lyria_"),
            generations=generation_count,
            generation_limit=settings.lyria_monthly_limit,
            estimated_cost_usd=round(generation_count * settings.lyria_unit_cost_usd, 2),
            unit_cost_usd=settings.lyria_unit_cost_usd,
            generator_backend=settings.music_generator_backend,
        ),
        cloud_runtime=_cloud_runtime_snapshot(),
    )


@app.post("/v1/uploads/sign", response_model=SignedUploadResponse)
def sign_upload(request: SignedUploadRequest, user: UserContext = Depends(get_current_user)):
    return storage.create_signed_upload(storage_owner_id(user), request)


@app.put("/local-storage/upload/{object_path:path}", status_code=204)
@app.put("/test-storage/upload/{object_path:path}", status_code=204)
async def local_storage_upload(
    object_path: str,
    request: Request,
    content_type: str = Header(default="application/octet-stream"),
):
    _require_local_storage_backend()
    data = await request.body()
    if not data:
        raise HTTPException(status_code=400, detail="Audio upload body is empty")
    if len(data) > 20_000_000:
        raise HTTPException(status_code=413, detail="Audio file is larger than the 20 MB prototype limit")
    storage.upload_bytes(object_path, data, content_type)
    return Response(status_code=204)


@app.get("/local-storage/download/{object_path:path}")
@app.get("/test-storage/download/{object_path:path}")
def local_storage_download(object_path: str, download_name: str | None = Query(default=None)):
    _require_local_storage_backend()
    try:
        data = storage.download_bytes(object_path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Audio object not found")
    headers = {}
    if download_name:
        headers["Content-Disposition"] = f'attachment; filename="{download_name.replace(chr(34), chr(39))}"'
    return Response(content=data, media_type=_content_type_from_path(object_path), headers=headers)


@app.post("/v1/uploads/verify", response_model=UploadVerificationResponse)
def verify_upload(request: UploadVerificationRequest, user: UserContext = Depends(get_current_user)):
    if not _is_owned_raw_path(request.raw_audio_path, user):
        raise HTTPException(status_code=403, detail="Raw audio path belongs to another user")
    return UploadVerificationResponse(raw_audio_path=request.raw_audio_path, exists=storage.object_exists(request.raw_audio_path))


@app.post("/v1/uploads/bytes", response_model=UploadVerificationResponse)
async def upload_bytes(
    request: Request,
    raw_audio_path: str = Query(min_length=1),
    content_type: str = Query(default="audio/mpeg", min_length=1, max_length=80),
    user: UserContext = Depends(get_current_user),
):
    if not _is_owned_raw_path(raw_audio_path, user):
        raise HTTPException(status_code=403, detail="Raw audio path belongs to another user")
    data = await request.body()
    if not data:
        raise HTTPException(status_code=400, detail="Audio upload body is empty")
    if len(data) > 20_000_000:
        raise HTTPException(status_code=413, detail="Audio file is larger than the 20 MB prototype limit")
    storage.upload_bytes(raw_audio_path, data, content_type)
    return UploadVerificationResponse(raw_audio_path=raw_audio_path, exists=True)


@app.get("/v1/me", response_model=UserProfileResponse)
def get_profile(user: UserContext = Depends(get_current_user)):
    profile = users.get(user.user_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    return UserProfileResponse(profile=profile)


@app.put("/v1/me", response_model=UserProfileResponse)
def save_profile(request: UserProfileRequest, user: UserContext = Depends(get_current_user)):
    try:
        profile = users.upsert(user.user_id, request)
    except DuplicateEmailError:
        raise HTTPException(status_code=409, detail="Email already registered")
    return UserProfileResponse(profile=profile)


@app.post("/v1/jobs", response_model=JobResponse)
def create_job(request: CreateJobRequest, background_tasks: BackgroundTasks, user: UserContext = Depends(get_current_user)):
    if not _is_owned_raw_path(request.raw_audio_path, user):
        raise HTTPException(status_code=403, detail="Raw audio path belongs to another user")
    if not storage.object_exists(request.raw_audio_path):
        raise HTTPException(status_code=404, detail="Raw audio file was not uploaded. Upload the audio before generating.")

    timestamp = now_utc()
    job = JobRecord(
        job_id=new_id("job"),
        user_id=user.user_id,
        creator_mode=user.creator_mode,
        genre=request.genre,
        track_name=request.track_name,
        source_type=request.source_type,
        arrangement_mode=request.arrangement_mode,
        production_style=request.production_style,
        arrangement_style=request.arrangement_style,
        main_instruments=request.main_instruments,
        user_overrides=_request_user_overrides(request),
        raw_audio_path=request.raw_audio_path,
        status=JobStatus.queued,
        stage="queued",
        delete_raw_after_mix=request.delete_raw_after_mix,
        created_at=timestamp,
        updated_at=timestamp,
    )
    jobs.create(job)
    _enqueue_generation(job.job_id, background_tasks)
    return JobResponse(job=job)


@app.get("/v1/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: str, user: UserContext = Depends(get_current_user)):
    job = _require_owned_job(job_id, user)
    return _job_response(job)


@app.get("/v1/history", response_model=HistoryResponse)
def history(user: UserContext = Depends(get_current_user)):
    return HistoryResponse(tracks=[job for job in jobs.list_for_user(user.user_id) if _is_visible_library_job(job)])


@app.get("/v1/projects", response_model=HistoryResponse)
def projects(user: UserContext = Depends(get_current_user)):
    return HistoryResponse(tracks=[job for job in jobs.list_for_user(user.user_id) if _is_visible_library_job(job)])


@app.get("/v1/voice-takes", response_model=VoiceTakeListResponse)
def list_voice_takes(user: UserContext = Depends(get_current_user)):
    return VoiceTakeListResponse(takes=voice_takes.list_for_user(user.user_id))


@app.get("/v1/recycle-bin", response_model=RecycleBinResponse)
def recycle_bin(user: UserContext = Depends(get_current_user)):
    return RecycleBinResponse(
        voice_takes=voice_takes.list_deleted_for_user(user.user_id),
        tracks=jobs.list_deleted_for_user(user.user_id),
    )


@app.get("/v1/voice-takes/{take_id}/play", response_model=VoiceTakePlaybackResponse)
def play_voice_take(take_id: str, user: UserContext = Depends(get_current_user)):
    take = _require_owned_voice_take(take_id, user)
    return VoiceTakePlaybackResponse(take_id=take.take_id, raw_audio_url=storage.signed_download_url(take.raw_audio_path))


@app.post("/v1/voice-takes", response_model=VoiceTakeResponse)
def save_voice_take(request: VoiceTakeRequest, user: UserContext = Depends(get_current_user)):
    if not _is_owned_raw_path(request.raw_audio_path, user):
        raise HTTPException(status_code=403, detail="Raw audio path belongs to another user")
    if not storage.object_exists(request.raw_audio_path):
        raise HTTPException(status_code=404, detail="Raw audio file was not uploaded. Upload the audio before saving.")
    return VoiceTakeResponse(take=voice_takes.create(user.user_id, request))


@app.delete("/v1/voice-takes/{take_id}", response_model=VoiceTakeResponse)
def delete_voice_take(take_id: str, user: UserContext = Depends(get_current_user)):
    try:
        return VoiceTakeResponse(take=voice_takes.delete(user.user_id, take_id))
    except PermissionError:
        raise HTTPException(status_code=403, detail="Voice take belongs to another user")
    except KeyError:
        raise HTTPException(status_code=404, detail="Voice take not found")


@app.post("/v1/voice-takes/{take_id}/restore", response_model=VoiceTakeResponse)
def restore_voice_take(take_id: str, user: UserContext = Depends(get_current_user)):
    try:
        return VoiceTakeResponse(take=voice_takes.restore(user.user_id, take_id))
    except PermissionError:
        raise HTTPException(status_code=403, detail="Voice take belongs to another user")
    except KeyError:
        raise HTTPException(status_code=404, detail="Voice take not found")


@app.delete("/v1/voice-takes/{take_id}/permanent", response_model=VoiceTakeResponse)
def permanently_delete_voice_take(take_id: str, user: UserContext = Depends(get_current_user)):
    try:
        take = voice_takes.permanent_delete(user.user_id, take_id)
    except PermissionError:
        raise HTTPException(status_code=403, detail="Voice take belongs to another user")
    except KeyError:
        raise HTTPException(status_code=404, detail="Voice take not found")
    _delete_storage_object_if_present(take.raw_audio_path)
    return VoiceTakeResponse(take=take)


@app.post("/v1/library/recover", response_model=LibraryRecoveryResponse)
def recover_library(user: UserContext = Depends(get_current_user)):
    existing_jobs = jobs.list_for_user(user.user_id)
    existing_final_paths = {job.final_mp3_path for job in existing_jobs if job.final_mp3_path}

    recovered_takes = 0
    recovered_tracks = 0
    for final_prefix in user_final_prefixes(user):
        for object_path in storage.list_objects(final_prefix):
            if object_path in existing_final_paths:
                continue
            if not object_path.lower().endswith(".mp3"):
                continue
            if object_path.lower().endswith("/final.mp3"):
                continue
            timestamp = now_utc()
            job = JobRecord(
                job_id=new_id("recovered_job"),
                user_id=user.user_id,
                creator_mode=user.creator_mode,
                genre=Genre.lofi,
                track_name=_title_from_object_path(object_path, "Recovered Mix").removesuffix(".mp3"),
                source_type=SourceType.recording,
                raw_audio_path=None,
                final_mp3_path=object_path,
                status=JobStatus.ready,
                stage="ready",
                library_status="Saved",
                delete_raw_after_mix=True,
                created_at=timestamp,
                updated_at=timestamp,
                completed_at=timestamp,
            )
            jobs.create(job)
            existing_final_paths.add(object_path)
            recovered_tracks += 1

    return LibraryRecoveryResponse(
        recovered_voice_takes=recovered_takes,
        recovered_tracks=recovered_tracks,
        takes=voice_takes.list_for_user(user.user_id),
        tracks=jobs.list_for_user(user.user_id),
    )


@app.post("/v1/jobs/{job_id}/retry", response_model=JobResponse)
def retry_job(job_id: str, background_tasks: BackgroundTasks, user: UserContext = Depends(get_current_user)):
    job = _require_owned_job(job_id, user)
    if job.raw_audio_path is None:
        raise HTTPException(status_code=409, detail="Cannot retry because raw audio was deleted")
    jobs.update_status(job_id, JobStatus.queued, "queued")
    _enqueue_generation(job_id, background_tasks)
    return JobResponse(job=jobs.get(job_id))


@app.patch("/v1/jobs/{job_id}/library", response_model=JobResponse)
def update_job_library(job_id: str, request: UpdateJobLibraryRequest, user: UserContext = Depends(get_current_user)):
    _require_owned_job(job_id, user)
    job = jobs.update_library(job_id, request.track_name, request.library_status)
    return _job_response(job)


@app.delete("/v1/tracks/{track_id}", response_model=JobResponse)
def delete_track(track_id: str, user: UserContext = Depends(get_current_user)):
    _require_owned_job(track_id, user)
    return JobResponse(job=jobs.mark_deleted(track_id))


@app.post("/v1/library/cleanup-stale", response_model=HistoryResponse)
def cleanup_stale_library(user: UserContext = Depends(require_admin_user)):
    cleaned: list[JobRecord] = []
    for job in jobs.list_for_user(user.user_id):
        if _is_stale_library_job(job):
            cleaned.append(jobs.mark_deleted(job.job_id))
    return HistoryResponse(tracks=cleaned)


@app.post("/v1/tracks/{track_id}/restore", response_model=JobResponse)
def restore_track(track_id: str, user: UserContext = Depends(get_current_user)):
    _require_owned_job(track_id, user)
    return JobResponse(job=jobs.restore(track_id))


@app.delete("/v1/tracks/{track_id}/permanent", response_model=JobResponse)
def permanently_delete_track(track_id: str, user: UserContext = Depends(get_current_user)):
    job = _require_owned_job(track_id, user)
    deleted = jobs.permanent_delete(track_id)
    paths = [
        job.final_mp3_path,
        job.isolated_vocal_path,
        job.backing_audio_path,
        job.raw_audio_path,
        *job.export_paths.values(),
    ]
    for object_path in dict.fromkeys(path for path in paths if path):
        _delete_storage_object_if_present(object_path)
    return JobResponse(job=deleted)


@app.post("/v1/privacy/delete-raw/{job_id}", response_model=JobResponse)
def delete_raw(job_id: str, user: UserContext = Depends(get_current_user)):
    _require_owned_job(job_id, user)
    return JobResponse(job=jobs.delete_raw(job_id))


@app.post("/v1/worker/jobs/{job_id}/run", response_model=JobResponse)
def run_worker_job(job_id: str, x_skarly_worker_secret: str | None = Header(default=None)):
    _require_worker_access(x_skarly_worker_secret)
    try:
        job = worker.run_job(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_response(job)


def _optional_preset(preset_id: str | None) -> dict | None:
    if not preset_id:
        return None
    return _require_preset(preset_id)


def _require_preset(preset_id: str) -> dict:
    preset = get_preset_by_id(preset_id)
    if preset is None:
        raise HTTPException(status_code=404, detail=f"Preset '{preset_id}' not found")
    return preset


def _producer_job_response(job: dict) -> JobStatusResponse:
    return JobStatusResponse(
        job_id=job["job_id"],
        status=job["status"],
        progress=job.get("progress"),
        message=job.get("message"),
        positive_prompt=job.get("positive_prompt"),
        negative_prompt=job.get("negative_prompt"),
        structured_summary=job.get("structured_summary"),
        recommended_settings=job.get("recommended_settings"),
        generation_mode=job.get("generation_mode"),
        generated_audio_path=job.get("generated_audio_path"),
        audio_url=job.get("audio_url"),
        preview_url=job.get("preview_url"),
        backing_audio_path=job.get("backing_audio_path"),
        backing_audio_url=job.get("backing_audio_url"),
        mixed_preview_path=job.get("mixed_preview_path"),
        mixed_preview_url=job.get("mixed_preview_url"),
        final_mix_wav_path=job.get("final_mix_wav_path"),
        final_mix_mp3_path=job.get("final_mix_mp3_path"),
        final_mix_mp3_url=job.get("final_mix_mp3_url"),
        audio_export=job.get("audio_export"),
        diagnostics=job.get("diagnostics"),
        mix_diagnostics=job.get("mix_diagnostics"),
        quality_report=job.get("quality_report"),
        online_response=job.get("online_response"),
    )


def _lookup_upload(upload_id: str) -> AudioUploadResponse | None:
    return upload_service.get_upload(upload_id, uploads_dir=settings.uploads_dir, url_for_path=_known_output_url)


def _store_online_generation_response(response: OnlineGenerationResponse) -> dict:
    best = response.best_candidate
    quality_report = None
    if best:
        quality_report = best.mix_quality_report or best.quality_report
    audio_export = AudioExport(
        backing_audio_path=best.backing_audio_path if best else None,
        backing_audio_url=best.backing_audio_url if best else None,
        mixed_preview_path=best.mixed_preview_path if best else None,
        mixed_preview_url=best.mixed_preview_url if best else None,
        final_mix_wav_path=best.final_mix_wav_path if best else None,
        final_mix_mp3_path=best.final_mix_mp3_path if best else None,
        final_mix_mp3_url=best.final_mix_mp3_url if best else None,
        final_wav_path=best.final_mix_wav_path if best else None,
        final_mp3_path=best.final_mix_mp3_path if best else None,
        quality_report=quality_report,
        backing_quality_report=best.quality_report if best else None,
    )
    serialized_response = response.model_dump(mode="json")
    online_job_store.save(settings.online_music_output_dir, response.job_id, serialized_response)
    return producer_jobs.update_job(
        response.job_id,
        {
            "status": response.status,
            "progress": 1.0,
            "message": response.message,
            "generation_mode": response.mode,
            "generated_audio_path": best.backing_audio_path if best else None,
            "audio_url": best.mixed_preview_url or best.backing_audio_url if best else None,
            "preview_url": best.mixed_preview_url or best.backing_audio_url if best else None,
            "backing_audio_path": best.backing_audio_path if best else None,
            "backing_audio_url": best.backing_audio_url if best else None,
            "mixed_preview_path": best.mixed_preview_path if best else None,
            "mixed_preview_url": best.mixed_preview_url if best else None,
            "final_mix_wav_path": best.final_mix_wav_path if best else None,
            "final_mix_mp3_path": best.final_mix_mp3_path if best else None,
            "final_mix_mp3_url": best.final_mix_mp3_url if best else None,
            "positive_prompt": response.composition_plan.provider_prompt if response.composition_plan else None,
            "negative_prompt": response.composition_plan.negative_prompt if response.composition_plan else None,
            "structured_summary": response.composition_plan.model_dump(mode="json") if response.composition_plan else None,
            "recommended_settings": _online_recommended_settings(response),
            "diagnostics": response.diagnostics.model_dump(mode="json") if response.diagnostics else None,
            "quality_report": quality_report.model_dump(mode="json") if quality_report else None,
            "audio_export": audio_export.model_dump(mode="json"),
            "online_response": serialized_response,
        },
    )


def _online_recommended_settings(response: OnlineGenerationResponse) -> dict:
    plan = response.composition_plan
    if not plan:
        return {}
    return {
        "provider_order": list(plan.provider_preferences),
        "bpm": plan.bpm,
        "key": plan.key,
        "duration_seconds": plan.duration_seconds,
        "production_style": plan.production_style,
        "arrangement_style": plan.arrangement_style,
        "instruments": list(plan.instruments),
        "mix_direction": plan.mix_direction,
        "best_candidate_id": response.best_candidate.candidate_id if response.best_candidate else None,
        "best_provider": response.best_candidate.provider_name if response.best_candidate else None,
    }


def _complete_generated_backing(
    *,
    job_id: str,
    request: PromptPreviewRequest,
    status: str,
    message: str,
    generation_mode: str,
    backing_path: str | None,
    backing_url: str | None,
    backing_quality_report: QualityReport,
    generation_diagnostics: GenerationDiagnostics,
) -> JobStatusResponse:
    audio_export = _audio_export_for_output(backing_path, backing_quality_report)
    audio_export.backing_audio_path = backing_path
    audio_export.backing_audio_url = backing_url
    audio_export.backing_quality_report = backing_quality_report

    vocal_path = (request.vocal_audio_path or "").strip()
    if not vocal_path:
        completed = producer_jobs.update_job(
            job_id,
            {
                "status": status,
                "progress": 1.0,
                "message": message,
                "generation_mode": generation_mode,
                "generated_audio_path": backing_path,
                "audio_url": backing_url,
                "preview_url": backing_url,
                "backing_audio_path": backing_path,
                "backing_audio_url": backing_url,
                "audio_export": audio_export.model_dump(),
                "diagnostics": generation_diagnostics.model_dump(),
                "quality_report": backing_quality_report.model_dump(),
            },
        )
        return _producer_job_response(completed)

    return _mix_generated_backing(
        job_id=job_id,
        request=request,
        status=status,
        message=message,
        generation_mode=generation_mode,
        backing_path=backing_path,
        backing_url=backing_url,
        backing_quality_report=backing_quality_report,
        generation_diagnostics=generation_diagnostics,
    )


def _mix_generated_backing(
    *,
    job_id: str,
    request: PromptPreviewRequest,
    status: str,
    message: str,
    generation_mode: str,
    backing_path: str | None,
    backing_url: str | None,
    backing_quality_report: QualityReport,
    generation_diagnostics: GenerationDiagnostics,
) -> JobStatusResponse:
    vocal_path = (request.vocal_audio_path or "").strip()
    vocal_gain_db = _float_or_default(request.vocal_gain_db, settings.mix_default_vocal_gain_db)
    backing_gain_db = _float_or_default(request.backing_gain_db, settings.mix_default_backing_gain_db)
    ducking_enabled = request.ducking_enabled if "ducking_enabled" in request.model_fields_set else settings.mix_default_ducking_enabled
    ducking_amount = _float_or_default(request.ducking_amount, settings.mix_default_ducking_amount)

    vocal_report = validate_audio_file(
        vocal_path,
        generator_name="vocal_input",
        fallback_used=False,
    )
    if not vocal_report.passed:
        mix_diagnostics = MixDiagnostics(
            status="mix_failed",
            vocal_path=vocal_path,
            backing_path=backing_path,
            vocal_gain_db=vocal_gain_db,
            backing_gain_db=backing_gain_db,
            ducking_enabled=ducking_enabled,
            ducking_amount=ducking_amount,
            warnings=[*vocal_report.validation_errors, *vocal_report.warnings],
            error_message=f"Vocal validation failed: {_validation_failure_summary(vocal_report)}",
            suggested_fix=_vocal_validation_suggested_fix(vocal_report),
        )
        return _update_generated_mix_failure(
            job_id=job_id,
            generation_mode=generation_mode,
            backing_path=backing_path,
            backing_url=backing_url,
            backing_quality_report=backing_quality_report,
            generation_diagnostics=generation_diagnostics,
            mix_diagnostics=mix_diagnostics,
        )

    result = mix_vocal_with_backing(
        vocal_path=vocal_path,
        backing_path=backing_path or "",
        output_dir=settings.mix_output_dir,
        job_id=job_id,
        vocal_gain_db=vocal_gain_db,
        backing_gain_db=backing_gain_db,
        ducking_enabled=ducking_enabled,
        ducking_amount=ducking_amount,
        output_format=settings.mix_preview_format or settings.mix_default_format,
        sample_rate=settings.mix_sample_rate,
    )
    expected_duration = int(round(backing_quality_report.duration_seconds)) if backing_quality_report.duration_seconds else None
    mix_quality_report = (
        validate_audio_file(
            result.preview_path or result.final_wav_path,
            expected_duration_seconds=expected_duration,
            generator_name=MIXER_NAME,
            fallback_used=backing_quality_report.fallback_used,
        )
        if result.success
        else _basic_mix_quality_report(result)
    )
    mix_diagnostics = _mix_diagnostics_from_result(
        result=result,
        quality_report=mix_quality_report,
        vocal_path=vocal_path,
        backing_path=backing_path,
        vocal_gain_db=vocal_gain_db,
        backing_gain_db=backing_gain_db,
        ducking_enabled=ducking_enabled,
        ducking_amount=ducking_amount,
    )
    if not result.success or not mix_quality_report.passed:
        return _update_generated_mix_failure(
            job_id=job_id,
            generation_mode=generation_mode,
            backing_path=backing_path,
            backing_url=backing_url,
            backing_quality_report=backing_quality_report,
            generation_diagnostics=generation_diagnostics,
            mix_diagnostics=mix_diagnostics,
        )

    audio_export = _audio_export_for_mix(
        result=result,
        quality_report=mix_quality_report,
        backing_path=backing_path,
        backing_url=backing_url,
        backing_quality_report=backing_quality_report,
    )
    mixed_preview_url = audio_export.mixed_preview_url
    final_mix_mp3_url = audio_export.final_mix_mp3_url
    completed = producer_jobs.update_job(
        job_id,
        {
            "status": status,
            "progress": 1.0,
            "message": f"{message} Vocal/backing mix completed.",
            "generation_mode": generation_mode,
            "generated_audio_path": backing_path,
            "audio_url": mixed_preview_url or backing_url,
            "preview_url": mixed_preview_url or backing_url,
            "backing_audio_path": backing_path,
            "backing_audio_url": backing_url,
            "mixed_preview_path": result.preview_path,
            "mixed_preview_url": mixed_preview_url,
            "final_mix_wav_path": result.final_wav_path,
            "final_mix_mp3_path": result.final_mp3_path,
            "final_mix_mp3_url": final_mix_mp3_url,
            "audio_export": audio_export.model_dump(),
            "diagnostics": generation_diagnostics.model_dump(),
            "mix_diagnostics": mix_diagnostics.model_dump(),
            "quality_report": mix_quality_report.model_dump(),
        },
    )
    return _producer_job_response(completed)


def _update_generated_mix_failure(
    *,
    job_id: str,
    generation_mode: str,
    backing_path: str | None,
    backing_url: str | None,
    backing_quality_report: QualityReport,
    generation_diagnostics: GenerationDiagnostics,
    mix_diagnostics: MixDiagnostics,
) -> JobStatusResponse:
    audio_export = _audio_export_for_output(backing_path, backing_quality_report)
    audio_export.backing_audio_path = backing_path
    audio_export.backing_audio_url = backing_url
    audio_export.backing_quality_report = backing_quality_report
    failed_diagnostics = _diagnostics_for_mix_failure(generation_diagnostics, mix_diagnostics)
    failed = producer_jobs.update_job(
        job_id,
        {
            "status": "mix_failed",
            "progress": 1.0,
            "message": "Backing audio was generated, but vocal/backing mix failed.",
            "generation_mode": generation_mode,
            "generated_audio_path": backing_path,
            "audio_url": backing_url,
            "preview_url": backing_url,
            "backing_audio_path": backing_path,
            "backing_audio_url": backing_url,
            "audio_export": audio_export.model_dump(),
            "diagnostics": failed_diagnostics.model_dump(),
            "mix_diagnostics": mix_diagnostics.model_dump(),
            "quality_report": backing_quality_report.model_dump(),
        },
    )
    return _producer_job_response(failed)


def _attempt_procedural_fallback(
    *,
    job_id: str,
    request: PromptPreviewRequest,
    preview: dict,
    summary: dict,
    fallback_reason: str,
    original_diagnostics: GenerationDiagnostics,
    original_quality_report: QualityReport,
) -> JobStatusResponse:
    producer_jobs.update_job(
        job_id,
        {
            "status": "fallback_pending",
            "progress": 0.85,
            "message": "ACE-Step failed or failed validation. procedural_v2 fallback started.",
        },
    )

    try:
        fallback_result = procedural_v2.generate_backing(
            job_id=job_id,
            output_dir=settings.procedural_output_dir,
            duration_seconds=_int_or_default(summary.get("duration_seconds") or request.duration_seconds, 90),
            bpm=_int_or_default(summary.get("bpm") or request.bpm, 88),
            key=summary.get("key") or request.key,
            genre=summary.get("genre") or request.genre,
            production_style=summary.get("production_style") or request.production_style,
            arrangement_style=summary.get("arrangement_style") or request.arrangement_style,
            instruments=list(summary.get("instruments") or request.instruments or []),
            mood_tags=list(summary.get("mood_tags") or request.mood_tags or []),
        )
    except Exception as exc:
        now = now_utc()
        fallback_result = procedural_v2.GenerationResult(
            success=False,
            output_path=None,
            generator_name=procedural_v2.GENERATOR_NAME,
            started_at=now,
            finished_at=now,
            duration_seconds=0.0,
            error_message=f"procedural_v2 wrapper crashed safely: {exc}",
            logs=[],
            suggested_fix="Check PROCEDURAL_OUTPUT_DIR permissions and procedural fallback settings.",
        )

    if fallback_result.success:
        quality_report = validate_audio_file(
            fallback_result.output_path,
            expected_duration_seconds=summary.get("duration_seconds"),
            generator_name=procedural_v2.GENERATOR_NAME,
            fallback_used=True,
        )
    else:
        quality_report = _basic_procedural_quality_report(fallback_result)

    audio_url = _procedural_output_url(fallback_result.output_path) if _safe_existing_procedural_output(fallback_result.output_path) else None
    audio_export = _audio_export_for_output(fallback_result.output_path, quality_report)
    if fallback_result.success and quality_report.passed:
        diagnostics = _diagnostics_for_fallback_success(
            fallback_result=fallback_result,
            fallback_reason=fallback_reason,
            original_diagnostics=original_diagnostics,
            original_quality_report=original_quality_report,
        )
        return _complete_generated_backing(
            job_id=job_id,
            request=request,
            status="completed_fallback",
            message="ACE-Step failed or failed validation, so procedural_v2 fallback audio was generated.",
            generation_mode="procedural_v2_fallback",
            backing_path=fallback_result.output_path,
            backing_url=audio_url,
            backing_quality_report=quality_report,
            generation_diagnostics=diagnostics,
        )

    diagnostics = _diagnostics_for_fallback_failure(
        fallback_result=fallback_result,
        quality_report=quality_report,
        fallback_reason=fallback_reason,
        original_diagnostics=original_diagnostics,
        original_quality_report=original_quality_report,
    )
    failed = producer_jobs.update_job(
        job_id,
        {
            "status": "failed",
            "progress": 1.0,
            "message": "ACE-Step failed and procedural_v2 fallback also failed.",
            "generation_mode": "procedural_v2_fallback",
            "generated_audio_path": fallback_result.output_path,
            "audio_url": audio_url,
            "preview_url": audio_url,
            "audio_export": audio_export.model_dump(),
            "diagnostics": diagnostics.model_dump(),
            "quality_report": quality_report.model_dump(),
        },
    )
    return _producer_job_response(failed)


def _diagnostics_from_ace_result(result: ace_step.GenerationResult) -> GenerationDiagnostics:
    return GenerationDiagnostics(
        generator_name=result.generator_name,
        status="success" if result.success else "failed",
        started_at=result.started_at,
        finished_at=result.finished_at,
        duration_seconds=result.duration_seconds,
        failed_step=None if result.success else "ace_step_generation",
        error_message=result.error_message,
        fallback_used=False,
        fallback_reason=None,
        last_logs=list(result.logs or [])[-40:],
        suggested_fix=result.suggested_fix
        or (
            None
            if result.success
            else "Set ACE_STEP_ENABLED=false to return to mock mode, check ACE_STEP_CLI_PATH, or try a shorter duration."
        ),
        command_used=result.command_used,
    )


def _diagnostics_for_validation_failure(result: ace_step.GenerationResult, quality_report: QualityReport) -> GenerationDiagnostics:
    summary = _validation_failure_summary(quality_report)
    return GenerationDiagnostics(
        generator_name=result.generator_name,
        status="failed_validation",
        started_at=result.started_at,
        finished_at=result.finished_at,
        duration_seconds=result.duration_seconds,
        failed_step="audio_validation",
        error_message=summary,
        fallback_used=False,
        fallback_reason=None,
        last_logs=list(result.logs or [])[-40:],
        suggested_fix=_validation_suggested_fix(quality_report),
        command_used=result.command_used,
    )


def _diagnostics_for_fallback_success(
    *,
    fallback_result: procedural_v2.GenerationResult,
    fallback_reason: str,
    original_diagnostics: GenerationDiagnostics,
    original_quality_report: QualityReport,
) -> GenerationDiagnostics:
    return GenerationDiagnostics(
        generator_name=fallback_result.generator_name,
        status="fallback_success",
        started_at=fallback_result.started_at,
        finished_at=fallback_result.finished_at,
        duration_seconds=fallback_result.duration_seconds,
        failed_step=None,
        error_message=None,
        fallback_used=True,
        fallback_reason=fallback_reason,
        last_logs=_fallback_logs(original_diagnostics, original_quality_report, fallback_result),
        suggested_fix="ACE-Step failed, so procedural_v2 fallback was used. Check ACE-Step configuration for higher-quality generation.",
    )


def _diagnostics_for_fallback_failure(
    *,
    fallback_result: procedural_v2.GenerationResult,
    quality_report: QualityReport,
    fallback_reason: str,
    original_diagnostics: GenerationDiagnostics,
    original_quality_report: QualityReport,
) -> GenerationDiagnostics:
    validation_summary = None if quality_report.passed else _validation_failure_summary(quality_report)
    error_message = fallback_result.error_message or f"procedural_v2 output failed validation: {validation_summary}"
    return GenerationDiagnostics(
        generator_name=fallback_result.generator_name,
        status="fallback_failed",
        started_at=fallback_result.started_at,
        finished_at=fallback_result.finished_at,
        duration_seconds=fallback_result.duration_seconds,
        failed_step="procedural_v2_generation",
        error_message=error_message,
        fallback_used=True,
        fallback_reason=fallback_reason,
        last_logs=_fallback_logs(original_diagnostics, original_quality_report, fallback_result, quality_report),
        suggested_fix=fallback_result.suggested_fix
        or "ACE-Step and procedural_v2 fallback both failed. Check output directory permissions and generator settings.",
    )


def _diagnostics_for_mix_failure(
    generation_diagnostics: GenerationDiagnostics,
    mix_diagnostics: MixDiagnostics,
) -> GenerationDiagnostics:
    logs = list(generation_diagnostics.last_logs or [])[-20:]
    logs.append(f"Mix status: {mix_diagnostics.status}")
    if mix_diagnostics.error_message:
        logs.append(f"Mix error: {mix_diagnostics.error_message}")
    logs.extend(f"Mix warning: {warning}" for warning in mix_diagnostics.warnings[-8:])
    return GenerationDiagnostics(
        generator_name=generation_diagnostics.generator_name,
        status="mix_failed",
        started_at=generation_diagnostics.started_at,
        finished_at=now_utc(),
        duration_seconds=generation_diagnostics.duration_seconds,
        failed_step="vocal_backing_mix",
        error_message=mix_diagnostics.error_message,
        fallback_used=generation_diagnostics.fallback_used,
        fallback_reason=generation_diagnostics.fallback_reason,
        last_logs=logs[-40:],
        suggested_fix=mix_diagnostics.suggested_fix,
        command_used=generation_diagnostics.command_used,
    )


def _mix_response_from_result(
    *,
    result: MixResult,
    vocal_path: str,
    backing_path: str,
    backing_url: str | None,
    backing_quality_report: QualityReport,
    vocal_gain_db: float,
    backing_gain_db: float,
    ducking_enabled: bool,
    ducking_amount: float,
) -> MixResponse:
    expected_duration = int(round(backing_quality_report.duration_seconds)) if backing_quality_report.duration_seconds else None
    quality_report = (
        validate_audio_file(
            result.preview_path or result.final_wav_path,
            expected_duration_seconds=expected_duration,
            generator_name=MIXER_NAME,
            fallback_used=False,
        )
        if result.success
        else _basic_mix_quality_report(result)
    )
    diagnostics = _mix_diagnostics_from_result(
        result=result,
        quality_report=quality_report,
        vocal_path=vocal_path,
        backing_path=backing_path,
        vocal_gain_db=vocal_gain_db,
        backing_gain_db=backing_gain_db,
        ducking_enabled=ducking_enabled,
        ducking_amount=ducking_amount,
    )
    audio_export = (
        _audio_export_for_mix(
            result=result,
            quality_report=quality_report,
            backing_path=backing_path,
            backing_url=backing_url,
            backing_quality_report=backing_quality_report,
        )
        if result.success
        else AudioExport(
            backing_audio_path=backing_path,
            backing_audio_url=backing_url,
            quality_report=quality_report,
            backing_quality_report=backing_quality_report,
        )
    )
    status = "mix_success" if result.success and quality_report.passed else "mix_failed"
    diagnostics.status = status
    return MixResponse(
        status=status,
        audio_export=audio_export,
        quality_report=quality_report,
        diagnostics=diagnostics,
    )


def _mix_diagnostics_from_result(
    *,
    result: MixResult,
    quality_report: QualityReport,
    vocal_path: str,
    backing_path: str | None,
    vocal_gain_db: float,
    backing_gain_db: float,
    ducking_enabled: bool,
    ducking_amount: float,
) -> MixDiagnostics:
    warnings = [*result.warnings]
    if not quality_report.passed:
        warnings.extend(quality_report.validation_errors or quality_report.warnings)
    status = "mix_success" if result.success and quality_report.passed else "mix_failed"
    error_message = result.error_message
    if result.success and not quality_report.passed:
        error_message = f"Mixed output failed validation: {_validation_failure_summary(quality_report)}"
    suggested_fix = result.suggested_fix
    if not suggested_fix and error_message:
        suggested_fix = _mix_suggested_fix(error_message, quality_report)
    return MixDiagnostics(
        status=status,
        vocal_path=vocal_path,
        backing_path=backing_path,
        preview_path=result.preview_path,
        final_wav_path=result.final_wav_path,
        final_mp3_path=result.final_mp3_path,
        vocal_gain_db=vocal_gain_db,
        backing_gain_db=backing_gain_db,
        ducking_enabled=ducking_enabled,
        ducking_amount=ducking_amount,
        duration_seconds=result.duration_seconds,
        warnings=_dedupe_strings(warnings),
        error_message=error_message,
        suggested_fix=suggested_fix,
    )


def _fallback_logs(
    original_diagnostics: GenerationDiagnostics,
    original_quality_report: QualityReport,
    fallback_result: procedural_v2.GenerationResult,
    fallback_quality_report: QualityReport | None = None,
) -> list[str]:
    logs: list[str] = []
    if original_diagnostics.failed_step:
        logs.append(f"Original failed step: {original_diagnostics.failed_step}")
    if original_diagnostics.error_message:
        logs.append(f"ACE-Step issue: {original_diagnostics.error_message}")
    if original_quality_report.validation_errors:
        logs.append(f"ACE-Step validation errors: {'; '.join(original_quality_report.validation_errors[:4])}")
    elif original_quality_report.warnings:
        logs.append(f"ACE-Step warnings: {'; '.join(original_quality_report.warnings[:4])}")
    logs.extend(f"ACE-Step log: {line}" for line in list(original_diagnostics.last_logs or [])[-12:])
    if fallback_result.error_message:
        logs.append(f"procedural_v2 error: {fallback_result.error_message}")
    logs.extend(f"procedural_v2 log: {line}" for line in list(fallback_result.logs or [])[-18:])
    if fallback_quality_report and not fallback_quality_report.passed:
        logs.append(f"procedural_v2 validation errors: {'; '.join(fallback_quality_report.validation_errors[:4])}")
    return logs[-40:]


def _validation_failure_summary(quality_report: QualityReport) -> str:
    errors = quality_report.validation_errors or quality_report.warnings
    if not errors:
        return "Generated audio failed validation."
    return "; ".join(errors[:3])


def _validation_suggested_fix(quality_report: QualityReport) -> str:
    text = " ".join([*quality_report.validation_errors, *quality_report.warnings]).lower()
    if "does not exist" in text or "missing" in text:
        return "ACE-Step completed but did not produce the expected output file. Check ACE_STEP_OUTPUT_DIR and ACE-Step CLI output arguments."
    if "decoded" in text:
        return "Generated file exists but could not be decoded. Check ACE-Step output format and FFmpeg/audio dependencies."
    if "silent" in text:
        return "Generated audio appears silent. Try a stronger prompt, shorter duration, or check ACE-Step model output."
    if "short" in text:
        return "Generated audio is much shorter than requested. Try reducing duration or increasing ACE_STEP_TIMEOUT_SECONDS."
    if "clipping" in text:
        return "Generated audio is clipping. Lower generator gain or normalize during post-processing in a later phase."
    return "Inspect the quality report warnings, try a shorter duration, or set ACE_STEP_ENABLED=false to return to mock mode."


def _basic_ace_quality_report(result: ace_step.GenerationResult) -> QualityReport:
    output_exists = bool(result.output_path and Path(result.output_path).exists())
    warnings: list[str] = []
    if not output_exists:
        warnings.append("ACE-Step output file is missing.")
    if result.error_message:
        warnings.append(result.error_message)
    return QualityReport(
        audio_exists=output_exists,
        generator_name="ACE-Step",
        fallback_used=False,
        warnings=warnings,
        passed=output_exists and result.success,
    )


def _basic_procedural_quality_report(result: procedural_v2.GenerationResult) -> QualityReport:
    output_exists = bool(result.output_path and Path(result.output_path).exists())
    warnings: list[str] = []
    if not output_exists:
        warnings.append("procedural_v2 output file is missing.")
    if result.error_message:
        warnings.append(result.error_message)
    return QualityReport(
        audio_exists=output_exists,
        generator_name=procedural_v2.GENERATOR_NAME,
        fallback_used=True,
        warnings=warnings,
        validation_errors=list(warnings),
        passed=False,
    )


def _basic_mix_quality_report(result: MixResult) -> QualityReport:
    warnings: list[str] = []
    if result.error_message:
        warnings.append(result.error_message)
    warnings.extend(result.warnings)
    output_exists = bool(result.preview_path and Path(result.preview_path).exists())
    if not output_exists:
        warnings.append("Mixed output file is missing.")
    return QualityReport(
        audio_exists=output_exists,
        generator_name=MIXER_NAME,
        fallback_used=False,
        warnings=_dedupe_strings(warnings),
        validation_errors=_dedupe_strings(warnings),
        passed=False,
    )


def _owned_ready_v2_generation(job_id: str, user: UserContext, output_dir: str) -> dict:
    job = studio_v2_jobs.get_job(output_dir, job_id)
    if job is None or job.get("job_type") != "generation":
        raise HTTPException(status_code=404, detail="Generation job not found")
    if job.get("owner_id") != user.user_id:
        raise HTTPException(status_code=403, detail="Generation job belongs to another user")
    if job.get("status") != "ready" or not isinstance(job.get("result"), dict):
        raise HTTPException(status_code=409, detail="Generation must be ready before this operation")
    return job


def _run_skarly_v2_mix_job(
    job_id: str,
    *,
    generation_job: dict,
    request: SkarlyV2MixRequest,
    runtime_settings,
) -> None:
    output_dir = runtime_settings.skarly_output_dir
    report_progress = studio_v2_jobs.progress_callback(output_dir, job_id)
    try:
        report_progress(stage="loading_existing_stems", progress=5)
        generation_result = generation_job.get("result") or {}
        versions = generation_result.get("versions") or []
        version = versions[request.version_index]
        vocal_url = str(generation_result.get("vocal_url") or version.get("input_vocal_url") or "")
        vocal_path = _skarly_path_from_url(vocal_url, output_dir)
        backing_path = _skarly_path_from_url(str(version.get("backing_url") or ""), output_dir)
        remix_id = new_id("remix").split("_", 1)[1][:12]
        output_path = backing_path.parent / f"remix_{request.version_index + 1}_{remix_id}.mp3"
        report_progress(stage="mixing_vocals", progress=30)
        adaptive = skarly_studio.mix_vocal_forward(
            vocal_path=vocal_path,
            backing_path=backing_path,
            output_path=output_path,
            preset_name=skarly_studio.normalize_mix_preset(request.mix_profile),
            vocal_music_balance=request.vocal_music_balance,
            ffmpeg_path=runtime_settings.ffmpeg_path,
            timeout_sec=runtime_settings.mixing_timeout_sec,
        )
        report_progress(stage="mastering", progress=82)
        duration = float(skarly_studio.safe_duration_seconds(output_path) or 0)
        source_duration = float(skarly_studio.safe_duration_seconds(vocal_path) or 0)
        if source_duration and abs(duration - source_duration) > max(0.05, source_duration * 0.001):
            raise RuntimeError(
                f"Remix duration {duration:.3f}s did not match the source vocal duration {source_duration:.3f}s."
            )
        output_url = skarly_studio.skarly_output_url(output_path, Path(output_dir).resolve())
        report_progress(stage="preparing_exports", progress=96)
        result = {
            "generation_id": generation_job["job_id"],
            "version_index": request.version_index,
            "arrangement_name": version.get("name"),
            "mix_profile": request.mix_profile,
            "vocal_music_balance": request.vocal_music_balance,
            "final_mix_url": output_url,
            "duration_seconds": duration,
            "mix_note": adaptive.note,
            "regenerated_arrangement": False,
        }
        # Persist an adaptive remix back onto the parent generation.  This
        # keeps exports, history, and a reopened result screen on the remixed
        # vocal version instead of silently reverting to the old backing.
        latest_generation = studio_v2_jobs.get_job(output_dir, generation_job["job_id"]) or generation_job
        updated_generation_result = deepcopy(latest_generation.get("result") or generation_result)
        updated_versions = list(updated_generation_result.get("versions") or [])
        updated_version = dict(updated_versions[request.version_index])
        updated_version["final_mix_url"] = output_url
        updated_version["mix_note"] = adaptive.note
        updated_versions[request.version_index] = updated_version
        updated_generation_result["versions"] = updated_versions
        updated_generation_result["vocal_url"] = vocal_url
        source_preparation = dict(updated_generation_result.get("source_preparation") or {})
        if source_preparation:
            source_preparation["vocal_preserved"] = True
            updated_generation_result["source_preparation"] = source_preparation
        studio_v2_jobs.update_job(
            output_dir,
            generation_job["job_id"],
            result=updated_generation_result,
            completed_outputs=[
                {
                    "index": index,
                    "name": item.get("name"),
                    "style_family": item.get("style_family"),
                    "backing_url": item.get("backing_url"),
                    "final_mix_url": item.get("final_mix_url"),
                }
                for index, item in enumerate(updated_versions, start=1)
            ],
        )
        studio_v2_jobs.update_job(
            output_dir,
            job_id,
            status="ready",
            stage="ready",
            progress=100,
            model="adaptive-vocal-mixer",
            completed_duration_seconds=duration,
            completed_outputs=[{"index": 1, "name": version.get("name"), "final_mix_url": output_url}],
            result=result,
            error=None,
        )
    except Exception as exc:
        _fail_skarly_v2_job(output_dir, job_id, exc)


def _run_skarly_v2_analysis_job(
    job_id: str,
    *,
    upload_id: str,
    owner_id: str,
    request: SkarlyV2AnalyzeRequest,
    runtime_settings,
) -> None:
    del owner_id
    output_dir = runtime_settings.skarly_output_dir
    report_progress = studio_v2_jobs.progress_callback(output_dir, job_id)
    try:
        report_progress(stage="validating_input", progress=2)
        report_progress(stage="analysing_complete_vocal", progress=8)
        result = skarly_studio.analyze_upload(
            upload_id=upload_id,
            uploads_dir=runtime_settings.uploads_dir,
            output_dir=runtime_settings.skarly_output_dir,
            ffmpeg_path=runtime_settings.ffmpeg_path,
            whisper_path=runtime_settings.whisper_path,
            whisper_model=runtime_settings.whisper_model,
            whisper_timeout_sec=runtime_settings.whisper_timeout_sec,
            melody_analyzer_backend=runtime_settings.melody_analyzer_backend,
            basic_pitch_path=runtime_settings.basic_pitch_path,
            basic_pitch_model_serialization=runtime_settings.basic_pitch_model_serialization,
            basic_pitch_save_note_events=runtime_settings.basic_pitch_save_note_events,
            melody_timeout_sec=runtime_settings.melody_timeout_sec,
            audio_classifier_checkpoint=runtime_settings.audio_classifier_checkpoint,
            audio_classifier_python_path=runtime_settings.audio_classifier_python_path,
            audio_classifier_timeout_sec=runtime_settings.audio_classifier_timeout_sec,
            language_override=request.language_override,
            mood_override=request.mood_override,
            url_for_path=_known_output_url,
        )
        report_progress(stage="building_song_map", progress=88)
        payload = result.model_dump(mode="json")
        studio_v2_jobs.update_job(
            output_dir,
            job_id,
            status="ready",
            stage="awaiting_confirmation",
            progress=100,
            warnings=list(result.warnings),
            completed_duration_seconds=float(
                (payload.get("song_intelligence_map") or {}).get("duration_seconds") or 0
            ),
            result=payload,
            error=None,
        )
    except Exception as exc:
        _fail_skarly_v2_job(output_dir, job_id, exc)


def _run_skarly_v2_generation_job(
    job_id: str,
    *,
    analysis_job: dict,
    owner_id: str,
    request: SkarlyV2GenerationRequest,
    runtime_settings,
) -> None:
    output_dir = runtime_settings.skarly_output_dir
    report_progress = studio_v2_jobs.progress_callback(output_dir, job_id)
    detected = (analysis_job.get("result") or {}).get("detected") or {}
    try:
        result = skarly_studio.generate_versions(
            upload_id=str(analysis_job.get("upload_id") or ""),
            uploads_dir=runtime_settings.uploads_dir,
            output_dir=runtime_settings.skarly_output_dir,
            ffmpeg_path=runtime_settings.ffmpeg_path,
            mixing_timeout_sec=runtime_settings.mixing_timeout_sec,
            generator_backend=runtime_settings.skarly_generator_backend,
            ace_step_base_url=runtime_settings.ace_step_base_url,
            ace_step_api_key=runtime_settings.ace_step_api_key,
            ace_step_timeout_seconds=runtime_settings.ace_step_timeout_seconds,
            ace_step_download_timeout_seconds=runtime_settings.ace_step_download_timeout_seconds,
            ace_step_poll_interval_seconds=runtime_settings.ace_step_poll_interval_seconds,
            ace_step_infer_step=runtime_settings.ace_step_infer_step,
            ace_step_guidance_scale=runtime_settings.ace_step_guidance_scale,
            ace_step_max_duration_seconds=runtime_settings.ace_step_max_duration_seconds,
            ace_step_use_source_audio=runtime_settings.ace_step_use_source_audio,
            ace_step_source_task_type=runtime_settings.ace_step_source_task_type,
            ace_step_source_audio_strength=runtime_settings.ace_step_source_audio_strength,
            ace_step_direct_enabled=runtime_settings.ace_step_direct_enabled,
            ace_step_repo_dir=runtime_settings.ace_step_repo_dir,
            ace_step_python_path=runtime_settings.ace_step_python_path,
            ace_step_fallback_to_procedural=runtime_settings.ace_step_fallback_to_procedural,
            require_cuda=bool(runtime_settings.require_cuda or request.require_cuda),
            allow_cpu_generation_fallback=runtime_settings.allow_cpu_generation_fallback,
            whisper_path=runtime_settings.whisper_path,
            whisper_model=runtime_settings.whisper_model,
            whisper_timeout_sec=runtime_settings.whisper_timeout_sec,
            melody_analyzer_backend=runtime_settings.melody_analyzer_backend,
            basic_pitch_path=runtime_settings.basic_pitch_path,
            basic_pitch_model_serialization=runtime_settings.basic_pitch_model_serialization,
            basic_pitch_save_note_events=runtime_settings.basic_pitch_save_note_events,
            melody_timeout_sec=runtime_settings.melody_timeout_sec,
            audio_classifier_checkpoint=runtime_settings.audio_classifier_checkpoint,
            audio_classifier_python_path=runtime_settings.audio_classifier_python_path,
            audio_classifier_timeout_sec=runtime_settings.audio_classifier_timeout_sec,
            stem_separator_backend=runtime_settings.stem_separator_backend,
            demucs_path=runtime_settings.demucs_path,
            demucs_model=runtime_settings.demucs_model,
            demucs_two_stems=runtime_settings.demucs_two_stems,
            demucs_device=runtime_settings.demucs_device,
            separation_timeout_sec=runtime_settings.separation_timeout_sec,
            language=request.language or detected.get("language"),
            mood=request.mood or detected.get("mood"),
            genre_override=request.genre_override,
            bpm_override=request.bpm_override,
            key_override=request.key_override,
            mix_preset=request.mix_profile,
            arrangement_mode=request.arrangement_mode.value,
            preserve_original_vocal=request.preserve_original_vocal,
            reference_strength=request.reference_strength,
            verify_music_transform_vocals=runtime_settings.music_to_music_verify_generated_vocals,
            music_transform_vocal_threshold_db=runtime_settings.music_to_music_vocal_threshold_db,
            music_transform_min_vocal_activity=runtime_settings.music_to_music_min_vocal_activity,
            owner_id=owner_id,
            producer_profile_ids=request.arrangement_profiles,
            progress_callback=report_progress,
            url_for_path=_known_output_url,
        )
        payload = result.model_dump(mode="json")
        telemetry = payload.get("generation_telemetry") or {}
        completed_outputs = [
            {
                "index": index,
                "name": version.get("name"),
                "style_family": version.get("style_family"),
                "backing_url": version.get("backing_url"),
                "final_mix_url": version.get("final_mix_url"),
            }
            for index, version in enumerate(payload.get("versions") or [], start=1)
        ]
        studio_v2_jobs.update_job(
            output_dir,
            job_id,
            status="ready",
            stage="ready",
            progress=100,
            current_arrangement=5,
            completed_arrangements=5,
            total_arrangements=5,
            cuda_device=telemetry.get("device"),
            model=telemetry.get("model"),
            warnings=list(result.warnings),
            completed_outputs=completed_outputs,
            result=payload,
            error=None,
        )
    except Exception as exc:
        _fail_skarly_v2_job(output_dir, job_id, exc)


def _run_skarly_v2_regeneration_job(
    job_id: str,
    *,
    generation_job: dict,
    request: SkarlyV2RegenerateRequest,
    runtime_settings,
) -> None:
    output_dir = runtime_settings.skarly_output_dir
    report_progress = studio_v2_jobs.progress_callback(output_dir, job_id)
    try:
        generation_result = deepcopy(generation_job.get("result") or {})
        versions = list(generation_result.get("versions") or [])
        current = dict(versions[request.version_index])
        detected = generation_result.get("detected") or {}
        song_map = generation_result.get("song_intelligence_map") or {}
        duration = float(song_map.get("duration_seconds") or 0)
        if duration <= 0:
            raise ValueError("The generation is missing its decoded vocal duration")
        profile_id = str(request.producer_profile_id or current.get("style_family") or "").strip().lower().replace("-", "_")
        profile = skarly_studio.PRODUCER_PROFILE_CATALOG[profile_id]
        vocal_path = _skarly_path_from_url(
            str(current.get("input_vocal_url") or generation_result.get("vocal_url") or ""),
            output_dir,
        )
        other_backings = [
            _skarly_path_from_url(str(version.get("backing_url") or ""), output_dir)
            for index, version in enumerate(versions)
            if index != request.version_index
        ]
        original_backing = _skarly_path_from_url(str(current.get("backing_url") or ""), output_dir)
        token = new_id("regen").split("_", 1)[1][:12]
        backing_path = original_backing.parent / f"backing_{request.version_index + 1}_regen_{token}.wav"
        final_path = original_backing.parent / f"final_mix_{request.version_index + 1}_regen_{token}.mp3"
        energy_direction = {
            -1: "reduced energy with a sparser verse and gentler chorus",
            0: profile.energy,
            1: "increased energy with stronger rhythmic lift and a denser chorus",
        }[request.energy_delta]
        revision = f" Producer revision: {energy_direction}."
        revised_instruments = list(profile.instruments)
        if request.instrument_change:
            instrument_change = request.instrument_change.strip()
            revision += f" Instrument change requested by the creator: {instrument_change}."
            normalized_change = instrument_change.lower().removeprefix("replace ")
            if " with " in normalized_change:
                old_instrument, new_instrument = [part.strip() for part in normalized_change.split(" with ", 1)]
                changed = False
                for instrument_index, instrument in enumerate(revised_instruments):
                    if old_instrument and old_instrument in instrument.lower():
                        revised_instruments[instrument_index] = new_instrument
                        changed = True
                if new_instrument and not changed:
                    revised_instruments.append(new_instrument)
        prompt = (
            f"Instrumental backing only for an uploaded {detected.get('language') or 'Hindi'} vocal. "
            f"Mood: {detected.get('mood') or 'adaptive'}. Tempo around {detected.get('bpm') or 84} BPM. "
            f"Key: {detected.get('key') or 'A minor'}. Duration exactly {duration:.3f} seconds. "
            f"Producer direction: {profile.direction}. Follow the complete vocal phrasing and section map; place fills between lyrics."
            f"{skarly_studio.profile_blueprint_prompt(profile)}{revision} No generated singing, humming, ad-libs, or spoken words."
        )
        plan = skarly_studio.VersionPlan(
            name=profile.name,
            prompt=prompt,
            negative_prompt="vocals, singing, humming, spoken words, ad-libs, voice clone, lead vocal",
            style_family=profile.profile_id,
            seed=skarly_studio.stable_plan_seed(
                language=str(detected.get("language") or "Hindi"),
                mood=str(detected.get("mood") or "adaptive"),
                key=str(detected.get("key") or "A minor"),
                bpm=int(detected.get("bpm") or 84),
                family=profile.profile_id,
                index=request.version_index + 1,
                variation_nonce=job_id,
            ),
            instruments=tuple(revised_instruments),
            energy=energy_direction,
            rhythm_character=profile.rhythm_character,
            mix_mode=profile.mix_mode,
            blueprint={**profile.blueprint(), "energy_curve": energy_direction, "instrument_family": ", ".join(revised_instruments)},
        )

        report_progress(stage="verifying_cuda", progress=5, current_arrangement=request.version_index + 1)
        cuda_info = None
        if runtime_settings.skarly_generator_backend == "ace_step":
            cuda_info = skarly_studio.cuda_runtime.verify_cuda_runtime(str(runtime_settings.ace_step_python_path or ""))
        report_progress(stage="creating_arrangement", progress=20, current_arrangement=request.version_index + 1)
        generated = None
        generation_seconds = 0.0
        peak_vram_mb = float((cuda_info or {}).get("peak_memory_mb") or 0)
        similarity_note = None
        for attempt in range(skarly_studio.MAX_DIVERSITY_GENERATION_ATTEMPTS):
            started = time.perf_counter()
            try:
                with skarly_studio.cuda_runtime.GpuMemorySampler(enabled=bool(cuda_info)) as memory_sampler:
                    generated = skarly_studio.generate_backing(
                        output_path=backing_path,
                        plan=plan,
                        seconds=duration,
                        bpm=float(detected.get("bpm") or 84),
                        key=detected.get("key"),
                        language=detected.get("language"),
                        mood=detected.get("mood"),
                        energy=energy_direction,
                        version_index=request.version_index + 1,
                        generator_backend=runtime_settings.skarly_generator_backend,
                        ace_step_base_url=runtime_settings.ace_step_base_url,
                        ace_step_api_key=runtime_settings.ace_step_api_key,
                        ace_step_timeout_seconds=runtime_settings.ace_step_timeout_seconds,
                        ace_step_download_timeout_seconds=runtime_settings.ace_step_download_timeout_seconds,
                        ace_step_poll_interval_seconds=runtime_settings.ace_step_poll_interval_seconds,
                        ace_step_infer_step=runtime_settings.ace_step_infer_step,
                        ace_step_guidance_scale=runtime_settings.ace_step_guidance_scale,
                        ace_step_max_duration_seconds=runtime_settings.ace_step_max_duration_seconds,
                        source_audio_path=vocal_path,
                        use_source_audio=runtime_settings.ace_step_use_source_audio,
                        source_task_type=runtime_settings.ace_step_source_task_type,
                        source_audio_strength=runtime_settings.ace_step_source_audio_strength,
                        ace_step_direct_enabled=runtime_settings.ace_step_direct_enabled,
                        ace_step_repo_dir=runtime_settings.ace_step_repo_dir,
                        ace_step_python_path=runtime_settings.ace_step_python_path,
                        ace_step_fallback_to_procedural=(
                            runtime_settings.ace_step_fallback_to_procedural
                            and runtime_settings.allow_cpu_generation_fallback
                            and not runtime_settings.require_cuda
                        ),
                        ffmpeg_path=runtime_settings.ffmpeg_path,
                        duration_conform_timeout_sec=runtime_settings.mixing_timeout_sec,
                    )
            except Exception:
                generation_seconds += time.perf_counter() - started
                if attempt < 1:
                    plan = skarly_studio.reroll_version_plan(plan, attempt + 1)
                    continue
                raise
            generation_seconds += time.perf_counter() - started
            peak_vram_mb = max(peak_vram_mb, memory_sampler.peak_vram_mb)
            duplicate, similarity_note = skarly_studio.backing_is_near_duplicate(backing_path, other_backings)
            if not duplicate:
                break
            if attempt >= skarly_studio.MAX_DIVERSITY_GENERATION_ATTEMPTS - 1:
                raise RuntimeError(f"Regenerated arrangement did not pass the diversity gate: {similarity_note}")
            plan = skarly_studio.reroll_version_plan(plan, attempt + 1)
        if generated is None:
            raise RuntimeError("Regeneration completed without an instrumental")

        report_progress(stage="mixing_vocals", progress=72, current_arrangement=request.version_index + 1)
        adaptive = skarly_studio.mix_vocal_forward(
            vocal_path=vocal_path,
            backing_path=backing_path,
            output_path=final_path,
            preset_name=skarly_studio.normalize_mix_preset(str(generation_result.get("mix_preset") or "balanced")),
            ffmpeg_path=runtime_settings.ffmpeg_path,
            timeout_sec=runtime_settings.mixing_timeout_sec,
        )
        output_duration = float(skarly_studio.safe_duration_seconds(final_path) or 0)
        if abs(output_duration - duration) > max(0.08, duration * 0.001):
            raise RuntimeError(f"Regenerated mix duration {output_duration:.3f}s did not match {duration:.3f}s")
        all_backings = []
        for index, version in enumerate(versions):
            all_backings.append(backing_path if index == request.version_index else _skarly_path_from_url(str(version.get("backing_url") or ""), output_dir))
        diversity = skarly_studio.build_arrangement_diversity_report(all_backings)
        if not diversity.passed or diversity.evaluated_pairs != 10:
            raise RuntimeError("Regenerated arrangement did not pass all ten pairwise diversity checks")

        new_version = {
            **current,
            "name": profile.name,
            "backing_url": skarly_studio.skarly_output_url(backing_path, Path(output_dir).resolve()),
            "final_mix_url": skarly_studio.skarly_output_url(final_path, Path(output_dir).resolve()),
            "prompt": plan.prompt,
            "generator": generated.generator,
            "generation_engine": generated.generation_engine,
            "style_family": profile.profile_id,
            "instruments": revised_instruments,
            "energy": energy_direction,
            "rhythm_character": profile.rhythm_character,
            "producer_mix_mode": profile.mix_mode,
            "blueprint": plan.blueprint or {},
            "seed": plan.seed,
            "mix_note": adaptive.note,
            "fallback_used": generated.fallback_used,
            "is_fallback": generated.fallback_used,
            "waveforms": {
                "input_vocal": ((current.get("waveforms") or {}).get("input_vocal") or skarly_studio.build_waveform_peaks(vocal_path, points=600, ffmpeg_path=runtime_settings.ffmpeg_path)),
                "backing": skarly_studio.build_waveform_peaks(backing_path, points=600, ffmpeg_path=runtime_settings.ffmpeg_path),
                "final_mix": skarly_studio.build_waveform_peaks(final_path, points=600, ffmpeg_path=runtime_settings.ffmpeg_path),
            },
        }
        versions[request.version_index] = new_version
        generation_result["versions"] = versions
        generation_result["arrangement_diversity"] = diversity.model_dump(mode="json")
        generation_result.setdefault("regeneration_history", []).append(
            {
                "job_id": job_id,
                "version_index": request.version_index,
                "producer_profile_id": profile.profile_id,
                "energy_delta": request.energy_delta,
                "instrument_change": request.instrument_change,
                "seed": plan.seed,
                "preserved_versions": 4,
            }
        )
        analysis_url = str(generation_result.get("analysis_url") or "")
        if analysis_url:
            analysis_path = _skarly_path_from_url(analysis_url, output_dir)
            manifest = json.loads(analysis_path.read_text(encoding="utf-8"))
            manifest["versions"] = [
                {
                    key: version.get(key)
                    for key in ("name", "style_family", "seed", "prompt", "instruments", "energy", "rhythm_character", "producer_mix_mode", "blueprint")
                }
                for version in versions
            ]
            manifest["arrangement_diversity"] = diversity.model_dump(mode="json")
            manifest["regeneration_history"] = generation_result["regeneration_history"]
            analysis_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

        completed_outputs = [
            {
                "index": index,
                "name": version.get("name"),
                "style_family": version.get("style_family"),
                "backing_url": version.get("backing_url"),
                "final_mix_url": version.get("final_mix_url"),
            }
            for index, version in enumerate(versions, start=1)
        ]
        studio_v2_jobs.update_job(
            output_dir,
            generation_job["job_id"],
            result=generation_result,
            completed_outputs=completed_outputs,
            warnings=list(generation_result.get("warnings") or []),
        )
        report_progress(stage="preparing_exports", progress=94, current_arrangement=request.version_index + 1)
        regeneration_result = {
            "generation_id": generation_job["job_id"],
            "version_index": request.version_index,
            "version": new_version,
            "updated_generation": generation_result,
            "arrangement_diversity": diversity.model_dump(mode="json"),
            "preserved_versions": 4,
            "regenerated_arrangement": True,
            "generation_telemetry": _v2_generation_telemetry(
                cuda_info=cuda_info,
                generator_backend=runtime_settings.skarly_generator_backend,
                model="acestep-v15-turbo"
                if runtime_settings.skarly_generator_backend == "ace_step"
                else "procedural_v2",
                peak_vram_mb=peak_vram_mb,
                generation_seconds=generation_seconds,
                cpu_fallback=generated.fallback_used,
            ),
        }
        studio_v2_jobs.update_job(
            output_dir,
            job_id,
            status="ready",
            stage="ready",
            progress=100,
            current_arrangement=request.version_index + 1,
            completed_arrangements=1,
            total_arrangements=1,
            completed_duration_seconds=duration,
            cuda_device=(cuda_info or {}).get("device"),
            model=regeneration_result["generation_telemetry"]["model"],
            completed_outputs=[completed_outputs[request.version_index]],
            result=regeneration_result,
            error=None,
        )
    except Exception as exc:
        _fail_skarly_v2_job(output_dir, job_id, exc)


def _run_skarly_v2_section_regeneration_job(
    job_id: str,
    *,
    generation_job: dict,
    request: SkarlyV2SectionRegenerateRequest,
    runtime_settings,
) -> None:
    """Repaint one instrumental interval, then remix the unchanged source vocal."""
    output_dir = runtime_settings.skarly_output_dir
    report_progress = studio_v2_jobs.progress_callback(output_dir, job_id)
    try:
        generation_result = deepcopy(generation_job.get("result") or {})
        versions = list(generation_result.get("versions") or [])
        current = dict(versions[request.version_index])
        detected = generation_result.get("detected") or {}
        song_map = generation_result.get("song_intelligence_map") or {}
        duration = float(song_map.get("duration_seconds") or 0)
        if duration <= 0:
            raise ValueError("The generation is missing its decoded vocal duration")

        vocal_path = _skarly_path_from_url(
            str(current.get("input_vocal_url") or generation_result.get("vocal_url") or ""),
            output_dir,
        )
        original_backing = _skarly_path_from_url(str(current.get("backing_url") or ""), output_dir)
        if not vocal_path.is_file() or not original_backing.is_file():
            raise FileNotFoundError("The selected version is missing its vocal or instrumental source")

        token = new_id("section").split("_", 1)[1][:12]
        section_request = SectionEditRequest(
            source_audio_path=str(original_backing),
            source_job_id=f"backing_{request.version_index + 1}_section_{token}",
            section_name=request.section_name,
            section_start_seconds=request.section_start_seconds,
            section_end_seconds=request.section_end_seconds,
            edit_instruction=request.edit_instruction,
            language=str(detected.get("language") or "Hindi"),
            genre=str(current.get("style_family") or ""),
            production_style=str(current.get("name") or ""),
            arrangement_style=str(current.get("rhythm_character") or ""),
            mood_tags=[str(detected.get("mood"))] if detected.get("mood") else [],
            instruments=[str(value) for value in current.get("instruments") or []],
            bpm=int(round(float(detected.get("bpm") or 84))),
            key=str(detected.get("key") or "A minor"),
            duration_seconds=duration,
            preserve_vocal=True,
            preserve_style=True,
            repaint_mode=request.repaint_mode,
            repaint_strength=request.repaint_strength,
            boundary_crossfade_seconds=request.boundary_crossfade_seconds,
        )
        edit_prompt = section_editor.build_section_edit_prompt(section_request)

        report_progress(stage="verifying_cuda", progress=5, current_arrangement=request.version_index + 1)
        cuda_info = skarly_studio.cuda_runtime.verify_cuda_runtime(str(runtime_settings.ace_step_python_path or ""))
        report_progress(stage="regenerating_section", progress=18, current_arrangement=request.version_index + 1)
        with skarly_studio.cuda_runtime.GpuMemorySampler(enabled=True) as memory_sampler:
            edit_result = ace_step.edit_section(
                source_audio_path=str(original_backing),
                section_name=request.section_name,
                edit_prompt=edit_prompt,
                output_dir=original_backing.parent,
                job_id=section_request.source_job_id or job_id,
                timeout_seconds=runtime_settings.section_edit_timeout_seconds,
                section_start_seconds=request.section_start_seconds,
                section_end_seconds=request.section_end_seconds,
                output_format="wav",
                base_url=runtime_settings.ace_step_base_url,
                api_key=runtime_settings.ace_step_api_key,
                model=runtime_settings.ace_step_model,
                inference_steps=runtime_settings.ace_step_infer_step,
                guidance_scale=runtime_settings.ace_step_guidance_scale,
                poll_interval_seconds=runtime_settings.ace_step_poll_interval_seconds,
                repaint_mode=request.repaint_mode,
                repaint_strength=request.repaint_strength,
                bpm=section_request.bpm,
                key=section_request.key,
                language=section_request.language,
                duration_seconds=duration,
                boundary_crossfade_seconds=request.boundary_crossfade_seconds,
            )
        if not edit_result.success or not edit_result.output_path:
            raise RuntimeError(edit_result.error_message or "ACE-Step did not produce a repainted instrumental")
        edit_metadata = dict(edit_result.metadata or {})
        if edit_metadata.get("cpu_fallback") is not False:
            raise RuntimeError("Section regeneration did not prove zero CPU generation fallback")
        if not edit_metadata.get("preserved_outside_section"):
            raise RuntimeError("Section regeneration changed audio outside the selected interval")
        if not edit_metadata.get("section_changed"):
            raise RuntimeError("Section regeneration did not change the selected interval")
        backing_path = Path(edit_result.output_path).resolve()
        backing_duration = float(skarly_studio.safe_duration_seconds(backing_path) or 0)
        if abs(backing_duration - duration) > max(0.05, duration * 0.001):
            raise RuntimeError(
                f"Repainted instrumental duration {backing_duration:.3f}s did not match {duration:.3f}s"
            )

        report_progress(stage="mixing_original_vocal", progress=68, current_arrangement=request.version_index + 1)
        final_path = original_backing.parent / f"final_mix_{request.version_index + 1}_section_{token}.mp3"
        adaptive = skarly_studio.mix_vocal_forward(
            vocal_path=vocal_path,
            backing_path=backing_path,
            output_path=final_path,
            preset_name=skarly_studio.normalize_mix_preset(str(generation_result.get("mix_preset") or "balanced")),
            ffmpeg_path=runtime_settings.ffmpeg_path,
            timeout_sec=runtime_settings.mixing_timeout_sec,
        )
        final_duration = float(skarly_studio.safe_duration_seconds(final_path) or 0)
        if abs(final_duration - duration) > max(0.08, duration * 0.001):
            raise RuntimeError(f"Section-edited mix duration {final_duration:.3f}s did not match {duration:.3f}s")

        report_progress(stage="checking_arrangement_diversity", progress=82, current_arrangement=request.version_index + 1)
        all_backings = [
            backing_path
            if index == request.version_index
            else _skarly_path_from_url(str(version.get("backing_url") or ""), output_dir)
            for index, version in enumerate(versions)
        ]
        diversity = skarly_studio.build_arrangement_diversity_report(all_backings)
        if not diversity.passed or diversity.evaluated_pairs != 10:
            raise RuntimeError("Section-edited arrangement did not pass all ten pairwise diversity checks")

        history_entry = {
            "job_id": job_id,
            "version_index": request.version_index,
            "section_name": request.section_name,
            "section_start_seconds": request.section_start_seconds,
            "section_end_seconds": request.section_end_seconds,
            "edit_instruction": request.edit_instruction,
            "edit_prompt": edit_prompt,
            "repaint_mode": request.repaint_mode,
            "repaint_strength": request.repaint_strength,
            "seed": edit_metadata.get("seed"),
            "preserved_outside_section": True,
            "outside_max_abs_error": edit_metadata.get("outside_max_abs_error"),
            "section_mean_abs_delta": edit_metadata.get("section_mean_abs_delta"),
            "cpu_fallback": False,
        }
        version_history = list(current.get("section_edit_history") or [])
        version_history.append(history_entry)
        new_version = {
            **current,
            "backing_url": skarly_studio.skarly_output_url(backing_path, Path(output_dir).resolve()),
            "final_mix_url": skarly_studio.skarly_output_url(final_path, Path(output_dir).resolve()),
            "generator": "ace_step",
            "generation_engine": "ace_step_1_5_repaint",
            "mix_note": adaptive.note,
            "fallback_used": False,
            "is_fallback": False,
            "section_edit_history": version_history,
            "last_section_edit": history_entry,
            "waveforms": {
                "input_vocal": (
                    (current.get("waveforms") or {}).get("input_vocal")
                    or skarly_studio.build_waveform_peaks(vocal_path, points=600, ffmpeg_path=runtime_settings.ffmpeg_path)
                ),
                "backing": skarly_studio.build_waveform_peaks(
                    backing_path, points=600, ffmpeg_path=runtime_settings.ffmpeg_path
                ),
                "final_mix": skarly_studio.build_waveform_peaks(
                    final_path, points=600, ffmpeg_path=runtime_settings.ffmpeg_path
                ),
            },
        }
        versions[request.version_index] = new_version
        generation_result["versions"] = versions
        generation_result["arrangement_diversity"] = diversity.model_dump(mode="json")
        generation_result.setdefault("section_regeneration_history", []).append(history_entry)

        analysis_url = str(generation_result.get("analysis_url") or "")
        if analysis_url:
            analysis_path = _skarly_path_from_url(analysis_url, output_dir)
            if analysis_path.is_file():
                manifest = json.loads(analysis_path.read_text(encoding="utf-8"))
                manifest["arrangement_diversity"] = diversity.model_dump(mode="json")
                manifest["section_regeneration_history"] = generation_result["section_regeneration_history"]
                analysis_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

        completed_outputs = [
            {
                "index": index,
                "name": version.get("name"),
                "style_family": version.get("style_family"),
                "backing_url": version.get("backing_url"),
                "final_mix_url": version.get("final_mix_url"),
            }
            for index, version in enumerate(versions, start=1)
        ]
        studio_v2_jobs.update_job(
            output_dir,
            generation_job["job_id"],
            result=generation_result,
            completed_outputs=completed_outputs,
            warnings=list(generation_result.get("warnings") or []),
        )

        report_progress(stage="preparing_exports", progress=94, current_arrangement=request.version_index + 1)
        result = {
            "generation_id": generation_job["job_id"],
            "version_index": request.version_index,
            "version": new_version,
            "updated_generation": generation_result,
            "arrangement_diversity": diversity.model_dump(mode="json"),
            "section_edit": history_entry,
            "preserved_versions": 4,
            "preserved_outside_section": True,
            "regenerated_arrangement": False,
            "regenerated_section": True,
            "generation_telemetry": _v2_generation_telemetry(
                cuda_info=cuda_info,
                generator_backend="ace_step",
                model="acestep-v15-turbo",
                peak_vram_mb=max(float(cuda_info.get("peak_memory_mb") or 0), memory_sampler.peak_vram_mb),
                generation_seconds=float(edit_result.duration_seconds),
                cpu_fallback=False,
            ),
        }
        studio_v2_jobs.update_job(
            output_dir,
            job_id,
            status="ready",
            stage="ready",
            progress=100,
            current_arrangement=request.version_index + 1,
            completed_arrangements=1,
            total_arrangements=1,
            completed_duration_seconds=duration,
            cuda_device=cuda_info.get("device"),
            model="acestep-v15-turbo",
            completed_outputs=[completed_outputs[request.version_index]],
            result=result,
            error=None,
        )
    except Exception as exc:
        _fail_skarly_v2_job(output_dir, job_id, exc)


def _v2_generation_telemetry(
    *,
    cuda_info: dict | None,
    generator_backend: str,
    model: str,
    peak_vram_mb: float,
    generation_seconds: float,
    cpu_fallback: bool,
) -> dict:
    """Build complete, schema-validated telemetry for every V2 generation variant."""
    return GenerationTelemetry(
        cuda_available=bool((cuda_info or {}).get("cuda_available")),
        device=(cuda_info or {}).get("device"),
        device_capability=(cuda_info or {}).get("device_capability"),
        torch_version=(cuda_info or {}).get("torch_version"),
        torch_cuda_runtime=(cuda_info or {}).get("torch_cuda_runtime"),
        compiled_architectures=list((cuda_info or {}).get("compiled_architectures") or []),
        generation_backend="cuda"
        if cuda_info
        else ("unverified" if generator_backend == "ace_step" else "cpu"),
        model=model,
        peak_vram_mb=round(float(peak_vram_mb), 2),
        generation_seconds=round(float(generation_seconds), 3),
        cpu_fallback=bool(cpu_fallback),
    ).model_dump(mode="json")


def _fail_skarly_v2_job(output_dir: str, job_id: str, exc: Exception) -> None:
    current = studio_v2_jobs.get_job(output_dir, job_id) or {}
    stage = str(current.get("stage") or "unknown")
    studio_v2_jobs.update_job(
        output_dir,
        job_id,
        status="failed",
        stage=stage,
        error={
            "stage": stage,
            "type": type(exc).__name__,
            "message": str(exc)[:2000],
            "retryable": isinstance(exc, (TimeoutError, ConnectionError)),
        },
    )


def _skarly_path_from_url(value: str, output_dir: str) -> Path:
    prefix = "/outputs/skarly/"
    decoded = unquote(str(value or "").split("?", 1)[0]).replace("\\", "/")
    if not decoded.startswith(prefix):
        raise ValueError("Expected a Skarly output URL")
    relative = decoded.removeprefix(prefix).lstrip("/")
    root = Path(output_dir).expanduser().resolve()
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("Skarly output URL escaped the configured output directory") from exc
    if not candidate.is_file():
        raise FileNotFoundError(candidate)
    return candidate


def _audio_export_for_output(output_path: str | None, quality_report: QualityReport) -> AudioExport:
    if not output_path:
        return AudioExport(quality_report=quality_report)
    suffix = Path(output_path).suffix.lower()
    return AudioExport(
        preview_mp3_path=output_path if suffix == ".mp3" else None,
        final_mp3_path=output_path if suffix == ".mp3" else None,
        final_wav_path=output_path if suffix == ".wav" else None,
        quality_report=quality_report,
    )


def _audio_export_for_mix(
    *,
    result: MixResult,
    quality_report: QualityReport,
    backing_path: str | None,
    backing_url: str | None,
    backing_quality_report: QualityReport,
) -> AudioExport:
    preview_url = _mix_output_url(result.preview_path) if _safe_existing_mix_output(result.preview_path) else None
    final_mp3_url = _mix_output_url(result.final_mp3_path) if _safe_existing_mix_output(result.final_mp3_path) else None
    preview_suffix = Path(result.preview_path).suffix.lower() if result.preview_path else ""
    return AudioExport(
        preview_mp3_path=result.preview_path if preview_suffix == ".mp3" else None,
        final_wav_path=result.final_wav_path,
        final_mp3_path=result.final_mp3_path,
        backing_audio_path=backing_path,
        backing_audio_url=backing_url,
        mixed_preview_path=result.preview_path,
        mixed_preview_url=preview_url,
        final_mix_wav_path=result.final_wav_path,
        final_mix_mp3_path=result.final_mp3_path,
        final_mix_mp3_url=final_mp3_url,
        quality_report=quality_report,
        backing_quality_report=backing_quality_report,
    )


def _int_or_default(value: object, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _float_or_default(value: object, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _vocal_validation_suggested_fix(quality_report: QualityReport) -> str:
    text = " ".join([*quality_report.validation_errors, *quality_report.warnings]).lower()
    if "does not exist" in text or "missing" in text:
        return "Upload a valid vocal audio file or remove vocal_audio_path."
    if "decoded" in text:
        return "Vocal file could not be decoded. Try WAV or MP3."
    if "silent" in text:
        return "Vocal audio appears silent. Upload a clearer vocal take or remove vocal_audio_path."
    return "Upload a valid vocal audio file or remove vocal_audio_path."


def _mix_suggested_fix(error_message: str, quality_report: QualityReport) -> str:
    text = f"{error_message} {' '.join([*quality_report.validation_errors, *quality_report.warnings])}".lower()
    if "vocal" in text and "decoded" in text:
        return "Vocal file could not be decoded. Try WAV or MP3."
    if "backing" in text and ("does not exist" in text or "missing" in text):
        return "Generate backing audio first or provide a valid backing_audio_path."
    if "ffmpeg" in text or "mp3" in text:
        return "MP3 export failed because FFmpeg may be unavailable. WAV export was kept."
    if "clipping" in text:
        return "Lower vocal_gain_db or backing_gain_db and try again."
    return "Check both audio files and try lower gain settings."


def _ace_step_output_url(output_path: str | None) -> str | None:
    if not output_path:
        return None
    try:
        output = Path(output_path).resolve()
        base = ace_step.resolve_output_dir(settings.ace_step_output_dir)
        relative = output.relative_to(base)
    except ValueError:
        return None
    return f"/outputs/ace_step/{quote(relative.as_posix(), safe='/')}"


def _mix_output_url(output_path: str | None) -> str | None:
    if not output_path:
        return None
    try:
        output = Path(output_path).resolve()
        base = resolve_mix_output_dir(settings.mix_output_dir)
        relative = output.relative_to(base)
    except ValueError:
        return None
    return f"/outputs/mixes/{quote(relative.as_posix(), safe='/')}"


def _procedural_output_url(output_path: str | None) -> str | None:
    if not output_path:
        return None
    try:
        output = Path(output_path).resolve()
        base = procedural_v2.resolve_output_dir(settings.procedural_output_dir)
        relative = output.relative_to(base)
    except ValueError:
        return None
    return f"/outputs/procedural_v2/{quote(relative.as_posix(), safe='/')}"


def _stem_output_url(output_path: str | None) -> str | None:
    if not output_path:
        return None
    try:
        output = Path(output_path).resolve()
        base = stems_service.resolve_output_dir(settings.stems_output_dir)
        relative = output.relative_to(base)
    except ValueError:
        return None
    return f"/outputs/stems/{quote(relative.as_posix(), safe='/')}"


def _section_output_url(output_path: str | None) -> str | None:
    if not output_path:
        return None
    try:
        output = Path(output_path).resolve()
        base = section_editor.resolve_output_dir(settings.section_output_dir)
        relative = output.relative_to(base)
    except ValueError:
        return None
    return f"/outputs/sections/{quote(relative.as_posix(), safe='/')}"


def _known_output_url(output_path: str | None) -> str | None:
    if not output_path:
        return None
    for resolver, route_prefix in (
        (lambda: resolve_mix_output_dir(settings.mix_output_dir), "/outputs/mixes"),
        (lambda: ace_step.resolve_output_dir(settings.ace_step_output_dir), "/outputs/ace_step"),
        (lambda: procedural_v2.resolve_output_dir(settings.procedural_output_dir), "/outputs/procedural_v2"),
        (lambda: stems_service.resolve_output_dir(settings.stems_output_dir), "/outputs/stems"),
        (lambda: section_editor.resolve_output_dir(settings.section_output_dir), "/outputs/sections"),
        (lambda: safe_paths.resolve_output_dir(settings.projects_dir), "/outputs/projects"),
        (lambda: safe_paths.resolve_output_dir(settings.exports_dir), "/outputs/exports"),
        (lambda: safe_paths.resolve_output_dir(settings.uploads_dir), "/outputs/uploads"),
        (lambda: safe_paths.resolve_output_dir(settings.online_music_output_dir), "/outputs/online_music"),
        (lambda: safe_paths.resolve_output_dir(settings.skarly_output_dir), "/outputs/skarly"),
    ):
        try:
            output = Path(output_path).resolve()
            relative = output.relative_to(resolver())
        except ValueError:
            continue
        return f"{route_prefix}/{quote(relative.as_posix(), safe='/')}"
    return None


def _configured_output_dirs() -> dict[str, str]:
    return {
        "ace_step": settings.ace_step_output_dir,
        "procedural_v2": settings.procedural_output_dir,
        "mixes": settings.mix_output_dir,
        "stems": settings.stems_output_dir,
        "sections": settings.section_output_dir,
        "projects": settings.projects_dir,
        "exports": settings.exports_dir,
        "uploads": settings.uploads_dir,
        "online_music": settings.online_music_output_dir,
        "skarly": settings.skarly_output_dir,
    }


def _allowed_output_dirs() -> list[str]:
    return list(_configured_output_dirs().values())


def _app_export_summary() -> dict:
    return {
        "version": app.version,
        "app_env": settings.app_env,
        "ace_step_enabled": settings.ace_step_enabled,
        "procedural_fallback_enabled": settings.procedural_fallback_enabled,
        "stems_enabled": settings.stems_enabled,
        "section_editing_mode": settings.section_editing_mode,
        "producer_assistant_mode": settings.producer_assistant_mode,
        "online_music_enabled": settings.online_music_enabled,
        "music_provider_primary": settings.music_provider_primary,
        "music_provider_secondary": settings.music_provider_secondary,
    }


def _safe_existing_output(output_path: str | None) -> bool:
    if not output_path:
        return False
    try:
        output = Path(output_path).resolve()
        base = ace_step.resolve_output_dir(settings.ace_step_output_dir)
        output.relative_to(base)
    except ValueError:
        return False
    return output.exists() and output.is_file()


def _safe_existing_mix_output(output_path: str | None) -> bool:
    if not output_path:
        return False
    try:
        output = Path(output_path).resolve()
        base = resolve_mix_output_dir(settings.mix_output_dir)
        output.relative_to(base)
    except ValueError:
        return False
    return output.exists() and output.is_file()


def _safe_existing_procedural_output(output_path: str | None) -> bool:
    if not output_path:
        return False
    try:
        output = Path(output_path).resolve()
        base = procedural_v2.resolve_output_dir(settings.procedural_output_dir)
        output.relative_to(base)
    except ValueError:
        return False
    return output.exists() and output.is_file()


def _safe_route_segment(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value)[:120] or "job"


def _dedupe_strings(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in result:
            result.append(text)
    return result


def _enqueue_generation(job_id: str, background_tasks: BackgroundTasks) -> None:
    if settings.task_backend == "inline":
        task_queue.enqueue_generation(job_id)
        background_tasks.add_task(_run_worker_safely, job_id)
        return
    task_queue.enqueue_generation(job_id)


def _run_worker_safely(job_id: str) -> None:
    try:
        worker.run_job(job_id)
    except KeyError:
        return
    except Exception as exc:
        try:
            jobs.update_status(job_id, JobStatus.failed, "failed", str(exc))
        except Exception:
            pass


def _require_worker_access(worker_secret: str | None) -> None:
    if settings.task_backend == "inline" and settings.app_env == "local" and not settings.worker_shared_secret:
        return
    if settings.worker_shared_secret and worker_secret == settings.worker_shared_secret:
        return
    raise HTTPException(status_code=401, detail="Worker access required")


def _require_owned_job(job_id: str, user: UserContext) -> JobRecord:
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.user_id != user.user_id:
        raise HTTPException(status_code=403, detail="Job belongs to another user")
    return job


def _preferred_skarly_style_families(user: UserContext, language: str | None) -> list[str]:
    """Return recent chosen style families, optionally scoped to the current language."""
    requested_language = (language or "").strip().casefold()
    families: list[str] = []
    for job in jobs.list_for_user(user.user_id):
        selection = job.final_generation_settings.get("skarly_selection")
        if not isinstance(selection, dict):
            continue
        selected_language = str(selection.get("language") or "").strip().casefold()
        if requested_language and selected_language and selected_language != requested_language:
            continue
        family = str(selection.get("style_family") or "").strip()
        if family and family not in families:
            families.append(family)
        if len(families) == 3:
            break
    return families


def _save_selected_skarly_version(job_id: str, version_index: int, user: UserContext) -> JobRecord:
    """Persist one selected static Skarly render as a user-owned library job."""
    safe_job_id = safe_paths.sanitize_filename(job_id)
    if safe_job_id != job_id:
        raise ValueError("Invalid Skarly job id")

    output_root = safe_paths.resolve_output_dir(settings.skarly_output_dir)
    job_dir = output_root / safe_job_id
    manifest_path = job_dir / "analysis.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    owner_id = str(manifest.get("owner_id") or "")
    if not owner_id:
        raise ValueError("Regenerate this version before saving it; this older render has no ownership record")
    if owner_id != user.user_id:
        raise PermissionError(job_id)

    versions = manifest.get("versions")
    if not isinstance(versions, list) or version_index >= len(versions):
        raise ValueError("Selected Skarly version is unavailable")
    selected = versions[version_index]
    if not isinstance(selected, dict):
        raise ValueError("Selected Skarly version metadata is invalid")

    final_path = next(
        (path for path in (job_dir / f"final_mix_{version_index + 1}.mp3", job_dir / f"final_mix_{version_index + 1}.wav") if path.is_file()),
        None,
    )
    backing_path = job_dir / f"backing_{version_index + 1}.wav"
    if final_path is None or not backing_path.is_file():
        raise FileNotFoundError("Selected Skarly audio files")

    existing = jobs.get(job_id)
    if existing is not None and existing.user_id != user.user_id:
        raise PermissionError(job_id)

    target_prefix = f"{user_storage_prefix(user)}/final/{job_id}"
    final_object = f"{target_prefix}/selected_mix{final_path.suffix.lower()}"
    backing_object = f"{target_prefix}/selected_backing.wav"
    _copy_skarly_artifact(final_path, final_object)
    _copy_skarly_artifact(backing_path, backing_object)

    vocal_path = next(
        (path for path in (job_dir / "vocals_isolated.wav", job_dir / "vocals.wav") if path.is_file()),
        None,
    )
    vocal_object = None
    if vocal_path is not None:
        vocal_object = f"{target_prefix}/selected_vocal.wav"
        _copy_skarly_artifact(vocal_path, vocal_object)

    export_paths: dict[str, str] = {}
    melody_path = job_dir / "melody.mid"
    if melody_path.is_file():
        melody_object = f"{target_prefix}/melody.mid"
        _copy_skarly_artifact(melody_path, melody_object)
        export_paths["melody_midi"] = melody_object

    detected = manifest.get("detected") if isinstance(manifest.get("detected"), dict) else {}
    family = str(selected.get("style_family") or "custom")
    timestamp = now_utc()
    selection = {
        "version_index": version_index,
        "name": str(selected.get("name") or f"Skarly Version {version_index + 1}"),
        "style_family": family,
        "seed": selected.get("seed"),
        "language": detected.get("language"),
        "mood": detected.get("mood"),
        "genre_hint": detected.get("genre_hint"),
        "selected_at": timestamp.isoformat(),
    }
    job = existing or JobRecord(
        job_id=job_id,
        user_id=user.user_id,
        creator_mode=user.creator_mode,
        genre=_skarly_library_genre(family),
        track_name=f"Skarly - {selection['name']}",
        source_type=SourceType.local_upload,
        raw_audio_path=None,
        created_at=timestamp,
        updated_at=timestamp,
    )
    job.genre = _skarly_library_genre(family)
    job.final_mp3_path = final_object
    job.backing_audio_path = backing_object
    job.isolated_vocal_path = vocal_object
    job.export_paths = export_paths
    job.worker_notes = f"Selected Skarly version {version_index + 1}: {selection['name']} ({family})."
    job.final_generation_settings = {"skarly_selection": selection}
    job.status = JobStatus.ready
    job.stage = "skarly_selected"
    job.library_status = "Selected"
    job.error = None
    job.updated_at = timestamp
    job.completed_at = timestamp
    jobs.create(job)
    return job


def _copy_skarly_artifact(source: Path, object_path: str) -> None:
    """Copy a chosen render into the active storage backend for durable library access."""
    storage.upload_bytes(object_path, source.read_bytes(), content_type_from_path(object_path))


def _skarly_library_genre(style_family: str) -> Genre:
    """Map a Skarly producer family to the closest library filter."""
    family = style_family.casefold()
    if "lofi" in family:
        return Genre.lofi
    if "cinematic" in family:
        return Genre.cinematic
    if "piano" in family:
        return Genre.piano
    if "acoustic" in family or "guitar" in family:
        return Genre.acoustic
    if "rock" in family:
        return Genre.rock
    return Genre.pop


def _require_owned_voice_take(take_id: str, user: UserContext):
    for take in [*voice_takes.list_for_user(user.user_id), *voice_takes.list_deleted_for_user(user.user_id)]:
        if take.take_id == take_id:
            return take
    raise HTTPException(status_code=404, detail="Voice take not found")


def _job_response(job: JobRecord) -> JobResponse:
    ready = job.status == JobStatus.ready
    final_url = storage.signed_download_url(job.final_mp3_path) if job.final_mp3_path and ready else None
    download_url = storage.signed_download_url(job.final_mp3_path, job.track_name) if job.final_mp3_path and ready else None
    isolated_url = storage.signed_download_url(job.isolated_vocal_path) if job.isolated_vocal_path and ready else None
    backing_url = storage.signed_download_url(job.backing_audio_path) if job.backing_audio_path and ready else None
    export_urls = {
        key: storage.signed_download_url(path, path.rsplit("/", 1)[-1])
        for key, path in job.export_paths.items()
        if path and ready
    }
    return JobResponse(
        job=job,
        quality_report=job.quality_report,
        final_mp3_url=final_url,
        final_mp3_download_url=download_url,
        final_wav_url=export_urls.get("wav"),
        midi_url=export_urls.get("midi"),
        melody_midi_url=export_urls.get("melody_midi"),
        chord_sheet_url=export_urls.get("chord_sheet"),
        producer_pack_url=export_urls.get("producer_pack"),
        isolated_vocal_url=isolated_url,
        backing_audio_url=backing_url,
        drums_stem_url=export_urls.get("drums_stem"),
        bass_stem_url=export_urls.get("bass_stem"),
        guitar_stem_url=export_urls.get("guitar_stem"),
        keys_stem_url=export_urls.get("keys_stem"),
        reference_stem_url=export_urls.get("reference_stem"),
    )


def _request_user_overrides(request: CreateJobRequest) -> dict[str, object]:
    overrides: dict[str, object] = {
        "genre": request.genre.value,
        "language": request.language.strip() or "Hindi",
    }
    lyrics = (request.lyrics or "").strip()
    if lyrics:
        overrides["lyrics"] = lyrics
    if request.production_style:
        overrides["production_style"] = request.production_style.value
    if request.arrangement_style:
        overrides["arrangement_style"] = request.arrangement_style
    if request.main_instruments:
        overrides["main_instruments"] = request.main_instruments
    if request.mood_tags:
        overrides["mood_tags"] = request.mood_tags
    if request.production_bpm is not None:
        overrides["production_bpm"] = request.production_bpm
    if request.key_override:
        overrides["key"] = request.key_override
    if request.energy_override:
        overrides["energy"] = request.energy_override
    if request.output_duration_seconds is not None:
        overrides["output_duration_seconds"] = request.output_duration_seconds
    if request.vocal_gain_db is not None:
        overrides["vocal_gain_db"] = request.vocal_gain_db
    if request.backing_gain_db is not None:
        overrides["backing_gain_db"] = request.backing_gain_db
    if request.ducking_strength:
        overrides["ducking_strength"] = request.ducking_strength
    return overrides


def _is_visible_library_job(job: JobRecord) -> bool:
    return job.status != JobStatus.deleted and not _is_stale_library_job(job)


def _is_stale_library_job(job: JobRecord) -> bool:
    title = (job.track_name or "").strip().lower()
    final_path = (job.final_mp3_path or "").strip().lower()
    if title in {"", "pending backend draft", "final", "final.mp3", "backend mock draft"}:
        return True
    if job.status == JobStatus.failed and title == "pending backend draft":
        return True
    return final_path.endswith("/final.mp3") and title in {"final", "final.mp3", "recovered mix"}


def _is_owned_raw_path(raw_audio_path: str, user: UserContext) -> bool:
    return any(raw_audio_path.startswith(prefix) for prefix in user_raw_prefixes(user))


def _resolve_skarly_upload_id(upload_id: str | None, *, raw_audio_path: str | None, user: UserContext) -> str:
    if upload_id:
        existing_upload = upload_service.get_upload(
            upload_id,
            uploads_dir=settings.uploads_dir,
            url_for_path=_known_output_url,
        )
        if existing_upload is not None:
            return existing_upload.upload_id

    if not raw_audio_path:
        raise FileNotFoundError(upload_id or "missing-upload")
    if not _is_owned_raw_path(raw_audio_path, user):
        raise HTTPException(status_code=403, detail="Raw audio path belongs to another user")
    if not storage.object_exists(raw_audio_path):
        raise FileNotFoundError(raw_audio_path)

    data = storage.download_bytes(raw_audio_path)
    upload = upload_service.save_audio_upload(
        filename=_title_from_object_path(raw_audio_path, "skarly-upload.wav"),
        content_type=_content_type_from_path(raw_audio_path),
        data=data,
        uploads_dir=settings.uploads_dir,
        max_upload_mb=settings.max_upload_mb,
        url_for_path=_known_output_url,
    )
    return upload.upload_id


def _looks_like_audio(object_path: str) -> bool:
    return object_path.lower().endswith((".mp3", ".wav", ".m4a", ".webm"))


def _title_from_object_path(object_path: str, fallback: str) -> str:
    filename = object_path.rsplit("/", 1)[-1].strip()
    return filename or fallback


def _content_type_from_path(object_path: str) -> str:
    return content_type_from_path(object_path)


def _delete_storage_object_if_present(object_path: str | None) -> None:
    if not object_path:
        return
    try:
        storage.delete_object(object_path)
    except Exception:
        pass


def _require_local_storage_backend() -> None:
    if settings.storage_backend not in {"local", "filesystem", "mock"}:
        raise HTTPException(status_code=404, detail="Local storage routes are disabled")


def _current_lyria_usage_key() -> str:
    return f"lyria_{now_utc().strftime('%Y_%m')}"


def _cloud_runtime_snapshot() -> CloudRuntimeSnapshot:
    service = os.getenv("K_SERVICE") or "local-fastapi"
    revision = os.getenv("K_REVISION") or "local"
    runtime = "cloud_run" if os.getenv("K_SERVICE") else "local"
    return CloudRuntimeSnapshot(
        runtime=runtime,
        service=service,
        revision=revision,
        region=settings.gcp_location,
        project_id=settings.gcp_project_id,
        service_url=os.getenv("SKARLY_PUBLIC_BACKEND_URL") or settings.worker_url,
        worker_url=settings.worker_url,
        task_queue=settings.cloud_tasks_queue,
        storage_bucket=settings.storage_bucket,
        cors_origins=list(settings.cors_origins),
    )
