# Skarly quick start

This guide starts the same local stack used for the verified guest run. It keeps all user audio and generated files local unless you deliberately configure cloud storage.

## Prerequisites

- Windows 10/11 with PowerShell 5.1 or newer
- Python 3.12
- Node.js 20 or newer and npm
- FFmpeg available on `PATH`
- NVIDIA CUDA GPU for the release generation path
- A working [ACE-Step 1.5](https://github.com/ace-step/ACE-Step-1.5) checkout and its model weights

Optional analysis tools are Demucs, Basic Pitch, and Whisper. The web application can run without Firebase credentials in guest mode.

## 1. Clone and configure

```powershell
git clone https://github.com/meghanath2005/Skarly.git
cd Skarly
Copy-Item .\lyricmorph-backend\.env.offline.example .\lyricmorph-backend\.env
```

Open `lyricmorph-backend/.env` and set executable paths only when the commands are not already on `PATH`. Never commit that file.

The ACE-Step launcher looks for a sibling checkout at `..\skarly-ai-repos\ACE-Step-1.5`. A different location is supported with:

```powershell
$env:SKARLY_ACE_STEP_REPO = 'D:\path\to\ACE-Step-1.5'
```

## 2. Start the three services

Open three PowerShell windows at the repository root.

Terminal 1 — ACE-Step API:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\start-ace-step-api.ps1
```

Terminal 2 — Skarly backend (the launcher creates `.env`, installs Python packages into `.pydeps`, and starts port 8090):

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\start-local-studio.ps1 -NoBrowser
```

Terminal 3 — Expo web UI:

```powershell
Set-Location .\lyricmorph-mobile
npm install
npm run web
```

Open `http://localhost:8081`, choose **Guest**, and upload or record audio. Keep all three terminals running during generation. The first ACE-Step request is slower because model weights must be loaded.

## 3. Verify the build

```powershell
Set-Location .\lyricmorph-mobile
npm run typecheck
```

The complete UI evidence is indexed in [`docs/ui-screenshots/README.md`](docs/ui-screenshots/README.md). The executable research notebook and report are in [`research/`](research/) and [`docs/research-report/`](docs/research-report/).

## Optional: rerun the research notebook

Install the research-only packages, point the notebook at audio you are allowed to analyse, then launch Jupyter:

```powershell
python -m pip install -r .\research\requirements-research.txt
$env:SKARLY_AUDIO_PATH = 'D:\path\to\permitted-audio.mp3'
jupyter notebook .\research\Skarly_Audio_Intelligence_Research.ipynb
```

The audio path is read at runtime. Source audio is intentionally excluded from Git.

## Troubleshooting

- `ACE-Step repo not found`: set `SKARLY_ACE_STEP_REPO` to the checkout directory.
- `ffmpeg not found`: install FFmpeg and reopen the terminal, or set `SKARLY_FFMPEG_PATH` in the local `.env`.
- CUDA unavailable: the release configuration deliberately rejects CPU fallback; install compatible NVIDIA drivers/CUDA or use the UI without running a generation.
- Port already in use: stop the old process on ports 8001, 8090, or 8081 before restarting.
