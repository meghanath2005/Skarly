from dataclasses import dataclass
import os
from pathlib import Path
import sys


def load_local_env() -> None:
    if "pytest" in sys.modules:
        return

    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


load_local_env()


def split_csv_env(name: str) -> tuple[str, ...]:
    return tuple(value.strip() for value in os.getenv(name, "").split(",") if value.strip())


def local_ai_repo_path(*parts: str) -> Path:
    workspace_root = Path(__file__).resolve().parents[3]
    return workspace_root.joinpath("skarly-ai-repos", *parts)


def default_local_tool(env_name: str, fallback: str, *parts: str) -> str:
    configured = os.getenv(env_name)
    if configured:
        return configured
    candidate = local_ai_repo_path(*parts)
    return str(candidate) if candidate.exists() else fallback


def default_local_python_module_tool(env_name: str, fallback: str, module: str, *parts: str) -> str:
    configured = os.getenv(env_name)
    if configured:
        return configured
    candidate = local_ai_repo_path(*parts)
    return f"{candidate} -m {module}" if candidate.exists() else fallback


def env_default(name: str, default: str, *, pytest_default: str | None = None) -> str:
    configured = os.getenv(name)
    if configured is not None:
        return configured
    if pytest_default is not None and "pytest" in sys.modules:
        return pytest_default
    return default


@dataclass(frozen=True)
class Settings:
    app_env: str = os.getenv("APP_ENV", os.getenv("SKARLY_ENV", "local"))
    app_public_base_url: str = os.getenv("APP_PUBLIC_BASE_URL", os.getenv("SKARLY_PUBLIC_BASE_URL", "http://127.0.0.1:8000"))
    log_level: str = os.getenv("LOG_LEVEL", os.getenv("SKARLY_LOG_LEVEL", "INFO"))
    storage_bucket: str = os.getenv("SKARLY_STORAGE_BUCKET", "skarly-local")
    storage_backend: str = os.getenv("SKARLY_STORAGE_BACKEND", "local")
    local_storage_dir: str = os.getenv(
        "SKARLY_LOCAL_STORAGE_DIR",
        str(Path(__file__).resolve().parent.parent / ".local-storage"),
    )
    gcs_signing_service_account: str | None = os.getenv("SKARLY_GCS_SIGNING_SERVICE_ACCOUNT")
    repository_backend: str = os.getenv("SKARLY_REPOSITORY_BACKEND", "sqlite")
    sqlite_path: str = os.getenv(
        "SKARLY_SQLITE_PATH",
        str(Path(__file__).resolve().parent.parent / ".skarly-projects.sqlite3"),
    )
    worker_backend: str = os.getenv("SKARLY_WORKER_BACKEND", "mvp_audio")
    max_demo_duration_seconds: int = int(os.getenv("SKARLY_MAX_DEMO_DURATION_SECONDS", "300"))
    analysis_timeout_sec: int = int(os.getenv("SKARLY_ANALYSIS_TIMEOUT_SEC", "600"))
    separation_timeout_sec: int = int(os.getenv("SKARLY_SEPARATION_TIMEOUT_SEC", "1200"))
    melody_timeout_sec: int = int(os.getenv("SKARLY_MELODY_TIMEOUT_SEC", "120"))
    backing_generation_timeout_sec: int = int(os.getenv("SKARLY_BACKING_GENERATION_TIMEOUT_SEC", "600"))
    mixing_timeout_sec: int = int(os.getenv("SKARLY_MIXING_TIMEOUT_SEC", "120"))
    export_timeout_sec: int = int(os.getenv("SKARLY_EXPORT_TIMEOUT_SEC", "120"))
    studio_poll_timeout_sec: int = int(os.getenv("SKARLY_STUDIO_POLL_TIMEOUT_SEC", "900"))
    music_generator_backend: str = os.getenv("SKARLY_MUSIC_GENERATOR_BACKEND", "procedural_v2")
    ace_step_base_url: str = os.getenv("SKARLY_ACE_STEP_BASE_URL", "http://127.0.0.1:8001")
    ace_step_enabled: bool = os.getenv("ACE_STEP_ENABLED", "false").lower() in {"1", "true", "yes"}
    ace_step_mode: str = os.getenv("ACE_STEP_MODE", "cli")
    ace_step_cli_path: str = os.getenv("ACE_STEP_CLI_PATH", "")
    ace_step_output_dir: str = os.getenv("ACE_STEP_OUTPUT_DIR", "outputs/ace_step")
    ace_step_device: str = os.getenv("ACE_STEP_DEVICE", "cuda")
    ace_step_default_format: str = os.getenv("ACE_STEP_DEFAULT_FORMAT", "wav")
    ace_step_benchmark_evidence_path: str = os.getenv(
        "SKARLY_ACE_STEP_BENCHMARK_EVIDENCE_PATH",
        "outputs/validation/ace_step_profile_inference_evidence.json",
    )
    procedural_fallback_enabled: bool = os.getenv("PROCEDURAL_FALLBACK_ENABLED", os.getenv("SKARLY_PROCEDURAL_FALLBACK_ENABLED", "true")).lower() in {"1", "true", "yes"}
    procedural_output_dir: str = os.getenv("PROCEDURAL_OUTPUT_DIR", os.getenv("SKARLY_PROCEDURAL_OUTPUT_DIR", "outputs/procedural_v2"))
    procedural_default_format: str = os.getenv("PROCEDURAL_DEFAULT_FORMAT", os.getenv("SKARLY_PROCEDURAL_DEFAULT_FORMAT", "wav"))
    mix_output_dir: str = os.getenv("MIX_OUTPUT_DIR", os.getenv("SKARLY_MIX_OUTPUT_DIR", "outputs/mixes"))
    mix_default_format: str = os.getenv("MIX_DEFAULT_FORMAT", os.getenv("SKARLY_MIX_DEFAULT_FORMAT", "mp3"))
    mix_preview_format: str = os.getenv("MIX_PREVIEW_FORMAT", os.getenv("SKARLY_MIX_PREVIEW_FORMAT", "mp3"))
    mix_sample_rate: int = int(os.getenv("MIX_SAMPLE_RATE", os.getenv("SKARLY_MIX_SAMPLE_RATE", "44100")))
    mix_default_vocal_gain_db: float = float(os.getenv("MIX_DEFAULT_VOCAL_GAIN_DB", os.getenv("SKARLY_MIX_DEFAULT_VOCAL_GAIN_DB", "2.0")))
    mix_default_backing_gain_db: float = float(os.getenv("MIX_DEFAULT_BACKING_GAIN_DB", os.getenv("SKARLY_MIX_DEFAULT_BACKING_GAIN_DB", "-3.0")))
    mix_default_ducking_enabled: bool = os.getenv("MIX_DEFAULT_DUCKING_ENABLED", os.getenv("SKARLY_MIX_DEFAULT_DUCKING_ENABLED", "true")).lower() in {"1", "true", "yes"}
    mix_default_ducking_amount: float = float(os.getenv("MIX_DEFAULT_DUCKING_AMOUNT", os.getenv("SKARLY_MIX_DEFAULT_DUCKING_AMOUNT", "0.35")))
    producer_assistant_enabled: bool = os.getenv("PRODUCER_ASSISTANT_ENABLED", os.getenv("SKARLY_PRODUCER_ASSISTANT_ENABLED", "true")).lower() in {"1", "true", "yes"}
    producer_assistant_mode: str = os.getenv("PRODUCER_ASSISTANT_MODE", os.getenv("SKARLY_PRODUCER_ASSISTANT_MODE", "rules"))
    producer_assistant_llm_provider: str | None = os.getenv("PRODUCER_ASSISTANT_LLM_PROVIDER", os.getenv("SKARLY_PRODUCER_ASSISTANT_LLM_PROVIDER", "")) or None
    producer_assistant_llm_model: str | None = os.getenv("PRODUCER_ASSISTANT_LLM_MODEL", os.getenv("SKARLY_PRODUCER_ASSISTANT_LLM_MODEL", "")) or None
    projects_enabled: bool = os.getenv("PROJECTS_ENABLED", os.getenv("SKARLY_PROJECTS_ENABLED", "true")).lower() in {"1", "true", "yes"}
    projects_dir: str = os.getenv("PROJECTS_DIR", os.getenv("SKARLY_PROJECTS_DIR", "outputs/projects"))
    exports_dir: str = os.getenv("EXPORTS_DIR", os.getenv("SKARLY_EXPORTS_DIR", "outputs/exports"))
    uploads_dir: str = os.getenv("UPLOADS_DIR", os.getenv("SKARLY_UPLOADS_DIR", "outputs/uploads"))
    max_upload_mb: int = int(os.getenv("MAX_UPLOAD_MB", os.getenv("SKARLY_MAX_UPLOAD_MB", "100")))
    max_projects_list: int = int(os.getenv("MAX_PROJECTS_LIST", os.getenv("SKARLY_MAX_PROJECTS_LIST", "100")))
    output_retention_days: int = int(os.getenv("OUTPUT_RETENTION_DAYS", os.getenv("SKARLY_OUTPUT_RETENTION_DAYS", "14")))
    startup_health_checks: bool = os.getenv("STARTUP_HEALTH_CHECKS", os.getenv("SKARLY_STARTUP_HEALTH_CHECKS", "true")).lower() in {"1", "true", "yes"}
    strict_safe_paths: bool = os.getenv("STRICT_SAFE_PATHS", os.getenv("SKARLY_STRICT_SAFE_PATHS", "true")).lower() in {"1", "true", "yes"}
    online_music_enabled: bool = os.getenv("ONLINE_MUSIC_ENABLED", os.getenv("SKARLY_ONLINE_MUSIC_ENABLED", "true")).lower() in {"1", "true", "yes"}
    music_provider_primary: str = os.getenv("MUSIC_PROVIDER_PRIMARY", os.getenv("SKARLY_MUSIC_PROVIDER_PRIMARY", "elevenlabs"))
    music_provider_secondary: str = os.getenv("MUSIC_PROVIDER_SECONDARY", os.getenv("SKARLY_MUSIC_PROVIDER_SECONDARY", "lyria"))
    elevenlabs_api_key: str | None = os.getenv("ELEVENLABS_API_KEY", os.getenv("SKARLY_ELEVENLABS_API_KEY", "")) or None
    elevenlabs_music_model: str = os.getenv("ELEVENLABS_MUSIC_MODEL", os.getenv("SKARLY_ELEVENLABS_MUSIC_MODEL", "music_v2"))
    gemini_api_key: str | None = os.getenv("GEMINI_API_KEY", os.getenv("GOOGLE_API_KEY", os.getenv("SKARLY_GEMINI_API_KEY", ""))) or None
    lyria_pro_model: str = os.getenv("LYRIA_PRO_MODEL", os.getenv("SKARLY_LYRIA_PRO_MODEL", "lyria-3-pro-preview"))
    online_music_timeout_seconds: int = int(os.getenv("ONLINE_MUSIC_TIMEOUT_SECONDS", os.getenv("SKARLY_ONLINE_MUSIC_TIMEOUT_SECONDS", "900")))
    generate_candidate_count: int = int(os.getenv("GENERATE_CANDIDATE_COUNT", os.getenv("SKARLY_GENERATE_CANDIDATE_COUNT", "3")))
    require_rights_confirmation: bool = os.getenv("REQUIRE_RIGHTS_CONFIRMATION", os.getenv("SKARLY_REQUIRE_RIGHTS_CONFIRMATION", "true")).lower() in {"1", "true", "yes"}
    online_music_output_dir: str = os.getenv("ONLINE_MUSIC_OUTPUT_DIR", os.getenv("SKARLY_ONLINE_MUSIC_OUTPUT_DIR", "outputs/online_music"))
    skarly_output_dir: str = os.getenv("SKARLY_OUTPUT_DIR", "outputs/skarly")
    skarly_generator_backend: str = os.getenv(
        "SKARLY_GENERATOR_BACKEND",
        env_default("SKARLY_MUSIC_GENERATOR_BACKEND", "ace_step", pytest_default="procedural_v2"),
    )
    whisper_path: str = os.getenv("SKARLY_WHISPER_PATH", "whisper")
    whisper_model: str = os.getenv("SKARLY_WHISPER_MODEL", "base")
    whisper_timeout_sec: int = int(os.getenv("SKARLY_WHISPER_TIMEOUT_SEC", "180"))
    # A reviewed checkpoint opts the production flow into the local CNN. Empty
    # by default so no unvalidated training artefact influences users.
    audio_classifier_checkpoint: str | None = os.getenv("SKARLY_AUDIO_CLASSIFIER_CHECKPOINT") or None
    audio_classifier_python_path: str = str(default_local_tool(
        "SKARLY_AUDIO_CLASSIFIER_PYTHON",
        "python",
        "ACE-Step-1.5",
        ".venv",
        "Scripts",
        "python.exe",
    ))
    audio_classifier_timeout_sec: int = int(os.getenv("SKARLY_AUDIO_CLASSIFIER_TIMEOUT_SEC", "30"))
    training_feedback_enabled: bool = os.getenv("SKARLY_TRAINING_FEEDBACK_ENABLED", "true").lower() in {"1", "true", "yes"}
    training_feedback_dir: str = os.getenv("SKARLY_TRAINING_FEEDBACK_DIR", "data/consented_feedback")
    training_feedback_manifest: str = os.getenv("SKARLY_TRAINING_FEEDBACK_MANIFEST", "data/manifests/user_feedback.jsonl")
    stems_enabled: bool = os.getenv("STEMS_ENABLED", os.getenv("SKARLY_STEMS_ENABLED", "true")).lower() in {"1", "true", "yes"}
    stems_engine: str = os.getenv("STEMS_ENGINE", os.getenv("SKARLY_STEMS_ENGINE", "demucs"))
    stems_output_dir: str = os.getenv("STEMS_OUTPUT_DIR", os.getenv("SKARLY_STEMS_OUTPUT_DIR", "outputs/stems"))
    stems_timeout_seconds: int = int(os.getenv("STEMS_TIMEOUT_SECONDS", os.getenv("SKARLY_STEMS_TIMEOUT_SECONDS", "900")))
    demucs_cli_path: str = os.getenv(
        "DEMUCS_CLI_PATH",
        os.getenv(
            "SKARLY_DEMUCS_CLI_PATH",
            os.getenv(
                "SKARLY_DEMUCS_PATH",
                default_local_python_module_tool(
                    "SKARLY_DEMUCS_PATH",
                    "python -m demucs",
                    "demucs.separate",
                    "_envs",
                    "demucs",
                    "Scripts",
                    "python.exe",
                ),
            ),
        ),
    )
    music_to_music_vocal_threshold_db: float = float(os.getenv("SKARLY_MUSIC_TO_MUSIC_VOCAL_THRESHOLD_DB", "-24"))
    music_to_music_min_vocal_activity: float = float(os.getenv("SKARLY_MUSIC_TO_MUSIC_MIN_VOCAL_ACTIVITY", "0.04"))
    music_to_music_verify_generated_vocals: bool = os.getenv("SKARLY_MUSIC_TO_MUSIC_VERIFY_GENERATED_VOCALS", "true").lower() in {"1", "true", "yes"}
    section_editing_enabled: bool = os.getenv("SECTION_EDITING_ENABLED", os.getenv("SKARLY_SECTION_EDITING_ENABLED", "true")).lower() in {"1", "true", "yes"}
    section_editing_mode: str = os.getenv("SECTION_EDITING_MODE", os.getenv("SKARLY_SECTION_EDITING_MODE", "ace_step"))
    section_output_dir: str = os.getenv("SECTION_OUTPUT_DIR", os.getenv("SKARLY_SECTION_OUTPUT_DIR", "outputs/sections"))
    section_edit_timeout_seconds: int = int(os.getenv("SECTION_EDIT_TIMEOUT_SECONDS", os.getenv("SKARLY_SECTION_EDIT_TIMEOUT_SECONDS", "900")))
    ace_step_api_command: str = default_local_tool(
        "SKARLY_ACE_STEP_API_COMMAND",
        "acestep-api",
        "ACE-Step-1.5",
        ".venv",
        "Scripts",
        "acestep-api.exe",
    )
    ace_step_api_key: str | None = os.getenv("SKARLY_ACE_STEP_API_KEY")
    ace_step_model: str | None = os.getenv("SKARLY_ACE_STEP_MODEL") or None
    ace_step_timeout_seconds: int = int(
        os.getenv(
            "ACE_STEP_TIMEOUT_SECONDS",
            os.getenv("SKARLY_ACE_STEP_TIMEOUT_SECONDS", os.getenv("SKARLY_BACKING_GENERATION_TIMEOUT_SEC", "600")),
        )
    )
    ace_step_download_timeout_seconds: int = int(os.getenv("SKARLY_ACE_STEP_DOWNLOAD_TIMEOUT_SECONDS", os.getenv("SKARLY_ACE_STEP_TIMEOUT_SECONDS", os.getenv("SKARLY_BACKING_GENERATION_TIMEOUT_SEC", "600"))))
    ace_step_poll_interval_seconds: float = float(os.getenv("SKARLY_ACE_STEP_POLL_INTERVAL_SECONDS", "2.0"))
    ace_step_infer_step: int = int(os.getenv("SKARLY_ACE_STEP_INFER_STEP", "8"))
    ace_step_guidance_scale: float = float(os.getenv("SKARLY_ACE_STEP_GUIDANCE_SCALE", "1.0"))
    ace_step_max_duration_seconds: int = int(os.getenv("SKARLY_ACE_STEP_MAX_DURATION_SECONDS", os.getenv("SKARLY_MAX_DEMO_DURATION_SECONDS", "300")))
    ace_step_thinking: bool = os.getenv("SKARLY_ACE_STEP_THINKING", "false").lower() in {"1", "true", "yes"}
    ace_step_use_source_audio: bool = os.getenv("SKARLY_ACE_STEP_USE_SOURCE_AUDIO", "false").lower() in {"1", "true", "yes"}
    ace_step_send_lyrics: bool = os.getenv("SKARLY_ACE_STEP_SEND_LYRICS", "false").lower() in {"1", "true", "yes"}
    ace_step_source_task_type: str | None = os.getenv("SKARLY_ACE_STEP_SOURCE_TASK_TYPE") or None
    ace_step_source_audio_strength: float = float(os.getenv("SKARLY_ACE_STEP_SOURCE_AUDIO_STRENGTH", "0.45"))
    ace_step_fallback_to_procedural: bool = os.getenv("SKARLY_ACE_STEP_FALLBACK_TO_PROCEDURAL", "false").lower() in {"1", "true", "yes"}
    require_cuda: bool = env_default("REQUIRE_CUDA", "true", pytest_default="false").lower() in {"1", "true", "yes"}
    allow_cpu_generation_fallback: bool = os.getenv("ALLOW_CPU_GENERATION_FALLBACK", "false").lower() in {"1", "true", "yes"}
    # Keep ACE-Step resident in its API worker across all five versions. Direct mode
    # starts a new model process per backing and is intended only as a recovery path.
    ace_step_direct_enabled: bool = os.getenv("SKARLY_ACE_STEP_DIRECT_ENABLED", "false").lower() in {"1", "true", "yes"}
    ace_step_repo_dir: str = str(default_local_tool("SKARLY_ACE_STEP_REPO_DIR", str(local_ai_repo_path("ACE-Step-1.5")), "ACE-Step-1.5"))
    ace_step_python_path: str = str(default_local_tool(
        "SKARLY_ACE_STEP_PYTHON_PATH",
        "python",
        "ACE-Step-1.5",
        ".venv",
        "Scripts",
        "python.exe",
    ))
    audiocraft_backend_status: str = os.getenv("SKARLY_AUDIOCRAFT_BACKEND_STATUS", "blocked_windows_av_dependency")
    stem_separator_backend: str = os.getenv("SKARLY_STEM_SEPARATOR_BACKEND", "demucs")
    demucs_path: str = default_local_python_module_tool(
        "SKARLY_DEMUCS_PATH",
        "demucs",
        "demucs.separate",
        "_envs",
        "demucs",
        "Scripts",
        "python.exe",
    )
    demucs_model: str = os.getenv("SKARLY_DEMUCS_MODEL", "htdemucs_ft")
    demucs_two_stems: str = os.getenv("SKARLY_DEMUCS_TWO_STEMS", "vocals")
    demucs_device: str = os.getenv("SKARLY_DEMUCS_DEVICE", "cuda")
    melody_analyzer_backend: str = env_default("SKARLY_MELODY_ANALYZER_BACKEND", "basic_pitch", pytest_default="off")
    basic_pitch_path: str = default_local_tool(
        "SKARLY_BASIC_PITCH_PATH",
        "basic-pitch",
        "_envs",
        "basic-pitch",
        "Scripts",
        "basic-pitch.exe",
    )
    basic_pitch_model_serialization: str = os.getenv("SKARLY_BASIC_PITCH_MODEL_SERIALIZATION", "onnx")
    basic_pitch_save_note_events: bool = os.getenv("SKARLY_BASIC_PITCH_SAVE_NOTE_EVENTS", "true").lower() in {"1", "true", "yes"}
    backing_vocal_cleanup_enabled: bool = os.getenv("SKARLY_BACKING_VOCAL_CLEANUP_ENABLED", "true").lower() in {"1", "true", "yes"}
    vocal_cleanup_enabled: bool = os.getenv("SKARLY_VOCAL_CLEANUP_ENABLED", "true").lower() in {"1", "true", "yes"}
    vocal_mix_gain: float = float(os.getenv("SKARLY_VOCAL_MIX_GAIN", "1.19"))
    backing_mix_gain: float = float(os.getenv("SKARLY_BACKING_MIX_GAIN", "0.71"))
    instrumental_mix_gain: float = float(os.getenv("SKARLY_INSTRUMENTAL_MIX_GAIN", "1.05"))
    default_vocal_gain_db: float = float(os.getenv("SKARLY_DEFAULT_VOCAL_GAIN_DB", "1.5"))
    default_backing_gain_db: float = float(os.getenv("SKARLY_DEFAULT_BACKING_GAIN_DB", "-3.0"))
    default_ducking_strength: str = os.getenv("SKARLY_DEFAULT_DUCKING_STRENGTH", "medium")
    lyria_model: str = os.getenv("SKARLY_LYRIA_MODEL", "lyria-003")
    lyria_fallback_to_procedural: bool = os.getenv("SKARLY_LYRIA_FALLBACK_TO_PROCEDURAL", "true").lower() in {"1", "true", "yes"}
    lyria_monthly_limit: int = int(os.getenv("SKARLY_LYRIA_MONTHLY_LIMIT", "25"))
    lyria_unit_cost_usd: float = float(os.getenv("SKARLY_LYRIA_UNIT_COST_USD", "0.04"))
    local_llm_base_url: str = os.getenv("SKARLY_LOCAL_LLM_BASE_URL", "http://127.0.0.1:11434")
    local_llm_model: str = os.getenv("SKARLY_LOCAL_LLM_MODEL", "llama3.2:1b")
    task_backend: str = os.getenv("SKARLY_TASK_BACKEND", "inline")
    worker_shared_secret: str | None = os.getenv("SKARLY_WORKER_SHARED_SECRET")
    worker_url: str | None = os.getenv("SKARLY_WORKER_URL")
    gcp_project_id: str | None = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT_ID") or os.getenv("FIREBASE_PROJECT_ID")
    gcp_location: str = os.getenv("SKARLY_CLOUD_TASKS_LOCATION", "us-central1")
    cloud_tasks_queue: str = os.getenv("SKARLY_CLOUD_TASKS_QUEUE", "skarly-generation")
    cloud_tasks_service_account_email: str | None = os.getenv("SKARLY_CLOUD_TASKS_SERVICE_ACCOUNT_EMAIL")
    cors_origins: tuple[str, ...] = split_csv_env("SKARLY_CORS_ORIGINS")
    ffmpeg_path: str = os.getenv("SKARLY_FFMPEG_PATH", "ffmpeg")
    local_base_url: str = os.getenv("SKARLY_LOCAL_BASE_URL", "http://localhost:8090")
    raw_audio_ttl_hours: int = int(os.getenv("SKARLY_RAW_AUDIO_TTL_HOURS", "24"))
    auth_mode: str = os.getenv("AUTH_MODE", "firebase_with_guest")
    firebase_project_id: str | None = os.getenv("FIREBASE_PROJECT_ID")
    firebase_service_account_json: str | None = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
    firebase_credentials_path: str | None = os.getenv("FIREBASE_CREDENTIALS_PATH")
    admin_emails: tuple[str, ...] = tuple(email.lower() for email in split_csv_env("SKARLY_ADMIN_EMAILS"))
    admin_uids: tuple[str, ...] = split_csv_env("SKARLY_ADMIN_UIDS")


settings = Settings()
