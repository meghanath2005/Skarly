import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Animated,
  Image,
  ImageBackground,
  Easing,
  Platform,
  Pressable,
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View
} from "react-native";
import type { DimensionValue } from "react-native";
import Svg, { Circle, Defs, LinearGradient, Path, Rect, Stop } from "react-native-svg";
import { StatusBar } from "expo-status-bar";
import * as DocumentPicker from "expo-document-picker";
import { Audio } from "expo-av";
import { FirebaseError, initializeApp, getApps } from "firebase/app";
import {
  createUserWithEmailAndPassword,
  getAuth,
  onAuthStateChanged,
  signInWithEmailAndPassword,
  signOut,
  type User
} from "firebase/auth";

type Screen =
  | "splash"
  | "login"
  | "authSignIn"
  | "authSignUp"
  | "setup"
  | "home"
  | "record"
  | "upload"
  | "genre"
  | "producer"
  | "processing"
  | "nameTrack"
  | "nameSuccess"
  | "result"
  | "download"
  | "history"
  | "recycleBin"
  | "profile"
  | "admin";

type CreatorMode = "guest" | "saved";
type LoginChoice = "guest" | "signin" | "signup" | null;
type CreatorProfile = {
  name: string;
  email: string;
  bio: string;
  avatarUri?: string;
};
type AuthSubmit = {
  profile: CreatorProfile;
  password: string;
};
type TrackStatus = "Ready" | "Temporary" | "Saved" | "Downloaded" | "Shared" | "Processing" | "Retry";
type GeneratedTrackView = {
  id: string;
  title: string;
  meta: string;
  status: TrackStatus;
};
type VoiceTake = {
  id: string;
  title: string;
  duration: number;
  createdAt: string;
  uploadId?: string;
  fileUri?: string;
  contentType?: string;
  sizeBytes?: number;
  rawAudioPath?: string;
  uploadUrl?: string;
  uploaded?: boolean;
  uploadState?: "uploading" | "failed";
  uploadError?: string;
  deletedAt?: string | null;
};
type RecordedTakeDraft = {
  duration: number;
  fileUri?: string;
  contentType?: string;
  sizeBytes?: number;
};
type TrackAction = {
  label: string;
  icon: IconName;
  onPress: () => void | Promise<void>;
  destructive?: boolean;
};
type WaveformMode = "vocal" | "blend" | "genre";
type FileNameMode = "keep" | "rename" | "tag";
type ArrangementMode = "vocal_to_song" | "music_to_music" | "full_song";
type InputSource = {
  kind: "recording" | "localUpload" | "sampleUpload";
  label: string;
  detail: string;
  arrangementMode?: ArrangementMode;
  preserveOriginalVocal?: boolean;
  referenceStrength?: number;
  uploadId?: string;
  fileUri?: string;
  rawAudioPath?: string;
  uploadUrl?: string;
  contentType?: string;
  sizeBytes?: number;
  uploaded?: boolean;
};
type MixPreset = "balanced" | "vocal_forward" | "soft_backing" | "beat_forward";
type GenerationIntent = {
  language: string;
  genreOverride: string;
  bpmOverride: string;
  keyOverride: string;
  trainingOptIn: boolean;
  trainingSingingSpeech: "singing" | "speaking" | "rap" | "humming";
  trainingVocalTechniques: string[];
  trainingTempoFamily: "free" | "slow" | "medium" | "fast";
  trainingMelodicCharacter: "indian" | "western" | "mixed";
  lyrics: string;
  productionStyle: string;
  arrangementStyle: string;
  moodTags: string;
  instruments: string;
  durationSeconds: number | null;
  mixPreset: MixPreset;
};
type BackendMode = "api" | "offline";
type BackendJobStatus = "created" | "uploaded" | "queued" | "analyzing" | "generating" | "mixing" | "ready" | "failed" | "deleted";
type BackendSongAnalysis = {
  bpm?: number | null;
  key?: string | null;
  duration_seconds: number;
  energy: string;
  mood: string;
  vocal_energy: number;
  suggested_genre: string;
  pitch_summary: string;
};
type BackendSongSection = {
  name: string;
  bars: number;
  note: string;
};
type BackendSongBlueprint = {
  structure: BackendSongSection[];
  chords: string[];
  production_notes: string[];
  lyric_suggestions: string[];
};
type BackendJob = {
  job_id: string;
  genre: string;
  track_name: string;
  source_type: InputSource["kind"];
  arrangement_mode?: ArrangementMode;
  status: BackendJobStatus;
  stage: string;
  library_status?: TrackStatus | null;
  final_mp3_path?: string | null;
  isolated_vocal_path?: string | null;
  backing_audio_path?: string | null;
  export_paths?: Record<string, string>;
  analysis?: BackendSongAnalysis | null;
  blueprint?: BackendSongBlueprint | null;
  worker_notes?: string | null;
  raw_audio_path?: string | null;
  error?: string | null;
  deleted_at?: string | null;
};
type DemoExportUrls = {
  mp3?: string | null;
  wav?: string | null;
  midi?: string | null;
  melodyMidi?: string | null;
  chordSheet?: string | null;
  producerPack?: string | null;
  vocalStem?: string | null;
  backingStem?: string | null;
  drumsStem?: string | null;
  bassStem?: string | null;
  guitarStem?: string | null;
  keysStem?: string | null;
  referenceStem?: string | null;
};
type BackendJobResponse = {
  job: BackendJob;
  final_mp3_url?: string | null;
  final_mp3_download_url?: string | null;
  final_wav_url?: string | null;
  midi_url?: string | null;
  melody_midi_url?: string | null;
  chord_sheet_url?: string | null;
  producer_pack_url?: string | null;
  isolated_vocal_url?: string | null;
  backing_audio_url?: string | null;
  drums_stem_url?: string | null;
  bass_stem_url?: string | null;
  guitar_stem_url?: string | null;
  keys_stem_url?: string | null;
  reference_stem_url?: string | null;
};
type SkarlyDetected = {
  language: string;
  language_confidence?: number | null;
  classification_source?: string | null;
  mood: string;
  vocal_type: string;
  bpm?: number | null;
  key?: string | null;
  timing_summary?: string | null;
  phrase_count?: number | null;
  song_structure?: Array<Record<string, unknown>>;
  genre_hint?: string | null;
  genre_confidence?: number | null;
  genre_source?: string | null;
  genre_probabilities?: Record<string, number>;
  audio_intelligence?: SkarlyAudioIntelligence | null;
  analysis_scope_seconds?: number | null;
  lyrics_preview?: string | null;
  source_profile?: string | null;
  energy?: string | null;
  input_quality?: string | null;
  input_quality_note?: string | null;
  melody_midi_status: string;
  song_intelligence_map?: SkarlySongIntelligenceMap | null;
};
type SkarlyAudioIntelligence = {
  architecture?: string | null;
  device?: string | null;
  analysis_scope: string;
  windows_analysed: number;
  singing_speech?: string | null;
  singing_speech_confidence?: number | null;
  vocal_technique_probabilities: Record<string, number>;
  mood_probabilities: Record<string, number>;
  tempo_family?: string | null;
  melodic_character?: string | null;
  in_distribution_probability?: number | null;
  requires_confirmation: boolean;
  trained_heads: Record<string, boolean>;
};
type SkarlySongIntelligenceMap = {
  duration_seconds: number;
  language: { primary: string; secondary?: string | null; confidence: number };
  tempo: { bpm?: number | null; confidence: number; rubato: boolean; source?: string };
  tonality: { key: string; scale: string; confidence: number; source?: string };
  vocal_range: { lowest_note?: string | null; highest_note?: string | null };
  mood: string[];
  genre_probabilities: Record<string, number>;
  genre_requires_confirmation: boolean;
  phrases: Array<Record<string, unknown>>;
  sections: Array<Record<string, unknown>>;
  energy_curve: Array<Record<string, unknown>>;
  melody_curve: Array<Record<string, unknown>>;
  stable_notes?: Array<Record<string, unknown>>;
  note_transitions?: Array<Record<string, unknown>>;
  pitch_slides?: Array<Record<string, unknown>>;
  ornamentation?: Array<Record<string, unknown>>;
  melodic_motifs?: Array<Record<string, unknown>>;
  lyrical_motifs?: Array<Record<string, unknown>>;
  chord_compatibility?: Array<Record<string, unknown>>;
  rhythm_analysis?: Record<string, unknown>;
  structure_analysis?: Record<string, unknown>;
  confirmed_corrections?: Record<string, unknown>;
  audio_intelligence?: SkarlyAudioIntelligence | null;
};
type SkarlyVersion = {
  name: string;
  input_vocal_url?: string | null;
  backing_url: string;
  final_mix_url: string;
  waveforms?: SkarlyWaveforms | null;
  prompt?: string | null;
  generator?: string | null;
  generation_engine?: string | null;
  style_family?: string | null;
  instruments?: string[];
  energy?: string | null;
  rhythm_character?: string | null;
  producer_mix_mode?: string | null;
  blueprint?: Record<string, string>;
  seed?: number | null;
  mix_note?: string | null;
  fallback_used?: boolean;
  transformation_quality?: {
    original_enough: boolean;
    duration_match: boolean;
    vocal_check_status: string;
    vocal_leakage_detected?: boolean | null;
    passed: boolean;
    warnings: string[];
  } | null;
  musical_compatibility?: {
    target_bpm: number;
    output_bpm?: number | null;
    tempo_match: boolean;
    target_key: string;
    output_key?: string | null;
    key_match: boolean;
    key_match_method?: string;
    key_correction_applied?: boolean;
    key_correction_semitones?: number | null;
    pre_correction_output_key?: string | null;
    post_correction_detected_key?: string | null;
    passed: boolean;
    warnings: string[];
  } | null;
};
type SkarlyWaveforms = {
  input_vocal: number[];
  backing: number[];
  final_mix: number[];
};
type SkarlyAnalyzeResponse = {
  job_id: string;
  upload_id: string;
  status: string;
  detected: SkarlyDetected;
  normalized_wav_url?: string | null;
  vocal_url?: string | null;
  melody_midi_url?: string | null;
  analysis_url?: string | null;
  song_intelligence_map?: SkarlySongIntelligenceMap | null;
  warnings: string[];
};
type SkarlyGenerationTelemetry = {
  cuda_available: boolean;
  device?: string | null;
  device_capability?: string | null;
  torch_version?: string | null;
  torch_cuda_runtime?: string | null;
  generation_backend: string;
  model: string;
  peak_vram_mb: number;
  generation_seconds: number;
  cpu_fallback: boolean;
};
type SkarlyArrangementDiversityReport = {
  method: string;
  calibration: string;
  calibration_approved?: boolean;
  calibration_sample_count?: number;
  calibration_rater_count?: number;
  calibration_manifest_sha256?: string | null;
  calibration_note?: string | null;
  passed: boolean;
  evaluated_pairs: number;
  rejected_pairs: number;
  thresholds: Record<string, number>;
  pairs: Array<{
    left_index: number;
    right_index: number;
    embedding_similarity: number;
    drum_onset_similarity: number;
    chord_change_similarity: number;
    instrumentation_similarity: number;
    perceptual_similarity: number;
    rejected: boolean;
    reason?: string | null;
  }>;
};
type SkarlyGenerateResponse = {
  job_id: string;
  detected: SkarlyDetected;
  versions: SkarlyVersion[];
  status: string;
  mix_preset: string;
  generator_backend: string;
  vocal_url?: string | null;
  melody_midi_url?: string | null;
  analysis_url?: string | null;
  generation_telemetry?: SkarlyGenerationTelemetry | null;
  arrangement_diversity?: SkarlyArrangementDiversityReport | null;
  song_intelligence_map?: SkarlySongIntelligenceMap | null;
  source_preparation?: {
    requested_mode: string;
    detected_mode: string;
    separation_status: string;
    vocal_detected: boolean;
    vocal_preserved: boolean;
    instrumental_audio_url?: string | null;
    vocal_audio_url?: string | null;
    vocal_energy_db_below_mix?: number | null;
    warnings: string[];
  } | null;
  warnings: string[];
};
type SkarlyProducerProfile = {
  profile_id: string;
  name: string;
  instruments: string[];
  energy: string;
  rhythm_character: string;
  mix_mode: string;
  blueprint: Record<string, string>;
  is_default: boolean;
};
type SkarlyV2Job = {
  job_id: string;
  job_type: "analysis" | "generation" | "section" | "mix" | "feedback";
  status: "queued" | "running" | "ready" | "failed";
  stage: string;
  progress: number;
  upload_id?: string | null;
  analysis_id?: string | null;
  current_arrangement?: number | null;
  completed_arrangements: number;
  total_arrangements: number;
  completed_duration_seconds: number;
  cuda_device?: string | null;
  model?: string | null;
  warnings: string[];
  completed_outputs: Array<Record<string, unknown>>;
  result?: Record<string, any> | null;
  error?: { stage?: string; type?: string; message?: string; retryable?: boolean } | null;
};
type SkarlyV2ExportResponse = {
  status: string;
  export_id: string;
  generation_id: string;
  version_index: number;
  arrangement_name: string;
  duration_seconds: number;
  files: Record<string, string>;
  sha256: Record<string, string>;
  durations_seconds: Record<string, number>;
  warnings: string[];
};
type BackendHistoryResponse = {
  tracks: BackendJob[];
};
type BackendProfile = {
  name: string;
  email: string;
  bio: string;
  photo_url?: string | null;
};
type BackendProfileResponse = {
  profile: BackendProfile;
};
type BackendVoiceTake = {
  take_id: string;
  title: string;
  duration: number;
  raw_audio_path: string;
  content_type: string;
  size_bytes?: number | null;
  created_at: string;
  status?: "active" | "deleted";
  deleted_at?: string | null;
};
type BackendVoiceTakeResponse = {
  take: BackendVoiceTake;
};
type BackendVoiceTakeListResponse = {
  takes: BackendVoiceTake[];
};
type BackendVoiceTakePlaybackResponse = {
  take_id: string;
  raw_audio_url: string;
};
type BackendLibraryRecoveryResponse = {
  recovered_voice_takes: number;
  recovered_tracks: number;
  takes: BackendVoiceTake[];
  tracks: BackendJob[];
};
type BackendRecycleBinResponse = {
  voice_takes: BackendVoiceTake[];
  tracks: BackendJob[];
};
type BackendAdminUser = {
  user_id: string;
  name: string;
  email: string;
  updated_at: string;
};
type BackendAdminSummaryResponse = {
  environment: string;
  repository_backend: string;
  storage_backend: string;
  worker_backend: string;
  music_generator_backend: string;
  task_backend: string;
  bucket: string;
  users: BackendAdminUser[];
  recent_jobs: BackendJob[];
  recent_voice_takes: BackendVoiceTake[];
  deleted_jobs: BackendJob[];
  deleted_voice_takes: BackendVoiceTake[];
  counts: Record<string, number>;
  cloud_cost?: {
    period: string;
    generations: number;
    generation_limit: number;
    estimated_cost_usd: number;
    unit_cost_usd: number;
    generator_backend: string;
  };
  cloud_runtime?: {
    runtime: string;
    service: string;
    revision: string;
    region: string;
    project_id?: string | null;
    service_url?: string | null;
    worker_url?: string | null;
    task_queue: string;
    storage_bucket: string;
    cors_origins: string[];
  };
};
type SignedUploadResponse = {
  upload_id: string;
  upload_url: string;
  raw_audio_path: string;
  expires_in_seconds: number;
};
type UploadVerificationResponse = {
  raw_audio_path: string;
  exists: boolean;
};
type FirebaseSetupStatus = "loading" | "ready" | "unconfigured" | "unavailable";
type IconName =
  | "back"
  | "creator"
  | "dance"
  | "edit"
  | "experiment"
  | "guest"
  | "home"
  | "saved"
  | "continue"
  | "logout"
  | "mic"
  | "upload"
  | "generate"
  | "speak"
  | "vibe"
  | "waveform"
  | "play"
  | "download"
  | "share"
  | "regenerate"
  | "settings"
  | "success"
  | "processing"
  | "retry"
  | "error"
  | "trash"
  | "recycle"
  | "more";

type Genre = {
  id: string;
  label: string;
  color: string;
  soft: string;
};

const genres: Genre[] = [
  { id: "lofi", label: "Lo-fi", color: "#c6aa6a", soft: "rgba(198,170,106,0.16)" },
  { id: "piano", label: "Piano", color: "#d8d0bd", soft: "rgba(216,208,189,0.13)" },
  { id: "pop", label: "Pop", color: "#b98f58", soft: "rgba(185,143,88,0.14)" },
  { id: "rock", label: "Rock", color: "#a66a44", soft: "rgba(166,106,68,0.14)" },
  { id: "rnb", label: "R&B", color: "#e1c47a", soft: "rgba(225,196,122,0.14)" },
  { id: "hiphop", label: "Hip-hop", color: "#9a855d", soft: "rgba(154,133,93,0.16)" },
  { id: "acoustic", label: "Acoustic", color: "#b7a988", soft: "rgba(183,169,136,0.13)" },
  { id: "bollywood", label: "Bollywood", color: "#daaa65", soft: "rgba(218,170,101,0.16)" },
  { id: "indie-pop", label: "Indie Pop", color: "#99b0a4", soft: "rgba(153,176,164,0.16)" },
  { id: "punjabi-pop", label: "Punjabi Pop", color: "#d67b4a", soft: "rgba(214,123,74,0.16)" },
  { id: "sufi-bhajan", label: "Sufi / Bhajan", color: "#b092c7", soft: "rgba(176,146,199,0.16)" },
  { id: "cinematic", label: "Cinematic", color: "#efeadb", soft: "rgba(239,234,219,0.1)" }
];

const languageOptions = ["Hindi", "Hinglish", "English", "Tamil", "Telugu", "Punjabi", "Urdu", "Bengali"];
const moodOptions = ["Sad / Emotional", "Romantic", "Devotional", "Heartbreak", "Hopeful", "Calm", "Energetic"];
const trainingDeliveryOptions: GenerationIntent["trainingSingingSpeech"][] = ["singing", "speaking", "rap", "humming"];
const trainingTechniqueOptions = ["straight", "vibrato", "breathy", "belting", "melismatic", "ornamented", "spoken", "rap"];
const trainingTempoOptions: GenerationIntent["trainingTempoFamily"][] = ["free", "slow", "medium", "fast"];
const trainingMelodicOptions: GenerationIntent["trainingMelodicCharacter"][] = ["indian", "western", "mixed"];
const productionStyleOptions = [
  "Auto",
  "Bollywood Ballad",
  "Romantic Pop",
  "Sufi Rock",
  "Punjabi Pop",
  "Bhajan / Devotional",
  "Lo-fi Cover",
  "Trap Soul"
];
const durationOptions: Array<{ label: string; value: number | null }> = [
  { label: "Auto", value: null },
  { label: "30s", value: 30 },
  { label: "60s", value: 60 },
  { label: "90s", value: 90 },
  { label: "150s", value: 150 },
  { label: "5 min", value: 300 }
];
const mixPresetOptions: Array<{ label: string; value: MixPreset; vocalGainDb: number; backingGainDb: number; duckingStrength: string }> = [
  { label: "Balanced", value: "balanced", vocalGainDb: 1.5, backingGainDb: -3, duckingStrength: "medium" },
  { label: "Vocal Up", value: "vocal_forward", vocalGainDb: 3, backingGainDb: -4.5, duckingStrength: "strong" },
  { label: "Beat Forward", value: "beat_forward", vocalGainDb: 0, backingGainDb: -1, duckingStrength: "light" },
  { label: "Soft Bed", value: "soft_backing", vocalGainDb: 2, backingGainDb: -6, duckingStrength: "light" }
];
const defaultProducerProfileIds = [
  "bollywood_acoustic",
  "modern_bollywood",
  "sufi_live",
  "punjabi_rhythm",
  "cinematic_urban"
];
const defaultGenerationIntent: GenerationIntent = {
  language: "Hindi",
  genreOverride: "",
  bpmOverride: "",
  keyOverride: "",
  trainingOptIn: false,
  trainingSingingSpeech: "singing",
  trainingVocalTechniques: [],
  trainingTempoFamily: "medium",
  trainingMelodicCharacter: "indian",
  lyrics: "",
  productionStyle: "Auto",
  arrangementStyle: "",
  moodTags: "",
  instruments: "",
  durationSeconds: null,
  mixPreset: "balanced"
};

function swapHindiEnglishDetection(language: string): string {
  const normalizedLanguage = language.trim().toLowerCase();
  if (normalizedLanguage === "hindi") return "English";
  if (normalizedLanguage === "english") return "Hindi";
  return language;
}

const processingSteps = ["Saving Idea", "Idea Analysis", "Isolating Vocals", "Building Demo", "Packing Exports", "Ready"];
const USE_BACKEND_API = true;
const BACKEND_BASE_URL = (process.env.EXPO_PUBLIC_BACKEND_BASE_URL || "http://localhost:8090").replace(/\/$/, "");
const BACKEND_CONNECTED_MESSAGE = "Backend: FastAPI connected. Firebase Auth, Firestore, and Cloud Storage are active.";
const BACKEND_OFFLINE_MESSAGE = "Backend is offline. Start FastAPI to use cloud history, storage, and generation.";
const BACKEND_PLACEHOLDER_TRACK = "Pending backend draft";
const ADMIN_FIREBASE_UIDS = new Set(["64EbLsRLTmflRHae5oJgrqQFs8f1"]);
const ADMIN_EMAILS = new Set(["yeshwant_satyada@srmap.edu.in"]);
const firebaseConfig = {
  apiKey: process.env.EXPO_PUBLIC_FIREBASE_API_KEY,
  authDomain: process.env.EXPO_PUBLIC_FIREBASE_AUTH_DOMAIN,
  projectId: process.env.EXPO_PUBLIC_FIREBASE_PROJECT_ID,
  appId: process.env.EXPO_PUBLIC_FIREBASE_APP_ID
};
const hasFirebaseConfig = Boolean(
  firebaseConfig.apiKey &&
  firebaseConfig.authDomain &&
  firebaseConfig.projectId &&
  firebaseConfig.appId
);
const firebaseApp = hasFirebaseConfig ? (getApps()[0] ?? initializeApp(firebaseConfig)) : null;
const firebaseAuth = firebaseApp ? getAuth(firebaseApp) : null;

function isAdminFirebaseUser(user: User | null) {
  const email = user?.email?.trim().toLowerCase() ?? "";
  return Boolean(user && (ADMIN_FIREBASE_UIDS.has(user.uid) || ADMIN_EMAILS.has(email)));
}

function buildTrackTitle(trackName: string, genre: Genre, mode: FileNameMode) {
  const cleanName = trackName.trim() || "Untitled Track";
  return mode === "tag" ? `${cleanName} - ${genre.label}` : cleanName;
}

function buildFileName(trackName: string, genre: Genre, mode: FileNameMode) {
  return `${buildTrackTitle(trackName, genre, mode)}.mp3`;
}

function buildDownloadName(trackName: string, genre: Genre, mode: FileNameMode, extension: string) {
  return `${buildTrackTitle(trackName, genre, mode)}.${extension.replace(/^\./, "")}`;
}

function demoExportUrlsFromResponse(response: BackendJobResponse): DemoExportUrls {
  return {
    mp3: response.final_mp3_download_url ?? response.final_mp3_url ?? null,
    wav: response.final_wav_url ?? null,
    midi: response.midi_url ?? null,
    melodyMidi: response.melody_midi_url ?? null,
    chordSheet: response.chord_sheet_url ?? null,
    producerPack: response.producer_pack_url ?? null,
    vocalStem: response.isolated_vocal_url ?? null,
    backingStem: response.backing_audio_url ?? null,
    drumsStem: response.drums_stem_url ?? null,
    bassStem: response.bass_stem_url ?? null,
    guitarStem: response.guitar_stem_url ?? null,
    keysStem: response.keys_stem_url ?? null,
    referenceStem: response.reference_stem_url ?? null
  };
}

function getGeneratedTrackStatus(creatorMode: CreatorMode, hasSaved: boolean, hasDownloaded: boolean, hasShared = false): TrackStatus {
  if (hasDownloaded) return "Downloaded";
  if (hasShared) return "Shared";
  if (creatorMode === "saved" && hasSaved) return "Saved";
  return "Temporary";
}

function getSourceLabel(source: InputSource) {
  if (source.arrangementMode === "music_to_music") return source.preserveOriginalVocal ? "New music with original singer" : "Instrumental only";
  if (source.arrangementMode === "full_song") return "Full song";
  if (source.kind === "recording") return "Recording";
  if (source.kind === "localUpload") return "Local upload";
  return "Sample upload";
}

function getArrangementModeLabel(mode?: ArrangementMode) {
  if (mode === "music_to_music") return "Music to New Music";
  if (mode === "full_song") return "Full Song";
  return "Vocal";
}

function uploadDetailForMode(extension: string, mode: ArrangementMode) {
  const fileType = extension ? extension.toUpperCase() : "Audio";
  return `${fileType} | ${getArrangementModeLabel(mode)}`;
}

function commaList(value: string) {
  return value.split(",").map((item) => item.trim()).filter(Boolean).slice(0, 12);
}

function generationIntentPayload(intent: GenerationIntent) {
  const mix = mixPresetOptions.find((option) => option.value === intent.mixPreset) ?? mixPresetOptions[0];
  const lyrics = intent.lyrics.trim();
  const arrangementStyle = intent.arrangementStyle.trim();
  return {
    language: intent.language.trim() || "Hindi",
    lyrics: lyrics || undefined,
    production_style: intent.productionStyle === "Auto" ? undefined : intent.productionStyle,
    arrangement_style: arrangementStyle || undefined,
    main_instruments: commaList(intent.instruments),
    mood_tags: commaList(intent.moodTags),
    output_duration_seconds: intent.durationSeconds ?? undefined,
    vocal_gain_db: mix.vocalGainDb,
    backing_gain_db: mix.backingGainDb,
    ducking_strength: mix.duckingStrength
  };
}

function skarlyMixPresetValue(mixPreset: MixPreset) {
  if (mixPreset === "vocal_forward") return "vocal_up";
  if (mixPreset === "soft_backing") return "soft_bed";
  if (mixPreset === "beat_forward") return "beat_up";
  return "balanced";
}

function skarlyTrainingMoodLabels(value: string) {
  const normalized = value.toLowerCase();
  const labels = new Set<string>();
  if (normalized.includes("romantic")) labels.add("romantic");
  if (normalized.includes("emotional")) labels.add("emotional");
  if (normalized.includes("intimate")) labels.add("intimate");
  if (normalized.includes("devotional") || normalized.includes("spiritual")) labels.add("devotional");
  if (normalized.includes("uplifting") || normalized.includes("happy")) labels.add("uplifting");
  if (normalized.includes("energetic") || normalized.includes("dance")) labels.add("energetic");
  if (normalized.includes("dark")) labels.add("dark");
  if (normalized.includes("sad") || normalized.includes("melanchol")) labels.add("melancholic");
  return Array.from(labels);
}

function formatSkarlyV2Stage(job: SkarlyV2Job) {
  const labels: Record<string, string> = {
    queued: "Queued for the local studio",
    validating_input: "Validating the complete vocal",
    verifying_cuda: "Verifying RTX CUDA execution",
    analysing_complete_vocal: "Analysing the complete vocal",
    building_song_map: "Building the Song Intelligence Map",
    preparing_vocal: "Preparing the original vocal for mixing",
    planning_arrangements: "Planning five producer directions",
    creating_arrangement: "Creating arrangements",
    mixing_vocals: "Mixing vocals clearly in front",
    checking_arrangement_diversity: "Checking arrangement diversity",
    mastering: "Mastering the selected balance",
    preparing_exports: "Preparing playable exports",
    awaiting_confirmation: "Analysis ready for your confirmation",
    ready: "Five finished versions are ready"
  };
  const arrangement = job.current_arrangement ? ` ${job.current_arrangement} of ${job.total_arrangements || 5}` : "";
  return `${labels[job.stage] ?? job.stage.replace(/_/g, " ")}${job.stage === "creating_arrangement" || job.stage === "mixing_vocals" ? arrangement : ""}`;
}

function skarlyUploadPayload(source: InputSource) {
  return {
    upload_id: source.uploadId,
    raw_audio_path: source.rawAudioPath
  };
}

function backendMediaUrl(url?: string | null) {
  if (!url) return null;
  if (/^https?:\/\//i.test(url)) return url;
  return `${BACKEND_BASE_URL}${url.startsWith("/") ? "" : "/"}${url}`;
}

function skarlyAnalysisToBackendAnalysis(detected: SkarlyDetected): BackendSongAnalysis {
  return {
    bpm: detected.bpm ?? null,
    key: detected.key ?? null,
    duration_seconds: 0,
    energy: detected.energy ?? "Auto",
    mood: detected.mood,
    vocal_energy: 0,
    suggested_genre: "Skarly",
    pitch_summary: detected.lyrics_preview
      ? `Lyrics preview: ${detected.lyrics_preview}`
      : `Vocal type: ${detected.vocal_type}. Melody MIDI: ${detected.melody_midi_status}.`
  };
}

function skarlyTempoText(detected: SkarlyDetected) {
  return detected.bpm ? `Around ${Math.round(detected.bpm)} BPM` : "Tempo estimate";
}

function skarlyTimingText(detected: SkarlyDetected) {
  return detected.timing_summary || (detected.phrase_count ? `${detected.phrase_count} vocal phrases detected` : "Phrase timing estimate");
}

function extensionFromAudioUrl(url: string | null | undefined) {
  const pathname = (url || "").split("?")[0].toLowerCase();
  return pathname.endsWith(".wav") ? "wav" : "mp3";
}

function cleanFileStem(value: string) {
  return value.replace(/[\\/:*?"<>|]+/g, "-").replace(/\s+/g, " ").trim() || "Skarly Mix";
}

function summarizeGenerationIntent(intent: GenerationIntent) {
  const style = intent.productionStyle === "Auto" ? "auto style" : intent.productionStyle;
  const duration = intent.durationSeconds ? `${intent.durationSeconds}s` : "auto length";
  return `${intent.language} | ${style} | ${duration}`;
}

function firebaseAuthErrorMessage(error: unknown, kind?: "signin" | "signup") {
  if (error instanceof FirebaseError) {
    if (error.code === "auth/email-already-in-use") return "Email already registered. Sign in instead.";
    if (error.code === "auth/invalid-credential" || error.code === "auth/wrong-password" || error.code === "auth/user-not-found") return "Email or password is incorrect.";
    if (error.code === "auth/weak-password") return "Password should be at least 6 characters.";
    if (error.code === "auth/invalid-email") return "Enter a valid email address.";
  }
  return kind === "signup" ? "Could not create Firebase account." : "Could not sign in.";
}

async function getAuthHeader(creatorMode: CreatorMode, firebaseUser: User | null) {
  if (creatorMode === "guest") return "Bearer guest:guest-session";
  if (!hasFirebaseConfig || !firebaseAuth) throw new Error("Firebase Auth is not configured.");
  if (!firebaseUser) throw new Error("Sign in again to continue.");
  return `Bearer ${await firebaseUser.getIdToken()}`;
}

function mapBackendStageToIndex(stage?: string) {
  if (stage === "analyzing") return 1;
  if (stage === "isolating vocals") return 2;
  if (stage === "generating") return 3;
  if (stage === "mixing") return 4;
  if (stage === "ready") return 5;
  return 0;
}

function backendTrackStatus(status: BackendJobStatus, libraryStatus?: TrackStatus | null): TrackStatus {
  if (libraryStatus) return libraryStatus;
  if (status === "ready") return "Ready";
  if (status === "failed") return "Retry";
  return "Processing";
}

function isStaleBackendJob(job: BackendJob) {
  const title = (job.track_name ?? "").trim().toLowerCase();
  const finalPath = (job.final_mp3_path ?? "").trim().toLowerCase();
  if (!title || ["pending backend draft", "backend mock draft", "final", "final.mp3"].includes(title)) return true;
  if (job.status === "failed" && title === "pending backend draft") return true;
  return finalPath.endsWith("/final.mp3") && ["final", "final.mp3", "recovered mix"].includes(title);
}

function visibleBackendJobs(jobs: BackendJob[]) {
  return jobs.filter((job) => !isStaleBackendJob(job));
}

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : "Unknown error";
}

function isMissingVerifyRouteError(error: unknown) {
  return errorMessage(error).includes("404: /v1/uploads/verify");
}

function inferAudioContentType(filename: string, offline?: string | null) {
  if (offline && offline !== "application/octet-stream") return offline;
  const extension = filename.includes(".") ? filename.split(".").pop()?.toLowerCase() : "";
  if (extension === "wav") return "audio/wav";
  if (extension === "m4a") return "audio/m4a";
  if (extension === "aac") return "audio/aac";
  if (extension === "flac") return "audio/flac";
  return "audio/mpeg";
}

function getAudioExtension(filename: string) {
  return filename.includes(".") ? (filename.split(".").pop() ?? "").toLowerCase() : "";
}

function isSupportedAudioFile(filename: string, mimeType?: string | null) {
  const extension = getAudioExtension(filename);
  const extensionOk = ["mp3", "wav", "m4a", "aac", "flac"].includes(extension);
  const mimeOk = !mimeType || mimeType === "application/octet-stream" || mimeType.startsWith("audio/");
  return extensionOk && mimeOk;
}

function getStoredGenre() {
  try {
    const storedId = (globalThis as any).localStorage?.getItem("skarly.defaultGenre");
    return genres.find((genre) => genre.id === storedId) ?? genres[0];
  } catch {
    return genres[0];
  }
}

function getStoredGenreForAccount(accountKey: string) {
  try {
    const storedId = (globalThis as any).localStorage?.getItem(`skarly.${accountKey}.defaultGenre`);
    return genres.find((genre) => genre.id === storedId);
  } catch {
    return undefined;
  }
}

function storeDefaultGenre(genre: Genre, accountKey = "guest") {
  try {
    (globalThis as any).localStorage?.setItem("skarly.defaultGenre", genre.id);
    (globalThis as any).localStorage?.setItem(`skarly.${accountKey}.defaultGenre`, genre.id);
  } catch {
    // Native builds can persist this through the cloud profile path instead.
  }
}

function localAccountKey(creatorMode: CreatorMode, firebaseUser: User | null) {
  return creatorMode === "saved" && firebaseUser?.uid ? `saved.${firebaseUser.uid}` : "guest";
}

function serializeLocalVoiceTake(take: VoiceTake) {
  const { uploadUrl: _uploadUrl, fileUri: _fileUri, ...safeTake } = take;
  return safeTake;
}

function loadLocalVoiceTakes(accountKey: string): VoiceTake[] {
  try {
    const raw = (globalThis as any).localStorage?.getItem(`skarly.${accountKey}.voiceTakes`);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function storeLocalVoiceTakes(accountKey: string, takes: VoiceTake[]) {
  try {
    const storable = takes.slice(0, 30).map(serializeLocalVoiceTake);
    (globalThis as any).localStorage?.setItem(`skarly.${accountKey}.voiceTakes`, JSON.stringify(storable));
  } catch {
    // Best effort browser cache for interrupted uploads.
  }
}

function confirmPermanentDelete(label: string) {
  const confirmRef = (globalThis as any).confirm;
  return typeof confirmRef === "function" ? confirmRef(`Delete ${label} forever? This cannot be undone.`) : true;
}

function mergeLocalVoiceTakes(stored: VoiceTake[], current: VoiceTake[]) {
  const keys = new Set(stored.flatMap((take) => [take.id, take.rawAudioPath ?? ""]).filter(Boolean));
  const currentOnly = current.filter((take) => !keys.has(take.id) && !(take.rawAudioPath && keys.has(take.rawAudioPath)));
  return [...currentOnly, ...stored];
}

async function downloadUrlToLocalFile(url: string, fileName: string) {
  const documentRef = (globalThis as any).document;
  if (Platform.OS === "web" && documentRef?.createElement) {
    const link = documentRef.createElement("a");
    link.href = url;
    link.download = fileName;
    link.rel = "noopener noreferrer";
    link.target = "_blank";
    documentRef.body.appendChild(link);
    link.click();
    link.remove();
    return true;
  }
  const windowRef = (globalThis as any).window;
  if (windowRef?.open) {
    windowRef.open(url, "_blank", "noopener,noreferrer");
    return true;
  }
  return false;
}

function estimatedDurationMs(source: InputSource) {
  const match = source.detail.match(/(\d+)\s*s/i);
  const seconds = match ? Number(match[1]) : 30;
  return Math.max(1000, seconds * 1000);
}

function formatPlayerTime(milliseconds: number) {
  const totalSeconds = Math.max(0, Math.floor(milliseconds / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}

function profileBioWithDefaultGenre(bio: string, genre: Genre) {
  const cleanBio = bio.replace(/\s*\[defaultGenre:[^\]]+\]\s*/g, "").trim() || "Private Skarly workspace";
  return `${cleanBio} [defaultGenre:${genre.id}]`;
}

function cleanProfileBio(bio?: string | null) {
  return (bio ?? "").replace(/\s*\[defaultGenre:[^\]]+\]\s*/g, "").trim() || "Private Skarly workspace";
}

function genreFromProfileBio(bio?: string | null) {
  const match = bio?.match(/\[defaultGenre:([^\]]+)\]/);
  return genres.find((genre) => genre.id === match?.[1]);
}

function genreFromLabel(label: string) {
  return genres.find((genre) => genre.label.toLowerCase() === label.toLowerCase());
}

async function readAudioFileBlob(fileUri: string) {
  const fileResponse = await fetch(fileUri);
  if (!fileResponse.ok) {
    throw new Error("Could not read selected audio file.");
  }
  return fileResponse.blob();
}

async function uploadFileToSignedUrl(fileUri: string, uploadUrl: string, contentType: string) {
  const fileBlob = await readAudioFileBlob(fileUri);
  const uploadResponse = await fetch(uploadUrl, {
    method: "PUT",
    headers: {
      "Content-Type": contentType
    },
    body: fileBlob
  });
  if (!uploadResponse.ok) {
    throw new Error(`Cloud upload failed: ${uploadResponse.status}`);
  }
}

async function uploadFileThroughBackend(fileUri: string, rawAudioPath: string, contentType: string, creatorMode: CreatorMode, firebaseUser: User | null) {
  const fileBlob = await readAudioFileBlob(fileUri);
  const query = `raw_audio_path=${encodeURIComponent(rawAudioPath)}&content_type=${encodeURIComponent(contentType)}`;
  return backendUploadBytes<UploadVerificationResponse>(`/v1/uploads/bytes?${query}`, creatorMode, firebaseUser, fileBlob, contentType);
}

async function uploadFileToCloud(fileUri: string, signed: SignedUploadResponse, contentType: string, creatorMode: CreatorMode, firebaseUser: User | null) {
  try {
    await uploadFileToSignedUrl(fileUri, signed.upload_url, contentType);
  } catch {
    await uploadFileThroughBackend(fileUri, signed.raw_audio_path, contentType, creatorMode, firebaseUser);
  }
}

async function prepareWebAudioSource(uri: string) {
  if (Platform.OS !== "web" || !/^https?:\/\//i.test(uri)) {
    return { uri, revokeAfterUse: false };
  }

  try {
    const response = await fetch(uri);
    if (!response.ok) throw new Error(`Audio fetch failed: ${response.status}`);
    const blob = await response.blob();
    return { uri: URL.createObjectURL(blob), revokeAfterUse: true };
  } catch {
    return { uri, revokeAfterUse: false };
  }
}

function revokeObjectUrl(uri: string | null | undefined) {
  if (Platform.OS === "web" && uri?.startsWith("blob:")) {
    try {
      URL.revokeObjectURL(uri);
    } catch {
      // Best effort cleanup only.
    }
  }
}

function safeStorageSegment(value: string) {
  const cleaned = value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return (cleaned || "creator").slice(0, 48);
}

function backendStorageOwnerPath(creatorMode: CreatorMode, firebaseUser: User | null) {
  if (creatorMode === "guest") return "guest/guest-session";
  const uid = firebaseUser?.uid ?? "signed-user";
  const readable = firebaseUser?.email?.split("@")[0] ?? uid;
  return `saved/${safeStorageSegment(readable)}--${safeStorageSegment(uid).slice(0, 8)}`;
}

function pendingRawAudioPath(creatorMode: CreatorMode, firebaseUser: User | null, source: InputSource) {
  return `users/${backendStorageOwnerPath(creatorMode, firebaseUser)}/raw/pending-${source.kind}/voice.mp3`;
}

function mapBackendVoiceTake(take: BackendVoiceTake): VoiceTake {
  return {
    id: take.take_id,
    title: take.title,
    duration: take.duration,
    createdAt: "Cloud saved",
    contentType: take.content_type,
    sizeBytes: take.size_bytes ?? undefined,
    rawAudioPath: take.raw_audio_path,
    uploaded: true,
    deletedAt: take.deleted_at ?? null
  };
}

function mergeVoiceTakesWithBackend(current: VoiceTake[], backendTakes: BackendVoiceTake[]) {
  const mappedBackend = backendTakes.map(mapBackendVoiceTake);
  const mergedBackend = mappedBackend.map((backendTake) => {
    const localMatch = current.find((take) =>
      take.id === backendTake.id ||
      (backendTake.rawAudioPath && take.rawAudioPath === backendTake.rawAudioPath) ||
      (!take.uploaded && take.title === backendTake.title && take.duration === backendTake.duration)
    );
    return localMatch ? { ...backendTake, fileUri: localMatch.fileUri, uploadUrl: localMatch.uploadUrl } : backendTake;
  });
  const backendKeys = new Set(mergedBackend.flatMap((take) => [take.id, take.rawAudioPath ?? ""]).filter(Boolean));
  const localOnly = current.filter((take) => !backendKeys.has(take.id) && !(take.rawAudioPath && backendKeys.has(take.rawAudioPath)));
  return [...mergedBackend, ...localOnly];
}

async function backendRequest<T>(path: string, creatorMode: CreatorMode, firebaseUser: User | null, options: RequestInit = {}) {
  const authorization = await getAuthHeader(creatorMode, firebaseUser);
  const response = await fetch(`${BACKEND_BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      Authorization: authorization,
      ...(options.headers ?? {})
    }
  });

  if (!response.ok) {
    let detail = "";
    try {
      const payload = await response.json() as { detail?: string };
      detail = typeof payload.detail === "string" ? payload.detail : "";
    } catch {
      detail = await response.text().catch(() => "");
    }
    throw new BackendHttpError(response.status, path, detail);
  }

  return response.json() as Promise<T>;
}

async function backendUploadBytes<T>(path: string, creatorMode: CreatorMode, firebaseUser: User | null, body: Blob, contentType: string) {
  const authorization = await getAuthHeader(creatorMode, firebaseUser);
  const response = await fetch(`${BACKEND_BASE_URL}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": contentType,
      Authorization: authorization
    },
    body
  });

  if (!response.ok) {
    throw new BackendHttpError(response.status, path);
  }

  return response.json() as Promise<T>;
}

class BackendHttpError extends Error {
  status: number;
  path: string;

  constructor(status: number, path: string, detail = "") {
    super(detail || `Backend ${status}: ${path}`);
    this.status = status;
    this.path = path;
  }
}

function backendStatus(error: unknown) {
  return error instanceof BackendHttpError ? error.status : undefined;
}

const backendApi = {
  getProfile: (creatorMode: CreatorMode, firebaseUser: User | null) => backendRequest<BackendProfileResponse>("/v1/me", creatorMode, firebaseUser),
  saveProfile: (creatorMode: CreatorMode, firebaseUser: User | null, profile: CreatorProfile) => backendRequest<BackendProfileResponse>("/v1/me", creatorMode, firebaseUser, {
    method: "PUT",
    body: JSON.stringify({
      name: profile.name,
      email: profile.email,
      bio: profile.bio,
      photo_url: profile.avatarUri ?? null
    })
  }),
  signUpload: (creatorMode: CreatorMode, firebaseUser: User | null, source: InputSource) => backendRequest<SignedUploadResponse>("/v1/uploads/sign", creatorMode, firebaseUser, {
    method: "POST",
    body: JSON.stringify({
      filename: source.label,
      content_type: source.contentType ?? (source.kind === "localUpload" ? "audio/mpeg" : "audio/mpeg"),
      size_bytes: source.sizeBytes ?? 2500000,
      source_type: source.kind
    })
  }),
  verifyUpload: (creatorMode: CreatorMode, firebaseUser: User | null, rawAudioPath: string) => backendRequest<UploadVerificationResponse>("/v1/uploads/verify", creatorMode, firebaseUser, {
    method: "POST",
    body: JSON.stringify({ raw_audio_path: rawAudioPath })
  }),
  getSkarlyProducerProfiles: (creatorMode: CreatorMode, firebaseUser: User | null) => backendRequest<SkarlyProducerProfile[]>("/api/v2/producer-profiles", creatorMode, firebaseUser),
  createSkarlyV2Analysis: (creatorMode: CreatorMode, firebaseUser: User | null, source: InputSource) => backendRequest<SkarlyV2Job>("/api/v2/analyse", creatorMode, firebaseUser, {
    method: "POST",
    body: JSON.stringify(skarlyUploadPayload(source))
  }),
  getSkarlyV2Job: (creatorMode: CreatorMode, firebaseUser: User | null, jobId: string) => backendRequest<SkarlyV2Job>(`/api/v2/jobs/${jobId}`, creatorMode, firebaseUser),
  createSkarlyV2Generation: (creatorMode: CreatorMode, firebaseUser: User | null, analysisId: string, durationSeconds: number, profiles: string[], intent: GenerationIntent, source: InputSource, detected?: SkarlyDetected | null) => backendRequest<SkarlyV2Job>("/api/v2/generations", creatorMode, firebaseUser, {
    method: "POST",
    body: JSON.stringify({
      analysis_id: analysisId,
      duration_seconds: durationSeconds,
      arrangement_profiles: profiles,
      mix_profile: skarlyMixPresetValue(intent.mixPreset),
      require_cuda: true,
      number_of_outputs: 5,
      language: intent.language || detected?.language,
      mood: intent.moodTags || detected?.mood,
      genre_override: intent.genreOverride.trim() || undefined,
      bpm_override: intent.bpmOverride.trim() ? Number(intent.bpmOverride) : undefined,
      key_override: intent.keyOverride.trim() || undefined,
      arrangement_mode: source.arrangementMode ?? "vocal_to_song",
      preserve_original_vocal: source.preserveOriginalVocal ?? source.arrangementMode === "full_song",
      reference_strength: source.referenceStrength ?? 0.35
    })
  }),
  regenerateSkarlyV2: (creatorMode: CreatorMode, firebaseUser: User | null, generationId: string, versionIndex: number, energyDelta = 0, instrumentChange?: string) => backendRequest<SkarlyV2Job>("/api/v2/generations/regenerate", creatorMode, firebaseUser, {
    method: "POST",
    body: JSON.stringify({
      generation_id: generationId,
      version_index: versionIndex,
      energy_delta: energyDelta,
      instrument_change: instrumentChange?.trim() || undefined
    })
  }),
  regenerateSkarlyV2Section: (creatorMode: CreatorMode, firebaseUser: User | null, generationId: string, versionIndex: number, sectionStartSeconds: number, sectionEndSeconds: number, editInstruction: string) => backendRequest<SkarlyV2Job>("/api/v2/generations/regenerate-section", creatorMode, firebaseUser, {
    method: "POST",
    body: JSON.stringify({
      generation_id: generationId,
      version_index: versionIndex,
      section_name: "selected section",
      section_start_seconds: sectionStartSeconds,
      section_end_seconds: sectionEndSeconds,
      edit_instruction: editInstruction.trim(),
      repaint_mode: "balanced",
      repaint_strength: 0.65,
      boundary_crossfade_seconds: 0.025
    })
  }),
  remixSkarlyV2: (creatorMode: CreatorMode, firebaseUser: User | null, generationId: string, versionIndex: number, mixPreset: MixPreset, balance: number) => backendRequest<SkarlyV2Job>("/api/v2/mixes", creatorMode, firebaseUser, {
    method: "POST",
    body: JSON.stringify({
      generation_id: generationId,
      version_index: versionIndex,
      mix_profile: skarlyMixPresetValue(mixPreset),
      vocal_music_balance: balance
    })
  }),
  exportSkarlyV2: (creatorMode: CreatorMode, firebaseUser: User | null, generationId: string, versionIndex: number) => backendRequest<SkarlyV2ExportResponse>("/api/v2/exports", creatorMode, firebaseUser, {
    method: "POST",
    body: JSON.stringify({
      generation_id: generationId,
      version_index: versionIndex,
      include_optional_stems: true
    })
  }),
  saveSkarlyV2Feedback: (creatorMode: CreatorMode, firebaseUser: User | null, payload: Record<string, unknown>) => backendRequest<SkarlyV2Job>("/api/v2/feedback", creatorMode, firebaseUser, {
    method: "POST",
    body: JSON.stringify(payload)
  }),
  analyzeSkarly: (creatorMode: CreatorMode, firebaseUser: User | null, source: InputSource, _intent: GenerationIntent) => backendRequest<SkarlyAnalyzeResponse>("/v1/skarly/analyze", creatorMode, firebaseUser, {
    method: "POST",
    body: JSON.stringify({
      ...skarlyUploadPayload(source)
    })
  }),
  generateSkarly: (creatorMode: CreatorMode, firebaseUser: User | null, source: InputSource, intent: GenerationIntent, detected?: SkarlyDetected | null) => backendRequest<SkarlyGenerateResponse>("/v1/skarly/generate", creatorMode, firebaseUser, {
    method: "POST",
    body: JSON.stringify({
      ...skarlyUploadPayload(source),
      language: intent.language || detected?.language,
      mood: intent.moodTags || detected?.mood,
      genre_override: intent.genreOverride.trim() || undefined,
      training_opt_in: intent.trainingOptIn,
      mix_preset: skarlyMixPresetValue(intent.mixPreset),
      arrangement_mode: source.arrangementMode ?? "vocal_to_song",
      preserve_original_vocal: source.preserveOriginalVocal ?? source.arrangementMode === "full_song",
      reference_strength: source.referenceStrength ?? 0.35
    })
  }),
  selectSkarlyVersion: (creatorMode: CreatorMode, firebaseUser: User | null, jobId: string, versionIndex: number) => backendRequest<BackendJobResponse>(`/v1/skarly/jobs/${jobId}/select`, creatorMode, firebaseUser, {
    method: "POST",
    body: JSON.stringify({ version_index: versionIndex })
  }),
  createJob: (creatorMode: CreatorMode, firebaseUser: User | null, source: InputSource, genre: Genre, intent: GenerationIntent) => backendRequest<BackendJobResponse>("/v1/jobs", creatorMode, firebaseUser, {
    method: "POST",
    body: JSON.stringify({
      raw_audio_path: source.rawAudioPath,
      genre: genre.label,
      track_name: "Pending backend draft",
      source_type: source.kind,
      arrangement_mode: source.arrangementMode ?? "vocal_to_song",
      ...generationIntentPayload(intent),
      delete_raw_after_mix: false
    })
  }),
  getJob: (creatorMode: CreatorMode, firebaseUser: User | null, jobId: string) => backendRequest<BackendJobResponse>(`/v1/jobs/${jobId}`, creatorMode, firebaseUser),
  updateJobLibrary: (creatorMode: CreatorMode, firebaseUser: User | null, jobId: string, trackName?: string, libraryStatus?: TrackStatus) => backendRequest<BackendJobResponse>(`/v1/jobs/${jobId}/library`, creatorMode, firebaseUser, {
    method: "PATCH",
    body: JSON.stringify({
      track_name: trackName,
      library_status: libraryStatus
    })
  }),
  getVoiceTakes: (creatorMode: CreatorMode, firebaseUser: User | null) => backendRequest<BackendVoiceTakeListResponse>("/v1/voice-takes", creatorMode, firebaseUser),
  getRecycleBin: (creatorMode: CreatorMode, firebaseUser: User | null) => backendRequest<BackendRecycleBinResponse>("/v1/recycle-bin", creatorMode, firebaseUser),
  recoverLibrary: (creatorMode: CreatorMode, firebaseUser: User | null) => backendRequest<BackendLibraryRecoveryResponse>("/v1/library/recover", creatorMode, firebaseUser, { method: "POST" }),
  getVoiceTakePlayback: (creatorMode: CreatorMode, firebaseUser: User | null, takeId: string) => backendRequest<BackendVoiceTakePlaybackResponse>(`/v1/voice-takes/${takeId}/play`, creatorMode, firebaseUser),
  saveVoiceTake: (creatorMode: CreatorMode, firebaseUser: User | null, take: VoiceTake) => backendRequest<BackendVoiceTakeResponse>("/v1/voice-takes", creatorMode, firebaseUser, {
    method: "POST",
    body: JSON.stringify({
      title: take.title,
      duration: take.duration,
      raw_audio_path: take.rawAudioPath,
      content_type: take.contentType ?? "audio/mpeg",
      size_bytes: take.sizeBytes ?? null
    })
  }),
  deleteVoiceTake: (creatorMode: CreatorMode, firebaseUser: User | null, takeId: string) => backendRequest<BackendVoiceTakeResponse>(`/v1/voice-takes/${takeId}`, creatorMode, firebaseUser, { method: "DELETE" }),
  restoreVoiceTake: (creatorMode: CreatorMode, firebaseUser: User | null, takeId: string) => backendRequest<BackendVoiceTakeResponse>(`/v1/voice-takes/${takeId}/restore`, creatorMode, firebaseUser, { method: "POST" }),
  permanentlyDeleteVoiceTake: (creatorMode: CreatorMode, firebaseUser: User | null, takeId: string) => backendRequest<BackendVoiceTakeResponse>(`/v1/voice-takes/${takeId}/permanent`, creatorMode, firebaseUser, { method: "DELETE" }),
  getAdminSummary: (creatorMode: CreatorMode, firebaseUser: User | null) => backendRequest<BackendAdminSummaryResponse>("/v1/admin/summary", creatorMode, firebaseUser),
  cleanupStaleLibrary: (creatorMode: CreatorMode, firebaseUser: User | null) => backendRequest<BackendHistoryResponse>("/v1/library/cleanup-stale", creatorMode, firebaseUser, { method: "POST" }),
  getHistory: (creatorMode: CreatorMode, firebaseUser: User | null) => backendRequest<BackendHistoryResponse>("/v1/history", creatorMode, firebaseUser),
  retryJob: (creatorMode: CreatorMode, firebaseUser: User | null, jobId: string) => backendRequest<BackendJobResponse>(`/v1/jobs/${jobId}/retry`, creatorMode, firebaseUser, { method: "POST" }),
  deleteTrack: (creatorMode: CreatorMode, firebaseUser: User | null, jobId: string) => backendRequest<BackendJobResponse>(`/v1/tracks/${jobId}`, creatorMode, firebaseUser, { method: "DELETE" }),
  restoreTrack: (creatorMode: CreatorMode, firebaseUser: User | null, jobId: string) => backendRequest<BackendJobResponse>(`/v1/tracks/${jobId}/restore`, creatorMode, firebaseUser, { method: "POST" }),
  permanentlyDeleteTrack: (creatorMode: CreatorMode, firebaseUser: User | null, jobId: string) => backendRequest<BackendJobResponse>(`/v1/tracks/${jobId}/permanent`, creatorMode, firebaseUser, { method: "DELETE" }),
  deleteRaw: (creatorMode: CreatorMode, firebaseUser: User | null, jobId: string) => backendRequest<BackendJobResponse>(`/v1/privacy/delete-raw/${jobId}`, creatorMode, firebaseUser, { method: "POST" })
};

async function pollSkarlyV2Job(
  creatorMode: CreatorMode,
  firebaseUser: User | null,
  jobId: string,
  onProgress: (job: SkarlyV2Job) => void,
  timeoutMs = 2 * 60 * 60 * 1000,
  staleTimeoutMs = 20 * 60 * 1000
) {
  const deadline = Date.now() + timeoutMs;
  let lastActivityAt = Date.now();
  let lastFingerprint = "";
  while (Date.now() < deadline) {
    const job = await backendApi.getSkarlyV2Job(creatorMode, firebaseUser, jobId);
    const fingerprint = [
      job.status,
      job.stage,
      job.progress,
      job.current_arrangement,
      job.completed_arrangements,
      job.completed_duration_seconds
    ].join("|");
    if (fingerprint !== lastFingerprint) {
      lastFingerprint = fingerprint;
      lastActivityAt = Date.now();
    }
    onProgress(job);
    if (job.status === "ready") return job;
    if (job.status === "failed") {
      throw new Error(job.error?.message || `Skarly stopped during ${job.stage}`);
    }
    if (Date.now() - lastActivityAt >= staleTimeoutMs) {
      throw new Error("Skarly stopped reporting progress. The job is still saved and can be resumed without starting over.");
    }
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  throw new Error("Skarly is still working beyond the monitoring window. The job is saved; resume it instead of starting over.");
}

function App() {
  const [screen, setScreen] = useState<Screen>("splash");
  const [creatorMode, setCreatorMode] = useState<CreatorMode>("guest");
  const [loginChoice, setLoginChoice] = useState<LoginChoice>(null);
  const [creatorProfile, setCreatorProfile] = useState<CreatorProfile>({
    name: "Guest Creator",
    email: "",
    bio: "Private Skarly workspace"
  });
  const [firebaseUser, setFirebaseUser] = useState<User | null>(null);
  const [firebaseStatus, setFirebaseStatus] = useState<FirebaseSetupStatus>(hasFirebaseConfig ? "loading" : "unconfigured");
  const [startupLoading, setStartupLoading] = useState(true);
  const [authBusy, setAuthBusy] = useState(false);
  const [accountRestoring, setAccountRestoring] = useState(false);
  const [intent, setIntent] = useState("Demo Song");
  const [selectedGenre, setSelectedGenreState] = useState(getStoredGenre);
  const [generationIntent, setGenerationIntent] = useState<GenerationIntent>(defaultGenerationIntent);
  const [processingIndex, setProcessingIndex] = useState(0);
  const [trackName, setTrackName] = useState("");
  const [fileNameMode, setFileNameMode] = useState<FileNameMode>("keep");
  const [isPlaying, setIsPlaying] = useState(false);
  const [mixDurationMs, setMixDurationMs] = useState(0);
  const [mixPositionMs, setMixPositionMs] = useState(0);
  const [activePlaybackUrl, setActivePlaybackUrl] = useState<string | null>(null);
  const [hasDownloaded, setHasDownloaded] = useState(false);
  const [hasShared, setHasShared] = useState(false);
  const [hasSaved, setHasSaved] = useState(false);
  const [toastMessage, setToastMessage] = useState("");
  const [backendMode, setBackendMode] = useState<BackendMode>(USE_BACKEND_API ? "api" : "offline");
  const [backendMessage, setBackendMessage] = useState(USE_BACKEND_API ? BACKEND_CONNECTED_MESSAGE : BACKEND_OFFLINE_MESSAGE);
  const [backendJobId, setBackendJobId] = useState<string | null>(null);
  const [generationError, setGenerationError] = useState<string | null>(null);
  const [backendFinalUrl, setBackendFinalUrl] = useState<string | null>(null);
  const [backendDownloadUrl, setBackendDownloadUrl] = useState<string | null>(null);
  const [backendIsolatedVocalUrl, setBackendIsolatedVocalUrl] = useState<string | null>(null);
  const [backendBackingUrl, setBackendBackingUrl] = useState<string | null>(null);
  const [backendExportUrls, setBackendExportUrls] = useState<DemoExportUrls>({});
  const [backendAnalysis, setBackendAnalysis] = useState<BackendSongAnalysis | null>(null);
  const [backendBlueprint, setBackendBlueprint] = useState<BackendSongBlueprint | null>(null);
  const [skarlyAnalysis, setSkarlyAnalysis] = useState<SkarlyAnalyzeResponse | null>(null);
  const [skarlyResult, setSkarlyResult] = useState<SkarlyGenerateResponse | null>(null);
  const [skarlyAnalysisV2Id, setSkarlyAnalysisV2Id] = useState<string | null>(null);
  const [skarlyGenerationV2Id, setSkarlyGenerationV2Id] = useState<string | null>(null);
  const [skarlyV2Job, setSkarlyV2Job] = useState<SkarlyV2Job | null>(null);
  const [producerProfiles, setProducerProfiles] = useState<SkarlyProducerProfile[]>([]);
  const [selectedProducerProfileIds, setSelectedProducerProfileIds] = useState<string[]>(defaultProducerProfileIds);
  const [vocalMusicBalance, setVocalMusicBalance] = useState(0);
  const [skarlyRemixBusy, setSkarlyRemixBusy] = useState(false);
  const [skarlyRegenerationBusy, setSkarlyRegenerationBusy] = useState(false);
  const [skarlySectionBusy, setSkarlySectionBusy] = useState(false);
  const [skarlyExportBusy, setSkarlyExportBusy] = useState(false);
  const [skarlyExportResult, setSkarlyExportResult] = useState<SkarlyV2ExportResponse | null>(null);
  const [selectedSkarlyVersionIndex, setSelectedSkarlyVersionIndex] = useState(0);
  const [skarlyBusy, setSkarlyBusy] = useState(false);
  const [backendTracks, setBackendTracks] = useState<BackendJob[]>([]);
  const [adminSummary, setAdminSummary] = useState<BackendAdminSummaryResponse | null>(null);
  const [adminLoading, setAdminLoading] = useState(false);
  const [recycleVoiceTakes, setRecycleVoiceTakes] = useState<VoiceTake[]>([]);
  const [recycleTracks, setRecycleTracks] = useState<BackendJob[]>([]);
  const [deletedGeneratedTracks, setDeletedGeneratedTracks] = useState<GeneratedTrackView[]>([]);
  const [deletedBackendTrackIds, setDeletedBackendTrackIds] = useState<string[]>([]);
  const [voiceTakes, setVoiceTakes] = useState<VoiceTake[]>([]);
  const [uploadingVoiceTakeIds, setUploadingVoiceTakeIds] = useState<string[]>([]);
  const [playingVoiceTakeId, setPlayingVoiceTakeId] = useState<string | null>(null);
  const [generatedTracks, setGeneratedTracks] = useState<GeneratedTrackView[]>([]);
  const [currentGeneratedTrackId, setCurrentGeneratedTrackId] = useState<string | null>(null);
  const [generationActive, setGenerationActive] = useState(false);
  const [inputSource, setInputSource] = useState<InputSource>({
    kind: "recording",
    label: "Recorded vocal",
    detail: "Recording input",
    arrangementMode: "vocal_to_song"
  });
  const voiceSoundRef = useRef<Audio.Sound | null>(null);
  const mixSoundRef = useRef<Audio.Sound | null>(null);
  const webAudioRef = useRef<any | null>(null);
  const webAudioObjectUrlRef = useRef<string | null>(null);
  const activePlaybackUrlRef = useRef<string | null>(null);
  const accountKey = useMemo(() => localAccountKey(creatorMode, firebaseUser), [creatorMode, firebaseUser]);

  const showToast = useCallback((message: string) => {
    setToastMessage(message);
  }, []);

  const setSelectedGenre = useCallback((genre: Genre) => {
    setSelectedGenreState(genre);
    storeDefaultGenre(genre, accountKey);
  }, [accountKey]);

  const applyBackendDemoResponse = useCallback((response: BackendJobResponse) => {
    setBackendFinalUrl(response.final_mp3_url ?? null);
    setBackendDownloadUrl(response.final_mp3_download_url ?? response.final_mp3_url ?? null);
    setBackendIsolatedVocalUrl(response.isolated_vocal_url ?? null);
    setBackendBackingUrl(response.backing_audio_url ?? null);
    setBackendExportUrls(demoExportUrlsFromResponse(response));
    setBackendAnalysis(response.job.analysis ?? null);
    setBackendBlueprint(response.job.blueprint ?? null);
  }, []);

  const clearSkarlySession = useCallback(() => {
    webAudioRef.current?.pause?.();
    webAudioRef.current = null;
    revokeObjectUrl(webAudioObjectUrlRef.current);
    webAudioObjectUrlRef.current = null;
    void mixSoundRef.current?.unloadAsync().catch(() => undefined);
    mixSoundRef.current = null;
    activePlaybackUrlRef.current = null;
    setActivePlaybackUrl(null);
    setIsPlaying(false);
    setMixDurationMs(0);
    setMixPositionMs(0);
    setSkarlyAnalysis(null);
    setSkarlyResult(null);
    setSkarlyAnalysisV2Id(null);
    setSkarlyGenerationV2Id(null);
    setSkarlyV2Job(null);
    setSelectedProducerProfileIds(defaultProducerProfileIds);
    setVocalMusicBalance(0);
    setSkarlyRemixBusy(false);
    setSkarlyRegenerationBusy(false);
    setSkarlySectionBusy(false);
    setSkarlyExportBusy(false);
    setSkarlyExportResult(null);
    setSelectedSkarlyVersionIndex(0);
    setSkarlyBusy(false);
    setGenerationError(null);
  }, []);

  const applySelectedSkarlyVersion = useCallback((response: SkarlyGenerateResponse, index: number, notify = false) => {
    const safeIndex = Math.max(0, Math.min(index, response.versions.length - 1));
    const version = response.versions[safeIndex];
    if (!version) return;
    const finalUrl = backendMediaUrl(version.final_mix_url);
    const backingUrl = backendMediaUrl(version.backing_url);
    setSelectedSkarlyVersionIndex(safeIndex);
    setBackendJobId(response.job_id);
    setBackendFinalUrl(finalUrl);
    setBackendDownloadUrl(finalUrl);
    setBackendBackingUrl(backingUrl);
    setBackendIsolatedVocalUrl(backendMediaUrl(response.vocal_url));
    setBackendExportUrls({
      mp3: finalUrl,
      melodyMidi: backendMediaUrl(response.melody_midi_url),
      backingStem: backingUrl
    });
    setBackendAnalysis(skarlyAnalysisToBackendAnalysis(response.detected));
    setBackendBlueprint(null);
    setTrackName(version.name);
    setFileNameMode("keep");
    if (notify) showToast(`${version.name} selected`);
  }, [showToast]);

  const finishSkarlyGeneration = useCallback((completed: SkarlyV2Job) => {
    if (!completed.result) throw new Error("Skarly generation completed without output files");
    const response = completed.result as unknown as SkarlyGenerateResponse;
    setSkarlyV2Job(completed);
    setProcessingIndex(5);
    setSkarlyResult(response);
    applySelectedSkarlyVersion(response, 0);
    setBackendMode("api");
    setBackendMessage(BACKEND_CONNECTED_MESSAGE);
    setGenerationError(null);
    setGenerationActive(false);
    setScreen("result");
  }, [applySelectedSkarlyVersion]);

  useEffect(() => {
    const storedGenre = getStoredGenreForAccount(accountKey);
    if (storedGenre) setSelectedGenreState(storedGenre);
    setVoiceTakes((current) => mergeLocalVoiceTakes(loadLocalVoiceTakes(accountKey), current));
  }, [accountKey]);

  useEffect(() => {
    storeLocalVoiceTakes(accountKey, voiceTakes);
  }, [accountKey, voiceTakes]);

  useEffect(() => {
    return () => {
      void voiceSoundRef.current?.unloadAsync();
      void mixSoundRef.current?.unloadAsync();
      webAudioRef.current?.pause?.();
      webAudioRef.current = null;
      revokeObjectUrl(webAudioObjectUrlRef.current);
      webAudioObjectUrlRef.current = null;
      activePlaybackUrlRef.current = null;
    };
  }, []);

  const resetAppSession = useCallback(() => {
    setScreen("splash");
    setCreatorMode("guest");
    setLoginChoice(null);
    setCreatorProfile({ name: "Guest Creator", email: "", bio: "Private Skarly workspace" });
    setIntent("Demo Song");
    setSelectedGenre(genres[0]);
    setGenerationIntent(defaultGenerationIntent);
    setProcessingIndex(0);
    setTrackName("");
    setFileNameMode("keep");
    setIsPlaying(false);
    setMixDurationMs(0);
    setMixPositionMs(0);
    activePlaybackUrlRef.current = null;
    setActivePlaybackUrl(null);
    setHasDownloaded(false);
    setHasShared(false);
    setHasSaved(false);
    setBackendMode(USE_BACKEND_API ? "api" : "offline");
    setBackendMessage(USE_BACKEND_API ? BACKEND_CONNECTED_MESSAGE : BACKEND_OFFLINE_MESSAGE);
    setBackendJobId(null);
    setBackendFinalUrl(null);
    setBackendDownloadUrl(null);
    setBackendIsolatedVocalUrl(null);
    setBackendBackingUrl(null);
    setBackendExportUrls({});
    setBackendAnalysis(null);
    setBackendBlueprint(null);
    setSkarlyAnalysis(null);
    setSkarlyResult(null);
    setSelectedSkarlyVersionIndex(0);
    setSkarlyBusy(false);
    setBackendTracks([]);
    setAdminSummary(null);
    setAdminLoading(false);
    setRecycleVoiceTakes([]);
    setRecycleTracks([]);
    setDeletedGeneratedTracks([]);
    setDeletedBackendTrackIds([]);
    setVoiceTakes([]);
    setGeneratedTracks([]);
    setCurrentGeneratedTrackId(null);
    setGenerationActive(false);
    setInputSource({ kind: "recording", label: "Recorded vocal", detail: "Recording input", arrangementMode: "vocal_to_song" });
    showToast("Session reset");
  }, [showToast]);

  const normalizeEmail = (email: string) => email.trim().toLowerCase();

  useEffect(() => {
    const timer = setTimeout(() => setStartupLoading(false), 1800);
    return () => clearTimeout(timer);
  }, []);

  useEffect(() => {
    if (!firebaseAuth) {
      setFirebaseStatus("unconfigured");
      return undefined;
    }

    let resolved = false;
    const timeout = setTimeout(() => {
      if (!resolved) {
        setFirebaseStatus("unavailable");
        showToast("Saved session check timed out. Sign in manually.");
      }
    }, 6000);

    const unsubscribe = onAuthStateChanged(firebaseAuth, (user) => {
      resolved = true;
      clearTimeout(timeout);
      setAccountRestoring(!!user);
      setFirebaseUser(user);
      setFirebaseStatus("ready");
      if (!user) {
        setAccountRestoring(false);
        return;
      }
      const email = user.email ?? "";
      setCreatorMode("saved");
      setLoginChoice("signin");
      setCreatorProfile((current) => ({
        ...current,
        name: current.name === "Guest Creator" ? (user.displayName || email.split("@")[0] || "Saved Creator") : current.name,
        email,
        bio: current.bio || "Private Skarly workspace"
      }));
    });
    return () => {
      resolved = true;
      clearTimeout(timeout);
      unsubscribe();
    };
  }, [showToast]);

  useEffect(() => {
    if (!firebaseUser || startupLoading || accountRestoring) return;
    setScreen((current) => ["splash", "login", "authSignIn", "authSignUp", "setup"].includes(current) ? "home" : current);
  }, [accountRestoring, firebaseUser, startupLoading]);

  useEffect(() => {
    if (!firebaseUser || creatorMode !== "saved") {
      setAccountRestoring(false);
      return;
    }
    if (!USE_BACKEND_API) {
      setAccountRestoring(false);
      return;
    }
    let cancelled = false;
    setAccountRestoring(true);
    const restoreSavedWorkspace = async () => {
      try {
        try {
          const response = await backendApi.getProfile("saved", firebaseUser);
          if (cancelled) return;
          const savedGenre = genreFromProfileBio(response.profile.bio);
          if (savedGenre) setSelectedGenre(savedGenre);
          setCreatorProfile({
            name: response.profile.name,
            email: response.profile.email,
            bio: cleanProfileBio(response.profile.bio),
            avatarUri: response.profile.photo_url ?? undefined
          });
        } catch {
          if (cancelled) return;
          setCreatorProfile((current) => ({
            ...current,
            email: firebaseUser.email ?? current.email,
            name: current.name === "Guest Creator" ? (firebaseUser.displayName || firebaseUser.email?.split("@")[0] || "Saved Creator") : current.name
          }));
        }

        const [history, takes] = await Promise.all([
          backendApi.getHistory("saved", firebaseUser),
          backendApi.getVoiceTakes("saved", firebaseUser)
        ]);
        if (cancelled) return;
        setBackendTracks(visibleBackendJobs(history.tracks));
        setVoiceTakes((current) => mergeVoiceTakesWithBackend(current, takes.takes));
        setBackendMode("api");
        setBackendMessage(BACKEND_CONNECTED_MESSAGE);
      } catch {
        if (cancelled) return;
        setBackendMode("offline");
        setBackendMessage(BACKEND_OFFLINE_MESSAGE);
      } finally {
        if (!cancelled) setAccountRestoring(false);
      }
    };
    void restoreSavedWorkspace();
    return () => {
      cancelled = true;
      setAccountRestoring(false);
    };
  }, [creatorMode, firebaseUser, setSelectedGenre]);

  const finishAuth = useCallback(async (submission: AuthSubmit, kind: "signin" | "signup") => {
    const email = normalizeEmail(submission.profile.email);
    if (!email) {
      showToast("Enter an email to continue");
      return;
    }

    if (!firebaseAuth || firebaseStatus === "unconfigured") {
      showToast("Add Firebase config to enable saved accounts");
      return;
    }

    setAuthBusy(true);
    setAccountRestoring(true);
    try {
      const credential = kind === "signup"
        ? await createUserWithEmailAndPassword(firebaseAuth, email, submission.password)
        : await signInWithEmailAndPassword(firebaseAuth, email, submission.password);
      setFirebaseUser(credential.user);
      setCreatorMode("saved");
      setCreatorProfile({
        ...submission.profile,
        name: submission.profile.name.trim() || email.split("@")[0] || "Saved Creator",
        email
      });
      await backendApi.saveProfile("saved", credential.user, {
        ...submission.profile,
        name: submission.profile.name.trim() || email.split("@")[0] || "Saved Creator",
        email,
        bio: profileBioWithDefaultGenre(submission.profile.bio, selectedGenre)
      });
      const [history, takes] = await Promise.all([
        backendApi.getHistory("saved", credential.user).catch(() => ({ tracks: [] })),
        backendApi.getVoiceTakes("saved", credential.user).catch(() => ({ takes: [] }))
      ]);
      setBackendTracks(visibleBackendJobs(history.tracks));
      setVoiceTakes((current) => mergeVoiceTakesWithBackend(current, takes.takes));
      setBackendMode("api");
      setBackendMessage(BACKEND_CONNECTED_MESSAGE);
      setScreen("home");
      showToast(kind === "signup" ? "Firebase workspace created" : "Signed in");
    } catch (error) {
      if (error instanceof Error && String(error.message).includes("Network request failed")) {
        setBackendMode("offline");
        setBackendMessage(BACKEND_OFFLINE_MESSAGE);
      }
      showToast(firebaseAuthErrorMessage(error, kind));
    } finally {
      setAccountRestoring(false);
      setAuthBusy(false);
    }
  }, [firebaseStatus, selectedGenre, showToast]);

  const logout = useCallback(async () => {
    setAuthBusy(true);
    let firebaseLogoutFailed = false;
    if (firebaseAuth && (firebaseUser || firebaseAuth.currentUser)) {
      try {
        await signOut(firebaseAuth);
      } catch {
        firebaseLogoutFailed = true;
      }
    }
    setFirebaseUser(null);
    setCreatorMode("guest");
    setLoginChoice(null);
    setCreatorProfile({ name: "Guest Creator", email: "", bio: "Private Skarly workspace" });
    setBackendTracks([]);
    setAdminSummary(null);
    setAdminLoading(false);
    setRecycleVoiceTakes([]);
    setRecycleTracks([]);
    setDeletedGeneratedTracks([]);
    setDeletedBackendTrackIds([]);
    setVoiceTakes([]);
    setGeneratedTracks([]);
    setCurrentGeneratedTrackId(null);
    setBackendJobId(null);
    setBackendFinalUrl(null);
    setBackendDownloadUrl(null);
    setBackendIsolatedVocalUrl(null);
    setBackendBackingUrl(null);
    setBackendMode("offline");
    setBackendMessage("Signed out. Choose Guest, Sign Up, or Sign In.");
    setAuthBusy(false);
    setScreen("login");
    showToast(firebaseLogoutFailed ? "Local session cleared. Sign in again if Firebase still shows this account." : "Logged out");
  }, [firebaseUser, showToast]);

  const refreshBackendHistory = useCallback(async () => {
    if (!USE_BACKEND_API) return;
    try {
      const history = await backendApi.getHistory(creatorMode, firebaseUser);
      setBackendTracks(visibleBackendJobs(history.tracks));
      setBackendMode("api");
      setBackendMessage(BACKEND_CONNECTED_MESSAGE);
    } catch {
      setBackendMode("offline");
      setBackendMessage(BACKEND_OFFLINE_MESSAGE);
    }
  }, [creatorMode, firebaseUser]);

  const refreshBackendVoiceTakes = useCallback(async () => {
    if (!USE_BACKEND_API || creatorMode !== "saved") return;
    try {
      const response = await backendApi.getVoiceTakes(creatorMode, firebaseUser);
      setVoiceTakes((current) => mergeVoiceTakesWithBackend(current, response.takes));
      setBackendMode("api");
      setBackendMessage(BACKEND_CONNECTED_MESSAGE);
    } catch {
      setBackendMode("offline");
      setBackendMessage(BACKEND_OFFLINE_MESSAGE);
    }
  }, [creatorMode, firebaseUser]);

  const refreshRecycleBin = useCallback(async () => {
    if (!USE_BACKEND_API || creatorMode !== "saved") return;
    try {
      const response = await backendApi.getRecycleBin(creatorMode, firebaseUser);
      setRecycleVoiceTakes(response.voice_takes.map(mapBackendVoiceTake));
      setRecycleTracks(response.tracks);
      setBackendMode("api");
      setBackendMessage(BACKEND_CONNECTED_MESSAGE);
    } catch {
      setBackendMode("offline");
      setBackendMessage(BACKEND_OFFLINE_MESSAGE);
    }
  }, [creatorMode, firebaseUser]);

  const refreshAdminSummary = useCallback(async () => {
    if (!USE_BACKEND_API || creatorMode !== "saved") {
      showToast("Admin panel needs a saved creator session");
      return;
    }
    setAdminLoading(true);
    try {
      const response = await backendApi.getAdminSummary(creatorMode, firebaseUser);
      setAdminSummary(response);
      setBackendMode("api");
      setBackendMessage(BACKEND_CONNECTED_MESSAGE);
    } catch (error) {
      const status = backendStatus(error);
      setBackendMode(status ? "api" : "offline");
      const message = status === 403
        ? "Admin access denied. Sign in with the configured admin account."
        : status === 401
          ? "Admin session missing. Sign out, sign in again, then refresh admin data."
        : status === 404
          ? "Backend is running old code. Restart the FastAPI server."
          : BACKEND_OFFLINE_MESSAGE;
      setBackendMessage(message);
      showToast(status === 403 ? "Use admin account" : status === 401 ? "Sign in again" : status === 404 ? "Restart backend to load admin route" : "Could not load admin panel");
    } finally {
      setAdminLoading(false);
    }
  }, [creatorMode, firebaseUser, showToast]);

  const cleanupStaleLibrary = useCallback(async () => {
    if (!USE_BACKEND_API || creatorMode !== "saved") {
      showToast("Cleanup needs a saved admin session");
      return;
    }
    setAdminLoading(true);
    try {
      const response = await backendApi.cleanupStaleLibrary(creatorMode, firebaseUser);
      setBackendTracks((current) => visibleBackendJobs(current).filter((job) => !response.tracks.some((deleted) => deleted.job_id === job.job_id)));
      await Promise.all([refreshAdminSummary(), refreshBackendHistory(), refreshRecycleBin()]);
      showToast(`Moved ${response.tracks.length} stale item${response.tracks.length === 1 ? "" : "s"} to Recycle Bin`);
    } catch (error) {
      showToast(`Cleanup failed: ${errorMessage(error)}`);
    } finally {
      setAdminLoading(false);
    }
  }, [creatorMode, firebaseUser, refreshAdminSummary, refreshBackendHistory, refreshRecycleBin, showToast]);

  const recoverCloudLibrary = useCallback(async (showFeedback = true) => {
    if (!USE_BACKEND_API || creatorMode !== "saved") {
      if (showFeedback) showToast("Cloud recovery is for saved creators");
      return;
    }
    try {
      const response = await backendApi.recoverLibrary(creatorMode, firebaseUser);
      const recoveredCount = response.recovered_voice_takes + response.recovered_tracks;
      setVoiceTakes((current) => mergeVoiceTakesWithBackend(current, response.takes));
      setBackendTracks(visibleBackendJobs(response.tracks));
      setBackendMode("api");
      setBackendMessage(BACKEND_CONNECTED_MESSAGE);
      if (showFeedback || recoveredCount > 0) {
        showToast(`Recovered ${recoveredCount} cloud item${recoveredCount === 1 ? "" : "s"}`);
      }
    } catch {
      setBackendMode("offline");
      setBackendMessage(BACKEND_OFFLINE_MESSAGE);
      if (showFeedback) showToast("Could not recover cloud library");
    }
  }, [creatorMode, firebaseUser, showToast]);

  useEffect(() => {
    if (screen !== "history" || creatorMode !== "saved" || !firebaseUser) return;
    void recoverCloudLibrary(false);
  }, [creatorMode, firebaseUser, recoverCloudLibrary, screen]);

  useEffect(() => {
    if (screen !== "recycleBin" || creatorMode !== "saved" || !firebaseUser) return;
    void refreshRecycleBin();
  }, [creatorMode, firebaseUser, refreshRecycleBin, screen]);

  useEffect(() => {
    if (screen !== "admin" || creatorMode !== "saved" || !firebaseUser) return;
    void refreshAdminSummary();
  }, [creatorMode, firebaseUser, refreshAdminSummary, screen]);

  const saveCreatorProfile = useCallback(async (profile: CreatorProfile) => {
    if (creatorMode !== "saved") {
      setCreatorProfile(profile);
      return true;
    }

    try {
      const profileGenre = genreFromProfileBio(profile.bio) ?? selectedGenre;
      const response = await backendApi.saveProfile(creatorMode, firebaseUser, {
        ...profile,
        bio: profileBioWithDefaultGenre(profile.bio, profileGenre)
      });
      const savedGenre = genreFromProfileBio(response.profile.bio);
      if (savedGenre) setSelectedGenre(savedGenre);
      setCreatorProfile({
        name: response.profile.name,
        email: response.profile.email,
        bio: cleanProfileBio(response.profile.bio),
        avatarUri: response.profile.photo_url ?? undefined
      });
      setBackendMode("api");
      setBackendMessage(BACKEND_CONNECTED_MESSAGE);
      return true;
    } catch {
      setBackendMode("offline");
      setBackendMessage(BACKEND_OFFLINE_MESSAGE);
      showToast("Could not save cloud profile");
      return false;
    }
  }, [creatorMode, firebaseUser, selectedGenre, setSelectedGenre, showToast]);

  const deleteCurrentGeneration = useCallback(() => {
    const deletedId = backendJobId ?? currentGeneratedTrackId;
    if (backendJobId) {
      setDeletedBackendTrackIds((current) => current.includes(backendJobId) ? current : [...current, backendJobId]);
      backendApi.deleteTrack(creatorMode, firebaseUser, backendJobId).then(() => {
        refreshBackendHistory();
        refreshRecycleBin();
      }).catch(() => {
        showToast("Removed locally. Backend delete will retry later.");
      });
    }
    webAudioRef.current?.pause?.();
    webAudioRef.current = null;
    revokeObjectUrl(webAudioObjectUrlRef.current);
    webAudioObjectUrlRef.current = null;
    void mixSoundRef.current?.unloadAsync().catch(() => undefined);
    mixSoundRef.current = null;
    activePlaybackUrlRef.current = null;
    setActivePlaybackUrl(null);
    setTrackName("");
    setIsPlaying(false);
    setMixDurationMs(0);
    setMixPositionMs(0);
    setHasDownloaded(false);
    setHasShared(false);
    setHasSaved(false);
    setBackendJobId(null);
    setBackendFinalUrl(null);
    setBackendDownloadUrl(null);
    setBackendIsolatedVocalUrl(null);
    setBackendBackingUrl(null);
    setSkarlyResult(null);
    setSkarlyAnalysis(null);
    setSelectedSkarlyVersionIndex(0);
    setGeneratedTracks((current) => {
      const deletedTrack = deletedId ? current.find((track) => track.id === deletedId) : undefined;
      if (deletedTrack) setDeletedGeneratedTracks((deleted) => [deletedTrack, ...deleted.filter((track) => track.id !== deletedTrack.id)]);
      return deletedId ? current.filter((track) => track.id !== deletedId) : current;
    });
    showToast("Moved to Recently Deleted");
    setScreen("home");
  }, [backendJobId, creatorMode, currentGeneratedTrackId, firebaseUser, refreshBackendHistory, refreshRecycleBin, showToast]);

  const deleteBackendHistoryTrack = useCallback((jobId: string) => {
    setDeletedBackendTrackIds((current) => current.includes(jobId) ? current : [...current, jobId]);
    backendApi.deleteTrack(creatorMode, firebaseUser, jobId).then(() => {
      refreshBackendHistory();
      refreshRecycleBin();
      showToast("Moved to Recently Deleted");
    }).catch(() => {
      showToast("Removed locally. Backend delete will retry later.");
    });
  }, [creatorMode, firebaseUser, refreshBackendHistory, refreshRecycleBin, showToast]);

  const deleteGeneratedTrack = useCallback((trackId: string) => {
    setGeneratedTracks((current) => {
      const deletedTrack = current.find((track) => track.id === trackId);
      if (deletedTrack) setDeletedGeneratedTracks((deleted) => [deletedTrack, ...deleted.filter((track) => track.id !== deletedTrack.id)]);
      return current.filter((track) => track.id !== trackId);
    });
    if (trackId === currentGeneratedTrackId || trackId === backendJobId) {
      setTrackName("");
      setIsPlaying(false);
      setHasDownloaded(false);
      setHasShared(false);
      setHasSaved(false);
      setBackendJobId(null);
      setBackendFinalUrl(null);
      setBackendDownloadUrl(null);
      setBackendIsolatedVocalUrl(null);
      setBackendBackingUrl(null);
      setBackendExportUrls({});
      setBackendAnalysis(null);
      setBackendBlueprint(null);
      setSkarlyResult(null);
      setSkarlyAnalysis(null);
      setSelectedSkarlyVersionIndex(0);
      setCurrentGeneratedTrackId(null);
    }
    showToast("Moved to Recently Deleted");
  }, [backendJobId, currentGeneratedTrackId, showToast]);

  const addVoiceTake = useCallback((draft: RecordedTakeDraft) => {
    const take: VoiceTake = {
      id: `take-${Date.now()}`,
      title: `Voice take ${voiceTakes.length + 1}`,
      duration: draft.duration,
      createdAt: "This session",
      fileUri: draft.fileUri,
      contentType: draft.contentType ?? "audio/m4a",
      sizeBytes: draft.sizeBytes
    };
    setVoiceTakes((current) => [take, ...current]);
    clearSkarlySession();
    setInputSource({
      kind: "recording",
      label: take.title,
      detail: `${take.duration}s recorded vocal`,
      arrangementMode: "vocal_to_song",
      fileUri: take.fileUri,
      contentType: take.contentType,
      sizeBytes: take.sizeBytes
    });
    showToast("Voice take saved");
    return take;
  }, [clearSkarlySession, showToast, voiceTakes.length]);

  const playVoiceTake = useCallback(async (take: VoiceTake) => {
    const getCloudPlaybackUri = async () => {
      if (!take.uploaded || !take.rawAudioPath) return undefined;
      showToast("Preparing cloud playback");
      const response = await backendApi.getVoiceTakePlayback(creatorMode, firebaseUser, take.id);
      setVoiceTakes((current) => current.map((item) => item.id === take.id ? { ...item, fileUri: response.raw_audio_url } : item));
      return response.raw_audio_url;
    };

    const startPlayback = async (uri: string) => {
      await voiceSoundRef.current?.unloadAsync().catch(() => undefined);
      await mixSoundRef.current?.unloadAsync().catch(() => undefined);
      voiceSoundRef.current = null;
      mixSoundRef.current = null;
      webAudioRef.current?.pause?.();
      webAudioRef.current = null;
      revokeObjectUrl(webAudioObjectUrlRef.current);
      webAudioObjectUrlRef.current = null;
      activePlaybackUrlRef.current = null;
      setActivePlaybackUrl(null);
      setIsPlaying(false);

      if (Platform.OS === "web") {
        const AudioElement = (globalThis as any).Audio;
        if (!AudioElement) throw new Error("Browser audio is not available");
        const playable = await prepareWebAudioSource(uri);
        const audio = new AudioElement(playable.uri);
        audio.preload = "auto";
        audio.onended = () => {
          if (webAudioRef.current === audio) webAudioRef.current = null;
          if (playable.revokeAfterUse) revokeObjectUrl(playable.uri);
          if (webAudioObjectUrlRef.current === playable.uri) webAudioObjectUrlRef.current = null;
          setPlayingVoiceTakeId(null);
        };
        audio.onerror = () => {
          if (webAudioRef.current === audio) webAudioRef.current = null;
          if (playable.revokeAfterUse) revokeObjectUrl(playable.uri);
          if (webAudioObjectUrlRef.current === playable.uri) webAudioObjectUrlRef.current = null;
          setPlayingVoiceTakeId(null);
          showToast("Browser could not decode this voice take");
        };
        webAudioObjectUrlRef.current = playable.revokeAfterUse ? playable.uri : null;
        webAudioRef.current = audio;
        setPlayingVoiceTakeId(take.id);
        await audio.play();
        return;
      }

      const { sound } = await Audio.Sound.createAsync({ uri }, { shouldPlay: true });
      voiceSoundRef.current = sound;
      setPlayingVoiceTakeId(take.id);
      sound.setOnPlaybackStatusUpdate((status) => {
        if ("didJustFinish" in status && status.didJustFinish) {
          setPlayingVoiceTakeId(null);
          void sound.unloadAsync();
          if (voiceSoundRef.current === sound) voiceSoundRef.current = null;
        }
      });
    };

    try {
      if (playingVoiceTakeId === take.id) {
        webAudioRef.current?.pause?.();
        webAudioRef.current = null;
        revokeObjectUrl(webAudioObjectUrlRef.current);
        webAudioObjectUrlRef.current = null;
        await voiceSoundRef.current?.stopAsync().catch(() => undefined);
        await voiceSoundRef.current?.unloadAsync().catch(() => undefined);
        voiceSoundRef.current = null;
        setPlayingVoiceTakeId(null);
        return;
      }

      let playbackUri = take.fileUri?.startsWith("blob:") && take.uploaded ? undefined : take.fileUri;
      playbackUri = playbackUri ?? await getCloudPlaybackUri();

      if (!playbackUri) {
        showToast(take.uploadState === "failed" ? "Upload failed. Retry upload before playback." : "This take needs cloud upload before playback.");
        return;
      }

      try {
        await startPlayback(playbackUri);
      } catch (firstError) {
        if (!take.rawAudioPath) throw firstError;
        const cloudUri = await getCloudPlaybackUri();
        if (!cloudUri || cloudUri === playbackUri) throw firstError;
        await startPlayback(cloudUri);
      }
    } catch (error) {
      showToast(`Could not play this voice take: ${errorMessage(error)}`);
      setPlayingVoiceTakeId(null);
    }
  }, [creatorMode, firebaseUser, playingVoiceTakeId, showToast]);

  const playUrl = useCallback(async (url: string, startPositionMs = 0) => {
    try {
      const requestedPositionMs = Math.max(0, Math.round(startPositionMs));
      const sameSource = activePlaybackUrlRef.current === url;

      if (sameSource && webAudioRef.current) {
        if (isPlaying) {
          webAudioRef.current.pause?.();
          setIsPlaying(false);
        } else {
          await webAudioRef.current.play?.();
          setIsPlaying(true);
        }
        return;
      }

      if (sameSource && mixSoundRef.current) {
        if (isPlaying) {
          await mixSoundRef.current.pauseAsync();
          setIsPlaying(false);
        } else {
          await mixSoundRef.current.playAsync();
          setIsPlaying(true);
        }
        return;
      }

      const previousWebAudio = webAudioRef.current;
      webAudioRef.current = null;
      previousWebAudio?.pause?.();
      revokeObjectUrl(webAudioObjectUrlRef.current);
      webAudioObjectUrlRef.current = null;
      await voiceSoundRef.current?.unloadAsync().catch(() => undefined);
      const previousMixSound = mixSoundRef.current;
      voiceSoundRef.current = null;
      mixSoundRef.current = null;
      await previousMixSound?.unloadAsync().catch(() => undefined);
      setPlayingVoiceTakeId(null);
      activePlaybackUrlRef.current = null;
      setActivePlaybackUrl(null);

      if (Platform.OS === "web") {
        const AudioElement = (globalThis as any).Audio;
        if (!AudioElement) throw new Error("Browser audio is not available");
        const playable = await prepareWebAudioSource(url);
        const audio = new AudioElement(playable.uri);
        audio.preload = "auto";
        audio.onloadedmetadata = () => {
          if (Number.isFinite(audio.duration)) {
            const durationMs = audio.duration * 1000;
            const safePositionMs = Math.min(requestedPositionMs, Math.max(0, durationMs - 50));
            audio.currentTime = safePositionMs / 1000;
            setMixDurationMs(durationMs);
            setMixPositionMs(safePositionMs);
          }
        };
        audio.ontimeupdate = () => {
          if (Number.isFinite(audio.currentTime)) setMixPositionMs(audio.currentTime * 1000);
        };
        audio.onended = () => {
          if (webAudioRef.current === audio) {
            webAudioRef.current = null;
            activePlaybackUrlRef.current = null;
            setActivePlaybackUrl(null);
            setIsPlaying(false);
          }
          if (playable.revokeAfterUse) revokeObjectUrl(playable.uri);
          if (webAudioObjectUrlRef.current === playable.uri) webAudioObjectUrlRef.current = null;
          if (Number.isFinite(audio.duration)) setMixPositionMs(audio.duration * 1000);
        };
        audio.onerror = () => {
          if (webAudioRef.current === audio) {
            webAudioRef.current = null;
            activePlaybackUrlRef.current = null;
            setActivePlaybackUrl(null);
            setIsPlaying(false);
          }
          if (playable.revokeAfterUse) revokeObjectUrl(playable.uri);
          if (webAudioObjectUrlRef.current === playable.uri) webAudioObjectUrlRef.current = null;
          showToast("Browser could not decode this MP3");
        };
        webAudioObjectUrlRef.current = playable.revokeAfterUse ? playable.uri : null;
        webAudioRef.current = audio;
        activePlaybackUrlRef.current = url;
        setActivePlaybackUrl(url);
        setMixPositionMs(requestedPositionMs);
        setIsPlaying(true);
        await audio.play();
        return;
      }

      const { sound } = await Audio.Sound.createAsync(
        { uri: url },
        { shouldPlay: true, positionMillis: requestedPositionMs }
      );
      mixSoundRef.current = sound;
      activePlaybackUrlRef.current = url;
      setActivePlaybackUrl(url);
      setMixPositionMs(requestedPositionMs);
      setIsPlaying(true);
      sound.setOnPlaybackStatusUpdate((status) => {
        if ("isLoaded" in status && status.isLoaded) {
          setMixPositionMs(status.positionMillis ?? 0);
          if (status.durationMillis) setMixDurationMs(status.durationMillis);
        }
        if ("didJustFinish" in status && status.didJustFinish) {
          if (mixSoundRef.current === sound) {
            mixSoundRef.current = null;
            activePlaybackUrlRef.current = null;
            setActivePlaybackUrl(null);
            setIsPlaying(false);
            void sound.unloadAsync();
          }
        }
      });
    } catch (error) {
      webAudioRef.current?.pause?.();
      webAudioRef.current = null;
      revokeObjectUrl(webAudioObjectUrlRef.current);
      webAudioObjectUrlRef.current = null;
      await mixSoundRef.current?.unloadAsync().catch(() => undefined);
      mixSoundRef.current = null;
      activePlaybackUrlRef.current = null;
      setActivePlaybackUrl(null);
      setIsPlaying(false);
      setMixPositionMs(0);
      showToast(`Could not play MP3: ${errorMessage(error)}`);
    }
  }, [isPlaying, showToast]);

  const playGeneratedMix = useCallback(async () => {
    if (!backendFinalUrl) {
      showToast("Final MP3 is not ready yet");
      return;
    }
    const synchronizedPositionMs = mixPositionMs > 0 && (!mixDurationMs || mixPositionMs < mixDurationMs - 250)
      ? mixPositionMs
      : 0;
    await playUrl(backendFinalUrl, synchronizedPositionMs);
  }, [backendFinalUrl, mixDurationMs, mixPositionMs, playUrl, showToast]);

  const selectSkarlyVersion = useCallback(async (index: number) => {
    if (!skarlyResult) return;
    applySelectedSkarlyVersion(skarlyResult, index, true);
    if (!isPlaying || index === selectedSkarlyVersionIndex) return;
    const nextUrl = backendMediaUrl(skarlyResult.versions[index]?.final_mix_url);
    if (!nextUrl) return;
    const synchronizedPositionMs = mixPositionMs > 0 && (!mixDurationMs || mixPositionMs < mixDurationMs - 250)
      ? mixPositionMs
      : 0;
    await playUrl(nextUrl, synchronizedPositionMs);
  }, [applySelectedSkarlyVersion, isPlaying, mixDurationMs, mixPositionMs, playUrl, selectedSkarlyVersionIndex, skarlyResult]);

  const persistSelectedSkarlyVersion = useCallback(async (index: number) => {
    if (!skarlyResult) throw new Error("No Skarly version is ready to save");
    const response = await backendApi.selectSkarlyVersion(creatorMode, firebaseUser, skarlyResult.job_id, index);
    applyBackendDemoResponse(response);
    await refreshBackendHistory();
    return response;
  }, [applyBackendDemoResponse, creatorMode, firebaseUser, refreshBackendHistory, skarlyResult]);

  const submitSkarlyFeedback = useCallback(async (index: number, rating: number) => {
    if (!skarlyGenerationV2Id || !skarlyResult) return;
    const selected = skarlyResult.versions[index];
    try {
      await backendApi.saveSkarlyV2Feedback(creatorMode, firebaseUser, {
        generation_id: skarlyGenerationV2Id,
        selected_arrangement: index,
        corrected_genre: generationIntent.genreOverride || skarlyResult.detected.genre_hint || selected?.style_family,
        corrected_language: generationIntent.language || skarlyResult.detected.language,
        mix_preference: skarlyMixPresetValue(generationIntent.mixPreset),
        user_rating: rating,
        explicit_training_consent: generationIntent.trainingOptIn,
        dataset_usage_permission_version: generationIntent.trainingOptIn ? "skarly-creator-terms-2026-07" : undefined,
        rights_confirmed: generationIntent.trainingOptIn,
        copyright_owner: generationIntent.trainingOptIn ? creatorProfile.name : undefined,
        commercial_use_permission: false,
        revocation_policy: generationIntent.trainingOptIn ? "Remove from future dataset versions on creator request." : undefined,
        singer_id: generationIntent.trainingOptIn ? (firebaseUser?.uid || creatorProfile.name) : undefined,
        recording_conditions: generationIntent.trainingOptIn ? inputSource.detail : undefined,
        confirmed_singing_speech: generationIntent.trainingOptIn ? generationIntent.trainingSingingSpeech : undefined,
        confirmed_vocal_techniques: generationIntent.trainingOptIn ? generationIntent.trainingVocalTechniques : [],
        confirmed_moods: generationIntent.trainingOptIn ? skarlyTrainingMoodLabels(generationIntent.moodTags || skarlyResult.detected.mood) : [],
        confirmed_tempo_family: generationIntent.trainingOptIn ? generationIntent.trainingTempoFamily : undefined,
        confirmed_melodic_character: generationIntent.trainingOptIn ? generationIntent.trainingMelodicCharacter : undefined,
        confirmed_in_distribution: generationIntent.trainingOptIn ? true : undefined
      });
      showToast(rating >= 4 ? "Producer preference saved" : "Feedback saved for this arrangement");
    } catch (error) {
      showToast(`Feedback could not be saved: ${errorMessage(error)}`);
    }
  }, [creatorMode, creatorProfile.name, firebaseUser, generationIntent, inputSource.detail, showToast, skarlyGenerationV2Id, skarlyResult]);

  const remixSkarlyVersion = useCallback(async (index: number) => {
    if (!skarlyGenerationV2Id || !skarlyResult) return;
    setSkarlyRemixBusy(true);
    try {
      const queued = await backendApi.remixSkarlyV2(
        creatorMode,
        firebaseUser,
        skarlyGenerationV2Id,
        index,
        generationIntent.mixPreset,
        vocalMusicBalance
      );
      const completed = await pollSkarlyV2Job(creatorMode, firebaseUser, queued.job_id, setSkarlyV2Job, 3 * 60 * 1000);
      const finalMixUrl = String(completed.result?.final_mix_url || "");
      if (!finalMixUrl) throw new Error("The remix completed without an output URL");
      const updated: SkarlyGenerateResponse = {
        ...skarlyResult,
        versions: skarlyResult.versions.map((version, versionIndex) => versionIndex === index ? {
          ...version,
          final_mix_url: finalMixUrl,
          mix_note: String(completed.result?.mix_note || "Adaptive remix ready")
        } : version)
      };
      setSkarlyResult(updated);
      applySelectedSkarlyVersion(updated, index);
      showToast("Mix balance updated without regenerating the music");
    } catch (error) {
      showToast(`Remix failed: ${errorMessage(error)}`);
    } finally {
      setSkarlyRemixBusy(false);
    }
  }, [applySelectedSkarlyVersion, creatorMode, firebaseUser, generationIntent.mixPreset, showToast, skarlyGenerationV2Id, skarlyResult, vocalMusicBalance]);

  const regenerateSkarlyVersion = useCallback(async (index: number, energyDelta = 0, instrumentChange?: string) => {
    if (!skarlyGenerationV2Id || !skarlyResult) return;
    setSkarlyRegenerationBusy(true);
    try {
      const queued = await backendApi.regenerateSkarlyV2(
        creatorMode,
        firebaseUser,
        skarlyGenerationV2Id,
        index,
        energyDelta,
        instrumentChange
      );
      setSkarlyV2Job(queued);
      const completed = await pollSkarlyV2Job(creatorMode, firebaseUser, queued.job_id, setSkarlyV2Job, 15 * 60 * 1000);
      const updated = completed.result?.updated_generation as unknown as SkarlyGenerateResponse | undefined;
      if (!updated?.versions || updated.versions.length !== 5) throw new Error("Regeneration completed without the updated five-version set");
      setSkarlyResult(updated);
      applySelectedSkarlyVersion(updated, index);
      setSkarlyExportResult(null);
      showToast(`Producer ${index + 1} regenerated; the other four versions were preserved`);
    } catch (error) {
      showToast(`Producer regeneration failed: ${errorMessage(error)}`);
    } finally {
      setSkarlyRegenerationBusy(false);
    }
  }, [applySelectedSkarlyVersion, creatorMode, firebaseUser, showToast, skarlyGenerationV2Id, skarlyResult]);

  const regenerateSkarlySection = useCallback(async (index: number, sectionStartSeconds: number, sectionEndSeconds: number, editInstruction: string) => {
    if (!skarlyGenerationV2Id || !skarlyResult) return;
    setSkarlySectionBusy(true);
    try {
      const queued = await backendApi.regenerateSkarlyV2Section(
        creatorMode,
        firebaseUser,
        skarlyGenerationV2Id,
        index,
        sectionStartSeconds,
        sectionEndSeconds,
        editInstruction
      );
      setSkarlyV2Job(queued);
      const completed = await pollSkarlyV2Job(creatorMode, firebaseUser, queued.job_id, setSkarlyV2Job, 15 * 60 * 1000);
      const updated = completed.result?.updated_generation as unknown as SkarlyGenerateResponse | undefined;
      if (!updated?.versions || updated.versions.length !== 5) throw new Error("Section regeneration completed without the updated five-version set");
      if (completed.result?.preserved_outside_section !== true) throw new Error("Section preservation verification was not returned");
      setSkarlyResult(updated);
      applySelectedSkarlyVersion(updated, index);
      setSkarlyExportResult(null);
      showToast(`Selected section regenerated; the rest of producer ${index + 1} and the original vocal were preserved`);
    } catch (error) {
      showToast(`Section regeneration failed: ${errorMessage(error)}`);
    } finally {
      setSkarlySectionBusy(false);
    }
  }, [applySelectedSkarlyVersion, creatorMode, firebaseUser, showToast, skarlyGenerationV2Id, skarlyResult]);

  const exportSkarlyVersion = useCallback(async (index: number) => {
    if (!skarlyGenerationV2Id || !skarlyResult) return;
    setSkarlyExportBusy(true);
    try {
      const exported = await backendApi.exportSkarlyV2(creatorMode, firebaseUser, skarlyGenerationV2Id, index);
      setSkarlyExportResult(exported);
      const bundleUrl = backendMediaUrl(exported.files.bundle_zip);
      if (!bundleUrl) throw new Error("The studio export completed without a bundle URL");
      await downloadUrlToLocalFile(bundleUrl, `${cleanFileStem(exported.arrangement_name)}-skarly-studio.zip`);
      setHasDownloaded(true);
      const stemNote = exported.warnings.length ? " Core files are ready; optional separated stems were unavailable." : "";
      showToast(`Studio export downloaded: WAV, MP3, instrumental, vocal, song map, and metadata.${stemNote}`);
    } catch (error) {
      showToast(`Studio export failed: ${errorMessage(error)}`);
    } finally {
      setSkarlyExportBusy(false);
    }
  }, [creatorMode, firebaseUser, showToast, skarlyGenerationV2Id, skarlyResult]);

  const chooseBestSkarlyVersion = useCallback(async (index: number) => {
    if (!skarlyResult) return;
    applySelectedSkarlyVersion(skarlyResult, index, true);
    // Preference feedback belongs to the V2 generation and must not depend on
    // the legacy library-save endpoint succeeding.
    await submitSkarlyFeedback(index, 5);
    try {
      await persistSelectedSkarlyVersion(index);
      const family = skarlyResult.versions[index]?.style_family?.replace(/_/g, " ") ?? "this producer style";
      showToast(`${family} saved as your preference for future Skarly versions`);
    } catch (error) {
      showToast(`Best version selected locally: ${errorMessage(error)}`);
    }
  }, [applySelectedSkarlyVersion, persistSelectedSkarlyVersion, showToast, skarlyResult, submitSkarlyFeedback]);

  const playSkarlyVersion = useCallback(async (index: number, kind: "final" | "backing" | "vocal" = "final") => {
    if (!skarlyResult) return;
    const version = skarlyResult.versions[index];
    if (!version) return;
    applySelectedSkarlyVersion(skarlyResult, index);
    const url = backendMediaUrl(kind === "backing" ? version.backing_url : kind === "vocal" ? (version.input_vocal_url ?? skarlyResult.vocal_url) : version.final_mix_url);
    if (!url) {
      showToast(`${kind === "backing" ? "Backing" : kind === "vocal" ? "Vocal" : "Final mix"} is not ready`);
      return;
    }
    const synchronizedPositionMs = mixPositionMs > 0 && (!mixDurationMs || mixPositionMs < mixDurationMs - 250)
      ? mixPositionMs
      : 0;
    await playUrl(url, synchronizedPositionMs);
  }, [applySelectedSkarlyVersion, mixDurationMs, mixPositionMs, playUrl, showToast, skarlyResult]);

  const uploadVoiceTake = useCallback(async (take: VoiceTake) => {
    let uploadCandidate = take;
    if (take.rawAudioPath && USE_BACKEND_API) {
      try {
        const verification = await backendApi.verifyUpload(creatorMode, firebaseUser, take.rawAudioPath);
        if (verification.exists) {
          const verifiedTake = { ...take, uploaded: true, uploadState: undefined, uploadError: undefined };
          setVoiceTakes((current) => current.map((item) => item.id === take.id ? verifiedTake : item));
          return verifiedTake;
        }
      } catch (error) {
        if (isMissingVerifyRouteError(error)) {
          return take;
        }
        if (!take.fileUri) {
          const message = errorMessage(error);
          const failedTake: VoiceTake = { ...take, uploaded: false, uploadState: "failed", uploadError: message };
          setVoiceTakes((current) => current.map((item) => item.id === take.id ? failedTake : item));
          showToast(`Cloud voice take unavailable: ${message}`);
          return failedTake;
        }
      }

      if (!take.fileUri) {
        const failedTake: VoiceTake = {
          ...take,
          uploaded: false,
          uploadState: "failed",
          uploadError: "Cloud copy is missing. Record a new take or upload the file again."
        };
        setVoiceTakes((current) => current.map((item) => item.id === take.id ? failedTake : item));
        showToast("Cloud copy is missing. Choose another take or record again.");
        return failedTake;
      }

      uploadCandidate = { ...take, rawAudioPath: undefined, uploadUrl: undefined, uploaded: false };
    }
    if (uploadCandidate.uploaded && uploadCandidate.rawAudioPath) return uploadCandidate;
    if (!uploadCandidate.fileUri) {
      showToast("No local recording file to upload");
      return uploadCandidate;
    }
    if (!USE_BACKEND_API) return uploadCandidate;

    let conversionTake = uploadCandidate;
    const baseSource: InputSource = {
      kind: "recording",
      label: uploadCandidate.title,
      detail: `${uploadCandidate.duration}s recorded vocal`,
      arrangementMode: "vocal_to_song",
      fileUri: uploadCandidate.fileUri,
      contentType: uploadCandidate.contentType ?? "audio/m4a",
      sizeBytes: uploadCandidate.sizeBytes,
      rawAudioPath: uploadCandidate.rawAudioPath,
      uploadUrl: uploadCandidate.uploadUrl,
      uploaded: uploadCandidate.uploaded
    };

    try {
      showToast("Uploading voice take");
      setVoiceTakes((current) => current.map((item) => item.id === uploadCandidate.id ? { ...item, uploadState: "uploading", uploadError: undefined } : item));
      const extension = baseSource.contentType?.includes("webm") ? "webm" : baseSource.contentType?.includes("wav") ? "wav" : "m4a";
      const signed = await backendApi.signUpload(creatorMode, firebaseUser, { ...baseSource, label: `${uploadCandidate.title}.${extension}` });
      await uploadFileToCloud(uploadCandidate.fileUri, signed, baseSource.contentType ?? "audio/m4a", creatorMode, firebaseUser);
      conversionTake = {
        ...uploadCandidate,
        uploadId: signed.upload_id,
        rawAudioPath: signed.raw_audio_path,
        uploadUrl: signed.upload_url,
        uploaded: true,
        uploadState: undefined,
        uploadError: undefined
      };
      if (creatorMode === "saved") {
        try {
          const saved = await backendApi.saveVoiceTake(creatorMode, firebaseUser, conversionTake);
          conversionTake = {
            ...mapBackendVoiceTake(saved.take),
            uploadId: signed.upload_id,
            fileUri: uploadCandidate.fileUri,
            uploadUrl: signed.upload_url
          };
        } catch {
          showToast("Voice uploaded. Library save will retry later.");
        }
      }
      setVoiceTakes((current) => current.map((item) => item.id === uploadCandidate.id ? conversionTake : item));
      setBackendMode("api");
      setBackendMessage(BACKEND_CONNECTED_MESSAGE);
      showToast("Voice take uploaded to Cloud Storage");
    } catch (error) {
      const message = errorMessage(error);
      setVoiceTakes((current) => current.map((item) => item.id === uploadCandidate.id ? { ...item, uploadState: "failed", uploadError: message } : item));
      setBackendMode("offline");
      setBackendMessage(message);
      showToast(`Recording kept local: ${message}`);
    }

    return conversionTake;
  }, [creatorMode, firebaseUser, showToast]);

  useEffect(() => {
    if (creatorMode !== "saved" || !firebaseUser || !USE_BACKEND_API) return;
    const pendingTake = voiceTakes.find((take) =>
      take.fileUri &&
      !take.uploaded &&
      !take.rawAudioPath &&
      !take.uploadState &&
      !uploadingVoiceTakeIds.includes(take.id)
    );
    if (!pendingTake) return;

    setUploadingVoiceTakeIds((current) => [...current, pendingTake.id]);
    uploadVoiceTake(pendingTake).finally(() => {
      setUploadingVoiceTakeIds((current) => current.filter((id) => id !== pendingTake.id));
    });
  }, [creatorMode, firebaseUser, uploadVoiceTake, uploadingVoiceTakeIds, voiceTakes]);

  const useVoiceTakeForConversion = useCallback(async (take: VoiceTake) => {
    const conversionTake = await uploadVoiceTake(take);
    if (USE_BACKEND_API && (!conversionTake.rawAudioPath || !conversionTake.uploaded)) {
      showToast("Upload the voice take before generating");
      return;
    }
    const baseSource: InputSource = {
      kind: "recording",
      label: take.title,
      detail: `${take.duration}s recorded vocal`,
      arrangementMode: "vocal_to_song",
      contentType: take.contentType ?? "audio/m4a",
      sizeBytes: take.sizeBytes
    };

    clearSkarlySession();
    setInputSource({
      ...baseSource,
      uploadId: conversionTake.uploadId,
      fileUri: conversionTake.fileUri,
      rawAudioPath: conversionTake.rawAudioPath,
      uploadUrl: conversionTake.uploadUrl,
      uploaded: conversionTake.uploaded
    });
    showToast(conversionTake.uploaded ? "Voice take ready for conversion" : "Voice take ready locally");
    setScreen("genre");
  }, [clearSkarlySession, showToast, uploadVoiceTake]);

  const deleteVoiceTake = useCallback((takeId: string) => {
    const take = voiceTakes.find((item) => item.id === takeId);
    setVoiceTakes((current) => current.filter((item) => item.id !== takeId));
    if (take) setRecycleVoiceTakes((current) => [take, ...current.filter((item) => item.id !== take.id)]);
    if (creatorMode === "saved" && take?.uploaded) {
      backendApi.deleteVoiceTake(creatorMode, firebaseUser, takeId).then(() => {
        refreshRecycleBin();
      }).catch(() => {
        showToast("Removed locally. Cloud voice take delete will retry later.");
      });
    }
    showToast("Moved to Recently Deleted");
  }, [creatorMode, firebaseUser, refreshRecycleBin, showToast, voiceTakes]);

  const restoreVoiceTake = useCallback((take: VoiceTake) => {
    setRecycleVoiceTakes((current) => current.filter((item) => item.id !== take.id));
    setVoiceTakes((current) => [take, ...current.filter((item) => item.id !== take.id)]);
    if (creatorMode === "saved" && take.uploaded) {
      backendApi.restoreVoiceTake(creatorMode, firebaseUser, take.id).then(() => {
        refreshBackendVoiceTakes();
        refreshRecycleBin();
      }).catch(() => showToast("Restored locally. Cloud restore will retry later."));
    }
    showToast("Restored voice take");
  }, [creatorMode, firebaseUser, refreshBackendVoiceTakes, refreshRecycleBin, showToast]);

  const permanentlyDeleteVoiceTake = useCallback((take: VoiceTake) => {
    if (!confirmPermanentDelete(take.title)) return;
    setRecycleVoiceTakes((current) => current.filter((item) => item.id !== take.id));
    if (creatorMode === "saved" && take.uploaded) {
      backendApi.permanentlyDeleteVoiceTake(creatorMode, firebaseUser, take.id).then(() => {
        refreshRecycleBin();
      }).catch(() => showToast("Could not permanently delete cloud voice take"));
    }
    showToast("Permanently deleted voice take");
  }, [creatorMode, firebaseUser, refreshRecycleBin, showToast]);

  const restoreGeneratedTrack = useCallback((track: GeneratedTrackView) => {
    setDeletedGeneratedTracks((current) => current.filter((item) => item.id !== track.id));
    setGeneratedTracks((current) => [track, ...current.filter((item) => item.id !== track.id)]);
    showToast("Restored track");
  }, [showToast]);

  const restoreBackendTrack = useCallback((jobId: string) => {
    setDeletedBackendTrackIds((current) => current.filter((id) => id !== jobId));
    backendApi.restoreTrack(creatorMode, firebaseUser, jobId).then(() => {
      refreshBackendHistory();
      refreshRecycleBin();
      showToast("Restored track");
    }).catch(() => showToast("Could not restore cloud track"));
  }, [creatorMode, firebaseUser, refreshBackendHistory, refreshRecycleBin, showToast]);

  const permanentlyDeleteGeneratedTrack = useCallback((trackId: string) => {
    const track = deletedGeneratedTracks.find((item) => item.id === trackId);
    if (!confirmPermanentDelete(track?.title ?? "this track")) return;
    setDeletedGeneratedTracks((current) => current.filter((track) => track.id !== trackId));
    showToast("Permanently deleted track");
  }, [deletedGeneratedTracks, showToast]);

  const permanentlyDeleteBackendTrack = useCallback((jobId: string) => {
    const track = recycleTracks.find((item) => item.job_id === jobId);
    if (!confirmPermanentDelete(track?.track_name ?? "this track")) return;
    setRecycleTracks((current) => current.filter((track) => track.job_id !== jobId));
    backendApi.permanentlyDeleteTrack(creatorMode, firebaseUser, jobId).then(() => {
      refreshRecycleBin();
      showToast("Permanently deleted track");
    }).catch(() => showToast("Could not permanently delete cloud track"));
  }, [creatorMode, firebaseUser, recycleTracks, refreshRecycleBin, showToast]);

  useEffect(() => {
    if (!generationActive) return;
    if (USE_BACKEND_API) return;
    setProcessingIndex(0);
    const timer = setInterval(() => {
      setProcessingIndex((current) => {
        if (current >= processingSteps.length - 1) {
          clearInterval(timer);
          setGenerationActive(false);
          setTimeout(() => setScreen("nameTrack"), 700);
          return current;
        }
        return current + 1;
      });
    }, 850);
    return () => clearInterval(timer);
  }, [generationActive, backendJobId]);

  useEffect(() => {
    if (!generationActive || !USE_BACKEND_API || !backendJobId) return;
    let cancelled = false;
    let completed = false;
    setProcessingIndex(0);

    const pollBackendJob = async () => {
      if (completed) return;
      try {
        const result = await backendApi.getJob(creatorMode, firebaseUser, backendJobId);
        if (cancelled) return;
        if (result.job.status === "failed") {
          const message = result.job.error ? `Generation failed: ${result.job.error}` : "Generation failed before creating the MP3.";
          setGenerationActive(false);
          setBackendJobId(null);
          setBackendMode("api");
          setBackendMessage(message);
          setGenerationError(message);
          showToast("Generation needs attention");
          if (result.job.track_name === BACKEND_PLACEHOLDER_TRACK) {
            backendApi.permanentlyDeleteTrack(creatorMode, firebaseUser, backendJobId).catch(() => undefined);
          }
          return;
        }
        if (result.job.status !== "ready") {
          setProcessingIndex(mapBackendStageToIndex(result.job.stage));
          setBackendMode("api");
          setBackendMessage(BACKEND_CONNECTED_MESSAGE);
          return;
        }
        completed = true;
        setProcessingIndex(mapBackendStageToIndex(result.job.stage));
        applyBackendDemoResponse(result);
        setBackendMode("api");
        setBackendMessage(BACKEND_CONNECTED_MESSAGE);
        setGenerationError(null);
        setTimeout(() => {
          if (!cancelled) {
            setGenerationActive(false);
            setScreen("nameTrack");
          }
        }, 650);
      } catch {
        if (cancelled) return;
        const failedJobId = backendJobId;
        setGenerationActive(false);
        setBackendJobId(null);
        setProcessingIndex(0);
        setBackendMode("offline");
        setBackendMessage("Generation stopped because FastAPI is offline.");
        setGenerationError("Backend connection stopped while generating. Keep FastAPI running and retry.");
        showToast("Generation paused. Retry when backend is ready.");
        backendApi.permanentlyDeleteTrack(creatorMode, firebaseUser, failedJobId).catch(() => undefined);
      }
    };

    pollBackendJob();
    const timer = setInterval(pollBackendJob, 1200);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [applyBackendDemoResponse, backendJobId, creatorMode, firebaseUser, generationActive, showToast]);

  useEffect(() => {
    if (screen !== "history" || !USE_BACKEND_API) return;
    refreshBackendHistory();
    refreshBackendVoiceTakes();
  }, [refreshBackendHistory, refreshBackendVoiceTakes, screen]);

  useEffect(() => {
    if (screen !== "nameSuccess") return;
    const timer = setTimeout(() => setScreen("result"), 650);
    return () => clearTimeout(timer);
  }, [screen]);

  useEffect(() => {
    if (!toastMessage) return;
    const timer = setTimeout(() => setToastMessage(""), 1800);
    return () => clearTimeout(timer);
  }, [toastMessage]);

  const currentGeneratedTrack: GeneratedTrackView | null = trackName.trim().length > 0 ? {
    id: backendJobId ?? currentGeneratedTrackId ?? `local-preview-${trackName.trim().toLowerCase().replace(/\s+/g, "-")}`,
    title: buildTrackTitle(trackName, selectedGenre, fileNameMode),
    meta: `${selectedGenre.label} | ${getSourceLabel(inputSource)}`,
    status: getGeneratedTrackStatus(creatorMode, hasSaved, hasDownloaded, hasShared)
  } : null;

  const rememberCurrentGeneration = useCallback((status?: TrackStatus) => {
    if (!currentGeneratedTrack) return;
    const rememberedTrack = { ...currentGeneratedTrack, status: status ?? currentGeneratedTrack.status };
    setGeneratedTracks((current) => {
      const withoutSameTrack = current.filter((track) => track.id !== rememberedTrack.id);
      return [rememberedTrack, ...withoutSameTrack];
    });
    if (skarlyResult && status) {
      const index = Math.max(0, Math.min(selectedSkarlyVersionIndex, skarlyResult.versions.length - 1));
      persistSelectedSkarlyVersion(index).then((response) => {
        return backendApi.updateJobLibrary(creatorMode, firebaseUser, response.job.job_id, rememberedTrack.title, status);
      }).then((response) => {
        applyBackendDemoResponse(response);
        refreshBackendHistory();
      }).catch(() => {
        showToast("Saved locally. Cloud history will retry later.");
      });
    } else if (backendJobId && status) {
      backendApi.updateJobLibrary(creatorMode, firebaseUser, backendJobId, rememberedTrack.title, status).then((response) => {
        applyBackendDemoResponse(response);
        refreshBackendHistory();
      }).catch(() => {
        showToast("Saved locally. Cloud history will retry later.");
      });
    }
  }, [applyBackendDemoResponse, backendJobId, creatorMode, currentGeneratedTrack, firebaseUser, persistSelectedSkarlyVersion, refreshBackendHistory, selectedSkarlyVersionIndex, showToast, skarlyResult]);

  const rememberGeneratedTrack = useCallback((track: GeneratedTrackView) => {
    setGeneratedTracks((current) => {
      const withoutSameTrack = current.filter((item) => item.id !== track.id);
      return [track, ...withoutSameTrack];
    });
  }, []);

  const updateGeneratedTrackStatus = useCallback((title: string, status: TrackStatus) => {
    setGeneratedTracks((current) => current.map((track) => track.title === title ? { ...track, status } : track));
  }, []);

  const updateBackendTrackStatus = useCallback((jobId: string, status: TrackStatus) => {
    backendApi.updateJobLibrary(creatorMode, firebaseUser, jobId, undefined, status).then(() => {
      refreshBackendHistory();
      showToast(`${status} in cloud history`);
    }).catch(() => {
      showToast("Updated locally. Cloud history will retry later.");
    });
  }, [creatorMode, firebaseUser, refreshBackendHistory, showToast]);

  const playBackendTrack = useCallback(async (jobId: string) => {
    try {
      const response = await backendApi.getJob(creatorMode, firebaseUser, jobId);
      if (!response.final_mp3_url) {
        showToast("Final MP3 is not ready");
        return;
      }
      applyBackendDemoResponse(response);
      await playUrl(response.final_mp3_url);
    } catch (error) {
      showToast(`Could not play track: ${errorMessage(error)}`);
    }
  }, [applyBackendDemoResponse, creatorMode, firebaseUser, playUrl, showToast]);

  const downloadBackendTrack = useCallback(async (jobId: string) => {
    try {
      const response = await backendApi.getJob(creatorMode, firebaseUser, jobId);
      const url = response.final_mp3_download_url ?? response.final_mp3_url;
      if (!url) {
        showToast("Final MP3 is not ready");
        return;
      }
      const fileName = buildFileName(response.job.track_name || "Skarly Mix", genreFromLabel(response.job.genre) ?? selectedGenre, "keep");
      await downloadUrlToLocalFile(url, fileName);
      await backendApi.updateJobLibrary(creatorMode, firebaseUser, jobId, undefined, "Downloaded");
      refreshBackendHistory();
      showToast("Download saved locally");
    } catch (error) {
      showToast(`Download failed: ${errorMessage(error)}`);
    }
  }, [creatorMode, firebaseUser, refreshBackendHistory, selectedGenre, showToast]);

  const finishNamingTrack = useCallback(() => {
    const cleanName = trackName.trim();
    if (!cleanName) return;
    const id = backendJobId ?? currentGeneratedTrackId ?? `local-${Date.now()}-${Math.round(Math.random() * 100000)}`;
    setCurrentGeneratedTrackId(id);
    rememberGeneratedTrack({
      id,
      title: buildTrackTitle(cleanName, selectedGenre, fileNameMode),
      meta: `${selectedGenre.label} | ${getSourceLabel(inputSource)}`,
      status: getGeneratedTrackStatus(creatorMode, hasSaved, hasDownloaded, hasShared)
    });
    if (backendJobId) {
      backendApi.updateJobLibrary(creatorMode, firebaseUser, backendJobId, buildTrackTitle(cleanName, selectedGenre, fileNameMode), "Ready").then((response) => {
        applyBackendDemoResponse(response);
        refreshBackendHistory();
      }).catch(() => {
        showToast("Named locally. Cloud history will retry later.");
      });
    }
    setScreen("nameSuccess");
  }, [applyBackendDemoResponse, backendJobId, creatorMode, currentGeneratedTrackId, fileNameMode, firebaseUser, hasDownloaded, hasSaved, hasShared, inputSource, refreshBackendHistory, rememberGeneratedTrack, selectedGenre, showToast, trackName]);

  const ensureSkarlySourceUploaded = useCallback(async () => {
    if (!USE_BACKEND_API) {
      showToast("Start FastAPI to run the Skarly studio pipeline");
      return null;
    }
    if (!inputSource.rawAudioPath || !inputSource.uploaded) {
      showToast("Audio upload must finish before Skarly can analyze it");
      return null;
    }

    let generationSource = inputSource;
    try {
      const verification = await backendApi.verifyUpload(creatorMode, firebaseUser, inputSource.rawAudioPath);
      if (!verification.exists) {
        if (!inputSource.fileUri) {
          const message = "Cloud audio file is missing. Record or upload again.";
          setBackendMode("offline");
          setBackendMessage(message);
          setGenerationError(message);
          showToast("Cloud audio is missing. Record or upload the audio again.");
          return null;
        }
        showToast("Cloud audio missing. Re-uploading now.");
        const signed = await backendApi.signUpload(creatorMode, firebaseUser, inputSource);
        await uploadFileToCloud(inputSource.fileUri, signed, inputSource.contentType ?? "audio/mpeg", creatorMode, firebaseUser);
        generationSource = {
          ...inputSource,
          uploadId: signed.upload_id,
          rawAudioPath: signed.raw_audio_path,
          uploadUrl: signed.upload_url,
          uploaded: true
        };
        setInputSource(generationSource);
      }
    } catch (error) {
      if (!isMissingVerifyRouteError(error)) throw error;
    }
    return generationSource;
  }, [creatorMode, firebaseUser, inputSource, showToast]);

  const analyzeSkarlySource = useCallback(async () => {
    try {
      const generationSource = await ensureSkarlySourceUploaded();
      if (!generationSource) return null;
      setSkarlyBusy(true);
      setGenerationError(null);
      setBackendMode("api");
      setBackendMessage("Skarly is detecting language, mood, melody, and timing.");
      const queued = await backendApi.createSkarlyV2Analysis(creatorMode, firebaseUser, generationSource);
      setSkarlyAnalysisV2Id(queued.job_id);
      setSkarlyV2Job(queued);
      const completed = await pollSkarlyV2Job(creatorMode, firebaseUser, queued.job_id, (job) => {
        setSkarlyV2Job(job);
        setBackendMessage(formatSkarlyV2Stage(job));
      });
      if (!completed.result) throw new Error("Skarly analysis completed without a Song Intelligence Map");
      const rawResponse = completed.result as unknown as SkarlyAnalyzeResponse;
      const response: SkarlyAnalyzeResponse = {
        ...rawResponse,
        detected: {
          ...rawResponse.detected,
          language: swapHindiEnglishDetection(rawResponse.detected.language)
        }
      };
      setSkarlyAnalysis(response);
      setSkarlyResult(null);
      setGenerationIntent((current) => ({
        ...current,
        // First pass is automatic; a refresh preserves the creator's confirmed choices.
        language: skarlyAnalysis ? current.language : (response.detected.language || current.language),
        moodTags: skarlyAnalysis ? current.moodTags : (response.detected.mood || current.moodTags),
        mixPreset: current.mixPreset || "vocal_forward"
      }));
      setBackendAnalysis(skarlyAnalysisToBackendAnalysis(response.detected));
      setBackendMessage(BACKEND_CONNECTED_MESSAGE);
      return { analysis: response, jobId: queued.job_id };
    } catch (error) {
      const message = `Skarly analysis failed: ${errorMessage(error)}`;
      setGenerationError(message);
      setBackendMode(backendStatus(error) ? "api" : "offline");
      setBackendMessage(errorMessage(error));
      showToast(message);
      return null;
    } finally {
      setSkarlyBusy(false);
    }
  }, [creatorMode, ensureSkarlySourceUploaded, firebaseUser, showToast, skarlyAnalysis]);

  useEffect(() => {
    if (screen !== "genre" || !USE_BACKEND_API) return;
    if (!inputSource.rawAudioPath || !inputSource.uploaded || skarlyAnalysis || skarlyBusy) return;
    void analyzeSkarlySource();
  }, [analyzeSkarlySource, inputSource.rawAudioPath, inputSource.uploaded, screen, skarlyAnalysis, skarlyBusy]);

  useEffect(() => {
    if (screen !== "producer" || producerProfiles.length) return;
    backendApi.getSkarlyProducerProfiles(creatorMode, firebaseUser).then((profiles) => {
      setProducerProfiles(profiles);
      const defaults = profiles.filter((profile) => profile.is_default).map((profile) => profile.profile_id);
      if (defaults.length === 5) setSelectedProducerProfileIds(defaults);
    }).catch((error) => {
      setGenerationError(`Producer profiles could not be loaded: ${errorMessage(error)}`);
    });
  }, [creatorMode, firebaseUser, producerProfiles.length, screen]);

  const replaceProducerProfile = useCallback((index: number, profileId: string) => {
    setSelectedProducerProfileIds((current) => {
      if (current.some((item, itemIndex) => item === profileId && itemIndex !== index)) {
        showToast("Each producer card must use a different arrangement blueprint");
        return current;
      }
      return current.map((item, itemIndex) => itemIndex === index ? profileId : item);
    });
  }, [showToast]);

  const startGeneration = useCallback(async () => {
    webAudioRef.current?.pause?.();
    webAudioRef.current = null;
    revokeObjectUrl(webAudioObjectUrlRef.current);
    webAudioObjectUrlRef.current = null;
    void mixSoundRef.current?.unloadAsync().catch(() => undefined);
    mixSoundRef.current = null;
    activePlaybackUrlRef.current = null;
    setActivePlaybackUrl(null);
    setTrackName("");
    setFileNameMode("rename");
    setIsPlaying(false);
    setHasDownloaded(false);
    setHasShared(false);
    setHasSaved(false);
    setGenerationError(null);
    setBackendJobId(null);
    setBackendFinalUrl(null);
    setBackendDownloadUrl(null);
    setBackendIsolatedVocalUrl(null);
    setBackendBackingUrl(null);
    setBackendExportUrls({});
    setBackendAnalysis(null);
    setBackendBlueprint(null);
    setSkarlyResult(null);
    setSkarlyGenerationV2Id(null);
    setSkarlyV2Job(null);
    setMixDurationMs(0);
    setMixPositionMs(0);
    setCurrentGeneratedTrackId(null);
    setProcessingIndex(0);
    setScreen("processing");

    try {
      setSkarlyBusy(true);
      const generationSource = await ensureSkarlySourceUploaded();
      if (!generationSource) {
        setSkarlyBusy(false);
        setScreen("genre");
        return;
      }
      setProcessingIndex(1);
      const analyzed = (!skarlyAnalysis || !skarlyAnalysisV2Id) ? await analyzeSkarlySource() : null;
      const analysis = analyzed?.analysis ?? skarlyAnalysis;
      const analysisId = analyzed?.jobId ?? skarlyAnalysisV2Id;
      if (!analysis || !analysisId) throw new Error("Complete the vocal analysis before generation");
      setSkarlyAnalysis(analysis);
      setBackendAnalysis(skarlyAnalysisToBackendAnalysis(analysis.detected));
      setProcessingIndex(3);
      setBackendMode("api");
      setBackendMessage("Skarly is generating 5 producer-style backing versions.");
      const decodedDuration = Number(
        analysis.song_intelligence_map?.duration_seconds ??
        analysis.detected.song_intelligence_map?.duration_seconds ??
        analysis.detected.analysis_scope_seconds ??
        0
      );
      if (!decodedDuration) throw new Error("Skarly could not verify the decoded vocal duration");
      if (selectedProducerProfileIds.length !== 5 || new Set(selectedProducerProfileIds).size !== 5) {
        throw new Error("Choose five different producer directions before generation");
      }
      const queued = await backendApi.createSkarlyV2Generation(
        creatorMode,
        firebaseUser,
        analysisId,
        decodedDuration,
        selectedProducerProfileIds,
        generationIntent,
        generationSource,
        analysis.detected
      );
      setSkarlyGenerationV2Id(queued.job_id);
      setSkarlyV2Job(queued);
      const completed = await pollSkarlyV2Job(creatorMode, firebaseUser, queued.job_id, (job) => {
        setSkarlyV2Job(job);
        setProcessingIndex(v2ProcessingStepIndex(job));
        setBackendMessage(formatSkarlyV2Stage(job));
      });
      finishSkarlyGeneration(completed);
    } catch (error) {
      const message = `Skarly generation failed: ${errorMessage(error)}`;
      setBackendMode(backendStatus(error) ? "api" : "offline");
      setBackendMessage(errorMessage(error));
      setGenerationError(message);
      setGenerationActive(false);
      showToast(message);
    } finally {
      setSkarlyBusy(false);
    }
  }, [analyzeSkarlySource, creatorMode, ensureSkarlySourceUploaded, firebaseUser, finishSkarlyGeneration, generationIntent, selectedProducerProfileIds, showToast, skarlyAnalysis, skarlyAnalysisV2Id]);

  const resumeGeneration = useCallback(async () => {
    if (!skarlyGenerationV2Id || skarlyV2Job?.status === "failed") {
      await startGeneration();
      return;
    }

    setGenerationError(null);
    setSkarlyBusy(true);
    setScreen("processing");
    setBackendMode("api");
    setBackendMessage("Reconnecting to the existing Skarly generation job.");
    try {
      const latest = await backendApi.getSkarlyV2Job(creatorMode, firebaseUser, skarlyGenerationV2Id);
      setSkarlyV2Job(latest);
      setProcessingIndex(v2ProcessingStepIndex(latest));
      setBackendMessage(formatSkarlyV2Stage(latest));
      if (latest.status === "failed") {
        throw new Error(latest.error?.message || `Skarly stopped during ${latest.stage}`);
      }
      const completed = latest.status === "ready"
        ? latest
        : await pollSkarlyV2Job(creatorMode, firebaseUser, skarlyGenerationV2Id, (job) => {
          setSkarlyV2Job(job);
          setProcessingIndex(v2ProcessingStepIndex(job));
          setBackendMessage(formatSkarlyV2Stage(job));
        });
      finishSkarlyGeneration(completed);
    } catch (error) {
      const message = `Skarly monitoring paused: ${errorMessage(error)}`;
      setBackendMode(backendStatus(error) ? "api" : "offline");
      setBackendMessage(errorMessage(error));
      setGenerationError(message);
      setGenerationActive(false);
      showToast(message);
    } finally {
      setSkarlyBusy(false);
    }
  }, [creatorMode, firebaseUser, finishSkarlyGeneration, showToast, skarlyGenerationV2Id, skarlyV2Job?.status, startGeneration]);

  useEffect(() => {
    if (screen !== "result" || !skarlyGenerationV2Id) return;
    let cancelled = false;
    void backendApi.getSkarlyV2Job(creatorMode, firebaseUser, skarlyGenerationV2Id)
      .then((latest) => {
        if (cancelled || latest.status !== "ready" || !latest.result) return;
        setSkarlyV2Job(latest);
        setSkarlyResult(latest.result as unknown as SkarlyGenerateResponse);
      })
      .catch(() => {
        // Keep the already-rendered result available when a background refresh
        // cannot reach the backend; explicit generation controls still report
        // actionable network errors.
      });
    return () => {
      cancelled = true;
    };
  }, [creatorMode, firebaseUser, screen, skarlyGenerationV2Id]);

  const content = useMemo(() => {
    const authTransitionScreens: Screen[] = ["splash", "login", "authSignIn", "authSignUp", "profile"];
    const showingAuthTransition = authBusy && authTransitionScreens.includes(screen);
    const restoringAccountWorkspace = accountRestoring && ["splash", "login", "authSignIn", "authSignUp"].includes(screen);
    const restoringSavedSession = firebaseStatus === "loading" && ["splash", "login", "authSignIn", "authSignUp"].includes(screen);

    if ((screen === "splash" && startupLoading) || restoringSavedSession || showingAuthTransition || restoringAccountWorkspace) {
      return <StartupLoadingScreen />;
    }

    switch (screen) {
      case "splash":
      case "login":
        return (
          <EntryScreen
            firebaseStatus={firebaseStatus}
            loginChoice={loginChoice}
            onChoose={(choice) => {
              setCreatorMode(choice === "guest" ? "guest" : "saved");
              setLoginChoice(choice);
            }}
            onContinue={(choice) => {
              if (firebaseUser) {
                setScreen("home");
                return;
              }
              if (choice === "guest") setScreen("setup");
              if (choice === "signin") setScreen("authSignIn");
              if (choice === "signup") setScreen("authSignUp");
            }}
          />
        );
      case "authSignIn":
        return <AuthScreen kind="signin" firebaseStatus={firebaseStatus} authBusy={authBusy} onBack={() => setScreen("login")} onContinue={(submission) => finishAuth(submission, "signin")} />;
      case "authSignUp":
        return <AuthScreen kind="signup" firebaseStatus={firebaseStatus} authBusy={authBusy} onBack={() => setScreen("login")} onContinue={(submission) => finishAuth(submission, "signup")} />;
      case "setup":
        return <CreatorSetup intent={intent} setIntent={setIntent} genre={selectedGenre} setGenre={setSelectedGenre} onNext={() => {
          setScreen("home");
        }} />;
      case "home":
        return <Home creatorMode={creatorMode} generatedTrack={currentGeneratedTrack ?? generatedTracks[0] ?? null} voiceTakes={voiceTakes} playingVoiceTakeId={playingVoiceTakeId} onPlayVoiceTake={playVoiceTake} onUseVoiceTake={useVoiceTakeForConversion} onDeleteVoiceTake={deleteVoiceTake} onShareTrack={(title) => {
          setHasShared(true);
          updateGeneratedTrackStatus(title, "Shared");
          showToast(`Shared ${title}`);
        }} onDownloadTrack={(title) => {
          setHasDownloaded(true);
          updateGeneratedTrackStatus(title, "Downloaded");
          showToast(`Downloaded ${title}`);
        }} onNavigate={setScreen} />;
      case "record":
        return <RecordVoice creatorMode={creatorMode} genre={selectedGenre} playingVoiceTakeId={playingVoiceTakeId} onNext={addVoiceTake} onUseTake={useVoiceTakeForConversion} onPlayTake={playVoiceTake} onHome={() => setScreen("home")} showToast={showToast} />;
      case "upload":
        return <UploadAudio onNext={(source) => {
          clearSkarlySession();
          setInputSource(source);
          setScreen("genre");
        }} onHome={() => setScreen("home")} creatorMode={creatorMode} firebaseUser={firebaseUser} showToast={showToast} setBackendMode={setBackendMode} setBackendMessage={setBackendMessage} />;
      case "genre":
        return <SkarlyDetectedConfirm source={inputSource} analysis={skarlyAnalysis} busy={skarlyBusy} errorMessage={generationError} onGenreSelect={setSelectedGenre} generationIntent={generationIntent} setGenerationIntent={setGenerationIntent} onBack={() => setScreen(inputSource.kind === "recording" ? "record" : "upload")} onRefresh={() => { void analyzeSkarlySource(); }} onNext={() => setScreen("producer")} />;
      case "producer":
        return <ProducerDirections profiles={producerProfiles} selectedProfileIds={selectedProducerProfileIds} analysis={skarlyAnalysis} mixPreset={generationIntent.mixPreset} busy={skarlyBusy} errorMessage={generationError} onReplace={replaceProducerProfile} onBack={() => setScreen("genre")} onGenerate={startGeneration} />;
      case "processing":
        return <Processing genre={selectedGenre} activeIndex={processingIndex} v2Job={skarlyV2Job} backendMessage={backendMessage} backendMode={backendMode} errorMessage={generationError} onRetry={resumeGeneration} onBackToGenre={() => {
          setGenerationError(null);
          setScreen("genre");
        }} onHome={() => {
          setGenerationError(null);
          setScreen("home");
        }} />;
      case "nameTrack":
        return <NameTrack genre={selectedGenre} trackName={trackName} setTrackName={setTrackName} fileNameMode={fileNameMode} setFileNameMode={setFileNameMode} onContinue={finishNamingTrack} />;
      case "nameSuccess":
        return <NameSuccess genre={selectedGenre} trackName={trackName} fileNameMode={fileNameMode} onDone={() => setScreen("result")} />;
      case "result":
        if (skarlyResult) {
          return <SkarlyVersions result={skarlyResult} selectedIndex={selectedSkarlyVersionIndex} source={inputSource} isPlaying={isPlaying} activePlaybackUrl={activePlaybackUrl} mixDurationMs={mixDurationMs} mixPositionMs={mixPositionMs} hasDownloaded={hasDownloaded} hasSaved={hasSaved} mixPreset={generationIntent.mixPreset} vocalMusicBalance={vocalMusicBalance} remixBusy={skarlyRemixBusy} regenerationBusy={skarlyRegenerationBusy} sectionBusy={skarlySectionBusy} exportBusy={skarlyExportBusy} setVocalMusicBalance={setVocalMusicBalance} setHasDownloaded={setHasDownloaded} setHasSaved={setHasSaved} showToast={showToast} onSelect={selectSkarlyVersion} onChooseBest={chooseBestSkarlyVersion} onPlayVersion={playSkarlyVersion} onRemix={remixSkarlyVersion} onRegenerate={regenerateSkarlyVersion} onRegenerateSection={regenerateSkarlySection} onExport={exportSkarlyVersion} onFeedback={submitSkarlyFeedback} onRemember={rememberCurrentGeneration} onDelete={deleteCurrentGeneration} onNavigate={setScreen} />;
        }
        return <ResultPlayer creatorMode={creatorMode} genre={selectedGenre} source={inputSource} backendFinalUrl={backendFinalUrl} backendDownloadUrl={backendDownloadUrl} exportUrls={backendExportUrls} analysis={backendAnalysis} blueprint={backendBlueprint} trackName={trackName} fileNameMode={fileNameMode} isPlaying={isPlaying} mixDurationMs={mixDurationMs} mixPositionMs={mixPositionMs} hasDownloaded={hasDownloaded} hasShared={hasShared} hasSaved={hasSaved} setHasDownloaded={setHasDownloaded} setHasShared={setHasShared} setHasSaved={setHasSaved} showToast={showToast} onRemember={rememberCurrentGeneration} onDelete={deleteCurrentGeneration} onNavigate={setScreen} onPlayMix={playGeneratedMix} />;
      case "download":
        if (skarlyResult) {
          return <SkarlyExportStudio result={skarlyResult} selectedIndex={selectedSkarlyVersionIndex} exported={skarlyExportResult} exportBusy={skarlyExportBusy} onExport={exportSkarlyVersion} onBack={() => setScreen("result")} onHome={() => setScreen("home")} showToast={showToast} />;
        }
        return <DownloadShare creatorMode={creatorMode} genre={selectedGenre} backendFinalUrl={backendFinalUrl} backendDownloadUrl={backendDownloadUrl} backendIsolatedVocalUrl={backendIsolatedVocalUrl} backendBackingUrl={backendBackingUrl} exportUrls={backendExportUrls} analysis={backendAnalysis} blueprint={backendBlueprint} trackName={trackName} fileNameMode={fileNameMode} isPlaying={isPlaying} hasDownloaded={hasDownloaded} hasShared={hasShared} hasSaved={hasSaved} setHasDownloaded={setHasDownloaded} setHasShared={setHasShared} setHasSaved={setHasSaved} showToast={showToast} onRemember={rememberCurrentGeneration} onDelete={deleteCurrentGeneration} onNavigate={setScreen} onPlayMix={playGeneratedMix} />;
      case "history":
        return <History creatorMode={creatorMode} voiceTakes={voiceTakes} generatedTracks={generatedTracks} backendTracks={backendTracks} backendMode={backendMode} deletedBackendTrackIds={deletedBackendTrackIds} playingVoiceTakeId={playingVoiceTakeId} onPlayVoiceTake={playVoiceTake} onPlayBackendTrack={playBackendTrack} onDownloadBackendTrack={downloadBackendTrack} onUploadVoiceTake={uploadVoiceTake} onUseVoiceTake={useVoiceTakeForConversion} onDeleteVoiceTake={deleteVoiceTake} onShareVoiceTake={(title) => {
          showToast(`Shared ${title}`);
        }} onDownloadTrack={(title) => {
          setHasDownloaded(true);
          updateGeneratedTrackStatus(title, "Downloaded");
          showToast(`Downloaded ${title}`);
        }} onShareTrack={(title) => {
          setHasShared(true);
          updateGeneratedTrackStatus(title, "Shared");
          showToast(`Shared ${title}`);
        }} onUpdateBackendTrackStatus={updateBackendTrackStatus} onDeleteGeneratedTrack={deleteGeneratedTrack} onDeleteBackendTrack={deleteBackendHistoryTrack} onOpenRecycleBin={() => setScreen("recycleBin")} />;
      case "recycleBin":
        return <RecycleBin voiceTakes={recycleVoiceTakes} localTracks={deletedGeneratedTracks} backendTracks={recycleTracks} onBack={() => setScreen("history")} onRestoreVoiceTake={restoreVoiceTake} onPermanentVoiceTake={permanentlyDeleteVoiceTake} onRestoreLocalTrack={restoreGeneratedTrack} onPermanentLocalTrack={permanentlyDeleteGeneratedTrack} onRestoreBackendTrack={restoreBackendTrack} onPermanentBackendTrack={permanentlyDeleteBackendTrack} />;
      case "profile":
        return <Profile creatorMode={creatorMode} firebaseStatus={firebaseStatus} firebaseEmail={firebaseUser?.email ?? ""} isAdmin={isAdminFirebaseUser(firebaseUser)} onGoToSignup={() => setScreen("authSignUp")} profile={creatorProfile} onSaveProfile={saveCreatorProfile} defaultGenre={selectedGenre} setDefaultGenre={setSelectedGenre} backendMode={backendMode} backendMessage={backendMessage} onOpenAdmin={() => setScreen("admin")} onReset={resetAppSession} onLogout={logout} showToast={showToast} />;
      case "admin":
        if (!isAdminFirebaseUser(firebaseUser)) {
          return <Profile creatorMode={creatorMode} firebaseStatus={firebaseStatus} firebaseEmail={firebaseUser?.email ?? ""} isAdmin={false} onGoToSignup={() => setScreen("authSignUp")} profile={creatorProfile} onSaveProfile={saveCreatorProfile} defaultGenre={selectedGenre} setDefaultGenre={setSelectedGenre} backendMode={backendMode} backendMessage="Admin panel is only available for the configured admin account." onOpenAdmin={() => setScreen("admin")} onReset={resetAppSession} onLogout={logout} showToast={showToast} />;
        }
        return <AdminPanel summary={adminSummary} loading={adminLoading} backendMode={backendMode} backendMessage={backendMessage} onBack={() => setScreen("profile")} onRefresh={refreshAdminSummary} onCleanupStale={cleanupStaleLibrary} />;
      default:
        return null;
    }
  }, [screen, startupLoading, accountRestoring, creatorMode, loginChoice, creatorProfile, firebaseUser, firebaseStatus, authBusy, intent, selectedGenre, setSelectedGenre, generationIntent, processingIndex, trackName, fileNameMode, isPlaying, activePlaybackUrl, hasDownloaded, hasShared, hasSaved, inputSource, showToast, resetAppSession, logout, finishAuth, backendMode, backendMessage, backendJobId, backendFinalUrl, backendDownloadUrl, backendIsolatedVocalUrl, backendBackingUrl, backendExportUrls, backendAnalysis, backendBlueprint, skarlyAnalysis, skarlyResult, skarlyV2Job, skarlyExportResult, producerProfiles, selectedProducerProfileIds, replaceProducerProfile, selectedSkarlyVersionIndex, skarlyBusy, skarlyRemixBusy, skarlyRegenerationBusy, skarlySectionBusy, skarlyExportBusy, vocalMusicBalance, backendTracks, adminSummary, adminLoading, recycleVoiceTakes, recycleTracks, deletedGeneratedTracks, deletedBackendTrackIds, generationActive, generationError, currentGeneratedTrack, generatedTracks, voiceTakes, playingVoiceTakeId, addVoiceTake, playVoiceTake, playBackendTrack, downloadBackendTrack, playGeneratedMix, selectSkarlyVersion, chooseBestSkarlyVersion, playSkarlyVersion, remixSkarlyVersion, regenerateSkarlyVersion, regenerateSkarlySection, exportSkarlyVersion, submitSkarlyFeedback, uploadVoiceTake, useVoiceTakeForConversion, deleteVoiceTake, restoreVoiceTake, permanentlyDeleteVoiceTake, recoverCloudLibrary, refreshAdminSummary, cleanupStaleLibrary, clearSkarlySession, deleteCurrentGeneration, deleteGeneratedTrack, deleteBackendHistoryTrack, restoreGeneratedTrack, permanentlyDeleteGeneratedTrack, restoreBackendTrack, permanentlyDeleteBackendTrack, finishNamingTrack, analyzeSkarlySource, startGeneration, resumeGeneration, saveCreatorProfile, updateBackendTrackStatus, updateGeneratedTrackStatus]);

  return (
    <SafeAreaView style={styles.safe}>
      <StatusBar style="light" />
      <AppShell screen={screen} setScreen={setScreen} toastMessage={toastMessage}>
        {content}
      </AppShell>
    </SafeAreaView>
  );
}

function AppShell({ children, screen, setScreen, toastMessage }: { children: React.ReactNode; screen: Screen; setScreen: (screen: Screen) => void; toastMessage: string }) {
  const lockedCreationScreens: Screen[] = ["genre", "producer", "processing", "nameTrack", "nameSuccess", "result", "download"];
  const showBottomNav = !["splash", "login", "authSignIn", "authSignUp", "setup", ...lockedCreationScreens].includes(screen);
  const lockScreenScroll = screen === "splash";
  const [navVisible, setNavVisible] = useState(true);
  const lastScrollY = useRef(0);
  const navOffset = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    setNavVisible(true);
    lastScrollY.current = 0;
  }, [screen]);

  useEffect(() => {
    Animated.timing(navOffset, {
      toValue: showBottomNav && navVisible ? 0 : 94,
      duration: 220,
      useNativeDriver: true
    }).start();
  }, [navOffset, navVisible, showBottomNav]);

  const handleScroll = (event: { nativeEvent: { contentOffset: { y: number } } }) => {
    if (!showBottomNav) return;
    const y = event.nativeEvent.contentOffset.y;
    const delta = y - lastScrollY.current;

    if (y < 16) {
      setNavVisible(true);
    } else if (delta > 10) {
      setNavVisible(false);
    } else if (delta < -10) {
      setNavVisible(true);
    }

    lastScrollY.current = y;
  };

  return (
    <View style={styles.appShell}>
      {lockScreenScroll ? (
        <View style={styles.lockedScreenContent}>
          {children}
        </View>
      ) : (
        <ScrollView contentContainerStyle={styles.scrollContent} showsVerticalScrollIndicator={false} onScroll={handleScroll} scrollEventThrottle={16}>
          {children}
        </ScrollView>
      )}
      {showBottomNav && (
        <BottomNav screen={screen} setScreen={setScreen} translateY={navOffset} visible={navVisible} />
      )}
      <Toast message={toastMessage} aboveTabs={showBottomNav} />
    </View>
  );
}

function StartupLoadingScreen() {
  const spin = useRef(new Animated.Value(0)).current;
  const pulse = useRef(new Animated.Value(0)).current;
  const sigilBreath = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    const spinLoop = Animated.loop(
      Animated.timing(spin, {
        toValue: 1,
        duration: 2600,
        easing: Easing.linear,
        useNativeDriver: true
      })
    );
    const pulseLoop = Animated.loop(
      Animated.sequence([
        Animated.timing(pulse, {
          toValue: 1,
          duration: 1900,
          easing: Easing.out(Easing.cubic),
          useNativeDriver: true
        }),
        Animated.timing(pulse, {
          toValue: 0,
          duration: 0,
          useNativeDriver: true
        })
      ])
    );
    const sigilLoop = Animated.loop(
      Animated.sequence([
        Animated.timing(sigilBreath, {
          toValue: 1,
          duration: 1350,
          easing: Easing.inOut(Easing.sin),
          useNativeDriver: true
        }),
        Animated.timing(sigilBreath, {
          toValue: 0,
          duration: 1350,
          easing: Easing.inOut(Easing.sin),
          useNativeDriver: true
        })
      ])
    );
    spinLoop.start();
    pulseLoop.start();
    sigilLoop.start();
    return () => {
      spinLoop.stop();
      pulseLoop.stop();
      sigilLoop.stop();
    };
  }, [pulse, sigilBreath, spin]);

  const rotation = spin.interpolate({ inputRange: [0, 1], outputRange: ["0deg", "360deg"] });

  return (
    <View style={styles.startupLoadingScreen}>
      <View style={styles.radarGrain} />
      <Animated.View
        style={[
          styles.radarPulseRing,
          {
            opacity: pulse.interpolate({ inputRange: [0, 0.4, 1], outputRange: [0, 0.38, 0] }),
            transform: [{ scale: pulse.interpolate({ inputRange: [0, 1], outputRange: [0.72, 1.15] }) }]
          }
        ]}
      />
      <View style={styles.radarStage}>
        <Svg width={278} height={278} viewBox="0 0 278 278">
          <Defs>
            <LinearGradient id="radarStroke" x1="0" y1="0" x2="1" y2="1">
              <Stop offset="0" stopColor="#f0f0f0" stopOpacity="0.12" />
              <Stop offset="0.55" stopColor="#d9d9d9" stopOpacity="0.32" />
              <Stop offset="1" stopColor="#8a8a8a" stopOpacity="0.08" />
            </LinearGradient>
          </Defs>
          <Circle cx="139" cy="139" r="48" stroke="rgba(220,220,220,0.13)" strokeWidth="1" fill="none" />
          <Circle cx="139" cy="139" r="78" stroke="rgba(220,220,220,0.11)" strokeWidth="1" fill="none" />
          <Circle cx="139" cy="139" r="108" stroke="rgba(220,220,220,0.08)" strokeWidth="1" fill="none" />
          <Path d="M43 139 C56 77 96 43 139 43 C189 43 225 76 235 123" stroke="url(#radarStroke)" strokeWidth="2.2" fill="none" strokeLinecap="round" />
          <Path d="M235 155 C222 216 182 235 139 235 C90 235 54 205 43 154" stroke="rgba(210,210,210,0.12)" strokeWidth="2" fill="none" strokeLinecap="round" />
          <Path d="M63 139 H99 M179 139 H215" stroke="rgba(210,210,210,0.11)" strokeWidth="1" strokeLinecap="round" />
          <Path d="M139 63 V99 M139 179 V215" stroke="rgba(210,210,210,0.09)" strokeWidth="1" strokeLinecap="round" />
        </Svg>
        <Animated.View style={[styles.radarSweep, { transform: [{ rotate: rotation }] }]}>
          <View style={styles.radarSweepLine} />
          <View style={styles.radarSweepGlow} />
        </Animated.View>
        <Animated.View
          style={[
            styles.radarSigil,
            {
              opacity: sigilBreath.interpolate({ inputRange: [0, 1], outputRange: [0.76, 1] }),
              transform: [{ scale: sigilBreath.interpolate({ inputRange: [0, 1], outputRange: [0.985, 1.02] }) }]
            }
          ]}
        >
          <Svg width={72} height={112} viewBox="0 0 72 112">
            <Defs>
              <LinearGradient id="sigilMetal" x1="0" y1="0" x2="1" y2="1">
                <Stop offset="0" stopColor="#f1f1f1" stopOpacity="0.9" />
                <Stop offset="0.48" stopColor="#a7a7a7" stopOpacity="0.86" />
                <Stop offset="1" stopColor="#5a5a5a" stopOpacity="0.82" />
              </LinearGradient>
            </Defs>
            <Path d="M38 3 C48 22 24 32 43 54 C58 72 41 88 31 109 C29 88 41 77 24 59 C8 41 28 25 38 3Z" fill="url(#sigilMetal)" />
            <Path d="M36.5 14 C41 28 28 40 43 55 C54 67 43 79 35 95" stroke="rgba(5,5,5,0.82)" strokeWidth={8} strokeLinecap="round" fill="none" />
            <Path d="M36 4 V108" stroke="rgba(230,230,230,0.25)" strokeWidth={1.1} />
            <Circle cx="23" cy="82" r="12" fill="rgba(0,0,0,0.9)" stroke="rgba(210,210,210,0.72)" strokeWidth={2} />
            <Path d="M23 94 L20 108 M28 93 L29 106 M35 83 L47 86 M37 26 L46 30 M30 48 L18 45" stroke="rgba(0,0,0,0.46)" strokeWidth={2} strokeLinecap="round" />
          </Svg>
        </Animated.View>
      </View>
    </View>
  );
}

function ScreenHeader({ title, hint, onBack, action }: { title: string; hint: string; onBack?: () => void; action?: { icon: IconName; onPress: () => void } }) {
  return (
    <View style={styles.header}>
      <View style={styles.headerTop}>
        {onBack ? (
          <Pressable style={({ pressed }) => [styles.headerBackButton, pressed && styles.touchPressedBlue]} onPress={onBack}>
            <IconSymbol name="back" tone="blue" size={18} />
          </Pressable>
        ) : (
          <View style={styles.headerBackSpacer} />
        )}
        {action ? (
          <Pressable style={({ pressed }) => [styles.headerBackButton, pressed && styles.touchPressedBlue]} onPress={action.onPress}>
            <IconSymbol name={action.icon} tone="blue" size={18} />
          </Pressable>
        ) : (
          <View style={styles.headerBackSpacer} />
        )}
      </View>
      <Text style={styles.title}>{title}</Text>
      <Text style={styles.hint}>{hint}</Text>
    </View>
  );
}

function EntryScreen({
  firebaseStatus,
  loginChoice,
  onChoose,
  onContinue
}: {
  firebaseStatus: FirebaseSetupStatus;
  loginChoice: LoginChoice;
  onChoose: (choice: Exclude<LoginChoice, null>) => void;
  onContinue: (choice: Exclude<LoginChoice, null>) => void;
}) {
  const imageReveal = useRef(new Animated.Value(0)).current;
  const titleReveal = useRef(new Animated.Value(0)).current;
  const ctaReveal = useRef(new Animated.Value(0)).current;
  const hasChoice = loginChoice !== null;
  const choiceCopy = loginChoice === "guest"
    ? "Try the studio right away. Drafts, recordings, and mixes stay in this session only."
    : loginChoice === "signin"
      ? "Return to your saved workspace with your private history and settings."
      : "Create a private creator workspace for saved tracks and future synced history.";
  const choiceTitle = loginChoice === "guest" ? "Guest Creator" : loginChoice === "signin" ? "Saved Workspace" : "New Workspace";

  useEffect(() => {
    Animated.sequence([
      Animated.timing(imageReveal, {
        toValue: 1,
        duration: 520,
        useNativeDriver: true
      }),
      Animated.timing(titleReveal, {
        toValue: 1,
        duration: 560,
        useNativeDriver: true
      }),
      Animated.timing(ctaReveal, {
        toValue: 1,
        duration: 520,
        useNativeDriver: true
      })
    ]).start();
  }, [ctaReveal, imageReveal, titleReveal]);

  return (
    <View style={styles.splashHeroScreen}>
      <Animated.View style={[styles.splashImageLayer, { opacity: imageReveal }]}>
        <ImageBackground source={require("./assets/splash-entry-portrait.png")} resizeMode="cover" style={styles.splashImage} imageStyle={styles.splashEntryPortraitFit}>
          <View style={styles.splashBottomFadeStrong} />
        </ImageBackground>
      </Animated.View>
      <Animated.View
        style={[
          styles.entryTitleBlock,
          {
            opacity: titleReveal,
            transform: [
              {
                translateY: titleReveal.interpolate({
                  inputRange: [0, 1],
                  outputRange: [22, 0]
                })
              },
              {
                scale: titleReveal.interpolate({
                  inputRange: [0, 1],
                  outputRange: [0.92, 1]
                })
              }
            ]
          }
        ]}
      >
        <Image source={require("./assets/logo.png")} resizeMode="contain" style={styles.entryWordmark} />
        <View style={styles.entryChoiceStack}>
          <EntryChoiceButton label="Guest" icon="guest" selected={loginChoice === "guest"} onPress={() => onChoose("guest")} />
          {loginChoice === "guest" && <EntryChoiceInfo title={choiceTitle} body={choiceCopy} />}
          <EntryChoiceButton label="Sign Up" icon="edit" selected={loginChoice === "signup"} onPress={() => onChoose("signup")} />
          {loginChoice === "signup" && <EntryChoiceInfo title={choiceTitle} body={choiceCopy} />}
          <EntryChoiceButton label="Sign In" icon="saved" selected={loginChoice === "signin"} onPress={() => onChoose("signin")} />
          {loginChoice === "signin" && <EntryChoiceInfo title={choiceTitle} body={choiceCopy} />}
        </View>
        {firebaseStatus === "unconfigured" && <StatusNotice title="Firebase Setup Needed" body="Guest mode still works. Add Expo Firebase env values to enable saved accounts." icon="error" />}
        {firebaseStatus === "unavailable" && <StatusNotice title="Manual Sign In" body="Saved session restore timed out. Choose Sign In to continue." icon="error" />}
        <Animated.View
          style={[
            styles.entryContinueWrap,
            {
              opacity: ctaReveal,
              transform: [
                {
                  translateY: ctaReveal.interpolate({
                    inputRange: [0, 1],
                    outputRange: [18, 0]
                  })
                }
              ]
            }
          ]}
        >
          <PrimaryButton label={hasChoice ? loginChoice === "guest" ? "Continue as Guest" : loginChoice === "signin" ? "Go to Sign In" : "Go to Sign Up" : "Choose an Option"} icon="continue" onPress={() => hasChoice && onContinue(loginChoice)} disabled={!hasChoice} golden />
        </Animated.View>
      </Animated.View>
    </View>
  );
}

function EntryChoiceButton({ label, icon, selected, onPress }: { label: string; icon: IconName; selected: boolean; onPress: () => void }) {
  return (
    <Pressable style={({ pressed }) => [styles.entryChoiceButton, selected && styles.entryChoiceButtonSelected, pressed && styles.entryChoiceButtonPressed]} onPress={onPress}>
      <IconSymbol name={icon} tone={selected ? "ink" : "blue"} size={17} />
      <Text style={[styles.entryChoiceText, selected && styles.entryChoiceTextSelected]}>{label}</Text>
    </Pressable>
  );
}

function EntryChoiceInfo({ title, body }: { title: string; body: string }) {
  return (
    <View style={styles.entryChoiceInfo}>
      <Text style={styles.entryChoiceTitle}>{title}</Text>
      <Text style={styles.entryChoiceBody}>{body}</Text>
    </View>
  );
}

function AuthScreen({
  kind,
  firebaseStatus,
  authBusy,
  onBack,
  onContinue
}: {
  kind: "signin" | "signup";
  firebaseStatus: FirebaseSetupStatus;
  authBusy: boolean;
  onBack: () => void;
  onContinue: (submission: AuthSubmit) => void;
}) {
  const isSignup = kind === "signup";
  const [name, setName] = useState(isSignup ? "" : "Saved Creator");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const normalizedEmail = email.trim().toLowerCase();
  const passwordsMatch = password === confirmPassword;
  const firebaseUnavailable = firebaseStatus === "unconfigured";
  const canContinue = !authBusy && !firebaseUnavailable && email.trim().length > 0 && password.trim().length > 0 && (!isSignup || (name.trim().length > 0 && confirmPassword.trim().length > 0 && passwordsMatch));
  return (
    <View>
      <ScreenHeader title={isSignup ? "Create Account" : "Sign In"} hint={isSignup ? "Set up a private creator workspace for saved tracks." : "Return to your private Skarly workspace."} />
      <Card>
        <Text style={styles.cardTitle}>{isSignup ? "Saved Creator" : "Welcome Back"}</Text>
        <Text style={styles.subtitle}>{isSignup ? "Your drafts, settings, and downloads stay in one place." : "Use your saved workspace and cloud library."}</Text>
        {firebaseStatus === "unconfigured" && <StatusNotice title="Firebase Setup Needed" body="Guest mode still works. Add Expo Firebase env values to enable saved accounts." icon="error" />}
        {firebaseStatus === "unavailable" && <StatusNotice title="Manual Sign In" body="Saved session restore timed out. You can still sign in manually." icon="error" />}
        {isSignup && <TextInput value={name} onChangeText={setName} placeholder="Creator name" placeholderTextColor={colors.muted} style={styles.input} />}
        <TextInput value={email} onChangeText={setEmail} placeholder="Email address" placeholderTextColor={colors.muted} style={styles.input} keyboardType="email-address" autoCapitalize="none" />
        <TextInput value={password} onChangeText={setPassword} placeholder="Password" placeholderTextColor={colors.muted} style={styles.input} secureTextEntry />
        {isSignup && <TextInput value={confirmPassword} onChangeText={setConfirmPassword} placeholder="Confirm password" placeholderTextColor={colors.muted} style={styles.input} secureTextEntry />}
        {isSignup && confirmPassword.length > 0 && !passwordsMatch && <Text style={styles.errorText}>Passwords do not match.</Text>}
      </Card>
      <PrimaryButton label={authBusy ? "Connecting..." : isSignup ? "Create Workspace" : "Sign In"} icon="continue" disabled={!canContinue} onPress={() => onContinue({
        profile: {
          name: (isSignup ? name : email.split("@")[0]).trim() || "Saved Creator",
          email: normalizedEmail,
          bio: "Private Skarly workspace"
        },
        password
      })} />
      <SecondaryButton label="Back To Options" icon="back" onPress={onBack} />
    </View>
  );
}

function LockedStudioOptions() {
  const options = ["Record idea", "Upload vocal", "Pick genre", "Build demo"];
  return (
    <View style={styles.lockedPanel}>
      <Text style={styles.metaText}>Choose a creator type to unlock studio options</Text>
      <View style={styles.lockedGrid}>
        {options.map((option) => (
          <View key={option} style={styles.lockedOption}>
            <Text style={styles.lockedText}>{option}</Text>
            <Text style={styles.lockText}>Locked</Text>
          </View>
        ))}
      </View>
    </View>
  );
}

function CreatorSetup({ intent, setIntent, genre, setGenre, onNext }: { intent: string; setIntent: (intent: string) => void; genre: Genre; setGenre: (genre: Genre) => void; onNext: () => void }) {
  const intents = [
    { label: "Demo Song", meta: "Structured Idea", accent: "#7bb7ff" },
    { label: "Hook Idea", meta: "Catchy Start", accent: "#ff6f91" },
    { label: "Vocal Practice", meta: "Clean Take", accent: "#6ee58b" },
    { label: "Fun Experiment", meta: "Try A Vibe", accent: "#b28cff" }
  ];
  return (
    <View>
      <ScreenHeader title="Creator Setup" hint="Personalize your private workspace." />
      <Card>
        <Row title="What Are You Making?" meta="Private" />
        <ScrollView horizontal showsHorizontalScrollIndicator={false} snapToInterval={312} decelerationRate="fast" contentContainerStyle={styles.intentCarousel}>
          {intents.map((item, index) => (
            <Pressable key={item.label} style={({ pressed }) => [styles.intentCard, pressed && styles.touchPressedBlue, intent === item.label && styles.intentSelected]} onPress={() => setIntent(item.label)}>
              <IntentArtwork index={index} label={item.label} meta={item.meta} selected={intent === item.label} />
            </Pressable>
          ))}
        </ScrollView>
      </Card>
      <Card>
        <Row title="Default Vibe" meta={genre.label} />
        <Text style={styles.subtitle}>Start with {genre.label} and keep the base Skarly aura.</Text>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.genrePills}>
          {genres.map((item) => (
            <Pressable key={item.id} style={({ pressed }) => [styles.genrePill, pressed && styles.touchPressedBlue, genre.id === item.id && { borderColor: item.color, backgroundColor: "rgba(198,170,106,0.18)" }]} onPress={() => setGenre(item)}>
              <Text style={[styles.genrePillText, { color: item.color }]}>{item.label}</Text>
            </Pressable>
          ))}
        </ScrollView>
      </Card>
      <PrimaryButton label="Enter Studio" icon="continue" onPress={onNext} />
    </View>
  );
}

function IntentArtwork({ index, label, meta, selected }: { index: number; label: string; meta: string; selected: boolean }) {
  const icons: IconName[] = ["mic", "waveform", "speak", "experiment"];
  const sources = [
    require("./assets/intent-full-song.jpg"),
    require("./assets/intent-hook-idea.jpg"),
    require("./assets/intent-vocal-practice.jpg"),
    require("./assets/intent-fun-experiment.png")
  ];
  return (
    <View style={styles.intentArtwork}>
      <Image source={sources[index]} resizeMode="cover" style={styles.intentArtworkImage} />
      <View style={selected ? styles.intentArtworkSelectedShade : styles.intentArtworkClearShade} />
      <View style={styles.intentImageLabel}>
        <IconSymbol name={icons[index]} tone="blue" size={30} />
        <View style={styles.intentLabelCopy}>
          <Text style={styles.intentText}>{label}</Text>
          <Text style={styles.intentMeta}>{meta}</Text>
        </View>
      </View>
    </View>
  );
}

function Home({
  creatorMode,
  generatedTrack,
  voiceTakes,
  playingVoiceTakeId,
  onPlayVoiceTake,
  onUseVoiceTake,
  onDeleteVoiceTake,
  onShareTrack,
  onDownloadTrack,
  onNavigate
}: {
  creatorMode: CreatorMode;
  generatedTrack: GeneratedTrackView | null;
  voiceTakes: VoiceTake[];
  playingVoiceTakeId: string | null;
  onPlayVoiceTake: (take: VoiceTake) => void | Promise<void>;
  onUseVoiceTake: (take: VoiceTake) => void;
  onDeleteVoiceTake: (takeId: string) => void;
  onShareTrack: (title: string) => void;
  onDownloadTrack: (title: string) => void;
  onNavigate: (screen: Screen) => void;
}) {
  return (
    <View>
      <ScreenHeader title="Skarly Vocal-to-Music Studio" hint="Upload your vocal. Skarly makes five finished, vocal-forward song versions." />
      <PrimaryButton label="Record Vocal" icon="mic" onPress={() => onNavigate("record")} golden />
      <SecondaryButton label="Upload Vocal or Song" icon="upload" onPress={() => onNavigate("upload")} />
      <CreatorWorkspaceCard mode={creatorMode} />
      {generatedTrack ? (
        <Card>
          <Row title="Latest Song Version" meta="Most recent Skarly arrangement" chip={generatedTrack.status} />
          <View style={styles.latestPreview}>
            <View style={styles.latestIcon}>
              <IconSymbol name="waveform" size={24} tone="blue" />
            </View>
            <View style={styles.latestCopy}>
              <Text style={styles.trackTitle}>{generatedTrack.title}</Text>
              <Text style={styles.metaText}>{generatedTrack.meta}</Text>
            </View>
          </View>
          <View style={styles.homeActionRow}>
            <SecondaryButton label="Open" icon="continue" onPress={() => onNavigate("result")} compact />
            <SecondaryButton label="Download" icon="download" onPress={() => onDownloadTrack(generatedTrack.title)} compact />
            <SecondaryButton label="Share" icon="share" onPress={() => onShareTrack(generatedTrack.title)} compact />
          </View>
        </Card>
      ) : voiceTakes.length > 0 ? (
        <Card>
          <Row title="Latest Activity" meta="Most recent voice take" chip="Temporary" />
          <View style={styles.latestPreview}>
            <View style={styles.latestIcon}>
              <IconSymbol name="mic" size={24} tone="blue" />
            </View>
            <View style={styles.latestCopy}>
              <Text style={styles.trackTitle}>{voiceTakes[0].title}</Text>
              <Text style={styles.metaText}>{voiceTakes[0].duration}s | {voiceTakes[0].createdAt}</Text>
            </View>
          </View>
          <View style={styles.homeActionRow}>
            <SecondaryButton label={playingVoiceTakeId === voiceTakes[0].id ? "Pause" : "Play"} icon={playingVoiceTakeId === voiceTakes[0].id ? "success" : "play"} onPress={() => onPlayVoiceTake(voiceTakes[0])} compact />
            <SecondaryButton label="Use" icon="waveform" onPress={() => onUseVoiceTake(voiceTakes[0])} compact />
            <SecondaryButton label="Delete" icon="trash" onPress={() => onDeleteVoiceTake(voiceTakes[0].id)} compact />
          </View>
        </Card>
      ) : (
        <Card>
          <Row title="Make Your First Song" meta="Record or upload a vocal, confirm the song read, then pick your best version" chip="Ready" />
          <View style={styles.emptyFlow}>
            <MiniStep icon="mic" label="Record" />
            <Text style={styles.emptyArrow}>→</Text>
            <MiniStep icon="vibe" label="Song map" />
            <Text style={styles.emptyArrow}>→</Text>
            <MiniStep icon="download" label="Best mix" />
          </View>
        </Card>
      )}
    </View>
  );
}

function RecordVoice({ creatorMode, genre, playingVoiceTakeId, onNext, onUseTake, onPlayTake, onHome, showToast }: { creatorMode: CreatorMode; genre: Genre; playingVoiceTakeId: string | null; onNext: (draft: RecordedTakeDraft) => VoiceTake; onUseTake: (take: VoiceTake) => void | Promise<void>; onPlayTake: (take: VoiceTake) => void | Promise<void>; onHome: () => void; showToast: (message: string) => void }) {
  const [seconds, setSeconds] = useState(0);
  const [isRecording, setIsRecording] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [savedTake, setSavedTake] = useState<VoiceTake | null>(null);
  const [recordingUri, setRecordingUri] = useState<string | undefined>();
  const [contentType, setContentType] = useState("audio/m4a");
  const [sizeBytes, setSizeBytes] = useState<number | undefined>();
  const nativeRecordingRef = useRef<Audio.Recording | null>(null);
  const browserRecorderRef = useRef<any>(null);
  const browserChunksRef = useRef<Blob[]>([]);
  const browserStreamRef = useRef<any>(null);
  const browserAudioContextRef = useRef<any>(null);
  const browserLevelTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const micPeakRef = useRef(0);
  const [micLevel, setMicLevel] = useState(0);
  const [micPeak, setMicPeak] = useState(0);
  const maxDuration = 300;
  const hasTake = seconds > 0 && Boolean(recordingUri);
  const hasMicSignal = Platform.OS !== "web" || micPeak >= 0.015;
  const recordState = isRecording ? "Recording" : isPaused ? "Paused" : seconds === 0 ? "Ready" : "Take ready";

  const cleanupBrowserStream = useCallback(() => {
    if (browserLevelTimerRef.current) {
      clearInterval(browserLevelTimerRef.current);
      browserLevelTimerRef.current = null;
    }
    browserAudioContextRef.current?.close?.().catch?.(() => undefined);
    browserAudioContextRef.current = null;
    browserStreamRef.current?.getTracks?.().forEach((track: any) => track.stop());
    browserStreamRef.current = null;
  }, []);

  const startBrowserMicMeter = useCallback((stream: any) => {
    const AudioContextCtor = (globalThis as any).AudioContext || (globalThis as any).webkitAudioContext;
    if (!AudioContextCtor) return;
    const audioContext = new AudioContextCtor();
    const source = audioContext.createMediaStreamSource(stream);
    const analyser = audioContext.createAnalyser();
    analyser.fftSize = 1024;
    source.connect(analyser);
    const samples = new Uint8Array(analyser.fftSize);
    browserAudioContextRef.current = audioContext;
    browserLevelTimerRef.current = setInterval(() => {
      analyser.getByteTimeDomainData(samples);
      let sum = 0;
      let peak = 0;
      for (let index = 0; index < samples.length; index += 1) {
        const centered = (samples[index] - 128) / 128;
        const abs = Math.abs(centered);
        sum += centered * centered;
        if (abs > peak) peak = abs;
      }
      const rms = Math.sqrt(sum / samples.length);
      const normalized = Math.min(1, Math.max(rms * 8, peak * 2.2));
      micPeakRef.current = Math.max(micPeakRef.current, peak, rms);
      setMicPeak(micPeakRef.current);
      setMicLevel(normalized);
    }, 100);
  }, []);

  const stopRecording = useCallback(async () => {
    try {
      if (Platform.OS === "web" && browserRecorderRef.current) {
        const recorder = browserRecorderRef.current;
        if (recorder.state !== "inactive") recorder.stop();
        browserRecorderRef.current = null;
      } else if (nativeRecordingRef.current) {
        const recorder = nativeRecordingRef.current;
        nativeRecordingRef.current = null;
        await recorder.stopAndUnloadAsync();
        const uri = recorder.getURI();
        if (uri) {
          setRecordingUri(uri);
          setContentType("audio/m4a");
        }
      }
    } catch {
      showToast("Could not finish recording");
    } finally {
      if (Platform.OS !== "web") {
        await Audio.setAudioModeAsync({
          allowsRecordingIOS: false,
          playsInSilentModeIOS: true,
          staysActiveInBackground: false,
          shouldDuckAndroid: true,
          playThroughEarpieceAndroid: false
        }).catch(() => undefined);
      }
      setIsRecording(false);
      setIsPaused(false);
    }
  }, [showToast]);

  useEffect(() => {
    if (!isRecording) return;
    const timer = setInterval(() => {
      setSeconds((current) => {
        const next = Math.min(maxDuration, current + 1);
        if (next >= maxDuration) {
          setTimeout(() => void stopRecording(), 0);
        }
        return next;
      });
    }, 1000);
    return () => clearInterval(timer);
  }, [isRecording, maxDuration, stopRecording]);

  useEffect(() => {
    return () => {
      void stopRecording();
      cleanupBrowserStream();
    };
  }, [cleanupBrowserStream, stopRecording]);

  const startRecording = async () => {
    if (recordingUri || savedTake) {
      setRecordingUri(undefined);
      setSavedTake(null);
      setSizeBytes(undefined);
      setSeconds(0);
    }
    setMicLevel(0);
    setMicPeak(0);
    micPeakRef.current = 0;

    try {
      if (isPaused) {
        if (Platform.OS === "web" && browserRecorderRef.current?.state === "paused") {
          browserRecorderRef.current.resume();
        } else if (nativeRecordingRef.current) {
          await nativeRecordingRef.current.startAsync();
        }
        setIsPaused(false);
        setIsRecording(true);
        return;
      }

      if (Platform.OS === "web") {
        const mediaDevices = (globalThis.navigator as any)?.mediaDevices;
        const MediaRecorderCtor = (globalThis as any).MediaRecorder;
        if (!mediaDevices || !MediaRecorderCtor) {
          showToast("Browser microphone recording is not available here");
          return;
        }

        const stream = await mediaDevices.getUserMedia({
          audio: {
            echoCancellation: true,
            noiseSuppression: true,
            autoGainControl: true
          }
        });
        const preferredType = MediaRecorderCtor.isTypeSupported?.("audio/webm;codecs=opus")
          ? "audio/webm;codecs=opus"
          : MediaRecorderCtor.isTypeSupported?.("audio/webm")
            ? "audio/webm"
            : "";
        const recorder = preferredType ? new MediaRecorderCtor(stream, { mimeType: preferredType }) : new MediaRecorderCtor(stream);
        browserStreamRef.current = stream;
        browserChunksRef.current = [];
        startBrowserMicMeter(stream);
        recorder.ondataavailable = (event: any) => {
          if (event.data?.size) browserChunksRef.current.push(event.data);
        };
        recorder.onstop = () => {
          const blob = new Blob(browserChunksRef.current, { type: recorder.mimeType || "audio/webm" });
          const detectedPeak = micPeakRef.current;
          setRecordingUri(URL.createObjectURL(blob));
          setContentType(blob.type || "audio/webm");
          setSizeBytes(blob.size);
          cleanupBrowserStream();
          if (detectedPeak < 0.015) {
            showToast("No mic input detected. Check the browser microphone or input device.");
          }
        };
        browserRecorderRef.current = recorder;
        recorder.start(250);
      } else {
        const permission = await Audio.requestPermissionsAsync();
        if (!permission.granted) {
          showToast("Microphone permission is needed to record");
          return;
        }
        await Audio.setAudioModeAsync({
          allowsRecordingIOS: true,
          playsInSilentModeIOS: true,
          staysActiveInBackground: false,
          shouldDuckAndroid: true,
          playThroughEarpieceAndroid: false
        });
        const recording = new Audio.Recording();
        await recording.prepareToRecordAsync(Audio.RecordingOptionsPresets.HIGH_QUALITY);
        await recording.startAsync();
        nativeRecordingRef.current = recording;
      }

      setIsRecording(true);
      setIsPaused(false);
      showToast("Recording started");
    } catch {
      cleanupBrowserStream();
      showToast("Could not start microphone recording");
    }
  };

  const pauseRecording = async () => {
    try {
      if (Platform.OS === "web" && browserRecorderRef.current?.state === "recording") {
        browserRecorderRef.current.pause();
      } else if (nativeRecordingRef.current) {
        await nativeRecordingRef.current.pauseAsync();
      }
      setIsRecording(false);
      setIsPaused(true);
    } catch {
      showToast("Pause is not available on this device");
    }
  };

  const toggleRecording = () => {
    if (isRecording) {
      void pauseRecording();
      return;
    }
    void startRecording();
  };

  const retry = () => {
    void stopRecording();
    setSeconds(0);
    setSavedTake(null);
    setRecordingUri(undefined);
    setSizeBytes(undefined);
    setMicLevel(0);
    setMicPeak(0);
    micPeakRef.current = 0;
  };

  const saveTake = () => {
    if (!hasTake) return;
    if (!hasMicSignal) {
      showToast("This take has no detectable voice. Check your mic and record again.");
      return;
    }
    setSavedTake(onNext({ duration: seconds, fileUri: recordingUri, contentType, sizeBytes }));
  };

  return (
    <View>
      <ScreenHeader title="Record Your Vocal" hint={`${creatorMode === "saved" ? "Saved creator" : "Guest creator"} session | up to ${maxDuration}s`} />
      <AudioRecorder seconds={seconds} maxDuration={maxDuration} isRecording={isRecording} state={recordState} onPress={toggleRecording} />
      <DurationCard seconds={seconds} maxDuration={maxDuration} />
      <VoiceCapturePanel genre={genre} seconds={seconds} maxDuration={maxDuration} isRecording={isRecording} state={recordState} micLevel={micLevel} signalWarning={hasTake && !hasMicSignal} />
      <Text style={styles.helperNote}>For the best music match, record the vocal dry with headphones, keep the meter in Good, and avoid a background beat in the recording.</Text>
      <View style={styles.buttonRow}>
        {isRecording ? <PrimaryButton label="Stop" icon="success" onPress={() => void stopRecording()} compact golden /> : <PrimaryButton label={savedTake ? "Take Saved" : "Save Take"} icon={hasTake ? "success" : undefined} onPress={saveTake} disabled={!hasTake || !hasMicSignal || Boolean(savedTake)} compact />}
        <SecondaryButton label="Retry" icon="retry" onPress={retry} disabled={!hasTake && !isRecording && !isPaused} compact />
      </View>
      {savedTake && (
        <Card>
          <Row title={savedTake.title} meta={`${savedTake.duration}s voice memo | ${savedTake.fileUri ? "Local audio" : "No file"}`} chip={savedTake.uploaded ? "Saved" : "Temporary"} />
          <Text style={styles.subtitle}>Saved separately as a voice take. Use it now for conversion or return home and use it later.</Text>
          <StatusNotice title={savedTake.uploaded ? "Uploaded" : "Saved Locally"} body={savedTake.uploaded ? "This voice take is already in Cloud Storage." : "Cloud upload starts when you use this take for conversion."} icon={savedTake.uploaded ? "success" : "mic"} />
          <SecondaryButton label={playingVoiceTakeId === savedTake.id ? "Pause Take" : "Play Take"} icon={playingVoiceTakeId === savedTake.id ? "success" : "play"} onPress={() => onPlayTake(savedTake)} />
          <PrimaryButton label="Use This Take For Conversion" icon="waveform" onPress={() => onUseTake(savedTake)} golden />
          <SecondaryButton label="Save For Later Use" onPress={onHome} />
        </Card>
      )}
    </View>
  );
}

function UploadAudio({
  onNext,
  onHome,
  creatorMode,
  firebaseUser,
  showToast,
  setBackendMode,
  setBackendMessage
}: {
  onNext: (source: InputSource) => void;
  onHome: () => void;
  creatorMode: CreatorMode;
  firebaseUser: User | null;
  showToast: (message: string) => void;
  setBackendMode: (mode: BackendMode) => void;
  setBackendMessage: (message: string) => void;
}) {
  const [selectedFile, setSelectedFile] = useState<InputSource | null>(null);
  const [arrangementMode, setArrangementModeState] = useState<ArrangementMode>("vocal_to_song");
  const [preserveOriginalVocal, setPreserveOriginalVocalState] = useState(true);
  const [referenceStrength, setReferenceStrengthState] = useState(0.35);
  const [uploadNotice, setUploadNotice] = useState("");
  const [uploadBusy, setUploadBusy] = useState(false);

  const setArrangementMode = (mode: ArrangementMode) => {
    setArrangementModeState(mode);
    setSelectedFile((current) => current ? {
      ...current,
      arrangementMode: mode,
      preserveOriginalVocal: mode === "music_to_music" || mode === "full_song" ? preserveOriginalVocal : false,
      referenceStrength,
      detail: uploadDetailForMode(getAudioExtension(current.label), mode)
    } : current);
  };

  const setPreserveOriginalVocal = (value: boolean) => {
    setPreserveOriginalVocalState(value);
    setSelectedFile((current) => current ? { ...current, preserveOriginalVocal: value } : current);
  };

  const setReferenceStrength = (value: number) => {
    setReferenceStrengthState(value);
    setSelectedFile((current) => current ? { ...current, referenceStrength: value } : current);
  };

  const chooseLocalFile = async () => {
    const result = await DocumentPicker.getDocumentAsync({
      type: ["audio/mpeg", "audio/mp3", "audio/wav", "audio/x-wav", "audio/mp4", "audio/m4a", "audio/aac", "audio/flac", "audio/x-flac"],
      copyToCacheDirectory: false,
      multiple: false
    });

    if (result.canceled || !result.assets[0]) return;

    const file = result.assets[0];
    const extension = getAudioExtension(file.name);
    const supported = isSupportedAudioFile(file.name, file.mimeType);

    if (!supported) {
      setSelectedFile(null);
      setUploadNotice("Choose an MP3, WAV, M4A, AAC, or FLAC file.");
      showToast("Unsupported file type");
      return;
    }

    const contentType = inferAudioContentType(file.name, file.mimeType);
    const nextSource: InputSource = {
      kind: "localUpload",
      label: file.name,
      detail: uploadDetailForMode(extension, arrangementMode),
      arrangementMode,
      preserveOriginalVocal: arrangementMode === "music_to_music" || arrangementMode === "full_song" ? preserveOriginalVocal : false,
      referenceStrength,
      fileUri: file.uri,
      contentType,
      sizeBytes: file.size || 1
    };

    setUploadBusy(true);
    setSelectedFile(null);
    setUploadNotice("Preparing signed upload...");
    if (USE_BACKEND_API) {
      try {
        const signed = await backendApi.signUpload(creatorMode, firebaseUser, nextSource);
        nextSource.uploadId = signed.upload_id;
        nextSource.rawAudioPath = signed.raw_audio_path;
        nextSource.uploadUrl = signed.upload_url;
        setUploadNotice("Uploading audio to Cloud Storage...");
        await uploadFileToCloud(file.uri, signed, contentType, creatorMode, firebaseUser);
        nextSource.uploaded = true;
        setBackendMode("api");
        setBackendMessage(BACKEND_CONNECTED_MESSAGE);
        setUploadNotice("Audio uploaded to Cloud Storage. Ready for Skarly detection.");
      } catch {
        setBackendMode("offline");
        setBackendMessage(BACKEND_OFFLINE_MESSAGE);
        setUploadNotice("Cloud upload failed. Check FastAPI, Google credentials, and bucket permissions.");
        showToast("Cloud upload failed");
        setUploadBusy(false);
        return;
      }
    } else {
      setUploadNotice("Local file ready. Audio stays on this device.");
    }

    setSelectedFile(nextSource);
    setUploadBusy(false);
  };

  return (
    <View>
      <ScreenHeader title="Upload Your Audio" hint="Start with a vocal, a music reference, or a full song for Skarly to rework." />
      <Card>
        <Row title="Input Mode" meta={getArrangementModeLabel(arrangementMode)} />
        <View style={styles.fileOptionRow}>
          {([
            { mode: "vocal_to_song", label: "Vocal only" },
            { mode: "music_to_music", label: "Music to New Music" },
            { mode: "full_song", label: "Full Song" }
          ] as Array<{ mode: ArrangementMode; label: string }>).map((option) => (
            <Pressable key={option.mode} style={({ pressed }) => [styles.fileOption, pressed && styles.touchPressedBlue, arrangementMode === option.mode && styles.fileOptionActive]} onPress={() => setArrangementMode(option.mode)}>
              <Text style={[styles.fileOptionText, arrangementMode === option.mode && styles.fileOptionTextActive]}>{option.label}</Text>
            </Pressable>
          ))}
        </View>
        <Text style={styles.helperNote}>{arrangementMode === "music_to_music" ? (preserveOriginalVocal ? "Skarly will separate the singer, transform the clean music reference, then mix the original singer into every final version." : "Skarly will separate vocals when detected and return five new instrumental versions.") : arrangementMode === "full_song" ? "Skarly will map the full song, isolate the lead when available, and build a new backing." : "Skarly will map your vocal, then build a full backing tune around it."}</Text>
        {arrangementMode !== "vocal_to_song" && (
          <>
            <Text style={styles.sectionLabel}>Reference Strength</Text>
            <View style={styles.fileOptionRow}>
              {[0.25, 0.35, 0.45].map((value) => (
                <Pressable key={value} style={({ pressed }) => [styles.fileOption, pressed && styles.touchPressedBlue, referenceStrength === value && styles.fileOptionActive]} onPress={() => setReferenceStrength(value)}>
                  <Text style={[styles.fileOptionText, referenceStrength === value && styles.fileOptionTextActive]}>{value.toFixed(2)}</Text>
                </Pressable>
              ))}
            </View>
          </>
        )}
        {(arrangementMode === "music_to_music" || arrangementMode === "full_song") && (
          <>
            <Text style={styles.sectionLabel}>Singer Output</Text>
            <View style={styles.fileOptionRow}>
              {[
                { value: true, label: "Keep singer" },
                { value: false, label: "Instrumental only" }
              ].map((option) => (
                <Pressable key={option.label} style={({ pressed }) => [styles.fileOption, pressed && styles.touchPressedBlue, preserveOriginalVocal === option.value && styles.fileOptionActive]} onPress={() => setPreserveOriginalVocal(option.value)}>
                  <Text style={[styles.fileOptionText, preserveOriginalVocal === option.value && styles.fileOptionTextActive]}>{option.label}</Text>
                </Pressable>
              ))}
            </View>
          </>
        )}
      </Card>
      <Card centered>
        <View style={styles.bigIcon}><IconSymbol name="upload" size={30} /></View>
        <Text style={styles.cardTitle}>{uploadBusy ? "Uploading Audio" : selectedFile ? "Audio Selected" : "Choose Audio File"}</Text>
        <Text style={styles.subtitle}>{selectedFile ? `${selectedFile.label} | ${getArrangementModeLabel(selectedFile.arrangementMode)}` : uploadBusy ? "Sending audio to Cloud Storage." : "WAV, MP3, M4A, AAC, or FLAC. Pick the input mode above before generation."}</Text>
        {selectedFile && <OwnershipChip status="Ready" label={selectedFile.uploaded ? "Uploaded" : "Ready"} />}
      </Card>
      <PrimaryButton label={uploadBusy ? "Uploading..." : "Choose Audio File"} icon="upload" onPress={chooseLocalFile} disabled={uploadBusy} />
      <Text style={styles.helperNote}>Your upload stays private. Music mode keeps the separated singer by default; choose Instrumental only when you do not want vocals in the final versions.</Text>
      {uploadNotice && <StatusNotice title="Upload Check" body={uploadNotice} icon={selectedFile ? "success" : "error"} />}
      {selectedFile && <SecondaryButton label="Remove Selected File" icon="trash" onPress={() => {
        setSelectedFile(null);
        setUploadNotice("Selection removed. Choose another audio file to continue.");
      }} disabled={uploadBusy} />}
      <PrimaryButton label={selectedFile ? "Continue To Skarly" : uploadBusy ? "Upload In Progress" : "Select A File First"} icon="continue" onPress={() => selectedFile && onNext(selectedFile)} disabled={!selectedFile || uploadBusy} />
      <SecondaryButton label="Return Home" icon="home" onPress={onHome} />
    </View>
  );
}

function SkarlyDetectedConfirm({
  source,
  analysis,
  busy,
  errorMessage,
  onGenreSelect,
  generationIntent,
  setGenerationIntent,
  onBack,
  onRefresh,
  onNext
}: {
  source: InputSource;
  analysis: SkarlyAnalyzeResponse | null;
  busy: boolean;
  errorMessage?: string | null;
  onGenreSelect: (genre: Genre) => void;
  generationIntent: GenerationIntent;
  setGenerationIntent: React.Dispatch<React.SetStateAction<GenerationIntent>>;
  onBack: () => void;
  onRefresh: () => void | Promise<void>;
  onNext: () => void | Promise<void>;
}) {
  const detected = analysis?.detected;
  const selectedLanguage = generationIntent.language || detected?.language || "Hindi";
  const selectedMood = generationIntent.moodTags || detected?.mood || "Sad / Emotional";
  const confirmedGenre = genres.find((genre) => genre.label === generationIntent.genreOverride) ?? null;
  const supportsTrainingFeedback = selectedLanguage === "Hindi" || selectedLanguage === "English";
  const selectedMix = mixPresetOptions.find((option) => option.value === generationIntent.mixPreset) ?? mixPresetOptions[1];
  const hasFullSongReference = detected?.source_profile === "full_song";
  const parsedBpmOverride = Number(generationIntent.bpmOverride);
  const bpmOverrideValid = !generationIntent.bpmOverride.trim()
    || (Number.isFinite(parsedBpmOverride) && parsedBpmOverride >= 40 && parsedBpmOverride <= 220);
  const keyOverrideValid = !generationIntent.keyOverride.trim()
    || /^(C|C#|Db|D|D#|Eb|E|F|F#|Gb|G|G#|Ab|A|A#|Bb|B)\s+(major|minor)$/i.test(generationIntent.keyOverride.trim());
  const musicalCorrectionsValid = bpmOverrideValid && keyOverrideValid;
  const updateIntent = (patch: Partial<GenerationIntent>) => setGenerationIntent((current) => ({ ...current, ...patch }));
  const toggleTrainingTechnique = (technique: string) => updateIntent({
    trainingVocalTechniques: generationIntent.trainingVocalTechniques.includes(technique)
      ? generationIntent.trainingVocalTechniques.filter((value) => value !== technique)
      : [...generationIntent.trainingVocalTechniques, technique]
  });
  return (
    <View>
      <ScreenHeader
        title="Skarly Detected"
        hint={source.arrangementMode === "music_to_music" ? "Confirm the reference analysis before creating five new arrangements." : "Confirm the vocal read before generating five music versions."}
        onBack={onBack}
      />
      <StatusNotice title={busy ? "Analyzing Upload" : "Upload Ready"} body={`${source.label} | ${getArrangementModeLabel(source.arrangementMode)} | ${source.uploaded ? "Cloud uploaded" : "Waiting for upload"}`} icon={busy ? "processing" : "mic"} />
      {errorMessage && <StatusNotice title="Needs Attention" body={errorMessage} icon="error" />}

      <Card>
        <Text style={styles.cardTitle}>Skarly detected:</Text>
        <View style={styles.skarlyDetectedPanel}>
          <DetectedFact label="Language" value={selectedLanguage} />
          <DetectedFact label="Language read" value={skarlyLanguageReadText(detected, busy)} />
          <DetectedFact label="Mood" value={selectedMood} />
          <DetectedFact label="Vocal type" value={detected?.vocal_type ?? (busy ? "Listening" : "Singing")} />
          <DetectedFact label="Tempo" value={detected ? skarlyTempoText(detected) : busy ? "Reading timing" : "Around 84 BPM"} />
          <DetectedFact label="Timing" value={detected ? skarlyTimingText(detected) : busy ? "Finding vocal phrases" : "Phrase timing estimate"} />
          <DetectedFact label="Key" value={detected?.key ?? "Key estimate"} />
          <DetectedFact label={hasFullSongReference ? "Genre hint" : "Style starting point"} value={detected?.genre_hint ?? (hasFullSongReference ? "Listening for genre" : "Choose a style direction")} />
          <DetectedFact label={hasFullSongReference ? "Genre read" : "Style source"} value={skarlyGenreReadText(detected, busy)} />
          <DetectedFact label="Vocal input" value={detected?.input_quality ?? (busy ? "Checking level" : "Ready")} />
          <DetectedFact label="Melody MIDI" value={detected?.melody_midi_status ?? "pending"} />
        </View>
      </Card>

      {detected?.input_quality_note ? (
        <StatusNotice
          title={`Vocal Check: ${detected.input_quality ?? "Ready"}`}
          body={detected.input_quality_note}
          icon={detected.input_quality === "Needs re-record" || detected.input_quality === "Clipping" || detected.input_quality === "Needs attention" ? "error" : detected.input_quality === "Quiet" ? "waveform" : "success"}
        />
      ) : null}

      {detected ? <SkarlySongMap detected={detected} /> : null}

      <Card>
        <Row title="Confirm Style Direction" meta={confirmedGenre ? `${confirmedGenre.label} will steer all five arrangements` : `${detected?.genre_hint ?? "Skarly's detected style"} will be used`} />
        <View style={styles.optionWrap}>
          <Pressable style={({ pressed }) => [styles.intentChip, pressed && styles.touchPressedBlue, !confirmedGenre && styles.intentChipActive]} onPress={() => updateIntent({ genreOverride: "", trainingOptIn: false })}>
            <Text style={[styles.intentChipText, !confirmedGenre && styles.intentChipTextActive]}>Use detected</Text>
          </Pressable>
          {genres.map((genre) => (
            <Pressable key={genre.id} style={({ pressed }) => [styles.intentChip, pressed && styles.touchPressedBlue, confirmedGenre?.id === genre.id && styles.intentChipActive]} onPress={() => {
              onGenreSelect(genre);
              updateIntent({ genreOverride: genre.label });
            }}>
              <Text style={[styles.intentChipText, confirmedGenre?.id === genre.id && styles.intentChipTextActive]}>{genre.label}</Text>
            </Pressable>
          ))}
        </View>
        <Text style={styles.helperNote}>Your confirmed style overrides a weak audio guess and selects a producer batch built for this song—five different arrangements, not five copies.</Text>
        <Text style={styles.sectionLabel}>Improve Hindi / English genre reads</Text>
        <Pressable disabled={!confirmedGenre || !supportsTrainingFeedback} style={({ pressed }) => [styles.intentChip, (!confirmedGenre || !supportsTrainingFeedback) && styles.intentChipDisabled, pressed && supportsTrainingFeedback && styles.touchPressedBlue, generationIntent.trainingOptIn && styles.intentChipActive]} onPress={() => updateIntent({ trainingOptIn: !generationIntent.trainingOptIn })}>
          <Text style={[styles.intentChipText, generationIntent.trainingOptIn && styles.intentChipTextActive]}>{generationIntent.trainingOptIn ? "Training contribution enabled" : "Keep my vocal private"}</Text>
        </Pressable>
        <Text style={styles.helperNote}>{!confirmedGenre ? "Confirm a genre first. Training contribution is unavailable for an unlabelled vocal." : !supportsTrainingFeedback ? "Training contribution currently accepts creator-confirmed Hindi or English labels only. Your vocal stays private." : generationIntent.trainingOptIn ? "You confirm you own this vocal and allow Skarly to retain the normalized vocal with your reviewed labels for the shared audio encoder heads." : "Off by default. Enable only if you own this vocal and want it retained with confirmed Hindi or English labels."}</Text>
        {generationIntent.trainingOptIn ? (
          <View>
            <Text style={styles.sectionLabel}>Confirm Delivery</Text>
            <View style={styles.optionWrap}>
              {trainingDeliveryOptions.map((value) => (
                <Pressable key={value} style={({ pressed }) => [styles.intentChip, pressed && styles.touchPressedBlue, generationIntent.trainingSingingSpeech === value && styles.intentChipActive]} onPress={() => updateIntent({ trainingSingingSpeech: value })}>
                  <Text style={[styles.intentChipText, generationIntent.trainingSingingSpeech === value && styles.intentChipTextActive]}>{value}</Text>
                </Pressable>
              ))}
            </View>
            <Text style={styles.sectionLabel}>Confirm Vocal Technique</Text>
            <View style={styles.optionWrap}>
              {trainingTechniqueOptions.map((value) => (
                <Pressable key={value} style={({ pressed }) => [styles.intentChip, pressed && styles.touchPressedBlue, generationIntent.trainingVocalTechniques.includes(value) && styles.intentChipActive]} onPress={() => toggleTrainingTechnique(value)}>
                  <Text style={[styles.intentChipText, generationIntent.trainingVocalTechniques.includes(value) && styles.intentChipTextActive]}>{value}</Text>
                </Pressable>
              ))}
            </View>
            <Text style={styles.sectionLabel}>Confirm Tempo Family</Text>
            <View style={styles.optionWrap}>
              {trainingTempoOptions.map((value) => (
                <Pressable key={value} style={({ pressed }) => [styles.intentChip, pressed && styles.touchPressedBlue, generationIntent.trainingTempoFamily === value && styles.intentChipActive]} onPress={() => updateIntent({ trainingTempoFamily: value })}>
                  <Text style={[styles.intentChipText, generationIntent.trainingTempoFamily === value && styles.intentChipTextActive]}>{value}</Text>
                </Pressable>
              ))}
            </View>
            <Text style={styles.sectionLabel}>Confirm Melodic Character</Text>
            <View style={styles.optionWrap}>
              {trainingMelodicOptions.map((value) => (
                <Pressable key={value} style={({ pressed }) => [styles.intentChip, pressed && styles.touchPressedBlue, generationIntent.trainingMelodicCharacter === value && styles.intentChipActive]} onPress={() => updateIntent({ trainingMelodicCharacter: value })}>
                  <Text style={[styles.intentChipText, generationIntent.trainingMelodicCharacter === value && styles.intentChipTextActive]}>{value}</Text>
                </Pressable>
              ))}
            </View>
            <Text style={styles.helperNote}>These labels are stored only with explicit consent. Unselected heads remain unknown and will not be guessed for training.</Text>
          </View>
        ) : null}
        <Text style={styles.sectionLabel}>Correct BPM and Key (optional)</Text>
        <View style={styles.buttonRow}>
          <TextInput
            value={generationIntent.bpmOverride}
            onChangeText={(bpmOverride) => updateIntent({ bpmOverride })}
            placeholder={detected?.bpm ? `Detected ${detected.bpm} BPM` : "BPM 40-220"}
            placeholderTextColor={colors.muted}
            keyboardType="decimal-pad"
            style={[styles.input, { flex: 1 }]}
            editable={!busy}
          />
          <TextInput
            value={generationIntent.keyOverride}
            onChangeText={(keyOverride) => updateIntent({ keyOverride })}
            placeholder={detected?.key ? `Detected ${detected.key}` : "e.g. D minor"}
            placeholderTextColor={colors.muted}
            autoCapitalize="words"
            style={[styles.input, { flex: 1 }]}
            editable={!busy}
          />
        </View>
        {!bpmOverrideValid ? <Text style={styles.errorText}>BPM must be between 40 and 220.</Text> : null}
        {!keyOverrideValid ? <Text style={styles.errorText}>Use a key and scale such as D minor, Bb major, or F# minor.</Text> : null}
        <Text style={styles.helperNote}>Leave these blank to use Skarly's measured values. Confirmed corrections are stored with the generation and used by all five producers.</Text>
        {(generationIntent.bpmOverride || generationIntent.keyOverride) ? (
          <SecondaryButton label="Use Detected BPM & Key" icon="retry" onPress={() => updateIntent({ bpmOverride: "", keyOverride: "" })} compact />
        ) : null}
        <Row title="Change Language" meta={selectedLanguage} />
        <View style={styles.optionWrap}>
          {languageOptions.map((language) => (
            <Pressable key={language} style={({ pressed }) => [styles.intentChip, pressed && styles.touchPressedBlue, selectedLanguage === language && styles.intentChipActive]} onPress={() => updateIntent({ language, trainingOptIn: language === "Hindi" || language === "English" ? generationIntent.trainingOptIn : false })}>
              <Text style={[styles.intentChipText, selectedLanguage === language && styles.intentChipTextActive]}>{language}</Text>
            </Pressable>
          ))}
        </View>
        <Text style={styles.sectionLabel}>Change Mood</Text>
        <View style={styles.optionWrap}>
          {moodOptions.map((mood) => (
            <Pressable key={mood} style={({ pressed }) => [styles.intentChip, pressed && styles.touchPressedBlue, selectedMood === mood && styles.intentChipActive]} onPress={() => updateIntent({ moodTags: mood })}>
              <Text style={[styles.intentChipText, selectedMood === mood && styles.intentChipTextActive]}>{mood}</Text>
            </Pressable>
          ))}
        </View>
        <Text style={styles.sectionLabel}>Mix Focus</Text>
        <View style={styles.optionWrap}>
          {mixPresetOptions.map((option) => (
            <Pressable key={option.value} style={({ pressed }) => [styles.intentChip, pressed && styles.touchPressedBlue, generationIntent.mixPreset === option.value && styles.intentChipActive]} onPress={() => updateIntent({ mixPreset: option.value })}>
              <Text style={[styles.intentChipText, generationIntent.mixPreset === option.value && styles.intentChipTextActive]}>{option.label}</Text>
            </Pressable>
          ))}
        </View>
        <Text style={styles.helperNote}>Default: {selectedMix.label}. Balanced keeps the beat audible; Beat Forward lifts drums and music when a loud vocal is taking over; Vocal Up and Soft Bed keep the singer more prominent.</Text>
      </Card>

      {analysis?.warnings.length ? (
        <StatusNotice title="Analysis Notes" body={analysis.warnings.slice(0, 2).join(" ")} icon="waveform" />
      ) : null}
      <View style={styles.buttonRow}>
        <SecondaryButton label={busy ? "Analyzing" : "Analyze Again"} icon="retry" onPress={onRefresh} disabled={busy} compact />
        <PrimaryButton label="Generate 5 Versions" icon="generate" onPress={onNext} disabled={busy || !source.rawAudioPath || !musicalCorrectionsValid} compact golden />
      </View>
    </View>
  );
}

function ProducerDirections({
  profiles,
  selectedProfileIds,
  analysis,
  mixPreset,
  busy,
  errorMessage,
  onReplace,
  onBack,
  onGenerate
}: {
  profiles: SkarlyProducerProfile[];
  selectedProfileIds: string[];
  analysis: SkarlyAnalyzeResponse | null;
  mixPreset: MixPreset;
  busy: boolean;
  errorMessage?: string | null;
  onReplace: (index: number, profileId: string) => void;
  onBack: () => void;
  onGenerate: () => void | Promise<void>;
}) {
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const selectedProfiles = selectedProfileIds.map((profileId) => profiles.find((profile) => profile.profile_id === profileId)).filter(Boolean) as SkarlyProducerProfile[];
  const genreMap = analysis?.song_intelligence_map?.genre_probabilities ?? analysis?.detected.song_intelligence_map?.genre_probabilities ?? {};
  const likelyStyles = Object.entries(genreMap)
    .sort((left, right) => right[1] - left[1])
    .slice(0, 3)
    .map(([name, confidence]) => `${name.replace(/_/g, " ")} ${Math.round(confidence * 100)}%`)
    .join(" · ");
  return (
    <View>
      <ScreenHeader title="Choose 5 Producers" hint="Each card uses a different instrument palette, groove, bass movement, energy arc, and stereo treatment." onBack={onBack} />
      {likelyStyles ? <StatusNotice title="Likely Styles" body={likelyStyles} icon="waveform" /> : null}
      {errorMessage ? <StatusNotice title="Needs Attention" body={errorMessage} icon="error" /> : null}
      {!profiles.length ? <StatusNotice title="Loading Producer Desk" body="Reading the available producer blueprints from your local Skarly backend." icon="processing" /> : null}
      {selectedProfileIds.map((profileId, index) => {
        const profile = profiles.find((item) => item.profile_id === profileId);
        if (!profile) return null;
        const isEditing = editingIndex === index;
        return (
          <View key={`${index}-${profileId}`} style={styles.skarlyVersionCard}>
            <View style={styles.row}>
              <View style={styles.trackTextBlock}>
                <Text style={styles.cardTitle}>{index + 1}. {profile.name}</Text>
                <Text style={styles.metaText}>{profile.instruments.join(" · ")}</Text>
              </View>
              <OwnershipChip status="Ready" label={profile.mix_mode.replace(/_/g, " ")} />
            </View>
            <DetectedFact label="Energy" value={profile.energy} />
            <DetectedFact label="Rhythm" value={profile.rhythm_character} />
            <Text style={styles.helperNote}>{profile.blueprint.intro_treatment} · {profile.blueprint.chorus_density}</Text>
            <SecondaryButton label={isEditing ? "Close Replacements" : "Replace Producer"} icon={isEditing ? "back" : "regenerate"} onPress={() => setEditingIndex(isEditing ? null : index)} compact />
            {isEditing ? (
              <View style={styles.optionWrap}>
                {profiles.map((option) => {
                  const usedElsewhere = selectedProfileIds.some((selectedId, selectedIndex) => selectedId === option.profile_id && selectedIndex !== index);
                  return (
                    <Pressable key={option.profile_id} disabled={usedElsewhere} style={({ pressed }) => [styles.intentChip, usedElsewhere && styles.intentChipDisabled, option.profile_id === profileId && styles.intentChipActive, pressed && !usedElsewhere && styles.touchPressedBlue]} onPress={() => {
                      onReplace(index, option.profile_id);
                      setEditingIndex(null);
                    }}>
                      <Text style={[styles.intentChipText, option.profile_id === profileId && styles.intentChipTextActive]}>{option.name}</Text>
                    </Pressable>
                  );
                })}
              </View>
            ) : null}
          </View>
        );
      })}
      <Card>
        <Row title="Producer Contract" meta={`${selectedProfiles.length}/5 unique blueprints · ${mixPresetOptions.find((item) => item.value === mixPreset)?.label ?? "Balanced"} mix`} chip={selectedProfiles.length === 5 ? "Ready" : "Processing"} />
        <Text style={styles.helperNote}>The complete decoded vocal duration is the source of truth. Skarly will reject a mismatched duration and will not silently crop your song.</Text>
      </Card>
      <View style={styles.buttonRow}>
        <SecondaryButton label="Back To Analysis" icon="back" onPress={onBack} compact />
        <PrimaryButton label="Generate 5 Versions" icon="generate" onPress={onGenerate} disabled={busy || selectedProfiles.length !== 5} compact golden />
      </View>
    </View>
  );
}

function DetectedFact({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.skarlyFactRow}>
      <Text style={styles.metaText}>{label}</Text>
      <Text style={styles.skarlyFactValue}>{value}</Text>
    </View>
  );
}

function skarlyLanguageReadText(detected?: SkarlyDetected | null, busy = false): string {
  if (!detected) return busy ? "Classifying language" : "Language classifier ready";
  const source = detected.classification_source === "shared_audio_encoder" ? "shared audio AI" : detected.classification_source === "local_cnn" ? "local CNN" : detected.classification_source === "user_confirmed" ? "confirmed" : "audio read";
  const confidence = typeof detected.language_confidence === "number" ? ` ${Math.round(detected.language_confidence * 100)}%` : "";
  return `${source}${confidence}`;
}

function skarlyGenreReadText(detected?: SkarlyDetected | null, busy = false): string {
  if (!detected) return busy ? "Classifying genre" : "Genre classifier ready";
  const source = detected.genre_source === "user_confirmed" ? "creator confirmed" : detected.genre_source === "shared_audio_encoder" ? "shared audio AI" : detected.genre_source === "local_cnn" ? "local CNN" : "audio read";
  if (detected.source_profile === "vocal_only" && detected.genre_source !== "user_confirmed") return "confirm your style";
  const confidence = typeof detected.genre_confidence === "number" ? ` ${Math.round(detected.genre_confidence * 100)}%` : "";
  return `${source}${confidence}`;
}

function SkarlySongMap({ detected }: { detected: SkarlyDetected }) {
  const scopeSeconds = Math.max(0, Math.round(Number(detected.analysis_scope_seconds ?? 0)));
  const songMap = detected.song_intelligence_map;
  const mapDuration = Math.max(0, Number(songMap?.duration_seconds ?? detected.analysis_scope_seconds ?? 0));
  const intelligence = songMap?.audio_intelligence ?? detected.audio_intelligence;
  const likelyStyles = Object.entries(songMap?.genre_probabilities ?? {})
    .sort((left, right) => right[1] - left[1])
    .slice(0, 3)
    .map(([name, confidence]) => `${name.replace(/_/g, " ")} ${Math.round(confidence * 100)}%`)
    .join(" · ");
  const sections = (detected.song_structure ?? []).map((section, index) => {
    const label = String(section.name ?? section.section ?? `Part ${index + 1}`).replace(/_/g, " ");
    const start = Number(section.start_seconds ?? section.start ?? 0);
    const end = Number(section.end_seconds ?? section.end ?? start);
    return {
      id: `${label}-${index}`,
      label,
      start: Number.isFinite(start) ? start : 0,
      end: Number.isFinite(end) ? end : start,
      span: Math.max(1, end - start)
    };
  }).filter((section) => Number.isFinite(section.start) && Number.isFinite(section.end));

  return (
    <Card>
      <Row
        title="Full Song Map"
        meta={scopeSeconds ? `${scopeSeconds}s analyzed across ${sections.length || "all"} detected sections` : "Preparing full-vocal timing map"}
        chip={sections.length ? "Ready" : "Processing"}
      />
      {songMap ? (
        <View style={styles.skarlyDetectedPanel}>
          <DetectedFact label="Vocal range" value={`${songMap.vocal_range.lowest_note ?? "?"} – ${songMap.vocal_range.highest_note ?? "?"}`} />
          <DetectedFact label="Mapped tempo" value={`${songMap.tempo.bpm ? `${songMap.tempo.bpm.toFixed(1)} BPM` : "Needs confirmation"}${songMap.tempo.source ? ` · ${songMap.tempo.source.replace(/_/g, " ")}` : ""}`} />
          <DetectedFact label="Tempo confidence" value={`${Math.round(songMap.tempo.confidence * 100)}%${songMap.tempo.rubato ? " · flexible/rubato" : ""}`} />
          <DetectedFact label="Mapped key" value={`${songMap.tonality.key} ${songMap.tonality.scale}${songMap.tonality.source ? ` · ${songMap.tonality.source.replace(/_/g, " ")}` : ""}`} />
          <DetectedFact label="Key confidence" value={`${Math.round(songMap.tonality.confidence * 100)}%`} />
          <DetectedFact label="Phrase map" value={`${songMap.phrases.length} phrases · ${songMap.energy_curve.length} energy points · ${songMap.melody_curve.length} melody points`} />
          <DetectedFact label="Melody detail" value={`${songMap.stable_notes?.length ?? 0} stable notes · ${songMap.pitch_slides?.length ?? 0} slides · ${songMap.ornamentation?.length ?? 0} ornament candidates`} />
          <DetectedFact label="Repeated motifs" value={`${songMap.melodic_motifs?.length ?? 0} melodic · ${songMap.lyrical_motifs?.length ?? 0} lyrical`} />
          <DetectedFact label="Likely styles" value={likelyStyles || "Confirmation required"} />
          {intelligence ? <DetectedFact label="AI representation" value={`ACE-Step shared encoder Â· ${intelligence.windows_analysed} full-song windows`} /> : null}
          {intelligence?.singing_speech ? <DetectedFact label="Delivery head" value={`${intelligence.singing_speech}${typeof intelligence.singing_speech_confidence === "number" ? ` ${Math.round(intelligence.singing_speech_confidence * 100)}%` : ""}`} /> : null}
          {intelligence?.tempo_family ? <DetectedFact label="Tempo family head" value={intelligence.tempo_family} /> : null}
          {intelligence?.melodic_character ? <DetectedFact label="Melodic character head" value={intelligence.melodic_character} /> : null}
          {intelligence ? <DetectedFact label="Model confidence" value={intelligence.requires_confirmation ? "Creator confirmation required" : "Calibrated and in distribution"} /> : null}
        </View>
      ) : null}
      {songMap ? <SongMapWaveform energyCurve={songMap.energy_curve} phrases={songMap.phrases} durationSeconds={mapDuration} /> : null}
      {sections.length ? (
        <View style={styles.songMapTrack}>
          {sections.map((section, index) => (
            <View key={section.id} style={[styles.songMapSegment, { flex: section.span }, index % 2 === 1 && styles.songMapSegmentAlt]}>
              <Text style={styles.songMapLabel} numberOfLines={2}>{section.label}</Text>
              <Text style={styles.songMapTime}>{Math.round(section.start)}–{Math.round(section.end)}s</Text>
            </View>
          ))}
        </View>
      ) : (
        <Text style={styles.helperNote}>Skarly will map the intro, verses, hooks, bridge, and outro before it plans the five arrangements.</Text>
      )}
      <Text style={styles.helperNote}>The producer prompts follow this map, leaving space during sung phrases and building only where the song can support it.</Text>
    </Card>
  );
}

function SongMapWaveform({
  energyCurve,
  phrases,
  durationSeconds
}: {
  energyCurve: Array<Record<string, unknown>>;
  phrases: Array<Record<string, unknown>>;
  durationSeconds: number;
}) {
  const peaks = useMemo(() => energyCurve.map((point) => {
    const value = Number(point.relative_energy ?? point.energy ?? 0);
    return Number.isFinite(value) ? Math.max(0, Math.min(1, value)) : 0;
  }), [energyCurve]);
  const inferredDuration = useMemo(() => Math.max(
    durationSeconds,
    ...energyCurve.map((point) => Number(point.time_seconds ?? 0)).filter(Number.isFinite),
    ...phrases.map((phrase) => Number(phrase.end_seconds ?? phrase.end ?? 0)).filter(Number.isFinite)
  ), [durationSeconds, energyCurve, phrases]);
  const phraseWindows = useMemo(() => phrases.map((phrase, index) => {
    const start = Number(phrase.start_seconds ?? phrase.start ?? 0);
    const end = Number(phrase.end_seconds ?? phrase.end ?? start);
    return {
      id: String(phrase.phrase ?? index),
      start: Number.isFinite(start) ? Math.max(0, start) : 0,
      end: Number.isFinite(end) ? Math.max(start, end) : start
    };
  }).filter((phrase) => phrase.end > phrase.start), [phrases]);
  const bars = useMemo(() => downsamplePeaks(peaks, 88), [peaks]);
  const displayBars = bars.length ? bars : Array.from({ length: 88 }, () => 0.04);
  const width = 352;
  const height = 68;
  const gap = 1.4;
  const barWidth = width / Math.max(1, displayBars.length) - gap;
  const timelineSeconds = Math.max(0.001, inferredDuration);

  return (
    <View style={styles.songMapWaveformPanel}>
      <View style={styles.waveformPanelHeader}>
        <Text style={styles.metaText}>Full-vocal energy and phrase map</Text>
        <Text style={styles.waveformPointCount}>{phraseWindows.length} phrase markers</Text>
      </View>
      <View style={styles.songMapWaveformGraph}>
        <Svg width="100%" height={height} viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none">
          {phraseWindows.map((phrase) => {
            const x = Math.min(width, phrase.start / timelineSeconds * width);
            const endX = Math.min(width, phrase.end / timelineSeconds * width);
            return (
              <React.Fragment key={phrase.id}>
                <Rect x={x} y={2} width={Math.max(1, endX - x)} height={height - 4} rx={2} fill="#c6aa6a" opacity={0.09} />
                <Rect x={x} y={2} width={1.25} height={height - 4} rx={0.5} fill="#c6aa6a" opacity={0.9} />
              </React.Fragment>
            );
          })}
          {displayBars.map((peak, index) => {
            const safePeak = Math.max(0.03, Math.min(1, Number.isFinite(peak) ? peak : 0));
            const barHeight = Math.max(3, safePeak * (height - 12));
            return (
              <Rect
                key={`${index}-${safePeak.toFixed(3)}`}
                x={index * (barWidth + gap)}
                y={(height - barHeight) / 2}
                width={Math.max(1, barWidth)}
                height={barHeight}
                rx={1.6}
                fill="#7bb7ff"
                opacity={bars.length ? 0.88 : 0.18}
              />
            );
          })}
        </Svg>
      </View>
      <Text style={styles.helperNote}>Gold regions show detected vocal phrases; vertical ticks mark phrase starts across the complete recording.</Text>
    </View>
  );
}

function ChooseGenre({
  source,
  selected,
  onSelect,
  generationIntent,
  setGenerationIntent,
  onBack,
  onNext
}: {
  source: InputSource;
  selected: Genre;
  onSelect: (genre: Genre) => void;
  generationIntent: GenerationIntent;
  setGenerationIntent: React.Dispatch<React.SetStateAction<GenerationIntent>>;
  onBack: () => void;
  onNext: () => void;
}) {
  const selectedMix = mixPresetOptions.find((option) => option.value === generationIntent.mixPreset) ?? mixPresetOptions[0];
  const updateIntent = (patch: Partial<GenerationIntent>) => setGenerationIntent((current) => ({ ...current, ...patch }));
  return (
    <View>
      <ScreenHeader
        title={source.arrangementMode === "music_to_music" ? "Music To New Music" : "Vocal To Music"}
        hint={source.arrangementMode === "music_to_music" ? "Choose a new style while Skarly preserves only the broad timing and energy." : "Choose the music language, style, and mix direction."}
        onBack={onBack}
      />
      <StatusNotice title={getArrangementModeLabel(source.arrangementMode)} body={`${source.label} | ${source.detail} | ${summarizeGenerationIntent(generationIntent)}`} icon={source.arrangementMode === "music_to_music" ? "vibe" : source.arrangementMode === "full_song" ? "waveform" : "mic"} />
      <View style={styles.genreGrid}>
        {genres.map((genre) => (
          <GenreTile key={genre.id} genre={genre} selected={genre.id === selected.id} onPress={() => onSelect(genre)} />
        ))}
      </View>
      <Card>
        <Row title="Song Direction" meta={`${generationIntent.language} | ${generationIntent.productionStyle === "Auto" ? selected.label : generationIntent.productionStyle}`} />
        <Text style={styles.sectionLabel}>Language</Text>
        <View style={styles.optionWrap}>
          {languageOptions.map((language) => (
            <Pressable key={language} style={({ pressed }) => [styles.intentChip, pressed && styles.touchPressedBlue, generationIntent.language === language && styles.intentChipActive]} onPress={() => updateIntent({ language })}>
              <Text style={[styles.intentChipText, generationIntent.language === language && styles.intentChipTextActive]}>{language}</Text>
            </Pressable>
          ))}
        </View>
        <TextInput
          value={generationIntent.lyrics}
          onChangeText={(lyrics) => updateIntent({ lyrics })}
          placeholder="Optional lyric emotion or hook lines"
          placeholderTextColor={colors.muted}
          style={[styles.input, styles.lyricsInput]}
          multiline
        />
        <Text style={styles.sectionLabel}>Production Style</Text>
        <View style={styles.optionWrap}>
          {productionStyleOptions.map((style) => (
            <Pressable key={style} style={({ pressed }) => [styles.intentChip, pressed && styles.touchPressedBlue, generationIntent.productionStyle === style && styles.intentChipActive]} onPress={() => updateIntent({ productionStyle: style })}>
              <Text style={[styles.intentChipText, generationIntent.productionStyle === style && styles.intentChipTextActive]}>{style}</Text>
            </Pressable>
          ))}
        </View>
        <TextInput
          value={generationIntent.arrangementStyle}
          onChangeText={(arrangementStyle) => updateIntent({ arrangementStyle })}
          placeholder="Optional arrangement: piano-led cinematic, indie band, tabla fusion"
          placeholderTextColor={colors.muted}
          style={styles.input}
        />
        <TextInput
          value={generationIntent.instruments}
          onChangeText={(instruments) => updateIntent({ instruments })}
          placeholder="Optional instruments, comma separated"
          placeholderTextColor={colors.muted}
          style={styles.input}
        />
        <TextInput
          value={generationIntent.moodTags}
          onChangeText={(moodTags) => updateIntent({ moodTags })}
          placeholder="Optional moods: romantic, devotional, heartbreak"
          placeholderTextColor={colors.muted}
          style={styles.input}
        />
      </Card>
      <Card>
        <Row title="Output Control" meta={`${generationIntent.durationSeconds ? `${generationIntent.durationSeconds}s` : "Auto length"} | ${selectedMix.label}`} />
        <Text style={styles.sectionLabel}>Duration</Text>
        <View style={styles.optionWrap}>
          {durationOptions.map((option) => (
            <Pressable key={option.label} style={({ pressed }) => [styles.intentChip, pressed && styles.touchPressedBlue, generationIntent.durationSeconds === option.value && styles.intentChipActive]} onPress={() => updateIntent({ durationSeconds: option.value })}>
              <Text style={[styles.intentChipText, generationIntent.durationSeconds === option.value && styles.intentChipTextActive]}>{option.label}</Text>
            </Pressable>
          ))}
        </View>
        <Text style={styles.sectionLabel}>Mix Focus</Text>
        <View style={styles.optionWrap}>
          {mixPresetOptions.map((option) => (
            <Pressable key={option.value} style={({ pressed }) => [styles.intentChip, pressed && styles.touchPressedBlue, generationIntent.mixPreset === option.value && styles.intentChipActive]} onPress={() => updateIntent({ mixPreset: option.value })}>
              <Text style={[styles.intentChipText, generationIntent.mixPreset === option.value && styles.intentChipTextActive]}>{option.label}</Text>
            </Pressable>
          ))}
        </View>
        <Text style={styles.helperNote}>ACE-Step creates the backing, Demucs isolates or cleans vocals, and Basic Pitch prepares melody/MIDI hints. AudioCraft stays optional until the local native audio dependency is fixed.</Text>
      </Card>
      <PrimaryButton label="Generate Preview" icon="waveform" onPress={onNext} />
    </View>
  );
}

function Processing({
  genre,
  activeIndex,
  v2Job,
  backendMessage,
  backendMode,
  errorMessage,
  onRetry,
  onBackToGenre,
  onHome
}: {
  genre: Genre;
  activeIndex: number;
  v2Job?: SkarlyV2Job | null;
  backendMessage: string;
  backendMode: BackendMode;
  errorMessage?: string | null;
  onRetry: () => void;
  onBackToGenre: () => void;
  onHome: () => void;
}) {
  const safeIndex = v2Job ? v2ProcessingStepIndex(v2Job) : Math.min(activeIndex, processingSteps.length - 1);
  const stageState = v2Job ? v2ProcessingStageState(v2Job) : processingStageState(safeIndex);
  const liveError = errorMessage || v2Job?.error?.message;
  const hasError = Boolean(liveError);
  const canResume = Boolean(v2Job && v2Job.status !== "failed");
  const detailCopy = hasError ? liveError : backendMode === "api" ? stageState.detail : backendMessage;
  return (
    <View style={styles.processingScreen}>
      <View style={styles.processingHeader}>
        <Text style={styles.title}>{hasError ? "Generation Paused" : "Processing"}</Text>
        <Text style={styles.hint}>{hasError ? (canResume ? "Your source audio and backend job are still saved. Resume without starting over." : "Your source audio is still selected. Retry when the backend is ready.") : stageState.header}</Text>
      </View>

      <ProcessingSigilSystem />
      <ProcessingSquareform activeIndex={safeIndex} genre={genre} />

      <View style={styles.processingGlassCard}>
        <View style={styles.processingStatusRow}>
          <Text style={styles.processingStageTitle}>{hasError ? "Needs Attention" : stageState.title}</Text>
          <Text style={styles.processingPercent}>{hasError ? "!" : `${stageState.percent}%`}</Text>
        </View>
        <Text style={styles.processingStageText}>{detailCopy}</Text>
        <View style={styles.processingProgressTrack}>
          <View style={[styles.processingProgressFill, { width: `${stageState.percent}%` as DimensionValue }]} />
        </View>
      </View>

      <ProcessingStageStack activeIndex={safeIndex} />
      {v2Job ? (
        <Card>
          <DetectedFact label="CUDA device" value={v2Job.cuda_device ?? (v2Job.stage === "verifying_cuda" ? "Checking RTX GPU" : "Waiting for telemetry")} />
          <DetectedFact label="Model" value={v2Job.model ?? "ACE-Step 1.5 Turbo"} />
          <DetectedFact label="Arrangements" value={`${v2Job.completed_arrangements}/${v2Job.total_arrangements || 5}${v2Job.current_arrangement ? ` · working on ${v2Job.current_arrangement}` : ""}`} />
          <DetectedFact label="Completed duration" value={`${v2Job.completed_duration_seconds.toFixed(1)} seconds`} />
        </Card>
      ) : null}
      {hasError && (
        <View style={styles.processingRetryActions}>
          <PrimaryButton label={canResume ? "Resume Generation" : "Retry Generation"} icon="retry" onPress={onRetry} />
          <View style={styles.inlineActions}>
            <SecondaryButton label="Choose Genre" icon="back" onPress={onBackToGenre} />
            <SecondaryButton label="Return Home" icon="home" onPress={onHome} />
          </View>
        </View>
      )}
    </View>
  );
}

function v2ProcessingStepIndex(job: SkarlyV2Job) {
  if (job.status === "ready" || job.stage === "ready") return 5;
  if (job.stage === "preparing_vocal") return 2;
  if (["planning_arrangements", "creating_arrangement", "regenerating_section", "checking_arrangement_diversity"].includes(job.stage)) return 3;
  if (["mixing_original_vocal", "loading_existing_stems", "mixing_vocals", "mastering", "preparing_exports"].includes(job.stage)) return 4;
  return 1;
}

function v2ProcessingStageState(job: SkarlyV2Job) {
  const current = job.current_arrangement ? ` ${job.current_arrangement} of ${job.total_arrangements || 5}` : "";
  const stageCopy: Record<string, { title: string; header: string; detail: string }> = {
    queued: { title: "Queued", header: "Waiting for the local studio", detail: "Your complete vocal is safely queued." },
    validating_input: { title: "Validating Vocal", header: "Checking the complete recording", detail: "Verifying format, duration, loudness, and file integrity." },
    verifying_cuda: { title: "Verifying CUDA", header: "Checking the RTX 5070", detail: "Running the Blackwell CUDA preflight with no CPU fallback." },
    analysing_complete_vocal: { title: "Analysing Vocal", header: "Understanding the complete song", detail: "Reading language, mood, melody, timing, phrases, BPM, and key." },
    building_song_map: { title: "Building Song Map", header: "Mapping the full performance", detail: "Aligning phrases, sections, breaths, silence, energy, and melody." },
    preparing_vocal: { title: "Preparing Vocal", header: "Protecting the original singer", detail: "Creating the clean mixing copy while preserving the upload unchanged." },
    planning_arrangements: { title: "Planning Producers", header: "Building five hard-constrained directions", detail: "Assigning different instruments, grooves, bass movement, energy, and stereo character." },
    creating_arrangement: { title: `Creating Arrangement${current}`, header: "Producing five different music versions", detail: "Generating a complete instrumental timeline that follows the vocal." },
    regenerating_section: { title: `Regenerating Section${current}`, header: "Repainting only the selected instrumental range", detail: "ACE-Step is using the surrounding arrangement as context while keeping the original vocal untouched." },
    mixing_original_vocal: { title: `Remixing Original Vocal${current}`, header: "Putting the same singer back in front", detail: "Skarly verified the untouched backing regions and is mixing the original vocal over the edited instrumental." },
    loading_existing_stems: { title: "Loading Existing Stems", header: "Reusing completed audio", detail: "The instrumental and vocal are being loaded without regenerating them." },
    mixing_vocals: { title: `Mixing Vocal${current}`, header: "Keeping your voice clear and in front", detail: "Applying adaptive phrase-aware ducking and output protection." },
    checking_arrangement_diversity: { title: "Checking Diversity", header: "Comparing all five producers", detail: "Rejecting arrangements that are too close to an earlier backing." },
    mastering: { title: "Mastering", header: "Protecting the final output", detail: "Checking duration, peak level, and vocal-to-music balance." },
    preparing_exports: { title: "Preparing Exports", header: "Finishing the studio files", detail: "Writing final mixes, backing tracks, analysis, and telemetry." },
    ready: { title: "Five Versions Ready", header: "Your producer desk is ready", detail: "Switch instantly between the five synchronized song versions." }
  };
  const copy = stageCopy[job.stage] ?? { title: formatSkarlyV2Stage(job), header: "Skarly is working", detail: formatSkarlyV2Stage(job) };
  return { ...copy, percent: Math.round(job.progress) };
}

function processingStageState(activeIndex: number) {
  const safeIndex = Math.min(activeIndex, processingSteps.length - 1);
  if (safeIndex <= 1) {
    return {
      title: safeIndex === 0 ? "Uploading Audio" : "Reading Source Timing",
      header: "Preparing the source audio",
      detail: safeIndex === 0 ? "Sending your original track into the studio" : "Reading timing, key, energy, and phrase shape",
      percent: safeIndex === 0 ? 12 : 24
    };
  }
  if (safeIndex === 2) {
    return {
      title: "Preparing Source",
      header: "Checking stems and reference audio",
      detail: "Separating vocals when needed and keeping music-only references instrumental",
      percent: 38
    };
  }
  if (safeIndex === 3) {
    return {
      title: "Generating Arrangement",
      header: "Building the new genre bed",
      detail: "Creating section changes, drums, bass, guitar or keys",
      percent: 64
    };
  }
  if (safeIndex === 4) {
    return {
      title: "Mixing Final Track",
      header: "Balancing the final mix",
      detail: "Balancing the source and new instrumental for playback",
      percent: 82
    };
  }
  return {
    title: "Ready To Save",
    header: "Final mix ready",
    detail: "Preparing your finished track for playback",
    percent: 100
  };
}

function ProcessingSigilSystem() {
  const tickAngles = Array.from({ length: 32 }, (_, index) => index * 11.25);
  return (
    <View style={styles.processingSigilSystem}>
      <Svg width={286} height={286} viewBox="0 0 286 286">
        <Defs>
          <LinearGradient id="processingSigilMetal" x1="0" y1="0" x2="1" y2="1">
            <Stop offset="0" stopColor="#f5f5f7" stopOpacity="0.94" />
            <Stop offset="0.48" stopColor="#d1d1d6" stopOpacity="0.82" />
            <Stop offset="1" stopColor="#6f6f74" stopOpacity="0.72" />
          </LinearGradient>
          <LinearGradient id="processingRingAccent" x1="0" y1="0" x2="1" y2="1">
            <Stop offset="0" stopColor="#f5f5f7" stopOpacity="0.12" />
            <Stop offset="0.58" stopColor="#d1d1d6" stopOpacity="0.28" />
            <Stop offset="1" stopColor="#c6aa6a" stopOpacity="0.18" />
          </LinearGradient>
        </Defs>
        <Circle cx="143" cy="143" r="46" stroke="rgba(209,209,214,0.13)" strokeWidth="1" fill="none" />
        <Circle cx="143" cy="143" r="70" stroke="rgba(209,209,214,0.12)" strokeWidth="1" fill="none" />
        <Circle cx="143" cy="143" r="94" stroke="rgba(209,209,214,0.09)" strokeWidth="1" fill="none" />
        <Circle cx="143" cy="143" r="116" stroke="rgba(209,209,214,0.06)" strokeWidth="1" fill="none" />
        <Path d="M45 143 H104 M182 143 H241" stroke="rgba(209,209,214,0.14)" strokeWidth="1" strokeLinecap="round" />
        <Path d="M143 45 V104 M143 182 V241" stroke="rgba(209,209,214,0.12)" strokeWidth="1" strokeLinecap="round" />
        <Path d="M57 132 C63 82 101 50 143 50 C190 50 224 79 231 127" stroke="url(#processingRingAccent)" strokeWidth="2" fill="none" strokeLinecap="round" />
        <Path d="M229 158 C218 209 181 235 143 235 C99 235 65 209 56 160" stroke="rgba(209,209,214,0.1)" strokeWidth="1.6" fill="none" strokeLinecap="round" />
        {tickAngles.map((angle, index) => {
          const rad = (angle * Math.PI) / 180;
          const inner = index % 4 === 0 ? 107 : 111;
          const outer = 116;
          const x1 = 143 + Math.cos(rad) * inner;
          const y1 = 143 + Math.sin(rad) * inner;
          const x2 = 143 + Math.cos(rad) * outer;
          const y2 = 143 + Math.sin(rad) * outer;
          return <Path key={`tick-${angle}`} d={`M${x1.toFixed(1)} ${y1.toFixed(1)} L${x2.toFixed(1)} ${y2.toFixed(1)}`} stroke="rgba(209,209,214,0.12)" strokeWidth={index % 4 === 0 ? 1.1 : 0.7} strokeLinecap="round" />;
        })}
        <Circle cx="76" cy="201" r="7.5" fill="rgba(2,2,2,0.92)" stroke="rgba(198,170,106,0.46)" strokeWidth="1.4" />
        <Circle cx="210" cy="88" r="3.2" fill="rgba(198,170,106,0.68)" />
        <Path d="M144 81 C154 101 130 113 149 137 C166 158 148 178 136 207 C133 181 145 167 127 147 C110 127 132 105 144 81Z" fill="url(#processingSigilMetal)" />
        <Path d="M142 94 C147 111 134 124 150 139 C162 151 151 168 141 188" stroke="rgba(2,2,2,0.82)" strokeWidth={8} strokeLinecap="round" fill="none" />
        <Path d="M142 82 V204" stroke="rgba(245,245,247,0.22)" strokeWidth={1.1} />
        <Circle cx="128" cy="178" r="13" fill="rgba(2,2,2,0.94)" stroke="rgba(209,209,214,0.68)" strokeWidth={2} />
        <Path d="M128 191 L125 209 M134 190 L135 206 M139 179 L154 183 M144 111 L154 115 M136 137 L121 134" stroke="rgba(2,2,2,0.5)" strokeWidth={2} strokeLinecap="round" />
      </Svg>
    </View>
  );
}

function ProcessingSquareform({ activeIndex, genre }: { activeIndex: number; genre: Genre }) {
  const [phase, setPhase] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => setPhase((current) => (current + 0.18) % 1000), 16);
    return () => clearInterval(timer);
  }, []);

  const bars = 24;
  const activeBoost = Math.min(activeIndex + 1, 5);
  return (
    <View style={styles.processingConsoleBars}>
      {Array.from({ length: bars }).map((_, index) => {
        const wave = Math.abs(Math.sin((index * 0.72 + phase) * 0.92)) + Math.abs(Math.sin(index * 0.31 + phase * 1.35));
        const height = 5 + wave * (7 + activeBoost * 1.7);
        const isAccent = index % 8 === activeIndex % 8 || index % 13 === activeIndex % 6;
        return (
          <View
            key={`console-${index}`}
            style={[
              styles.processingConsoleBar,
              {
                height,
                backgroundColor: isAccent ? genre.color : "rgba(209,209,214,0.46)",
                opacity: isAccent ? 0.55 : 0.28 + wave * 0.2
              }
            ]}
          />
        );
      })}
    </View>
  );
}

function ProcessingStageStack({ activeIndex }: { activeIndex: number }) {
  const stackRows = [
    { label: "01 Upload Received", min: 0, max: 1 },
    { label: "02 Isolating Vocals", min: 2, max: 2 },
    { label: "03 Generating Instrumental", min: 3, max: 3 },
    { label: "04 Mixing Final Track", min: 4, max: 4 },
    { label: "05 Ready To Save", min: 5, max: 5 }
  ];
  return (
    <View style={styles.processingStageStack}>
      {stackRows.map((row) => {
        const isActive = activeIndex >= row.min && activeIndex <= row.max;
        const isDone = activeIndex > row.max;
        return (
          <View key={row.label} style={[styles.processingStackRow, isActive && styles.processingStackRowActive]}>
            <View style={[styles.processingStackIndicator, isDone && styles.processingStackIndicatorDone, isActive && styles.processingStackIndicatorActive]} />
            <Text style={[styles.processingStackText, isDone && styles.processingStackTextDone, isActive && styles.processingStackTextActive]}>{row.label}</Text>
            <View style={styles.processingStackStatusSlot}>
              {isActive ? (
                <View style={styles.processingStackPulse} />
              ) : (
                <View style={[styles.processingStackMiniLine, isDone && styles.processingStackMiniLineDone]} />
              )}
            </View>
          </View>
        );
      })}
    </View>
  );
}

function NameTrack({
  genre,
  trackName,
  setTrackName,
  fileNameMode,
  setFileNameMode,
  onContinue
}: {
  genre: Genre;
  trackName: string;
  setTrackName: (name: string) => void;
  fileNameMode: FileNameMode;
  setFileNameMode: (mode: FileNameMode) => void;
  onContinue: () => void;
}) {
  const hasName = trackName.trim().length > 0;
  const fileName = hasName ? buildFileName(trackName, genre, fileNameMode) : "";
  return (
    <View>
      <ScreenHeader title="Name Demo" hint="Give this structured idea a title before opening the project." />
      <Card>
        <AuraWaveform genre={genre} compact mode="genre" />
        <Text style={styles.cardTitle}>Name your demo project</Text>
        <Text style={styles.subtitle}>This name will appear in Result, Producer Pack, and Idea Vault.</Text>
        <TextInput value={trackName} onChangeText={setTrackName} placeholder="Demo name" placeholderTextColor={colors.muted} style={styles.input} />
        <View style={styles.fileOptionRow}>
          <Pressable style={({ pressed }) => [styles.fileOption, pressed && styles.touchPressedBlue, fileNameMode !== "tag" && styles.fileOptionActive]} onPress={() => setFileNameMode("rename")}>
            <Text style={[styles.fileOptionText, fileNameMode !== "tag" && styles.fileOptionTextActive]}>Keep plain name</Text>
          </Pressable>
          <Pressable style={({ pressed }) => [styles.fileOption, pressed && styles.touchPressedBlue, fileNameMode === "tag" && styles.fileOptionActive]} onPress={() => setFileNameMode("tag")}>
            <Text style={[styles.fileOptionText, fileNameMode === "tag" && styles.fileOptionTextActive]}>Add genre tag</Text>
          </Pressable>
        </View>
        {hasName && <Text style={styles.filePreview}>{fileName}</Text>}
      </Card>
      <PrimaryButton label="Open Demo" icon="success" onPress={onContinue} disabled={!hasName} />
    </View>
  );
}

function NameSuccess({ genre, trackName, fileNameMode, onDone }: { genre: Genre; trackName: string; fileNameMode: FileNameMode; onDone: () => void }) {
  return (
    <View style={styles.centerScreen}>
      <View style={styles.successBubble}>
        <IconSymbol name="success" tone="ink" size={30} />
      </View>
      <Text style={styles.title}>Track named</Text>
      <Text style={styles.subtitle}>{buildFileName(trackName, genre, fileNameMode)}</Text>
      <PrimaryButton label="View Result" icon="continue" onPress={onDone} />
    </View>
  );
}

function FinalVersionMessagePlayer({
  title,
  isPlaying,
  positionMs,
  durationMs,
  onPress
}: {
  title: string;
  isPlaying: boolean;
  positionMs: number;
  durationMs: number;
  onPress: () => void | Promise<void>;
}) {
  const safeDuration = Math.max(1000, durationMs);
  const progress = Math.max(0, Math.min(1, positionMs / safeDuration));
  return (
    <View style={styles.finalVersionMessageCard}>
      <View style={styles.finalVersionMessageAvatar}>
        <Svg viewBox="0 0 24 24" width={28} height={28}>
          <Path d="M5.5 13v-2a6.5 6.5 0 0 1 13 0v2" stroke="#ffffff" strokeWidth={1.8} strokeLinecap="round" fill="none" />
          <Path d="M5.5 12.5h2.8v6H6.9c-.8 0-1.4-.6-1.4-1.4v-4.6Zm13 0h-2.8v6h1.4c.8 0 1.4-.6 1.4-1.4v-4.6Z" stroke="#ffffff" strokeWidth={1.8} strokeLinejoin="round" fill="none" />
        </Svg>
      </View>
      <View style={styles.finalVersionMessageBody}>
        <Text style={styles.finalVersionMessageTitle} numberOfLines={1}>{title}</Text>
        <View style={styles.finalVersionMessageControls}>
          <Pressable
            accessibilityLabel={isPlaying ? "Pause final version preview" : "Play final version preview"}
            style={({ pressed }) => [styles.finalVersionMessagePlay, pressed && styles.finalVersionMessagePlayPressed]}
            onPress={onPress}
          >
            <Svg viewBox="0 0 24 24" width={22} height={22}>
              {isPlaying
                ? <><Rect x="7" y="6" width="3.5" height="12" rx="1" fill="#17231c" /><Rect x="13.5" y="6" width="3.5" height="12" rx="1" fill="#17231c" /></>
                : <Path d="M8.5 6.5 17 12l-8.5 5.5Z" fill="#17231c" />}
            </Svg>
          </Pressable>
          <View style={styles.finalVersionMessageProgressArea}>
            <View style={styles.finalVersionMessageTrack}>
              <View style={[styles.finalVersionMessageFill, { width: `${Math.max(2, progress * 100)}%` as DimensionValue }]} />
              <View style={[styles.finalVersionMessageKnob, { left: `${Math.max(0, Math.min(98, progress * 100))}%` as DimensionValue }]} />
            </View>
            <View style={styles.finalVersionMessageMeta}>
              <Text style={styles.finalVersionMessageTime}>{formatPlayerTime(positionMs)}</Text>
              <Text style={styles.finalVersionMessageTime}>{formatPlayerTime(safeDuration)}  ✓✓</Text>
            </View>
          </View>
        </View>
      </View>
    </View>
  );
}

function SkarlyVersions({
  result,
  selectedIndex,
  source,
  isPlaying,
  activePlaybackUrl,
  mixDurationMs,
  mixPositionMs,
  hasDownloaded,
  hasSaved,
  mixPreset,
  vocalMusicBalance,
  remixBusy,
  regenerationBusy,
  sectionBusy,
  exportBusy,
  setVocalMusicBalance,
  setHasDownloaded,
  setHasSaved,
  showToast,
  onSelect,
  onChooseBest,
  onPlayVersion,
  onRemix,
  onRegenerate,
  onRegenerateSection,
  onExport,
  onFeedback,
  onRemember,
  onDelete,
  onNavigate
}: {
  result: SkarlyGenerateResponse;
  selectedIndex: number;
  source: InputSource;
  isPlaying: boolean;
  activePlaybackUrl: string | null;
  mixDurationMs: number;
  mixPositionMs: number;
  hasDownloaded: boolean;
  hasSaved: boolean;
  mixPreset: MixPreset;
  vocalMusicBalance: number;
  remixBusy: boolean;
  regenerationBusy: boolean;
  sectionBusy: boolean;
  exportBusy: boolean;
  setVocalMusicBalance: (value: number) => void;
  setHasDownloaded: (value: boolean) => void;
  setHasSaved: (value: boolean) => void;
  showToast: (message: string) => void;
  onSelect: (index: number) => void | Promise<void>;
  onChooseBest: (index: number) => void | Promise<void>;
  onPlayVersion: (index: number, kind?: "final" | "backing" | "vocal") => void | Promise<void>;
  onRemix: (index: number) => void | Promise<void>;
  onRegenerate: (index: number, energyDelta?: number, instrumentChange?: string) => void | Promise<void>;
  onRegenerateSection: (index: number, sectionStartSeconds: number, sectionEndSeconds: number, editInstruction: string) => void | Promise<void>;
  onExport: (index: number) => void | Promise<void>;
  onFeedback: (index: number, rating: number) => void | Promise<void>;
  onRemember: (status?: TrackStatus) => void;
  onDelete: () => void;
  onNavigate: (screen: Screen) => void;
}) {
  const [instrumentChange, setInstrumentChange] = useState("");
  const songDuration = result.song_intelligence_map?.duration_seconds ?? 0;
  const [sectionStartText, setSectionStartText] = useState("0.0");
  const [sectionEndText, setSectionEndText] = useState(Math.min(10, songDuration || 10).toFixed(1));
  const [sectionInstruction, setSectionInstruction] = useState("");
  const sectionStart = Number(sectionStartText);
  const sectionEnd = Number(sectionEndText);
  const sectionRangeValid = Number.isFinite(sectionStart)
    && Number.isFinite(sectionEnd)
    && sectionStart >= 0
    && sectionEnd > sectionStart
    && sectionEnd - sectionStart >= 0.5
    && (songDuration <= 0 || sectionEnd <= songDuration + 0.01);
  const selected = result.versions[Math.max(0, Math.min(selectedIndex, result.versions.length - 1))];
  const selectedUrl = backendMediaUrl(selected?.final_mix_url);
  const selectedBackingUrl = backendMediaUrl(selected?.backing_url);
  const selectedVocalUrl = backendMediaUrl(selected?.input_vocal_url ?? result.vocal_url);
  const finalMixIsPlaying = isPlaying && activePlaybackUrl === selectedUrl;
  const backingIsPlaying = isPlaying && activePlaybackUrl === selectedBackingUrl;
  const vocalIsPlaying = isPlaying && activePlaybackUrl === selectedVocalUrl;
  const detected = result.detected;
  const telemetry = result.generation_telemetry;
  const diversity = result.arrangement_diversity;
  const sourcePreparation = result.source_preparation;
  const hasPreservedVocal = Boolean(result.vocal_url || sourcePreparation?.vocal_preserved);
  const isInstrumentalFlow = source.arrangementMode === "music_to_music" && !hasPreservedVocal;
  const finalVersionDurationMs = mixDurationMs || Math.round((result.song_intelligence_map?.duration_seconds ?? 0) * 1000);
  return (
    <View>
      <ScreenHeader title="5 Skarly Versions" hint={isInstrumentalFlow ? "Pick the new instrumental direction you like best." : "Pick the mix where your vocal feels best."} />
      <Card>
        <Row title={isInstrumentalFlow ? "Analyzed Music" : "Detected Vocal"} meta={`${detected.language} | ${detected.mood} | ${skarlyTempoText(detected)}`} chip="Ready" />
        <View style={styles.finalMixMetaRow}>
          <MiniInfo label="Vocal" value={detected.vocal_type} />
          <MiniInfo label="Key" value={detected.key ?? "Estimate"} />
          <MiniInfo label="Generator" value={result.generator_backend} />
        </View>
        <Text style={styles.helperNote}>{source.label}</Text>
      </Card>
      {sourcePreparation ? (
        <Card>
          <Row
            title="Source Preparation"
            meta={`${sourcePreparation.detected_mode.replace(/_/g, " ")} · ${sourcePreparation.separation_status.replace(/_/g, " ")} · ${sourcePreparation.vocal_preserved ? "singer kept" : "clean music"}`}
            chip="Ready"
          />
          <View style={styles.finalMixMetaRow}>
            <MiniInfo label="Vocals" value={sourcePreparation.vocal_detected ? "Detected" : "None"} />
            <MiniInfo label="Singer" value={sourcePreparation.vocal_preserved ? "Preserved" : "Not mixed"} />
            <MiniInfo label="Music input" value={sourcePreparation.instrumental_audio_url ? "Prepared" : "Original"} />
          </View>
          {sourcePreparation.warnings.length ? <Text style={styles.helperNote}>{sourcePreparation.warnings.slice(0, 2).join(" ")}</Text> : null}
        </Card>
      ) : null}
      {telemetry ? (
        <Card>
          <Row title="Local CUDA Generation" meta={`${telemetry.device ?? "RTX GPU"} · ${telemetry.model} · ${telemetry.cpu_fallback ? "fallback used" : "CUDA only"}`} chip={telemetry.cpu_fallback ? "Retry" : "Ready"} />
          <View style={styles.finalMixMetaRow}>
            <MiniInfo label="VRAM" value={`${Math.round(telemetry.peak_vram_mb)} MB`} />
            <MiniInfo label="Render" value={`${Math.round(telemetry.generation_seconds)}s`} />
            <MiniInfo label="Runtime" value={telemetry.torch_cuda_runtime ?? "CUDA"} />
          </View>
        </Card>
      ) : null}
      {diversity ? (
        <Card>
          <Row
            title="Instrumental Diversity Gate"
            meta={`${diversity.evaluated_pairs - diversity.rejected_pairs}/${diversity.evaluated_pairs} producer pairs passed · vocal excluded`}
            chip={diversity.passed ? "Ready" : "Retry"}
          />
          <View style={styles.finalMixMetaRow}>
            <MiniInfo label="Embeddings" value="Compared" />
            <MiniInfo label="Onsets" value="Compared" />
            <MiniInfo label="Harmony" value="Compared" />
            <MiniInfo label="Thresholds" value={diversity.calibration_approved ? "Human rated" : "Prototype"} />
          </View>
          {!diversity.calibration_approved ? <Text style={styles.helperNote}>The multi-view rejection gate is active, but its threshold still needs release-reviewed human pair ratings.</Text> : null}
        </Card>
      ) : null}

      {result.warnings.length ? (
        <StatusNotice title="Production Notes" body={result.warnings.slice(0, 2).join(" ")} icon="waveform" />
      ) : null}

      <Text style={styles.sectionTitle}>Final Mixes</Text>
      {result.versions.map((version, index) => {
        const isSelected = index === selectedIndex;
        return (
          <View key={`${version.name}-${index}`} style={[styles.skarlyVersionCard, isSelected && styles.skarlyVersionCardSelected]}>
            <Pressable style={({ pressed }) => [styles.row, pressed && styles.touchPressedBlue]} onPress={() => onSelect(index)}>
              <View style={styles.trackTextBlock}>
                <Text style={styles.cardTitle}>{index + 1}. {version.name}</Text>
                <Text style={styles.metaText}>{version.style_family?.replace(/_/g, " ") ?? version.generator ?? result.generator_backend}{version.fallback_used ? " | fallback used" : version.generation_engine === "ace_step_1_5_cover" ? " | vocal-aware CUDA mix" : " | vocal-forward mix"}{isSelected ? "" : " | tap to open"}</Text>
              </View>
              <OwnershipChip status="Ready" label={isSelected ? "Selected" : "Mix"} />
            </Pressable>
            {isSelected && (
              <>
                <DetectedFact label="Instruments" value={version.instruments?.join(" · ") || "Producer-selected instrumentation"} />
                <DetectedFact label="Energy" value={version.energy ?? "Adaptive song arc"} />
                <DetectedFact label="Rhythm" value={version.rhythm_character ?? "Vocal-following groove"} />
                <SkarlyWaveformStack version={version} />
                {version.mix_note ? <Text style={styles.helperNote}>{version.mix_note}</Text> : null}
                {version.transformation_quality ? (
                  <View style={styles.finalMixMetaRow}>
                    <MiniInfo label="Originality" value={version.transformation_quality.original_enough ? "Passed" : "Retry"} />
                    <MiniInfo label="Duration" value={version.transformation_quality.duration_match ? "Matched" : "Retry"} />
                    <MiniInfo label="New vocals" value={version.transformation_quality.vocal_leakage_detected ? "Detected" : "Clear"} />
                  </View>
                ) : null}
                {version.musical_compatibility ? (
                  <View style={styles.finalMixMetaRow}>
                    <MiniInfo label="Vocal fit" value={version.musical_compatibility.passed ? "Passed" : "Retry"} />
                    <MiniInfo label="Tempo fit" value={version.musical_compatibility.tempo_match ? "Matched" : "Retry"} />
                    <MiniInfo
                      label="Key fit"
                      value={version.musical_compatibility.key_correction_applied
                        ? `Corrected ${version.musical_compatibility.key_correction_semitones! > 0 ? "+" : ""}${version.musical_compatibility.key_correction_semitones}`
                        : version.musical_compatibility.key_match ? "Matched" : "Retry"}
                    />
                  </View>
                ) : null}
                <View style={styles.optionWrap}>
                  <SecondaryButton label={finalMixIsPlaying ? "Pause Final Mix" : "Play Final Mix"} icon="play" onPress={() => onPlayVersion(index, "final")} compact />
                  <SecondaryButton label={backingIsPlaying ? "Pause Music" : "Play Music"} icon="waveform" onPress={() => onPlayVersion(index, "backing")} compact />
                  {!isInstrumentalFlow && selectedVocalUrl ? <SecondaryButton label={vocalIsPlaying ? "Pause Vocal" : "Solo Vocal"} icon="mic" onPress={() => onPlayVersion(index, "vocal")} compact /> : null}
                </View>
                <Text style={styles.sectionLabel}>Advanced vocal / music balance</Text>
                <View style={styles.optionWrap}>
                  {[
                    { value: -1, label: "Beat ++" },
                    { value: -0.5, label: "Beat +" },
                    { value: 0, label: "Center" },
                    { value: 0.5, label: "Vocal +" },
                    { value: 1, label: "Vocal ++" }
                  ].map((option) => (
                    <Pressable key={option.value} style={({ pressed }) => [styles.intentChip, vocalMusicBalance === option.value && styles.intentChipActive, pressed && styles.touchPressedBlue]} onPress={() => setVocalMusicBalance(option.value)}>
                      <Text style={[styles.intentChipText, vocalMusicBalance === option.value && styles.intentChipTextActive]}>{option.label}</Text>
                    </Pressable>
                  ))}
                </View>
                <Text style={styles.helperNote}>{mixPresetOptions.find((item) => item.value === mixPreset)?.label ?? "Balanced"} preset · the backing is reused, not regenerated.</Text>
                <SecondaryButton label={remixBusy ? "Remixing Existing Stems" : "Apply Mix Balance"} icon="waveform" onPress={() => onRemix(index)} disabled={remixBusy} />
                <Text style={styles.sectionLabel}>Producer revision</Text>
                <TextInput
                  value={instrumentChange}
                  onChangeText={setInstrumentChange}
                  placeholder="e.g. replace piano with sitar"
                  placeholderTextColor={colors.muted}
                  style={styles.input}
                  editable={!regenerationBusy}
                />
                <View style={styles.optionWrap}>
                  <SecondaryButton label="Fresh Take" icon="retry" onPress={() => onRegenerate(index, 0)} disabled={regenerationBusy} compact />
                  <SecondaryButton label="Energy -" icon="waveform" onPress={() => onRegenerate(index, -1)} disabled={regenerationBusy} compact />
                  <SecondaryButton label="Energy +" icon="waveform" onPress={() => onRegenerate(index, 1)} disabled={regenerationBusy} compact />
                </View>
                <SecondaryButton
                  label={regenerationBusy ? "Regenerating One Producer" : "Apply Instrument Change"}
                  icon="retry"
                  disabled={regenerationBusy || !instrumentChange.trim()}
                  onPress={() => Promise.resolve(onRegenerate(index, 0, instrumentChange)).then(() => setInstrumentChange(""))}
                />
                <Text style={styles.helperNote}>Only this producer is regenerated. The other four completed arrangements and their hashes are preserved.</Text>
                <Text style={styles.sectionLabel}>Regenerate one section</Text>
                <View style={styles.buttonRow}>
                  <TextInput
                    value={sectionStartText}
                    onChangeText={setSectionStartText}
                    placeholder="Start sec"
                    placeholderTextColor={colors.muted}
                    keyboardType="decimal-pad"
                    style={[styles.input, { flex: 1 }]}
                    editable={!sectionBusy}
                  />
                  <TextInput
                    value={sectionEndText}
                    onChangeText={setSectionEndText}
                    placeholder="End sec"
                    placeholderTextColor={colors.muted}
                    keyboardType="decimal-pad"
                    style={[styles.input, { flex: 1 }]}
                    editable={!sectionBusy}
                  />
                </View>
                <TextInput
                  value={sectionInstruction}
                  onChangeText={setSectionInstruction}
                  placeholder="e.g. add a warm sarangi response in this section"
                  placeholderTextColor={colors.muted}
                  style={styles.input}
                  editable={!sectionBusy}
                />
                {!sectionRangeValid && (sectionStartText || sectionEndText) ? (
                  <Text style={styles.errorText}>Choose at least 0.5 seconds inside the {songDuration ? `${songDuration.toFixed(1)}s` : "complete"} song.</Text>
                ) : null}
                <SecondaryButton
                  label={sectionBusy ? "Regenerating Selected Section" : "Regenerate This Section"}
                  icon="regenerate"
                  disabled={sectionBusy || regenerationBusy || !sectionRangeValid || !sectionInstruction.trim()}
                  onPress={() => onRegenerateSection(index, sectionStart, sectionEnd, sectionInstruction)}
                />
                <Text style={styles.helperNote}>ACE-Step repaints only this instrumental interval. Skarly verifies the rest is preserved, then remixes the unchanged original vocal.</Text>
                <View style={styles.buttonRow}>
                  <SecondaryButton label="Like" icon="success" onPress={() => onFeedback(index, 5)} compact />
                  <SecondaryButton label="Needs Work" icon="retry" onPress={() => onFeedback(index, 2)} compact />
                </View>
                <PrimaryButton label="Best Version" icon="success" onPress={() => onChooseBest(index)} compact golden />
              </>
            )}
          </View>
        );
      })}

      <Text style={styles.sectionTitle}>Final version preview</Text>
      <FinalVersionMessagePlayer
        title={`${selectedIndex + 1}. ${selected?.name ?? "Selected Version"}`}
        isPlaying={finalMixIsPlaying}
        positionMs={mixPositionMs}
        durationMs={finalVersionDurationMs}
        onPress={() => onPlayVersion(selectedIndex, "final")}
      />

      <Card>
        <Row title={selected?.name ?? "Selected Version"} meta="WAV + MP3 + instrumental + vocal + song map + disclosure" chip={hasSaved ? "Saved" : "Ready"} />
        <PrimaryButton
          label={exportBusy ? "Preparing Studio Bundle" : "Download Complete Studio Bundle"}
          icon={exportBusy ? "waveform" : "download"}
          disabled={!selected || exportBusy}
          onPress={() => selected && onExport(selectedIndex)}
        />
        <SecondaryButton label="Open Export Studio" icon="download" onPress={() => onNavigate("download")} />
        <PrimaryButton label={hasDownloaded ? "Downloaded Selected Mix" : "Download Selected Mix"} icon={hasDownloaded ? "success" : "download"} disabled={!selectedUrl} onPress={() => {
          if (!selectedUrl || !selected) {
            showToast("Selected mix is not ready");
            return;
          }
          downloadUrlToLocalFile(selectedUrl, `${cleanFileStem(selected.name)}.${extensionFromAudioUrl(selectedUrl)}`).then(() => {
            setHasDownloaded(true);
            onRemember("Downloaded");
            showToast("Selected mix saved locally");
          }).catch((error) => showToast(`Download failed: ${errorMessage(error)}`));
        }} />
        <View style={styles.buttonRow}>
          <SecondaryButton label="Instrumental" icon="download" disabled={!selectedBackingUrl} onPress={() => selectedBackingUrl && selected && downloadUrlToLocalFile(selectedBackingUrl, `${cleanFileStem(selected.name)}-instrumental.wav`).then(() => showToast("Instrumental saved")).catch((error) => showToast(`Download failed: ${errorMessage(error)}`))} compact />
          <SecondaryButton label="Processed Vocal" icon="download" disabled={!selectedVocalUrl} onPress={() => selectedVocalUrl && selected && downloadUrlToLocalFile(selectedVocalUrl, `${cleanFileStem(selected.name)}-vocal.wav`).then(() => showToast("Processed vocal saved")).catch((error) => showToast(`Download failed: ${errorMessage(error)}`))} compact />
        </View>
        <SecondaryButton label={hasSaved ? "Kept In Idea Vault" : "Keep Selected Draft"} icon={hasSaved ? "success" : "saved"} onPress={() => {
          setHasSaved(true);
          onRemember("Temporary");
          showToast("Selected version kept");
        }} />
        <View style={styles.buttonRow}>
          <SecondaryButton label="Change Detection" icon="back" onPress={() => onNavigate("genre")} compact />
          <SecondaryButton label="Delete" icon="trash" onPress={onDelete} compact />
        </View>
        <SecondaryButton label="Return Home" icon="home" onPress={() => onNavigate("home")} />
      </Card>
    </View>
  );
}

function SkarlyExportStudio({
  result,
  selectedIndex,
  exported,
  exportBusy,
  onExport,
  onBack,
  onHome,
  showToast
}: {
  result: SkarlyGenerateResponse;
  selectedIndex: number;
  exported: SkarlyV2ExportResponse | null;
  exportBusy: boolean;
  onExport: (index: number) => void | Promise<void>;
  onBack: () => void;
  onHome: () => void;
  showToast: (message: string) => void;
}) {
  const selected = result.versions[Math.max(0, Math.min(selectedIndex, result.versions.length - 1))];
  const activeExport = exported?.version_index === selectedIndex ? exported : null;
  const duration = result.song_intelligence_map?.duration_seconds ?? result.detected.analysis_scope_seconds ?? 0;
  const artifacts = [
    { key: "final_wav", label: "Final WAV", filename: "final_mix.wav" },
    { key: "final_mp3", label: "Final MP3", filename: "final_mix.mp3" },
    { key: "instrumental", label: "Instrumental WAV", filename: "instrumental.wav" },
    { key: "processed_vocal", label: "Processed Vocal", filename: "processed_vocal.wav" },
    { key: "analysis_json", label: "Analysis JSON", filename: "analysis.json" },
    { key: "song_map_json", label: "Song Map", filename: "song_map.json" },
    { key: "ai_generation_metadata", label: "AI Disclosure", filename: "ai_generation_metadata.json" },
    { key: "bundle_zip", label: "Complete ZIP", filename: "skarly_export_bundle.zip" }
  ];
  const downloadArtifact = (key: string, filename: string) => {
    const url = backendMediaUrl(activeExport?.files[key]);
    if (!url) {
      showToast("Prepare the studio export first");
      return;
    }
    void downloadUrlToLocalFile(url, `${cleanFileStem(selected?.name ?? "skarly")}-${filename}`)
      .then(() => showToast(`${filename} downloaded`))
      .catch((error) => showToast(`Download failed: ${errorMessage(error)}`));
  };
  return (
    <View>
      <ScreenHeader title="Export Studio" hint="Take the finished song, clean stems, analysis, and disclosure metadata." />
      <Card>
        <Row title={selected?.name ?? "Selected Version"} meta={`${duration.toFixed(1)} seconds · complete vocal timeline`} chip={activeExport ? "Ready" : "Processing"} />
        <DetectedFact label="Final audio" value="24-bit WAV and 320 kbps MP3" />
        <DetectedFact label="Core stems" value="Instrumental WAV and processed vocal WAV" />
        <DetectedFact label="Metadata" value="Analysis, Song Intelligence Map, seeds, CUDA model, diversity report, and AI disclosure" />
        <PrimaryButton label={exportBusy ? "Preparing Export Files" : activeExport ? "Rebuild & Download ZIP" : "Prepare & Download Studio Export"} icon={exportBusy ? "waveform" : "download"} disabled={!selected || exportBusy} onPress={() => selected && onExport(selectedIndex)} />
      </Card>
      {activeExport ? (
        <Card>
          <Row title="Verified Export Files" meta={`${Object.keys(activeExport.files).length} artifacts · ${activeExport.duration_seconds.toFixed(1)}s source of truth`} chip="Ready" />
          {artifacts.map((artifact) => activeExport.files[artifact.key] ? (
            <View key={artifact.key} style={styles.downloadFormatRow}>
              <View style={styles.trackTextBlock}>
                <Text style={styles.cardTitle}>{artifact.label}</Text>
                <Text style={styles.metaText}>{activeExport.durations_seconds[artifact.key] ? `${activeExport.durations_seconds[artifact.key].toFixed(1)} seconds · ` : ""}SHA-256 verified</Text>
              </View>
              <SecondaryButton label="Download" icon="download" compact onPress={() => downloadArtifact(artifact.key, artifact.filename)} />
            </View>
          ) : null)}
          {activeExport.warnings.length ? <StatusNotice title="Optional Stems" body={activeExport.warnings.join(" ")} icon="waveform" /> : null}
        </Card>
      ) : (
        <StatusNotice title="Export Not Prepared Yet" body="Skarly will render the selected mix as WAV and MP3, verify exact duration, package the stems and metadata, then make every file available here." icon="download" />
      )}
      <View style={styles.buttonRow}>
        <SecondaryButton label="Back To Versions" icon="back" onPress={onBack} compact />
        <SecondaryButton label="Return Home" icon="home" onPress={onHome} compact />
      </View>
    </View>
  );
}

function SkarlyWaveformStack({ version }: { version: SkarlyVersion }) {
  const waveforms = version.waveforms;
  return (
    <View style={styles.skarlyWaveformStack}>
      <WaveformPanel label="Input Vocal" peaks={waveforms?.input_vocal ?? []} color="#7bb7ff" />
      <WaveformPanel label="Skarly Music" peaks={waveforms?.backing ?? []} color={colors.blue} />
      <WaveformPanel label="Final Mix" peaks={waveforms?.final_mix ?? []} color="#ff6f91" />
    </View>
  );
}

function WaveformPanel({ label, peaks, color }: { label: string; peaks: number[]; color: string }) {
  return (
    <View style={styles.waveformPanel}>
      <View style={styles.waveformPanelHeader}>
        <Text style={styles.metaText}>{label}</Text>
        <Text style={styles.waveformPointCount}>{peaks.length ? `${peaks.length} pts` : "pending"}</Text>
      </View>
      <WaveformBars peaks={peaks} color={color} />
    </View>
  );
}

function WaveformBars({ peaks, color }: { peaks: number[]; color: string }) {
  const bars = useMemo(() => downsamplePeaks(peaks, 88), [peaks]);
  const width = 352;
  const height = 58;
  const gap = 1.4;
  const barWidth = width / Math.max(1, bars.length) - gap;
  const displayBars = bars.length ? bars : Array.from({ length: 88 }, () => 0.04);
  return (
    <View style={styles.waveformGraph}>
      <Svg width="100%" height={height} viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none">
        {displayBars.map((peak, index) => {
          const safePeak = Math.max(0.03, Math.min(1, Number.isFinite(peak) ? peak : 0));
          const barHeight = Math.max(3, safePeak * (height - 8));
          const x = index * (barWidth + gap);
          const y = (height - barHeight) / 2;
          return <Rect key={`${index}-${safePeak.toFixed(3)}`} x={x} y={y} width={Math.max(1, barWidth)} height={barHeight} rx={1.6} fill={color} opacity={bars.length ? 0.9 : 0.18} />;
        })}
      </Svg>
    </View>
  );
}

function downsamplePeaks(peaks: number[], target: number) {
  if (!peaks.length || target <= 0) return [];
  if (peaks.length <= target) return peaks.map((peak) => Math.max(0, Math.min(1, peak)));
  const result: number[] = [];
  const bucket = peaks.length / target;
  for (let index = 0; index < target; index += 1) {
    const start = Math.floor(index * bucket);
    const end = Math.max(start + 1, Math.floor((index + 1) * bucket));
    const slice = peaks.slice(start, end);
    result.push(Math.max(...slice.map((peak) => Math.max(0, Math.min(1, peak)))));
  }
  return result;
}

function ResultPlayer({
  creatorMode,
  genre,
  source,
  backendFinalUrl,
  backendDownloadUrl,
  exportUrls,
  analysis,
  blueprint,
  trackName,
  fileNameMode,
  isPlaying,
  mixDurationMs,
  mixPositionMs,
  hasDownloaded,
  hasShared,
  hasSaved,
  setHasDownloaded,
  setHasShared,
  setHasSaved,
  showToast,
  onRemember,
  onDelete,
  onNavigate,
  onPlayMix
}: {
  creatorMode: CreatorMode;
  genre: Genre;
  source: InputSource;
  backendFinalUrl: string | null;
  backendDownloadUrl: string | null;
  exportUrls: DemoExportUrls;
  analysis: BackendSongAnalysis | null;
  blueprint: BackendSongBlueprint | null;
  trackName: string;
  fileNameMode: FileNameMode;
  isPlaying: boolean;
  mixDurationMs: number;
  mixPositionMs: number;
  hasDownloaded: boolean;
  hasShared: boolean;
  hasSaved: boolean;
  setHasDownloaded: (value: boolean) => void;
  setHasShared: (value: boolean) => void;
  setHasSaved: (value: boolean) => void;
  showToast: (message: string) => void;
  onRemember: (status?: TrackStatus) => void;
  onDelete: () => void;
  onNavigate: (screen: Screen) => void;
  onPlayMix: () => void | Promise<void>;
}) {
  return (
    <View>
      <ScreenHeader title="Demo Project" hint="Your rough idea is now structured for producer handoff." />
      <MusicPlayer
        creatorMode={creatorMode}
        genre={genre}
        source={source}
        backendFinalUrl={backendFinalUrl}
        backendDownloadUrl={backendDownloadUrl}
        exportUrls={exportUrls}
        analysis={analysis}
        blueprint={blueprint}
        trackName={trackName}
        fileNameMode={fileNameMode}
        isPlaying={isPlaying}
        mixDurationMs={mixDurationMs}
        mixPositionMs={mixPositionMs}
        hasDownloaded={hasDownloaded}
        hasShared={hasShared}
        hasSaved={hasSaved}
        setHasDownloaded={setHasDownloaded}
        setHasShared={setHasShared}
        setHasSaved={setHasSaved}
        showToast={showToast}
        onRemember={onRemember}
        onDelete={onDelete}
        onNavigate={onNavigate}
        onPlayMix={onPlayMix}
      />
    </View>
  );
}

function DownloadShare({
  creatorMode,
  genre,
  backendFinalUrl,
  backendDownloadUrl,
  backendIsolatedVocalUrl,
  backendBackingUrl,
  exportUrls,
  analysis,
  blueprint,
  trackName,
  fileNameMode,
  isPlaying,
  hasDownloaded,
  hasShared,
  hasSaved,
  setHasDownloaded,
  setHasShared,
  setHasSaved,
  showToast,
  onRemember,
  onDelete,
  onNavigate,
  onPlayMix
}: {
  creatorMode: CreatorMode;
  genre: Genre;
  backendFinalUrl: string | null;
  backendDownloadUrl: string | null;
  backendIsolatedVocalUrl: string | null;
  backendBackingUrl: string | null;
  exportUrls: DemoExportUrls;
  analysis: BackendSongAnalysis | null;
  blueprint: BackendSongBlueprint | null;
  trackName: string;
  fileNameMode: FileNameMode;
  isPlaying: boolean;
  hasDownloaded: boolean;
  hasShared: boolean;
  hasSaved: boolean;
  setHasDownloaded: (value: boolean) => void;
  setHasShared: (value: boolean) => void;
  setHasSaved: (value: boolean) => void;
  showToast: (message: string) => void;
  onRemember: (status?: TrackStatus) => void;
  onDelete: () => void;
  onNavigate: (screen: Screen) => void;
  onPlayMix: () => void | Promise<void>;
}) {
  const fileName = buildFileName(trackName, genre, fileNameMode);
  const status: TrackStatus = hasDownloaded ? "Downloaded" : hasShared ? "Shared" : creatorMode === "saved" && hasSaved ? "Saved" : hasSaved ? "Temporary" : "Ready";
  const saveLabel = creatorMode === "guest" ? "Keep temporary draft" : hasSaved ? "Saved to Idea Vault" : "Save to Idea Vault";
  const downloadUrl = backendDownloadUrl ?? backendFinalUrl;
  const canDownload = Boolean(downloadUrl);
  const vocalStemUrl = exportUrls.vocalStem ?? backendIsolatedVocalUrl;
  const backingStemUrl = exportUrls.backingStem ?? backendBackingUrl;
  const instrumentStemRows = [
    { label: "Drums Stem", url: exportUrls.drumsStem, suffix: "drums.wav" },
    { label: "Bass Stem", url: exportUrls.bassStem, suffix: "bass.wav" },
    { label: "Guitar Stem", url: exportUrls.guitarStem, suffix: "guitar.wav" },
    { label: "Keys Stem", url: exportUrls.keysStem, suffix: "keys.wav" },
    { label: "Source Ref", url: exportUrls.referenceStem, suffix: "source.wav" }
  ];
  return (
    <View>
      <ScreenHeader title="Producer Pack" hint="Export the demo, stems, MIDI, and chord sheet." />
      <Card>
        <TrackListItem
          title={fileName}
          meta={`${analysis?.key ?? "Key estimate"} | ${analysis?.bpm ? `${Math.round(analysis.bpm)} BPM` : "Tempo estimate"} | Private demo`}
          status={status}
        />
        <SecondaryButton label={isPlaying ? "Pause Mix" : "Play Mix"} icon="play" disabled={!backendFinalUrl} onPress={onPlayMix} />
        <PrimaryButton label={exportUrls.producerPack ? "Download Producer Pack ZIP" : "Producer Pack Not Ready"} icon="download" disabled={!exportUrls.producerPack} onPress={() => {
          if (!exportUrls.producerPack) {
            showToast("Producer Pack is not ready yet");
            return;
          }
          downloadUrlToLocalFile(exportUrls.producerPack, buildDownloadName(trackName || "skarly-demo", genre, fileNameMode, "zip")).then(() => {
            showToast("Producer Pack saved locally");
          }).catch((error) => showToast(`Producer Pack failed: ${errorMessage(error)}`));
          setHasDownloaded(true);
          onRemember("Downloaded");
        }} />
        <View style={styles.buttonRow}>
          <ExportDownloadButton label="MP3" url={downloadUrl} fileName={fileName} showToast={showToast} />
          <ExportDownloadButton label="WAV" url={exportUrls.wav} fileName={buildDownloadName(trackName || "skarly-demo", genre, fileNameMode, "wav")} showToast={showToast} />
        </View>
        <View style={styles.buttonRow}>
          <ExportDownloadButton label="MIDI" url={exportUrls.midi} fileName={buildDownloadName(trackName || "skarly-demo", genre, fileNameMode, "mid")} showToast={showToast} />
          <ExportDownloadButton label="Melody MIDI" url={exportUrls.melodyMidi} fileName={buildDownloadName(trackName || "skarly-demo", genre, fileNameMode, "melody.mid")} showToast={showToast} />
        </View>
        <View style={styles.buttonRow}>
          <ExportDownloadButton label="Chord Sheet" url={exportUrls.chordSheet} fileName={buildDownloadName(trackName || "skarly-demo", genre, fileNameMode, "txt")} showToast={showToast} />
        </View>
        {(vocalStemUrl || backingStemUrl) && (
          <View style={styles.buttonRow}>
            {vocalStemUrl && <ExportDownloadButton label="Vocal Stem" url={vocalStemUrl} fileName={buildDownloadName(trackName || "vocal", genre, fileNameMode, "vocal.wav")} showToast={showToast} />}
            {backingStemUrl && <ExportDownloadButton label="Backing Stem" url={backingStemUrl} fileName={buildDownloadName(trackName || "backing", genre, fileNameMode, "backing.wav")} showToast={showToast} />}
          </View>
        )}
        {instrumentStemRows.some((stem) => stem.url) && (
          <>
            <View style={styles.buttonRow}>
              {instrumentStemRows.slice(0, 2).map((stem) => (
                <ExportDownloadButton key={stem.label} label={stem.label} url={stem.url} fileName={buildDownloadName(trackName || "stem", genre, fileNameMode, stem.suffix)} showToast={showToast} />
              ))}
            </View>
            <View style={styles.buttonRow}>
              {instrumentStemRows.slice(2, 4).map((stem) => (
                <ExportDownloadButton key={stem.label} label={stem.label} url={stem.url} fileName={buildDownloadName(trackName || "stem", genre, fileNameMode, stem.suffix)} showToast={showToast} />
              ))}
            </View>
            {instrumentStemRows[4].url && (
              <ExportDownloadButton label="Source Reference" url={instrumentStemRows[4].url} fileName={buildDownloadName(trackName || "source", genre, fileNameMode, instrumentStemRows[4].suffix)} showToast={showToast} />
            )}
          </>
        )}
        <PrimaryButton label={hasDownloaded ? `Downloaded ${fileName}` : canDownload ? `Download ${fileName}` : "MP3 Not Ready"} icon={hasDownloaded ? "success" : "download"} disabled={!canDownload} onPress={() => {
          if (!downloadUrl) {
            showToast("Run the worker first to create the MP3");
            return;
          }
          downloadUrlToLocalFile(downloadUrl, fileName).then(() => {
            showToast("Download saved locally");
          }).catch((error) => showToast(`Download failed: ${errorMessage(error)}`));
          setHasDownloaded(true);
          onRemember("Downloaded");
        }} />
        <SecondaryButton label={hasShared ? `Shared ${fileName}` : `Share ${fileName}`} icon={hasShared ? "success" : "share"} onPress={() => {
          setHasShared(true);
          onRemember("Shared");
          showToast("Share marked complete");
        }} />
        <SecondaryButton label={saveLabel} icon={hasSaved ? "success" : "saved"} onPress={() => {
          setHasSaved(true);
          onRemember(creatorMode === "saved" ? "Saved" : "Temporary");
          showToast(creatorMode === "guest" ? "Temporary draft kept" : "Saved to workspace");
          onNavigate("history");
        }} />
        <SecondaryButton label="Delete track" icon="trash" onPress={onDelete} />
        <SecondaryButton label="Return Home" icon="home" onPress={() => onNavigate("home")} />
        {!canDownload && <StatusNotice title="MP3 Not Ready" body="The final file is created after the backend worker finishes. If this stays here, check backend worker output." icon="error" />}
      </Card>
      <BlueprintPanel blueprint={blueprint} />
    </View>
  );
}

function ExportDownloadButton({ label, url, fileName, showToast }: { label: string; url?: string | null; fileName: string; showToast: (message: string) => void }) {
  return (
    <SecondaryButton
      label={url ? label : `${label} Pending`}
      icon={url ? "download" : "processing"}
      disabled={!url}
      onPress={() => {
        if (!url) return;
        downloadUrlToLocalFile(url, fileName)
          .then(() => showToast(`${label} saved locally`))
          .catch((error) => showToast(`${label} failed: ${errorMessage(error)}`));
      }}
      compact
    />
  );
}

function History({
  creatorMode,
  voiceTakes,
  generatedTracks,
  backendTracks,
  backendMode,
  deletedBackendTrackIds,
  playingVoiceTakeId,
  onPlayVoiceTake,
  onPlayBackendTrack,
  onDownloadBackendTrack,
  onUploadVoiceTake,
  onUseVoiceTake,
  onDeleteVoiceTake,
  onShareVoiceTake,
  onDownloadTrack,
  onShareTrack,
  onUpdateBackendTrackStatus,
  onDeleteGeneratedTrack,
  onDeleteBackendTrack,
  onOpenRecycleBin
}: {
  creatorMode: CreatorMode;
  voiceTakes: VoiceTake[];
  generatedTracks: GeneratedTrackView[];
  backendTracks: BackendJob[];
  backendMode: BackendMode;
  deletedBackendTrackIds: string[];
  playingVoiceTakeId: string | null;
  onPlayVoiceTake: (take: VoiceTake) => void | Promise<void>;
  onPlayBackendTrack: (jobId: string) => void | Promise<void>;
  onDownloadBackendTrack: (jobId: string) => void | Promise<void>;
  onUploadVoiceTake: (take: VoiceTake) => Promise<VoiceTake>;
  onUseVoiceTake: (take: VoiceTake) => void | Promise<void>;
  onDeleteVoiceTake: (takeId: string) => void;
  onShareVoiceTake: (title: string) => void;
  onDownloadTrack: (title: string) => void;
  onShareTrack: (title: string) => void;
  onUpdateBackendTrackStatus: (jobId: string, status: TrackStatus) => void;
  onDeleteGeneratedTrack: (trackId: string) => void;
  onDeleteBackendTrack: (jobId: string) => void;
  onOpenRecycleBin: () => void;
}) {
  const isGuest = creatorMode === "guest";
  type VisibleHistoryTrack = GeneratedTrackView & { origin: "local" | "backend" };
  const backendVisibleTracks = backendMode === "api" ? backendTracks.filter((job) => !isStaleBackendJob(job) && job.status !== "deleted" && !deletedBackendTrackIds.includes(job.job_id)).map((job) => ({
    id: job.job_id,
    title: job.track_name,
    meta: `${job.genre} | ${getArrangementModeLabel(job.arrangement_mode)} | Private demo`,
    status: backendTrackStatus(job.status, job.library_status),
    origin: "backend" as const
  } satisfies VisibleHistoryTrack)) : [];
  const visibleTracks: VisibleHistoryTrack[] = [
    ...generatedTracks.map((track) => ({ ...track, origin: "local" as const })),
    ...backendVisibleTracks.filter((track) => !generatedTracks.some((generated) => generated.title === track.title))
  ];
  return (
    <View>
      <ScreenHeader title="Idea Vault" hint="Your voice takes, demos, and producer packs live here." action={{ icon: "recycle", onPress: onOpenRecycleBin }} />
      <Card>
        <Row title={isGuest ? "Guest Creator" : "Saved Creator"} meta={isGuest ? "Temporary session" : "Only you"} chip={isGuest ? "Temporary" : "Saved"} />
        <Text style={styles.subtitle}>{isGuest ? "Guest drafts stay only for this session." : "Signed-in history is scoped to your Firebase account."}</Text>
      </Card>
      <StatusNotice title={backendMode === "api" ? "Idea Vault Connected" : "Cloud Sync Offline"} body={backendMode === "api" ? "Saved recordings and demos load from your private cloud library." : "Start FastAPI to sync private recordings and demos."} icon={backendMode === "api" ? "success" : "error"} />
      <Text style={styles.sectionTitle}>Voice Recordings</Text>
      {voiceTakes.length === 0 ? (
        <Card>
          <Row title="No Voice Takes Yet" meta="Record a vocal to save it here" chip="Ready" />
        </Card>
      ) : (
        voiceTakes.map((take) => (
          <TrackListItem
            key={take.id}
            title={take.title}
            meta={`${take.duration}s voice memo | ${take.uploadError ?? (take.uploaded ? "Cloud uploaded" : take.uploadState === "uploading" ? "Uploading to cloud" : "Local recording")} | ${take.createdAt}`}
            status={take.uploaded ? "Saved" : take.uploadState === "uploading" ? "Processing" : take.uploadState === "failed" ? "Retry" : "Temporary"}
            icon="mic"
            actions={[
              { label: playingVoiceTakeId === take.id ? "Pause" : "Play", icon: playingVoiceTakeId === take.id ? "success" : "play", onPress: () => onPlayVoiceTake(take) },
              ...(take.uploaded || take.uploadState === "uploading" ? [] : [{ label: take.uploadState === "failed" ? "Retry Upload" : "Upload", icon: "upload" as IconName, onPress: async () => { await onUploadVoiceTake(take); } }]),
              { label: "Use", icon: "waveform", onPress: () => onUseVoiceTake(take) },
              { label: "Share", icon: "share", onPress: () => onShareVoiceTake(take.title) },
              { label: "Delete", icon: "trash", destructive: true, onPress: () => onDeleteVoiceTake(take.id) }
            ]}
          />
        ))
      )}
      <Text style={styles.sectionTitle}>Demo Projects</Text>
      {visibleTracks.length === 0 && (
        <Card>
          <Row title="No Demo Projects Yet" meta="Build a demo and name it first" chip="Ready" />
        </Card>
      )}
      {visibleTracks.map((track) => (
        <TrackListItem
          key={track.id}
          {...track}
          icon="waveform"
          actions={[
            ...(track.origin === "backend" ? [{ label: "Play", icon: "play" as IconName, onPress: () => onPlayBackendTrack(track.id) }] : []),
            { label: "Download", icon: "download", onPress: () => track.origin === "backend" ? onDownloadBackendTrack(track.id) : onDownloadTrack(track.title) },
            { label: "Share", icon: "share", onPress: () => track.origin === "backend" ? onUpdateBackendTrackStatus(track.id, "Shared") : onShareTrack(track.title) },
            { label: "Delete", icon: "trash", destructive: true, onPress: () => track.origin === "backend" ? onDeleteBackendTrack(track.id) : onDeleteGeneratedTrack(track.id) }
          ]}
        />
      ))}
    </View>
  );
}

function RecycleBin({
  voiceTakes,
  localTracks,
  backendTracks,
  onBack,
  onRestoreVoiceTake,
  onPermanentVoiceTake,
  onRestoreLocalTrack,
  onPermanentLocalTrack,
  onRestoreBackendTrack,
  onPermanentBackendTrack
}: {
  voiceTakes: VoiceTake[];
  localTracks: GeneratedTrackView[];
  backendTracks: BackendJob[];
  onBack: () => void;
  onRestoreVoiceTake: (take: VoiceTake) => void;
  onPermanentVoiceTake: (take: VoiceTake) => void;
  onRestoreLocalTrack: (track: GeneratedTrackView) => void;
  onPermanentLocalTrack: (trackId: string) => void;
  onRestoreBackendTrack: (jobId: string) => void;
  onPermanentBackendTrack: (jobId: string) => void;
}) {
  const visibleBackendTracks = backendTracks.filter((job) => job.track_name && job.status === "deleted");
  return (
    <View>
      <ScreenHeader title="Recently Deleted" hint="Restore items or delete them forever." onBack={onBack} />
      <StatusNotice title="Recycle Bin" body="Items here are hidden from your library. Delete Forever removes the cloud file and metadata." icon="recycle" />
      <Text style={styles.sectionTitle}>Voice Recordings</Text>
      {voiceTakes.length === 0 ? (
        <Card>
          <Row title="No Deleted Voice Takes" meta="Deleted recordings will appear here" chip="Ready" />
        </Card>
      ) : (
        voiceTakes.map((take) => (
          <TrackListItem
            key={take.id}
            title={take.title}
            meta={`${take.duration}s voice memo | Deleted${take.deletedAt ? ` ${formatDeletedDate(take.deletedAt)}` : ""}`}
            status="Retry"
            icon="mic"
            actions={[
              { label: "Restore", icon: "success", onPress: () => onRestoreVoiceTake(take) },
              { label: "Delete Forever", icon: "trash", destructive: true, onPress: () => onPermanentVoiceTake(take) }
            ]}
          />
        ))
      )}
      <Text style={styles.sectionTitle}>Demo Projects</Text>
      {localTracks.length === 0 && visibleBackendTracks.length === 0 ? (
        <Card>
          <Row title="No Deleted Demos" meta="Deleted demo projects will appear here" chip="Ready" />
        </Card>
      ) : null}
      {localTracks.map((track) => (
        <TrackListItem
          key={track.id}
          {...track}
          status="Retry"
          icon="waveform"
          actions={[
            { label: "Restore", icon: "success", onPress: () => onRestoreLocalTrack(track) },
            { label: "Delete Forever", icon: "trash", destructive: true, onPress: () => onPermanentLocalTrack(track.id) }
          ]}
        />
      ))}
      {visibleBackendTracks.map((job) => (
        <TrackListItem
          key={job.job_id}
          title={job.track_name}
          meta={`${job.genre} | Deleted${job.deleted_at ? ` ${formatDeletedDate(job.deleted_at)}` : ""}`}
          status="Retry"
          icon="waveform"
          actions={[
            { label: "Restore", icon: "success", onPress: () => onRestoreBackendTrack(job.job_id) },
            { label: "Delete Forever", icon: "trash", destructive: true, onPress: () => onPermanentBackendTrack(job.job_id) }
          ]}
        />
      ))}
    </View>
  );
}

function formatDeletedDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function Profile({
  creatorMode,
  firebaseStatus,
  firebaseEmail,
  isAdmin,
  onGoToSignup,
  profile,
  onSaveProfile,
  defaultGenre,
  setDefaultGenre,
  backendMode,
  backendMessage,
  onOpenAdmin,
  onReset,
  onLogout,
  showToast
}: {
  creatorMode: CreatorMode;
  firebaseStatus: FirebaseSetupStatus;
  firebaseEmail: string;
  isAdmin: boolean;
  onGoToSignup: () => void;
  profile: CreatorProfile;
  onSaveProfile: (profile: CreatorProfile) => Promise<boolean>;
  defaultGenre: Genre;
  setDefaultGenre: (genre: Genre) => void;
  backendMode: BackendMode;
  backendMessage: string;
  onOpenAdmin: () => void;
  onReset: () => void;
  onLogout: () => void;
  showToast: (message: string) => void;
}) {
  const [voicePrivate, setVoicePrivate] = useState(true);
  const [deleteRaw, setDeleteRaw] = useState(true);
  const [keepFinalOnly, setKeepFinalOnly] = useState(true);
  const [draftProfile, setDraftProfile] = useState(profile);
  const [isEditingProfile, setIsEditingProfile] = useState(false);
  const initials = (profile.name.trim() || "LC").split(" ").map((part) => part[0]).join("").slice(0, 2).toUpperCase();
  const profileStatus = creatorMode === "guest" ? "Temporary profile" : "Saved creator";
  const visibleEmail = creatorMode === "saved" ? firebaseEmail || profile.email : profile.email;
  const canSaveProfile = draftProfile.name.trim().length > 0;

  useEffect(() => {
    setDraftProfile(profile);
  }, [profile]);

  const pickProfileImage = async () => {
    const result = await DocumentPicker.getDocumentAsync({
      type: ["image/png", "image/jpeg", "image/jpg", "image/webp"],
      copyToCacheDirectory: true,
      multiple: false
    });

    if (result.canceled || !result.assets[0]) return;
    const file = result.assets[0];
    setDraftProfile((current) => ({ ...current, avatarUri: file.uri }));
    showToast("Profile image selected");
  };

  const saveProfile = async () => {
    const normalizedEmail = draftProfile.email.trim().toLowerCase();
    const nextProfile = {
      ...draftProfile,
      name: draftProfile.name.trim() || "Guest Creator",
      email: creatorMode === "saved" ? visibleEmail : normalizedEmail,
      bio: draftProfile.bio.trim() || "Private Skarly workspace"
    };
    if (creatorMode === "guest" && nextProfile.email.length > 0) {
      showToast(firebaseStatus === "ready" ? "Create an account to save this email" : "Add Firebase config to create saved accounts");
      if (firebaseStatus === "ready") onGoToSignup();
      return;
    }
    const saved = await onSaveProfile(nextProfile);
    if (!saved) return;
    setIsEditingProfile(false);
    showToast(creatorMode === "saved" ? "Cloud profile saved" : "Profile details saved");
  };

  return (
    <View>
      <ScreenHeader title="Profile" hint="Creator identity and studio defaults." />
      <Card>
        <View style={styles.profileHero}>
          <Pressable style={styles.avatarButton} onPress={pickProfileImage}>
            {draftProfile.avatarUri ? (
              <Image source={{ uri: draftProfile.avatarUri }} resizeMode="cover" style={styles.avatarImage} />
            ) : (
              <Text style={styles.avatarInitials}>{initials}</Text>
            )}
          </Pressable>
          <Pressable style={({ pressed }) => [styles.avatarEditButton, pressed && styles.touchPressedBlue]} onPress={() => setIsEditingProfile((current) => !current)}>
            <IconSymbol name="edit" tone="blue" size={18} />
          </Pressable>
          <View style={styles.profileHeroCopy}>
            <Text style={styles.cardTitle}>{profile.name}</Text>
            <Text style={styles.metaText}>{visibleEmail || profileStatus}</Text>
            <Text style={styles.settingValue}>{profile.bio}</Text>
          </View>
        </View>
      </Card>
      {isEditingProfile && (
        <Card>
          <Row title="Edit Details" meta={creatorMode === "guest" ? "Session only" : "Firebase account"} />
          {creatorMode === "guest" && <Text style={styles.helperNote}>Add an email and save to continue into Firebase sign up. Guest sessions still stay temporary.</Text>}
          {creatorMode === "saved" && <Text style={styles.helperNote}>Account email comes from Firebase Auth. Profile fields save to your cloud profile.</Text>}
          <SecondaryButton label={draftProfile.avatarUri ? "Change Profile Image" : "Upload Profile Image"} icon="upload" onPress={pickProfileImage} />
          <TextInput value={draftProfile.name} onChangeText={(name) => setDraftProfile((current) => ({ ...current, name }))} placeholder="Creator name" placeholderTextColor={colors.muted} style={styles.input} />
          <TextInput value={creatorMode === "saved" ? visibleEmail : draftProfile.email} onChangeText={(email) => setDraftProfile((current) => ({ ...current, email }))} placeholder="Email address" placeholderTextColor={colors.muted} style={styles.input} keyboardType="email-address" autoCapitalize="none" editable={creatorMode === "guest"} />
          <TextInput value={draftProfile.bio} onChangeText={(bio) => setDraftProfile((current) => ({ ...current, bio }))} placeholder="Short bio" placeholderTextColor={colors.muted} style={[styles.input, styles.bioInput]} multiline />
          <PrimaryButton label="Save Profile" icon="success" onPress={saveProfile} disabled={!canSaveProfile} />
        </Card>
      )}
      <Text style={styles.sectionTitle}>Settings</Text>
      <Card>
        <Row title={creatorMode === "guest" ? "Guest Creator" : "Saved Creator"} meta={creatorMode === "guest" ? "Temporary" : "Private"} />
        <SettingsToggle label="Voice Privacy" value="Private by default" icon="speak" enabled={voicePrivate} onPress={() => setVoicePrivate((current) => !current)} />
        <SettingsToggle label="Delete Raw Recording" value="After mix" icon="trash" enabled={deleteRaw} onPress={() => setDeleteRaw((current) => !current)} />
        <SettingsToggle label="Keep Demo Exports" value="Producer Pack retained" icon="saved" enabled={keepFinalOnly} onPress={() => setKeepFinalOnly((current) => !current)} />
        <SettingStepper label="Default Vibe" value={defaultGenre.label} icon="vibe" color={defaultGenre.color} onPress={() => {
          const currentIndex = genres.findIndex((genre) => genre.id === defaultGenre.id);
          const nextGenre = genres[(currentIndex + 1) % genres.length];
          setDefaultGenre(nextGenre);
          if (creatorMode === "saved") {
            onSaveProfile({ ...profile, bio: profileBioWithDefaultGenre(profile.bio, nextGenre) }).then((saved) => {
              if (saved) showToast(`Default vibe saved: ${nextGenre.label}`);
            });
          } else {
            showToast(`Default vibe set: ${nextGenre.label}`);
          }
        }} />
        <DisabledSetting label="Export Data" value="After persisted history" icon="share" />
        <DisabledSetting label="Backend" value={backendMode === "api" ? "FastAPI connected" : "Offline"} icon={backendMode === "api" ? "success" : "error"} />
      </Card>
      <StatusNotice title="Backend Status" body={backendMessage} icon={backendMode === "api" ? "success" : "error"} />
      <IntegrationStatus />
      {creatorMode === "saved" && isAdmin && <PrimaryButton label="Open Admin Panel" icon="generate" onPress={onOpenAdmin} golden />}
      {creatorMode === "saved" && <SecondaryButton label="Logout / Switch Account" icon="logout" onPress={onLogout} />}
      <SecondaryButton label="Reset App Session" icon="retry" onPress={onReset} />
    </View>
  );
}

function AdminPanel({
  summary,
  loading,
  backendMode,
  backendMessage,
  onBack,
  onRefresh,
  onCleanupStale
}: {
  summary: BackendAdminSummaryResponse | null;
  loading: boolean;
  backendMode: BackendMode;
  backendMessage: string;
  onBack: () => void;
  onRefresh: () => void | Promise<void>;
  onCleanupStale: () => void | Promise<void>;
}) {
  const counts = summary?.counts ?? {};
  return (
    <View>
      <ScreenHeader title="Admin Panel" hint="Operational view for Skarly testing." onBack={onBack} />
      <Card>
        <Row title="Control Room" meta={summary ? `${summary.environment} | ${summary.repository_backend}` : backendMode === "api" ? "Backend connected" : "Waiting for backend"} chip={backendMode === "api" ? "Ready" : "Retry"} />
        <Text style={styles.subtitle}>{backendMessage}</Text>
        <View style={styles.adminMetaGrid}>
          <MiniInfo label="Storage" value={summary?.storage_backend ?? "Unknown"} />
          <MiniInfo label="Worker" value={summary?.worker_backend ?? "Unknown"} />
          <MiniInfo label="Music" value={summary?.music_generator_backend ?? "Unknown"} />
          <MiniInfo label="Task" value={summary?.task_backend ?? "Unknown"} />
          <MiniInfo label="Bucket" value={summary?.bucket ?? "Unknown"} />
        </View>
      </Card>
      <Card>
        <Row
          title="Cloud Status"
          meta={summary?.cloud_runtime ? `${summary.cloud_runtime.runtime} | ${summary.cloud_runtime.region}` : "Cloud runtime details"}
          chip={summary?.cloud_runtime?.runtime === "cloud_run" ? "Ready" : "Temporary"}
        />
        <View style={styles.adminMetaGrid}>
          <MiniInfo label="Service" value={summary?.cloud_runtime?.service ?? "Unknown"} />
          <MiniInfo label="Revision" value={summary?.cloud_runtime?.revision ?? "Unknown"} />
          <MiniInfo label="Queue" value={summary?.cloud_runtime?.task_queue ?? "Unknown"} />
          <MiniInfo label="Project" value={summary?.cloud_runtime?.project_id ?? "Unknown"} />
        </View>
        <Text style={styles.helperNote} numberOfLines={2}>{summary?.cloud_runtime?.service_url ?? "Backend URL will appear after Cloud Run deploy"}</Text>
      </Card>
      <PrimaryButton label={loading ? "Refreshing..." : "Refresh Admin Data"} icon="retry" onPress={onRefresh} disabled={loading} golden />
      <SecondaryButton label="Clean Stale Library Items" icon="trash" onPress={onCleanupStale} disabled={loading} />
      <View style={styles.adminCountGrid}>
        <AdminCount label="Users" value={counts.users ?? 0} />
        <AdminCount label="Jobs" value={counts.recent_jobs ?? 0} />
        <AdminCount label="Voice Takes" value={counts.voice_takes ?? 0} />
        <AdminCount label="Failed" value={counts.failed_jobs ?? 0} warning />
      </View>
      <Card>
        <Row
          title="Cloud Cost"
          meta={summary?.cloud_cost ? `${summary.cloud_cost.period} | $${summary.cloud_cost.estimated_cost_usd.toFixed(2)} estimated` : "Usage estimate"}
          chip={summary?.cloud_runtime?.runtime === "cloud_run" ? "Saved" : "Ready"}
        />
        <View style={styles.adminMetaGrid}>
          <MiniInfo label="Runs" value={summary?.cloud_cost ? `${summary.cloud_cost.generations}` : "0"} />
          <MiniInfo label="Limit" value={summary?.cloud_cost ? `${summary.cloud_cost.generation_limit}` : "25"} />
          <MiniInfo label="Unit" value={summary?.cloud_cost ? `$${summary.cloud_cost.unit_cost_usd.toFixed(2)}` : "$0.04"} />
          <MiniInfo label="Generator" value={summary?.cloud_cost?.generator_backend ?? "Unknown"} />
        </View>
      </Card>
      <Text style={styles.sectionTitle}>Recent Users</Text>
      {summary?.users.length ? summary.users.map((user) => (
        <Card key={user.user_id}>
          <Row title={user.name || "Unnamed Creator"} meta={user.email} chip="Saved" />
          <Text style={styles.helperNote}>{shortId(user.user_id)} | Updated {formatAdminDate(user.updated_at)}</Text>
        </Card>
      )) : (
        <Card><Row title="No Users Yet" meta="Saved profiles will appear here" chip="Ready" /></Card>
      )}
      <Text style={styles.sectionTitle}>Recent Voice Takes</Text>
      {summary?.recent_voice_takes.length ? summary.recent_voice_takes.map((take) => (
        <TrackListItem
          key={take.take_id}
          title={take.title}
          meta={`${take.duration}s | ${take.content_type} | ${formatBytes(take.size_bytes ?? undefined)}`}
          status={take.status === "deleted" ? "Retry" : "Saved"}
          icon="mic"
        />
      )) : (
        <Card><Row title="No Voice Takes" meta="Recordings will appear here after cloud save" chip="Ready" /></Card>
      )}
      <Text style={styles.sectionTitle}>Recent Jobs</Text>
      {summary?.recent_jobs.length ? summary.recent_jobs.map((job) => (
        <TrackListItem
          key={job.job_id}
          title={job.track_name || "Unnamed Job"}
          meta={`${job.genre} | ${job.status} | ${job.error ?? job.stage}`}
          status={backendTrackStatus(job.status, job.library_status)}
          icon="waveform"
        />
      )) : (
        <Card><Row title="No Jobs Yet" meta="Generated mixes will appear here" chip="Ready" /></Card>
      )}
      <Text style={styles.sectionTitle}>Recently Deleted</Text>
      <Card>
        <View style={styles.adminMetaGrid}>
          <MiniInfo label="Tracks" value={`${counts.deleted_jobs ?? 0}`} />
          <MiniInfo label="Voice Takes" value={`${counts.deleted_voice_takes ?? 0}`} />
          <MiniInfo label="Mode" value="Soft delete" />
        </View>
      </Card>
    </View>
  );
}

function AdminCount({ label, value, warning }: { label: string; value: number; warning?: boolean }) {
  return (
    <View style={[styles.adminCountCard, warning && value > 0 && styles.adminCountWarning]}>
      <Text style={styles.metaText}>{label}</Text>
      <Text style={styles.adminCountValue}>{value}</Text>
    </View>
  );
}

function formatAdminDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "unknown";
  return date.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

function shortId(value: string) {
  if (value.length <= 14) return value;
  return `${value.slice(0, 8)}...${value.slice(-4)}`;
}

function formatBytes(value?: number | null) {
  if (!value) return "Unknown size";
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${Math.round(value / 1024)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function BottomNav({ screen, setScreen, translateY, visible }: { screen: Screen; setScreen: (screen: Screen) => void; translateY: Animated.Value; visible: boolean }) {
  const items: Array<{ label: string; screen: Screen; icon: IconName }> = [
    { label: "Create", screen: "home", icon: "home" },
    { label: "Record", screen: "record", icon: "mic" },
    { label: "Tracks", screen: "history", icon: "waveform" },
    { label: "Profile", screen: "profile", icon: "guest" }
  ];
  const activeScreen: Screen = ["record", "upload", "genre", "producer", "processing", "nameTrack", "nameSuccess", "result", "download"].includes(screen) ? "record" : screen;
  const activeIndex = Math.max(0, items.findIndex((item) => item.screen === activeScreen));
  const [navWidth, setNavWidth] = useState(0);
  const slideProgress = useRef(new Animated.Value(activeIndex)).current;
  const tabWidth = navWidth ? (navWidth - 16) / items.length : 0;

  useEffect(() => {
    Animated.spring(slideProgress, {
      toValue: activeIndex,
      tension: 170,
      friction: 20,
      useNativeDriver: true
    }).start();
  }, [activeIndex, slideProgress]);

  const sliderTranslate = tabWidth
    ? slideProgress.interpolate({
      inputRange: items.map((_, index) => index),
      outputRange: items.map((_, index) => index * tabWidth)
    })
    : 0;

  return (
    <Animated.View
      pointerEvents={visible ? "auto" : "none"}
      onLayout={(event) => setNavWidth(event.nativeEvent.layout.width)}
      style={[styles.bottomNav, { opacity: translateY.interpolate({ inputRange: [0, 94], outputRange: [1, 0.14] }), transform: [{ translateY }] }]}
    >
      {tabWidth > 0 && (
        <Animated.View style={[styles.navSlider, { width: tabWidth, transform: [{ translateX: sliderTranslate }] }]} />
      )}
      {items.map((item) => (
        <Pressable key={item.label} style={({ pressed }) => [styles.navItem, pressed && styles.touchPressedBlue]} onPress={() => setScreen(item.screen)}>
          <IconSymbol name={item.icon} size={18} tone={activeScreen === item.screen ? "blue" : "muted"} />
          <Text style={[styles.navText, activeScreen === item.screen && styles.navTextActive]}>{item.label}</Text>
        </Pressable>
      ))}
    </Animated.View>
  );
}

function CreatorChoice({ selected, icon, title, subtitle, chip, body, onPress }: { selected: boolean; icon: IconName; title: string; subtitle: string; chip: string; body: string; onPress: () => void }) {
  return (
    <Pressable style={({ pressed }) => [styles.workspaceCard, pressed && styles.touchPressedBlue, selected && styles.choiceSelected]} onPress={onPress}>
      <View style={styles.workspaceTitle}>
        <View style={styles.creatorLabel}>
          <View style={styles.iconBadge}><IconSymbol name={icon} size={26} /></View>
          <View>
            <Text style={styles.cardTitle}>{title}</Text>
            <Text style={styles.metaText}>{subtitle}</Text>
          </View>
        </View>
        <OwnershipChip status={selected ? "Saved" : "Temporary"} label={selected ? "Selected" : chip} />
      </View>
      <Text style={styles.subtitle}>{body}</Text>
    </Pressable>
  );
}

function CreatorWorkspaceCard({ mode }: { mode: CreatorMode }) {
  const maxDuration = "300 sec";
  return (
    <View style={styles.workspaceCard}>
      <Row title="Workspace Status" meta={mode === "guest" ? "Guest Creator" : "Saved Creator"} chip={mode === "guest" ? "Temporary" : "Saved"} />
      <View style={styles.statusStrip}>
        <View style={styles.statusPill}>
          <Text style={styles.metaText}>Mode</Text>
          <Text style={styles.statusPillValue}>{mode === "guest" ? "Guest" : "Saved"}</Text>
        </View>
        <View style={styles.statusPill}>
          <Text style={styles.metaText}>Record</Text>
          <Text style={styles.statusPillValue}>{maxDuration}</Text>
        </View>
        <View style={styles.statusPill}>
          <Text style={styles.metaText}>Session</Text>
          <Text style={styles.statusPillValue}>{mode === "guest" ? "Temporary" : "Private"}</Text>
        </View>
      </View>
    </View>
  );
}

function MiniStep({ icon, label }: { icon: IconName; label: string }) {
  return (
    <View style={styles.miniStep}>
      <IconSymbol name={icon} size={20} tone="blue" />
      <Text style={styles.miniStepText}>{label}</Text>
    </View>
  );
}

function AudioRecorder({ seconds, maxDuration, isRecording, state, onPress }: { seconds: number; maxDuration: number; isRecording: boolean; state: "Ready" | "Recording" | "Paused" | "Take ready"; onPress: () => void }) {
  const actionHint = state === "Recording" ? "Tap to pause" : state === "Take ready" ? "Tap to restart" : "Tap to record";
  return (
    <View style={styles.recordModule}>
      <Pressable style={[styles.recordShell, isRecording && styles.recordShellActive]} onPress={onPress}>
        <View style={[styles.recordRing, isRecording && styles.recordRingActive]}>
          <View style={[styles.recordInner, isRecording && styles.recordInnerActive]}>
            <View style={[styles.recordDot, isRecording && styles.recordDotActive, state === "Take ready" && styles.recordDotReady]} />
          </View>
        </View>
      </Pressable>
      <View style={styles.recordCaptionRow}>
        <View style={[styles.recordStatePill, isRecording && styles.recordStatePillActive]}>
          <Text style={[styles.recordStateText, isRecording && styles.recordStateTextActive]}>{state}</Text>
        </View>
        <Text style={styles.recordCaption}>{seconds} of {maxDuration} sec</Text>
      </View>
      <Text style={styles.recordActionHint}>{actionHint}</Text>
    </View>
  );
}

function VoiceCapturePanel({ genre, seconds, maxDuration, isRecording, state, micLevel = 0, signalWarning }: { genre: Genre; seconds: number; maxDuration: number; isRecording: boolean; state: "Ready" | "Recording" | "Paused" | "Take ready"; micLevel?: number; signalWarning?: boolean }) {
  const energy = Platform.OS === "web" && (isRecording || seconds > 0) ? micLevel : getSimulatedVoiceEnergy(seconds, isRecording);
  const levelLabel = signalWarning ? "No Input" : !isRecording && seconds === 0 ? "Waiting" : energy > 0.78 ? "Peaking" : energy > 0.38 ? "Good" : energy > 0.08 ? "Quiet" : "No Input";
  return (
    <View style={styles.capturePanel}>
      <View style={styles.captureHeader}>
        <View style={styles.captureCopy}>
          <Text style={styles.captureTitle}>Record</Text>
          <Text style={styles.metaText}>{state === "Recording" ? "Speak or sing into the mic" : state === "Ready" ? "Tap record to begin" : "Preview saved audio shape"}</Text>
        </View>
        <OwnershipChip status={state === "Recording" ? "Processing" : state === "Take ready" ? "Ready" : "Temporary"} label={state} />
      </View>
      <LiveVoiceWaveform genre={genre} seconds={seconds} energy={energy} active={isRecording} />
      <View style={styles.levelRow}>
        <Text style={styles.metaText}>Input Level</Text>
        <Text style={[styles.levelLabel, levelLabel === "Peaking" && styles.levelPeak, levelLabel === "Good" && styles.levelGood, levelLabel === "No Input" && styles.levelNoInput]}>{levelLabel}</Text>
      </View>
      <View style={styles.levelTrack}>
        <View style={[styles.levelFill, { width: `${Math.max(8, energy * 100)}%` as DimensionValue }, levelLabel === "Peaking" && styles.levelFillPeak]} />
      </View>
      <Text style={styles.helperNote}>{signalWarning ? "No voice signal was detected. Pick the right microphone in the browser and record again." : isRecording ? "Live mic input is being measured from the browser." : seconds > 0 ? `${seconds}s captured from ${maxDuration}s limit.` : "Waveform wakes up when recording starts."}</Text>
    </View>
  );
}

function LiveVoiceWaveform({ genre, seconds, energy, active }: { genre: Genre; seconds: number; energy: number; active: boolean }) {
  const bars = Array.from({ length: 32 }, (_, index) => {
    const phase = seconds * 0.76 + index * 0.58;
    const speech = Math.abs(Math.sin(phase) * 0.58 + Math.cos(phase * 0.47) * 0.42);
    const phraseShape = index % 7 === 0 ? 0.36 : index % 5 === 0 ? 0.22 : 0;
    const idle = active ? energy : seconds > 0 ? 0.34 : 0.08;
    return 14 + Math.min(78, (speech + phraseShape) * 56 * idle + (index % 3) * 3);
  });
  return (
    <View style={styles.liveWaveFrame}>
      <View style={styles.liveWaveBaseline} />
      <View style={styles.liveWave}>
        {bars.map((height, index) => (
          <View
            key={`${index}-${seconds}`}
            style={[
              styles.liveWaveBar,
              {
                height,
                backgroundColor: index % 4 === 0 ? colors.blue : index % 3 === 0 ? genre.color : colors.pink,
                opacity: active ? 0.95 : 0.52
              }
            ]}
          />
        ))}
      </View>
    </View>
  );
}

function getSimulatedVoiceEnergy(seconds: number, active: boolean) {
  if (!active && seconds === 0) return 0.08;
  if (!active) return 0.34;
  const wave = Math.abs(Math.sin(seconds * 1.7) * 0.46 + Math.cos(seconds * 0.63) * 0.34);
  return Math.min(0.96, 0.28 + wave);
}

function DurationCard({ seconds, maxDuration }: { seconds: number; maxDuration: number }) {
  const progress = `${Math.min(seconds / maxDuration, 1) * 100}%` as DimensionValue;
  const midpoint = Math.round(maxDuration / 2);
  return (
    <View style={styles.durationCard}>
      <View style={styles.row}>
        <View>
          <Text style={styles.metaText}>Duration</Text>
          <Text style={styles.durationValue}>{seconds} sec</Text>
        </View>
        <Text style={styles.metaText}>{Math.max(maxDuration - seconds, 0)} sec left</Text>
      </View>
      <View style={styles.durationTrack}>
        <View style={[styles.durationFill, { width: progress }]} />
      </View>
      <View style={styles.durationTicks}>
        <Text style={styles.tickText}>0</Text>
        <Text style={styles.tickText}>{Math.round(midpoint / 2)}</Text>
        <Text style={styles.tickText}>{midpoint}</Text>
        <Text style={styles.tickText}>{maxDuration}</Text>
      </View>
    </View>
  );
}

function AuraWaveform({ genre, compact, tall, active, mode = "vocal" }: { genre: Genre; compact?: boolean; tall?: boolean; active?: boolean; mode?: WaveformMode }) {
  const height = tall ? 150 : compact ? 112 : 132;
  const [phase, setPhase] = useState(0);

  useEffect(() => {
    if (!active) {
      setPhase(0);
      return;
    }
    const timer = setInterval(() => setPhase((current) => (current + 1) % 4), mode === "vocal" ? 150 : 210);
    return () => clearInterval(timer);
  }, [active]);

  const waves = [
    [
      "M-12 74 C16 54, 30 96, 54 66 S88 28, 108 80 S142 118, 164 54 S196 18, 218 74 S252 112, 276 62 S306 44, 332 74",
      "M-12 72 C16 62, 24 48, 38 55 C55 64, 54 108, 72 110 C92 112, 88 24, 110 28 C131 32, 124 120, 150 118 C174 116, 172 22, 194 20 C218 18, 212 106, 236 104 C260 102, 258 42, 280 44 C300 46, 306 66, 332 72",
      "M-12 68 C24 80, 42 36, 64 62 S96 108, 122 66 S156 26, 182 72 S220 110, 246 62 S292 34, 332 74"
    ],
    [
      "M-12 68 C18 96, 34 46, 58 72 S92 114, 116 58 S148 18, 172 78 S204 124, 228 64 S260 34, 286 76 S314 100, 332 62",
      "M-12 76 C12 44, 32 84, 50 58 C72 32, 70 116, 96 112 C122 108, 112 24, 140 28 C168 32, 158 120, 188 114 C214 108, 210 32, 236 34 C262 36, 260 108, 286 96 C306 88, 314 58, 332 72",
      "M-12 74 C18 42, 42 86, 66 58 S100 28, 124 74 S158 118, 184 66 S220 28, 244 78 S286 116, 332 64"
    ],
    [
      "M-12 76 C20 36, 36 82, 58 56 S90 18, 114 72 S148 124, 174 62 S208 26, 232 82 S270 122, 292 68 S314 44, 332 78",
      "M-12 70 C14 86, 30 40, 54 54 C78 68, 76 116, 100 108 C126 100, 118 20, 146 26 C174 32, 166 120, 192 118 C220 116, 216 28, 242 36 C266 44, 266 102, 290 102 C310 102, 318 66, 332 70",
      "M-12 66 C22 88, 44 42, 70 70 S106 116, 130 62 S164 20, 190 76 S226 118, 252 58 S294 30, 332 76"
    ],
    [
      "M-12 72 C14 62, 30 34, 52 64 S84 112, 108 70 S144 28, 168 76 S202 116, 226 58 S260 22, 286 70 S314 98, 332 68",
      "M-12 74 C14 54, 26 92, 48 62 C72 30, 72 104, 96 112 C122 120, 116 34, 144 24 C172 14, 168 108, 194 118 C222 128, 218 44, 244 34 C270 24, 270 96, 294 104 C314 110, 320 78, 332 74",
      "M-12 70 C20 78, 40 30, 66 64 S102 110, 128 68 S162 34, 188 72 S224 108, 250 64 S292 38, 332 72"
    ]
  ];
  const [softWave, vocalWave, genreWave] = waves[phase];
  const showVocal = mode === "vocal" || mode === "blend";
  const showGenre = mode === "genre" || mode === "blend";
  const vocalColor = colors.pink;
  return (
    <View style={[styles.auraWave, { height }, { shadowColor: genre.color }, active && styles.auraWaveActive]}>
      <Svg viewBox="0 0 320 140" preserveAspectRatio="none" style={StyleSheet.absoluteFill}>
        {showGenre && <Path d={softWave} stroke={genre.soft} strokeWidth={5.4} fill="none" strokeLinecap="round" opacity={mode === "genre" ? 0.46 : 0.38} />}
        {showVocal && <Path d={vocalWave} stroke={vocalColor} strokeWidth={mode === "vocal" ? 4.8 : 3.3} fill="none" strokeLinecap="round" opacity={active ? 1 : 0.82} />}
        {showGenre && <Path d={genreWave} stroke={genre.color} strokeWidth={mode === "genre" ? 4 : 3.1} fill="none" strokeLinecap="round" opacity={1} />}
      </Svg>
    </View>
  );
}

function GenreTile({ genre, selected, onPress }: { genre: Genre; selected: boolean; onPress: () => void }) {
  return (
    <Pressable style={({ pressed }) => [styles.genreTile, pressed && styles.touchPressedBlue, { borderColor: selected ? genre.color : colors.line, backgroundColor: selected ? genre.soft : colors.panel }]} onPress={onPress}>
      <Text style={styles.genreTitle}>{genre.label}</Text>
      <GenreWavePreview genre={genre} />
    </Pressable>
  );
}

function GenreWavePreview({ genre }: { genre: Genre }) {
  return (
    <Svg viewBox="0 0 120 34" preserveAspectRatio="none" style={styles.genreWave}>
      <Path d="M0 18 C18 6, 26 30, 42 17 S66 6, 82 18 S104 28, 120 14" stroke="#ff6f91" strokeWidth={3} fill="none" strokeLinecap="round" />
      <Path d="M0 20 C16 22, 26 8, 42 18 S68 30, 84 15 S104 8, 120 18" stroke={genre.color} strokeWidth={2.2} fill="none" strokeLinecap="round" />
    </Svg>
  );
}

function ProcessingSteps({ activeIndex }: { activeIndex: number }) {
  return (
    <View>
      {processingSteps.map((step, index) => {
        const state = index < activeIndex ? "done" : index === activeIndex ? "active" : "pending";
        return <ProcessingStep key={step} label={step} state={state} />;
      })}
    </View>
  );
}

function ProcessingStep({ label, state }: { label: string; state: "done" | "active" | "pending" }) {
  const icon = state === "done" ? "success" : "processing";
  return (
    <View style={styles.stageRow}>
      <Text style={styles.stageText}>{label}</Text>
      <View style={[styles.stepIcon, state === "done" && styles.stepDone, state === "pending" && styles.stepPending]}>
        <IconSymbol name={icon} tone={state === "pending" ? "muted" : "ink"} />
      </View>
    </View>
  );
}

function MusicPlayer({
  creatorMode,
  genre,
  source,
  backendFinalUrl,
  backendDownloadUrl,
  exportUrls,
  analysis,
  blueprint,
  trackName,
  fileNameMode,
  isPlaying,
  mixDurationMs,
  mixPositionMs,
  hasDownloaded,
  hasShared,
  hasSaved,
  setHasDownloaded,
  setHasShared,
  setHasSaved,
  showToast,
  onRemember,
  onDelete,
  onNavigate,
  onPlayMix
}: {
  creatorMode: CreatorMode;
  genre: Genre;
  source: InputSource;
  backendFinalUrl: string | null;
  backendDownloadUrl: string | null;
  exportUrls: DemoExportUrls;
  analysis: BackendSongAnalysis | null;
  blueprint: BackendSongBlueprint | null;
  trackName: string;
  fileNameMode: FileNameMode;
  isPlaying: boolean;
  mixDurationMs: number;
  mixPositionMs: number;
  hasDownloaded: boolean;
  hasShared: boolean;
  hasSaved: boolean;
  setHasDownloaded: (value: boolean) => void;
  setHasShared: (value: boolean) => void;
  setHasSaved: (value: boolean) => void;
  showToast: (message: string) => void;
  onRemember: (status?: TrackStatus) => void;
  onDelete: () => void;
  onNavigate: (screen: Screen) => void;
  onPlayMix: () => void | Promise<void>;
}) {
  const fileName = buildFileName(trackName, genre, fileNameMode);
  const downloadUrl = backendDownloadUrl ?? backendFinalUrl;
  const duration = mixDurationMs || estimatedDurationMs(source);
  const progress = `${Math.min(100, Math.max(0, (mixPositionMs / duration) * 100))}%` as const;

  return (
    <View>
      <View style={styles.finalMixCard}>
        <View style={styles.finalMixHeader}>
          <View style={styles.finalMixTitleBlock}>
            <Text style={styles.finalMixEyebrow}>Private Demo</Text>
            <Text style={styles.finalMixTitle}>{buildTrackTitle(trackName, genre, fileNameMode)}</Text>
            <Text style={styles.finalMixMeta}>{buildFileName(trackName, genre, fileNameMode)}</Text>
          </View>
          <OwnershipChip status="Ready" label={genre.label} />
        </View>
        <AuraWaveform genre={genre} tall mode="genre" />
        <View style={styles.mp3Timeline}>
          <View style={styles.mp3TimelineHeader}>
            <Text style={styles.mp3TimeText}>{formatPlayerTime(mixPositionMs)}</Text>
            <Text style={styles.mp3TimeText}>{formatPlayerTime(duration)}</Text>
          </View>
          <View style={styles.mp3Track}>
            <View style={[styles.mp3Fill, { width: progress }]} />
          </View>
        </View>
        <View style={styles.finalMixMetaRow}>
          <MiniInfo label="Source" value={getSourceLabel(source)} />
          <MiniInfo label="BPM" value={analysis?.bpm ? `${Math.round(analysis.bpm)}` : "Estimate"} />
          <MiniInfo label="Key" value={analysis?.key ?? "Estimate"} />
          <MiniInfo label="Mode" value={getArrangementModeLabel(source.arrangementMode)} />
        </View>
        <PrimaryButton label={isPlaying ? "Pause Mix" : "Play Mix"} icon="play" onPress={onPlayMix} golden />
      </View>
      <DemoAnalysisPanel analysis={analysis} genre={genre} />
      <BlueprintPanel blueprint={blueprint} />
      <View style={styles.resultActionRow}>
        <ActionButton label={hasDownloaded ? "Downloaded" : "Download"} icon={hasDownloaded ? "success" : "download"} onPress={() => {
          if (!downloadUrl) {
            showToast("MP3 is not ready yet");
            return;
          }
          downloadUrlToLocalFile(downloadUrl, fileName).then(() => {
            showToast("Download saved locally");
          }).catch((error) => showToast(`Download failed: ${errorMessage(error)}`));
          setHasDownloaded(true);
          onRemember("Downloaded");
        }} />
        <ActionButton label={hasShared ? "Shared" : "Share"} icon={hasShared ? "success" : "share"} onPress={() => {
          setHasShared(true);
          onRemember("Shared");
          showToast("Share marked complete");
        }} />
        <ActionButton label={hasSaved ? "Saved" : "Save"} icon={hasSaved ? "success" : "saved"} onPress={() => {
          setHasSaved(true);
          onRemember(creatorMode === "saved" ? "Saved" : "Temporary");
          showToast(creatorMode === "guest" ? "Saved to temporary vault" : "Saved to Idea Vault");
          onNavigate("history");
        }} />
      </View>
      <View style={styles.resultFooterRow}>
        <SecondaryButton label={exportUrls.producerPack ? "Producer Pack" : "Exports"} icon="download" onPress={() => onNavigate("download")} compact />
        <SecondaryButton label="Try Genre" icon="regenerate" onPress={() => onNavigate("genre")} compact />
        <SecondaryButton label="Delete" icon="trash" onPress={onDelete} compact />
      </View>
      <Text style={styles.helperNote}>{backendFinalUrl ? "Demo exports are ready from the private backend." : "Demo exports appear after the backend worker finishes."}</Text>
    </View>
  );
}

function DemoAnalysisPanel({ analysis, genre }: { analysis: BackendSongAnalysis | null; genre: Genre }) {
  const display = analysis ?? {
    bpm: null,
    key: null,
    duration_seconds: 0,
    energy: "Pending",
    mood: "Private demo",
    vocal_energy: 0,
    suggested_genre: genre.label,
    pitch_summary: "Run the backend worker to see pitch and energy notes."
  };
  return (
    <Card>
      <Text style={styles.cardTitle}>Idea Analysis</Text>
      <View style={styles.finalMixMetaRow}>
        <MiniInfo label="BPM" value={display.bpm ? `${Math.round(display.bpm)}` : "Estimate"} />
        <MiniInfo label="Key" value={display.key ?? "Estimate"} />
        <MiniInfo label="Mood" value={display.mood} />
      </View>
      <View style={styles.finalMixMetaRow}>
        <MiniInfo label="Energy" value={display.energy} />
        <MiniInfo label="Genre" value={display.suggested_genre} />
        <MiniInfo label="Length" value={display.duration_seconds ? `${Math.round(display.duration_seconds)}s` : "Pending"} />
      </View>
      <Text style={styles.subtitle}>{display.pitch_summary}</Text>
    </Card>
  );
}

function BlueprintPanel({ blueprint }: { blueprint: BackendSongBlueprint | null }) {
  const sections = blueprint?.structure ?? [];
  return (
    <Card>
      <Text style={styles.cardTitle}>Song Blueprint</Text>
      <Text style={styles.subtitle}>{blueprint?.chords?.length ? blueprint.chords.join(" - ") : "Chords appear after analysis."}</Text>
      {sections.slice(0, 6).map((section) => (
        <View key={`${section.name}-${section.bars}`} style={styles.stageRow}>
          <Text style={styles.stageText}>{section.name}</Text>
          <Text style={styles.metaText}>{section.bars} bars</Text>
        </View>
      ))}
      {(blueprint?.production_notes ?? []).slice(0, 2).map((note) => (
        <Text key={note} style={styles.helperNote}>{note}</Text>
      ))}
    </Card>
  );
}

function MiniInfo({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.miniInfo}>
      <Text style={styles.miniInfoLabel}>{label}</Text>
      <Text style={styles.miniInfoValue} numberOfLines={1}>{value}</Text>
    </View>
  );
}

function ActionButton({ label, icon, onPress }: { label: string; icon: IconName; onPress: () => void }) {
  return (
    <Pressable style={({ pressed }) => [styles.resultAction, pressed && styles.touchPressedBlue]} onPress={onPress}>
      <IconSymbol name={icon} size={22} tone="blue" />
      <Text style={styles.resultActionText}>{label}</Text>
    </Pressable>
  );
}

function FileNameEditor({
  genre,
  trackName,
  setTrackName,
  mode,
  setMode,
  compact
}: {
  genre: Genre;
  trackName: string;
  setTrackName: (name: string) => void;
  mode: FileNameMode;
  setMode: (mode: FileNameMode) => void;
  compact?: boolean;
}) {
  const needsName = trackName.trim().length === 0;
  const activeMode = needsName ? "rename" : mode;
  const options: Array<{ label: string; mode: FileNameMode }> = [
    { label: "Keep name", mode: "keep" },
    { label: "Rename", mode: "rename" },
    { label: "Add genre tag", mode: "tag" }
  ];
  return (
    <Card>
      <View style={styles.row}>
        <View>
          <Text style={styles.cardTitle}>File name</Text>
          <Text style={styles.metaText}>{buildFileName(trackName, genre, mode)}</Text>
        </View>
        <OwnershipChip status="Private" label="MP3" />
      </View>
      <View style={styles.fileOptionRow}>
        {options.map((option) => (
          <Pressable key={option.mode} style={({ pressed }) => [styles.fileOption, pressed && styles.touchPressedBlue, activeMode === option.mode && styles.fileOptionActive]} onPress={() => setMode(option.mode)}>
            <Text style={[styles.fileOptionText, activeMode === option.mode && styles.fileOptionTextActive]}>{option.label}</Text>
          </Pressable>
        ))}
      </View>
      {needsName && <Text style={styles.namePrompt}>Name this demo before downloading.</Text>}
      {(activeMode === "rename" || activeMode === "tag") && (
        <TextInput
          value={trackName}
          onChangeText={setTrackName}
          placeholder="Enter track name"
          placeholderTextColor={colors.muted}
          style={[styles.input, compact && styles.compactInput]}
        />
      )}
    </Card>
  );
}

function TrackListItem({ title, meta, status, icon = "waveform", actions }: { title: string; meta: string; status: TrackStatus; icon?: IconName; actions?: TrackAction[] }) {
  const [showActions, setShowActions] = useState(false);
  return (
    <View style={styles.trackItem}>
      <View style={styles.trackRow}>
        <View style={styles.libraryTrackIcon}>
          <IconSymbol name={icon} tone="blue" size={23} />
        </View>
        <View style={styles.trackTextBlock}>
          <Text style={styles.trackTitle}>{title}</Text>
          <Text style={styles.metaText}>{meta}</Text>
        </View>
        <View style={styles.trackTrailing}>
          <OwnershipChip status={status} />
          {actions && actions.length > 0 && (
            <Pressable style={({ pressed }) => [styles.moreButton, pressed && styles.touchPressedBlue]} onPress={() => setShowActions((current) => !current)}>
              <IconSymbol name="more" tone="blue" size={22} />
            </Pressable>
          )}
        </View>
      </View>
      {showActions && actions && (
        <View style={styles.trackActions}>
          {actions.map((action) => (
            <Pressable key={action.label} style={({ pressed }) => [styles.trackActionButton, pressed && styles.touchPressedBlue, action.destructive && styles.trackActionDestructive]} onPress={() => {
              setShowActions(false);
              action.onPress();
            }}>
              <IconSymbol name={action.icon} tone={action.destructive ? "muted" : "blue"} size={19} />
              <Text style={[styles.trackActionText, action.destructive && styles.trackActionTextDestructive]}>{action.label}</Text>
            </Pressable>
          ))}
        </View>
      )}
    </View>
  );
}

function OwnershipChip({ status, label }: { status: TrackStatus | "Private"; label?: string }) {
  const chipStyle = status === "Saved" ? styles.chipSaved : status === "Temporary" ? styles.chipTemporary : status === "Retry" ? styles.chipRetry : styles.chipPrivate;
  return (
    <View style={[styles.chip, chipStyle]}>
      <Text style={styles.chipText}>{label ?? status}</Text>
    </View>
  );
}

function Card({ children, centered }: { children: React.ReactNode; centered?: boolean }) {
  return <View style={[styles.card, centered && styles.centered]}>{children}</View>;
}

function Row({ title, meta, chip }: { title: string; meta: string; chip?: TrackStatus }) {
  return (
    <View style={styles.row}>
      <View>
        <Text style={styles.cardTitle}>{title}</Text>
        <Text style={styles.metaText}>{meta}</Text>
      </View>
      {chip && <OwnershipChip status={chip} />}
    </View>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.metricCard}>
      <Text style={styles.metaText}>{label}</Text>
      <Text style={styles.metricValue}>{value}</Text>
    </View>
  );
}

function SettingsToggle({ label, value, icon, enabled, onPress }: { label: string; value: string; icon: IconName; enabled: boolean; onPress: () => void }) {
  return (
    <Pressable style={({ pressed }) => [styles.privacyAction, pressed && styles.touchPressedBlue]} onPress={onPress}>
      <View style={styles.inlineLabel}>
        <IconSymbol name={icon} tone="blue" size={21} />
        <View>
          <Text style={styles.privacyLabel}>{label}</Text>
          <Text style={styles.settingValue}>{value}</Text>
        </View>
      </View>
      <View style={[styles.switchTrack, enabled && styles.switchTrackOn]}>
        <View style={[styles.switchThumb, enabled && styles.switchThumbOn]} />
      </View>
    </Pressable>
  );
}

function SettingStepper({ label, value, icon, color = colors.blue, onPress }: { label: string; value: string; icon: IconName; color?: string; onPress: () => void }) {
  return (
    <Pressable style={({ pressed }) => [styles.privacyAction, pressed && styles.touchPressedBlue]} onPress={onPress}>
      <View style={styles.inlineLabel}>
        <IconSymbol name={icon} tone="blue" size={21} />
        <View>
          <Text style={styles.privacyLabel}>{label}</Text>
          <Text style={[styles.settingValue, { color }]}>{value}</Text>
        </View>
      </View>
      <IconSymbol name="continue" tone="blue" />
    </Pressable>
  );
}

function DisabledSetting({ label, value, icon }: { label: string; value: string; icon: IconName }) {
  return (
    <View style={[styles.privacyAction, styles.disabledPanel]}>
      <View style={styles.inlineLabel}>
        <IconSymbol name={icon} tone="muted" size={21} />
        <View>
          <Text style={styles.privacyLabel}>{label}</Text>
          <Text style={styles.settingValue}>{value}</Text>
        </View>
      </View>
      <OwnershipChip status="Ready" label="Later" />
    </View>
  );
}

function StatusNotice({ title, body, icon }: { title: string; body: string; icon: IconName }) {
  return (
    <View style={styles.statusNotice}>
      <IconSymbol name={icon} tone="blue" size={22} />
      <View style={styles.noticeCopy}>
        <Text style={styles.privacyLabel}>{title}</Text>
        <Text style={styles.settingValue}>{body}</Text>
      </View>
    </View>
  );
}

function Toast({ message, aboveTabs }: { message: string; aboveTabs: boolean }) {
  if (!message) return null;
  return (
    <View pointerEvents="none" style={[styles.toast, aboveTabs ? styles.toastAboveTabs : styles.toastLow]}>
      <IconSymbol name="success" tone="ink" size={18} />
      <Text style={styles.toastText}>{message}</Text>
    </View>
  );
}

function IntegrationStatus() {
  const checks = [
    "Auth: Firebase",
    "Upload: Cloud Storage signed URL",
    "Jobs: local FastAPI",
    "History: account-scoped API",
    "Still next: Firestore profile sync"
  ];
  return (
    <Card>
      <Text style={styles.cardTitle}>Integration status</Text>
      <View style={styles.integrationGrid}>
        {checks.map((check) => (
          <View key={check} style={styles.integrationPill}>
            <Text style={styles.integrationText}>{check}</Text>
          </View>
        ))}
      </View>
    </Card>
  );
}

function PrimaryButton({ label, icon, onPress, disabled, compact, golden }: { label: string; icon?: IconName; onPress: () => void; disabled?: boolean; compact?: boolean; golden?: boolean }) {
  return (
    <Pressable style={({ pressed }) => [styles.primaryButton, golden && styles.goldenButton, compact && styles.compactButton, pressed && !disabled && styles.touchPressedBlue, disabled && styles.buttonDisabled]} onPress={disabled ? undefined : onPress}>
      <View style={styles.buttonContent}>
        {icon && <IconSymbol name={icon} tone="ink" size={20} />}
        <Text style={[styles.primaryButtonText, disabled && styles.disabledText]}>{label}</Text>
      </View>
    </Pressable>
  );
}

function SecondaryButton({ label, icon, onPress, disabled, compact }: { label: string; icon?: IconName; onPress: () => void; disabled?: boolean; compact?: boolean }) {
  return (
    <Pressable style={({ pressed }) => [styles.secondaryButton, compact && styles.compactButton, pressed && !disabled && styles.touchPressedBlue, disabled && styles.secondaryButtonDisabled]} onPress={disabled ? undefined : onPress}>
      <View style={styles.buttonContent}>
        {icon && <IconSymbol name={icon} tone={disabled ? "muted" : "blue"} size={20} />}
        <Text style={[styles.secondaryButtonText, disabled && styles.disabledText]}>{label}</Text>
      </View>
    </Pressable>
  );
}

function IconSymbol({ name, size = 18, tone = "blue" }: { name: IconName; size?: number; tone?: "blue" | "ink" | "muted" }) {
  const color = tone === "ink" ? colors.ink : tone === "muted" ? colors.muted : colors.blue;
  const strokeProps = { stroke: color, strokeWidth: 1.3, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
  return (
    <View style={[styles.iconBox, { width: size, height: size }]}>
      <Svg viewBox="0 0 24 24" width={size} height={size}>
        {name === "play" && <Path d="M9 7.5 L16.5 12 L9 16.5 Z" {...strokeProps} fill="none" />}
        {name === "download" && <><Path d="M12 4.5 V14.5 M8.5 11 L12 14.5 L15.5 11" {...strokeProps} fill="none" /><Path d="M5.5 18.5 H18.5" {...strokeProps} fill="none" /></>}
        {name === "share" && <><Path d="M8 8.5 L12 4.5 L16 8.5 M12 4.5 V15" {...strokeProps} fill="none" /><Path d="M6.5 12.5 V19 H17.5 V12.5" {...strokeProps} fill="none" /></>}
        {name === "back" && <Path d="M14 6 L8 12 L14 18 M8.8 12 H18" {...strokeProps} fill="none" />}
        {name === "edit" && <><Path d="M5.2 18.8 L9.2 17.9 L18.6 8.5 C19.4 7.7 19.4 6.5 18.6 5.7 L18.3 5.4 C17.5 4.6 16.3 4.6 15.5 5.4 L6.1 14.8 Z" {...strokeProps} fill="none" /><Path d="M14.5 6.4 L17.6 9.5 M5.2 18.8 H19" {...strokeProps} fill="none" /></>}
        {name === "logout" && <><Path d="M9.4 5.2 H5.8 C5 5.2 4.4 5.8 4.4 6.6 V17.4 C4.4 18.2 5 18.8 5.8 18.8 H9.4" {...strokeProps} fill="none" /><Path d="M12.1 12 H20 M16.7 7.4 L20.8 12 L16.7 16.6" {...strokeProps} fill="none" /></>}
        {(name === "regenerate" || name === "retry") && <Path d="M17.5 7.5 A7 7 0 0 0 6.5 7 L4.8 8.7 M6.5 7 V11.5 M6.5 16.5 A7 7 0 0 0 17.5 17 L19.2 15.3 M17.5 17 V12.5" {...strokeProps} fill="none" />}
        {name === "settings" && <><Circle cx="12" cy="12" r="3" {...strokeProps} fill="none" /><Path d="M12 4.2 V6.2 M12 17.8 V19.8 M4.2 12 H6.2 M17.8 12 H19.8 M6.5 6.5 L8 8 M16 16 L17.5 17.5 M17.5 6.5 L16 8 M8 16 L6.5 17.5" {...strokeProps} fill="none" /></>}
        {name === "success" || name === "saved" ? <Path d="M5.5 12.5 L10 16.7 L18.5 7.3" {...strokeProps} fill="none" /> : null}
        {name === "continue" && <Path d="M9 5.5 L15.5 12 L9 18.5" {...strokeProps} fill="none" />}
        {name === "upload" && <><Path d="M12 19 V5 M8.5 8.5 L12 5 L15.5 8.5" {...strokeProps} fill="none" /><Path d="M5.5 19.5 H18.5" {...strokeProps} fill="none" /></>}
        {(name === "generate" || name === "waveform") && <Path d="M3 12 H5.3 C6.5 12 6.7 7 8 7 C9.6 7 9.3 17 11 17 C12.8 17 12.5 5 14.2 5 C16 5 15.8 15 17.2 15 C18.3 15 18.4 12 19.6 12 H21" {...strokeProps} fill="none" />}
        {name === "vibe" && <><Path d="M3.2 13 H5.4 C6.6 13 6.8 9.5 8 9.5 C9.4 9.5 9.2 16.5 10.7 16.5 C12.3 16.5 12.1 7.5 13.7 7.5 C15.3 7.5 15.1 14.7 16.5 14.7 C17.5 14.7 17.7 13 18.7 13 H20.8" {...strokeProps} fill="none" /><Path d="M18 3.8 L18.7 5.8 L20.7 6.5 L18.7 7.2 L18 9.2 L17.3 7.2 L15.3 6.5 L17.3 5.8 Z" {...strokeProps} fill="none" /></>}
        {name === "mic" && <><Path d="M9.4 5.2 C9.4 3.6 10.5 2.7 12 2.7 C13.5 2.7 14.6 3.6 14.6 5.2 V10.6 C14.6 12.2 13.5 13.1 12 13.1 C10.5 13.1 9.4 12.2 9.4 10.6 Z" {...strokeProps} fill="none" /><Path d="M11 6 H13 M11 8.3 H13 M6.7 10.3 C6.7 13.6 8.9 15.8 12 15.8 C15.1 15.8 17.3 13.6 17.3 10.3 M12 15.8 V20.3 M8.8 20.3 H15.2" {...strokeProps} fill="none" /></>}
        {name === "home" && <><Path d="M4.2 11.2 L12 4.5 L19.8 11.2" {...strokeProps} fill="none" /><Path d="M6.8 10.2 V19.5 H10.2 V14.8 H13.8 V19.5 H17.2 V10.2" {...strokeProps} fill="none" /></>}
        {name === "creator" && <><Path d="M6.2 15.6 C5.4 14.5 5 13.2 5 11.8 C5 8 7.8 5.3 11.2 5.3 C13.9 5.3 15.9 6.9 16.5 9.2" {...strokeProps} fill="none" /><Path d="M9 9.2 H9.1 M9.2 15.5 L7.4 19.2 L11.1 16.6 C12.9 16.4 14.2 15.6 15.1 14.5" {...strokeProps} fill="none" /><Path d="M13.2 11.7 C14.3 11 15.5 11 16.6 11.7 M18.3 9.2 C20 10.8 20 13.2 18.3 14.8 M20.2 7.4 C22.8 10.2 22.8 13.8 20.2 16.6" {...strokeProps} fill="none" /></>}
        {name === "speak" && <><Path d="M8.2 4.8 C8.2 3.6 9.1 2.9 10.3 2.9 C11.5 2.9 12.4 3.6 12.4 4.8 V8.9 C12.4 10.1 11.5 10.8 10.3 10.8 C9.1 10.8 8.2 10.1 8.2 8.9 Z" {...strokeProps} fill="none" /><Path d="M5.9 8.4 C5.9 11.2 7.7 13 10.3 13 C12.9 13 14.7 11.2 14.7 8.4 M10.3 13 V15.4" {...strokeProps} fill="none" /><Path d="M15.2 13.7 V12.2 C15.2 10.9 16.1 10.1 17.3 10.1 C18.5 10.1 19.4 10.9 19.4 12.2 V13.7" {...strokeProps} fill="none" /><Rect x="14.2" y="13.6" width="6.2" height="5.9" rx="1.4" {...strokeProps} fill="none" /><Path d="M17.3 16 V17.1" {...strokeProps} fill="none" /></>}
        {name === "guest" && <><Path d="M8.5 6.8 C8.5 4.8 10 3.5 12 3.5 C14 3.5 15.5 4.8 15.5 6.8 C15.5 8.9 14 10.2 12 10.2 C10 10.2 8.5 8.9 8.5 6.8 Z" {...strokeProps} fill="none" /><Path d="M6 20 C6.6 15.8 8.8 13.2 12 13.2 C15.2 13.2 17.4 15.8 18 20" {...strokeProps} fill="none" /><Path d="M9.2 13.8 L12 20 L14.8 13.8 M10.3 13.4 L12 15.4 L13.7 13.4" {...strokeProps} fill="none" /><Path d="M7.7 5.8 H16.3 M9 4.7 C10.8 3.8 13.2 3.8 15 4.7" {...strokeProps} fill="none" /></>}
        {name === "experiment" && <><Path d="M9.2 4.2 H14.8 M10.2 4.2 V8.2 L6.4 16.6 C5.7 18.1 6.8 19.8 8.4 19.8 H15.6 C17.2 19.8 18.3 18.1 17.6 16.6 L13.8 8.2 V4.2" {...strokeProps} fill="none" /><Path d="M8.2 15.2 C9.6 14.4 10.8 14.4 12 15.2 C13.2 16 14.6 16 15.8 15.2" {...strokeProps} fill="none" /><Path d="M18.2 4.2 L18.7 5.6 L20.1 6.1 L18.7 6.6 L18.2 8 L17.7 6.6 L16.3 6.1 L17.7 5.6 Z" {...strokeProps} fill="none" /></>}
        {name === "dance" && <><Circle cx="12.2" cy="4.2" r="1.35" {...strokeProps} fill="none" /><Path d="M11.5 6.1 C9.7 7 8.7 8.6 8.9 10.4 C9.2 12.5 11.3 13.4 14.8 12.1 C13.1 13.9 11.8 16.4 10.9 20.2" {...strokeProps} fill="none" /><Path d="M9.6 8.5 C7.6 7.8 6.4 6.4 5.4 4.7 M13.4 7.2 C15.8 7 17.7 6.1 19.2 4.8" {...strokeProps} fill="none" /><Path d="M9.1 11.2 C7 13.2 5.9 15.3 5.7 18 M14.8 12.1 C17 13.6 18.4 15.5 19.2 18.4 M8.2 13.4 C10.6 14.6 13.5 14.6 16.3 12.9" {...strokeProps} fill="none" /></>}
        {name === "processing" && <><Circle cx="12" cy="12" r="1.5" fill={color} /><Circle cx="5.8" cy="12" r="1.25" fill={color} /><Circle cx="18.2" cy="12" r="1.25" fill={color} /></>}
        {name === "error" && <><Circle cx="12" cy="12" r="8" {...strokeProps} fill="none" /><Path d="M12 7.5 V13 M12 16.7 H12.1" {...strokeProps} fill="none" /></>}
        {name === "trash" && <><Path d="M5.5 7 H18.5 M9.2 7 V5 H14.8 V7 M8 9.5 L8.7 19.5 H15.3 L16 9.5 M10.6 10.8 V17 M13.4 10.8 V17" {...strokeProps} fill="none" /></>}
        {name === "recycle" && <><Path d="M7.2 8 H16.8 L16.1 19 H7.9 Z" {...strokeProps} fill="none" /><Path d="M9.2 8 V6.2 H14.8 V8 M6 8 H18" {...strokeProps} fill="none" /><Path d="M9.2 13.2 A3.4 3.4 0 0 1 14.5 10.4 L15.5 11.4 M14.8 10.1 V12.4 H12.5" {...strokeProps} fill="none" /></>}
        {name === "more" && <><Circle cx="6.2" cy="12" r="1.05" fill={color} /><Circle cx="12" cy="12" r="1.05" fill={color} /><Circle cx="17.8" cy="12" r="1.05" fill={color} /></>}
      </Svg>
    </View>
  );
}

const colors = {
  bg: "#020202",
  app: "#070706",
  panel: "#151516",
  panel2: "#242426",
  ink: "#f5f5f7",
  silver: "#d1d1d6",
  muted: "#a1a1a6",
  line: "rgba(225,196,122,0.14)",
  blue: "#c6aa6a",
  pink: "#e1c47a",
  danger: "#ff6f91"
};

const systemFont = "system-ui, -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Segoe UI', sans-serif";
const tapRadius = 20;

const styles = StyleSheet.create({
  safe: {
    flex: 1,
    backgroundColor: colors.bg,
    fontFamily: systemFont
  },
  appShell: {
    flex: 1,
    width: "100%",
    maxWidth: 430,
    alignSelf: "center",
    backgroundColor: "#000"
  },
  startupLoadingScreen: {
    flex: 1,
    height: "100%",
    minHeight: 720,
    marginHorizontal: -20,
    marginTop: -20,
    marginBottom: -20,
    backgroundColor: "#000",
    alignItems: "center",
    justifyContent: "center",
    overflow: "hidden"
  },
  radarGrain: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: "rgba(255,255,255,0.018)"
  },
  radarStage: {
    width: 278,
    height: 278,
    alignItems: "center",
    justifyContent: "center"
  },
  radarPulseRing: {
    position: "absolute",
    width: 258,
    height: 258,
    borderRadius: 129,
    borderWidth: 1,
    borderColor: "rgba(230,230,230,0.18)",
    shadowColor: "#d8d8d8",
    shadowOpacity: 0.2,
    shadowRadius: 24,
    shadowOffset: { width: 0, height: 0 }
  },
  radarSweep: {
    position: "absolute",
    width: 278,
    height: 278,
    alignItems: "center"
  },
  radarSweepLine: {
    position: "absolute",
    top: 24,
    width: 1,
    height: 112,
    backgroundColor: "rgba(235,235,235,0.35)"
  },
  radarSweepGlow: {
    position: "absolute",
    top: 64,
    width: 96,
    height: 96,
    borderTopWidth: 1,
    borderRightWidth: 1,
    borderColor: "rgba(230,230,230,0.16)",
    borderTopRightRadius: 96,
    transform: [{ rotate: "18deg" }]
  },
  radarSigil: {
    position: "absolute",
    width: 88,
    height: 132,
    alignItems: "center",
    justifyContent: "center",
    shadowColor: "#cfcfcf",
    shadowOpacity: 0.18,
    shadowRadius: 18,
    shadowOffset: { width: 0, height: 0 }
  },
  scrollContent: {
    padding: 20,
    paddingBottom: 116
  },
  lockedScreenContent: {
    flex: 1,
    overflow: "hidden"
  },
  centerScreen: {
    minHeight: 680,
    justifyContent: "center"
  },
  splashScreen: {
    minHeight: 680,
    justifyContent: "space-between",
    paddingTop: 6,
    paddingBottom: 8
  },
  splashHeroScreen: {
    minHeight: 720,
    height: "100%",
    marginHorizontal: -20,
    marginTop: -20,
    marginBottom: -20,
    paddingHorizontal: 26,
    paddingTop: 24,
    paddingBottom: 18,
    justifyContent: "flex-start",
    overflow: "hidden",
    backgroundColor: "#000"
  },
  splashImageLayer: {
    ...StyleSheet.absoluteFillObject
  },
  splashImage: {
    flex: 1,
    backgroundColor: "#000"
  },
  splashImageFit: {
    width: "100%",
    height: "100%",
    transform: [{ scale: 1.03 }]
  },
  splashEntryImageFit: {
    width: "100%",
    height: "100%",
    transform: [{ scale: 1.18 }]
  },
  splashEntryPortraitFit: {
    width: "100%",
    height: "100%",
    transform: [{ scale: 1 }]
  },
  splashTopFadeStrong: {
    ...StyleSheet.absoluteFillObject,
    top: 0,
    bottom: undefined,
    height: 180,
    backgroundColor: "rgba(0,0,0,0.38)"
  },
  splashBottomFadeStrong: {
    ...StyleSheet.absoluteFillObject,
    top: undefined,
    height: 430,
    backgroundColor: "rgba(0,0,0,0.12)"
  },
  entryTitleBlock: {
    position: "absolute",
    top: 262,
    left: 26,
    right: 26,
    zIndex: 2,
    paddingHorizontal: 0,
    paddingTop: 0,
    paddingBottom: 0,
    alignItems: "center"
  },
  entryWordmark: {
    width: "122%",
    maxWidth: 500,
    height: 136,
    marginBottom: -4,
    transform: [{ translateX: 6 }]
  },
  entryAlbumCard: {
    width: "100%",
    maxWidth: 392,
    aspectRatio: 1,
    overflow: "hidden",
    borderWidth: 1,
    borderColor: "rgba(198,170,106,0.2)",
    backgroundColor: "#050506"
  },
  entryAlbumImage: {
    flex: 1,
    justifyContent: "flex-end"
  },
  entryAlbumImageFit: {
    width: "100%",
    height: "100%",
    transform: [{ scale: 1.05 }]
  },
  entryAlbumFade: {
    ...StyleSheet.absoluteFillObject,
    top: undefined,
    height: 178,
    backgroundColor: "rgba(0,0,0,0.46)"
  },
  entryAlbumLogoBlock: {
    paddingHorizontal: 18,
    paddingBottom: 18,
    alignItems: "center"
  },
  entryBrand: {
    color: "rgba(198,170,106,0.96)",
    fontSize: 72,
    lineHeight: 74,
    fontFamily: "'Snell Roundhand', 'Brush Script MT', cursive",
    fontWeight: "400",
    letterSpacing: 0,
    textAlign: "center",
    textShadowColor: "rgba(0,0,0,0.78)",
    textShadowOffset: { width: 0, height: 2 },
    textShadowRadius: 10
  },
  entryScriptTag: {
    marginTop: -12,
    color: "rgba(198,170,106,0.82)",
    fontSize: 16,
    lineHeight: 20,
    fontFamily: "'Snell Roundhand', 'Brush Script MT', cursive",
    fontStyle: "italic",
    fontWeight: "400",
    textAlign: "center"
  },
  entrySubline: {
    maxWidth: 320,
    marginTop: 12,
    color: "rgba(239,228,204,0.66)",
    fontSize: 12,
    lineHeight: 18,
    fontFamily: systemFont,
    fontWeight: "500",
    textAlign: "center"
  },
  entryChoiceRow: {
    width: "100%",
    marginTop: 18,
    flexDirection: "row",
    gap: 8
  },
  entryChoiceStack: {
    width: "100%",
    maxWidth: 390,
    marginTop: 24,
    gap: 6
  },
  entryChoiceButton: {
    minHeight: 46,
    borderRadius: 23,
    alignItems: "center",
    justifyContent: "center",
    flexDirection: "row",
    gap: 9,
    borderWidth: 1,
    borderColor: "rgba(239,228,204,0.18)",
    backgroundColor: "rgba(239,228,204,0.055)"
  },
  entryChoiceButtonPressed: {
    borderColor: "rgba(198,170,106,0.34)",
    backgroundColor: "rgba(198,170,106,0.12)"
  },
  entryChoiceButtonSelected: {
    borderColor: "rgba(198,170,106,0.72)",
    backgroundColor: "rgba(198,170,106,0.24)"
  },
  entryChoiceText: {
    color: "rgba(239,228,204,0.78)",
    fontSize: 14,
    fontFamily: systemFont,
    fontWeight: "500"
  },
  entryChoiceTextSelected: {
    color: "#fff4de"
  },
  entryChoiceInfo: {
    width: "100%",
    marginTop: -2,
    marginBottom: 0,
    minHeight: 56,
    paddingHorizontal: 16,
    paddingVertical: 9,
    borderRadius: 22,
    borderWidth: 1,
    borderColor: "rgba(239,228,204,0.12)",
    backgroundColor: "rgba(9,9,11,0.52)"
  },
  entryChoiceTitle: {
    color: "#f1e6d0",
    fontSize: 14,
    lineHeight: 18,
    fontFamily: systemFont,
    fontWeight: "600"
  },
  entryChoiceBody: {
    marginTop: 4,
    color: "rgba(239,228,204,0.68)",
    fontSize: 12,
    lineHeight: 18,
    fontFamily: systemFont,
    fontWeight: "500"
  },
  entryContinueWrap: {
    width: "100%",
    marginTop: -2,
    maxWidth: 390
  },
  splashTopFade: {
    ...StyleSheet.absoluteFillObject,
    bottom: undefined,
    height: 190,
    backgroundColor: "rgba(0,0,0,0.18)"
  },
  splashBottomFade: {
    ...StyleSheet.absoluteFillObject,
    top: undefined,
    height: 260,
    backgroundColor: "rgba(0,0,0,0.18)"
  },
  splashHeroTop: {
    minHeight: 44,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    zIndex: 2
  },
  splashHeroTitleBlock: {
    alignItems: "center",
    zIndex: 2,
    marginTop: 392,
    paddingHorizontal: 18,
    paddingTop: 26,
    paddingBottom: 22,
    borderRadius: 36,
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.18)",
    backgroundColor: "rgba(8,16,30,0.42)",
    shadowColor: "#000",
    shadowOpacity: 0.34,
    shadowRadius: 26,
    overflow: "hidden"
  },
  splashGlassRing: {
    position: "absolute",
    top: -46,
    width: 188,
    height: 188,
    borderRadius: 94,
    borderWidth: 2,
    borderColor: "rgba(255,255,255,0.08)",
    borderRightColor: "rgba(255,255,255,0.18)",
    borderBottomColor: "rgba(255,255,255,0.04)",
    opacity: 0.95
  },
  splashHeroBrand: {
    color: colors.ink,
    fontSize: 38,
    lineHeight: 43,
    fontFamily: systemFont,
    fontWeight: "500",
    letterSpacing: 0,
    textAlign: "center",
    textShadowColor: "rgba(123,183,255,0.42)",
    textShadowOffset: { width: 0, height: 0 },
    textShadowRadius: 16
  },
  splashAppIcon: {
    width: 76,
    height: 76,
    marginTop: 14,
    borderRadius: 18,
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.14)",
    backgroundColor: "#050506"
  },
  splashHeroSubline: {
    marginTop: 8,
    maxWidth: 300,
    color: "rgba(245,245,247,0.68)",
    fontSize: 11,
    lineHeight: 16,
    fontFamily: systemFont,
    fontWeight: "500",
    textAlign: "center",
    textShadowColor: "rgba(0,0,0,0.65)",
    textShadowOffset: { width: 0, height: 1 },
    textShadowRadius: 10
  },
  splashHeroCta: {
    zIndex: 2,
    paddingBottom: 12
  },
  splashHeroButton: {
    width: "100%",
    marginTop: 14
  },
  splashMiniWave: {
    height: 86,
    marginTop: 14,
    borderRadius: 28,
    overflow: "hidden",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.12)",
    backgroundColor: "rgba(12,12,16,0.58)"
  },
  splashTopBar: {
    minHeight: 40,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between"
  },
  splashPill: {
    minHeight: 34,
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    borderRadius: 18,
    paddingHorizontal: 12,
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.14)",
    backgroundColor: "rgba(255,255,255,0.075)"
  },
  splashPillText: {
    color: colors.ink,
    fontSize: 12,
    fontWeight: "500"
  },
  splashStatus: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: "500"
  },
  splashBrandBlock: {
    marginTop: 44
  },
  brandKicker: {
    color: colors.blue,
    fontSize: 13,
    fontWeight: "500",
    textTransform: "uppercase"
  },
  header: {
    marginBottom: 18,
    alignItems: "center"
  },
  headerTop: {
    width: "100%",
    minHeight: 38,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between"
  },
  headerBackButton: {
    width: 34,
    height: 34,
    borderRadius: 17,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.08)",
    backgroundColor: "rgba(255,255,255,0.04)"
  },
  headerBackSpacer: {
    width: 34,
    height: 34
  },
  brand: {
    color: colors.ink,
    fontSize: 42,
    fontFamily: systemFont,
    fontWeight: "500",
    letterSpacing: 0,
    textAlign: "center"
  },
  splashSubtitle: {
    maxWidth: 330,
    marginTop: 10,
    color: colors.muted,
    fontSize: 17,
    lineHeight: 24,
    fontWeight: "500"
  },
  splashWavePanel: {
    marginVertical: 30,
    padding: 18,
    borderRadius: 34,
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.16)",
    backgroundColor: "rgba(26,26,32,0.82)",
    shadowColor: "#000",
    shadowOpacity: 0.36,
    shadowRadius: 28
  },
  splashWaveHeader: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12,
    marginBottom: 8
  },
  splashWaveTitle: {
    color: colors.ink,
    fontSize: 14,
    fontWeight: "600"
  },
  splashStatRow: {
    flexDirection: "row",
    gap: 10,
    marginTop: 14
  },
  splashStat: {
    flex: 1,
    minHeight: 66,
    justifyContent: "center",
    borderRadius: 22,
    paddingHorizontal: 12,
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.1)",
    backgroundColor: "rgba(255,255,255,0.055)"
  },
  splashStatValue: {
    color: colors.ink,
    fontSize: 20,
    fontWeight: "600"
  },
  splashStatLabel: {
    marginTop: 4,
    color: colors.muted,
    fontSize: 11,
    fontWeight: "500"
  },
  splashFooter: {
    marginTop: 14,
    color: colors.muted,
    fontSize: 12,
    lineHeight: 18,
    textAlign: "center",
    fontWeight: "500"
  },
  title: {
    color: colors.ink,
    fontSize: 34,
    lineHeight: 39,
    fontFamily: systemFont,
    fontWeight: "700",
    letterSpacing: 0,
    textAlign: "center"
  },
  hint: {
    marginTop: 8,
    color: colors.muted,
    fontSize: 14,
    lineHeight: 20,
    fontFamily: systemFont,
    textAlign: "center"
  },
  subtitle: {
    color: colors.muted,
    fontSize: 14,
    lineHeight: 20,
    marginTop: 8,
    fontFamily: systemFont
  },
  sectionLabel: {
    marginTop: 18,
    marginBottom: 2,
    color: colors.ink,
    fontSize: 13,
    fontWeight: "600"
  },
  workspaceCard: {
    marginTop: 14,
    padding: 17,
    borderRadius: tapRadius,
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.14)",
    backgroundColor: "rgba(35,35,42,0.72)",
    shadowColor: "#000",
    shadowOpacity: 0.28,
    shadowRadius: 24
  },
  choiceSelected: {
    borderColor: "rgba(198,170,106,0.72)",
    backgroundColor: "rgba(24,54,86,0.82)"
  },
  workspaceTitle: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    gap: 10,
    marginBottom: 10
  },
  creatorLabel: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
    flex: 1
  },
  iconBadge: {
    width: 42,
    height: 42,
    borderRadius: 21,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "transparent"
  },
  iconText: {
    color: colors.blue,
    fontSize: 16,
    fontWeight: "500",
    lineHeight: 18
  },
  lockedPanel: {
    marginTop: 16,
    padding: 14,
    borderRadius: 28,
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.1)",
    backgroundColor: "rgba(255,255,255,0.045)"
  },
  lockedGrid: {
    marginTop: 12,
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 10
  },
  lockedOption: {
    width: "48%",
    minHeight: 62,
    borderRadius: tapRadius,
    padding: 12,
    justifyContent: "space-between",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.08)",
    backgroundColor: "rgba(255,255,255,0.035)",
    opacity: 0.58
  },
  lockedText: {
    color: colors.ink,
    fontSize: 12,
    fontWeight: "500"
  },
  lockText: {
    color: colors.muted,
    fontSize: 10,
    fontWeight: "500"
  },
  detailPanel: {
    marginTop: 14,
    padding: 14,
    borderRadius: tapRadius,
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.13)",
    backgroundColor: "rgba(255,255,255,0.055)"
  },
  input: {
    marginTop: 10,
    minHeight: 52,
    borderRadius: tapRadius,
    paddingHorizontal: 15,
    color: colors.ink,
    fontSize: 14,
    backgroundColor: "rgba(255,255,255,0.075)",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.1)"
  },
  errorText: {
    marginTop: 8,
    color: colors.pink,
    fontSize: 12,
    fontWeight: "500"
  },
  compactInput: {
    minHeight: 46,
    borderRadius: 16
  },
  bioInput: {
    minHeight: 84,
    paddingTop: 14,
    textAlignVertical: "top"
  },
  card: {
    marginTop: 16,
    padding: 16,
    borderRadius: 28,
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: colors.panel
  },
  centered: {
    minHeight: 180,
    alignItems: "center",
    justifyContent: "center"
  },
  uploadOption: {
    marginTop: 10,
    paddingHorizontal: 14,
    borderRadius: 22,
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.08)",
    backgroundColor: "rgba(255,255,255,0.035)"
  },
  uploadOptionSelected: {
    borderColor: "rgba(198,170,106,0.44)",
    backgroundColor: "rgba(198,170,106,0.13)"
  },
  row: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12
  },
  cardTitle: {
    color: colors.ink,
    fontSize: 16,
    fontFamily: systemFont,
    fontWeight: "600"
  },
  sectionTitle: {
    marginTop: 18,
    marginBottom: 2,
    color: colors.ink,
    fontSize: 20,
    lineHeight: 25,
    fontFamily: systemFont,
    fontWeight: "600",
    textAlign: "left"
  },
  metaText: {
    color: colors.muted,
    fontSize: 12,
    fontFamily: systemFont,
    fontWeight: "500"
  },
  intentGrid: {
    marginTop: 14,
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 10
  },
  intentCarousel: {
    gap: 12,
    paddingTop: 14,
    paddingRight: 4
  },
  intentCard: {
    width: 300,
    minHeight: 190,
    borderRadius: tapRadius,
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: "rgba(255,255,255,0.055)",
    overflow: "hidden"
  },
  intentSelected: {
    borderColor: colors.blue,
    backgroundColor: "rgba(198,170,106,0.16)"
  },
  intentArtwork: {
    flex: 1,
    minHeight: 190,
    borderRadius: tapRadius,
    overflow: "hidden",
    backgroundColor: "rgba(255,255,255,0.06)",
    justifyContent: "flex-end"
  },
  intentArtworkImage: {
    ...StyleSheet.absoluteFillObject,
    width: "100%",
    height: "100%",
    borderRadius: tapRadius
  },
  intentArtworkClearShade: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: "rgba(0,0,0,0.02)"
  },
  intentArtworkSelectedShade: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: "rgba(198,170,106,0.08)"
  },
  intentImageLabel: {
    minHeight: 56,
    paddingHorizontal: 13,
    paddingVertical: 9,
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
    backgroundColor: "rgba(0,0,0,0.54)"
  },
  intentLabelCopy: {
    flex: 1,
    minWidth: 0
  },
  intentText: {
    color: colors.ink,
    fontSize: 16,
    fontFamily: systemFont,
    fontWeight: "600"
  },
  intentMeta: {
    marginTop: 2,
    color: colors.blue,
    fontSize: 12,
    fontWeight: "500"
  },
  genrePills: {
    gap: 8,
    paddingTop: 12
  },
  genrePill: {
    borderWidth: 1,
    borderColor: colors.line,
    borderRadius: tapRadius,
    paddingHorizontal: 12,
    paddingVertical: 8,
    backgroundColor: "rgba(255,255,255,0.055)"
  },
  genrePillText: {
    fontSize: 12,
    fontWeight: "500"
  },
  optionWrap: {
    marginTop: 10,
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8
  },
  intentChip: {
    minHeight: 36,
    borderRadius: tapRadius,
    paddingHorizontal: 12,
    paddingVertical: 8,
    justifyContent: "center",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.1)",
    backgroundColor: "rgba(255,255,255,0.045)"
  },
  intentChipActive: {
    borderColor: "rgba(198,170,106,0.48)",
    backgroundColor: "rgba(198,170,106,0.18)"
  },
  intentChipDisabled: {
    opacity: 0.48
  },
  intentChipText: {
    color: colors.muted,
    fontSize: 11,
    fontWeight: "600"
  },
  intentChipTextActive: {
    color: colors.ink
  },
  lyricsInput: {
    minHeight: 92,
    paddingTop: 14,
    textAlignVertical: "top"
  },
  skarlyDetectedPanel: {
    marginTop: 14,
    borderRadius: 18,
    overflow: "hidden",
    borderWidth: 1,
    borderColor: "rgba(198,170,106,0.16)",
    backgroundColor: "rgba(255,255,255,0.035)"
  },
  skarlyFactRow: {
    minHeight: 46,
    paddingHorizontal: 12,
    paddingVertical: 9,
    borderBottomWidth: 1,
    borderBottomColor: "rgba(198,170,106,0.1)",
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 14
  },
  skarlyFactValue: {
    flexShrink: 1,
    color: colors.ink,
    fontSize: 13,
    fontWeight: "600",
    textAlign: "right"
  },
  songMapWaveformPanel: {
    marginTop: 14,
    borderRadius: 16,
    paddingHorizontal: 10,
    paddingVertical: 9,
    borderWidth: 1,
    borderColor: "rgba(123,183,255,0.2)",
    backgroundColor: "rgba(0,0,0,0.18)"
  },
  songMapWaveformGraph: {
    marginTop: 6,
    height: 68,
    borderRadius: 12,
    overflow: "hidden",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.06)",
    backgroundColor: "rgba(255,255,255,0.035)"
  },
  songMapTrack: {
    marginTop: 14,
    flexDirection: "row",
    minHeight: 76,
    overflow: "hidden",
    borderRadius: 16,
    borderWidth: 1,
    borderColor: "rgba(198,170,106,0.18)",
    backgroundColor: "rgba(255,255,255,0.035)"
  },
  songMapSegment: {
    minWidth: 42,
    paddingHorizontal: 7,
    paddingVertical: 9,
    justifyContent: "space-between",
    borderRightWidth: 1,
    borderRightColor: "rgba(198,170,106,0.14)",
    backgroundColor: "rgba(198,170,106,0.17)"
  },
  songMapSegmentAlt: {
    backgroundColor: "rgba(225,196,122,0.09)"
  },
  songMapLabel: {
    color: colors.ink,
    fontSize: 11,
    fontWeight: "700",
    textTransform: "capitalize"
  },
  songMapTime: {
    marginTop: 5,
    color: colors.muted,
    fontSize: 10,
    fontWeight: "600"
  },
  skarlyVersionCard: {
    marginTop: 12,
    padding: 14,
    borderRadius: 22,
    borderWidth: 1,
    borderColor: "rgba(198,170,106,0.14)",
    backgroundColor: "rgba(255,255,255,0.045)"
  },
  skarlyVersionCardSelected: {
    borderColor: "rgba(198,170,106,0.64)",
    backgroundColor: "rgba(198,170,106,0.13)"
  },
  finalVersionMessageCard: {
    marginTop: 12,
    minHeight: 96,
    paddingHorizontal: 14,
    paddingVertical: 12,
    borderRadius: 22,
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    borderWidth: 1,
    borderColor: "rgba(214,255,209,0.9)",
    backgroundColor: "#d6ffd1"
  },
  finalVersionMessageAvatar: {
    width: 60,
    height: 60,
    borderRadius: 30,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#ffab1a"
  },
  finalVersionMessageBody: {
    flex: 1,
    minWidth: 0
  },
  finalVersionMessageTitle: {
    color: "#17231c",
    fontSize: 13,
    fontWeight: "700"
  },
  finalVersionMessageControls: {
    marginTop: 7,
    flexDirection: "row",
    alignItems: "center",
    gap: 8
  },
  finalVersionMessagePlay: {
    width: 30,
    height: 38,
    alignItems: "center",
    justifyContent: "center"
  },
  finalVersionMessagePlayPressed: {
    opacity: 0.55,
    transform: [{ scale: 0.96 }]
  },
  finalVersionMessageProgressArea: {
    flex: 1
  },
  finalVersionMessageTrack: {
    position: "relative",
    height: 4,
    borderRadius: 999,
    backgroundColor: "rgba(23,35,28,0.16)"
  },
  finalVersionMessageFill: {
    height: 4,
    borderRadius: 999,
    backgroundColor: "#2e9bd3"
  },
  finalVersionMessageKnob: {
    position: "absolute",
    top: -5,
    width: 14,
    height: 14,
    marginLeft: -7,
    borderRadius: 7,
    backgroundColor: "#2e9bd3"
  },
  finalVersionMessageMeta: {
    marginTop: 7,
    flexDirection: "row",
    justifyContent: "space-between"
  },
  finalVersionMessageTime: {
    color: "rgba(23,35,28,0.68)",
    fontSize: 11,
    fontWeight: "600"
  },
  skarlyWaveformStack: {
    marginTop: 14,
    gap: 10
  },
  waveformPanel: {
    borderRadius: 16,
    paddingHorizontal: 10,
    paddingVertical: 9,
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.08)",
    backgroundColor: "rgba(0,0,0,0.18)"
  },
  waveformPanelHeader: {
    minHeight: 22,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 10
  },
  waveformPointCount: {
    color: colors.muted,
    fontSize: 10,
    fontWeight: "600"
  },
  waveformGraph: {
    marginTop: 6,
    height: 58,
    borderRadius: 12,
    overflow: "hidden",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.06)",
    backgroundColor: "rgba(255,255,255,0.035)"
  },
  metricPair: {
    marginTop: 12,
    flexDirection: "row",
    gap: 10
  },
  statusStrip: {
    marginTop: 12,
    flexDirection: "row",
    gap: 8
  },
  statusPill: {
    flex: 1,
    minHeight: 58,
    borderRadius: tapRadius,
    paddingHorizontal: 11,
    paddingVertical: 10,
    justifyContent: "center",
    borderWidth: 1,
    borderColor: "rgba(198,170,106,0.16)",
    backgroundColor: "rgba(255,255,255,0.045)"
  },
  statusPillValue: {
    marginTop: 3,
    color: colors.ink,
    fontSize: 13,
    fontWeight: "600"
  },
  adminMetaGrid: {
    marginTop: 14,
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8
  },
  adminCountGrid: {
    marginTop: 14,
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 10
  },
  adminCountCard: {
    width: "47%",
    minHeight: 74,
    borderRadius: 22,
    padding: 14,
    justifyContent: "center",
    borderWidth: 1,
    borderColor: "rgba(198,170,106,0.17)",
    backgroundColor: "rgba(255,255,255,0.045)"
  },
  adminCountWarning: {
    borderColor: "rgba(255,111,145,0.34)",
    backgroundColor: "rgba(255,111,145,0.09)"
  },
  adminCountValue: {
    marginTop: 6,
    color: colors.ink,
    fontSize: 25,
    fontWeight: "600"
  },
  latestPreview: {
    marginTop: 12,
    minHeight: 64,
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    borderRadius: tapRadius,
    padding: 12,
    borderWidth: 1,
    borderColor: "rgba(198,170,106,0.14)",
    backgroundColor: "rgba(255,255,255,0.04)"
  },
  latestIcon: {
    width: 42,
    height: 42,
    borderRadius: 21,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1,
    borderColor: "rgba(198,170,106,0.18)",
    backgroundColor: "rgba(198,170,106,0.08)"
  },
  latestCopy: {
    flex: 1,
    minWidth: 0
  },
  homeActionRow: {
    flexDirection: "row",
    gap: 8,
    marginTop: 12
  },
  emptyFlow: {
    marginTop: 16,
    minHeight: 58,
    borderRadius: tapRadius,
    paddingHorizontal: 12,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    borderWidth: 1,
    borderColor: "rgba(198,170,106,0.14)",
    backgroundColor: "rgba(255,255,255,0.035)"
  },
  emptyArrow: {
    color: colors.muted,
    fontSize: 15,
    fontWeight: "500"
  },
  miniStep: {
    minWidth: 72,
    alignItems: "center",
    justifyContent: "center",
    gap: 5
  },
  miniStepText: {
    color: colors.ink,
    fontSize: 11,
    fontWeight: "500",
    textAlign: "center"
  },
  finalMixCard: {
    marginTop: 14,
    padding: 16,
    borderRadius: 30,
    borderWidth: 1,
    borderColor: "rgba(198,170,106,0.2)",
    backgroundColor: "rgba(16,16,18,0.98)"
  },
  finalMixHeader: {
    flexDirection: "row",
    alignItems: "flex-start",
    justifyContent: "space-between",
    gap: 12
  },
  finalMixTitleBlock: {
    flex: 1,
    minWidth: 0
  },
  finalMixEyebrow: {
    color: colors.blue,
    fontSize: 11,
    fontWeight: "500",
    marginBottom: 4
  },
  finalMixTitle: {
    color: colors.ink,
    fontSize: 22,
    lineHeight: 27,
    fontFamily: systemFont,
    fontWeight: "700"
  },
  finalMixMeta: {
    marginTop: 5,
    color: colors.muted,
    fontSize: 12,
    fontWeight: "500"
  },
  mp3Timeline: {
    marginTop: 12,
    paddingHorizontal: 4
  },
  mp3TimelineHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    marginBottom: 7
  },
  mp3TimeText: {
    color: colors.muted,
    fontSize: 11,
    fontWeight: "500"
  },
  mp3Track: {
    height: 5,
    borderRadius: 999,
    overflow: "hidden",
    backgroundColor: "rgba(255,255,255,0.12)"
  },
  mp3Fill: {
    height: "100%",
    borderRadius: 999,
    backgroundColor: colors.blue
  },
  finalMixMetaRow: {
    marginTop: 14,
    flexDirection: "row",
    gap: 8
  },
  miniInfo: {
    flex: 1,
    minHeight: 50,
    borderRadius: 16,
    paddingHorizontal: 10,
    paddingVertical: 8,
    justifyContent: "center",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.08)",
    backgroundColor: "rgba(255,255,255,0.045)"
  },
  miniInfoLabel: {
    color: colors.muted,
    fontSize: 10,
    fontWeight: "500"
  },
  miniInfoValue: {
    marginTop: 3,
    color: colors.ink,
    fontSize: 11,
    fontWeight: "600"
  },
  resultActionRow: {
    marginTop: 12,
    flexDirection: "row",
    gap: 10
  },
  resultAction: {
    flex: 1,
    minHeight: 70,
    borderRadius: 22,
    alignItems: "center",
    justifyContent: "center",
    gap: 7,
    borderWidth: 1,
    borderColor: "rgba(198,170,106,0.17)",
    backgroundColor: "rgba(255,255,255,0.045)"
  },
  resultActionText: {
    color: colors.ink,
    fontSize: 12,
    fontWeight: "600"
  },
  resultFooterRow: {
    flexDirection: "row",
    gap: 8,
    marginTop: 12
  },
  summaryGrid: {
    marginTop: 12,
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 10
  },
  metricCard: {
    flex: 1,
    minWidth: "46%",
    minHeight: 78,
    borderRadius: 24,
    padding: 14,
    backgroundColor: "rgba(255,255,255,0.055)"
  },
  metricValue: {
    marginTop: 8,
    color: colors.ink,
    fontSize: 18,
    fontWeight: "600"
  },
  recordModule: {
    alignItems: "center",
    marginVertical: 16
  },
  recordShell: {
    width: 146,
    height: 146,
    borderRadius: 73,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.06)",
    backgroundColor: "rgba(255,255,255,0.02)"
  },
  recordShellActive: {
    borderColor: "rgba(255,111,145,0.18)",
    backgroundColor: "rgba(255,111,145,0.03)"
  },
  recordRing: {
    width: 114,
    height: 114,
    borderRadius: 57,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "rgba(17,17,20,0.98)",
    borderWidth: 8,
    borderColor: "rgba(198,170,106,0.2)"
  },
  recordRingActive: {
    borderColor: "rgba(255,111,145,0.45)",
    shadowColor: colors.pink,
    shadowOpacity: 0.32,
    shadowRadius: 18
  },
  recordInner: {
    width: 82,
    height: 82,
    borderRadius: 41,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "rgba(28,28,34,0.96)",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.08)"
  },
  recordInnerActive: {
    backgroundColor: "rgba(36,23,28,0.96)"
  },
  recordDot: {
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: colors.pink
  },
  recordDotActive: {
    width: 26,
    height: 26,
    borderRadius: 7
  },
  recordDotReady: {
    backgroundColor: colors.blue
  },
  recordCaptionRow: {
    marginTop: 12,
    flexDirection: "row",
    alignItems: "center",
    gap: 10
  },
  recordStatePill: {
    minHeight: 28,
    borderRadius: 999,
    paddingHorizontal: 12,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.08)",
    backgroundColor: "rgba(255,255,255,0.04)"
  },
  recordStatePillActive: {
    borderColor: "rgba(255,111,145,0.34)",
    backgroundColor: "rgba(255,111,145,0.12)"
  },
  recordStateText: {
    color: colors.ink,
    fontSize: 11,
    fontWeight: "600"
  },
  recordStateTextActive: {
    color: colors.pink
  },
  recordCaption: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: "500"
  },
  recordActionHint: {
    marginTop: 8,
    color: colors.muted,
    fontSize: 11,
    fontWeight: "500"
  },
  capturePanel: {
    marginTop: 14,
    padding: 16,
    borderRadius: 30,
    borderWidth: 1,
    borderColor: "rgba(198,170,106,0.18)",
    backgroundColor: "rgba(16,16,18,0.96)"
  },
  captureHeader: {
    flexDirection: "row",
    alignItems: "flex-start",
    justifyContent: "space-between",
    gap: 12,
    paddingTop: 2
  },
  captureCopy: {
    flex: 1,
    minWidth: 0
  },
  captureTitle: {
    color: colors.ink,
    fontSize: 17,
    lineHeight: 22,
    fontFamily: systemFont,
    fontWeight: "600",
    marginBottom: 2
  },
  liveWaveFrame: {
    marginTop: 16,
    minHeight: 118,
    borderRadius: 26,
    overflow: "hidden",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.08)",
    backgroundColor: "rgba(255,255,255,0.035)"
  },
  liveWaveBaseline: {
    position: "absolute",
    left: 14,
    right: 14,
    top: "50%",
    height: 1,
    backgroundColor: "rgba(255,255,255,0.08)"
  },
  liveWave: {
    minHeight: 118,
    paddingHorizontal: 12,
    paddingVertical: 16,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 2
  },
  liveWaveBar: {
    width: 4,
    borderRadius: 999
  },
  levelRow: {
    marginTop: 14,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between"
  },
  levelLabel: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: "600"
  },
  levelGood: {
    color: colors.blue
  },
  levelPeak: {
    color: colors.pink
  },
  levelNoInput: {
    color: colors.danger
  },
  levelTrack: {
    marginTop: 8,
    height: 10,
    borderRadius: 999,
    overflow: "hidden",
    backgroundColor: "rgba(255,255,255,0.07)"
  },
  levelFill: {
    height: "100%",
    borderRadius: 999,
    backgroundColor: colors.blue
  },
  levelFillPeak: {
    backgroundColor: colors.pink
  },
  durationCard: {
    padding: 16,
    borderRadius: 28,
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: colors.panel
  },
  durationValue: {
    color: colors.ink,
    fontSize: 28,
    fontFamily: systemFont,
    fontWeight: "600",
    marginTop: 4
  },
  durationTrack: {
    marginTop: 16,
    height: 14,
    borderRadius: 999,
    backgroundColor: "rgba(255,255,255,0.08)",
    overflow: "hidden"
  },
  durationFill: {
    height: "100%",
    borderRadius: 999,
    backgroundColor: colors.pink
  },
  durationTicks: {
    marginTop: 8,
    flexDirection: "row",
    justifyContent: "space-between"
  },
  tickText: {
    color: colors.muted,
    fontSize: 10,
    fontWeight: "500"
  },
  processingScreen: {
    minHeight: 650,
    paddingBottom: 8,
    alignItems: "stretch"
  },
  processingHeader: {
    paddingTop: 0,
    paddingBottom: 0
  },
  processingSigilSystem: {
    height: 286,
    marginTop: 8,
    alignItems: "center",
    justifyContent: "center",
    overflow: "hidden"
  },
  processingGlassCard: {
    marginTop: 14,
    marginHorizontal: 2,
    paddingVertical: 13,
    paddingHorizontal: 14,
    borderRadius: 18,
    borderWidth: 1,
    borderColor: "rgba(209,209,214,0.16)",
    backgroundColor: "rgba(21,21,22,0.68)",
    shadowColor: "#000",
    shadowOpacity: 0.24,
    shadowRadius: 18,
    shadowOffset: { width: 0, height: 12 }
  },
  processingStatusRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12
  },
  processingStageTitle: {
    color: colors.ink,
    fontSize: 15,
    letterSpacing: 0.1,
    fontFamily: systemFont,
    fontWeight: "700"
  },
  processingPercent: {
    color: "rgba(198,170,106,0.88)",
    fontSize: 12,
    letterSpacing: 0.2,
    fontFamily: systemFont,
    fontWeight: "700"
  },
  processingStageText: {
    marginTop: 5,
    color: colors.muted,
    fontSize: 11,
    lineHeight: 15,
    fontFamily: systemFont,
    fontWeight: "500"
  },
  processingProgressTrack: {
    marginTop: 12,
    height: 2,
    borderRadius: 2,
    overflow: "hidden",
    backgroundColor: "rgba(209,209,214,0.1)"
  },
  processingProgressFill: {
    height: 2,
    borderRadius: 2,
    backgroundColor: "rgba(198,170,106,0.78)"
  },
  processingConsoleBars: {
    width: 126,
    height: 34,
    marginTop: -4,
    alignSelf: "center",
    flexDirection: "row",
    alignItems: "flex-end",
    justifyContent: "center",
    gap: 2
  },
  processingConsoleBar: {
    width: 3,
    borderRadius: 2
  },
  processingStageStack: {
    marginTop: 10,
    marginHorizontal: 2,
    paddingVertical: 7,
    paddingHorizontal: 10,
    borderRadius: 18,
    borderWidth: 1,
    borderColor: "rgba(209,209,214,0.12)",
    backgroundColor: "rgba(21,21,22,0.46)",
    overflow: "hidden"
  },
  processingRetryActions: {
    marginTop: 14,
    gap: 12
  },
  inlineActions: {
    flexDirection: "row",
    gap: 10
  },
  processingStackRow: {
    minHeight: 30,
    flexDirection: "row",
    alignItems: "center",
    gap: 9,
    borderRadius: 12,
    paddingHorizontal: 8
  },
  processingStackRowActive: {
    backgroundColor: "rgba(198,170,106,0.055)"
  },
  processingStackIndicator: {
    width: 5,
    height: 5,
    borderRadius: 3,
    backgroundColor: "rgba(209,209,214,0.18)"
  },
  processingStackIndicatorDone: {
    backgroundColor: "rgba(209,209,214,0.42)"
  },
  processingStackIndicatorActive: {
    width: 6,
    height: 18,
    borderRadius: 6,
    backgroundColor: "rgba(198,170,106,0.78)"
  },
  processingStackText: {
    flex: 1,
    color: "rgba(161,161,166,0.72)",
    fontSize: 11,
    letterSpacing: 0.15,
    fontFamily: systemFont,
    fontWeight: "600"
  },
  processingStackTextDone: {
    color: "rgba(209,209,214,0.52)"
  },
  processingStackTextActive: {
    color: colors.ink
  },
  processingStackStatusSlot: {
    width: 24,
    alignItems: "flex-end"
  },
  processingStackMiniLine: {
    width: 12,
    height: 1,
    borderRadius: 1,
    backgroundColor: "rgba(209,209,214,0.1)"
  },
  processingStackMiniLineDone: {
    backgroundColor: "rgba(209,209,214,0.26)"
  },
  processingStackPulse: {
    width: 16,
    height: 2,
    borderRadius: 2,
    backgroundColor: "rgba(198,170,106,0.72)"
  },
  auraWave: {
    marginTop: 12,
    minHeight: 112,
    borderRadius: 28,
    overflow: "hidden",
    backgroundColor: "#111127",
    borderWidth: 1,
    borderColor: colors.line,
    shadowOpacity: 0.32,
    shadowRadius: 22
  },
  auraWaveActive: {
    borderColor: "rgba(255,111,145,0.32)",
    backgroundColor: "#15122d"
  },
  genreGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 10
  },
  genreTile: {
    width: "48%",
    minHeight: 92,
    padding: 12,
    borderRadius: tapRadius,
    borderWidth: 1,
    justifyContent: "space-between"
  },
  genreTitle: {
    color: colors.ink,
    fontSize: 13,
    fontFamily: systemFont,
    fontWeight: "600"
  },
  genreWave: {
    width: "100%",
    height: 34
  },
  waveLegend: {
    marginTop: 12,
    flexDirection: "row",
    justifyContent: "space-between",
    gap: 12
  },
  legendDot: {
    width: 8,
    height: 8,
    borderRadius: 4
  },
  stageRow: {
    minHeight: 56,
    borderBottomWidth: 1,
    borderBottomColor: colors.line,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between"
  },
  stageText: {
    color: colors.ink,
    fontSize: 13,
    fontWeight: "500"
  },
  stepIcon: {
    width: 26,
    height: 26,
    borderRadius: 13,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "rgba(198,170,106,0.16)"
  },
  stepDone: {
    backgroundColor: colors.blue
  },
  stepPending: {
    backgroundColor: "rgba(255,255,255,0.07)"
  },
  stepIconText: {
    color: colors.ink,
    fontSize: 13,
    fontWeight: "500"
  },
  trackItem: {
    marginTop: 10,
    borderRadius: 24,
    borderWidth: 1,
    borderColor: "rgba(198,170,106,0.13)",
    backgroundColor: "rgba(255,255,255,0.045)",
    overflow: "hidden"
  },
  trackRow: {
    minHeight: 76,
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    padding: 12
  },
  libraryTrackIcon: {
    width: 46,
    height: 46,
    borderRadius: 23,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1,
    borderColor: "rgba(198,170,106,0.2)",
    backgroundColor: "rgba(198,170,106,0.08)"
  },
  trackTextBlock: {
    flex: 1,
    minWidth: 0
  },
  trackTrailing: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8
  },
  trackTitle: {
    color: colors.ink,
    fontSize: 15,
    fontFamily: systemFont,
    fontWeight: "600"
  },
  moreButton: {
    width: 38,
    height: 38,
    borderRadius: 19,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1,
    borderColor: "rgba(198,170,106,0.22)",
    backgroundColor: "transparent"
  },
  trackActions: {
    flexDirection: "row",
    gap: 8,
    paddingHorizontal: 12,
    paddingBottom: 12,
    flexWrap: "wrap"
  },
  trackActionButton: {
    minHeight: 40,
    borderRadius: tapRadius,
    paddingHorizontal: 14,
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.1)",
    backgroundColor: "rgba(209,209,214,0.075)"
  },
  trackActionDestructive: {
    borderColor: "rgba(255,111,145,0.24)",
    backgroundColor: "rgba(255,111,145,0.08)"
  },
  trackActionText: {
    color: colors.ink,
    fontSize: 12,
    fontFamily: systemFont,
    fontWeight: "500"
  },
  trackActionTextDestructive: {
    color: colors.pink
  },
  chip: {
    minHeight: 30,
    borderRadius: 999,
    paddingHorizontal: 12,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.06)"
  },
  chipText: {
    color: colors.ink,
    fontSize: 12,
    fontWeight: "600"
  },
  chipSaved: {
    backgroundColor: "rgba(48,209,88,0.13)"
  },
  chipTemporary: {
    backgroundColor: "rgba(255,214,10,0.12)"
  },
  chipRetry: {
    backgroundColor: "rgba(255,111,145,0.13)"
  },
  chipPrivate: {
    backgroundColor: "rgba(198,170,106,0.13)"
  },
  privacyAction: {
    minHeight: 50,
    marginTop: 10,
    paddingHorizontal: 12,
    borderRadius: tapRadius,
    backgroundColor: "rgba(209,209,214,0.075)",
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    gap: 12
  },
  disabledPanel: {
    opacity: 0.68
  },
  profileHero: {
    flexDirection: "row",
    alignItems: "center",
    gap: 14,
    marginBottom: 12
  },
  avatarButton: {
    width: 78,
    height: 78,
    borderRadius: 39,
    alignItems: "center",
    justifyContent: "center",
    overflow: "hidden",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.18)",
    backgroundColor: "rgba(198,170,106,0.18)"
  },
  avatarEditButton: {
    width: 34,
    height: 34,
    marginLeft: -26,
    marginTop: 42,
    borderRadius: 17,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1,
    borderColor: "rgba(198,170,106,0.36)",
    backgroundColor: "rgba(0,0,0,0.72)"
  },
  avatarImage: {
    width: "100%",
    height: "100%"
  },
  avatarInitials: {
    color: colors.ink,
    fontSize: 24,
    fontWeight: "600"
  },
  profileHeroCopy: {
    flex: 1
  },
  privacyLabel: {
    color: colors.ink,
    fontSize: 12,
    fontFamily: systemFont,
    fontWeight: "500"
  },
  inlineLabel: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8
  },
  settingValue: {
    marginTop: 2,
    color: colors.muted,
    fontSize: 11,
    fontWeight: "500"
  },
  fileOptionRow: {
    marginTop: 14,
    flexDirection: "row",
    gap: 8
  },
  fileOption: {
    flex: 1,
    minHeight: 38,
    borderRadius: tapRadius,
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.1)",
    backgroundColor: "rgba(255,255,255,0.045)",
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 8
  },
  fileOptionActive: {
    borderColor: "rgba(198,170,106,0.4)",
    backgroundColor: "rgba(198,170,106,0.18)"
  },
  fileOptionText: {
    color: colors.muted,
    fontSize: 11,
    fontWeight: "500",
    textAlign: "center"
  },
  fileOptionTextActive: {
    color: colors.ink
  },
  filePreview: {
    marginTop: 12,
    color: colors.ink,
    fontSize: 13,
    fontFamily: systemFont,
    fontWeight: "500"
  },
  namePrompt: {
    marginTop: 10,
    color: colors.pink,
    fontSize: 12,
    fontWeight: "500"
  },
  successBubble: {
    width: 76,
    height: 76,
    borderRadius: 38,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: 18,
    backgroundColor: colors.blue,
    shadowColor: colors.blue,
    shadowOpacity: 0.44,
    shadowRadius: 26
  },
  compareGrid: {
    marginTop: 12,
    gap: 12
  },
  comparePane: {
    padding: 12,
    borderRadius: 22,
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.08)",
    backgroundColor: "rgba(255,255,255,0.035)"
  },
  helperNote: {
    marginTop: 10,
    marginBottom: 8,
    color: colors.muted,
    fontSize: 11,
    fontWeight: "500",
    textAlign: "center"
  },
  statusNotice: {
    minHeight: 64,
    marginTop: 12,
    padding: 12,
    borderRadius: tapRadius,
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.08)",
    backgroundColor: "rgba(255,255,255,0.035)",
    flexDirection: "row",
    alignItems: "center",
    gap: 10
  },
  toast: {
    position: "absolute",
    left: 34,
    right: 34,
    maxWidth: 330,
    alignSelf: "center",
    minHeight: 42,
    paddingHorizontal: 14,
    borderRadius: 21,
    borderWidth: 1,
    borderColor: "rgba(198,170,106,0.24)",
    backgroundColor: "rgba(0,0,0,0.96)",
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
    shadowColor: "#000",
    shadowOpacity: 0.28,
    shadowRadius: 18
  },
  toastAboveTabs: {
    bottom: 104
  },
  toastLow: {
    bottom: 18
  },
  toastText: {
    color: colors.ink,
    fontSize: 13,
    fontFamily: systemFont,
    fontWeight: "500"
  },
  noticeCopy: {
    flex: 1
  },
  integrationGrid: {
    marginTop: 14,
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8
  },
  integrationPill: {
    borderRadius: tapRadius,
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.1)",
    backgroundColor: "rgba(255,255,255,0.045)",
    paddingHorizontal: 11,
    paddingVertical: 8
  },
  integrationText: {
    color: colors.ink,
    fontSize: 11,
    fontWeight: "500"
  },
  switchTrack: {
    width: 46,
    height: 28,
    borderRadius: 999,
    padding: 3,
    backgroundColor: "rgba(255,255,255,0.12)"
  },
  switchTrackOn: {
    backgroundColor: colors.blue
  },
  switchThumb: {
    width: 22,
    height: 22,
    borderRadius: 11,
    backgroundColor: colors.ink
  },
  switchThumbOn: {
    transform: [{ translateX: 18 }]
  },
  primaryButton: {
    minHeight: 50,
    marginTop: 16,
    borderRadius: tapRadius,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1,
    borderColor: "rgba(209,209,214,0.22)",
    backgroundColor: "rgba(209,209,214,0.12)"
  },
  goldenButton: {
    borderColor: "rgba(198,170,106,0.58)",
    backgroundColor: "rgba(198,170,106,0.24)"
  },
  touchPressedBlue: {
    borderColor: "rgba(198,170,106,0.72)",
    backgroundColor: "rgba(198,170,106,0.26)"
  },
  buttonDisabled: {
    borderColor: "rgba(255,255,255,0.09)",
    backgroundColor: "rgba(255,255,255,0.055)",
    shadowOpacity: 0
  },
  primaryButtonText: {
    color: colors.ink,
    fontSize: 13,
    fontFamily: systemFont,
    fontWeight: "600"
  },
  secondaryButton: {
    minHeight: 50,
    marginTop: 12,
    borderRadius: tapRadius,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1,
    borderColor: "rgba(209,209,214,0.18)",
    backgroundColor: "rgba(209,209,214,0.075)"
  },
  secondaryButtonDisabled: {
    opacity: 0.62,
    backgroundColor: "rgba(255,255,255,0.03)"
  },
  secondaryButtonText: {
    color: colors.ink,
    fontSize: 13,
    fontFamily: systemFont,
    fontWeight: "600"
  },
  buttonContent: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
    paddingHorizontal: 10
  },
  disabledText: {
    color: colors.muted
  },
  compactButton: {
    flex: 1,
    minHeight: 48,
    marginTop: 0
  },
  iconBox: {
    alignItems: "center",
    justifyContent: "center"
  },
  buttonRow: {
    flexDirection: "row",
    gap: 12,
    marginTop: 16
  },
  downloadFormatRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12,
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: colors.line
  },
  bigIcon: {
    width: 48,
    height: 48,
    borderRadius: 24,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "transparent",
    marginBottom: 12
  },
  bottomNav: {
    position: "absolute",
    left: 18,
    right: 18,
    bottom: 16,
    minHeight: 74,
    borderRadius: 42,
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.16)",
    backgroundColor: "rgba(28,28,34,0.76)",
    flexDirection: "row",
    padding: 8,
    shadowColor: "#000",
    shadowOpacity: 0.36,
    shadowRadius: 26,
    overflow: "hidden"
  },
  navSlider: {
    position: "absolute",
    top: 8,
    bottom: 8,
    left: 8,
    borderRadius: 34,
    backgroundColor: "rgba(198,170,106,0.24)",
    borderWidth: 1,
    borderColor: "rgba(198,170,106,0.18)"
  },
  navItem: {
    flex: 1,
    minHeight: 58,
    borderRadius: 34,
    alignItems: "center",
    justifyContent: "center",
    gap: 3,
    zIndex: 1
  },
  navActive: {
    backgroundColor: "rgba(198,170,106,0.24)",
    borderWidth: 1,
    borderColor: "rgba(198,170,106,0.18)"
  },
  navText: {
    color: colors.muted,
    fontSize: 12,
    fontFamily: systemFont,
    fontWeight: "500"
  },
  navTextActive: {
    color: colors.blue
  }
});

export default App;



