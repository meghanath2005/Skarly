"""Train Skarly's calibrated multi-head intelligence model on ACE-Step features."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import random
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

import torch
import torchaudio
from torch import Tensor
from torch.utils.data import DataLoader, Dataset, WeightedRandomSampler

from audio_intelligence import (
    CATEGORICAL_HEADS,
    CLIP_SECONDS,
    DEFAULT_HEAD_CLASSES,
    IGNORE_INDEX,
    MULTILABEL_HEADS,
    OOD_HEAD,
    SAMPLE_RATE,
    AceStepVaeEncoder,
    AudioIntelligenceHeads,
    augment_audio,
    binary_auc,
    classification_metrics,
    count_supervision,
    encode_row_targets,
    encoder_fingerprint,
    fit_temperature,
    fixed_audio_window,
    genre_top_three_accuracy,
    masked_multitask_loss,
    multilabel_metrics,
    singer_group_id,
    split_singer_disjoint,
)


CREATOR_SOURCE = "creator_opt_in_vocal"
MIN_CREATOR_GENRE_EXAMPLES = 50
MIN_CREATOR_GENRE_CLASSES = 3
MIN_CREATOR_EXAMPLES_PER_GENRE = 5


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def audio_inventory_sha256(rows: Sequence[Mapping[str, Any]]) -> str:
    digest = hashlib.sha256()
    for row in rows:
        path = Path(str(row.get("audio_path") or "")).resolve()
        digest.update(str(path).encode("utf-8"))
        digest.update(str(path.stat().st_size if path.is_file() else -1).encode("ascii"))
    return digest.hexdigest()


def read_manifests(paths: Sequence[Path], *, limit: int | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for manifest_path in paths:
        with manifest_path.open("r", encoding="utf-8-sig") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                row = json.loads(line)
                audio_path = Path(str(row.get("audio_path") or ""))
                if not audio_path.is_file():
                    continue
                if not bool(row.get("rights_confirmed")):
                    raise ValueError(f"{manifest_path}:{line_number} lacks rights_confirmed=true")
                if not any(
                    row.get(field) is not None
                    for field in (
                        "language",
                        "singing_speech",
                        "vocal_type",
                        "vocal_technique",
                        "vocal_techniques",
                        "mood",
                        "moods",
                        "genre",
                        "genres",
                        "tempo_family",
                        "bpm",
                        "melodic_character",
                        "melodic_system",
                        "in_distribution",
                    )
                ):
                    continue
                normalized_row = {**row, "audio_path": str(audio_path.resolve())}
                source = str(normalized_row.get("source") or "").strip().lower()
                # Dataset-role supervision is narrow and explicit: FLEURS is
                # spoken language data; MMGenre is generated/song audio.  This
                # trains only the singing-vs-speaking routing head and does not
                # reuse either dataset for vocal technique, mood, or Hindi
                # producer-style claims.
                if not normalized_row.get("singing_speech"):
                    if source == "google_fleurs_cc_by":
                        normalized_row["singing_speech"] = "speaking"
                        normalized_row["singing_speech_label_origin"] = "dataset_role"
                    elif source == "mmgenre_cc_by_4_0":
                        normalized_row["singing_speech"] = "singing"
                        normalized_row["singing_speech_label_origin"] = "dataset_role"
                if normalized_row.get("in_distribution") is None:
                    normalized_row["in_distribution"] = True
                    normalized_row["distribution_label_origin"] = "rights_reviewed_training_scope"
                encoded = encode_row_targets(normalized_row)
                has_supervision = any(int(encoded[head]) != IGNORE_INDEX for head in CATEGORICAL_HEADS)
                has_supervision = has_supervision or any(bool(encoded[f"{head}_valid"]) for head in MULTILABEL_HEADS)
                has_supervision = has_supervision or float(encoded[OOD_HEAD]) >= 0
                # Broad research datasets often contain labels outside
                # Skarly's reviewed ten-style taxonomy.  Skip them instead of
                # silently forcing an incorrect product genre.
                if not has_supervision:
                    continue
                rows.append(normalized_row)
                if limit and len(rows) >= limit:
                    return rows
    if not rows:
        raise ValueError("No readable, rights-confirmed, labelled audio was found in the manifests")
    return rows


def genre_release_gate(rows: Sequence[Mapping[str, Any]]) -> tuple[bool, str]:
    counts: Counter[str] = Counter()
    for row in rows:
        if str(row.get("source") or "").strip().lower() != CREATOR_SOURCE:
            continue
        targets = encode_row_targets(row)
        for index in torch.nonzero(targets["genre"], as_tuple=False).flatten().tolist():
            counts[DEFAULT_HEAD_CLASSES["genre"][index]] += 1
    total = sum(counts.values())
    if total < MIN_CREATOR_GENRE_EXAMPLES:
        return False, f"need {MIN_CREATOR_GENRE_EXAMPLES} creator-confirmed genre labels; found {total}"
    if len(counts) < MIN_CREATOR_GENRE_CLASSES:
        return False, f"need {MIN_CREATOR_GENRE_CLASSES} creator-confirmed genres; found {len(counts)}"
    sparse = sorted(label for label, count in counts.items() if count < MIN_CREATOR_EXAMPLES_PER_GENRE)
    if sparse:
        return False, f"need {MIN_CREATOR_EXAMPLES_PER_GENRE} examples per creator genre; sparse: {', '.join(sparse)}"
    return True, "creator-confirmed genre coverage passed; grouped metrics still require human release review"


class IntelligenceDataset(Dataset[tuple[Tensor, dict[str, Tensor]]]):
    def __init__(self, rows: Sequence[dict[str, Any]], *, augment: bool) -> None:
        self.rows = list(rows)
        self.augment = augment

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, index: int) -> tuple[Tensor, dict[str, Tensor]]:
        row = self.rows[index]
        waveform, rate = torchaudio.load(row["audio_path"])
        waveform = fixed_audio_window(waveform, rate, random_crop=self.augment)
        if self.augment:
            waveform = augment_audio(waveform)
        return waveform, encode_row_targets(row)


class EmbeddingDataset(Dataset[tuple[Tensor, dict[str, Tensor]]]):
    def __init__(self, items: Sequence[tuple[Tensor, dict[str, Tensor]]]) -> None:
        self.items = list(items)

    def __len__(self) -> int:
        return len(self.items)

    def __getitem__(self, index: int) -> tuple[Tensor, dict[str, Tensor]]:
        return self.items[index]


def precompute_embeddings(
    encoder: AceStepVaeEncoder,
    rows: Sequence[dict[str, Any]],
    *,
    device: torch.device,
    batch_size: int,
    augmentation_copies: int,
) -> list[tuple[Tensor, dict[str, Tensor]]]:
    """Encode each clip once per augmentation, then train heads from RAM.

    This keeps the 337 MB frozen encoder out of the optimizer and avoids
    recomputing identical music embeddings during every head-training epoch.
    """
    items: list[tuple[Tensor, dict[str, Tensor]]] = []
    for copy_index in range(augmentation_copies + 1):
        dataset = IntelligenceDataset(rows, augment=copy_index > 0)
        loader = DataLoader(dataset, batch_size=batch_size, shuffle=False, num_workers=0)
        for audio, targets in loader:
            with torch.inference_mode():
                embeddings = encoder(audio.to(device)).cpu()
            for index in range(len(embeddings)):
                items.append(
                    (
                        embeddings[index],
                        {key: value[index].cpu() for key, value in targets.items()},
                    )
                )
    return items


def precompute_synthetic_ood_embeddings(
    encoder: AceStepVaeEncoder,
    *,
    count: int,
    device: torch.device,
    batch_size: int,
    seed: int,
) -> list[tuple[Tensor, dict[str, Tensor]]]:
    """Create obvious invalid-audio negatives without copying third-party audio."""
    generator = torch.Generator().manual_seed(seed)
    samples = SAMPLE_RATE * CLIP_SECONDS
    audio: list[Tensor] = []
    for index in range(max(0, count)):
        kind = index % 5
        if kind == 0:
            waveform = torch.zeros(2, samples)
        elif kind == 1:
            waveform = torch.randn(2, samples, generator=generator) * 0.2
        elif kind == 2:
            waveform = torch.full((2, samples), 0.75 if index % 2 else -0.75)
        elif kind == 3:
            waveform = torch.zeros(2, samples)
            positions = torch.randint(0, samples, (64,), generator=generator)
            waveform[:, positions] = torch.randn(2, 64, generator=generator).sign()
        else:
            alternating = torch.ones(samples)
            alternating[1::2] = -1
            waveform = alternating.repeat(2, 1) * 0.4
        audio.append(waveform)
    items: list[tuple[Tensor, dict[str, Tensor]]] = []
    for start in range(0, len(audio), max(1, batch_size)):
        batch = torch.stack(audio[start : start + batch_size]).to(device)
        with torch.inference_mode():
            embeddings = encoder(batch).cpu()
        for embedding in embeddings:
            targets = encode_row_targets({"in_distribution": False})
            items.append((embedding, targets))
    return items


def row_sampling_weights(rows: Sequence[Mapping[str, Any]], creator_weight: float) -> list[float]:
    label_counts: Counter[str] = Counter()
    row_keys: list[list[str]] = []
    for row in rows:
        targets = encode_row_targets(row)
        keys: list[str] = []
        for head in CATEGORICAL_HEADS:
            index = int(targets[head])
            if index != IGNORE_INDEX:
                keys.append(f"{head}:{index}")
        for head in MULTILABEL_HEADS:
            for index in torch.nonzero(targets[head], as_tuple=False).flatten().tolist():
                keys.append(f"{head}:{index}")
        if float(targets[OOD_HEAD]) >= 0:
            keys.append(f"{OOD_HEAD}:{int(float(targets[OOD_HEAD]))}")
        row_keys.append(keys)
        label_counts.update(keys)
    weights: list[float] = []
    for row, keys in zip(rows, row_keys):
        balance = max((1.0 / label_counts[key] for key in keys), default=1.0)
        feedback = creator_weight if str(row.get("source") or "").strip().lower() == CREATOR_SOURCE else 1.0
        weights.append(balance * feedback)
    average = sum(weights) / max(1, len(weights))
    return [value / max(1e-9, average) for value in weights]


def move_targets(targets: Mapping[str, Tensor], device: torch.device) -> dict[str, Tensor]:
    return {key: value.to(device) for key, value in targets.items()}


def append_head_batches(
    collected: dict[str, dict[str, list[Tensor]]], logits: Mapping[str, Tensor], targets: Mapping[str, Tensor]
) -> None:
    for head in CATEGORICAL_HEADS:
        valid = targets[head] != IGNORE_INDEX
        if valid.any():
            collected[head]["logits"].append(logits[head][valid].detach().cpu())
            collected[head]["targets"].append(targets[head][valid].detach().cpu())
    for head in MULTILABEL_HEADS:
        valid = targets[f"{head}_valid"].bool()
        if valid.any():
            collected[head]["logits"].append(logits[head][valid].detach().cpu())
            collected[head]["targets"].append(targets[head][valid].detach().cpu())
    valid = targets[OOD_HEAD] >= 0
    if valid.any():
        collected[OOD_HEAD]["logits"].append(logits[OOD_HEAD].squeeze(1)[valid].detach().cpu())
        collected[OOD_HEAD]["targets"].append(targets[OOD_HEAD][valid].detach().cpu())


def metrics_from_batches(collected: Mapping[str, Mapping[str, list[Tensor]]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for head in CATEGORICAL_HEADS:
        if collected[head]["logits"]:
            logits = torch.cat(collected[head]["logits"])
            targets = torch.cat(collected[head]["targets"])
            result[head] = classification_metrics(logits, targets, DEFAULT_HEAD_CLASSES[head])
    for head in MULTILABEL_HEADS:
        if collected[head]["logits"]:
            logits = torch.cat(collected[head]["logits"])
            targets = torch.cat(collected[head]["targets"])
            result[head] = multilabel_metrics(logits, targets, DEFAULT_HEAD_CLASSES[head])
            if head == "genre":
                result[head]["top_three_accuracy"] = genre_top_three_accuracy(logits, targets)
    if collected[OOD_HEAD]["logits"]:
        logits = torch.cat(collected[OOD_HEAD]["logits"])
        targets = torch.cat(collected[OOD_HEAD]["targets"]).long()
        predictions = (torch.sigmoid(logits) >= 0.5).long()
        result[OOD_HEAD] = {
            "accuracy": round(float((predictions == targets).float().mean()), 4),
            "auc": binary_auc(torch.sigmoid(logits), targets),
            "support": int(len(targets)),
        }
    return result


def empty_collection() -> dict[str, dict[str, list[Tensor]]]:
    return {head: {"logits": [], "targets": []} for head in (*CATEGORICAL_HEADS, *MULTILABEL_HEADS, OOD_HEAD)}


def run_epoch(
    heads: AudioIntelligenceHeads,
    loader: DataLoader,
    optimizer: torch.optim.Optimizer | None,
    device: torch.device,
) -> tuple[dict[str, Any], dict[str, dict[str, list[Tensor]]]]:
    training = optimizer is not None
    heads.train(training)
    collected = empty_collection()
    loss_total = 0.0
    sample_total = 0
    head_loss_total: Counter[str] = Counter()
    for embeddings, raw_targets in loader:
        targets = move_targets(raw_targets, device)
        with torch.set_grad_enabled(training):
            logits = heads(embeddings.to(device))
            loss, head_losses = masked_multitask_loss(logits, targets)
            if training:
                optimizer.zero_grad(set_to_none=True)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(heads.parameters(), 2.0)
                optimizer.step()
        batch_size = int(embeddings.shape[0])
        sample_total += batch_size
        loss_total += float(loss.detach()) * batch_size
        for head, value in head_losses.items():
            head_loss_total[head] += value * batch_size
        append_head_batches(collected, logits, targets)
    summary = metrics_from_batches(collected)
    summary["loss"] = round(loss_total / max(1, sample_total), 6)
    summary["head_loss"] = {head: round(value / max(1, sample_total), 6) for head, value in head_loss_total.items()}
    summary["samples"] = sample_total
    return summary, collected


def metric_score(metrics: Mapping[str, Any]) -> float:
    values: list[float] = []
    for head in CATEGORICAL_HEADS:
        if head in metrics:
            values.append(float(metrics[head]["accuracy"]))
    if "genre" in metrics:
        values.append(float(metrics["genre"].get("top_three_accuracy", 0)))
    if OOD_HEAD in metrics:
        values.append(float(metrics[OOD_HEAD].get("auc") or metrics[OOD_HEAD].get("accuracy") or 0))
    return sum(values) / max(1, len(values))


def calibrated_temperatures(collected: Mapping[str, Mapping[str, list[Tensor]]]) -> dict[str, float]:
    temperatures: dict[str, float] = {}
    for head in CATEGORICAL_HEADS:
        if collected[head]["logits"]:
            temperatures[head] = fit_temperature(
                torch.cat(collected[head]["logits"]), torch.cat(collected[head]["targets"])
            )
    for head in MULTILABEL_HEADS:
        if collected[head]["logits"]:
            temperatures[head] = fit_temperature(
                torch.cat(collected[head]["logits"]),
                torch.cat(collected[head]["targets"]),
                multilabel=True,
            )
    if collected[OOD_HEAD]["logits"]:
        temperatures[OOD_HEAD] = fit_temperature(
            torch.cat(collected[OOD_HEAD]["logits"]).unsqueeze(1),
            torch.cat(collected[OOD_HEAD]["targets"]).unsqueeze(1),
            multilabel=True,
        )
    return temperatures


def verify_cuda(device: torch.device) -> dict[str, Any]:
    if device.type != "cuda":
        return {"cuda": False, "device": str(device)}
    capability = torch.cuda.get_device_capability(0)
    architectures = torch.cuda.get_arch_list()
    if capability < (12, 0) or "sm_120" not in architectures:
        raise RuntimeError(f"Skarly intelligence training requires Blackwell sm_120; got {capability}, {architectures}")
    return {
        "cuda": True,
        "device": torch.cuda.get_device_name(0),
        "capability": f"{capability[0]}.{capability[1]}",
        "torch": torch.__version__,
        "cuda_runtime": torch.version.cuda,
        "architectures": architectures,
    }


def parse_args() -> argparse.Namespace:
    default_encoder = os.getenv(
        "SKARLY_AUDIO_ENCODER_PATH",
        r"D:\intern\skarly-ai-repos\ACE-Step-1.5\checkpoints\vae",
    )
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, action="append", required=True)
    parser.add_argument("--encoder", type=Path, default=Path(default_encoder))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--epochs", type=int, default=12)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--learning-rate", type=float, default=0.0005)
    parser.add_argument("--validation-fraction", type=float, default=0.15)
    parser.add_argument("--seed", type=int, default=5070)
    parser.add_argument("--num-workers", type=int, default=0)
    parser.add_argument("--creator-feedback-weight", type=float, default=3.0)
    parser.add_argument("--augmentation-copies", type=int, default=1)
    parser.add_argument("--embedding-cache", type=Path)
    parser.add_argument("--synthetic-ood-ratio", type=float, default=0.20)
    parser.add_argument("--smoke-limit", type=int)
    parser.add_argument("--approve-genre", action="store_true")
    parser.add_argument("--require-cuda", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    random.seed(args.seed)
    torch.manual_seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if args.require_cuda and device.type != "cuda":
        raise RuntimeError("CUDA is required for Skarly audio-intelligence training")
    cuda = verify_cuda(device)
    rows = read_manifests(args.manifest, limit=args.smoke_limit)
    training_rows, validation_rows = split_singer_disjoint(rows, args.validation_fraction, args.seed)
    supervision = count_supervision(training_rows)
    genre_approved = False
    genre_approval_note = "genre routing remains confirmation-first"
    if args.approve_genre:
        genre_approved, genre_approval_note = genre_release_gate(rows)
        if not genre_approved:
            raise ValueError(f"Cannot approve genre head: {genre_approval_note}")

    print(json.dumps({
        "cuda": cuda,
        "rows": len(rows),
        "training_rows": len(training_rows),
        "validation_rows": len(validation_rows),
        "training_groups": len({singer_group_id(row) for row in training_rows}),
        "validation_groups": len({singer_group_id(row) for row in validation_rows}),
        "supervision": supervision,
    }))

    encoder = AceStepVaeEncoder(args.encoder).to_device(device)
    heads = AudioIntelligenceHeads().to(device)
    if args.dry_run:
        smoke_loader = DataLoader(IntelligenceDataset(training_rows, augment=True), batch_size=args.batch_size)
        audio, targets = next(iter(smoke_loader))
        with torch.inference_mode():
            logits = heads(encoder(audio.to(device)))
        print(json.dumps({
            "dry_run": True,
            "audio_shape": list(audio.shape),
            "embedding_dim": heads.shared_projection[1].in_features,
            "head_shapes": {head: list(value.shape) for head, value in logits.items()},
            "label_keys": sorted(targets),
            "encoder_fingerprint": encoder_fingerprint(args.encoder),
        }))
        return

    manifest_metadata = [
        {"path": str(path.resolve()), "sha256": sha256_file(path)} for path in args.manifest
    ]
    encoder_sha256 = encoder_fingerprint(args.encoder)
    cache_path = args.embedding_cache or args.output.with_suffix(".embeddings.pt")
    cache_identity = {
        "format": "skarly_audio_intelligence_embeddings_v1",
        "encoder_sha256": encoder_sha256,
        "manifest_sha256": [item["sha256"] for item in manifest_metadata],
        "seed": args.seed,
        "augmentation_copies": max(0, args.augmentation_copies),
        "training_rows": len(training_rows),
        "validation_rows": len(validation_rows),
        "audio_inventory_sha256": audio_inventory_sha256([*training_rows, *validation_rows]),
    }
    cached = torch.load(cache_path, map_location="cpu", weights_only=False) if cache_path.is_file() else None
    cached_identity = cached.get("identity") if isinstance(cached, dict) else None
    legacy_cache_match = bool(
        isinstance(cached_identity, dict)
        and cached_identity.get("encoder_sha256") == encoder_sha256
        and cached_identity.get("seed") == args.seed
        and cached_identity.get("augmentation_copies") == max(0, args.augmentation_copies)
        and cached_identity.get("training_rows") == len(training_rows)
        and cached_identity.get("validation_rows") == len(validation_rows)
        and "audio_inventory_sha256" not in cached_identity
    )
    if isinstance(cached, dict) and (cached_identity == cache_identity or legacy_cache_match):
        cached_train_items = cached["train_items"]
        cached_validation_items = cached["validation_items"]
        repeated_training_rows = list(training_rows) * (max(0, args.augmentation_copies) + 1)
        train_items = [
            (embedding, encode_row_targets(row))
            for (embedding, _old_targets), row in zip(cached_train_items, repeated_training_rows)
        ]
        validation_items = [
            (embedding, encode_row_targets(row))
            for (embedding, _old_targets), row in zip(cached_validation_items, validation_rows)
        ]
        if legacy_cache_match:
            torch.save({"identity": cache_identity, "train_items": cached_train_items, "validation_items": cached_validation_items}, cache_path)
        print(json.dumps({"embedding_cache": str(cache_path), "status": "hit", "training_embeddings": len(train_items)}))
    else:
        train_items = precompute_embeddings(
            encoder,
            training_rows,
            device=device,
            batch_size=args.batch_size,
            augmentation_copies=max(0, args.augmentation_copies),
        )
        validation_items = precompute_embeddings(
            encoder,
            validation_rows,
            device=device,
            batch_size=args.batch_size,
            augmentation_copies=0,
        ) if validation_rows else []
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        torch.save({"identity": cache_identity, "train_items": train_items, "validation_items": validation_items}, cache_path)
        print(json.dumps({"embedding_cache": str(cache_path), "status": "written", "training_embeddings": len(train_items)}))
    synthetic_train_count = round(len(training_rows) * max(0.0, args.synthetic_ood_ratio))
    synthetic_validation_count = round(len(validation_rows) * max(0.0, args.synthetic_ood_ratio))
    train_items.extend(
        precompute_synthetic_ood_embeddings(
            encoder,
            count=synthetic_train_count,
            device=device,
            batch_size=args.batch_size,
            seed=args.seed + 101,
        )
    )
    validation_items.extend(
        precompute_synthetic_ood_embeddings(
            encoder,
            count=synthetic_validation_count,
            device=device,
            batch_size=args.batch_size,
            seed=args.seed + 202,
        )
    )
    train_dataset = EmbeddingDataset(train_items)
    base_weights = row_sampling_weights(training_rows, args.creator_feedback_weight)
    feature_weights = base_weights * (max(0, args.augmentation_copies) + 1) + [1.0] * synthetic_train_count
    sampler = WeightedRandomSampler(feature_weights, num_samples=len(train_dataset), replacement=True)
    train_loader = DataLoader(train_dataset, batch_size=max(8, args.batch_size * 4), sampler=sampler)
    validation_loader = DataLoader(EmbeddingDataset(validation_items), batch_size=max(8, args.batch_size * 4)) if validation_items else None

    optimizer = torch.optim.AdamW(heads.parameters(), lr=args.learning_rate, weight_decay=0.0001)
    best_state = copy.deepcopy(heads.state_dict())
    best_metrics: dict[str, Any] = {}
    best_collection = empty_collection()
    best_score = -1.0
    best_epoch = 0
    history: list[dict[str, Any]] = []
    for epoch in range(1, args.epochs + 1):
        train_metrics, _ = run_epoch(heads, train_loader, optimizer, device)
        if validation_loader:
            validation_metrics, validation_collection = run_epoch(heads, validation_loader, None, device)
        else:
            validation_metrics, validation_collection = train_metrics, empty_collection()
        score = metric_score(validation_metrics)
        record = {"epoch": epoch, "train": train_metrics, "validation": validation_metrics, "selection_score": round(score, 5)}
        history.append(record)
        print(json.dumps(record))
        if score >= best_score:
            best_score = score
            best_epoch = epoch
            best_state = copy.deepcopy(heads.state_dict())
            best_metrics = copy.deepcopy(validation_metrics)
            best_collection = validation_collection

    temperatures = calibrated_temperatures(best_collection)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    checkpoint = {
        "format": "skarly_audio_intelligence_v2",
        "architecture": "frozen_acestep_vae_shared_encoder_with_independent_heads",
        "encoder": {
            "type": "ACE-Step-1.5 AutoencoderOobleck",
            "path": str(args.encoder.resolve()),
            "fingerprint_sha256": encoder_sha256,
            "sample_rate": 48_000,
            "clip_seconds": CLIP_SECONDS,
            "embedding_dim": 128,
            "frozen": True,
        },
        "head_classes": {head: list(labels) for head, labels in DEFAULT_HEAD_CLASSES.items()},
        "head_state": best_state,
        "trained_heads": {head: count > 0 for head, count in supervision.items()},
        "supervision_counts": supervision,
        "temperatures": temperatures,
        "multilabel_thresholds": {head: 0.5 for head in MULTILABEL_HEADS},
        "low_confidence_thresholds": {"language": 0.70, "genre": 0.78, "default": 0.65, "in_distribution": 0.60},
        "genre_approved": genre_approved,
        "genre_approval_note": genre_approval_note,
        "seed": args.seed,
        "manifests": manifest_metadata,
        "dataset_versions": sorted({str(row.get("dataset_version") or row.get("source") or "unknown") for row in rows}),
        "training_examples": len(training_rows),
        "validation_examples": len(validation_rows),
        "training_singer_groups": len({singer_group_id(row) for row in training_rows}),
        "validation_singer_groups": len({singer_group_id(row) for row in validation_rows}),
        "augmentation": ["safe_speed", "safe_pitch", "room", "noise", "compression", "phone_microphone", "synthetic_ood"],
        "augmentation_copies": max(0, args.augmentation_copies),
        "training_embeddings": len(train_items),
        "synthetic_ood_training_examples": synthetic_train_count,
        "synthetic_ood_validation_examples": synthetic_validation_count,
        "best_epoch": best_epoch,
        "best_validation": best_metrics,
        "history": history,
        "cuda": cuda,
    }
    torch.save(checkpoint, args.output)
    print(json.dumps({
        "checkpoint": str(args.output.resolve()),
        "best_epoch": best_epoch,
        "best_validation": best_metrics,
        "temperatures": temperatures,
        "genre_approved": genre_approved,
    }))


if __name__ == "__main__":
    main()
