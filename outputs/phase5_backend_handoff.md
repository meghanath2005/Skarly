# Skarly Phase 5 Backend Handoff

## Current Implementation

The Phase 5 backend scaffold lives in `lyricmorph-backend`.

It includes a FastAPI service, local auth shim, in-memory Firestore-style repository, mocked signed storage URLs, in-memory Cloud Tasks queue, and mocked AI worker. This gives the app a real backend contract before Firebase/GCP credentials are available.

## Replace Later

- `app/auth.py`: replace mock bearer parsing with Firebase Admin `verify_id_token`.
- `app/repository.py`: replace `InMemoryJobRepository` with Firestore collections.
- `app/storage.py`: replace mocked URLs with Cloud Storage signed upload/download URLs.
- `app/tasks.py`: replace in-memory queue with Cloud Tasks.
- `app/worker.py`: replace mock generation with Whisper, librosa/basic pitch analysis, MusicGen, and FFmpeg.

## Local Demo Contract

Use this token for a saved creator:

```text
Authorization: Bearer demo-user
```

Use this token for a guest creator:

```text
Authorization: Bearer guest:demo-session
```

The backend does not process real audio yet. `POST /v1/worker/jobs/{job_id}/run` simulates the worker completing the MP3.

## Next Integration Step

Wire the Expo app to this local backend behind a `USE_BACKEND_MOCK` flag:

- Upload screen calls `POST /v1/uploads/sign`.
- Genre generation calls `POST /v1/jobs`.
- Processing polls `GET /v1/jobs/{jobId}`.
- Result uses `final_mp3_url` when ready.
- History calls `GET /v1/history`.
