from app.models import SectionEditRequest
from app.services.section_editor import build_section_edit_prompt, edit_section


def request_for_hook(**overrides) -> SectionEditRequest:
    data = {
        "section_name": "hook",
        "edit_instruction": "Make hook like Tum Hi Ho but bigger with warm strings.",
        "lyrics": "mera dil tumhare bina adhoora hai",
        "language": "Hindi",
        "genre": "Pop",
        "production_style": "Bollywood Ballad",
        "arrangement_style": "Piano-led cinematic",
        "mood_tags": ["heartbreak", "longing"],
        "instruments": ["piano", "strings", "soft drums"],
        "bpm": 88,
        "key": "A minor",
    }
    data.update(overrides)
    return SectionEditRequest(**data)


def test_build_section_edit_prompt_includes_context_and_originality():
    prompt = build_section_edit_prompt(request_for_hook())

    assert "hook" in prompt.lower()
    assert "Make hook" in prompt
    assert "Bollywood Ballad" in prompt
    assert "Piano-led cinematic" in prompt
    assert "88 BPM" in prompt
    assert "Create original audio" in prompt
    assert "do not copy any existing song" in prompt
    assert "Tum Hi Ho" not in prompt


def test_prompt_only_mode_returns_prompt_ready():
    response = edit_section(request_for_hook(), mode="prompt_only", enabled=True)

    assert response.status == "prompt_ready"
    assert response.mode == "prompt_only"
    assert response.edit_prompt
    assert response.message == "Section edit prompt prepared without changing audio."


def test_ace_step_mode_unavailable_returns_not_implemented():
    response = edit_section(request_for_hook(), mode="ace_step", enabled=True, ace_step_editor=None)

    assert response.status == "not_implemented"
    assert response.diagnostics is not None
    assert response.diagnostics.failed_step == "ace_step_section_edit"
    assert "not configured" in response.diagnostics.error_message


def test_missing_source_audio_in_prompt_only_does_not_crash():
    response = edit_section(
        request_for_hook(source_audio_path=None, source_job_id=None),
        mode="prompt_only",
        enabled=True,
    )

    assert response.status == "prompt_ready"
    assert response.output_audio_path is None


def test_ace_step_mode_forwards_repaint_controls_and_metadata(tmp_path):
    output_path = tmp_path / "edited.wav"
    output_path.write_bytes(b"placeholder")
    received = {}

    class Result:
        success = True
        generator_name = "ACE-Step repaint"
        error_message = None
        suggested_fix = None
        command_used = "POST /release_task task_type=repaint"
        logs = ["preserved"]
        metadata = {
            "preserved_outside_section": True,
            "section_changed": True,
            "outside_max_abs_error": 0.0,
        }

        def __init__(self):
            self.output_path = str(output_path)

    def fake_editor(**kwargs):
        received.update(kwargs)
        return Result()

    response = edit_section(
        request_for_hook(
            source_audio_path=str(tmp_path / "backing.wav"),
            section_start_seconds=4.0,
            section_end_seconds=8.0,
            duration_seconds=12,
            repaint_mode="conservative",
            repaint_strength=0.4,
            boundary_crossfade_seconds=0.02,
        ),
        mode="ace_step",
        enabled=True,
        ace_step_editor=fake_editor,
    )

    assert received["section_start_seconds"] == 4.0
    assert received["section_end_seconds"] == 8.0
    assert received["repaint_mode"] == "conservative"
    assert received["repaint_strength"] == 0.4
    assert received["boundary_crossfade_seconds"] == 0.02
    assert received["duration_seconds"] == 12
    assert response.edit_metadata["preserved_outside_section"] is True
