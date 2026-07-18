"""Train Skarly's small CUDA-friendly CNN for language and genre routing."""

from __future__ import annotations

import argparse
import copy
import json
import random
import re
from collections import Counter
from pathlib import Path
from typing import Any

import torch
from torch import Tensor, nn
from torch.nn import functional as functional
from torch.utils.data import DataLoader, Dataset, WeightedRandomSampler
import torchaudio


SAMPLE_RATE = 16_000
CLIP_SECONDS = 6
N_MELS = 64
IGNORE_INDEX = -100
CREATOR_FEEDBACK_SOURCE = "creator_opt_in_vocal"
MIN_APPROVED_GENRE_FEEDBACK_EXAMPLES = 50
MIN_APPROVED_GENRE_FEEDBACK_PER_CLASS = 5


class MelCnn(nn.Module):
    """Compact shared CNN with separate language and optional genre heads."""

    def __init__(self, language_count: int, genre_count: int) -> None:
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv2d(1, 24, kernel_size=5, padding=2), nn.BatchNorm2d(24), nn.GELU(), nn.MaxPool2d(2),
            nn.Conv2d(24, 48, kernel_size=3, padding=1), nn.BatchNorm2d(48), nn.GELU(), nn.MaxPool2d(2),
            nn.Conv2d(48, 96, kernel_size=3, padding=1), nn.BatchNorm2d(96), nn.GELU(),
            nn.AdaptiveAvgPool2d((1, 1)),
        )
        self.embedding = nn.Sequential(nn.Flatten(), nn.Linear(96, 96), nn.GELU(), nn.Dropout(0.15))
        self.language_head = nn.Linear(96, language_count)
        self.genre_head = nn.Linear(96, genre_count) if genre_count else None

    def forward(self, mels: Tensor) -> tuple[Tensor, Tensor | None]:
        embedding = self.embedding(self.features(mels))
        return self.language_head(embedding), self.genre_head(embedding) if self.genre_head else None


def read_manifest(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            audio_path = Path(str(row.get("audio_path") or ""))
            language = str(row.get("language") or "").strip() or None
            genre = str(row.get("genre") or "").strip() or None
            if not audio_path.is_file() or (not language and not genre):
                continue
            rows.append({**row, "audio_path": str(audio_path), "language": language, "genre": genre})
    if not rows:
        raise ValueError("The manifest contains no readable audio with a language or genre label.")
    return rows


def sample_group_id(row: dict[str, Any]) -> str:
    """Keep clips from one original recording on the same side of validation."""
    source = str(row.get("source") or "unknown").strip() or "unknown"
    explicit = str(row.get("source_group") or row.get("recording_id") or "").strip()
    if explicit:
        return f"{source}|{explicit}"
    path = Path(str(row.get("audio_path") or ""))
    # MMGenre stores multiple numbered excerpts from one generated song as
    # ``..._000_01.wav``, ``..._000_02.wav``.  A file-level split leaks that
    # song's timbre and arrangement into validation.
    normalized_source = source.lower()
    # Only MMGenre uses its final numeric component as a segment index.  FLEURS
    # clip IDs are themselves numeric, so stripping them would collapse an
    # entire language corpus into one validation group.
    stem = re.sub(r"_\d+$", "", path.stem) if "mmgenre" in normalized_source else path.stem
    return f"{source}|{stem}"


def row_label_keys(row: dict[str, Any]) -> tuple[str, ...]:
    """Return every supervised head label carried by an example."""
    labels: list[str] = []
    if row.get("language"):
        labels.append(f"language:{row['language']}")
    if row.get("genre"):
        labels.append(f"genre:{row['genre']}")
    return tuple(labels)


def training_sample_weights(rows: list[dict[str, Any]], creator_feedback_weight: float) -> list[float]:
    """Give reviewed creator examples a measured boost during training only.

    The bootstrap manifests are useful for language ID, but a few high-quality
    Hindi/English creator labels would otherwise be almost invisible beside
    hundreds of generic benchmark clips.  Validation remains unweighted, so a
    feedback-heavy batch cannot inflate the checkpoint's reported accuracy.
    """
    if creator_feedback_weight < 1.0:
        raise ValueError("creator_feedback_weight must be at least 1.0")
    return [
        float(creator_feedback_weight)
        if str(row.get("source") or "").strip().lower() == CREATOR_FEEDBACK_SOURCE
        else 1.0
        for row in rows
    ]


def can_approve_genre_checkpoint(rows: list[dict[str, Any]]) -> tuple[bool, str]:
    """Require meaningful creator-confirmed coverage before auto-genre routing.

    Generic benchmark music can bootstrap a conservative prior, but cannot make
    the product claim that it recognises Hindi producer styles.  Approval is a
    deliberate release decision backed by independently recorded, creator-
    confirmed examples.
    """
    genre_counts = Counter(
        str(row.get("genre") or "").strip()
        for row in rows
        if str(row.get("source") or "").strip().lower() == CREATOR_FEEDBACK_SOURCE
        and str(row.get("genre") or "").strip()
    )
    total = sum(genre_counts.values())
    if total < MIN_APPROVED_GENRE_FEEDBACK_EXAMPLES:
        return False, f"need at least {MIN_APPROVED_GENRE_FEEDBACK_EXAMPLES} creator-confirmed genre examples; found {total}"
    if len(genre_counts) < 3:
        return False, "need creator-confirmed examples for at least three genres"
    sparse = sorted(label for label, count in genre_counts.items() if count < MIN_APPROVED_GENRE_FEEDBACK_PER_CLASS)
    if sparse:
        return False, f"need at least {MIN_APPROVED_GENRE_FEEDBACK_PER_CLASS} examples per confirmed genre; sparse: {', '.join(sparse[:5])}"
    return True, "creator-confirmed genre coverage is sufficient for manual metric review"


def split_rows(rows: list[dict[str, Any]], validation_fraction: float, seed: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Create a grouped multi-task split without leaking a recording.

    Creator feedback is labelled for both language and genre.  It must be
    balanced for both heads, while every clip from a recording remains entirely
    in training or validation.  The old one-label split could validate a genre
    only by accident and could produce misleading accuracy after feedback was
    added.
    """
    if len(rows) < 10 or validation_fraction <= 0:
        return rows[:], []

    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(sample_group_id(row), []).append(row)

    groups_for_label: dict[str, set[str]] = {}
    row_counts_for_label: Counter[str] = Counter()
    rows_for_group_label: dict[str, Counter[str]] = {}
    for group_id, group_rows in grouped.items():
        label_counts: Counter[str] = Counter()
        for row in group_rows:
            for label in row_label_keys(row):
                label_counts[label] += 1
                row_counts_for_label[label] += 1
                groups_for_label.setdefault(label, set()).add(group_id)
        rows_for_group_label[group_id] = label_counts

    rng = random.Random(seed)
    target_rows_for_label = {
        label: max(1, round(total * validation_fraction)) if len(groups_for_label[label]) > 1 else 0
        for label, total in row_counts_for_label.items()
    }
    candidate_groups_for_label: dict[str, list[str]] = {}
    for label, group_ids in groups_for_label.items():
        candidates = list(group_ids)
        rng.shuffle(candidates)
        candidate_groups_for_label[label] = candidates

    validation_groups: set[str] = set()
    validation_counts: Counter[str] = Counter()
    # Resolve rare labels first so a multi-labelled feedback recording cannot
    # accidentally consume a rare label's only training group.
    ordered_labels = sorted(groups_for_label, key=lambda label: (len(groups_for_label[label]), label))
    for label in ordered_labels:
        target = target_rows_for_label[label]
        if target <= 0:
            continue
        for group_id in candidate_groups_for_label[label]:
            if validation_counts[label] >= target:
                break
            if group_id in validation_groups:
                continue
            group_labels = rows_for_group_label[group_id]
            # Every label represented by this group must retain at least one
            # whole recording for training after this group enters validation.
            preserves_training_group = all(
                bool(groups_for_label[group_label] - validation_groups - {group_id})
                for group_label in group_labels
            )
            if not preserves_training_group:
                continue
            validation_groups.add(group_id)
            validation_counts.update(group_labels)

    validation_rows = [row for row in rows if sample_group_id(row) in validation_groups]
    training_rows = [row for row in rows if sample_group_id(row) not in validation_groups]
    return training_rows, validation_rows


class AudioDataset(Dataset[tuple[Tensor, Tensor, Tensor]]):
    def __init__(self, rows: list[dict[str, Any]], language_to_index: dict[str, int], genre_to_index: dict[str, int], augment: bool) -> None:
        self.rows = rows
        self.language_to_index = language_to_index
        self.genre_to_index = genre_to_index
        self.augment = augment
        self.mel = torchaudio.transforms.MelSpectrogram(sample_rate=SAMPLE_RATE, n_fft=1024, hop_length=160, n_mels=N_MELS)

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, index: int) -> tuple[Tensor, Tensor, Tensor]:
        row = self.rows[index]
        waveform, rate = torchaudio.load(row["audio_path"])
        waveform = waveform.mean(dim=0, keepdim=True)
        if rate != SAMPLE_RATE:
            waveform = torchaudio.functional.resample(waveform, rate, SAMPLE_RATE)
        target_samples = SAMPLE_RATE * CLIP_SECONDS
        if waveform.shape[1] > target_samples:
            if self.augment:
                start = random.randint(0, waveform.shape[1] - target_samples)
            else:
                start = max(0, (waveform.shape[1] - target_samples) // 2)
            waveform = waveform[:, start:start + target_samples]
        else:
            waveform = functional.pad(waveform, (0, target_samples - waveform.shape[1]))
        if self.augment:
            waveform = waveform * random.uniform(0.85, 1.15)
        # MelSpectrogram keeps the mono channel dimension. DataLoader adds the
        # batch dimension, yielding [batch, 1, mel_bins, frames] for Conv2d.
        mel = torch.log(self.mel(waveform).clamp_min(1e-5))
        language = torch.tensor(self.language_to_index.get(row["language"], IGNORE_INDEX), dtype=torch.long)
        genre = torch.tensor(self.genre_to_index.get(row["genre"], IGNORE_INDEX), dtype=torch.long)
        return mel, language, genre


def accuracy(logits: Tensor | None, targets: Tensor) -> tuple[int, int]:
    if logits is None:
        return 0, 0
    valid = targets != IGNORE_INDEX
    if not valid.any():
        return 0, 0
    correct = (logits.argmax(dim=1)[valid] == targets[valid]).sum().item()
    return int(correct), int(valid.sum().item())


def run_epoch(model: MelCnn, loader: DataLoader, optimizer: torch.optim.Optimizer | None, device: torch.device) -> dict[str, float]:
    training = optimizer is not None
    model.train(training)
    totals = Counter()
    for mel, language, genre in loader:
        mel, language, genre = mel.to(device), language.to(device), genre.to(device)
        with torch.set_grad_enabled(training):
            language_logits, genre_logits = model(mel)
            losses: list[Tensor] = []
            if (language != IGNORE_INDEX).any():
                losses.append(functional.cross_entropy(language_logits, language, ignore_index=IGNORE_INDEX))
            if genre_logits is not None and (genre != IGNORE_INDEX).any():
                losses.append(0.75 * functional.cross_entropy(genre_logits, genre, ignore_index=IGNORE_INDEX))
            if not losses:
                continue
            loss = sum(losses)
            if training:
                optimizer.zero_grad(set_to_none=True)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 2.0)
                optimizer.step()
        language_correct, language_total = accuracy(language_logits, language)
        genre_correct, genre_total = accuracy(genre_logits, genre)
        totals.update(loss=float(loss.detach().item()) * len(language), count=len(language), language_correct=language_correct, language_total=language_total, genre_correct=genre_correct, genre_total=genre_total)
    return {
        "loss": totals["loss"] / max(1, totals["count"]),
        "language_accuracy": totals["language_correct"] / max(1, totals["language_total"]),
        "genre_accuracy": totals["genre_correct"] / max(1, totals["genre_total"]),
        "genre_examples": float(totals["genre_total"]),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, action="append", required=True, help="One or more JSONL manifests; language-only and genre-only manifests may be supplied separately.")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--epochs", type=int, default=16)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--learning-rate", type=float, default=0.001)
    parser.add_argument("--validation-fraction", type=float, default=0.15)
    parser.add_argument("--seed", type=int, default=5070)
    parser.add_argument("--num-workers", type=int, default=0)
    parser.add_argument(
        "--creator-feedback-weight",
        type=float,
        default=3.0,
        help="Relative sampling weight for reviewed creator_opt_in_vocal rows during training (validation is never weighted).",
    )
    parser.add_argument(
        "--approve-genre",
        action="store_true",
        help="Mark this checkpoint eligible for automatic full-song genre routing only after creator-feedback coverage is sufficient.",
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    random.seed(args.seed)
    torch.manual_seed(args.seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(json.dumps({"device": str(device), "gpu": torch.cuda.get_device_name(0) if device.type == "cuda" else None}))

    rows: list[dict[str, Any]] = []
    for manifest_path in args.manifest:
        rows.extend(read_manifest(manifest_path))
    genre_approved = False
    genre_approval_note = "genre routing remains confirmation-first"
    if args.approve_genre:
        genre_approved, genre_approval_note = can_approve_genre_checkpoint(rows)
        if not genre_approved:
            raise ValueError(f"Cannot approve genre checkpoint: {genre_approval_note}")
    language_classes = sorted({row["language"] for row in rows if row["language"]})
    genre_classes = sorted({row["genre"] for row in rows if row["genre"]})
    if len(language_classes) < 2:
        raise ValueError("Need at least two language labels (for example Hindi and English).")
    train_rows, validation_rows = split_rows(rows, args.validation_fraction, args.seed)
    if not train_rows:
        train_rows, validation_rows = rows, []
    language_to_index = {name: index for index, name in enumerate(language_classes)}
    genre_to_index = {name: index for index, name in enumerate(genre_classes)}
    train_dataset = AudioDataset(train_rows, language_to_index, genre_to_index, augment=True)
    sample_weights = training_sample_weights(train_rows, args.creator_feedback_weight)
    feedback_examples = sum(
        1
        for row in train_rows
        if str(row.get("source") or "").strip().lower() == CREATOR_FEEDBACK_SOURCE
    )
    sampler = (
        WeightedRandomSampler(sample_weights, num_samples=len(train_dataset), replacement=True)
        if feedback_examples
        else None
    )
    train_loader = DataLoader(
        train_dataset,
        batch_size=args.batch_size,
        shuffle=sampler is None,
        sampler=sampler,
        num_workers=args.num_workers,
        pin_memory=device.type == "cuda",
    )
    validation_loader = DataLoader(AudioDataset(validation_rows, language_to_index, genre_to_index, augment=False), batch_size=args.batch_size, num_workers=args.num_workers) if validation_rows else None
    model = MelCnn(len(language_classes), len(genre_classes)).to(device)
    if args.dry_run:
        mel, language, genre = next(iter(train_loader))
        language_logits, genre_logits = model(mel.to(device))
        print(json.dumps({"samples": len(rows), "languages": language_classes, "genres": genre_classes, "creator_feedback_examples": feedback_examples, "creator_feedback_weight": args.creator_feedback_weight if feedback_examples else 1.0, "genre_approved": genre_approved, "genre_approval_note": genre_approval_note, "language_logits": list(language_logits.shape), "genre_logits": list(genre_logits.shape) if genre_logits is not None else None}))
        return
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate, weight_decay=0.0001)
    history: list[dict[str, Any]] = []
    best_state = copy.deepcopy(model.state_dict())
    best_epoch = 0
    best_metrics: dict[str, float] | None = None
    best_score = -1.0
    for epoch in range(1, args.epochs + 1):
        train_metrics = run_epoch(model, train_loader, optimizer, device)
        validation_metrics = run_epoch(model, validation_loader, None, device) if validation_loader else None
        result = {"epoch": epoch, "train": train_metrics, "validation": validation_metrics}
        history.append(result)
        print(json.dumps(result))
        selection_metrics = validation_metrics or train_metrics
        genre_weight = 0.35 if selection_metrics["genre_examples"] else 0.0
        selection_score = (1.0 - genre_weight) * float(selection_metrics["language_accuracy"]) + genre_weight * float(selection_metrics["genre_accuracy"])
        if selection_score >= best_score:
            best_state = copy.deepcopy(model.state_dict())
            best_epoch = epoch
            best_metrics = dict(selection_metrics)
            best_score = selection_score
    args.output.parent.mkdir(parents=True, exist_ok=True)
    torch.save({
        "format": "skarly_audio_cnn_v1",
        "sample_rate": SAMPLE_RATE,
        "clip_seconds": CLIP_SECONDS,
        "n_mels": N_MELS,
        "language_classes": language_classes,
        "genre_classes": genre_classes,
        "model_state": best_state,
        "history": history,
        "best_epoch": best_epoch,
        "best_validation": best_metrics,
        "training_examples": len(train_rows),
        "validation_examples": len(validation_rows),
        "creator_feedback_examples": feedback_examples,
        "creator_feedback_weight": args.creator_feedback_weight if feedback_examples else 1.0,
        "genre_approved": genre_approved,
        "genre_approval_note": genre_approval_note,
    }, args.output)
    print(json.dumps({"checkpoint": str(args.output), "best_epoch": best_epoch, "best_validation": best_metrics, "training_examples": len(train_rows), "validation_examples": len(validation_rows)}))


if __name__ == "__main__":
    main()
