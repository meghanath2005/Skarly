# Skarly local run guide

Skarly runs as a local guest studio. Metadata is stored in SQLite and audio is stored under `lyricmorph-backend/.local-storage`.

## Start the complete stack

Terminal 1 - ACE-Step API:

```powershell
powershell -ExecutionPolicy Bypass -File tools\start-ace-step-api.ps1
```

Terminal 2 - FastAPI backend:

```powershell
Copy-Item lyricmorph-backend\.env.offline.example lyricmorph-backend\.env
powershell -ExecutionPolicy Bypass -File tools\start-local-studio.ps1
```

Terminal 3 - Expo UI:

```powershell
Copy-Item lyricmorph-mobile\.env.offline.example lyricmorph-mobile\.env
cd lyricmorph-mobile
npm install
npm run web
```

Open `http://localhost:8081` and select **Enter Local Studio**.

## Audio tools

- FFmpeg is required for real decoding, mixing and export.
- Demucs is required for full-song and music-to-music vocal isolation.
- ACE-Step produces the five backing arrangements.
- Whisper and Basic Pitch enrich analysis but have guarded fallbacks.

Keep `SKARLY_ACE_STEP_SEND_LYRICS=false` so ACE-Step generates an instrumental backing for the uploaded vocal.

## Smoke test

With the backend running:

```powershell
powershell -ExecutionPolicy Bypass -File tools\smoke-local-generation.ps1
```

The smoke test output is local and excluded from Git.
