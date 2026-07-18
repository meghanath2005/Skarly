# Phase 16: ACE-Step Open-Source Music Generation

## Status

Started. Skarly backend now supports `SKARLY_MUSIC_GENERATOR_BACKEND=ace_step`.

## What Changed

- Added ACE-Step generator support inside the existing MVP audio worker.
- The worker can now:
  - download the recorded/uploaded vocal from Cloud Storage,
  - call an external ACE-Step REST server,
  - poll the ACE task until audio is ready,
  - download the generated backing audio,
  - mix vocal + backing bed with FFmpeg,
  - upload the final MP3 back to Cloud Storage.
- Procedural generation remains available as a fallback through:
  - `SKARLY_ACE_STEP_FALLBACK_TO_PROCEDURAL=true`

## Required ACE Setup

ACE-Step is not bundled into Skarly. It should run as a separate GPU-backed service.

Backend environment:

```env
SKARLY_MUSIC_GENERATOR_BACKEND=ace_step
SKARLY_ACE_STEP_BASE_URL=http://127.0.0.1:8001
SKARLY_ACE_STEP_API_KEY=
SKARLY_ACE_STEP_TIMEOUT_SECONDS=1800
SKARLY_ACE_STEP_DOWNLOAD_TIMEOUT_SECONDS=1800
SKARLY_ACE_STEP_POLL_INTERVAL_SECONDS=2.0
SKARLY_ACE_STEP_INFER_STEP=20
SKARLY_ACE_STEP_GUIDANCE_SCALE=15
SKARLY_ACE_STEP_MAX_DURATION_SECONDS=60
SKARLY_ACE_STEP_THINKING=false
SKARLY_ACE_STEP_USE_SOURCE_AUDIO=false
SKARLY_ACE_STEP_FALLBACK_TO_PROCEDURAL=false
SKARLY_STEM_SEPARATOR_BACKEND=demucs
SKARLY_DEMUCS_PATH=C:\Users\yeshw\Documents\Codex\ai-models\ACE-Step-1.5\.venv\Scripts\python.exe -m demucs.separate
SKARLY_DEMUCS_MODEL=htdemucs_ft
SKARLY_DEMUCS_TWO_STEMS=vocals
SKARLY_BACKING_VOCAL_CLEANUP_ENABLED=true
SKARLY_VOCAL_CLEANUP_ENABLED=true
SKARLY_VOCAL_MIX_GAIN=1.18
SKARLY_BACKING_MIX_GAIN=0.06
```

Local ACE-Step API command:

```bat
cd C:\Users\yeshw\Documents\Codex\ai-models\ACE-Step-1.5
start_api_server.bat
```

## Current Recommendation

Use ACE-Step locally or on a GPU VM first. Do not deploy ACE-Step inside the current Cloud Run backend. The FastAPI backend can call ACE-Step, but the model service itself needs GPU resources for acceptable generation speed.

## Still Pending

- Install and run ACE-Step separately with `start_api_server.bat`.
- Confirm the exact ACE REST server output shape on your machine.
- Run a real Skarly generation with `SKARLY_MUSIC_GENERATOR_BACKEND=ace_step`.
- Install Demucs in the same Python/runtime environment used by FastAPI, or set `SKARLY_DEMUCS_PATH` to a full command such as `C:\Path\To\python.exe -m demucs`.
- Keep `SKARLY_ACE_STEP_USE_SOURCE_AUDIO=false` for the current replacement-beat flow. Skarly analyzes the isolated vocal timing separately, then prompts ACE for a new instrumental so ACE does not try to continue or reconstruct the uploaded song.
- Keep generated-backing cleanup enabled with `SKARLY_BACKING_VOCAL_CLEANUP_ENABLED=true` so ACE vocal-like artifacts are stripped before final mixing.

## Fallback Behavior

If ACE-Step is offline and fallback is enabled, Skarly still produces a real MP3 using the procedural generator. This prevents demos from breaking while ACE setup is incomplete.

## Mix Notes

Skarly now isolates vocals from uploaded mixes before sending the vocal stem into ACE/procedural generation and final mixing. Backing vocals/ad-libs remain part of the vocal stem when Demucs preserves them. The generated backing defaults lower than the vocal and is ducked under the vocal during final FFmpeg mixing.
