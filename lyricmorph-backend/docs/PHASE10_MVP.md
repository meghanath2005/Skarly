# Skarly / LyricMorph Phase 10 MVP

Phase 10 turns the local backend into a testable studio MVP. It keeps the existing generation pipeline and adds local project saving, manifest exports, full health checks, safe output path handling, and dry-run cleanup.

## Pipeline

Prompt/preset -> ACE-Step if enabled -> audio validation -> procedural_v2 fallback if needed -> vocal/backing mix if vocal path is provided -> optional stems -> optional section edit prompt -> project save/export.

## Run Mock Mode

```powershell
$env:ACE_STEP_ENABLED="false"
py -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/studio`.

Mock mode builds prompts and stores mock jobs. It does not run ACE-Step, Demucs, or GPU workloads.

## Run ACE-Step Mode

```powershell
$env:ACE_STEP_ENABLED="true"
$env:ACE_STEP_MODE="cli"
$env:ACE_STEP_CLI_PATH="python -m acestep.generate"
$env:ACE_STEP_OUTPUT_DIR="outputs/ace_step"
py -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

If ACE-Step fails or fails validation and `PROCEDURAL_FALLBACK_ENABLED=true`, the backend attempts `procedural_v2`.

## Key Environment Variables

- `PROJECTS_ENABLED=true`
- `PROJECTS_DIR=outputs/projects`
- `EXPORTS_DIR=outputs/exports`
- `UPLOADS_DIR=outputs/uploads`
- `MAX_UPLOAD_MB=100`
- `MAX_PROJECTS_LIST=100`
- `OUTPUT_RETENTION_DAYS=14`
- `STARTUP_HEALTH_CHECKS=true`
- `STRICT_SAFE_PATHS=true`
- `APP_ENV=local`
- `APP_PUBLIC_BASE_URL=http://127.0.0.1:8000`
- `LOG_LEVEL=INFO`
- `PROCEDURAL_FALLBACK_ENABLED=true`
- `MIX_OUTPUT_DIR=outputs/mixes`
- `STEMS_ENABLED=true`
- `DEMUCS_CLI_PATH=python -m demucs`
- `SECTION_EDITING_MODE=ace_step`

## Project Saving

Projects are local JSON files:

```text
outputs/projects/{project_id}/project.json
```

Projects store lyrics, settings, safe audio path references, safe audio URLs, job diagnostics, quality reports, and notes. Audio files are referenced by default rather than copied.

Endpoints:

- `POST /projects`
- `GET /projects`
- `GET /projects/{project_id}`
- `PATCH /projects/{project_id}`
- `DELETE /projects/{project_id}`
- `POST /projects/from-job/{job_id}`

## Export Manifests

Exports write:

```text
outputs/exports/{export_id}/manifest.json
```

The manifest includes project metadata, job metadata, prompts, settings, quality reports, diagnostics, and safe audio/stem references when requested. ZIP packaging is intentionally not required in this phase.

Endpoints:

- `POST /exports`
- `GET /exports/{export_id}/manifest`

## Health And Diagnostics

Use `GET /health/full` for:

- output directory writability
- ACE-Step config state
- procedural fallback state
- mixer output state
- producer assistant mode
- stem config and Demucs availability
- section editing mode
- FFmpeg availability
- disk usage

Missing optional tools are reported as warnings, not crashes.

## Cleanup

Use `POST /cleanup` with `dry_run=true` by default. Cleanup scans known output directories and reports candidate files older than `OUTPUT_RETENTION_DAYS`. It never deletes project metadata. Actual deletion requires `dry_run=false` and `include_outputs=true`.

## Safe Paths

Only these output roots are considered safe:

- `outputs/ace_step`
- `outputs/procedural_v2`
- `outputs/mixes`
- `outputs/stems`
- `outputs/sections`
- `outputs/projects`
- `outputs/exports`
- `outputs/uploads`

Path traversal and arbitrary absolute paths are rejected.

## Feature Notes

- Mixing keeps backing audio available even if vocal mixing fails.
- Stem separation supports Demucs if installed, but tests do not require it.
- Section editing now uses ACE-Step 1.5 repaint mode. Skarly restores the original backing outside the selected interval, keeps boundary crossfades inside the interval, verifies preservation, and remixes the unchanged source vocal.
- Producer assistant remains deterministic/rule-based by default.

## Test Command

```powershell
py -m pytest
```

Known limitations: no billing, no remote identity layer, no model training, no ZIP export requirement, and no full DAW timeline.
