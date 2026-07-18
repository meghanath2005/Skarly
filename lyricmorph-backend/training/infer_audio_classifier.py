"""Emit predictions from a legacy CNN or V2 shared-encoder checkpoint."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch
import torchaudio

from train_audio_classifier import CLIP_SECONDS, SAMPLE_RATE, MelCnn, N_MELS


def predict(checkpoint_path: Path, audio_path: Path) -> dict[str, object]:
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    if checkpoint.get("format") == "skarly_audio_intelligence_v2":
        # Keep one stable backend command while allowing reviewed V2
        # checkpoints to opt into the richer, full-song inference path.
        from infer_audio_intelligence import predict as predict_v2

        return predict_v2(checkpoint_path, audio_path)
    if checkpoint.get("format") != "skarly_audio_cnn_v1":
        raise ValueError("This is not a supported Skarly audio-intelligence checkpoint.")
    language_classes = checkpoint["language_classes"]
    genre_classes = checkpoint["genre_classes"]
    model = MelCnn(len(language_classes), len(genre_classes))
    model.load_state_dict(checkpoint["model_state"])
    model.eval()
    waveform, rate = torchaudio.load(audio_path)
    waveform = waveform.mean(dim=0, keepdim=True)
    if rate != SAMPLE_RATE:
        waveform = torchaudio.functional.resample(waveform, rate, SAMPLE_RATE)
    sample_count = SAMPLE_RATE * CLIP_SECONDS
    if waveform.shape[1] > sample_count:
        start = (waveform.shape[1] - sample_count) // 2
        waveform = waveform[:, start:start + sample_count]
    else:
        waveform = torch.nn.functional.pad(waveform, (0, sample_count - waveform.shape[1]))
    mel = torchaudio.transforms.MelSpectrogram(sample_rate=SAMPLE_RATE, n_fft=1024, hop_length=160, n_mels=N_MELS)(waveform)
    # MelSpectrogram returns [channel, mel_bins, frames] for one waveform;
    # inference needs the explicit leading batch dimension expected by Conv2d.
    mel = torch.log(mel.clamp_min(1e-5)).unsqueeze(0)
    with torch.no_grad():
        language_logits, genre_logits = model(mel)
    language_probability, language_index = torch.softmax(language_logits[0], dim=0).max(dim=0)
    result: dict[str, object] = {
        "checkpoint": str(checkpoint_path),
        "language": language_classes[int(language_index)],
        "language_confidence": round(float(language_probability), 4),
        "genre": None,
        "genre_confidence": None,
        "genre_approved": bool(checkpoint.get("genre_approved", False)),
    }
    if genre_logits is not None:
        genre_probability, genre_index = torch.softmax(genre_logits[0], dim=0).max(dim=0)
        result["genre"] = genre_classes[int(genre_index)]
        result["genre_confidence"] = round(float(genre_probability), 4)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--audio", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(predict(args.checkpoint, args.audio), ensure_ascii=False))


if __name__ == "__main__":
    main()
