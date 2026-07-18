"""Add transparent DSP-derived tempo-family labels to a rights-cleared manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import librosa
import numpy as np


def classify_tempo(bpm: float) -> str:
    if bpm < 78:
        return "slow"
    if bpm < 122:
        return "medium"
    return "fast"


def estimate(path: Path) -> tuple[float, float]:
    audio, sample_rate = librosa.load(path, sr=22_050, mono=True, duration=45.0)
    if not len(audio):
        raise ValueError("decoded audio is empty")
    onset = librosa.onset.onset_strength(y=audio, sr=sample_rate)
    tempo, beats = librosa.beat.beat_track(onset_envelope=onset, sr=sample_rate, units="frames")
    bpm = float(np.asarray(tempo).reshape(-1)[0])
    if not np.isfinite(bpm) or bpm <= 0:
        raise ValueError("tempo estimator did not find a stable BPM")
    beat_count = int(len(beats))
    duration = len(audio) / sample_rate
    expected = max(1.0, duration * bpm / 60.0)
    confidence = min(0.95, max(0.15, beat_count / expected))
    return bpm, confidence


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source", default="mmgenre_cc_by_4_0", help="Only this source receives weak tempo labels")
    args = parser.parse_args()

    rows: list[dict[str, object]] = []
    labelled = 0
    failed = 0
    for line in args.manifest.read_text(encoding="utf-8-sig").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if str(row.get("source") or "") == args.source and bool(row.get("rights_confirmed")):
            try:
                bpm, confidence = estimate(Path(str(row["audio_path"])))
                row["bpm"] = round(bpm, 3)
                row["tempo_family"] = classify_tempo(bpm)
                row["tempo_confidence"] = round(confidence, 3)
                row["tempo_label_origin"] = "librosa_beat_bootstrap"
                labelled += 1
            except Exception as exc:
                row["tempo_label_warning"] = str(exc)[:160]
                failed += 1
        rows.append(row)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(json.dumps({"input": str(args.manifest), "output": str(args.output), "rows": len(rows), "tempo_labelled": labelled, "failed": failed}))


if __name__ == "__main__":
    main()

