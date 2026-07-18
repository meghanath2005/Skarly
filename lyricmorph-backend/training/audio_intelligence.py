"""Shared pretrained audio encoder and calibrated task heads for Skarly.

The frozen encoder is ACE-Step 1.5's music-audio VAE.  It was trained to
represent complete music waveforms and is therefore a better common feature
space for vocal/music routing than the legacy scratch mel CNN.  Only the small
prediction heads are trained by this module; the upstream encoder weights stay
frozen and are referenced (not copied) by Skarly checkpoints.
"""

from __future__ import annotations

import hashlib
import math
import random
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import torch
import torchaudio
from torch import Tensor, nn
from torch.nn import functional as functional

try:
    from .audio_taxonomy import (
        CATEGORICAL_HEADS,
        DEFAULT_HEAD_CLASSES,
        MULTILABEL_HEADS,
        OOD_HEAD,
        normalize_genre,
        normalize_language,
        normalize_token,
        normalize_values,
    )
except ImportError:  # pragma: no cover - direct script execution
    from audio_taxonomy import (
        CATEGORICAL_HEADS,
        DEFAULT_HEAD_CLASSES,
        MULTILABEL_HEADS,
        OOD_HEAD,
        normalize_genre,
        normalize_language,
        normalize_token,
        normalize_values,
    )


SAMPLE_RATE = 48_000
CLIP_SECONDS = 6
EMBEDDING_DIM = 128
IGNORE_INDEX = -100

def tempo_family(row: Mapping[str, Any]) -> str | None:
    explicit = normalize_token(row.get("tempo_family"))
    if explicit in DEFAULT_HEAD_CLASSES["tempo_family"]:
        return explicit
    if bool(row.get("rubato")) or bool(row.get("free_tempo")):
        return "free"
    try:
        bpm = float(row.get("bpm") or row.get("tempo_bpm"))
    except (TypeError, ValueError):
        return None
    if bpm <= 0:
        return None
    if bpm < 78:
        return "slow"
    if bpm < 122:
        return "medium"
    return "fast"


def singer_group_id(row: Mapping[str, Any]) -> str:
    """Singer-disjoint group key, with a conservative recording fallback."""
    for field in ("singer_id", "contributor_id", "creator_id"):
        value = str(row.get(field) or "").strip()
        if value:
            return f"singer:{value}"
    for field in ("source_group", "recording_id"):
        value = str(row.get(field) or "").strip()
        if value:
            return f"recording:{value}"
    source = str(row.get("source") or "unknown").strip()
    path = Path(str(row.get("audio_path") or ""))
    return f"recording:{source}:{path.stem}"


def split_singer_disjoint(
    rows: Sequence[dict[str, Any]], validation_fraction: float, seed: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if len(rows) < 10 or validation_fraction <= 0:
        return list(rows), []
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(singer_group_id(row), []).append(row)
    groups = list(grouped)
    random.Random(seed).shuffle(groups)
    target = max(1, round(len(rows) * validation_fraction))
    validation_groups: set[str] = set()
    count = 0
    for group in groups:
        if count >= target and validation_groups:
            break
        if len(validation_groups) + 1 >= len(groups):
            break
        validation_groups.add(group)
        count += len(grouped[group])
    validation = [row for row in rows if singer_group_id(row) in validation_groups]
    training = [row for row in rows if singer_group_id(row) not in validation_groups]
    return training, validation


def encoder_fingerprint(encoder_path: str | Path) -> str:
    root = Path(encoder_path)
    digest = hashlib.sha256()
    for name in ("config.json", "diffusion_pytorch_model.safetensors"):
        path = root / name
        if not path.is_file():
            raise FileNotFoundError(f"ACE-Step VAE encoder file is missing: {path}")
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


class AceStepVaeEncoder(nn.Module):
    """Frozen ACE-Step/Stable-Audio VAE converted to a compact song embedding."""

    def __init__(self, encoder_path: str | Path, *, dtype: torch.dtype = torch.bfloat16) -> None:
        super().__init__()
        from diffusers.models import AutoencoderOobleck

        self.encoder_path = str(Path(encoder_path).resolve())
        self.vae = AutoencoderOobleck.from_pretrained(self.encoder_path)
        self.vae.requires_grad_(False)
        self.vae.eval()
        self.requested_dtype = dtype

    def to_device(self, device: torch.device) -> "AceStepVaeEncoder":
        dtype = self.requested_dtype if device.type == "cuda" else torch.float32
        self.vae.to(device=device, dtype=dtype)
        return self

    @property
    def device(self) -> torch.device:
        return next(self.vae.parameters()).device

    @property
    def dtype(self) -> torch.dtype:
        return next(self.vae.parameters()).dtype

    @torch.inference_mode()
    def forward(self, audio: Tensor) -> Tensor:
        if audio.ndim != 3 or audio.shape[1] != 2:
            raise ValueError("ACE-Step encoder input must be [batch, 2, samples] stereo audio")
        latent = self.vae.encode(audio.to(device=self.device, dtype=self.dtype)).latent_dist.mode().float()
        # Mean and standard deviation retain both overall timbre and variation
        # through the analysed window: [B, 64, T] -> [B, 128].
        return torch.cat((latent.mean(dim=-1), latent.std(dim=-1, unbiased=False)), dim=1)


class AudioIntelligenceHeads(nn.Module):
    """Independent prediction heads over one shared pretrained embedding."""

    def __init__(
        self,
        classes: Mapping[str, Sequence[str]] | None = None,
        *,
        embedding_dim: int = EMBEDDING_DIM,
        hidden_dim: int = 256,
        dropout: float = 0.2,
    ) -> None:
        super().__init__()
        self.classes = {key: tuple(values) for key, values in (classes or DEFAULT_HEAD_CLASSES).items()}
        self.shared_projection = nn.Sequential(
            nn.LayerNorm(embedding_dim),
            nn.Linear(embedding_dim, hidden_dim),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, hidden_dim),
            nn.GELU(),
        )
        self.heads = nn.ModuleDict(
            {
                head: nn.Linear(hidden_dim, 1 if head == OOD_HEAD else len(labels))
                for head, labels in self.classes.items()
            }
        )

    def forward(self, embeddings: Tensor) -> dict[str, Tensor]:
        shared = self.shared_projection(embeddings)
        return {head: layer(shared) for head, layer in self.heads.items()}


def fixed_audio_window(
    waveform: Tensor,
    sample_rate: int,
    *,
    clip_seconds: int = CLIP_SECONDS,
    random_crop: bool = False,
) -> Tensor:
    waveform = waveform.float()
    if waveform.ndim == 1:
        waveform = waveform.unsqueeze(0)
    if sample_rate != SAMPLE_RATE:
        waveform = torchaudio.functional.resample(waveform, sample_rate, SAMPLE_RATE)
    if waveform.shape[0] == 1:
        waveform = waveform.repeat(2, 1)
    elif waveform.shape[0] > 2:
        waveform = waveform[:2]
    samples = SAMPLE_RATE * clip_seconds
    if waveform.shape[1] > samples:
        maximum = waveform.shape[1] - samples
        start = random.randint(0, maximum) if random_crop else maximum // 2
        waveform = waveform[:, start : start + samples]
    elif waveform.shape[1] < samples:
        waveform = functional.pad(waveform, (0, samples - waveform.shape[1]))
    peak = waveform.abs().amax().clamp_min(1e-4)
    return (waveform / max(1.0, float(peak))).clamp(-1.0, 1.0)


def full_song_windows(
    waveform: Tensor,
    sample_rate: int,
    *,
    clip_seconds: int = CLIP_SECONDS,
) -> Tensor:
    """Return contiguous windows that cover the decoded song end-to-end."""
    waveform = waveform.float()
    if waveform.ndim == 1:
        waveform = waveform.unsqueeze(0)
    if sample_rate != SAMPLE_RATE:
        waveform = torchaudio.functional.resample(waveform, sample_rate, SAMPLE_RATE)
    if waveform.shape[0] == 1:
        waveform = waveform.repeat(2, 1)
    elif waveform.shape[0] > 2:
        waveform = waveform[:2]
    window_samples = SAMPLE_RATE * clip_seconds
    windows: list[Tensor] = []
    for start in range(0, max(1, waveform.shape[1]), window_samples):
        chunk = waveform[:, start : start + window_samples]
        if chunk.shape[1] < window_samples:
            chunk = functional.pad(chunk, (0, window_samples - chunk.shape[1]))
        windows.append(chunk)
    if not windows:
        windows.append(torch.zeros(2, window_samples))
    stacked = torch.stack(windows)
    peaks = stacked.abs().amax(dim=(1, 2), keepdim=True).clamp_min(1.0)
    return (stacked / peaks).clamp(-1.0, 1.0)


def augment_audio(waveform: Tensor, *, sample_rate: int = SAMPLE_RATE) -> Tensor:
    """Safe vocal augmentation: speed/pitch, room, noise, mic, and compression."""
    result = waveform.clone()
    if random.random() < 0.45:
        # Small speed perturbation changes timing/pitch only inside the safe
        # range used for robust routing; final generation never uses this copy.
        factor = random.uniform(0.94, 1.06)
        intermediate_rate = max(8_000, round(sample_rate * factor))
        result = torchaudio.functional.resample(result, sample_rate, intermediate_rate)
        result = functional.interpolate(result.unsqueeze(0), size=waveform.shape[-1], mode="linear", align_corners=False).squeeze(0)
    if random.random() < 0.30:
        semitones = random.uniform(-1.25, 1.25)
        result = torchaudio.functional.pitch_shift(result, sample_rate, semitones)
    if random.random() < 0.35:
        decay_samples = random.randint(160, 960)
        time = torch.linspace(0, 5, decay_samples, device=result.device)
        impulse = torch.exp(-time)
        impulse[0] = 1.0
        impulse = impulse / impulse.sum().clamp_min(1e-6)
        channels = []
        for channel in result:
            reverbed = functional.conv1d(
                functional.pad(channel[None, None], (decay_samples - 1, 0)), impulse[None, None]
            )[0, 0, : channel.shape[-1]]
            channels.append(0.82 * channel + 0.18 * reverbed)
        result = torch.stack(channels)
    if random.random() < 0.45:
        noise_scale = random.uniform(0.0003, 0.012)
        result = result + noise_scale * torch.randn_like(result)
    if random.random() < 0.30:
        drive = random.uniform(1.1, 2.0)
        result = torch.tanh(result * drive) / math.tanh(drive)
    if random.random() < 0.25:
        # Phone/microphone simulation by bandwidth reduction.
        result = torchaudio.functional.highpass_biquad(result, sample_rate, 120)
        result = torchaudio.functional.lowpass_biquad(result, sample_rate, 6_500)
    return (result * random.uniform(0.82, 1.12)).clamp(-1.0, 1.0)


def encode_row_targets(
    row: Mapping[str, Any], classes: Mapping[str, Sequence[str]] = DEFAULT_HEAD_CLASSES
) -> dict[str, Tensor]:
    targets: dict[str, Tensor] = {}
    language = normalize_language(row.get("language"))
    categorical_values = {
        "language": language,
        "singing_speech": normalize_token(row.get("singing_speech") or row.get("vocal_type")) or None,
        "tempo_family": tempo_family(row),
        "melodic_character": normalize_token(row.get("melodic_character") or row.get("melodic_system")) or None,
    }
    for head, value in categorical_values.items():
        labels = list(classes[head])
        targets[head] = torch.tensor(labels.index(value) if value in labels else IGNORE_INDEX, dtype=torch.long)

    raw_multilabel = {
        "vocal_technique": row.get("vocal_techniques") or row.get("vocal_technique"),
        "mood": row.get("moods") or row.get("mood"),
        "genre": row.get("genres") or row.get("genre"),
    }
    for head, raw in raw_multilabel.items():
        mapper = normalize_genre if head == "genre" else normalize_token
        values = set(normalize_values(raw, mapper=mapper))
        labels = list(classes[head])
        vector = torch.zeros(len(labels), dtype=torch.float32)
        for value in values:
            if value in labels:
                vector[labels.index(value)] = 1.0
        targets[head] = vector
        targets[f"{head}_valid"] = torch.tensor(bool(values), dtype=torch.bool)

    in_distribution = row.get("in_distribution")
    if in_distribution is None and normalize_token(row.get("distribution")) in {"in_distribution", "out_of_distribution"}:
        in_distribution = normalize_token(row.get("distribution")) == "in_distribution"
    targets[OOD_HEAD] = torch.tensor(float(bool(in_distribution)) if in_distribution is not None else -1.0)
    return targets


def masked_multitask_loss(
    logits: Mapping[str, Tensor],
    targets: Mapping[str, Tensor],
    *,
    head_weights: Mapping[str, float] | None = None,
) -> tuple[Tensor, dict[str, float]]:
    weights = dict(head_weights or {})
    losses: list[Tensor] = []
    details: dict[str, float] = {}
    for head in CATEGORICAL_HEADS:
        target = targets[head]
        valid = target != IGNORE_INDEX
        if valid.any():
            value = functional.cross_entropy(logits[head][valid], target[valid])
            value = value * float(weights.get(head, 1.0))
            losses.append(value)
            details[head] = float(value.detach())
    for head in MULTILABEL_HEADS:
        valid = targets[f"{head}_valid"].bool()
        if valid.any():
            value = functional.binary_cross_entropy_with_logits(logits[head][valid], targets[head][valid])
            value = value * float(weights.get(head, 1.0))
            losses.append(value)
            details[head] = float(value.detach())
    ood_target = targets[OOD_HEAD]
    ood_valid = ood_target >= 0
    if ood_valid.any():
        value = functional.binary_cross_entropy_with_logits(
            logits[OOD_HEAD].squeeze(1)[ood_valid], ood_target[ood_valid]
        ) * float(weights.get(OOD_HEAD, 1.0))
        losses.append(value)
        details[OOD_HEAD] = float(value.detach())
    if not losses:
        raise ValueError("The batch has no labels for any Skarly intelligence head")
    return sum(losses), details


def temperature_scale(logits: Tensor, temperature: float) -> Tensor:
    return logits / max(0.05, float(temperature))


def fit_temperature(logits: Tensor, targets: Tensor, *, multilabel: bool = False) -> float:
    """Small deterministic validation-grid calibrator without train leakage."""
    if logits.numel() == 0 or targets.numel() == 0:
        return 1.0
    best_temperature = 1.0
    best_loss = float("inf")
    for step in range(5, 61):
        temperature = step / 20.0
        scaled = temperature_scale(logits, temperature)
        loss = (
            functional.binary_cross_entropy_with_logits(scaled, targets.float())
            if multilabel
            else functional.cross_entropy(scaled, targets.long())
        )
        value = float(loss)
        if value < best_loss:
            best_loss = value
            best_temperature = temperature
    return round(best_temperature, 3)


def classification_metrics(logits: Tensor, targets: Tensor, labels: Sequence[str]) -> dict[str, Any]:
    predictions = logits.argmax(dim=1)
    confusion = torch.zeros(len(labels), len(labels), dtype=torch.int64)
    per_class: dict[str, dict[str, float | int]] = {}
    for target, prediction in zip(targets.cpu(), predictions.cpu()):
        confusion[int(target), int(prediction)] += 1
    for index, label in enumerate(labels):
        tp = int(confusion[index, index])
        fp = int(confusion[:, index].sum()) - tp
        fn = int(confusion[index, :].sum()) - tp
        precision = tp / max(1, tp + fp)
        recall = tp / max(1, tp + fn)
        f1 = 2 * precision * recall / max(1e-9, precision + recall)
        per_class[label] = {"precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4), "support": int(confusion[index].sum())}
    return {
        "accuracy": round(float((predictions == targets).float().mean()), 4),
        "per_class": per_class,
        "confusion_matrix": confusion.tolist(),
    }


def multilabel_metrics(logits: Tensor, targets: Tensor, labels: Sequence[str], threshold: float = 0.5) -> dict[str, Any]:
    predictions = torch.sigmoid(logits) >= threshold
    truth = targets.bool()
    per_label: dict[str, dict[str, float | int]] = {}
    for index, label in enumerate(labels):
        tp = int((predictions[:, index] & truth[:, index]).sum())
        fp = int((predictions[:, index] & ~truth[:, index]).sum())
        fn = int((~predictions[:, index] & truth[:, index]).sum())
        precision = tp / max(1, tp + fp)
        recall = tp / max(1, tp + fn)
        f1 = 2 * precision * recall / max(1e-9, precision + recall)
        per_label[label] = {"precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4), "support": int(truth[:, index].sum())}
    return {"per_label": per_label}


def genre_top_three_accuracy(logits: Tensor, targets: Tensor) -> float:
    if logits.numel() == 0:
        return 0.0
    top = logits.topk(min(3, logits.shape[1]), dim=1).indices
    hits = []
    for predicted, truth in zip(top, targets.bool()):
        positive = torch.nonzero(truth, as_tuple=False).flatten()
        hits.append(bool(positive.numel() and torch.isin(predicted, positive).any()))
    return round(sum(hits) / max(1, len(hits)), 4)


def binary_auc(scores: Tensor, targets: Tensor) -> float | None:
    positives = scores[targets == 1]
    negatives = scores[targets == 0]
    if not len(positives) or not len(negatives):
        return None
    comparisons = (positives[:, None] > negatives[None, :]).float()
    ties = (positives[:, None] == negatives[None, :]).float() * 0.5
    return round(float((comparisons + ties).mean()), 4)


def count_supervision(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    totals: Counter[str] = Counter()
    for row in rows:
        encoded = encode_row_targets(row)
        for head in CATEGORICAL_HEADS:
            totals[head] += int(encoded[head].item() != IGNORE_INDEX)
        for head in MULTILABEL_HEADS:
            totals[head] += int(bool(encoded[f"{head}_valid"].item()))
        totals[OOD_HEAD] += int(encoded[OOD_HEAD].item() >= 0)
    return dict(totals)
