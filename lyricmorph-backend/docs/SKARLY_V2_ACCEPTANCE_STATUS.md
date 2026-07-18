# Skarly V2 vocal-to-music acceptance status

Last verified: 2026-07-15 (Asia/Calcutta)

## Release statement

The local Hindi/English vocal-to-music prototype is operational end to end. It accepts a complete vocal, builds a Song Intelligence Map, creates five source-conditioned ACE-Step arrangements on the RTX 5070, adaptively mixes the unchanged vocal, supports whole-version and section regeneration, and exports a DAW-ready package.

This is not yet approved as a production ML release. Human-rated diversity calibration, a structured Hindi clarity listening panel, and consented singer-labelled Indian training data remain release gates.

## Verified local capabilities

| Requirement | Current evidence | Status |
| --- | --- | --- |
| WAV, MP3, M4A, AAC, and FLAC upload | `app/services/uploads.py` validates the supported extensions and preserves `original.*` before decoding/analysis. | Verified |
| Complete Song Intelligence Map | The map now stores the original full-song pitch curve plus stable notes, note transitions, pitch-slide and possible meend/andolan/gamak candidates, transposition-invariant repeated melodic motifs, timestamped Whisper lyric-repetition evidence when available, pickup candidates, phrase-relative tempo, rhythmic density, persistent key-change candidates, chord-fit planning candidates, and phrase/motif/lyric/energy section evidence. Raw expressive pitch is never quantized away, and untimed transcript text is never used to invent boundaries. | Verified technically; semantic candidates require confirmation |
| Creator-confirmed BPM and key | Screen 2 accepts an optional 40-220 BPM correction and a normalized major/minor key such as `D minor` or `F# major`. The V2 generation request validates both values, all five producers use the corrected tempo/tonality, chord compatibility is recomputed for a confirmed key, and the Song Intelligence Map persists the values and their creator-confirmed provenance. | Verified |
| Five distinct producer arrangements | The five default Hindi profiles have different instruments, rhythm, bass, energy, transitions, and stereo blueprints. Live CUDA jobs produced all five versions. | Verified |
| 30, 120, and 300 second songs | `skarly_job_1b1f073d4ea1`, `skarly_job_4f205933dbfe`, and `skarly_job_fc03db3d1f55` contain five backings and five mixes each. All 30 audio files independently decode to the exact vocal duration. | Verified |
| Pairwise arrangement diversity | The current evaluator rechecked all ten pairs for each 30/120/300-second set: 10 evaluated, 0 rejected, pass. Threshold set is `prototype-conservative-v1`. | Prototype-verified; human calibration pending |
| RTX 5070 CUDA enforcement | Live telemetry records `NVIDIA GeForce RTX 5070 Laptop GPU`, capability `12.0`, Torch `2.7.1+cu128`, CUDA `12.8`, `sm_120`, backend `cuda`, model `acestep-v15-turbo`, and `cpu_fallback=false`. ACE-Step's official benchmark matrix passed all 12 configurations across 30/60/120 seconds, batch sizes 1/2, with and without the language-model path; LM, DiT, and VAE timings are preserved in hashed evidence. | Verified |
| Adaptive vocal-forward mixing | The mixer adapts measured vocal/backing levels and uses vocal-triggered multiband ducking: bass/kick stay unducked while the vocal presence and air bands are dynamically protected. | Verified technically |
| Vocal Forward, Balanced, Beat Forward | Four Hindi vocals now have all three live adaptive mix modes at exact decoded lengths: 10, 120, 220.992, and 258.408 seconds. The 10-second Beat Forward mix increased sub-180 Hz energy share from 4.4% to 20.1%. | Verified technically; human ratings pending |
| Blinded human validation workflow | Panel `human_panel_422016e3dba25b5b` contains 12 Hindi clarity items, 60 genuine producer pairs, ten hidden same-arrangement controls, 50 decodable 10-30 second MP3 montages, a private admin mapping, and a served reviewer UI. JavaScript syntax, HTTP 200 page delivery, HTTP 206 audio ranges, and HTTP 404 admin isolation passed. | Ready for three independent reviewers |
| Regenerate one producer | Live regeneration changed the requested backing and preserved the other four SHA-256 hashes. | Verified |
| Regenerate one section | Live job `section_8773c6cb307c4dc187cd452bebb9b58d` repainted 2.0-4.0 seconds. Independent comparison found `outside_max_abs_error=0.0`, `inside_mean_abs_delta=0.12677`, exact 10-second output, ten diversity pairs passed, and no CPU fallback. | Verified |
| Remix without regeneration | `/api/v2/mixes` preserves the instrumental and reruns only adaptive mixing. | Verified |
| Complete export and individual stems | Live export `skarly_export_841ca1b316134656b8158121c97468c8` contains final WAV/MP3, instrumental, processed vocal, drums, bass, other, analysis, song map, AI disclosure, and ZIP. Every audio artifact is exactly 10 seconds and has a SHA-256 digest. | Verified |
| Six-screen application flow | Expo implements record/upload, analysis confirmation, five producer cards, real progress, comparison/editing, and export. The analysis screen renders a complete-vocal energy waveform with shaded phrase regions and phrase-start markers. Producer switching preserves the current playback position, while final, instrumental, and solo-vocal controls independently show their correct play/pause state. | Verified by TypeScript build and live React Native Web render |
| V2 API | Analyse, generate, job status, regenerate, section regenerate, remix, feedback, and export endpoints are present and owner-scoped. | Verified |
| Explicit training opt-in | Audio retention occurs only with explicit consent plus permission/version metadata; otherwise feedback remains non-training product feedback. | Verified |
| Full regression | `py -3.12 -m pytest -q`: 289 passed. Shared ACE-Step encoder/head tests: 4 passed. Expo `tsc --noEmit`: passed. The live web bundle reached the Studio home without runtime errors; only React Native Web deprecation warnings were reported. | Verified |

## Full-song intelligence live check

The enriched analyser was run against the existing 120-second Hindi validation vocal on 2026-07-15. It covered all 120 seconds in 5.61 seconds and produced 17 phrases, 3,000 full-timeline pitch samples, 214 stable-note regions, 152 note transitions, 77 slide candidates, 93 possible ornament candidates, four repeated melodic-motif groups, phrase-relative rhythmic evidence, six phrase-aligned sections, and a flexible beat-map recommendation. These are planning candidates, not claims of musicological ground truth; semantic section, key-change, delivery, and ornament labels remain visibly confirmable.

## ML/AI implementation state

Skarly uses ACE-Step 1.5 for music generation, Basic Pitch for melody/MIDI analysis, Whisper for language/transcription assistance, Demucs for source/stem separation, signal analysis for BPM/key/phrases/energy, and FFmpeg for adaptive mixing/mastering.

The learning architecture uses one shared pretrained ACE-Step VAE/audio representation with independent heads for:

- language;
- singing/speech/rap/humming;
- vocal technique;
- mood;
- multi-label genre;
- tempo family;
- Indian/Western/mixed melodic character;
- in/out-of-distribution confidence.

The architecture and masked multi-task training code are implemented. Prototype checkpoints/evidence exist for language, singing/speech, tempo, broad genre, and OOD behavior. Mood, vocal-technique, and melodic-character heads do not yet have adequate supervised data and must not be presented as production-trained predictions.

## Unapproved release gates

1. **Hindi vocal clarity ratings** — the blinded panel is built and served at `http://127.0.0.1:8090/api/v2/validation-panels/human_panel_422016e3dba25b5b`. Three independent Hindi-speaking reviewers must rate lyric intelligibility, pumping, pronunciation integrity, and vocal/music balance. No ratings have been fabricated or pre-filled.
2. **Human-rated diversity calibration** — the same panel has 60 genuine pairs and ten hidden controls, but the active calibration remains `approved=false` until three reviewers complete it and an identified release owner explicitly approves the scored manifest.
3. **Consented Indian vocal dataset** — `outputs/validation/dataset_readiness.json` reports 1,233 research rows but no singer IDs, no supervised mood/vocal-technique/melodic-character rows, and zero rows for the five target Indian popular genres. Production training requires singer-disjoint, consented data with rights and revocation metadata.

## Current local services

- Expo: `http://127.0.0.1:8081`
- FastAPI: `http://127.0.0.1:8090/health`
- ACE-Step: `http://127.0.0.1:8001/docs`

All three endpoints returned HTTP 200 at the time of this audit.

The blinded Hindi review panel at `http://127.0.0.1:8090/api/v2/validation-panels/human_panel_422016e3dba25b5b` also returned HTTP 200. The running OpenAPI contract exposes `bpm_override`, `key_override`, and persisted `confirmed_corrections` after the final backend restart.

## Time to the next milestones

- Polished local vocal-to-music demo: engineering work is complete for the currently automatable scope; the ready-made panel reduces the remaining structured listening work to roughly 2-4 reviewer-hours plus any mix tuning it reveals.
- Human-calibrated beta: about 1 working day once three Hindi-speaking reviewers are available, plus up to 1-2 days if their ratings reveal mix or diversity defects.
- Production ML release: approximately 6-12 weeks, primarily for consented singer-labelled data collection, model training, and human validation rather than application plumbing.
