from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


class CreatorMode(str, Enum):
    guest = "guest"
    saved = "saved"


class SourceType(str, Enum):
    recording = "recording"
    local_upload = "localUpload"
    sample_upload = "sampleUpload"


class ArrangementMode(str, Enum):
    vocal_to_song = "vocal_to_song"
    music_to_music = "music_to_music"
    full_song = "full_song"


class JobStatus(str, Enum):
    created = "created"
    uploaded = "uploaded"
    queued = "queued"
    analyzing = "analyzing"
    generating = "generating"
    mixing = "mixing"
    ready = "ready"
    failed = "failed"
    deleted = "deleted"


class ItemStatus(str, Enum):
    active = "active"
    deleted = "deleted"


class Genre(str, Enum):
    lofi = "Lo-fi"
    piano = "Piano"
    pop = "Pop"
    rock = "Rock"
    rnb = "R&B"
    hiphop = "Hip-hop"
    acoustic = "Acoustic"
    cinematic = "Cinematic"


class ProductionStyle(str, Enum):
    bollywood_ballad = "Bollywood Ballad"
    romantic_pop = "Romantic Pop"
    acoustic_unplugged = "Acoustic Unplugged"
    piano_ballad = "Piano Ballad"
    cinematic_strings = "Cinematic Strings"
    indie_pop = "Indie Pop"
    lofi_cover = "Lo-fi Cover"
    edm_rework = "EDM Rework"
    rock_cover = "Rock Cover"
    trap_soul = "Trap Soul"
    ambient = "Ambient"
    orchestral_pop = "Orchestral Pop"
    qawwali_fusion = "Qawwali Fusion"
    ghazal_pop = "Ghazal Pop"
    bhajan_devotional = "Bhajan / Devotional"
    folk_fusion = "Folk Fusion"
    sufi_rock = "Sufi Rock"
    punjabi_pop = "Punjabi Pop"
    south_indian_cinematic = "South Indian Cinematic"


class ProducerSettings(BaseModel):
    bpm: Optional[int] = Field(default=None, ge=40, le=220)
    key: Optional[str] = Field(default=None, max_length=40)
    duration_seconds: Optional[int] = Field(default=None, ge=10, le=600)
    energy: Optional[str] = Field(default=None, max_length=40)
    vocal_gain_db: Optional[float] = Field(default=None, ge=-24, le=24)
    backing_gain_db: Optional[float] = Field(default=None, ge=-24, le=24)
    ducking_enabled: bool = True
    ducking_amount: Optional[float] = Field(default=None, ge=0, le=1)
    vocal_forward_mix: bool = True


class SongGenerateRequest(BaseModel):
    lyrics: Optional[str] = None
    language: str = Field(default="Hindi", min_length=1, max_length=40)
    genre: str = Field(default="Pop", min_length=1, max_length=80)
    production_style: Optional[str] = Field(default=None, max_length=80)
    arrangement_style: Optional[str] = Field(default=None, max_length=100)
    mood_tags: list[str] = Field(default_factory=list)
    instruments: list[str] = Field(default_factory=list)
    bpm: Optional[int] = Field(default=None, ge=40, le=220)
    key: Optional[str] = Field(default=None, max_length=40)
    duration_seconds: Optional[int] = Field(default=None, ge=10, le=600)
    energy: Optional[str] = Field(default=None, max_length=40)
    vocal_audio_path: Optional[str] = Field(default=None, max_length=400)
    vocal_gain_db: Optional[float] = Field(default=None, ge=-24, le=24)
    backing_gain_db: Optional[float] = Field(default=None, ge=-24, le=24)
    ducking_enabled: bool = True
    ducking_amount: Optional[float] = Field(default=None, ge=0, le=1)
    vocal_forward_mix: bool = True
    output_format: str = "mp3"

    @field_validator("output_format")
    @classmethod
    def validate_output_format(cls, value: str) -> str:
        normalized = value.lower().strip()
        if normalized not in {"mp3", "wav"}:
            raise ValueError("output_format must be 'mp3' or 'wav'")
        return normalized


class PromptPreviewRequest(SongGenerateRequest):
    preset_id: Optional[str] = Field(default=None, max_length=120)


class ImproveLyricsRequest(BaseModel):
    lyrics: str = ""
    language: str = "Hindi"
    mood_tags: list[str] = Field(default_factory=list)
    production_style: Optional[str] = None


class ImproveLyricsResponse(BaseModel):
    original_lyrics: str
    improved_lyrics: str
    notes: list[str] = Field(default_factory=list)


class LyricsImproveRequest(BaseModel):
    lyrics: str = ""
    language: str = "Hindi"
    mood_tags: list[str] = Field(default_factory=list)
    production_style: Optional[str] = None
    arrangement_style: Optional[str] = None
    target_section: Optional[str] = None
    preserve_meaning: bool = True
    intensity: str = "medium"


class LyricsImproveResponse(BaseModel):
    original_lyrics: str
    improved_lyrics: str
    detected_language_style: Optional[str] = None
    suggested_sections: list[str] = Field(default_factory=list)
    rhyme_notes: list[str] = Field(default_factory=list)
    pronunciation_notes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    assistant_mode: str = "rules"
    notes: list[str] = Field(default_factory=list)


class ProducerSuggestionRequest(BaseModel):
    lyrics: Optional[str] = None
    language: str = "Hindi"
    mood_tags: list[str] = Field(default_factory=list)
    genre: Optional[str] = None
    production_style: Optional[str] = None
    arrangement_style: Optional[str] = None
    instruments: list[str] = Field(default_factory=list)
    bpm: Optional[int] = Field(default=None, ge=40, le=220)
    key: Optional[str] = Field(default=None, max_length=40)
    duration_seconds: Optional[int] = Field(default=None, ge=10, le=600)


class ProducerSuggestionResponse(BaseModel):
    recommended_preset_id: Optional[str] = None
    recommended_genre: Optional[str] = None
    recommended_production_style: Optional[str] = None
    recommended_arrangement_style: Optional[str] = None
    recommended_mood_tags: list[str] = Field(default_factory=list)
    recommended_instruments: list[str] = Field(default_factory=list)
    recommended_bpm: Optional[int] = None
    recommended_key: Optional[str] = None
    reasoning: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    prompt_hints: list[str] = Field(default_factory=list)


class QualityExplanationRequest(BaseModel):
    quality_report: Optional["QualityReport"] = None
    diagnostics: Optional["GenerationDiagnostics"] = None
    mix_diagnostics: Optional["MixDiagnostics"] = None


class QualityExplanationResponse(BaseModel):
    summary: str
    issues: list[str] = Field(default_factory=list)
    suggested_fixes: list[str] = Field(default_factory=list)
    user_friendly_status: str


class SongAnalysis(BaseModel):
    # Phase 1 producer-facing fields.
    bpm: Optional[float] = None
    key: Optional[str] = None
    detected_bpm: Optional[float] = None
    production_bpm: Optional[float] = None
    bpm_confidence: Optional[float] = Field(default=None, ge=0, le=1)
    detected_key: Optional[str] = None
    production_key: Optional[str] = None
    key_confidence: Optional[float] = Field(default=None, ge=0, le=1)
    tempo_feel: Optional[str] = "original"
    mood_tags: list[str] = Field(default_factory=list)
    genre: str = "Pop"
    production_style: Optional[str] = None
    arrangement_style: Optional[str] = None
    main_instruments: list[str] = Field(default_factory=list)
    vocal_priority: Optional[str] = None
    warnings: list[str] = Field(default_factory=list)
    production_recommendations: list[str] = Field(default_factory=list)

    # Legacy fields used by the existing audio worker and mobile contract.
    primary_key: Optional[str] = None
    alternative_key: Optional[str] = None
    key_candidates: list[str] = Field(default_factory=list)
    duration_seconds: Optional[float] = Field(default=None, ge=0)
    energy: Optional[str] = None
    mood: Optional[str] = None
    compatible_genre: Optional[str] = None
    detected_instruments: list[str] = Field(default_factory=list)
    recommended_production: list[str] = Field(default_factory=list)
    pitch_contour_status: str = "unavailable"
    melody_midi_status: str = "unavailable"
    vocal_energy: Optional[float] = Field(default=None, ge=0)
    suggested_genre: Optional[Genre] = None
    pitch_summary: Optional[str] = None

    def model_post_init(self, __context: Any) -> None:
        if self.detected_key is None:
            self.detected_key = self.primary_key or self.key
        if self.production_key is None:
            self.production_key = self.primary_key or self.key
        if not self.production_recommendations and self.recommended_production:
            self.production_recommendations = list(self.recommended_production)
        if not self.recommended_production and self.production_recommendations:
            self.recommended_production = list(self.production_recommendations)


class GenerationDiagnostics(BaseModel):
    generator_name: Optional[str] = None
    status: str
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    failed_step: Optional[str] = None
    error_message: Optional[str] = None
    fallback_used: bool = False
    fallback_reason: Optional[str] = None
    last_logs: list[str] = Field(default_factory=list)
    suggested_fix: Optional[str] = None
    command_used: Optional[str] = None


class QualityReport(BaseModel):
    audio_exists: bool = False
    file_size_bytes: Optional[int] = None
    duration_seconds: Optional[float] = None
    is_silent: Optional[bool] = None
    peak_db: Optional[float] = None
    loudness_estimate: Optional[float] = None
    clipping_detected: Optional[bool] = None
    sample_rate: Optional[int] = None
    channels: Optional[int] = None
    format: Optional[str] = None
    generator_name: Optional[str] = None
    fallback_used: bool = False
    warnings: list[str] = Field(default_factory=list)
    validation_errors: list[str] = Field(default_factory=list)
    passed: bool = False


class AudioExport(BaseModel):
    preview_mp3_path: Optional[str] = None
    final_wav_path: Optional[str] = None
    final_mp3_path: Optional[str] = None
    backing_audio_path: Optional[str] = None
    backing_audio_url: Optional[str] = None
    mixed_preview_path: Optional[str] = None
    mixed_preview_url: Optional[str] = None
    final_mix_wav_path: Optional[str] = None
    final_mix_mp3_path: Optional[str] = None
    final_mix_mp3_url: Optional[str] = None
    stems_dir: Optional[str] = None
    quality_report: Optional[QualityReport] = None
    backing_quality_report: Optional[QualityReport] = None


class MixDiagnostics(BaseModel):
    status: str
    vocal_path: Optional[str] = None
    backing_path: Optional[str] = None
    preview_path: Optional[str] = None
    final_wav_path: Optional[str] = None
    final_mp3_path: Optional[str] = None
    vocal_gain_db: Optional[float] = None
    backing_gain_db: Optional[float] = None
    ducking_enabled: Optional[bool] = None
    ducking_amount: Optional[float] = None
    duration_seconds: Optional[float] = None
    warnings: list[str] = Field(default_factory=list)
    error_message: Optional[str] = None
    suggested_fix: Optional[str] = None


class MixRequest(BaseModel):
    vocal_audio_path: str = Field(min_length=1, max_length=600)
    backing_audio_path: str = Field(min_length=1, max_length=600)
    vocal_gain_db: Optional[float] = Field(default=None, ge=-24, le=24)
    backing_gain_db: Optional[float] = Field(default=None, ge=-24, le=24)
    ducking_enabled: Optional[bool] = None
    ducking_amount: Optional[float] = Field(default=None, ge=0, le=1)
    output_format: str = "mp3"

    @field_validator("output_format")
    @classmethod
    def validate_output_format(cls, value: str) -> str:
        normalized = value.lower().strip()
        if normalized not in {"mp3", "wav"}:
            raise ValueError("output_format must be 'mp3' or 'wav'")
        return normalized


class MixResponse(BaseModel):
    status: str
    audio_export: Optional[AudioExport] = None
    quality_report: Optional[QualityReport] = None
    diagnostics: Optional[MixDiagnostics] = None


class StemSeparationRequest(BaseModel):
    audio_path: str = Field(min_length=1, max_length=600)
    stems: list[str] = Field(default_factory=lambda: ["vocals", "drums", "bass", "other"])
    engine: str = "demucs"
    output_format: str = "wav"

    @field_validator("output_format")
    @classmethod
    def validate_output_format(cls, value: str) -> str:
        normalized = value.lower().strip().lstrip(".")
        if normalized != "wav":
            raise ValueError("Phase 9 stem export currently supports wav output")
        return normalized


class StemSeparationResponse(BaseModel):
    status: str
    engine: str
    source_audio_path: Optional[str] = None
    stems_dir: Optional[str] = None
    stem_paths: dict[str, str] = Field(default_factory=dict)
    stem_urls: dict[str, str] = Field(default_factory=dict)
    diagnostics: Optional[GenerationDiagnostics] = None
    quality_reports: dict[str, QualityReport] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class SectionEditRequest(BaseModel):
    source_audio_path: Optional[str] = Field(default=None, max_length=600)
    source_job_id: Optional[str] = Field(default=None, max_length=120)
    section_name: str = Field(min_length=1, max_length=80)
    section_start_seconds: Optional[float] = Field(default=None, ge=0)
    section_end_seconds: Optional[float] = Field(default=None, ge=0)
    edit_instruction: str = Field(min_length=1, max_length=1200)
    lyrics: Optional[str] = None
    language: str = "Hindi"
    genre: Optional[str] = Field(default=None, max_length=80)
    production_style: Optional[str] = Field(default=None, max_length=100)
    arrangement_style: Optional[str] = Field(default=None, max_length=120)
    mood_tags: list[str] = Field(default_factory=list)
    instruments: list[str] = Field(default_factory=list)
    bpm: Optional[int] = Field(default=None, ge=40, le=220)
    key: Optional[str] = Field(default=None, max_length=40)
    duration_seconds: Optional[float] = Field(default=None, gt=0, le=600)
    preserve_vocal: bool = True
    preserve_style: bool = True
    repaint_mode: str = Field(default="balanced", max_length=20)
    repaint_strength: float = Field(default=0.65, ge=0, le=1)
    boundary_crossfade_seconds: float = Field(default=0.025, ge=0, le=0.25)


class SectionEditResponse(BaseModel):
    status: str
    mode: str
    section_name: str
    edit_prompt: str
    output_audio_path: Optional[str] = None
    output_audio_url: Optional[str] = None
    diagnostics: Optional[GenerationDiagnostics] = None
    quality_report: Optional[QualityReport] = None
    edit_metadata: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    message: Optional[str] = None


class StemMixerState(BaseModel):
    stem_volumes: dict[str, float] = Field(default_factory=dict)
    stem_mutes: dict[str, bool] = Field(default_factory=dict)
    stem_solos: dict[str, bool] = Field(default_factory=dict)


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: Optional[str] = Field(default=None, max_length=1000)
    lyrics: Optional[str] = None
    language: str = "Hindi"
    genre: Optional[str] = Field(default=None, max_length=80)
    production_style: Optional[str] = Field(default=None, max_length=100)
    arrangement_style: Optional[str] = Field(default=None, max_length=120)
    mood_tags: list[str] = Field(default_factory=list)
    instruments: list[str] = Field(default_factory=list)
    bpm: Optional[int] = Field(default=None, ge=40, le=220)
    key: Optional[str] = Field(default=None, max_length=40)
    duration_seconds: Optional[int] = Field(default=None, ge=1, le=600)
    source_job_id: Optional[str] = Field(default=None, max_length=120)
    audio_paths: dict[str, str] = Field(default_factory=dict)
    notes: Optional[str] = None


class ProjectUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    description: Optional[str] = Field(default=None, max_length=1000)
    lyrics: Optional[str] = None
    settings: Optional[dict[str, Any]] = None
    audio_paths: Optional[dict[str, str]] = None
    notes: Optional[str] = None


class ProjectResponse(BaseModel):
    project_id: str
    name: str
    description: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    lyrics: Optional[str] = None
    settings: dict[str, Any] = Field(default_factory=dict)
    audio_paths: dict[str, str] = Field(default_factory=dict)
    audio_urls: dict[str, str] = Field(default_factory=dict)
    source_job_id: Optional[str] = None
    quality_report: Optional[QualityReport] = None
    diagnostics: Optional[GenerationDiagnostics] = None
    notes: Optional[str] = None


class ProjectListResponse(BaseModel):
    projects: list[ProjectResponse] = Field(default_factory=list)
    count: int = 0


class ExportRequest(BaseModel):
    project_id: Optional[str] = Field(default=None, max_length=120)
    job_id: Optional[str] = Field(default=None, max_length=120)
    include_audio: bool = True
    include_prompts: bool = True
    include_quality_report: bool = True
    include_diagnostics: bool = True
    include_stems: bool = False
    format: str = "manifest_json"

    @field_validator("format")
    @classmethod
    def validate_format(cls, value: str) -> str:
        normalized = value.lower().strip()
        if normalized not in {"manifest_json"}:
            raise ValueError("Phase 10 export format must be manifest_json")
        return normalized


class ExportResponse(BaseModel):
    status: str
    export_id: str
    export_dir: Optional[str] = None
    manifest_path: Optional[str] = None
    manifest_url: Optional[str] = None
    files: dict[str, str] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    message: Optional[str] = None


class AppHealthResponse(BaseModel):
    status: str
    app_env: str
    version: Optional[str] = None
    checks: dict[str, dict[str, Any]] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class CleanupRequest(BaseModel):
    dry_run: bool = True
    older_than_days: Optional[int] = Field(default=None, ge=0)
    include_outputs: bool = False
    include_mock_jobs: bool = False


class CleanupResponse(BaseModel):
    status: str
    dry_run: bool
    files_found: int = 0
    files_deleted: int = 0
    bytes_found: int = 0
    bytes_deleted: int = 0
    warnings: list[str] = Field(default_factory=list)


class AudioUploadResponse(BaseModel):
    upload_id: str
    filename: str
    content_type: Optional[str] = None
    original_path: str
    audio_url: Optional[str] = None
    duration_seconds: Optional[float] = None
    quality_report: Optional[QualityReport] = None
    warnings: list[str] = Field(default_factory=list)


class SongLanguageInfo(BaseModel):
    primary: str = "unknown"
    secondary: Optional[str] = None
    confidence: float = Field(default=0, ge=0, le=1)


class SongTempoInfo(BaseModel):
    bpm: Optional[float] = Field(default=None, ge=0)
    confidence: float = Field(default=0, ge=0, le=1)
    rubato: bool = False
    tempo_drift_percent: float = Field(default=0, ge=0)
    half_time_bpm: Optional[float] = Field(default=None, ge=0)
    double_time_bpm: Optional[float] = Field(default=None, ge=0)
    downbeats: list[float] = Field(default_factory=list)
    source: str = "unavailable"


class SongTonalityInfo(BaseModel):
    key: str = "A"
    scale: str = "minor"
    confidence: float = Field(default=0, ge=0, le=1)
    key_changes: list[dict[str, Any]] = Field(default_factory=list)
    source: str = "audio_chroma"


class SongVocalRange(BaseModel):
    lowest_note: Optional[str] = None
    highest_note: Optional[str] = None
    lowest_midi: Optional[float] = None
    highest_midi: Optional[float] = None


class SongAudioIntelligence(BaseModel):
    architecture: Optional[str] = None
    device: Optional[str] = None
    analysis_scope: str = "complete"
    windows_analysed: int = Field(default=0, ge=0)
    singing_speech: Optional[str] = None
    singing_speech_confidence: Optional[float] = Field(default=None, ge=0, le=1)
    vocal_technique_probabilities: dict[str, float] = Field(default_factory=dict)
    mood_probabilities: dict[str, float] = Field(default_factory=dict)
    tempo_family: Optional[str] = None
    melodic_character: Optional[str] = None
    in_distribution_probability: Optional[float] = Field(default=None, ge=0, le=1)
    requires_confirmation: bool = True
    trained_heads: dict[str, bool] = Field(default_factory=dict)


class SongIntelligenceMap(BaseModel):
    duration_seconds: float = Field(default=0, ge=0)
    analysis_scope: str = "complete"
    language: SongLanguageInfo = Field(default_factory=SongLanguageInfo)
    tempo: SongTempoInfo = Field(default_factory=SongTempoInfo)
    tonality: SongTonalityInfo = Field(default_factory=SongTonalityInfo)
    time_signature: str = "4/4"
    time_signature_confidence: float = Field(default=0, ge=0, le=1)
    vocal_range: SongVocalRange = Field(default_factory=SongVocalRange)
    mood: list[str] = Field(default_factory=list)
    genre_probabilities: dict[str, float] = Field(default_factory=dict)
    genre_source: str = "unavailable"
    genre_requires_confirmation: bool = True
    phrases: list[dict[str, Any]] = Field(default_factory=list)
    sections: list[dict[str, Any]] = Field(default_factory=list)
    energy_curve: list[dict[str, Any]] = Field(default_factory=list)
    melody_curve: list[dict[str, Any]] = Field(default_factory=list)
    stable_notes: list[dict[str, Any]] = Field(default_factory=list)
    note_transitions: list[dict[str, Any]] = Field(default_factory=list)
    pitch_slides: list[dict[str, Any]] = Field(default_factory=list)
    ornamentation: list[dict[str, Any]] = Field(default_factory=list)
    melodic_motifs: list[dict[str, Any]] = Field(default_factory=list)
    lyrical_motifs: list[dict[str, Any]] = Field(default_factory=list)
    chord_compatibility: list[dict[str, Any]] = Field(default_factory=list)
    rhythm_analysis: dict[str, Any] = Field(default_factory=dict)
    structure_analysis: dict[str, Any] = Field(default_factory=dict)
    confirmed_corrections: dict[str, Any] = Field(default_factory=dict)
    silence_regions: list[dict[str, Any]] = Field(default_factory=list)
    breath_regions: list[dict[str, Any]] = Field(default_factory=list)
    pitch_method: str = "unavailable"
    audio_intelligence: Optional[SongAudioIntelligence] = None


class VocalAnalysisReport(BaseModel):
    upload_id: Optional[str] = None
    source_audio_path: str
    normalized_wav_path: Optional[str] = None
    normalized_wav_url: Optional[str] = None
    duration_seconds: Optional[float] = None
    sample_rate: Optional[int] = None
    channels: Optional[int] = None
    is_silent: Optional[bool] = None
    estimated_bpm: Optional[float] = None
    estimated_key: Optional[str] = None
    key_confidence: Optional[float] = None
    pitch_contour_status: str = "unavailable"
    phrase_boundaries: list[dict[str, Any]] = Field(default_factory=list)
    section_candidates: list[dict[str, Any]] = Field(default_factory=list)
    vocal_activity: list[dict[str, Any]] = Field(default_factory=list)
    song_intelligence_map: Optional[SongIntelligenceMap] = None
    peak_db: Optional[float] = None
    loudness_estimate: Optional[float] = None
    quality_report: Optional[QualityReport] = None
    warnings: list[str] = Field(default_factory=list)


class SkarlyDetected(BaseModel):
    language: str = "Hindi"
    language_confidence: Optional[float] = Field(default=None, ge=0, le=1)
    classification_source: Optional[str] = None
    mood: str = "Sad / Emotional"
    vocal_type: str = "Singing"
    bpm: Optional[int] = None
    key: Optional[str] = None
    timing_summary: Optional[str] = None
    phrase_count: Optional[int] = None
    song_structure: list[dict[str, Any]] = Field(default_factory=list)
    genre_hint: Optional[str] = None
    genre_confidence: Optional[float] = Field(default=None, ge=0, le=1)
    genre_source: Optional[str] = None
    genre_probabilities: dict[str, float] = Field(default_factory=dict)
    audio_intelligence: Optional[SongAudioIntelligence] = None
    analysis_scope_seconds: Optional[float] = None
    lyrics_preview: Optional[str] = None
    source_profile: Optional[str] = None
    energy: Optional[str] = None
    input_quality: Optional[str] = None
    input_quality_note: Optional[str] = None
    melody_midi_status: str = "unavailable"
    song_intelligence_map: Optional[SongIntelligenceMap] = None


class SkarlyWaveforms(BaseModel):
    input_vocal: list[float] = Field(default_factory=list)
    backing: list[float] = Field(default_factory=list)
    final_mix: list[float] = Field(default_factory=list)


class GenerationTelemetry(BaseModel):
    cuda_available: bool = False
    device: Optional[str] = None
    device_capability: Optional[str] = None
    torch_version: Optional[str] = None
    torch_cuda_runtime: Optional[str] = None
    compiled_architectures: list[str] = Field(default_factory=list)
    generation_backend: str
    model: str
    peak_vram_mb: float = Field(default=0, ge=0)
    generation_seconds: float = Field(default=0, ge=0)
    cpu_fallback: bool = False


class ArrangementDiversityPair(BaseModel):
    left_index: int = Field(ge=1, le=5)
    right_index: int = Field(ge=1, le=5)
    left_file: str
    right_file: str
    embedding_similarity: float = Field(ge=0, le=1)
    drum_onset_similarity: float = Field(ge=0, le=1)
    chord_change_similarity: float = Field(ge=0, le=1)
    instrumentation_similarity: float = Field(ge=0, le=1)
    perceptual_similarity: float = Field(ge=0, le=1)
    rejected: bool = False
    reason: Optional[str] = None


class ArrangementDiversityReport(BaseModel):
    method: str = "skarly-perceptual-v1"
    calibration: str = "prototype-conservative-v1"
    calibration_approved: bool = False
    calibration_sample_count: int = Field(default=0, ge=0)
    calibration_rater_count: int = Field(default=0, ge=0)
    calibration_manifest_sha256: Optional[str] = None
    calibration_note: Optional[str] = None
    passed: bool
    evaluated_pairs: int = Field(ge=0, le=10)
    rejected_pairs: int = Field(ge=0, le=10)
    thresholds: dict[str, float] = Field(default_factory=dict)
    pairs: list[ArrangementDiversityPair] = Field(default_factory=list)


class MusicalCompatibilityQuality(BaseModel):
    target_bpm: float = Field(gt=0)
    output_bpm: Optional[float] = Field(default=None, gt=0)
    tempo_delta_bpm: Optional[float] = Field(default=None, ge=0)
    tempo_tolerance_bpm: float = Field(gt=0)
    tempo_match: bool = False
    target_key: str
    output_key: Optional[str] = None
    output_key_confidence: Optional[float] = Field(default=None, ge=0, le=1)
    key_match: bool = False
    key_match_method: str = "exact"
    key_correction_applied: bool = False
    key_correction_semitones: Optional[int] = Field(default=None, ge=-6, le=6)
    pre_correction_output_key: Optional[str] = None
    post_correction_detected_key: Optional[str] = None
    melody_chord_tone_ratio: Optional[float] = Field(default=None, ge=0, le=1)
    melody_match: bool = False
    phrase_beat_alignment_ratio: Optional[float] = Field(default=None, ge=0, le=1)
    phrase_match: bool = False
    downbeat_alignment_ratio: Optional[float] = Field(default=None, ge=0, le=1)
    downbeat_match: bool = False
    analysed_phrase_count: int = Field(default=0, ge=0)
    analysed_downbeat_count: int = Field(default=0, ge=0)
    analysed_melody_points: int = Field(default=0, ge=0)
    passed: bool = False
    warnings: list[str] = Field(default_factory=list)


class SkarlyVersion(BaseModel):
    name: str
    input_vocal_url: Optional[str] = None
    melody_midi_url: Optional[str] = None
    backing_url: str
    final_mix_url: str
    waveforms: Optional[SkarlyWaveforms] = None
    prompt: Optional[str] = None
    generator: Optional[str] = None
    generation_engine: Optional[str] = None
    style_family: Optional[str] = None
    instruments: list[str] = Field(default_factory=list)
    energy: Optional[str] = None
    rhythm_character: Optional[str] = None
    producer_mix_mode: Optional[str] = None
    blueprint: dict[str, str] = Field(default_factory=dict)
    seed: Optional[int] = None
    mix_note: Optional[str] = None
    fallback_used: bool = False
    is_fallback: bool = False
    transformation_quality: Optional[dict[str, Any]] = None
    musical_compatibility: Optional[MusicalCompatibilityQuality] = None


class SkarlyStudioAnalyzeRequest(BaseModel):
    upload_id: Optional[str] = Field(default=None, min_length=1, max_length=160)
    raw_audio_path: Optional[str] = Field(default=None, min_length=1, max_length=500)
    language_override: Optional[str] = Field(default=None, max_length=40)
    mood_override: Optional[str] = Field(default=None, max_length=80)


class SkarlyStudioAnalyzeResponse(BaseModel):
    job_id: str
    upload_id: str
    status: str = "analysis_ready"
    detected: SkarlyDetected
    normalized_wav_url: Optional[str] = None
    vocal_url: Optional[str] = None
    melody_midi_url: Optional[str] = None
    analysis_url: Optional[str] = None
    song_intelligence_map: Optional[SongIntelligenceMap] = None
    warnings: list[str] = Field(default_factory=list)


class SkarlyStudioGenerateRequest(BaseModel):
    upload_id: Optional[str] = Field(default=None, min_length=1, max_length=160)
    raw_audio_path: Optional[str] = Field(default=None, min_length=1, max_length=500)
    language: Optional[str] = Field(default=None, max_length=40)
    mood: Optional[str] = Field(default=None, max_length=80)
    genre_override: Optional[str] = Field(default=None, max_length=80)
    training_opt_in: bool = False
    mix_preset: str = Field(default="balanced", max_length=40)
    arrangement_mode: ArrangementMode = ArrangementMode.vocal_to_song
    preserve_original_vocal: bool = True
    reference_strength: float = Field(default=0.35, ge=0.05, le=0.95)


class SkarlyVersionSelectionRequest(BaseModel):
    version_index: int = Field(ge=0, le=4)


class SkarlyStudioResponse(BaseModel):
    job_id: str
    detected: SkarlyDetected
    versions: list[SkarlyVersion]
    status: str = "ready"
    # Keep the public API aligned with the mobile studio default.  Clients that
    # omit this field should hear a balanced music bed, not an unexpectedly
    # reduced backing track.
    mix_preset: str = "balanced"
    generator_backend: str = "procedural_v2"
    vocal_url: Optional[str] = None
    melody_midi_url: Optional[str] = None
    analysis_url: Optional[str] = None
    generation_telemetry: Optional[GenerationTelemetry] = None
    arrangement_diversity: Optional[ArrangementDiversityReport] = None
    song_intelligence_map: Optional[SongIntelligenceMap] = None
    source_preparation: Optional[dict[str, Any]] = None
    warnings: list[str] = Field(default_factory=list)


class SkarlyV2AnalyzeRequest(BaseModel):
    upload_id: Optional[str] = Field(default=None, min_length=1, max_length=160)
    raw_audio_path: Optional[str] = Field(default=None, min_length=1, max_length=500)
    language_override: Optional[str] = Field(default=None, max_length=40)
    mood_override: Optional[str] = Field(default=None, max_length=80)


class SkarlyV2GenerationRequest(BaseModel):
    analysis_id: str = Field(min_length=1, max_length=160)
    duration_seconds: Optional[float] = Field(default=None, gt=0, le=600)
    arrangement_profiles: list[str] = Field(
        default_factory=lambda: [
            "bollywood_acoustic",
            "modern_bollywood",
            "sufi_live",
            "punjabi_rhythm",
            "cinematic_urban",
        ]
    )
    mix_profile: str = Field(default="balanced", max_length=40)
    require_cuda: bool = True
    number_of_outputs: int = Field(default=5, ge=1, le=5)
    language: Optional[str] = Field(default=None, max_length=40)
    mood: Optional[str] = Field(default=None, max_length=80)
    genre_override: Optional[str] = Field(default=None, max_length=80)
    bpm_override: Optional[float] = Field(default=None, ge=40, le=220)
    key_override: Optional[str] = Field(default=None, max_length=40)
    arrangement_mode: ArrangementMode = ArrangementMode.vocal_to_song
    preserve_original_vocal: bool = True
    reference_strength: float = Field(default=0.35, ge=0.05, le=0.95)

    @field_validator("arrangement_profiles")
    @classmethod
    def validate_arrangement_profiles(cls, value: list[str]) -> list[str]:
        normalized = [str(item).strip().lower().replace("-", "_") for item in value]
        if len(normalized) != 5:
            raise ValueError("Exactly five arrangement profiles are required")
        if len(set(normalized)) != 5:
            raise ValueError("Arrangement profiles must be unique")
        if any(not item for item in normalized):
            raise ValueError("Arrangement profile IDs cannot be empty")
        return normalized

    @field_validator("number_of_outputs")
    @classmethod
    def validate_number_of_outputs(cls, value: int) -> int:
        if value != 5:
            raise ValueError("Skarly V2 always creates exactly five outputs")
        return value

    @field_validator("key_override")
    @classmethod
    def validate_key_override(cls, value: Optional[str]) -> Optional[str]:
        if value is None or not value.strip():
            return None
        parts = value.strip().replace("♭", "b").replace("♯", "#").split()
        allowed_roots = {"C", "C#", "Db", "D", "D#", "Eb", "E", "F", "F#", "Gb", "G", "G#", "Ab", "A", "A#", "Bb", "B"}
        if len(parts) != 2 or parts[0] not in allowed_roots or parts[1].lower() not in {"major", "minor"}:
            raise ValueError("key_override must use a key and scale such as D minor or F# major")
        return f"{parts[0]} {parts[1].lower()}"


class SkarlyV2RegenerateRequest(BaseModel):
    generation_id: str = Field(min_length=1, max_length=160)
    version_index: int = Field(ge=0, le=4)
    producer_profile_id: Optional[str] = Field(default=None, max_length=80)
    energy_delta: int = Field(default=0, ge=-1, le=1)
    instrument_change: Optional[str] = Field(default=None, max_length=160)


class SkarlyV2SectionRegenerateRequest(BaseModel):
    generation_id: str = Field(min_length=1, max_length=160)
    version_index: int = Field(ge=0, le=4)
    section_name: str = Field(default="selected section", min_length=1, max_length=80)
    section_start_seconds: float = Field(ge=0)
    section_end_seconds: float = Field(gt=0)
    edit_instruction: str = Field(min_length=1, max_length=1200)
    repaint_mode: str = Field(default="balanced", max_length=20)
    repaint_strength: float = Field(default=0.65, ge=0, le=1)
    boundary_crossfade_seconds: float = Field(default=0.025, ge=0, le=0.25)


class SkarlyV2MixRequest(BaseModel):
    generation_id: str = Field(min_length=1, max_length=160)
    version_index: int = Field(ge=0, le=4)
    mix_profile: str = Field(default="balanced", max_length=40)
    vocal_music_balance: float = Field(default=0, ge=-1, le=1)


class SkarlyV2ExportRequest(BaseModel):
    generation_id: str = Field(min_length=1, max_length=160)
    version_index: int = Field(ge=0, le=4)
    include_optional_stems: bool = False


class SkarlyV2ExportResponse(BaseModel):
    status: str = "ready"
    export_id: str
    generation_id: str
    version_index: int
    arrangement_name: str
    duration_seconds: float = Field(gt=0)
    files: dict[str, str] = Field(default_factory=dict)
    sha256: dict[str, str] = Field(default_factory=dict)
    durations_seconds: dict[str, float] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class SkarlyV2FeedbackRequest(BaseModel):
    generation_id: str = Field(min_length=1, max_length=160)
    selected_arrangement: Optional[int] = Field(default=None, ge=0, le=4)
    corrected_genre: Optional[str] = Field(default=None, max_length=80)
    corrected_language: Optional[str] = Field(default=None, max_length=40)
    mix_preference: Optional[str] = Field(default=None, max_length=40)
    user_rating: Optional[int] = Field(default=None, ge=1, le=5)
    explicit_training_consent: bool = False
    dataset_usage_permission_version: Optional[str] = Field(default=None, max_length=80)
    rights_confirmed: bool = False
    copyright_owner: Optional[str] = Field(default=None, max_length=160)
    commercial_use_permission: bool = False
    revocation_policy: Optional[str] = Field(default=None, max_length=240)
    singer_id: Optional[str] = Field(default=None, max_length=160)
    recording_conditions: Optional[str] = Field(default=None, max_length=240)
    confirmed_singing_speech: Optional[str] = Field(default=None, max_length=40)
    confirmed_vocal_techniques: list[str] = Field(default_factory=list, max_length=8)
    confirmed_moods: list[str] = Field(default_factory=list, max_length=8)
    confirmed_tempo_family: Optional[str] = Field(default=None, max_length=20)
    confirmed_melodic_character: Optional[str] = Field(default=None, max_length=20)
    confirmed_in_distribution: Optional[bool] = None
    notes: Optional[str] = Field(default=None, max_length=1000)


class SkarlyProducerProfileResponse(BaseModel):
    profile_id: str
    name: str
    instruments: list[str] = Field(default_factory=list)
    energy: str
    rhythm_character: str
    mix_mode: str
    blueprint: dict[str, str] = Field(default_factory=dict)
    is_default: bool = False


class SkarlyV2JobResponse(BaseModel):
    job_id: str
    job_type: str
    status: str
    stage: str
    progress: float = Field(default=0, ge=0, le=100)
    created_at: str
    updated_at: str
    upload_id: Optional[str] = None
    analysis_id: Optional[str] = None
    current_arrangement: Optional[int] = Field(default=None, ge=1, le=5)
    completed_arrangements: int = Field(default=0, ge=0, le=5)
    total_arrangements: int = Field(default=0, ge=0, le=5)
    completed_duration_seconds: float = Field(default=0, ge=0)
    cuda_device: Optional[str] = None
    model: Optional[str] = None
    warnings: list[str] = Field(default_factory=list)
    completed_outputs: list[dict[str, Any]] = Field(default_factory=list)
    result: Optional[dict[str, Any]] = None
    error: Optional[dict[str, Any]] = None


class MusicCompositionPlan(BaseModel):
    plan_id: str
    mode: str
    provider_prompt: str
    negative_prompt: str
    bpm: Optional[int] = None
    key: Optional[str] = None
    duration_seconds: Optional[int] = None
    genre: Optional[str] = None
    production_style: Optional[str] = None
    arrangement_style: Optional[str] = None
    mood_tags: list[str] = Field(default_factory=list)
    instruments: list[str] = Field(default_factory=list)
    sections: list[dict[str, Any]] = Field(default_factory=list)
    mix_direction: str = "vocal-forward"
    provider_preferences: list[str] = Field(default_factory=list)
    reference_strength: Optional[float] = Field(default=None, ge=0.05, le=0.95)
    warnings: list[str] = Field(default_factory=list)


class OnlineGenerationDiagnostics(BaseModel):
    status: str
    provider_order: list[str] = Field(default_factory=list)
    fallback_used: bool = False
    rights_confirmed: bool = False
    failed_step: Optional[str] = None
    error_message: Optional[str] = None
    suggested_fix: Optional[str] = None
    last_logs: list[str] = Field(default_factory=list)


class VocalLeakageQuality(BaseModel):
    status: str = "not_run"
    waveform_correlation: Optional[float] = None
    low_activity_spectral_similarity: Optional[float] = None
    low_activity_leakage_db: Optional[float] = None
    analysed_duration_seconds: Optional[float] = None
    analysed_frames: int = 0
    passed: bool = False
    warnings: list[str] = Field(default_factory=list)


class MusicSourcePreparation(BaseModel):
    requested_mode: str = "auto"
    detected_mode: str = "instrumental"
    separation_status: str = "not_required"
    vocal_detected: bool = False
    vocal_preserved: bool = False
    detection_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source_audio_path: Optional[str] = None
    instrumental_audio_path: Optional[str] = None
    instrumental_audio_url: Optional[str] = None
    vocal_audio_path: Optional[str] = None
    vocal_audio_url: Optional[str] = None
    vocal_energy_db_below_mix: Optional[float] = None
    vocal_activity_ratio: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    vocal_leakage_quality: Optional[VocalLeakageQuality] = None
    quality_reports: dict[str, QualityReport] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class MusicTransformationQuality(BaseModel):
    source_sha256: Optional[str] = None
    output_sha256: Optional[str] = None
    hashes_differ: Optional[bool] = None
    waveform_correlation: Optional[float] = None
    onset_similarity: Optional[float] = None
    source_bpm: Optional[float] = None
    output_bpm: Optional[float] = None
    tempo_family_delta_bpm: Optional[float] = None
    duration_match: bool = False
    original_enough: bool = False
    vocal_check_status: str = "not_run"
    vocal_energy_db_below_mix: Optional[float] = None
    vocal_leakage_detected: Optional[bool] = None
    passed: bool = False
    warnings: list[str] = Field(default_factory=list)


class OnlineGenerationCandidate(BaseModel):
    candidate_id: str
    provider_name: str
    status: str
    backing_audio_path: Optional[str] = None
    backing_audio_url: Optional[str] = None
    mixed_preview_path: Optional[str] = None
    mixed_preview_url: Optional[str] = None
    final_mix_wav_path: Optional[str] = None
    final_mix_mp3_path: Optional[str] = None
    final_mix_mp3_url: Optional[str] = None
    quality_report: Optional[QualityReport] = None
    mix_quality_report: Optional[QualityReport] = None
    score: Optional[float] = None
    reference_conditioned: bool = False
    reference_strength: Optional[float] = Field(default=None, ge=0.05, le=0.95)
    transformation_quality: Optional[MusicTransformationQuality] = None
    diagnostics: Optional[OnlineGenerationDiagnostics] = None
    warnings: list[str] = Field(default_factory=list)
    prompt: Optional[str] = None


class VocalToMusicRequest(BaseModel):
    upload_id: str = Field(min_length=1, max_length=160)
    lyrics: Optional[str] = None
    language: str = "Hindi"
    genre: Optional[str] = "Pop"
    production_style: Optional[str] = None
    arrangement_style: Optional[str] = None
    mood_tags: list[str] = Field(default_factory=list)
    instruments: list[str] = Field(default_factory=list)
    bpm: Optional[int] = Field(default=None, ge=40, le=220)
    key: Optional[str] = Field(default=None, max_length=40)
    duration_seconds: Optional[int] = Field(default=None, ge=3, le=600)
    provider_preference: Optional[str] = None
    candidate_count: Optional[int] = Field(default=None, ge=1, le=5)
    rights_confirmed: bool = False
    send_source_audio_to_provider: bool = False
    output_format: str = "mp3"

    @field_validator("output_format")
    @classmethod
    def validate_output_format(cls, value: str) -> str:
        normalized = value.lower().strip()
        if normalized not in {"mp3", "wav"}:
            raise ValueError("output_format must be 'mp3' or 'wav'")
        return normalized


class MusicToMusicRequest(BaseModel):
    reference_upload_id: str = Field(min_length=1, max_length=160)
    vocal_upload_id: Optional[str] = Field(default=None, max_length=160)
    style_instruction: str = Field(default="Create a fresh original arrangement inspired by the broad mood and energy.", max_length=1200)
    lyrics: Optional[str] = None
    language: str = "Hindi"
    genre: Optional[str] = "Pop"
    production_style: Optional[str] = None
    arrangement_style: Optional[str] = None
    mood_tags: list[str] = Field(default_factory=list)
    instruments: list[str] = Field(default_factory=list)
    bpm: Optional[int] = Field(default=None, ge=40, le=220)
    key: Optional[str] = Field(default=None, max_length=40)
    duration_seconds: Optional[int] = Field(default=None, ge=3, le=600)
    provider_preference: Optional[str] = None
    candidate_count: Optional[int] = Field(default=None, ge=1, le=5)
    rights_confirmed: bool = False
    send_source_audio_to_provider: bool = False
    source_mode: str = "auto"
    preserve_original_vocal: bool = False
    reference_strength: float = Field(default=0.35, ge=0.05, le=0.95)
    output_format: str = "mp3"

    @field_validator("output_format")
    @classmethod
    def validate_output_format(cls, value: str) -> str:
        normalized = value.lower().strip()
        if normalized not in {"mp3", "wav"}:
            raise ValueError("output_format must be 'mp3' or 'wav'")
        return normalized

    @field_validator("source_mode")
    @classmethod
    def validate_source_mode(cls, value: str) -> str:
        normalized = value.lower().strip().replace("-", "_")
        if normalized not in {"auto", "instrumental", "full_song"}:
            raise ValueError("source_mode must be 'auto', 'instrumental', or 'full_song'")
        return normalized


class RegenerateMusicRequest(BaseModel):
    edit_instruction: str = Field(min_length=1, max_length=1200)
    candidate_count: Optional[int] = Field(default=None, ge=1, le=5)
    provider_preference: Optional[str] = None
    reference_strength: Optional[float] = Field(default=None, ge=0.05, le=0.95)
    rights_confirmed: bool = False


class OnlineGenerationResponse(BaseModel):
    job_id: str
    status: str
    mode: str
    upload_id: Optional[str] = None
    reference_upload_id: Optional[str] = None
    vocal_upload_id: Optional[str] = None
    analysis: Optional[VocalAnalysisReport] = None
    reference_analysis: Optional[VocalAnalysisReport] = None
    source_preparation: Optional[MusicSourcePreparation] = None
    composition_plan: Optional[MusicCompositionPlan] = None
    candidates: list[OnlineGenerationCandidate] = Field(default_factory=list)
    best_candidate: Optional[OnlineGenerationCandidate] = None
    diagnostics: Optional[OnlineGenerationDiagnostics] = None
    message: Optional[str] = None


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    progress: Optional[float] = None
    message: Optional[str] = None
    positive_prompt: Optional[str] = None
    negative_prompt: Optional[str] = None
    structured_summary: Optional[dict[str, Any]] = None
    recommended_settings: Optional[dict[str, Any]] = None
    generation_mode: Optional[str] = None
    generated_audio_path: Optional[str] = None
    audio_url: Optional[str] = None
    preview_url: Optional[str] = None
    backing_audio_path: Optional[str] = None
    backing_audio_url: Optional[str] = None
    mixed_preview_path: Optional[str] = None
    mixed_preview_url: Optional[str] = None
    final_mix_wav_path: Optional[str] = None
    final_mix_mp3_path: Optional[str] = None
    final_mix_mp3_url: Optional[str] = None
    audio_export: Optional[AudioExport] = None
    diagnostics: Optional[GenerationDiagnostics] = None
    mix_diagnostics: Optional[MixDiagnostics] = None
    quality_report: Optional[QualityReport] = None
    online_response: Optional[dict[str, Any]] = None


class SongSection(BaseModel):
    name: str
    bars: int = Field(ge=1)
    note: str


class SongBlueprint(BaseModel):
    structure: list[SongSection]
    chords: list[str]
    production_notes: list[str]
    lyric_suggestions: list[str]
    production_style: Optional[str] = None
    arrangement_style: Optional[str] = None
    main_instruments: list[str] = Field(default_factory=list)


class UserContext(BaseModel):
    user_id: str
    creator_mode: CreatorMode = CreatorMode.guest
    email: Optional[str] = None


class UserProfileRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    email: str = Field(min_length=3, max_length=160)
    bio: str = Field(default="Private Skarly workspace", max_length=220)
    photo_url: Optional[str] = None


class UserProfile(BaseModel):
    user_id: str
    creator_mode: CreatorMode = CreatorMode.saved
    name: str
    email: str
    bio: str = "Private Skarly workspace"
    photo_url: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class UserProfileResponse(BaseModel):
    profile: UserProfile


class VoiceTakeRequest(BaseModel):
    title: str = Field(min_length=1, max_length=80)
    duration: int = Field(ge=1, le=60)
    raw_audio_path: str = Field(min_length=1)
    content_type: str = Field(default="audio/mpeg", min_length=1, max_length=80)
    size_bytes: Optional[int] = Field(default=None, ge=1, le=20_000_000)


class VoiceTakeRecord(BaseModel):
    take_id: str
    user_id: str
    title: str
    duration: int
    raw_audio_path: str
    content_type: str = "audio/mpeg"
    size_bytes: Optional[int] = None
    status: ItemStatus = ItemStatus.active
    deleted_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class VoiceTakeResponse(BaseModel):
    take: VoiceTakeRecord


class VoiceTakeListResponse(BaseModel):
    takes: list[VoiceTakeRecord]


class VoiceTakePlaybackResponse(BaseModel):
    take_id: str
    raw_audio_url: str


class SignedUploadRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=160)
    content_type: str = Field(min_length=1, max_length=80)
    size_bytes: int = Field(ge=1, le=20_000_000)
    source_type: SourceType


class SignedUploadResponse(BaseModel):
    upload_id: str
    upload_url: str
    raw_audio_path: str
    expires_in_seconds: int


class UploadVerificationRequest(BaseModel):
    raw_audio_path: str = Field(min_length=1)


class UploadVerificationResponse(BaseModel):
    raw_audio_path: str
    exists: bool


class CreateJobRequest(BaseModel):
    raw_audio_path: str = Field(min_length=1)
    genre: Genre
    track_name: str = Field(min_length=1, max_length=80)
    source_type: SourceType
    arrangement_mode: ArrangementMode = ArrangementMode.vocal_to_song
    language: str = Field(default="Hindi", min_length=1, max_length=40)
    lyrics: Optional[str] = Field(default=None, max_length=2000)
    production_style: Optional[ProductionStyle] = None
    arrangement_style: Optional[str] = Field(default=None, max_length=80)
    main_instruments: list[str] = Field(default_factory=list, max_length=12)
    mood_tags: list[str] = Field(default_factory=list, max_length=12)
    production_bpm: Optional[float] = Field(default=None, ge=20, le=260)
    key_override: Optional[str] = Field(default=None, max_length=40)
    energy_override: Optional[str] = Field(default=None, max_length=40)
    output_duration_seconds: Optional[int] = Field(default=None, ge=10, le=300)
    vocal_gain_db: Optional[float] = Field(default=None, ge=-24, le=24)
    backing_gain_db: Optional[float] = Field(default=None, ge=-24, le=24)
    ducking_strength: Optional[str] = Field(default=None, max_length=20)
    delete_raw_after_mix: bool = True


class UpdateJobLibraryRequest(BaseModel):
    track_name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    library_status: Optional[str] = Field(default=None, max_length=40)


class JobRecord(BaseModel):
    job_id: str
    user_id: str
    creator_mode: CreatorMode
    genre: Genre
    track_name: str
    source_type: SourceType
    arrangement_mode: ArrangementMode = ArrangementMode.vocal_to_song
    production_style: Optional[ProductionStyle] = None
    arrangement_style: Optional[str] = None
    main_instruments: list[str] = Field(default_factory=list)
    raw_audio_path: Optional[str]
    final_mp3_path: Optional[str] = None
    isolated_vocal_path: Optional[str] = None
    backing_audio_path: Optional[str] = None
    export_paths: dict[str, str] = Field(default_factory=dict)
    analysis: Optional[SongAnalysis] = None
    blueprint: Optional[SongBlueprint] = None
    worker_notes: Optional[str] = None
    user_overrides: dict[str, Any] = Field(default_factory=dict)
    final_generation_settings: dict[str, Any] = Field(default_factory=dict)
    generation_diagnostics: dict[str, Any] = Field(default_factory=dict)
    job_logs: list[str] = Field(default_factory=list)
    quality_report: Optional[dict[str, Any]] = None
    status: JobStatus = JobStatus.created
    stage: str = "created"
    library_status: Optional[str] = None
    error: Optional[str] = None
    delete_raw_after_mix: bool = True
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None


class JobResponse(BaseModel):
    job: JobRecord
    quality_report: Optional[dict[str, Any]] = None
    final_mp3_url: Optional[str] = None
    final_mp3_download_url: Optional[str] = None
    final_wav_url: Optional[str] = None
    midi_url: Optional[str] = None
    melody_midi_url: Optional[str] = None
    chord_sheet_url: Optional[str] = None
    producer_pack_url: Optional[str] = None
    isolated_vocal_url: Optional[str] = None
    backing_audio_url: Optional[str] = None
    drums_stem_url: Optional[str] = None
    bass_stem_url: Optional[str] = None
    guitar_stem_url: Optional[str] = None
    keys_stem_url: Optional[str] = None
    reference_stem_url: Optional[str] = None


class HistoryResponse(BaseModel):
    tracks: list[JobRecord]


class RecycleBinResponse(BaseModel):
    voice_takes: list[VoiceTakeRecord]
    tracks: list[JobRecord]


class LibraryRecoveryResponse(BaseModel):
    recovered_voice_takes: int
    recovered_tracks: int
    takes: list[VoiceTakeRecord]
    tracks: list[JobRecord]


class AdminUserSnapshot(BaseModel):
    user_id: str
    name: str
    email: str
    updated_at: datetime


class CloudCostSnapshot(BaseModel):
    period: str
    generations: int
    generation_limit: int
    estimated_cost_usd: float
    unit_cost_usd: float
    generator_backend: str


class CloudRuntimeSnapshot(BaseModel):
    runtime: str
    service: str
    revision: str
    region: str
    project_id: Optional[str] = None
    service_url: Optional[str] = None
    worker_url: Optional[str] = None
    task_queue: str
    storage_bucket: str
    cors_origins: list[str]


class AdminSummaryResponse(BaseModel):
    environment: str
    repository_backend: str
    storage_backend: str
    worker_backend: str
    music_generator_backend: str
    task_backend: str
    bucket: str
    users: list[AdminUserSnapshot]
    recent_jobs: list[JobRecord]
    recent_voice_takes: list[VoiceTakeRecord]
    deleted_jobs: list[JobRecord]
    deleted_voice_takes: list[VoiceTakeRecord]
    counts: dict[str, int]
    cloud_cost: CloudCostSnapshot
    cloud_runtime: CloudRuntimeSnapshot


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"
