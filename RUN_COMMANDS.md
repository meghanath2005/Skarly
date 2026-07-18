# Skarly local run commands

All commands are relative to the repository root. See [QUICKSTART.md](QUICKSTART.md) for first-time setup and troubleshooting.

Run these in three separate PowerShell terminals:

## 1. ACE-Step API — port 8001

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\start-ace-step-api.ps1
```

If ACE-Step is not stored at `..\skarly-ai-repos\ACE-Step-1.5`, set `SKARLY_ACE_STEP_REPO` first.

## 2. Skarly backend — port 8090

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\start-local-studio.ps1 -NoBrowser
```

## 3. Expo web UI — port 8081

```powershell
Set-Location .\lyricmorph-mobile
npm install
npm run web
```

Open `http://localhost:8081`. Keep the three terminals open and start ACE-Step before requesting generation.
