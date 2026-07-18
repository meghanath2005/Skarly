# Skarly Phase Status

## Phase 1: MVP Scope

Status: Complete.

Locked scope: 30-second guest recordings/uploads, 60-second saved creator recordings, one generation at a time, MP3 output, no payments, no remixing, no AI voice cloning, and eight MVP genres.

## Phase 2: UI/UX Direction

Status: Complete.

Direction: Apple-oriented dark Health-style interface, waveform-led creation flow, clean controls, simple creator identity, and clear prototype language.

## Phase 3: Mobile Frontend Prototype

Status: Complete.

Implemented in `lyricmorph-mobile`. The Expo app includes the full flow from splash/login/setup through record/upload, genre, processing, naming, result, download/share, history, and profile.

## Phase 4: Demo Hardening

Status: Complete.

Added real local file picker metadata handling, clearer record/upload states, action feedback, scroll-aware bottom nav, profile reset, and prototype QA notes.

## Phase 5: Backend Scaffold

Status: Historical scaffold complete.

Implemented in `lyricmorph-backend` as the original FastAPI contract. This phase is now historical; later phases replaced the scaffold paths with Firebase Auth, Firestore, GCS signed URLs, and the MVP audio worker.

## Phase 6: Local Backend Mock Integration

Status: Historical integration complete.

The Expo app can call FastAPI for upload signing, job creation, worker execution, result URL readiness, and history loading. Current generation stops with a retry/error state when FastAPI is offline.

## Phase 7: Account Foundation

Status: Firebase Auth foundation complete.

Implemented so far:

- Firebase Auth sign up/sign in/logout/session restore.
- Duplicate email blocking through Firebase Auth and backend profile checks.
- Guest Profile email entry routes to sign up instead of silently converting accounts.
- Logout / switch account action in Profile.
- Profile details sync through `/v1/me` for saved creators.
- Backend duplicate email conflict response for profile saves.
- Backend Firebase Admin ID token verification.
- Backend `AUTH_MODE=firebase_with_guest` for saved users plus scoped guest sessions.
- Frontend Firebase Auth SDK integration.
- Real sign up, sign in, logout, and session restore when Firebase web config is present.
- Saved creator backend calls now send Firebase ID tokens instead of the old `demo-user` token.
- Guest Creator mode uses a scoped guest session token and remains temporary.

Later account work:

- Cloud Storage-backed profile images.
- Optional stricter Firebase-only backend mode for production deployment.

## Phase 8: Google Cloud Storage

Status: Complete for signed upload/download plumbing.

Implemented so far:

- Google Cloud Storage bucket created: `lyricmorph-user`.
- Bucket location: `us-central1`.
- Uniform access and public access prevention are enabled.
- Backend environment points to `SKARLY_STORAGE_BACKEND=gcs`.
- Backend storage adapter can generate signed upload/download URLs with the Firebase service account.
- Cloud Storage bucket CORS allows local Expo web uploads.
- Frontend local audio picker uploads selected file bytes to the signed Cloud Storage URL before genre selection.

Real final MP3 object creation is handled by Phase 11.

## Phase 9: Firestore Persistence

Status: Complete.

Implemented so far:

- Backend can use `SKARLY_REPOSITORY_BACKEND=memory` or `firestore`.
- Firestore mode stores saved creator profiles in `users/{uid}`.
- Firestore mode stores job/history metadata in `users/{uid}/jobs/{jobId}`.
- Duplicate profile emails are protected through `profile_emails/{normalized_email}`.
- Existing API responses remain compatible with the Expo app.
- Saved profile load/save now syncs through `/v1/me`.
- Named generated tracks and library status changes update backend history.

Voice-take metadata persistence is now handled through Firestore for saved creators.

## Phase 10: Real Recording Input

Status: Complete.

Implemented so far:

- Expo app can capture real microphone recordings as local voice takes.
- Web preview uses the browser `MediaRecorder` API when available.
- Native Expo builds use Expo audio recording APIs.
- Guest recording limit remains 30 seconds.
- Saved creator recording limit remains 60 seconds.
- Saved voice takes keep local URI, duration, content type, and size metadata when available.
- Saved voice takes can be played back before conversion.
- Track Library separates voice recordings from generated tracks.
- Voice recordings show local vs cloud-uploaded status.
- Voice recordings can be uploaded/retried from Track Library.
- Using a recorded take for conversion uploads the audio bytes through the backend signed Cloud Storage URL before genre selection when the backend is running.
- If backend upload fails, the app keeps the local voice take and shows a retry/error state.

Moved to later phases:

- Cloud Tasks worker execution.
- Full AI generation from uploaded raw audio.

## Phase 11: MVP Audio Worker

Status: Complete.

Implemented so far:

- Backend worker mode uses `SKARLY_WORKER_BACKEND=mvp_audio` for real local testing.
- Storage adapters can download and upload private object bytes.
- MVP worker downloads raw uploaded audio, normalizes it with FFmpeg, creates a simple genre-aware backing bed, mixes a real MP3, uploads it to Cloud Storage-compatible storage, and returns the existing signed result URL.
- Backend genre contract now matches the frontend genre set, including `R&B` and `Hip-hop`.
- Isolated in-memory worker paths remain available for automated tests.

Moved to later phases:

- Cloud Tasks execution.
- Full AI music generation model.
- Advanced melody/key extraction.

## Phase 12: Backend-Owned Task Execution

Status: Complete for local automatic execution; ready for Cloud Tasks deployment configuration.

Implemented so far:

- Backend now owns job execution after `/v1/jobs`.
- Local development uses `SKARLY_TASK_BACKEND=inline`, which schedules the MVP audio worker automatically after job creation.
- Frontend processing no longer calls `/v1/worker/jobs/{jobId}/run` directly.
- Frontend processing now polls `GET /v1/jobs/{jobId}` until the job is `ready` or `failed`.
- Worker route can require `X-Skarly-Worker-Secret` when configured for deployed task execution.
- Backend supports `SKARLY_TASK_BACKEND=cloud_tasks` with Cloud Tasks dispatch settings for Cloud Run deployment.
- Admin Panel summary now reports the active task backend.

Moved to later phases:

- Creating the real GCP Cloud Tasks queue and Cloud Run deployment.
- Replacing the simple generated backing bed with a real AI music generation service.

## Phase 14: Music Quality Upgrade Foundation

Status: Implemented for the built-in generator.

Implemented so far:

- Added `SKARLY_MUSIC_GENERATOR_BACKEND`.
- Default music generation is now `procedural_v2`.
- The MVP audio worker now creates a layered genre-aware bed instead of the older single-tone backing bed.
- Procedural v2 adds chord movement, bass, lead accents, kick/snare/hat texture, stereo movement, and genre-specific profiles.
- Health/Admin responses expose the active music generator backend.

Moved to later phases:

- Hosted external AI music generation provider.
- Melody/key extraction from the recorded vocal.
- Better vocal-aware arrangement and automatic mix mastering.

## Current Boundaries

- Frontend recording captures real local audio input for voice takes.
- Frontend upload signs metadata with the backend and uploads local file bytes to Cloud Storage for real selected files.
- Firebase Auth is real in the frontend when configured; backend token verification requires Firebase Admin credentials.
- Firestore is available for saved profile/job/history persistence when `SKARLY_REPOSITORY_BACKEND=firestore`.
- Cloud Storage signed URLs are real in backend `gcs` mode; tests use isolated in-memory services.
- Local task execution runs inline after job creation; Cloud Tasks mode is configured but not deployed yet.
- External ACE-Step generation is connected through a separate local API service when `SKARLY_MUSIC_GENERATOR_BACKEND=ace_step`. The procedural generator remains a fallback path for isolated testing.

## Phase 17: Accurate Vocal Isolation + Vocal-Aware Beat Replacement

Status: Implemented in backend/frontend code; real full-mix quality requires backend dependency installation.

Implemented so far:

- Added `SKARLY_STEM_SEPARATOR_BACKEND=demucs` with Demucs path/model settings.
- Installed Demucs into the ACE-Step virtualenv and configured Windows local execution through `python.exe -m demucs.separate`.
- Added backend upload-byte fallback so failed browser signed PUT uploads can still be written to Cloud Storage by FastAPI.
- Uploaded files now run a vocal-isolation stage before backing generation, while direct microphone recordings skip separation.
- Worker uses the isolated vocal stem for ACE/procedural conditioning and final mixing.
- Processing UI now includes `Isolating Vocals` and `Creating Beat`.
- Backing mix gain defaults lower and the final mix uses vocal-first ducking so generated beats sit under vocals.
- Frontend job creation keeps raw audio after generation so `Try another genre` can reuse the same vocal instead of failing with a missing raw file.
- ACE-Step source-audio conditioning is disabled locally for the current replacement-beat flow. Skarly uses isolated-vocal timing analysis and genre-specific prompts, then cleans the generated backing before final mixing.

Pending setup/QA:

- Start ACE-Step with `C:\Users\yeshw\Documents\Codex\ai-models\ACE-Step-1.5\start_api_server.bat`.
- Restart FastAPI so it reloads `SKARLY_DEMUCS_PATH` and the current ACE-Step timing settings.
- Test with an original full mix and confirm the old instrumental is mostly removed while lead/backing vocals remain.
- For best generation quality, keep ACE-Step running before testing so the model is already loaded, then validate isolated vocal, generated backing, and final mix separately.

## Readiness Recommendation

Do not add new UI features before validating the real audio path. The next practical step is installing Demucs, running one full-mix upload through isolation, then testing ACE-Step generation with the isolated vocal stem.
