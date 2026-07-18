# Skarly Phase 6 Integration Notes

## What Is Connected

- Expo upload flow calls `POST /v1/uploads/sign` when the local backend is running.
- Genre generation calls `POST /v1/jobs` with source metadata and selected genre.
- Processing calls `POST /v1/worker/jobs/{job_id}/run` to simulate worker completion, then reads `GET /v1/jobs/{job_id}`.
- Result Player receives a backend mock `final_mp3_url` when available.
- History attempts `GET /v1/history` and falls back to local prototype rows if the backend is offline.
- Profile shows whether the app is using `Local mock` or `Local fallback`.

## What Is Still Mocked

- Firebase Auth is not installed in the app.
- Local audio bytes are not uploaded to backend storage.
- Signed upload/download URLs are mock URLs.
- Cloud Tasks is still represented by the backend in-memory queue.
- AI generation is still represented by the backend mock worker.
- Result playback remains visual only.

## Run Order For Demo

1. Start backend on port `8090`.
2. Start Expo web on port `8082`.
3. Use the app normally.
4. Turn backend off to verify the fallback state.

## Next Backend Step

Replace `app/auth.py`, `app/repository.py`, `app/storage.py`, and `app/tasks.py` with real Firebase/GCP adapters after credentials are available.
