from __future__ import annotations

import torch

from audio_intelligence import (
    DEFAULT_HEAD_CLASSES,
    IGNORE_INDEX,
    AudioIntelligenceHeads,
    encode_row_targets,
    full_song_windows,
    masked_multitask_loss,
    split_singer_disjoint,
)


def test_all_independent_heads_share_one_embedding() -> None:
    model = AudioIntelligenceHeads(dropout=0)
    outputs = model(torch.randn(3, 128))
    assert set(outputs) == set(DEFAULT_HEAD_CLASSES)
    assert outputs["language"].shape == (3, 3)
    assert outputs["genre"].shape == (3, 10)
    assert outputs["in_distribution"].shape == (3, 1)


def test_partial_labels_are_masked_without_inventing_targets() -> None:
    hindi_only = encode_row_targets({"language": "Hindi"})
    assert hindi_only["language"].item() == 0
    assert hindi_only["singing_speech"].item() == IGNORE_INDEX
    assert not hindi_only["genre_valid"].item()

    model = AudioIntelligenceHeads(dropout=0)
    logits = model(torch.randn(2, 128))
    targets = {key: torch.stack([value, value]) for key, value in hindi_only.items()}
    loss, details = masked_multitask_loss(logits, targets)
    assert loss.item() > 0
    assert set(details) == {"language"}


def test_full_song_windows_cover_the_decoded_tail() -> None:
    waveform = torch.randn(1, 48_000 * 13 + 123)
    windows = full_song_windows(waveform, 48_000, clip_seconds=6)
    assert windows.shape == (3, 2, 48_000 * 6)
    # The last non-padding sample is retained in the final window.
    assert torch.isclose(windows[2, 0, 48_000 + 122], waveform[0, -1] / max(1.0, float(waveform[:, 48_000 * 12 :].abs().max())))


def test_split_is_singer_disjoint() -> None:
    rows = [
        {"audio_path": f"clip_{index}.wav", "language": "Hindi", "singer_id": f"singer_{index // 2}"}
        for index in range(20)
    ]
    training, validation = split_singer_disjoint(rows, 0.2, 5070)
    train_singers = {row["singer_id"] for row in training}
    validation_singers = {row["singer_id"] for row in validation}
    assert validation
    assert train_singers.isdisjoint(validation_singers)

