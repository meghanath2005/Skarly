# Vocal-to-Music and Music-to-New-Music MVP

This upgrade adds a first-class browser upload and online-candidate workflow.

## User Flow

1. Open `/studio`.
2. Upload either a vocal, instrumental, or complete song in the **AI Music Transformation** panel.
3. Confirm that you own or have rights to use the audio.
4. Click **Analyze Vocal** to estimate duration, BPM, key, phrases, and sections.
5. Choose style settings, for example `Sufi Rock` + `Indie band arrangement`.
6. Click **Generate Around Vocal**.
7. Review A/B/C candidates:
   - backing only
   - vocal + backing mix
   - status/warnings
8. Use **Regenerate** with instructions such as `stronger rock drums and sadder piano`.

## API Flow

Upload:

```bash
curl -F "file=@vocal.wav" http://127.0.0.1:8000/uploads/audio
```

Analyze:

```bash
curl -X POST http://127.0.0.1:8000/uploads/{upload_id}/analyze
```

Vocal to music:

```bash
curl -X POST http://127.0.0.1:8000/v2/vocal-to-music \
  -H "Content-Type: application/json" \
  -d '{"upload_id":"upload_...","rights_confirmed":true,"production_style":"Sufi Rock","arrangement_style":"Indie band arrangement","candidate_count":3}'
```

Music to music:

```bash
curl -X POST http://127.0.0.1:8000/v2/music-to-music \
  -H "Content-Type: application/json" \
  -d '{"reference_upload_id":"upload_...","rights_confirmed":true,"source_mode":"auto","preserve_original_vocal":true,"style_instruction":"sad Bollywood rock, original arrangement","reference_strength":0.35}'
```

`source_mode` accepts `auto`, `instrumental`, or `full_song`. In `auto`,
Demucs checks for vocals. Instrumentals go directly to ACE-Step; complete songs
are split into `vocals.wav` and `no_vocals.wav`, and only the clean instrumental
is used as the generation reference. Set `preserve_original_vocal=true` to mix
the separated original singer onto the newly generated music.

Music-to-new-music prefers the local `ace_step` provider. It sends the
normalized reference as ACE-Step `cover` input, requests instrumental output,
and returns `reference_conditioned` plus `reference_strength` on each candidate.
A lower strength gives the model more freedom; `0.25` to `0.45` is the intended
range for a new arrangement that retains only broad structure and energy.

If ACE-Step is unavailable, the existing prompt-only providers and
`local_fallback` remain available. Their candidates explicitly report
`reference_conditioned: false`.

Regenerate:

```bash
curl -X POST http://127.0.0.1:8000/v2/jobs/{job_id}/regenerate \
  -H "Content-Type: application/json" \
  -d '{"rights_confirmed":true,"edit_instruction":"stronger rock drums and sadder piano","candidate_count":1,"reference_strength":0.45}'
```

## Environment

```env
ONLINE_MUSIC_ENABLED=true
MUSIC_PROVIDER_PRIMARY=elevenlabs
MUSIC_PROVIDER_SECONDARY=lyria
ELEVENLABS_API_KEY=
GEMINI_API_KEY=
ONLINE_MUSIC_TIMEOUT_SECONDS=900
GENERATE_CANDIDATE_COUNT=3
REQUIRE_RIGHTS_CONFIRMATION=true
UPLOADS_DIR=outputs/uploads
MAX_UPLOAD_MB=100
ONLINE_MUSIC_OUTPUT_DIR=outputs/online_music
STEMS_ENABLED=true
STEMS_ENGINE=demucs
DEMUCS_CLI_PATH=D:\path\to\demucs-python.exe -m demucs.separate
SKARLY_MUSIC_TO_MUSIC_VERIFY_GENERATED_VOCALS=true
SKARLY_MUSIC_TO_MUSIC_VOCAL_THRESHOLD_DB=-24
SKARLY_MUSIC_TO_MUSIC_MIN_VOCAL_ACTIVITY=0.04
```

If no online provider key is configured, v2 generation falls back to `local_fallback` using `procedural_v2`. This is useful for debugging the end-to-end upload, analysis, candidate, and mix flow, but it is not the product-quality path.

## Safety Rules

- Rights confirmation is required by default before online generation.
- Famous song or artist references are translated into broad style language.
- Vocal-to-music sends derived analysis and prompts. Local music-to-new-music intentionally sends the rights-confirmed clean instrumental to ACE-Step for reference conditioning.
- Every generated backing and mix is validated before being returned.
- Generated music must differ from the reference, match duration, pass silence/clipping validation, and pass the Demucs unwanted-vocal gate.
- Complete-song generation fails closed if both clean vocal and instrumental stems are not available.
- Online job responses are persisted under `ONLINE_MUSIC_OUTPUT_DIR/_jobs`, so Studio loading and regeneration survive a backend restart.

## Current Pipeline

Upload audio -> validate -> detect/split vocals when needed -> analyze timing/key/BPM/structure -> build an original composition plan -> reference-condition ACE-Step on the clean instrumental -> validate originality/duration/silence/clipping/unwanted vocals -> optionally remix the original separated singer -> return prepared-stem previews and candidates -> persist the job -> regenerate from the same clean reference after restart if needed.
