# Skarly Audio Validation Checklist

Use this for one real full-song upload in the local Studio at `http://127.0.0.1:8090/studio`.

## Fillable QA Table

| Artifact | What to listen for | Good sign | Problem sign | Fix if bad | Notes |
| --- | --- | --- | --- | --- | --- |
| Isolated vocal | Lead clarity, lyric intelligibility, old beat bleed, phrase starts | Vocal is clear and usable | Muffled vocal, beat leaking, too quiet, chopped consonants | Try a cleaner source, improve separation, lower backing gain | |
| Backing-only | Mood, tempo, key feel, arrangement density | Supports the vocal mood and leaves space | Wrong mood, off-tempo, too busy, too empty | Try 30s first, override BPM/key/style, switch style preset | |
| Final mix | Vocal level, timing, clipping, masking | Vocal is slightly forward and timing feels stable | Vocal too low, backing too loud, clipping, timing mismatch | Raise vocal gain, lower backing gain, adjust ducking, retry short duration | |
| Melody MIDI | Melody contour and note density | Captures the main vocal shape | Missing, too sparse, noisy, wrong octave | Treat as fallback guide or retry with cleaner vocal | |
| Chord sheet | Key/chords as producer starting point | Chords feel plausible for demo handoff | Chords clash with vocal or key feels wrong | Override key and regenerate pack | |
| Producer Pack ZIP | Required files and JSON readability | Pack is complete and readable | Missing files or unreadable JSON | Check `quality_report.json` warnings and rerun failed step | |

## Recommended First Real Test

- Upload type: full song
- Mode: Full Song re-arrange
- Style: Bollywood Ballad or Piano Ballad
- Duration: 30s first
- Production BPM: use half-time if auto BPM is double
- Key: use auto unless clearly wrong
- Then test 60s
- Then test 150s only after 30s and 60s work

Recommended validation order:

1. procedural_v2, 30s
2. ACE-Step, 30s
3. ACE-Step, 60s
4. ACE-Step, 150s

## Result Template

isolated vocal:
- clear / muffled / beat leaking / too quiet

backing-only:
- good mood / wrong mood / too busy / off-tempo / too empty

final mix:
- vocal clear / vocal too low / backing too loud / clipping / timing mismatch

Producer Pack:
- complete / missing files / JSON unreadable
