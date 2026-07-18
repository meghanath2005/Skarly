from __future__ import annotations

from pathlib import Path
from typing import Callable

from ..audio_validation import validate_audio_file
from ..models import GenerationDiagnostics, QualityReport, SectionEditRequest, SectionEditResponse, now_utc

BACKEND_ROOT = Path(__file__).resolve().parents[2]

FAMOUS_REFERENCE_REPLACEMENTS = {
    "tum hi ho": "an emotional Hindi romantic Bollywood ballad with piano-led cinematic arrangement",
    "arijit singh": "an emotional contemporary Hindi playback vocal direction",
    "atif aslam": "a broad romantic pop-rock vocal direction",
    "jubin nautiyal": "a broad modern Hindi ballad vocal direction",
}


def build_section_edit_prompt(request: SectionEditRequest) -> str:
    section_name = _clean_phrase(request.section_name) or "selected section"
    edit_instruction = _sanitize_reference_language(request.edit_instruction)
    style_bits = _style_bits(request)
    lyric_block = _trim(request.lyrics, 900)

    lines = [
        f"Edit only the {section_name} section of this original {request.language or 'Hindi'} song.",
    ]
    if style_bits:
        lines.append(f"Keep the established style context: {', '.join(style_bits)}.")
    if request.section_start_seconds is not None or request.section_end_seconds is not None:
        lines.append(
            "Target timing: "
            f"{request.section_start_seconds if request.section_start_seconds is not None else 'start'}s"
            " to "
            f"{request.section_end_seconds if request.section_end_seconds is not None else 'end'}s."
        )
    lines.append(f"Edit instruction: {edit_instruction}.")
    if lyric_block:
        lines.append(f"Relevant lyrics/context:\n{lyric_block}")
    if request.preserve_style:
        lines.append("Preserve the song's overall genre, arrangement identity, tempo feel, and emotional direction.")
    if request.preserve_vocal:
        lines.append("Preserve the lead vocal intent and avoid changing the singer identity.")
    lines.append(
        "Create original audio, melody, lyrics, and arrangement material; do not copy any existing song, "
        "melody, lyrics, arrangement, or artist voice. Reference styles only as broad production direction "
        "and do not imitate a specific living artist."
    )
    return "\n".join(lines)


def edit_section(
    request: SectionEditRequest,
    *,
    mode: str = "prompt_only",
    enabled: bool = True,
    output_dir: str | Path = "outputs/sections",
    timeout_seconds: int = 900,
    ace_step_editor: Callable[..., object] | None = None,
    url_for_path: Callable[[str], str | None] | None = None,
) -> SectionEditResponse:
    normalized_mode = (mode or "prompt_only").strip().lower()
    edit_prompt = build_section_edit_prompt(request)

    if not enabled:
        return SectionEditResponse(
            status="not_enabled",
            mode=normalized_mode,
            section_name=request.section_name,
            edit_prompt=edit_prompt,
            warnings=["Section editing is disabled. Set SECTION_EDITING_ENABLED=true to enable it."],
            diagnostics=GenerationDiagnostics(
                generator_name="section_editor",
                status="not_enabled",
                failed_step="section_editing",
                error_message="Section editing is disabled.",
                suggested_fix="Set SECTION_EDITING_ENABLED=true to prepare section edits.",
            ),
            message="Section editing is disabled.",
        )

    if normalized_mode == "prompt_only":
        return SectionEditResponse(
            status="prompt_ready",
            mode="prompt_only",
            section_name=request.section_name,
            edit_prompt=edit_prompt,
            diagnostics=GenerationDiagnostics(
                generator_name="section_editor",
                status="prompt_ready",
                last_logs=["Section edit prompt prepared in prompt_only mode."],
                suggested_fix="Use /sections/edit or /api/v2/generations/regenerate-section for real ACE-Step repainting.",
            ),
            message="Section edit prompt prepared without changing audio.",
        )

    if normalized_mode != "ace_step":
        return SectionEditResponse(
            status="not_supported",
            mode=normalized_mode,
            section_name=request.section_name,
            edit_prompt=edit_prompt,
            warnings=[f"Section editing mode '{normalized_mode}' is not supported."],
            diagnostics=GenerationDiagnostics(
                generator_name="section_editor",
                status="not_supported",
                failed_step="section_editing",
                error_message=f"Unsupported section editing mode: {normalized_mode}",
                suggested_fix="Use SECTION_EDITING_MODE=prompt_only or ace_step.",
            ),
            message="Unsupported section editing mode.",
        )

    if ace_step_editor is None:
        return _ace_not_implemented_response(request, edit_prompt, "ACE-Step edit function is not configured.")

    started_at = now_utc()
    try:
        result = ace_step_editor(
            source_audio_path=request.source_audio_path,
            section_name=request.section_name,
            section_start_seconds=request.section_start_seconds,
            section_end_seconds=request.section_end_seconds,
            edit_prompt=edit_prompt,
            output_dir=output_dir,
            job_id=request.source_job_id or "section_edit",
            timeout_seconds=timeout_seconds,
            bpm=request.bpm,
            key=request.key,
            language=request.language,
            duration_seconds=request.duration_seconds,
            repaint_mode=request.repaint_mode,
            repaint_strength=request.repaint_strength,
            boundary_crossfade_seconds=request.boundary_crossfade_seconds,
        )
    except Exception as exc:
        return SectionEditResponse(
            status="failed",
            mode="ace_step",
            section_name=request.section_name,
            edit_prompt=edit_prompt,
            warnings=[f"ACE-Step section edit crashed safely: {exc}"],
            diagnostics=GenerationDiagnostics(
                generator_name="ACE-Step",
                status="failed",
                started_at=started_at,
                finished_at=now_utc(),
                failed_step="ace_step_section_edit",
                error_message=f"ACE-Step section edit crashed safely: {exc}",
                suggested_fix="Verify the ACE-Step repaint service and selected instrumental, then retry.",
            ),
            message="ACE-Step section edit failed.",
        )

    success = bool(getattr(result, "success", False))
    output_path = getattr(result, "output_path", None)
    logs = list(getattr(result, "logs", []) or [])
    error_message = getattr(result, "error_message", None)
    suggested_fix = getattr(result, "suggested_fix", None)
    command_used = getattr(result, "command_used", None)
    edit_metadata = dict(getattr(result, "metadata", {}) or {})

    if not success:
        status = "not_implemented" if "not implemented" in (error_message or "").lower() else "failed"
        return SectionEditResponse(
            status=status,
            mode="ace_step",
            section_name=request.section_name,
            edit_prompt=edit_prompt,
            output_audio_path=output_path,
            edit_metadata=edit_metadata,
            warnings=[error_message] if error_message else ["ACE-Step section edit did not produce audio."],
            diagnostics=GenerationDiagnostics(
                generator_name=getattr(result, "generator_name", "ACE-Step"),
                status=status,
                started_at=getattr(result, "started_at", started_at),
                finished_at=getattr(result, "finished_at", now_utc()),
                duration_seconds=getattr(result, "duration_seconds", None),
                failed_step="ace_step_section_edit",
                error_message=error_message or "ACE-Step section edit did not produce audio.",
                last_logs=logs[-40:],
                suggested_fix=suggested_fix or "Verify the ACE-Step repaint service and selected instrumental, then retry.",
                command_used=command_used,
            ),
            message="ACE-Step section edit is not available." if status == "not_implemented" else "ACE-Step section edit failed.",
        )

    quality_report = validate_audio_file(output_path, generator_name="ACE-Step section_edit")
    output_url = url_for_path(output_path) if output_path and url_for_path else None
    status = "completed" if quality_report.passed else "failed_validation"
    return SectionEditResponse(
        status=status,
        mode="ace_step",
        section_name=request.section_name,
        edit_prompt=edit_prompt,
        output_audio_path=output_path,
        output_audio_url=output_url,
        quality_report=quality_report,
        edit_metadata=edit_metadata,
        warnings=[*quality_report.validation_errors, *quality_report.warnings],
        diagnostics=GenerationDiagnostics(
            generator_name=getattr(result, "generator_name", "ACE-Step"),
            status=status,
            started_at=getattr(result, "started_at", started_at),
            finished_at=getattr(result, "finished_at", now_utc()),
            duration_seconds=getattr(result, "duration_seconds", None),
            failed_step=None if quality_report.passed else "section_audio_validation",
            error_message=None if quality_report.passed else "Edited section audio failed validation.",
            last_logs=logs[-40:],
            suggested_fix=None if quality_report.passed else "Review section edit output and try a simpler instruction.",
            command_used=command_used,
        ),
        message="Section audio edited successfully." if quality_report.passed else "Section audio was created but failed validation.",
    )


def resolve_output_dir(output_dir: str | Path) -> Path:
    path = Path(output_dir)
    if not path.is_absolute():
        path = BACKEND_ROOT / path
    return path.resolve()


def _ace_not_implemented_response(request: SectionEditRequest, edit_prompt: str, reason: str) -> SectionEditResponse:
    return SectionEditResponse(
        status="not_implemented",
        mode="ace_step",
        section_name=request.section_name,
        edit_prompt=edit_prompt,
        warnings=[reason],
        diagnostics=GenerationDiagnostics(
            generator_name="ACE-Step",
            status="not_implemented",
            failed_step="ace_step_section_edit",
            error_message=reason,
            suggested_fix="Configure the ACE-Step repaint editor callback.",
        ),
        message="ACE-Step section edit callback is not configured.",
    )


def _style_bits(request: SectionEditRequest) -> list[str]:
    bits: list[str] = []
    for value in (
        request.genre,
        request.production_style,
        request.arrangement_style,
        f"{request.bpm} BPM" if request.bpm else None,
        request.key,
    ):
        if value:
            bits.append(_sanitize_reference_language(str(value)))
    if request.mood_tags:
        bits.append("mood: " + ", ".join(_clean_phrase(tag) for tag in request.mood_tags if _clean_phrase(tag)))
    if request.instruments:
        bits.append("instruments: " + ", ".join(_clean_phrase(item) for item in request.instruments if _clean_phrase(item)))
    return [bit for bit in bits if bit]


def _sanitize_reference_language(text: str) -> str:
    sanitized = text or ""
    lowered = sanitized.lower()
    for reference, replacement in FAMOUS_REFERENCE_REPLACEMENTS.items():
        if reference in lowered:
            sanitized = _replace_case_insensitive(sanitized, reference, replacement)
            lowered = sanitized.lower()
    return sanitized.replace("exactly like", "in the broad style of").replace("copy", "reference broadly")


def _replace_case_insensitive(text: str, needle: str, replacement: str) -> str:
    lower_text = text.lower()
    lower_needle = needle.lower()
    start = lower_text.find(lower_needle)
    while start != -1:
        end = start + len(needle)
        text = text[:start] + replacement + text[end:]
        lower_text = text.lower()
        start = lower_text.find(lower_needle, start + len(replacement))
    return text


def _clean_phrase(value: str | None) -> str:
    return " ".join(str(value or "").strip().split())


def _trim(value: str | None, limit: int) -> str:
    text = _clean_phrase(value)
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."
