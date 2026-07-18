# Skarly Backend

Current Skarly V2 acceptance evidence and remaining release gates are tracked in
[`docs/SKARLY_V2_ACCEPTANCE_STATUS.md`](docs/SKARLY_V2_ACCEPTANCE_STATUS.md).

The backend now supports Firebase Auth, Firestore persistence, Google Cloud Storage signed URLs, backend-owned task execution, and an MVP audio worker that can produce a real MP3 with FFmpeg.

## Architecture

Mobile App -> Firebase ID token -> FastAPI API -> Firestore job metadata -> task runner -> Audio Worker -> Cloud Storage final MP3 -> App result player

Local automated tests use isolated in-memory adapters. Real saved-user mode uses Firebase Auth, Firestore, GCS, `SKARLY_TASK_BACKEND=inline`, and the `mvp_audio` worker. Cloud deployment can switch task execution to `SKARLY_TASK_BACKEND=cloud_tasks`.

## Local Setup

```bat
cd lyricmorph-backend
python -m pip install -r requirements.txt --target .pydeps --upgrade
```

Local `.env` storage settings:

```text
SKARLY_REPOSITORY_BACKEND=firestore
SKARLY_STORAGE_BUCKET=lyricmorph-user
SKARLY_STORAGE_BACKEND=gcs
SKARLY_WORKER_BACKEND=mvp_audio
SKARLY_MUSIC_GENERATOR_BACKEND=ace_step
SKARLY_TASK_BACKEND=inline
SKARLY_FFMPEG_PATH=ffmpeg
SKARLY_STEM_SEPARATOR_BACKEND=demucs
SKARLY_DEMUCS_PATH=<path-to-demucs-venv>\Scripts\python.exe -m demucs.separate
SKARLY_DEMUCS_MODEL=htdemucs_ft
SKARLY_DEMUCS_TWO_STEMS=vocals
SKARLY_DEMUCS_DEVICE=cuda
SKARLY_SEPARATION_TIMEOUT_SEC=1200
SKARLY_ACE_STEP_BASE_URL=http://127.0.0.1:8001
SKARLY_ACE_STEP_TIMEOUT_SECONDS=1800
SKARLY_ACE_STEP_DOWNLOAD_TIMEOUT_SECONDS=1800
SKARLY_ACE_STEP_INFER_STEP=20
SKARLY_ACE_STEP_GUIDANCE_SCALE=15
SKARLY_ACE_STEP_MAX_DURATION_SECONDS=60
SKARLY_ACE_STEP_USE_SOURCE_AUDIO=false
SKARLY_ACE_STEP_SOURCE_AUDIO_STRENGTH=0.35
SKARLY_ACE_STEP_FALLBACK_TO_PROCEDURAL=false
SKARLY_ACE_STEP_DIRECT_ENABLED=false
SKARLY_BACKING_VOCAL_CLEANUP_ENABLED=true
SKARLY_BACKING_MIX_GAIN=0.06
SKARLY_WHISPER_PATH=D:\intern\skarly-ai-repos\_envs\whisper\Scripts\whisper.exe
SKARLY_WHISPER_MODEL=base
SKARLY_WHISPER_TIMEOUT_SEC=300
SKARLY_CORS_ORIGINS=https://your-frontend-domain
FIREBASE_CREDENTIALS_PATH=C:\Users\yeshw\Documents\Codex\firebase\lyricmorph-service-account.json
```

The `lyricmorph-user` bucket has CORS enabled for local Expo web uploads from `http://localhost:8082` and `http://127.0.0.1:8082`.

You can also use the included launcher:

```bat
C:\Users\yeshw\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe dev_server.py
```

For local app development, sign in through the Expo frontend. Saved creator API calls use Firebase ID tokens, and guest calls use the scoped guest token created by the app.

## ACE-Step API

The local RTX 5070 validation using ACE-Step's repository-owned profiler is
recorded in [`docs/RTX5070_ACE_STEP_PROFILE.md`](docs/RTX5070_ACE_STEP_PROFILE.md).

ACE-Step is not bundled into this backend. Start it in a separate Command Prompt window before real AI generation:

```bat
cd C:\Users\yeshw\Documents\Codex\ai-models\ACE-Step-1.5
start_api_server.bat
```

Expected output:

```text
Uvicorn running on http://127.0.0.1:8001
```

Do not use `python app.py` for the current local ACE-Step checkout. This installation provides `start_api_server.bat`, already configured for the same URL used by `SKARLY_ACE_STEP_BASE_URL`.

Keep `SKARLY_ACE_STEP_DIRECT_ENABLED=false` for normal five-version work. The API keeps the model resident in GPU memory, avoiding a model reload for every backing version. Direct mode is a recovery path only.

## Hindi language detection

Skarly uses Whisper locally to detect the vocal language and extract a short lyric preview before the creator confirms the detected language and mood. The local tool lives at:

```text
D:\intern\skarly-ai-repos\_envs\whisper\Scripts\whisper.exe
```

Full-song generation is fail-closed: Demucs must produce validated `vocals` and `no_vocals` stems, and the vocal stem must pass the pre-mix leakage gate. Skarly never substitutes the mixed source or a center-channel estimate when separation fails.

For an RTX 50-series GPU on Windows, install a PyTorch CUDA build that includes the GPU architecture in the dedicated Demucs environment, then verify it before starting the backend:

```powershell
<path-to-demucs-venv>\Scripts\python.exe -m pip install --upgrade torch==2.7.1 torchaudio==2.7.1 --index-url https://download.pytorch.org/whl/cu128
<path-to-demucs-venv>\Scripts\python.exe -c "import torch; print(torch.__version__, torch.cuda.get_device_name(0), torch.cuda.get_arch_list())"
```

`SKARLY_ACE_STEP_USE_SOURCE_AUDIO=false` keeps vocal-to-music generation on the
established prompt-conditioned path. Music-to-new-music jobs always send their
normalized music reference to ACE-Step with `task_type=cover`; the strength is
controlled by `SKARLY_ACE_STEP_SOURCE_AUDIO_STRENGTH` (recommended `0.25`-`0.45`).

Set `SKARLY_WHISPER_PATH` to that executable in your local `.env`. No paid transcription API key is required. The first run downloads the selected Whisper model; `base` is the default. In production, run Whisper on the same GPU worker as ACE-Step or point `SKARLY_WHISPER_PATH` at a compatible worker command for faster processing.

## Implemented API Contract

- `GET /health`
- `POST /v1/uploads/sign`
- `POST /v1/jobs`
- `GET /v1/jobs/{job_id}`
- `GET /v1/history`
- `POST /v1/jobs/{job_id}/retry`
- `DELETE /v1/tracks/{track_id}`
- `POST /v1/privacy/delete-raw/{job_id}`
- `POST /v1/worker/jobs/{job_id}/run` for worker/task execution only

Skarly V2 also exposes `/api/v2/analyse`, `/api/v2/generations`,
`/api/v2/generations/regenerate`, `/api/v2/generations/regenerate-section`,
`/api/v2/mixes`, `/api/v2/exports`, and `/api/v2/feedback`. Section
regeneration uses ACE-Step repainting on the instrumental only, restores the
original decoded samples outside the selected range, and remixes the same
source vocal afterward.

## Frontend Screen Mapping

| Frontend screen | Future backend endpoint |
| --- | --- |
| Login / Signup | Firebase Auth SDK, then `Authorization: Bearer <id_token>` |
| Upload Audio | `POST /v1/uploads/sign` |
| Choose Genre / Generate | `POST /v1/jobs` |
| Processing | `GET /v1/jobs/{job_id}` |
| Result Player | `GET /v1/jobs/{job_id}` final MP3 URL |
| Download / Share | Signed `final_mp3_url` |
| History | `GET /v1/history` |
| Retry failed job | `POST /v1/jobs/{job_id}/retry` |
| Privacy delete raw | `POST /v1/privacy/delete-raw/{job_id}` |

## Smoke Test Examples

```powershell
curl http://localhost:8090/health
```

```powershell
curl -X POST http://localhost:8090/v1/uploads/sign `
  -H "Authorization: Bearer <firebase-id-token>" `
  -H "Content-Type: application/json" `
  -d "{\"filename\":\"voice_take_01.mp3\",\"content_type\":\"audio/mpeg\",\"size_bytes\":2500000,\"source_type\":\"localUpload\"}"
```

```powershell
curl -X POST http://localhost:8090/v1/jobs `
  -H "Authorization: Bearer <firebase-id-token>" `
  -H "Content-Type: application/json" `
  -d "{\"raw_audio_path\":\"users/saved/<creator>/raw/<upload_id>/voice.mp3\",\"genre\":\"Lo-fi\",\"track_name\":\"Ocean Demo\",\"source_type\":\"localUpload\",\"delete_raw_after_mix\":true}"
```

```powershell
curl -X POST http://localhost:8090/v1/worker/jobs/<job_id>/run
```

Normal local app flow does not need that worker curl. `POST /v1/jobs` schedules the worker automatically when `SKARLY_TASK_BACKEND=inline`.

## Current Boundary

- Auth supports Firebase Admin verification plus scoped guest sessions in `app/auth.py`.
- Storage supports Google Cloud Storage signed URLs in real local mode; automated tests use an isolated in-memory adapter.
- Repository mode supports in-memory tests and Firestore saved profile/job/history persistence in `app/repository.py`.
- Task execution is controlled by `SKARLY_TASK_BACKEND`: `inline` runs the worker automatically after job creation for local testing, and `cloud_tasks` dispatches an authenticated HTTP task to the worker endpoint.
- Worker mode is configured as `SKARLY_WORKER_BACKEND=mvp_audio` for real local testing.
- Music generation mode is configured by `SKARLY_MUSIC_GENERATOR_BACKEND`.
- Local real-generation mode uses ACE-Step through `SKARLY_MUSIC_GENERATOR_BACKEND=ace_step`.
- `SKARLY_ACE_STEP_USE_SOURCE_AUDIO=false` is intentional for vocal-to-music: Skarly analyzes isolated vocal timing and prompts ACE for a new instrumental. Music-to-new-music is the scoped exception and always uses the uploaded music as an ACE-Step cover reference.

Next step is audio QA: listen to isolated vocal preview, backing-only preview, and final mix for the same upload.

See `outputs/phase13_cloud_run_tasks_plan.md` for the deployment checklist.

## Command Prompt Deployment Helpers

Create or verify the queue:

```bat
deploy_cloud_tasks_queue.cmd
```

Deploy Cloud Run:

```bat
set SKARLY_WORKER_SHARED_SECRET=replace-with-a-long-random-secret
deploy_cloud_run.cmd
```

After deploy, copy the printed Cloud Run URL into `lyricmorph-mobile\.env`:

```text
EXPO_PUBLIC_BACKEND_BASE_URL=https://YOUR-CLOUD-RUN-URL
```
