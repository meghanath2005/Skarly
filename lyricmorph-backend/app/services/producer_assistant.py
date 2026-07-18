from __future__ import annotations

import re
from typing import Any

from ..models import (
    GenerationDiagnostics,
    LyricsImproveRequest,
    LyricsImproveResponse,
    MixDiagnostics,
    ProducerSuggestionRequest,
    ProducerSuggestionResponse,
    QualityExplanationRequest,
    QualityExplanationResponse,
    QualityReport,
    SongAnalysis,
    SongGenerateRequest,
)
from ..presets import get_all_presets, get_default_preset, get_preset_by_id
from ..prompt_builder import build_generation_prompt

ASSISTANT_MODE = "rules"

ROMANTIC_WORDS = {
    "dil",
    "yaad",
    "tere",
    "meri",
    "tanha",
    "adhoora",
    "adhoori",
    "bina",
    "khamoshi",
    "safar",
    "raat",
    "aansu",
    "judaai",
    "intezaar",
}
URDU_TOUCH_WORDS = {"ishq", "khwaab", "rooh", "dua", "ibadat", "sukoon", "qismat", "mehfil", "fanaa", "wafa"}
HINDI_ROMAN_WORDS = ROMANTIC_WORDS | URDU_TOUCH_WORDS | {
    "mera",
    "tum",
    "tumhare",
    "aa",
    "aao",
    "jao",
    "saath",
    "pyaar",
    "pyar",
    "mann",
    "maula",
    "ram",
    "krishna",
    "shiv",
    "mandir",
}

PRESET_KEYWORDS = {
    "bollywood_ballad_piano": {
        "heartbreak",
        "yaad",
        "tanha",
        "adhoora",
        "adhoori",
        "judaai",
        "aansu",
        "intezaar",
        "longing",
        "romantic",
        "emotional",
    },
    "lofi_hindi_cover": {
        "late night",
        "late-night",
        "nostalgic",
        "rain",
        "baarish",
        "memory",
        "soft",
        "dreamy",
        "lofi",
        "lo-fi",
    },
    "qawwali_fusion": {"ibadat", "maula", "allah", "dua", "qawwali", "rooh", "sufi", "mehfil", "devotional"},
    "devotional_bhajan": {"bhajan", "ram", "krishna", "shiv", "mandir", "devotion", "devotional", "aarti", "prarthana"},
    "trap_soul_hindi": {"dark", "modern", "toxic", "nightlife", "moody", "808", "trap", "r&b", "rnb"},
    "acoustic_unplugged_hindi": {"simple", "raw", "guitar", "unplugged", "acoustic", "sincere"},
    "sufi_rock": {"sufi", "rooh", "junoon", "anthemic", "rock", "intense"},
}


def improve_lyrics_rules(request: LyricsImproveRequest, assistant_mode: str = ASSISTANT_MODE) -> LyricsImproveResponse:
    original = request.lyrics or ""
    cleaned = _clean_lyric_text(original)
    language_style = detect_language_style(cleaned or original)
    warnings: list[str] = []

    if not cleaned:
        return LyricsImproveResponse(
            original_lyrics=original,
            improved_lyrics="",
            detected_language_style=language_style,
            suggested_sections=suggest_sections([], request.production_style),
            rhyme_notes=[],
            pronunciation_notes=[],
            warnings=["Add at least one lyric line before asking for improvement."],
            assistant_mode=assistant_mode,
            notes=["Rule-based assistant did not rewrite empty lyrics."],
        )

    lines = split_lyrics_into_lines(cleaned)
    suggested_sections = suggest_sections(lines, request.production_style)
    if _has_section_labels(cleaned):
        improved = "\n".join(improve_hinglish_romantic_line(line) for line in lines)
    else:
        improved = add_song_sections(cleaned, request.production_style, request.target_section)

    if _mentions_famous_reference(cleaned):
        warnings.append("Converted any famous-song reference into a broad original style direction; do not copy melodies or lyrics.")
    warnings.append("Keep the final lyric original; avoid copying existing songs or imitating a specific living artist voice.")

    return LyricsImproveResponse(
        original_lyrics=original,
        improved_lyrics=improved,
        detected_language_style=language_style,
        suggested_sections=suggested_sections,
        rhyme_notes=_rhyme_notes(improved),
        pronunciation_notes=pronunciation_notes_for_hinglish(improved),
        warnings=warnings,
        assistant_mode=assistant_mode,
        notes=["Rule-based Hindi/Hinglish lyric improvement applied while preserving the core meaning."],
    )


def improve_lyrics_placeholder(
    lyrics: str,
    language: str = "Hindi",
    mood_tags: list[str] | None = None,
    production_style: str | None = None,
) -> LyricsImproveResponse:
    return improve_lyrics_rules(
        LyricsImproveRequest(
            lyrics=lyrics,
            language=language,
            mood_tags=mood_tags or [],
            production_style=production_style,
        )
    )


def detect_language_style(text: str) -> str:
    value = (text or "").strip()
    if not value:
        return "Unknown"
    lowered = value.lower()
    words = set(re.findall(r"[a-zA-Z']+", lowered))
    has_devanagari = bool(re.search(r"[\u0900-\u097F]", value))
    has_latin = bool(re.search(r"[A-Za-z]", value))
    if words & URDU_TOUCH_WORDS:
        return "Urdu-touch Hindi"
    if has_devanagari and has_latin:
        return "Hinglish"
    if has_devanagari:
        return "Hindi"
    if words & HINDI_ROMAN_WORDS:
        return "Hinglish"
    if has_latin:
        return "English"
    return "Unknown"


def split_lyrics_into_lines(text: str) -> list[str]:
    cleaned = _clean_lyric_text(text)
    if not cleaned:
        return []
    raw_lines = [line.strip() for line in re.split(r"[\n\r]+", cleaned) if line.strip()]
    if len(raw_lines) > 1:
        return raw_lines
    chunks = [chunk.strip() for chunk in re.split(r"[.!?;।]+", cleaned) if chunk.strip()]
    if len(chunks) > 1:
        return chunks
    words = cleaned.split()
    if len(words) <= 8:
        return [cleaned]
    lines: list[str] = []
    for index in range(0, len(words), 6):
        lines.append(" ".join(words[index : index + 6]))
    return lines


def suggest_sections(lines: list[str], production_style: str | None) -> list[str]:
    style = (production_style or "").lower()
    if "bhajan" in style or "devotional" in style:
        return ["Sthayi", "Antara", "Repeat", "Outro"]
    if "qawwali" in style:
        return ["Alaap", "Lead", "Response Hook", "Final Hook"]
    if "trap" in style or "lo-fi" in style:
        return ["Verse", "Hook", "Verse", "Outro"]
    return ["Mukhda", "Hook", "Antara", "Outro"]


def improve_hinglish_romantic_line(line: str) -> str:
    text = _clean_lyric_text(line)
    if not text:
        return ""
    lowered = text.lower()
    if "adhoora" in lowered and "bina" in lowered:
        return "Mera dil adhoora sa hai, tere bina yeh safar kya hai?"
    if "aa jao" in lowered or "aao" in lowered:
        return "Aa jao, mere paas aa jao, is khamoshi ko awaaz bana jao."
    replacements = {
        "mera dil": "Mera dil",
        "tumhare bina": "tere bina",
        "tum aa jao": "tum aa jao",
        "yaad": "yaad",
        "khamoshi": "khamoshi",
    }
    improved = text
    for source, target in replacements.items():
        improved = re.sub(source, target, improved, flags=re.IGNORECASE)
    return improved[:1].upper() + improved[1:].rstrip(",") + ","


def add_song_sections(lyrics: str, production_style: str | None, target_section: str | None = None) -> str:
    lines = split_lyrics_into_lines(lyrics)
    if not lines:
        return ""
    style = (production_style or "").lower()
    if "bhajan" in style or "devotional" in style:
        first_label, hook_label = "Sthayi", "Antara"
    else:
        first_label, hook_label = target_section or "Mukhda", "Hook"

    joined = " ".join(lines).lower()
    if ROMANTIC_WORDS & set(re.findall(r"[a-zA-Z']+", joined)):
        mukhda = [
            "Mera dil adhoora sa hai,",
            "Tere bina yeh safar kya hai?",
        ]
        hook = [
            "Aa jao, mere paas aa jao,",
            "Is khamoshi ko awaaz bana jao.",
        ]
    else:
        improved_lines = [improve_hinglish_romantic_line(line) for line in lines]
        midpoint = max(1, len(improved_lines) // 2)
        mukhda = improved_lines[:midpoint]
        hook = improved_lines[midpoint:] or ["Is ehsaas ko ek nayi awaaz do."]

    return f"[{first_label}]\n" + "\n".join(mukhda) + f"\n\n[{hook_label}]\n" + "\n".join(hook)


def pronunciation_notes_for_hinglish(lyrics: str) -> list[str]:
    if not lyrics.strip():
        return []
    notes = ["Keep kh, gh, sh, and aa sounds clear for Hindi singing."]
    lowered = lyrics.lower()
    careful_words = [word for word in ("khwaab", "ishq", "yaad", "saath", "khamoshi", "rooh") if word in lowered]
    if careful_words:
        notes.append(f"Words like {', '.join(careful_words)} may need careful pronunciation.")
    notes.append("Avoid over-English pronunciation for Hindi vowels.")
    return notes


def suggest_producer_settings(request: ProducerSuggestionRequest) -> ProducerSuggestionResponse:
    text = _combined_text(request)
    preset_id, matched_terms = _select_preset(text)
    preset = get_preset_by_id(preset_id) or get_default_preset()
    inferred_moods = _infer_moods(text, preset.get("mood_tags") or [])
    warnings = _assistant_conflict_warnings(
        request.production_style or preset["production_style"],
        request.arrangement_style or preset["arrangement_style"],
        request.instruments or preset["instruments"],
    )
    reasoning = [
        f"Matched {preset['name']} from lyric/mood cues.",
        f"Recommended {preset['arrangement_style']} because it supports {preset['production_style']}.",
    ]
    if matched_terms:
        reasoning.append(f"Detected cues: {', '.join(matched_terms[:6])}.")
    return ProducerSuggestionResponse(
        recommended_preset_id=preset["id"],
        recommended_genre=request.genre or preset["genre"],
        recommended_production_style=request.production_style or preset["production_style"],
        recommended_arrangement_style=request.arrangement_style or preset["arrangement_style"],
        recommended_mood_tags=_dedupe([*inferred_moods, *(request.mood_tags or [])]),
        recommended_instruments=_dedupe([*(request.instruments or []), *preset["instruments"]]),
        recommended_bpm=request.bpm or preset.get("default_bpm"),
        recommended_key=request.key or _first_real_key(preset.get("key_suggestions") or []),
        reasoning=reasoning,
        warnings=warnings,
        prompt_hints=list(preset.get("prompt_hints") or []),
    )


def compile_producer_prompt(request: ProducerSuggestionRequest) -> dict[str, Any]:
    suggestion = suggest_producer_settings(request)
    preset = get_preset_by_id(suggestion.recommended_preset_id) if suggestion.recommended_preset_id else get_default_preset()
    prompt_request = SongGenerateRequest(
        lyrics=request.lyrics,
        language=request.language,
        genre=suggestion.recommended_genre or "Pop",
        production_style=suggestion.recommended_production_style,
        arrangement_style=suggestion.recommended_arrangement_style,
        mood_tags=suggestion.recommended_mood_tags,
        instruments=suggestion.recommended_instruments,
        bpm=suggestion.recommended_bpm,
        key=suggestion.recommended_key,
        duration_seconds=request.duration_seconds,
    )
    prompt = build_generation_prompt(prompt_request, preset)
    prompt["assistant_reasoning"] = suggestion.reasoning
    prompt["assistant_suggestion"] = suggestion.model_dump()
    return prompt


def analyze_request_placeholder(request: SongGenerateRequest, preset: dict[str, Any] | None = None) -> SongAnalysis:
    preview = build_generation_prompt(request, preset)
    summary = preview["structured_summary"]
    suggestion = suggest_producer_settings(
        ProducerSuggestionRequest(
            lyrics=request.lyrics,
            language=request.language,
            mood_tags=request.mood_tags,
            genre=request.genre,
            production_style=request.production_style,
            arrangement_style=request.arrangement_style,
            instruments=request.instruments,
            bpm=request.bpm,
            key=request.key,
            duration_seconds=request.duration_seconds,
        )
    )
    recommendations = [
        *suggestion.reasoning,
        "Keep lead vocal phrasing clear and leave midrange space in the backing.",
    ]
    if suggestion.recommended_preset_id:
        recommendations.append(f"Suggested preset: {suggestion.recommended_preset_id}.")
    return SongAnalysis(
        detected_bpm=None,
        production_bpm=summary.get("bpm") or suggestion.recommended_bpm,
        bpm_confidence=None,
        detected_key=summary.get("key") or suggestion.recommended_key,
        production_key=summary.get("key") or suggestion.recommended_key,
        key_confidence=None,
        tempo_feel="rule-based producer estimate",
        mood_tags=summary.get("mood_tags") or suggestion.recommended_mood_tags,
        genre=summary.get("genre") or suggestion.recommended_genre or request.genre,
        production_style=summary.get("production_style") or suggestion.recommended_production_style,
        arrangement_style=summary.get("arrangement_style") or suggestion.recommended_arrangement_style,
        main_instruments=summary.get("instruments") or suggestion.recommended_instruments,
        vocal_priority="vocal-forward" if request.vocal_forward_mix else "balanced",
        warnings=_dedupe([*preview["warnings"], *suggestion.warnings]),
        production_recommendations=recommendations,
        recommended_production=recommendations,
        duration_seconds=summary.get("duration_seconds"),
        energy=request.energy,
        mood=", ".join(summary.get("mood_tags") or suggestion.recommended_mood_tags),
    )


def explain_quality_report_rules(request: QualityExplanationRequest) -> QualityExplanationResponse:
    report = request.quality_report
    diagnostics = request.diagnostics
    mix_diagnostics = request.mix_diagnostics
    issues: list[str] = []
    fixes: list[str] = []

    if report is None and diagnostics is None and mix_diagnostics is None:
        return QualityExplanationResponse(
            summary="No quality or diagnostic report was provided yet.",
            issues=["Generate or mix audio first, then ask for an explanation."],
            suggested_fixes=["Run Generate, then use Explain Quality after a report is available."],
            user_friendly_status="No report",
        )

    if report:
        if report.passed:
            summary = "Audio passed validation and looks usable for preview."
        else:
            summary = "Audio needs attention before it should be treated as a finished result."
        if report.is_silent:
            issues.append("Audio was generated, but it appears silent or nearly silent.")
            fixes.append("Try a stronger prompt, shorter duration, or check the generator output.")
        if report.clipping_detected:
            issues.append("The audio is too loud and may distort.")
            fixes.append("Lower gain or use normalization before export.")
        if report.fallback_used:
            issues.append("procedural_v2 fallback was used, so this is a basic preview rather than full AI generation.")
            fixes.append("Check ACE-Step configuration for higher-quality generation.")
        for warning in report.warnings:
            if warning not in issues:
                issues.append(warning)
    else:
        summary = "Diagnostics are available, but no audio quality report was provided."

    if diagnostics and diagnostics.failed_step:
        issues.append(f"Generation stopped at {diagnostics.failed_step}.")
        if diagnostics.suggested_fix:
            fixes.append(diagnostics.suggested_fix)
    if mix_diagnostics:
        if mix_diagnostics.status == "mix_success":
            issues.append("Vocal/backing mix completed with the selected gain and ducking settings.")
        elif mix_diagnostics.status == "mix_failed":
            issues.append("Backing audio was created, but vocal mixing failed.")
            fixes.append(mix_diagnostics.suggested_fix or "Check whether the vocal file path is valid and readable.")
        if mix_diagnostics.warnings:
            issues.extend(mix_diagnostics.warnings)

    if not issues:
        issues.append("No major issues detected.")
    if not fixes:
        fixes.append("Keep these settings if the preview sounds right; otherwise adjust style, duration, or mix gain.")

    status = "Ready for preview" if report and report.passed and not (mix_diagnostics and mix_diagnostics.status == "mix_failed") else "Needs attention"
    return QualityExplanationResponse(
        summary=summary,
        issues=_dedupe(issues),
        suggested_fixes=_dedupe(fixes),
        user_friendly_status=status,
    )


def explain_quality_report_placeholder_or_rules(
    quality_report: QualityReport | None = None,
    diagnostics: GenerationDiagnostics | None = None,
    mix_diagnostics: MixDiagnostics | None = None,
) -> QualityExplanationResponse:
    return explain_quality_report_rules(
        QualityExplanationRequest(
            quality_report=quality_report,
            diagnostics=diagnostics,
            mix_diagnostics=mix_diagnostics,
        )
    )


def explain_quality_report_placeholder() -> QualityReport:
    return QualityReport(
        audio_exists=False,
        generator_name="mock_prompt_builder",
        fallback_used=False,
        warnings=["Real audio quality checks will begin after Phase 4 generation is connected."],
        passed=False,
    )


def _clean_lyric_text(text: str) -> str:
    cleaned = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _has_section_labels(text: str) -> bool:
    return bool(re.search(r"^\s*\[[^\]]+\]", text, re.MULTILINE))


def _mentions_famous_reference(text: str) -> bool:
    lowered = text.lower()
    return any(reference in lowered for reference in ("tum hi ho", "arijit", "atif", "jubin", "shreya"))


def _rhyme_notes(lyrics: str) -> list[str]:
    lines = [line.strip(" ,.?") for line in lyrics.splitlines() if line.strip() and not line.startswith("[")]
    if len(lines) < 2:
        return ["Add at least two lyric lines to create a clearer rhyme pattern."]
    endings = [line.split()[-1].lower() for line in lines if line.split()]
    if len(set(endings)) < len(endings):
        return ["Repeated line endings can create a simple hook rhyme."]
    return ["Use soft vowel endings like aa, hai, and jao for singable Hindi/Hinglish phrasing."]


def _combined_text(request: ProducerSuggestionRequest) -> str:
    values = [
        request.lyrics or "",
        request.language,
        request.genre or "",
        request.production_style or "",
        request.arrangement_style or "",
        " ".join(request.mood_tags or []),
        " ".join(request.instruments or []),
    ]
    return " ".join(values).lower()


def _select_preset(text: str) -> tuple[str, list[str]]:
    scores: dict[str, int] = {}
    matched: dict[str, list[str]] = {}
    for preset_id, keywords in PRESET_KEYWORDS.items():
        for keyword in keywords:
            if keyword in text:
                scores[preset_id] = scores.get(preset_id, 0) + (2 if " " in keyword else 1)
                matched.setdefault(preset_id, []).append(keyword)
    if "sufi" in text and "rock" not in text and scores.get("qawwali_fusion", 0) >= scores.get("sufi_rock", 0):
        return "qawwali_fusion", matched.get("qawwali_fusion", [])
    if scores:
        preset_id = max(scores, key=lambda item: (scores[item], item == "bollywood_ballad_piano"))
        return preset_id, matched.get(preset_id, [])
    return "bollywood_ballad_piano", []


def _infer_moods(text: str, defaults: list[str]) -> list[str]:
    moods = list(defaults)
    if any(word in text for word in ("yaad", "tanha", "adhoora", "heartbreak", "judaai")):
        moods.extend(["heartbreak", "longing", "emotional"])
    if any(word in text for word in ("ibadat", "maula", "dua", "ram", "krishna", "shiv")):
        moods.extend(["devotional", "spiritual"])
    if any(word in text for word in ("late night", "rain", "baarish", "memory")):
        moods.extend(["nostalgic", "soft", "late-night"])
    if any(word in text for word in ("dark", "modern", "toxic", "nightlife")):
        moods.extend(["dark", "modern", "moody"])
    return _dedupe(moods)


def _assistant_conflict_warnings(production_style: str, arrangement_style: str, instruments: list[str]) -> list[str]:
    style = production_style.lower()
    arrangement = arrangement_style.lower()
    joined = " ".join(instruments).lower()
    warnings: list[str] = []
    if ("bhajan" in style or "devotional" in style) and any(token in joined or token in arrangement for token in ("808", "trap", "nightclub")):
        warnings.append("Devotional/Bhajan usually conflicts with aggressive trap or nightclub percussion.")
    if "lo-fi" in style and any(token in joined for token in ("bright edm", "heavy drums")):
        warnings.append("Lo-fi works better with soft drums and warm texture.")
    if "qawwali" in style and len(instruments) < 3:
        warnings.append("Qawwali Fusion benefits from harmonium, claps, percussion, and chorus support.")
    return warnings


def _first_real_key(keys: list[str]) -> str | None:
    for key in keys:
        lowered = str(key).lower()
        if ("major" in lowered or "minor" in lowered) and "keys" not in lowered and "/" not in lowered:
            return str(key)
    return None


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in result:
            result.append(text)
    return result
