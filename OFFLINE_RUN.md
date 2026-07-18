# Skarly Offline Run Guide

This mode runs Skarly as a local studio:

- no Firebase required for guest mode
- no Firestore
- no Google Cloud Storage
- no ACE-Step server
- no Demucs vocal isolation
- local files are stored under `lyricmorph-backend/.local-storage`
- backend data is in memory and resets when the backend restarts

## Fastest Path: Python Studio

This is the recommended prototype path because it does not require Node or Expo.

```powershell
powershell -ExecutionPolicy Bypass -File tools\start-local-studio.ps1
```

Open:

```text
http://127.0.0.1:8090/studio
```

The Studio page can record or upload audio, select a genre, generate an MP3, play it, and download it.

## Manual Backend

```powershell
Copy-Item lyricmorph-backend\.env.offline.example lyricmorph-backend\.env
cd lyricmorph-backend
python -m pip install -r requirements.txt --target .pydeps --upgrade
python dev_server.py
```

Backend URL:

```text
http://127.0.0.1:8090
```

## Smoke Test

With the backend running:

```powershell
powershell -ExecutionPolicy Bypass -File tools\smoke-local-generation.ps1
```

This creates a synthetic voice WAV, uploads it, generates a Lo-fi MP3, and downloads the result to:

```text
lyricmorph-backend/offline-prototype-demo.mp3
```

## Optional Expo Frontend

Copy the offline env file:

```powershell
Copy-Item lyricmorph-mobile\.env.offline.example lyricmorph-mobile\.env
```

Install and run:

```powershell
cd lyricmorph-mobile
npm install
npm run web
```

Open the Expo web URL, usually:

```text
http://localhost:8081
```

Choose guest mode for the offline path.

## Audio Generation

The offline backend can use ACE-Step when the local ACE-Step API is running, with procedural generation as the debug fallback. Real mixing still needs FFmpeg.

Start the local ACE-Step service:

```powershell
powershell -ExecutionPolicy Bypass -File tools\start-ace-step-api.ps1
```

Keep `SKARLY_ACE_STEP_SEND_LYRICS=false` for the normal vocal-to-music path. Skarly uses language and lyric emotion in the prompt but keeps ACE-Step instrumental so the final mix stays focused on the uploaded vocal.

AudioCraft remains a research backend on Windows because its native `av`/FFmpeg development-library dependency may need a custom toolchain.

Install FFmpeg and make sure this works:

```powershell
ffmpeg -version
```

If FFmpeg is not installed, upload/record flows can still reach the backend, but generation will fail with `FFmpeg is not available`.

If FFmpeg is installed outside `PATH`, set `SKARLY_FFMPEG_PATH` in the local backend `.env`.

## Visual Studio Code

Open the cloned repo folder:

```powershell
code .
```

Then use `Terminal > Run Task`:

- `Skarly: local studio`
- `Skarly: smoke local generation`
- `Skarly: install backend deps`
- `Skarly: backend offline`
- `Skarly: install frontend deps`
- `Skarly: frontend web`
