# Demucs RTX 5070 validation

Validated on 2026-07-16 with an NVIDIA GeForce RTX 5070 Laptop GPU.

## Runtime

- Python: dedicated `skarly-ai-repos/_envs/demucs` environment
- PyTorch: `2.7.1+cu128`
- Torchaudio: `2.7.1+cu128`
- CUDA available: `true`
- Device capability: `12.0`
- Compiled architecture: `sm_120`
- Demucs model: `htdemucs_ft`
- Demucs device: `cuda`
- Separation timeout: `1200` seconds

The archived Demucs 4.1 alpha package metadata declares `torchaudio<2.1`. The installed CUDA runtime is newer because the RTX 5070 requires a build containing `sm_120`. Compatibility was established with actual inference, not imports alone.

## Full-song acceptance run

Input: the 265.68-second full-song source from `skarly_job_9b34f1a34c7d`.

- Service status: `completed`
- Fallback used: `false`
- Demucs processing time: `31.914` seconds
- Wall time: `32.209` seconds
- Vocal stem: 265.68 seconds, stereo, 44.1 kHz, no clipping, validation passed
- No-vocals stem: 265.68 seconds, stereo, 44.1 kHz, no clipping, validation passed
- Vocal waveform correlation with instrumental: `0.038825`
- Low-activity spectral similarity: `0.303973`
- Low-activity vocal/instrumental level: `-10.056 dB`
- Leakage gate: `passed`

Validated files are under `outputs/validation/demucs-full-song/gpu-full/htdemucs_ft/source/`.

## Safety gates

- Demucs runs through the isolated stem service, which removes inherited `PYTHONPATH` and `PYTHONHOME`.
- Full-song generation requires validated `vocals` and `no_vocals` stems.
- A leakage report is required before the preserved singer reaches the mixer.
- Failed separation, failed leakage analysis, or detected leakage stops generation.
- The mixed source and center-channel estimate are never substituted as the lead vocal.

## Automated verification

The complete backend suite passed after these changes: `306 passed`.

