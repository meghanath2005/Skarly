# Skarly local audio intelligence

## V2 shared pretrained encoder

The production-direction pipeline is `train_audio_intelligence.py`. It freezes
ACE-Step 1.5's pretrained `AutoencoderOobleck` music-audio encoder and trains
independent calibrated heads for language, singing/speech, vocal technique,
mood, multi-label genre, tempo family, Indian/Western melodic character, and
out-of-distribution confidence. Unlabelled heads are recorded as unavailable;
they never emit fabricated predictions.

Inference covers the complete decoded recording in contiguous six-second
windows and averages calibrated logits over every window. The frozen encoder
fingerprint, manifests, random seed, dataset versions, singer-group split,
per-head metrics, confusion matrices, calibration temperatures, and CUDA
runtime are stored in the checkpoint.

```powershell
$py = 'python'
& $py .\training\train_audio_intelligence.py `
  --manifest .\data\manifests\fleurs_hindi_english.jsonl `
  --manifest .\data\manifests\mmgenre_cc_by.jsonl `
  --output .\data\models\skarly_audio_intelligence_v2_candidate.pt `
  --epochs 20 --batch-size 4

& $py .\training\infer_audio_intelligence.py `
  --checkpoint .\data\models\skarly_audio_intelligence_v2_candidate.pt `
  --audio ..\sample-voice.wav
```

The legacy `train_audio_classifier.py` scratch CNN remains readable for old
checkpoints, but new releases should use the shared-encoder V2 format. Genre
approval still requires creator-confirmed coverage and `--approve-genre`.

This folder trains the small local classifier that improves the **language** and
**genre/style** hints used by Skarly. It is deliberately separate from music
generation: ACE-Step makes the backing tracks, while this CNN learns how to
route an uploaded vocal to better arrangement prompts.

## Data rights policy

Only train on audio that Skarly is allowed to use for ML training.

- Use Common Voice Hindi and English only for the `language` label. It is speech
  data, so it must **not** be used as musical genre data.
- Use user-owned recordings, artist-consented stems, or a dataset whose licence
  explicitly allows the intended commercial ML use for the `genre` label.
- Do not use a music dataset marked non-commercial research only in a commercial
  Skarly model. Keep a record of source, licence, and consent outside the
  manifest.
- Never put a customer upload in the training manifest without their explicit
  opt-in.

## Expected layout for owned/consented music

```
data/owned_music/
  Hindi/
    indie_pop/
      artist_consent_001.wav
  English/
    acoustic_ballad/
      artist_consent_002.wav
```

Build a manifest after confirming rights:

```powershell
$py = 'python'
& $py .\training\prepare_manifest.py owned-music `
  --audio-root .\data\owned_music `
  --output .\data\manifests\owned_music.jsonl `
  --rights-confirmed
```

## Creator-confirmed opt-in feedback

In the Skarly confirmation screen, a creator can explicitly confirm a genre and
enable **Training contribution**. It is off by default. When enabled, Skarly
retains only the normalized vocal plus the confirmed Hindi or English genre
label in `data/consented_feedback/`, and appends an auditable row to
`data/manifests/user_feedback.jsonl`.

Do not enable this for vocals the creator does not own or have permission to
contribute. Add the resulting manifest only after reviewing the labels:

```powershell
& $py .\training\train_audio_classifier.py `
  --manifest .\data\manifests\fleurs_hindi_english.jsonl `
  --manifest .\data\manifests\mmgenre_cc_by.jsonl `
  --manifest .\data\manifests\user_feedback.jsonl `
  --output .\data\models\skarly_audio_cnn.pt `
  --epochs 16 --batch-size 16
```

Creator-confirmed rows are sampled at **3×** by default during training, while
the grouped validation set remains unweighted. This makes a small reviewed
Hindi/English feedback set useful without presenting an inflated accuracy
score. Use `--creator-feedback-weight 1` to disable the boost; do not increase
it until each confirmed genre has enough independent recordings for a grouped
holdout.

Automatic genre routing is deliberately disabled unless the checkpoint was
trained with `--approve-genre`. That flag refuses to run until the manifest has
at least 50 creator-confirmed examples across three or more genres, with at
least five independent examples per genre. Review the grouped holdout metrics
before using it; otherwise Skarly continues to ask the creator to confirm the
style and uses the CNN for language ID only.

## Bootstrap Hindi + English language ID

The repository includes a downloader for the Hindi and English FLEURS `dev`
subset. FLEURS is CC-BY speech data; it improves language ID only, not music
genre or production style. The fast bootstrap is about 300 MB. Use `--split
train` when you are ready for the larger production language corpus.

```powershell
$py = 'python'
& $py .\training\download_fleurs.py --split dev

& $py .\training\train_audio_classifier.py `
  --manifest .\data\manifests\fleurs_hindi_english.jsonl `
  --output .\data\models\skarly_language_cnn.pt `
  --epochs 12 --batch-size 16
```

Set `SKARLY_AUDIO_CLASSIFIER_CHECKPOINT` to the reviewed checkpoint path and
restart the backend. Skarly will use its prediction only at confidence 0.70 or
higher, otherwise it retains the current Whisper/audio-analysis result. Broad
genre predictions have a stricter 0.78 confidence gate.

## Broad music-genre prior

`download_mmgenre.py` downloads a balanced CC-BY 4.0 subset of the MMGenre
benchmark. Its labels are broad (`pop`, `electronic`, `rock`, `world`, etc.)
and its singing source is Chinese/generated, so use it as a conservative genre
prior only. It does **not** replace a rights-cleared Hindi music collection.

```powershell
& $py .\training\download_mmgenre.py --per-genre 60
& $py .\training\train_audio_classifier.py `
  --manifest .\data\manifests\fleurs_hindi_english.jsonl `
  --manifest .\data\manifests\mmgenre_cc_by.jsonl `
  --output .\data\models\skarly_audio_cnn.pt `
  --epochs 16 --batch-size 16
```

After downloading Common Voice yourself under its current terms, make one
manifest per language (this carries no genre label):

```powershell
& $py .\training\prepare_manifest.py common-voice `
  --dataset-root D:\datasets\cv-corpus-26.0-2026-06-23\hi `
  --language Hindi `
  --output .\data\manifests\common_voice_hindi.jsonl
```

Merge manifests and train on the RTX GPU:

```powershell
Get-Content .\data\manifests\common_voice_hindi.jsonl, `
  .\data\manifests\common_voice_english.jsonl, `
  .\data\manifests\owned_music.jsonl | Set-Content -Encoding utf8 .\data\manifests\skarly_train.jsonl

& $py .\training\train_audio_classifier.py `
  --manifest .\data\manifests\skarly_train.jsonl `
  --output .\data\models\skarly_audio_cnn.pt `
  --epochs 16 --batch-size 16
```

The script auto-selects CUDA and prints the GPU name. Start with at least 100
clips for each language and 50 consented clips for each genre; balance matters
more than raw duration. A trained checkpoint can be checked with:

Validation is grouped by original recording: adjacent excerpts from one song
are never split between training and validation. When a creator-consented
example has both a language and genre label, the split balances and protects
both classifier heads together. This makes the genre score more conservative
but prevents a misleading result from song-level leakage.
Do not promote a genre checkpoint based only on generic or non-Hindi music;
keep creator genre confirmation enabled until rights-cleared Hindi examples
produce a useful grouped holdout score.

```powershell
& $py .\training\infer_audio_classifier.py `
  --checkpoint .\data\models\skarly_audio_cnn.pt `
  --audio ..\sample-voice.wav
```

The output is JSON so the backend can safely consume it after a checkpoint is
reviewed and approved.

## Human-rated arrangement diversity calibration

Skarly always compares the ten pairs formed by five instrumental backings.
Prototype thresholds remain conservative and are clearly reported as
unapproved until they are calibrated from human judgements.

The preferred workflow builds one blinded panel that covers Hindi clarity in
all three mix modes and at least 50 genuine arrangement pairs. It also inserts
hidden same-arrangement controls, keeps the admin mapping outside the served
directory, and generates calibration-ready JSONL after three reviewers finish:

```powershell
$py = 'python'

& $py -m training.human_validation build `
  --jobs-dir .\outputs\skarly\_v2_jobs `
  --backend-root . `
  --generation-ids <five-or-more-ready-generation-ids> `
  --mix-ids <three-mix-job-ids-for-each-of-three-or-more-Hindi-vocals> `
  --output .\outputs\validation
```

The command creates a deterministic `human_panel_<id>` directory. Reviewers
open `http://127.0.0.1:8090/api/v2/validation-panels/<panel-id>`, complete every
item independently with headphones, and place each exported JSON file in the
panel's `ratings/` directory. Then score the panel without approving it:

```powershell
& $py -m training.human_validation score `
  --panel .\outputs\validation\human_panel_<id> `
  --ratings .\outputs\validation\human_panel_<id>\ratings `
  --output .\outputs\validation\human_panel_<id>\scored
```

The report requires at least three independent raters, three Hindi sources,
all three mix modes, median clarity scores of at least 4/5, at least 80% beta
acceptance per mode, at least 50 genuine pairs, ten controls, 80% mean majority
agreement, and 90% control accuracy. It does not auto-approve itself.

For manual calibration input, create one JSONL row per pair/rater judgement.
The same `pair_id` should appear once for each independent `rater_id`; do not
duplicate a judgement to inflate coverage. Required fields are
`pair_id`, `rater_id`, `too_similar`, `embedding_similarity`,
`drum_onset_similarity`, `chord_change_similarity`,
`instrumentation_similarity`, and `perceptual_similarity`.

```powershell
& $py .\training\calibrate_diversity.py `
  --ratings .\data\manifests\diversity_human_ratings.jsonl `
  --output .\data\models\diversity_calibration.json
```

The candidate reports metrics and readiness but cannot activate itself. A
release approval requires at least 50 distinct pairs, ten examples in each
class, three independent raters, and an identified reviewer:

```powershell
& $py .\training\calibrate_diversity.py `
  --ratings .\data\manifests\diversity_human_ratings.jsonl `
  --output .\data\models\diversity_calibration.json `
  --approve --approved-by "reviewer-id"
```

Only then set `SKARLY_DIVERSITY_CALIBRATION_PATH` and restart the backend. The
health endpoint, generation manifests, export metadata, and Compare screen
continue to say `Prototype` if the file is missing, invalid, under-covered, or
not explicitly approved.

## Dataset release-readiness audit

Run the dependency-free audit before training or promoting any checkpoint:

```powershell
& python `
  .\training\audit_dataset_readiness.py `
  --manifest .\data\manifests\fleurs_hindi_english.jsonl `
  --manifest .\data\manifests\mmgenre_cc_by_tempo.jsonl `
  --output .\outputs\validation\dataset_readiness.json
```

It reports legal/provenance omissions, FLEURS dataset-role violations, labels
per class, independent singers per class, all eight head statuses, and separate
prototype-versus-production readiness. Unknown singer identity remains missing;
the tool never invents a singer ID from a clip or sentence ID.

Older generated public manifests can be upgraded without downloading audio
again:

```powershell
& python `
  .\training\enrich_public_manifest_metadata.py `
  --manifest .\data\manifests\fleurs_hindi_english.jsonl `
  --manifest .\data\manifests\mmgenre_cc_by_tempo.jsonl
```

The enrichment stores the truthful licence, provenance, usage, revocation,
audio-role, dataset-version, and review fields available for the public source.
It deliberately leaves `singer_id` null when the upstream dataset does not
provide one, which keeps production release blocked until singer-disjoint data
exists.
