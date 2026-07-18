"""Run Skarly's V2 multi-head model across the complete decoded recording."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import torch
import torchaudio

from audio_intelligence import (
    CATEGORICAL_HEADS,
    DEFAULT_HEAD_CLASSES,
    MULTILABEL_HEADS,
    OOD_HEAD,
    AceStepVaeEncoder,
    AudioIntelligenceHeads,
    full_song_windows,
    temperature_scale,
)


def sorted_probabilities(labels: Sequence[str], values: torch.Tensor) -> list[dict[str, Any]]:
    pairs = sorted(zip(labels, values.tolist()), key=lambda item: item[1], reverse=True)
    return [{"label": label, "probability": round(float(probability), 4)} for label, probability in pairs]


def predict(checkpoint_path: Path, audio_path: Path, *, batch_size: int = 4) -> dict[str, Any]:
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    if checkpoint.get("format") != "skarly_audio_intelligence_v2":
        raise ValueError("This is not a Skarly V2 audio-intelligence checkpoint")
    classes: Mapping[str, Sequence[str]] = checkpoint.get("head_classes") or DEFAULT_HEAD_CLASSES
    encoder_config = checkpoint.get("encoder") or {}
    encoder_path = Path(str(encoder_config.get("path") or ""))
    if not encoder_path.is_dir():
        raise FileNotFoundError(f"The checkpoint's frozen ACE-Step encoder was not found: {encoder_path}")
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    encoder = AceStepVaeEncoder(encoder_path).to_device(device)
    heads = AudioIntelligenceHeads(classes).to(device)
    heads.load_state_dict(checkpoint["head_state"])
    heads.eval()

    waveform, sample_rate = torchaudio.load(audio_path)
    decoded_duration = float(waveform.shape[1]) / max(1, int(sample_rate))
    windows = full_song_windows(waveform, int(sample_rate))
    aggregated: dict[str, list[torch.Tensor]] = {head: [] for head in classes}
    with torch.inference_mode():
        for start in range(0, len(windows), max(1, batch_size)):
            embeddings = encoder(windows[start : start + batch_size].to(device))
            logits = heads(embeddings)
            for head, values in logits.items():
                aggregated[head].append(values.float().cpu())
    averaged = {head: torch.cat(parts).mean(dim=0) for head, parts in aggregated.items()}
    temperatures = checkpoint.get("temperatures") or {}
    thresholds = checkpoint.get("multilabel_thresholds") or {}
    confidence_thresholds = checkpoint.get("low_confidence_thresholds") or {}
    trained_heads = checkpoint.get("trained_heads") or {}

    result: dict[str, Any] = {
        "checkpoint": str(checkpoint_path.resolve()),
        "format": checkpoint["format"],
        "architecture": checkpoint.get("architecture"),
        "device": torch.cuda.get_device_name(0) if device.type == "cuda" else "cpu",
        "cuda": device.type == "cuda",
        "encoder": {
            "type": encoder_config.get("type"),
            "fingerprint_sha256": encoder_config.get("fingerprint_sha256"),
            "frozen": True,
        },
        "decoded_duration_seconds": round(decoded_duration, 4),
        "analysis_scope_seconds": round(decoded_duration, 4),
        "analysis_scope": "complete",
        "window_seconds": encoder_config.get("clip_seconds", 6),
        "windows_analysed": len(windows),
        "trained_heads": trained_heads,
        "genre_approved": bool(checkpoint.get("genre_approved", False)),
        "genre_approval_note": checkpoint.get("genre_approval_note"),
        "heads": {},
    }

    for head in CATEGORICAL_HEADS:
        if not trained_heads.get(head):
            result["heads"][head] = {"available": False, "reason": "no reviewed labels in checkpoint"}
            continue
        scaled = temperature_scale(averaged[head], temperatures.get(head, 1.0))
        probabilities = torch.softmax(scaled, dim=0)
        ranked = sorted_probabilities(classes[head], probabilities)
        threshold = float(confidence_thresholds.get(head, confidence_thresholds.get("default", 0.65)))
        result["heads"][head] = {
            "available": True,
            "prediction": ranked[0]["label"],
            "confidence": ranked[0]["probability"],
            "top_predictions": ranked[:3],
            "calibration_temperature": float(temperatures.get(head, 1.0)),
            "low_confidence": ranked[0]["probability"] < threshold,
        }

    for head in MULTILABEL_HEADS:
        if not trained_heads.get(head):
            result["heads"][head] = {"available": False, "reason": "no reviewed labels in checkpoint"}
            continue
        scaled = temperature_scale(averaged[head], temperatures.get(head, 1.0))
        probabilities = torch.sigmoid(scaled)
        ranked = sorted_probabilities(classes[head], probabilities)
        threshold = float(thresholds.get(head, 0.5))
        selected = [item for item in ranked if item["probability"] >= threshold]
        result["heads"][head] = {
            "available": True,
            "predictions": selected,
            "top_predictions": ranked[:3],
            "calibration_temperature": float(temperatures.get(head, 1.0)),
            "threshold": threshold,
            "low_confidence": ranked[0]["probability"] < float(confidence_thresholds.get(head, confidence_thresholds.get("default", 0.65))),
        }

    if trained_heads.get(OOD_HEAD):
        probability = float(
            torch.sigmoid(temperature_scale(averaged[OOD_HEAD], temperatures.get(OOD_HEAD, 1.0))).item()
        )
        result["heads"][OOD_HEAD] = {
            "available": True,
            "in_distribution_probability": round(probability, 4),
            "out_of_distribution": probability < float(confidence_thresholds.get(OOD_HEAD, 0.60)),
            "calibration_temperature": float(temperatures.get(OOD_HEAD, 1.0)),
        }
    else:
        result["heads"][OOD_HEAD] = {"available": False, "reason": "no reviewed OOD labels in checkpoint"}

    language = result["heads"].get("language") or {}
    genre = result["heads"].get("genre") or {}
    genre_top = (genre.get("top_predictions") or [{}])[0]
    result.update(
        {
            "language": language.get("prediction"),
            "language_confidence": language.get("confidence"),
            "genre": genre_top.get("label"),
            "genre_confidence": genre_top.get("probability"),
            "genre_probabilities": {
                item["label"]: item["probability"] for item in genre.get("top_predictions") or []
            },
            "mood_probabilities": {
                item["label"]: item["probability"]
                for item in (result["heads"].get("mood") or {}).get("top_predictions") or []
            },
            "vocal_technique_probabilities": {
                item["label"]: item["probability"]
                for item in (result["heads"].get("vocal_technique") or {}).get("top_predictions") or []
            },
            "singing_speech": (result["heads"].get("singing_speech") or {}).get("prediction"),
            "tempo_family": (result["heads"].get("tempo_family") or {}).get("prediction"),
            "melodic_character": (result["heads"].get("melodic_character") or {}).get("prediction"),
        }
    )
    ood = result["heads"].get(OOD_HEAD) or {}
    result["requires_confirmation"] = bool(
        not checkpoint.get("genre_approved", False)
        or genre.get("low_confidence", True)
        or ood.get("out_of_distribution", False)
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=4)
    args = parser.parse_args()
    print(json.dumps(predict(args.checkpoint, args.audio, batch_size=args.batch_size), ensure_ascii=False))


if __name__ == "__main__":
    main()

