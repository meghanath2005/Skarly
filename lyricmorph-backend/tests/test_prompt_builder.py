from app.models import SongGenerateRequest
from app.presets import get_preset_by_id
from app.prompt_builder import build_generation_prompt


def test_bollywood_ballad_prompt_contains_required_details():
    preset = get_preset_by_id("bollywood_ballad_piano")
    result = build_generation_prompt(SongGenerateRequest(), preset)
    positive = result["positive_prompt"]

    assert "original Hindi romantic Bollywood ballad" in positive
    assert "piano-led cinematic" in positive
    assert "vocal forward" in positive
    assert "Do not copy any existing song" in positive
    assert "mukhda" in positive
    assert "antara" in positive


def test_lofi_hindi_cover_prompt_contains_required_details():
    preset = get_preset_by_id("lofi_hindi_cover")
    result = build_generation_prompt(SongGenerateRequest(preset_id="lofi_hindi_cover"), preset)
    text = f"{result['positive_prompt']} {result['negative_prompt']}".lower()

    assert "lo-fi" in text
    assert "warm tape" in text
    assert "nostalgic" in text
    assert "no harsh drums" in text


def test_bhajan_prompt_contains_required_details():
    preset = get_preset_by_id("devotional_bhajan")
    result = build_generation_prompt(SongGenerateRequest(), preset)
    text = f"{result['positive_prompt']} {result['negative_prompt']}".lower()

    assert "devotional" in text
    assert "harmonium" in text
    assert "tabla" in text
    assert "tanpura" in text
    assert "no nightclub drums" in text


def test_user_overrides_bpm_and_duration():
    preset = get_preset_by_id("bollywood_ballad_piano")
    result = build_generation_prompt(SongGenerateRequest(bpm=92, duration_seconds=120), preset)

    assert result["structured_summary"]["bpm"] == 92
    assert result["structured_summary"]["duration_seconds"] == 120
    assert result["recommended_settings"]["bpm"] == 92
    assert result["recommended_settings"]["duration_seconds"] == 120


def test_conflict_warnings_are_generated():
    result = build_generation_prompt(
        SongGenerateRequest(
            genre="Acoustic",
            production_style="Acoustic Unplugged",
            arrangement_style="Trap drums + Indian melody",
            instruments=["acoustic guitar", "808 bass", "trap drums"],
        )
    )

    assert any("Acoustic Unplugged conflicts" in warning for warning in result["warnings"])


def test_negative_prompt_includes_originality_and_anti_copying_rules():
    preset = get_preset_by_id("bollywood_ballad_piano")
    result = build_generation_prompt(SongGenerateRequest(), preset)
    negative = result["negative_prompt"]

    assert "Do not copy any existing song" in negative
    assert "Do not imitate a specific living artist voice" in negative
