# Music-to-New-Music Live Validation

Date: 2026-07-15  
Machine: NVIDIA GeForce RTX 5070 Laptop GPU (8,151 MiB)  
Generator: ACE-Step v1.5 Turbo, local API on port 8001  
Skarly backend: local FastAPI on port 8090

## Result

The local deployment path is technically functional. Real reference-conditioned audio was generated through Skarly and ACE-Step, survived validation, loaded in the Studio player, and downloaded byte-for-byte correctly. The remaining release gates are a human listening/originality review and a real-user playback click on target desktop/mobile browsers.

## Complete-Song Validation (2026-07-16)

A real 30-second pop song containing both lead vocal and instrumentation was
uploaded through `/v2/music-to-music` with `source_mode=auto`,
`preserve_original_vocal=true`, and strength `0.35`.

- Source job: `39e14f9f-6d1b-44b5-bbe1-2249dabcf7af`
- Auto detection: `full_song` at confidence `0.99`
- Demucs: completed with both `vocals.wav` and `no_vocals.wav`
- Detected vocal level/activity: `-8.559 dB` relative to the mix / `0.8733`
- ACE-Step provider: local reference-conditioned `cover`, no CPU fallback
- New backing: exact 30.0 seconds, no silence, no clipping
- Originality: passed; source/new-backing waveform correlation `0.00359`
- Generated-vocal gate: passed; no vocal leakage detected
- Singer preservation: separated vocal versus known source vocal correlation `0.994791`; separated vocal versus final mix correlation `0.989234`
- Final mix: exact 30.0 seconds, peak `0.603811`, clipped sample fraction `0.0`
- HTTP delivery: prepared instrumental, separated vocal, new backing, final mix, and regenerated backing returned `200`; byte-range playback returned `206`
- Studio: the persisted job loaded after restart; all four audio elements decoded with `readyState=4` and 30-second duration; source mode, preserve-singer, strength, preview, and download controls were present and interactive

The first live attempt also proved fail-closed behavior when the Demucs command
was misconfigured: status was `separation_failed` and ACE-Step was not called.
The configuration was corrected so both the v1 and v2 paths use the installed
local Demucs environment.

Online response persistence was added after restart testing exposed an
in-memory-only job record. After a real backend restart, job
`39e14f9f-6d1b-44b5-bbe1-2249dabcf7af` was recovered from disk and regenerated
as `4afb3f71-491f-45c3-8651-848ef585f33d`; its best candidate again passed
originality, duration, and generated-vocal checks while preserving the singer.

## Source

- File: `backing_test.wav`
- Duration: 30.0 seconds
- Format: 48 kHz stereo PCM float WAV
- Upload ID: `upload_bdf90cb1c1d744dcaa79c41dbbb9f805`
- Source loudness: -18.02 dB
- Source quality: no silence or clipping detected

## Strength Matrix

| Reference strength | Job ID | Wall time | Peak observed GPU memory | Duration | Loudness | Quality result |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| 0.25 | `0756e421-1517-4359-9ec2-57287c5f1962` | 47.43 s (cold model load) | 7,062 MiB | 30.0 s | -16.58 dB | Passed; no silence/clipping |
| 0.35 | `db7be75b-de13-4ee7-9bd0-f12fb42af396` | 11.64 s | 5,554 MiB | 30.0 s | -15.64 dB | Passed; no silence/clipping |
| 0.45 | `d1bb8c08-6b88-4991-b2dd-7b301e32c96c` | 11.55 s | 6,072 MiB | 30.0 s | -17.75 dB | Passed; no silence/clipping |

All three responses reported `provider=ace_step`, `reference_conditioned=true`, and the requested reference strength.

## Originality and Musical Continuity Checks

- All three output hashes are unique and differ from the reference hash.
- Waveform correlations against the reference were low: 0.0203, 0.0081, and 0.0198.
- Chroma similarity remained high: 0.9635, 0.9826, and 0.9776, providing evidence that harmonic identity was retained while the waveform was newly generated.
- The 0.25 output retained the detected 161.50 BPM. The 0.35 and 0.45 outputs were detected at 83.35 BPM (a half-time interpretation), with a tempo-family delta of 5.21 BPM.
- Onset similarity varied substantially across strengths, further indicating distinct arrangements rather than copied audio.

These are automated indicators, not a substitute for a release-approved human originality panel. The backend currently reports that diversity calibration `prototype-conservative-v1` has not been human release-approved.

## Vocal Leakage Check

- Demucs estimated vocal-stem energy at -42.25 dB, -40.62 dB, and -34.99 dB relative to each mix.
- Whisper returned the same low-confidence `Thank you.` fragment for every instrumental result. This is consistent with a common ASR hallucination on music and is not treated as evidence of an audible vocal.

Automated checks indicate no material vocal content. A headphone listening check remains the final subjective gate.

## Resilience and Workflow Checks

- Regeneration: passed; a new 30-second reference-conditioned result was produced in 8.45 seconds.
- Longer input: passed; a 60-second result completed in 14.10 seconds with no silence or clipping.
- Two simultaneous jobs: passed; jobs completed in 12.37 and 18.43 seconds. ACE-Step safely queued/serialized the GPU work.
- ACE-Step outage: passed; Skarly completed with `local_fallback` and clearly reported `reference_conditioned=false`.
- Stop/restart recovery: passed; after ACE-Step restart, a real conditioned result completed in 31.39 seconds including model reload.
- HTTP downloads: passed for all three strength outputs; each returned HTTP 200 and the downloaded SHA-256 matched the server file.
- Studio loading: passed; the deep-linked job rendered its candidate and Chromium decoded the 30-second WAV with `readyState=4`, `duration=30`, and no media error.
- Machine playback: passed; the exact Skarly 0.35 WAV played through the Windows/SDL audio stack for two seconds, reached 1.93 seconds of decoded audio, and exited successfully (`ffplay` exit code 0).
- Studio download control: passed; a direct browser-input click invoked the candidate's `download` link without navigating away from Studio. Independent HTTP downloads for every strength returned byte-identical files.
- Studio controls: explicit Play/Pause and Download controls were added. The embedded automation browser globally rejects audible `audio.play()` because its harness does not grant media user activation, even for direct pointer input. Browser decoding plus real machine playback proves the media itself is playable; one physical click on each release browser remains a compatibility sign-off rather than a core pipeline blocker.

## Regression Tests

- Focused new source-preparation/transformation/API suite: 58 passed.
- Final full backend suite: 303 passed.
- Browser JavaScript syntax and Python compilation checks: passed.
- Expo/React Native TypeScript (`tsc --noEmit`): passed.

## Runtime Notes

- Flash Attention is unavailable on this Windows setup; ACE-Step falls back to PyTorch SDPA and generation succeeds.
- `torchao` reports an optional C++ extension compatibility warning; it did not prevent generation.
- ACE-Step and Skarly health endpoints are currently healthy, the model is initialized, CUDA is required, and CPU generation fallback is disabled.

## Remaining Human Release Gates

1. Listen to the 0.25, 0.35, and 0.45 outputs on headphones and record which strength best balances preservation and novelty.
2. Confirm no audible words or vocal artifacts, especially in the 0.45 result.
3. Click Play/Pause and Download in Skarly on the actual deployment desktop and mobile browsers to sign off browser-specific media policy and UX.
4. Obtain human approval for the diversity/originality calibration before calling the feature production-release ready.
