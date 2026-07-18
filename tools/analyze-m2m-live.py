from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf


def load_audio(path: Path, sample_rate: int = 22050) -> tuple[np.ndarray, int]:
    audio, rate = librosa.load(str(path), sr=sample_rate, mono=True)
    return np.asarray(audio, dtype=np.float32), int(rate)


def cosine(left: np.ndarray, right: np.ndarray) -> float:
    left = np.asarray(left, dtype=np.float64).reshape(-1)
    right = np.asarray(right, dtype=np.float64).reshape(-1)
    denominator = float(np.linalg.norm(left) * np.linalg.norm(right))
    if denominator <= 1e-12:
        return 0.0
    return float(np.dot(left, right) / denominator)


def correlation(left: np.ndarray, right: np.ndarray) -> float:
    size = min(left.size, right.size)
    if size < 2:
        return 0.0
    left = left[:size] - float(np.mean(left[:size]))
    right = right[:size] - float(np.mean(right[:size]))
    denominator = float(np.linalg.norm(left) * np.linalg.norm(right))
    if denominator <= 1e-12:
        return 0.0
    return float(np.dot(left, right) / denominator)


def audio_features(audio: np.ndarray, sample_rate: int) -> dict[str, object]:
    tempo, _ = librosa.beat.beat_track(y=audio, sr=sample_rate)
    tempo_value = float(np.asarray(tempo).reshape(-1)[0])
    chroma = librosa.feature.chroma_cqt(y=audio, sr=sample_rate)
    mfcc = librosa.feature.mfcc(y=audio, sr=sample_rate, n_mfcc=20)
    onset = librosa.onset.onset_strength(y=audio, sr=sample_rate)
    return {
        "tempo_bpm": round(tempo_value, 3),
        "chroma": np.mean(chroma, axis=1),
        "mfcc": np.mean(mfcc, axis=1),
        "onset": onset,
    }


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tempo_family_delta(reference_bpm: float, output_bpm: float) -> float:
    candidates = [output_bpm * factor for factor in (0.5, 1.0, 2.0)]
    return min(abs(candidate - reference_bpm) for candidate in candidates)


def analyze(reference: Path, outputs: list[Path], demucs_root: Path | None = None) -> dict[str, object]:
    reference_audio, sample_rate = load_audio(reference)
    reference_features = audio_features(reference_audio, sample_rate)
    results = []
    for path in outputs:
        audio, output_rate = load_audio(path)
        features = audio_features(audio, output_rate)
        info = sf.info(str(path))
        peak = float(np.max(np.abs(audio))) if audio.size else 0.0
        result = {
                "path": str(path.resolve()),
                "sha256": sha256(path),
                "duration_seconds": round(float(info.frames) / float(info.samplerate), 3),
                "sample_rate": int(info.samplerate),
                "channels": int(info.channels),
                "tempo_bpm": features["tempo_bpm"],
                "tempo_delta_bpm": round(float(features["tempo_bpm"]) - float(reference_features["tempo_bpm"]), 3),
                "tempo_family_delta_bpm": round(
                    tempo_family_delta(float(reference_features["tempo_bpm"]), float(features["tempo_bpm"])),
                    3,
                ),
                "peak_amplitude": round(peak, 6),
                "waveform_correlation": round(correlation(reference_audio, audio), 6),
                "chroma_similarity": round(cosine(reference_features["chroma"], features["chroma"]), 6),
                "timbre_similarity": round(cosine(reference_features["mfcc"], features["mfcc"]), 6),
                "onset_similarity": round(correlation(reference_features["onset"], features["onset"]), 6),
            }
        if demucs_root:
            vocal_path = demucs_root / "htdemucs" / path.stem / "vocals.wav"
            if vocal_path.is_file():
                vocal_audio, _ = load_audio(vocal_path, output_rate)
                mixture_rms = float(np.sqrt(np.mean(np.square(audio), dtype=np.float64)))
                vocal_rms = float(np.sqrt(np.mean(np.square(vocal_audio), dtype=np.float64)))
                ratio = vocal_rms / max(mixture_rms, 1e-12)
                result["demucs_vocal_energy_ratio"] = round(ratio, 6)
                result["demucs_vocal_energy_db_below_mix"] = round(20 * np.log10(max(ratio, 1e-12)), 3)
                result["demucs_vocal_stem_path"] = str(vocal_path.resolve())
        results.append(result)
    return {
        "reference": {
            "path": str(reference.resolve()),
            "sha256": sha256(reference),
            "duration_seconds": round(reference_audio.size / sample_rate, 3),
            "tempo_bpm": reference_features["tempo_bpm"],
        },
        "outputs": results,
        "all_outputs_unique": len({item["sha256"] for item in results}) == len(results),
        "none_byte_identical_to_reference": all(item["sha256"] != sha256(reference) for item in results),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("reference", type=Path)
    parser.add_argument("outputs", nargs="+", type=Path)
    parser.add_argument("--demucs-root", type=Path)
    args = parser.parse_args()
    print(json.dumps(analyze(args.reference, args.outputs, args.demucs_root), indent=2))


if __name__ == "__main__":
    main()
