# ACE-Step 1.5 RTX 5070 profile

Validated on 2026-07-14 with ACE-Step's repository-owned
`profile_inference.py` tool.

## Command

```powershell
& 'D:\intern\skarly-ai-repos\ACE-Step-1.5\.venv\Scripts\python.exe' `
  'profile_inference.py' `
  --device cuda `
  --config-path 'acestep-v15-turbo' `
  --duration 10 `
  --batch-size 1 `
  --inference-steps 8 `
  --no-warmup
```

## Result

| Field | Result |
| --- | --- |
| GPU | NVIDIA GeForce RTX 5070 Laptop GPU |
| Reported VRAM tier | 8.0 GB, tier 3 |
| Device | CUDA |
| Model | `acestep-v15-turbo` |
| Audio duration | 10 seconds |
| Batch size | 1 |
| Diffusion steps | 8 |
| Generated outputs | 1 |
| Status | Success |
| Total wall time | 4.183 seconds |
| DiT pipeline time | 1.434 seconds |
| Diffusion time | 0.515 seconds |
| VAE decode time | 0.884 seconds |
| Peak CUDA allocation reported in the detailed log | 5.62 GB |

ACE-Step automatically enabled model CPU offload for the 8 GB tier. This is
memory management around a CUDA generation and is not Skarly's prohibited CPU
generation fallback. The diffusion model and VAE execution were reported on
`cuda`; Skarly continues to use `REQUIRE_CUDA=true` and
`ALLOW_CPU_GENERATION_FALLBACK=false`.

After profiling, the resident ACE-Step API was restarted and verified at
`http://127.0.0.1:8001/docs`. The Skarly backend health endpoint also confirmed
that ACE-Step is enabled, CUDA is required, and CPU generation fallback is
disabled.

## Official benchmark matrix

On 2026-07-15 the repository-owned benchmark mode was also run across the full
validation matrix:

```powershell
& 'D:\intern\skarly-ai-repos\ACE-Step-1.5\.venv\Scripts\python.exe' `
  'profile_inference.py' `
  --mode benchmark `
  --device cuda `
  --lm-backend pt `
  --config-path 'acestep-v15-turbo' `
  --lm-model 'acestep-5Hz-lm-0.6B' `
  --thinking `
  --offload-to-cpu
```

All 12 configurations passed: durations 30/60/120 seconds, batch sizes 1/2,
and both the direct DiT/VAE and language-model-thinking paths. The mean wall
time was 17.36 seconds (minimum 5.19, maximum 54.06); maximum component times
were 38.57 seconds for the LM, 12.01 seconds for DiT, and 8.13 seconds for VAE.

Canonical evidence is stored in
`outputs/validation/ace_step_profile_inference_evidence.json`. It records ACE-Step
commit `6d467e4b5081ccb0abf1ec1bf4fdf9051a2d34b0`, the profile script hash, the raw
result hash `ab32d1d80df52d96befad8ef9c96cb8cba02356811a1178f02c4744fbd44fd3b`,
CUDA runtime details, every per-configuration result, and the ten pass/fail
checks used by the backend health report.
