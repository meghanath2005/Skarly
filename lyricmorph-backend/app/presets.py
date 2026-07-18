from __future__ import annotations

from copy import deepcopy
from typing import Any

AVAILABLE_GENRES = ["Rock", "Pop", "Hip-hop", "R&B", "Lo-fi", "Piano", "Acoustic", "Cinematic"]

AVAILABLE_PRODUCTION_STYLES = [
    "Bollywood Ballad",
    "Romantic Pop",
    "Acoustic Unplugged",
    "Piano Ballad",
    "Cinematic Strings",
    "Indie Pop",
    "Lo-fi Cover",
    "EDM Rework",
    "Rock Cover",
    "Trap Soul",
    "Ambient",
    "Orchestral Pop",
    "Qawwali Fusion",
    "Ghazal Pop",
    "Bhajan / Devotional",
    "Folk Fusion",
    "Sufi Rock",
    "Punjabi Pop",
    "South Indian Cinematic",
]

AVAILABLE_ARRANGEMENT_STYLES = [
    "Piano-led cinematic",
    "Acoustic guitar-led",
    "Tabla + strings fusion",
    "Lo-fi warm tape",
    "Orchestral pop",
    "Dholak romantic",
    "Ambient pads",
    "Trap drums + Indian melody",
    "Qawwali harmonium + claps",
    "Minimal vocal piano",
    "Cinematic strings build",
    "Indie band arrangement",
    "Electronic pop arrangement",
    "Folk acoustic arrangement",
]

REQUIRED_PRESET_FIELDS = [
    "id",
    "name",
    "description",
    "genre",
    "production_style",
    "arrangement_style",
    "mood_tags",
    "instruments",
    "bpm_range",
    "default_bpm",
    "key_suggestions",
    "duration_range",
    "structure",
    "mix_direction",
    "prompt_hints",
    "negative_prompt_hints",
]

PRESETS: list[dict[str, Any]] = [
    {
        "id": "bollywood_ballad_piano",
        "name": "Hindi Romantic Ballad",
        "description": "Original Hindi/Bollywood-style romantic ballad with piano-led cinematic arrangement.",
        "genre": "Pop",
        "production_style": "Bollywood Ballad",
        "arrangement_style": "Piano-led cinematic",
        "mood_tags": ["heartbreak", "longing", "emotional", "romantic", "intimate"],
        "instruments": ["piano", "strings", "pads", "clean guitar", "soft drums", "bass"],
        "bpm_range": [80, 95],
        "default_bpm": 88,
        "key_suggestions": ["minor keys", "F minor", "C minor", "A minor"],
        "duration_range": [60, 180],
        "structure": ["intro", "mukhda", "hook", "antara", "final hook", "outro"],
        "mix_direction": "vocal-forward, warm reverb, soft delay, backing slightly lower",
        "prompt_hints": [
            "slow emotional 4/4 feel",
            "Bollywood romantic phrasing",
            "cinematic but intimate dynamics",
        ],
        "negative_prompt_hints": [
            "no EDM drop",
            "no heavy percussion",
            "do not copy any existing song",
            "do not imitate a specific artist voice",
        ],
    },
    {
        "id": "lofi_hindi_cover",
        "name": "Lo-fi Hindi Cover",
        "description": "Soft late-night Hindi/Hinglish lo-fi arrangement.",
        "genre": "Lo-fi",
        "production_style": "Lo-fi Cover",
        "arrangement_style": "Lo-fi warm tape",
        "mood_tags": ["nostalgic", "soft", "late-night", "dreamy"],
        "instruments": ["electric piano", "vinyl texture", "soft drums", "sub bass", "pads"],
        "bpm_range": [65, 90],
        "default_bpm": 76,
        "key_suggestions": ["minor keys", "D minor", "A minor"],
        "duration_range": [45, 150],
        "structure": ["intro", "verse", "hook", "verse", "hook", "outro"],
        "mix_direction": "soft vocal, warm tape texture, gentle compression",
        "prompt_hints": ["late-night intimacy", "dusty groove", "soft lo-fi texture"],
        "negative_prompt_hints": ["no harsh drums", "no bright EDM synths", "no aggressive vocals"],
    },
    {
        "id": "qawwali_fusion",
        "name": "Qawwali Fusion",
        "description": "Devotional and powerful qawwali-inspired fusion arrangement.",
        "genre": "Cinematic",
        "production_style": "Qawwali Fusion",
        "arrangement_style": "Qawwali harmonium + claps",
        "mood_tags": ["devotional", "powerful", "spiritual", "rising energy"],
        "instruments": ["harmonium", "claps", "tabla", "dholak", "bass", "strings", "chorus vocals"],
        "bpm_range": [90, 125],
        "default_bpm": 104,
        "key_suggestions": ["minor/modal keys"],
        "duration_range": [90, 240],
        "structure": ["alaap intro", "lead vocal", "response chorus", "rising hook", "final energetic hook"],
        "mix_direction": "lead vocal forward, group chorus wide, percussion energetic but controlled",
        "prompt_hints": ["call-and-response lift", "wide chorus vocals", "devotional intensity"],
        "negative_prompt_hints": [
            "no EDM drop unless explicitly requested",
            "no parody tone",
            "no copied qawwali composition",
        ],
    },
    {
        "id": "trap_soul_hindi",
        "name": "Trap Soul Hindi",
        "description": "Modern dark romantic Hindi/R&B trap-soul style.",
        "genre": "R&B",
        "production_style": "Trap Soul",
        "arrangement_style": "Trap drums + Indian melody",
        "mood_tags": ["dark", "romantic", "modern", "moody"],
        "instruments": ["808 bass", "trap drums", "pads", "pluck melody", "Indian flute texture"],
        "bpm_range": [70, 100],
        "default_bpm": 82,
        "key_suggestions": ["minor keys"],
        "duration_range": [60, 180],
        "structure": ["intro", "verse", "hook", "verse", "hook", "outro"],
        "mix_direction": "intimate vocal, deep bass, atmospheric reverb",
        "prompt_hints": ["dark romantic pocket", "sparse Indian melodic accent", "deep sub movement"],
        "negative_prompt_hints": ["no overbright pop drums", "no excessive distortion", "no copied artist flow"],
    },
    {
        "id": "devotional_bhajan",
        "name": "Devotional Bhajan",
        "description": "Peaceful Indian devotional song arrangement.",
        "genre": "Acoustic",
        "production_style": "Bhajan / Devotional",
        "arrangement_style": "Tabla + strings fusion",
        "mood_tags": ["peaceful", "devotional", "warm", "spiritual"],
        "instruments": ["harmonium", "tabla", "tanpura", "flute", "soft strings"],
        "bpm_range": [70, 105],
        "default_bpm": 84,
        "key_suggestions": ["simple major/minor/modal keys"],
        "duration_range": [90, 240],
        "structure": ["intro", "sthayi", "antara", "repeat", "soft outro"],
        "mix_direction": "natural vocal, warm harmonium, gentle tabla, devotional space",
        "prompt_hints": ["peaceful devotional phrasing", "natural Indian acoustic space", "gentle repeatable hook"],
        "negative_prompt_hints": ["no nightclub drums", "no aggressive bass", "no parody devotional tone"],
    },
    {
        "id": "acoustic_unplugged_hindi",
        "name": "Acoustic Unplugged Hindi",
        "description": "Simple acoustic guitar-led Hindi romantic arrangement.",
        "genre": "Acoustic",
        "production_style": "Acoustic Unplugged",
        "arrangement_style": "Acoustic guitar-led",
        "mood_tags": ["intimate", "warm", "sincere", "romantic"],
        "instruments": ["acoustic guitar", "soft bass", "light percussion", "pads"],
        "bpm_range": [75, 110],
        "default_bpm": 90,
        "key_suggestions": ["G major", "D major", "A minor", "C major"],
        "duration_range": [60, 180],
        "structure": ["intro", "verse", "hook", "verse", "hook", "outro"],
        "mix_direction": "dry intimate vocal, gentle guitar, light room reverb",
        "prompt_hints": ["honest acoustic performance", "soft guitar pulse", "room-close vocal"],
        "negative_prompt_hints": ["no heavy orchestra", "no EDM beat", "no metallic drums"],
    },
    {
        "id": "sufi_rock",
        "name": "Sufi Rock",
        "description": "Emotional Sufi-inspired rock/pop arrangement.",
        "genre": "Rock",
        "production_style": "Sufi Rock",
        "arrangement_style": "Indie band arrangement",
        "mood_tags": ["spiritual", "intense", "emotional", "anthemic"],
        "instruments": ["electric guitar", "bass", "drums", "harmonium texture", "strings", "backing vocals"],
        "bpm_range": [85, 125],
        "default_bpm": 100,
        "key_suggestions": ["minor/modal keys"],
        "duration_range": [90, 240],
        "structure": ["intro", "verse", "hook", "bridge", "final hook", "outro"],
        "mix_direction": "powerful vocal, wide guitars, controlled drums",
        "prompt_hints": ["spiritual rock lift", "anthemic final hook", "supportive harmonium texture"],
        "negative_prompt_hints": ["no copied riffs", "no harsh metal tone unless requested"],
    },
]


def _copy_preset(preset: dict[str, Any]) -> dict[str, Any]:
    return deepcopy(preset)


def get_all_presets() -> list[dict[str, Any]]:
    return [_copy_preset(preset) for preset in PRESETS]


def get_preset_by_id(preset_id: str | None) -> dict[str, Any] | None:
    if not preset_id:
        return None
    normalized = preset_id.strip().lower()
    for preset in PRESETS:
        if preset["id"].lower() == normalized:
            return _copy_preset(preset)
    return None


def get_presets_by_production_style(style: str | None) -> list[dict[str, Any]]:
    if not style:
        return []
    normalized = style.strip().lower()
    return [_copy_preset(preset) for preset in PRESETS if preset["production_style"].lower() == normalized]


def get_default_preset() -> dict[str, Any]:
    return _copy_preset(PRESETS[0])
