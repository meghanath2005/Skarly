# Skarly local backend

The backend is a FastAPI service for the local guest studio. It stores metadata in SQLite, stores audio under `.local-storage`, runs jobs inline, and exposes local playback/download routes.

## Audio pipeline

1. Validate and decode the uploaded file with FFmpeg.
2. Use Demucs for full-song or music-to-music source separation.
3. Analyse language, timing, melody and signal features with Whisper, Basic Pitch and local analysis code.
4. Ask the separately running ACE-Step API for five backing arrangements.
5. Mix the selected vocal and backing with the Skarly adaptive mixer.
6. Export MP3, WAV, stems, MIDI, chord sheet and Producer Pack files locally.

The backend is a local guest service with SQLite or memory persistence, filesystem storage, and in-process job execution.

## Start

Copy `.env.offline.example` to `.env`, then run the repository helper:

```powershell
powershell -ExecutionPolicy Bypass -File ..\tools\start-local-studio.ps1
```

ACE-Step must be running at `http://127.0.0.1:8001`. Keep `SKARLY_ACE_STEP_DIRECT_ENABLED=false` for five-version generation so the API can keep the model resident in GPU memory.

## Local API identity

The Expo application sends `Authorization: Bearer guest:guest-session`. All project and storage paths are scoped to that local guest session.

## Tests

```powershell
python -m pytest tests
```
