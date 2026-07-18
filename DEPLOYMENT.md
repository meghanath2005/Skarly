# Skarly Prototype Deployment

Skarly now has two deployable prototype paths.

## Local Python Studio

Best for development and demos on this machine:

```powershell
powershell -ExecutionPolicy Bypass -File tools\start-local-studio.ps1
```

Open:

```text
http://127.0.0.1:8090/studio
```

This path uses:

- FastAPI
- local filesystem storage
- FFmpeg
- procedural audio generation
- local GPU/system detection
- rule-agent production planning
- optional local LLM planning through Ollama at `http://127.0.0.1:11434`

## Container Backend

Requires Docker Desktop or another Docker-compatible runtime.

```powershell
docker compose up --build
```

Open:

```text
http://127.0.0.1:8090/studio
```

The container image installs FFmpeg and serves the Studio UI from FastAPI. Generated files are persisted to:

```text
lyricmorph-backend/.local-storage
```

## Optional Local LLM Agent

If Ollama is installed and running, Skarly will use it for the production-plan agent. Otherwise it uses the built-in rule agent.

Setup helper:

```powershell
powershell -ExecutionPolicy Bypass -File tools\setup-local-llm-agent.ps1
```

Suggested local settings:

```text
SKARLY_LOCAL_LLM_BASE_URL=http://127.0.0.1:11434
SKARLY_LOCAL_LLM_MODEL=llama3.2:1b
```

The machine has an NVIDIA RTX 5070 Laptop GPU with about 8 GB VRAM, so small local LLMs are the practical target for agent planning. The actual offline audio renderer remains FFmpeg plus procedural generation for reliability.

## Cloud Direction

The existing Cloud Run deployment scripts are still present under `lyricmorph-backend`. For cloud mode, switch storage/repository back to GCS/Firestore and configure Firebase credentials. For this offline prototype, those cloud services are intentionally not required.
