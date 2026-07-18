# Skarly Project Handoff

This handoff is for a developer joining the Skarly project.

Skarly is a mobile-first Expo app plus a FastAPI backend. It lets a user record or upload audio, choose a genre, isolate vocals from uploaded mixes, generate a backing track, and export a private MP3.

## Repository Layout

- `lyricmorph-mobile/` - Expo React Native frontend.
- `lyricmorph-backend/` - FastAPI backend, Firebase Auth verification, Firestore, Cloud Storage, audio worker.
- `outputs/` - phase notes, design notes, and implementation status.
- `README.md` - current run instructions and boundaries.

The folder names still say `lyricmorph-*` because they are historical local names. The app/product name in UI is Skarly.

## What Is Real Now

- Firebase Auth for saved creator sign up/sign in/logout/session restore.
- Firestore persistence for saved creator profile, jobs, history, and voice-take metadata.
- Google Cloud Storage for private raw audio and final MP3 objects.
- Real browser/local audio upload path.
- Backend upload fallback through `POST /v1/uploads/bytes` when browser signed PUT fails.
- Real microphone recording in the frontend.
- Backend worker with FFmpeg, Demucs vocal isolation, ACE-Step integration, and MP3 output.
- Admin Panel restricted by configured admin email/UID.

## What Is Still In Progress

- ACE-Step quality tuning for better genre-specific accompaniment.
- Stronger vocal/beat alignment.
- Cloud Tasks deployment is configured but not fully deployed.
- Production hosting and domain setup.
- App Store / Play Store packaging.
- Payment/subscription features are intentionally out of scope.

## Do Not Commit

Do not commit these files or folders:

- `lyricmorph-backend/.env`
- `lyricmorph-mobile/.env`
- Firebase service account JSON files
- Google Cloud credentials
- `node_modules/`
- `.pydeps/`
- `.demucsdeps/`
- `.venv/`
- Expo/export build folders
- Logs
- ACE-Step checkpoints/model folders

Use `.env.example` files and this handoff instead.

## Required Accounts And Access

Ask the project owner for:

- GitHub repository access.
- Firebase project access for project `lyricmorph`.
- Google Cloud project access for project `lyricmorph`.
- Cloud Storage bucket access for `lyricmorph-user`.
- Firestore access.
- Admin allowlist email/UID if you need the Admin Panel.

Recommended Google Cloud role for development:

- Firebase Admin viewer/editor as needed.
- Cloud Datastore User for Firestore testing.
- Storage Object Admin for the dev bucket.

Do not share service account JSON in GitHub. Use IAM access where possible.

## Frontend Setup

Install Node.js LTS.

```bat
cd C:\path\to\skarly\lyricmorph-mobile
npm install
```

Create `lyricmorph-mobile/.env`:

```text
EXPO_PUBLIC_FIREBASE_API_KEY=your_web_api_key
EXPO_PUBLIC_FIREBASE_AUTH_DOMAIN=lyricmorph.firebaseapp.com
EXPO_PUBLIC_FIREBASE_PROJECT_ID=lyricmorph
EXPO_PUBLIC_FIREBASE_APP_ID=your_firebase_web_app_id
EXPO_PUBLIC_BACKEND_BASE_URL=http://127.0.0.1:8090
```

Run frontend:

```bat
cd C:\path\to\skarly\lyricmorph-mobile
npm run web
```

## Local Run Order

Run these in three separate Command Prompt windows and keep all three open.

Window 1, ACE-Step API:

```bat
cd C:\Users\yeshw\Documents\Codex\ai-models\ACE-Step-1.5
start_api_server.bat
```

ACE should print:

```text
Uvicorn running on http://127.0.0.1:8001
```

Window 2, Skarly backend:

```bat
cd C:\path\to\skarly\lyricmorph-backend
python dev_server.py
```

Backend should print:

```text
Uvicorn running on http://127.0.0.1:8090
```

Window 3, Skarly frontend:

```bat
cd C:\path\to\skarly\lyricmorph-mobile
npm run web
```

Open the Expo web URL that appears, usually `http://localhost:8081` or `http://localhost:8082`.

## Backend Setup

Install Python 3.12.

```bat
cd C:\path\to\skarly\lyricmorph-backend
python -m pip install -r requirements.txt --target .pydeps --upgrade
```

Create `lyricmorph-backend/.env` from `.env.example`.

Minimum local real-service settings:

```text
AUTH_MODE=firebase_with_guest
FIREBASE_PROJECT_ID=lyricmorph
FIREBASE_CREDENTIALS_PATH=C:\path\to\firebase-service-account.json
SKARLY_REPOSITORY_BACKEND=firestore
SKARLY_STORAGE_BACKEND=gcs
SKARLY_STORAGE_BUCKET=lyricmorph-user
SKARLY_WORKER_BACKEND=mvp_audio
SKARLY_MUSIC_GENERATOR_BACKEND=ace_step
SKARLY_TASK_BACKEND=inline
SKARLY_FFMPEG_PATH=ffmpeg
SKARLY_ACE_STEP_BASE_URL=http://127.0.0.1:8001
SKARLY_ACE_STEP_TIMEOUT_SECONDS=1800
SKARLY_ACE_STEP_DOWNLOAD_TIMEOUT_SECONDS=1800
SKARLY_ACE_STEP_INFER_STEP=20
SKARLY_ACE_STEP_GUIDANCE_SCALE=15
SKARLY_ACE_STEP_MAX_DURATION_SECONDS=60
SKARLY_ACE_STEP_FALLBACK_TO_PROCEDURAL=false
SKARLY_ACE_STEP_USE_SOURCE_AUDIO=false
SKARLY_STEM_SEPARATOR_BACKEND=demucs
SKARLY_DEMUCS_PATH=C:\path\to\ACE-Step-1.5\.venv\Scripts\python.exe -m demucs.separate
SKARLY_DEMUCS_MODEL=htdemucs_ft
SKARLY_DEMUCS_TWO_STEMS=vocals
SKARLY_BACKING_VOCAL_CLEANUP_ENABLED=true
SKARLY_VOCAL_CLEANUP_ENABLED=true
SKARLY_BACKING_MIX_GAIN=0.06
```

Run backend:

```bat
cd C:\path\to\skarly\lyricmorph-backend
python dev_server.py
```

Health check:

```bat
curl http://127.0.0.1:8090/health
```

## ACE-Step And Demucs

ACE-Step is not part of this repo. Install/run it separately.

The current local setup uses:

```text
C:\Users\yeshw\Documents\Codex\ai-models\ACE-Step-1.5
```

Run the local ACE-Step API with:

```bat
cd C:\Users\yeshw\Documents\Codex\ai-models\ACE-Step-1.5
start_api_server.bat
```

Do not use `python app.py`; this local ACE-Step checkout uses its own `start_api_server.bat` launcher. The launcher is already configured for `127.0.0.1:8001`, which matches `SKARLY_ACE_STEP_BASE_URL`.

Demucs was installed into the ACE-Step virtualenv and is called by the backend through:

```text
C:\path\to\ACE-Step-1.5\.venv\Scripts\python.exe -m demucs.separate
```

Verify Demucs:

```bat
C:\path\to\ACE-Step-1.5\.venv\Scripts\python.exe -m demucs.separate --help
```

## Test Commands

Frontend:

```bat
cd C:\path\to\skarly\lyricmorph-mobile
npm run typecheck
npx expo export --platform web --output-dir dist-test-review
```

Backend:

```bat
cd C:\path\to\skarly\lyricmorph-backend
set PYTHONPATH=.pydeps
python -m pytest
```

## Manual QA Checklist

- Guest can enter without email/password.
- Saved user can sign up, log out, sign back in.
- Duplicate email is blocked by Firebase.
- Saved session restores after refresh.
- Guest data is temporary.
- Saved data persists from Firestore.
- Recording permission prompt works.
- Guest recording limit is 30 seconds.
- Saved recording limit is 60 seconds.
- Upload accepts `.mp3`, `.wav`, `.m4a`.
- Weird file types are rejected.
- Upload reaches Cloud Storage.
- Full-mix upload runs vocal isolation.
- Processing reaches ready instead of hanging.
- Result can play generated MP3.
- Download saves an MP3 with the user-entered track name.
- Track Library separates Voice Recordings and Generated Tracks.
- Delete sends items to Recycle Bin.
- Restore and permanent delete work.
- Admin Panel is visible only to allowed admin account.

## Current Known Risk

Generation quality depends heavily on Demucs and ACE-Step. If the old beat is still audible, debug by listening to:

- isolated vocal preview,
- backing-only preview,
- final mix.

If isolated vocal still contains too much old beat, tune Demucs/model settings first. If backing-only has vocals or wrong style, tune ACE-Step prompt/settings next.
