from app.presets import REQUIRED_PRESET_FIELDS, get_all_presets, get_default_preset, get_preset_by_id, get_presets_by_production_style


REQUIRED_PRESET_IDS = {
    "bollywood_ballad_piano",
    "lofi_hindi_cover",
    "qawwali_fusion",
    "trap_soul_hindi",
    "devotional_bhajan",
    "acoustic_unplugged_hindi",
    "sufi_rock",
}


def test_get_all_presets_returns_required_presets():
    presets = get_all_presets()
    preset_ids = {preset["id"] for preset in presets}

    assert REQUIRED_PRESET_IDS.issubset(preset_ids)


def test_get_preset_by_id_works():
    preset = get_preset_by_id("bollywood_ballad_piano")

    assert preset is not None
    assert preset["name"] == "Hindi Romantic Ballad"
    assert preset["production_style"] == "Bollywood Ballad"


def test_every_preset_has_required_fields():
    for preset in get_all_presets():
        for field in REQUIRED_PRESET_FIELDS:
            assert field in preset
            assert preset[field] not in (None, "")


def test_default_preset_is_hindi_romantic_ballad():
    preset = get_default_preset()

    assert preset["id"] == "bollywood_ballad_piano"
    assert preset["name"] == "Hindi Romantic Ballad"


def test_get_presets_by_production_style_is_case_insensitive():
    presets = get_presets_by_production_style("lo-fi cover")

    assert [preset["id"] for preset in presets] == ["lofi_hindi_cover"]
