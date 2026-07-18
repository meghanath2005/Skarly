# Skarly research artifacts

`Skarly_Audio_Intelligence_Research.ipynb` is an executable, original research notebook for signal analysis, model documentation, and reproducible plots.

## Run

1. Install Python 3.11+ and FFmpeg.
2. Install the packages in `requirements-research.txt`.
3. Point `SKARLY_AUDIO_PATH` to an audio file you are permitted to analyze.
4. Run the notebook from the repository root.

PowerShell example:

```powershell
$env:SKARLY_AUDIO_PATH='C:\path\to\your-audio.mp3'
jupyter notebook .\research\Skarly_Audio_Intelligence_Research.ipynb
```

The notebook writes charts to `research/artifacts/`. The source audio is never copied into the repository.

`data/skarly_audio_cnn_history.json` contains only training metadata exported from the local checkpoint; no weights or audio are duplicated.
