"""Dependency-free label taxonomy shared by Skarly training and audits."""

from __future__ import annotations

from typing import Iterable, Sequence


CATEGORICAL_HEADS = ("language", "singing_speech", "tempo_family", "melodic_character")
MULTILABEL_HEADS = ("vocal_technique", "mood", "genre")
OOD_HEAD = "in_distribution"

DEFAULT_HEAD_CLASSES: dict[str, tuple[str, ...]] = {
    "language": ("Hindi", "English", "Code-switched"),
    "singing_speech": ("singing", "speaking", "rap", "humming"),
    "vocal_technique": (
        "straight",
        "vibrato",
        "breathy",
        "belting",
        "melismatic",
        "ornamented",
        "spoken",
        "rap",
    ),
    "mood": (
        "romantic",
        "emotional",
        "intimate",
        "devotional",
        "uplifting",
        "energetic",
        "dark",
        "melancholic",
    ),
    "genre": (
        "bollywood_ballad",
        "bollywood_dance_pop",
        "sufi",
        "punjabi",
        "indian_acoustic_indie",
        "western_pop",
        "rock",
        "rnb_urban",
        "electronic",
        "indian_classical_semiclassical",
    ),
    "tempo_family": ("free", "slow", "medium", "fast"),
    "melodic_character": ("indian", "western", "mixed"),
    OOD_HEAD: ("out_of_distribution", "in_distribution"),
}


def normalize_token(value: object) -> str:
    return "_".join(str(value or "").strip().lower().replace("&", " and ").replace("/", " ").split())


def normalize_language(value: object) -> str | None:
    token = normalize_token(value)
    if token in {"hi", "hi_in", "hindi"}:
        return "Hindi"
    if token in {"en", "en_us", "english"}:
        return "English"
    if token in {"hinglish", "code_switched", "code-switched", "code_switch", "hindi_english"}:
        return "Code-switched"
    return None


def normalize_genre(value: object) -> str | None:
    token = normalize_token(value)
    aliases = {
        "bollywood_ballad": "bollywood_ballad",
        "bollywood_romance": "bollywood_ballad",
        "bollywood_dance_pop": "bollywood_dance_pop",
        "bollywood_pop": "bollywood_dance_pop",
        "bollywood_dance": "bollywood_dance_pop",
        "sufi": "sufi",
        "qawwali": "sufi",
        "punjabi": "punjabi",
        "punjabi_pop": "punjabi",
        "indian_acoustic": "indian_acoustic_indie",
        "indian_acoustic_indie": "indian_acoustic_indie",
        "indie_pop": "indian_acoustic_indie",
        "indian_indie": "indian_acoustic_indie",
        "pop": "western_pop",
        "western_pop": "western_pop",
        "rock": "rock",
        "r_and_b": "rnb_urban",
        "rnb": "rnb_urban",
        "rnb_urban": "rnb_urban",
        "electronic": "electronic",
        "edm": "electronic",
        "indian_classical": "indian_classical_semiclassical",
        "semi_classical": "indian_classical_semiclassical",
        "indian_classical_semiclassical": "indian_classical_semiclassical",
    }
    return aliases.get(token)


def normalize_values(value: object, *, mapper=normalize_token) -> list[str]:
    if value is None:
        return []
    values: Iterable[object]
    if isinstance(value, str):
        values = [part for part in value.replace(";", ",").split(",") if part.strip()]
    elif isinstance(value, Sequence):
        values = value
    else:
        values = [value]
    normalized = [mapper(item) for item in values]
    return list(dict.fromkeys(item for item in normalized if item))
