from __future__ import annotations

from typing import Any

from .models import SongGenerateRequest
from .presets import get_default_preset

ORIGINALITY_RULES = [
    "Create an original melody, lyrics, arrangement, and vocal performance.",
    "Do not copy any existing song, melody, lyrics, or artist voice.",
]

BASE_NEGATIVE_RULES = [
    "Do not copy any existing song.",
    "Do not imitate a specific living artist voice.",
    "Avoid random tabla or sitar usage unless requested.",
    "Avoid parody tone, distorted vocals, clipping, silence, and muddy mix.",
]


def build_generation_prompt(request: SongGenerateRequest, preset: dict[str, Any] | None = None) -> dict[str, Any]:
    selected_preset = preset or {}
    fields_set = request.model_fields_set

    language = _field_or_default(request.language, selected_preset.get("language"), "Hindi")
    genre = _explicit_value(request, "genre", selected_preset.get("genre") or "Pop", fields_set)
    production_style = _explicit_value(request, "production_style", selected_preset.get("production_style"), fields_set)
    production_style = production_style or genre
    arrangement_style = _explicit_value(request, "arrangement_style", selected_preset.get("arrangement_style"), fields_set)
    arrangement_style = arrangement_style or _fallback_arrangement(production_style, genre)
    mood_tags = _list_value(request.mood_tags, selected_preset.get("mood_tags"), "mood_tags", fields_set)
    instruments = _list_value(request.instruments, selected_preset.get("instruments"), "instruments", fields_set)
    bpm = _explicit_value(request, "bpm", selected_preset.get("default_bpm"), fields_set)
    bpm = bpm or _midpoint(selected_preset.get("bpm_range")) or 88
    key = _explicit_value(request, "key", _default_key(selected_preset.get("key_suggestions")), fields_set)
    duration_seconds = _explicit_value(request, "duration_seconds", None, fields_set)
    duration_seconds = duration_seconds or _default_duration(selected_preset.get("duration_range"))
    energy = _explicit_value(request, "energy", None, fields_set)
    structure = list(selected_preset.get("structure") or _fallback_structure(production_style))
    mix_direction = selected_preset.get("mix_direction") or _fallback_mix_direction(request)
    if request.vocal_forward_mix and "vocal-forward" not in mix_direction and "vocal forward" not in mix_direction:
        mix_direction = f"vocal-forward, {mix_direction}"

    warnings = _conflict_warnings(production_style, arrangement_style, instruments, energy)

    positive_prompt = _positive_prompt(
        language=language,
        genre=genre,
        production_style=production_style,
        arrangement_style=arrangement_style,
        mood_tags=mood_tags,
        instruments=instruments,
        bpm=int(bpm),
        key=key,
        duration_seconds=int(duration_seconds) if duration_seconds else None,
        structure=structure,
        mix_direction=mix_direction,
        preset=selected_preset,
    )
    negative_prompt = _negative_prompt(selected_preset)

    structured_summary = {
        "language": language,
        "genre": genre,
        "production_style": production_style,
        "arrangement_style": arrangement_style,
        "mood_tags": mood_tags,
        "instruments": instruments,
        "bpm": int(bpm) if bpm is not None else None,
        "key": key,
        "duration_seconds": int(duration_seconds) if duration_seconds is not None else None,
        "structure": structure,
        "mix_direction": mix_direction,
    }
    recommended_settings = {
        "bpm": structured_summary["bpm"],
        "key": key,
        "duration_seconds": structured_summary["duration_seconds"],
        "vocal_forward_mix": request.vocal_forward_mix,
        "ducking_enabled": request.ducking_enabled,
        "vocal_gain_db": request.vocal_gain_db if request.vocal_gain_db is not None else 1.5,
        "backing_gain_db": request.backing_gain_db if request.backing_gain_db is not None else -3.0,
    }

    return {
        "positive_prompt": positive_prompt,
        "negative_prompt": negative_prompt,
        "structured_summary": structured_summary,
        "recommended_settings": recommended_settings,
        "warnings": warnings,
    }


def _explicit_value(request: SongGenerateRequest, field: str, default: Any, fields_set: set[str]) -> Any:
    value = getattr(request, field)
    if field in fields_set and value not in (None, ""):
        return value
    return default


def _field_or_default(value: Any, default: Any, fallback: Any) -> Any:
    return value if value not in (None, "") else default or fallback


def _list_value(values: list[str], default: Any, field: str, fields_set: set[str]) -> list[str]:
    cleaned = _clean_list(values)
    if field in fields_set and cleaned:
        return cleaned
    return _clean_list(default) or []


def _clean_list(values: Any) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        values = values.split(",")
    cleaned: list[str] = []
    for value in values:
        item = str(value).strip()
        if item and item not in cleaned:
            cleaned.append(item)
    return cleaned


def _midpoint(value: Any) -> int | None:
    if isinstance(value, (list, tuple)) and len(value) == 2:
        try:
            return round((int(value[0]) + int(value[1])) / 2)
        except (TypeError, ValueError):
            return None
    return None


def _default_duration(value: Any) -> int:
    if isinstance(value, (list, tuple)) and len(value) == 2:
        low, high = int(value[0]), int(value[1])
        return min(max(90, low), high)
    return 90


def _default_key(suggestions: Any) -> str | None:
    for suggestion in _clean_list(suggestions):
        lowered = suggestion.lower()
        if "major" in lowered or "minor" in lowered:
            if "keys" not in lowered and "/" not in lowered:
                return suggestion
    return None


def _fallback_arrangement(production_style: str, genre: str) -> str:
    style = production_style.lower()
    if "bollywood" in style or genre == "Pop":
        return "Piano-led cinematic"
    if "lo-fi" in style:
        return "Lo-fi warm tape"
    if "qawwali" in style:
        return "Qawwali harmonium + claps"
    if "trap" in style:
        return "Trap drums + Indian melody"
    if "acoustic" in style:
        return "Acoustic guitar-led"
    return "Indie band arrangement"


def _fallback_structure(production_style: str) -> list[str]:
    if "bollywood" in production_style.lower():
        return ["intro", "mukhda", "hook", "antara", "final hook", "outro"]
    return ["intro", "verse", "hook", "verse", "hook", "outro"]


def _fallback_mix_direction(request: SongGenerateRequest) -> str:
    if request.vocal_forward_mix:
        return "vocal-forward, warm reverb, backing slightly lower"
    return "balanced vocal and backing, clean headroom"


def _positive_prompt(
    *,
    language: str,
    genre: str,
    production_style: str,
    arrangement_style: str,
    mood_tags: list[str],
    instruments: list[str],
    bpm: int,
    key: str | None,
    duration_seconds: int | None,
    structure: list[str],
    mix_direction: str,
    preset: dict[str, Any],
) -> str:
    style_intro = _style_intro(language, production_style, mood_tags)
    bpm_text = f"at around {bpm} BPM"
    key_text = f" in {key}" if key else ""
    duration_text = f" for about {duration_seconds} seconds" if duration_seconds else ""
    mood_text = _serial(mood_tags) if mood_tags else "emotionally clear and cinematic"
    instrument_text = _serial(instruments) if instruments else "a restrained, vocal-friendly band"
    arrangement_text = arrangement_style[:1].lower() + arrangement_style[1:] if arrangement_style else arrangement_style
    structure_text = ", ".join(structure)
    hints = _clean_list(preset.get("prompt_hints"))
    hint_text = f" Include {', '.join(hints)}." if hints else ""
    return (
        f"Create an original {style_intro} in the {genre} genre with a stable musical feel {bpm_text}{key_text}{duration_text}. "
        f"Use a {arrangement_text} arrangement with {instrument_text}. "
        f"The mood should feel {mood_text}. "
        f"Use a structure with {structure_text}. "
        f"Keep the vocal forward in the mix with {mix_direction}. "
        "For Indian/Bollywood context, use melodic phrasing and arrangement details only where they fit the selected style; "
        "do not assume tabla or sitar is needed unless requested. "
        f"{' '.join(ORIGINALITY_RULES)}"
        f"{hint_text}"
    ).strip()


def _style_intro(language: str, production_style: str, mood_tags: list[str]) -> str:
    style = production_style.strip()
    if style == "Bollywood Ballad":
        return f"{language} romantic Bollywood ballad"
    if style == "Lo-fi Cover":
        return f"{language}/Hinglish lo-fi cover-inspired arrangement"
    if style == "Bhajan / Devotional":
        return f"{language} devotional bhajan"
    if style == "Qawwali Fusion":
        return f"{language} qawwali fusion"
    if "romantic" in {tag.lower() for tag in mood_tags} and "romantic" not in style.lower():
        return f"{language} romantic {style}"
    return f"{language} {style}"


def _negative_prompt(preset: dict[str, Any]) -> str:
    hints = _clean_list(preset.get("negative_prompt_hints"))
    rules = [*BASE_NEGATIVE_RULES, *hints]
    normalized: list[str] = []
    for rule in rules:
        text = str(rule).strip().rstrip(".")
        if text and text.lower() not in {item.lower() for item in normalized}:
            normalized.append(text)
    sentences = []
    for rule in normalized:
        if rule.lower().startswith(("no ", "avoid ", "do not ")):
            sentences.append(rule[0].upper() + rule[1:] + ".")
        else:
            sentences.append(f"Avoid {rule}.")
    return " ".join(sentences)


def _conflict_warnings(
    production_style: str,
    arrangement_style: str,
    instruments: list[str],
    energy: str | None,
) -> list[str]:
    style = production_style.lower()
    arrangement = arrangement_style.lower()
    joined_instruments = " ".join(instruments).lower()
    warnings: list[str] = []
    has_trap = any(token in joined_instruments or token in arrangement for token in ("808", "trap", "aggressive"))

    if ("bhajan" in style or "devotional" in style) and has_trap:
        warnings.append("Bhajan / Devotional conflicts with aggressive trap drums or 808-heavy instrumentation.")
    if "lo-fi" in style and str(energy or "").lower() in {"high", "very high", "very-high"}:
        warnings.append("Lo-fi Cover usually works better with low or medium energy than very high energy.")
    if "bollywood ballad" in style and ("edm rework" in arrangement or "edm" in arrangement):
        warnings.append("Bollywood Ballad conflicts with an EDM Rework arrangement unless the user wants a hybrid.")
    if "qawwali" in style and len(instruments) < 3:
        warnings.append("Qawwali Fusion usually needs harmonium, claps, percussion, and chorus support.")
    if "acoustic unplugged" in style and has_trap:
        warnings.append("Acoustic Unplugged conflicts with heavy 808 or trap drums.")
    return warnings


def _serial(values: list[str]) -> str:
    if not values:
        return ""
    if len(values) == 1:
        return values[0]
    if len(values) == 2:
        return f"{values[0]} and {values[1]}"
    return f"{', '.join(values[:-1])}, and {values[-1]}"


def preview_default_prompt() -> dict[str, Any]:
    return build_generation_prompt(SongGenerateRequest(), get_default_preset())
