# Skarly

Skarly is a local-first research prototype for vocal-to-music and music-to-music generation. It runs as a guest studio with no account system and no cloud services.

## Working architecture

- Expo / React Native web interface in `lyricmorph-mobile/`
- FastAPI backend in `lyricmorph-backend/`
- SQLite project metadata and local filesystem audio storage
- ACE-Step 1.5 for five AI backing versions
- Demucs for vocal isolation from full-song inputs
- FFmpeg for decoding, normalization, mixing and exports
- Whisper, Basic Pitch and a reviewed local audio-intelligence checkpoint for analysis

This release is deliberately limited to a local guest session, local persistence, an in-process worker, and the checked-in generation stack.

## Research internship package

- Executed notebook: `research/Skarly_Audio_Intelligence_Research.ipynb`
- Reproduction notes: `research/README.md`
- UI catalogue: `docs/ui-screenshots/README.md`
- PDF report: `output/pdf/Skarly_Research_Internship_Report.pdf`
- Editable report: `docs/research-report/Skarly_Research_Internship_Report.docx`

## Run locally

See `QUICKSTART.md`. The normal stack is:

1. Start the ACE-Step API with `tools/start-ace-step-api.ps1`.
2. Start FastAPI with `tools/start-local-studio.ps1`.
3. Run `npm install` and `npm run web` from `lyricmorph-mobile/`.
4. Open the Expo URL, enter the Local Guest Studio, and upload or record audio.

The ACE-Step repository and model weights are installed separately under a sibling `skarly-ai-repos/ACE-Step-1.5` checkout. Generated audio, downloaded datasets, dependencies, caches and local environment files are intentionally excluded from Git.

## Product boundary

Skarly is a private local research tool. It does not provide payments, public feeds, voice cloning, public remix distribution or account-based synchronization. Only use audio you have permission to process.
