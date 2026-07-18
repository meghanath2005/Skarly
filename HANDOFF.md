# Skarly handoff

Skarly is a local Expo interface plus FastAPI audio backend. The supported path is guest-only vocal-to-music and music-to-music generation.

Keep these components together:

- `lyricmorph-mobile/` - primary user interface
- `lyricmorph-backend/` - API, SQLite/local storage, analysis and mixing
- `tools/` - local startup and smoke-test scripts
- `research/`, `docs/` and `output/pdf/` - internship evidence

External local dependencies are ACE-Step 1.5 and its weights, FFmpeg, Demucs, Whisper and Basic Pitch. They are intentionally not committed.

Use `QUICKSTART.md` for a new machine. Verify both a vocal/acapella upload and a full-song/music-to-music upload before releasing changes.
