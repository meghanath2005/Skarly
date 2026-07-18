from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
from typing import Any, Callable

from ..audio_validation import validate_audio_file
from ..models import GenerationDiagnostics, QualityReport, StemSeparationResponse

BACKEND_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STEMS = ["vocals", "drums", "bass", "other"]
SUPPORTED_AUDIO_SUFFIXES = {".wav", ".mp3", ".flac", ".m4a", ".aac", ".ogg"}


def separate_stems(
    audio_path: str | Path,
    output_dir: str | Path,
    job_id: str | None = None,
    stems: list[str] | None = None,
    engine: str = "demucs",
    timeout_seconds: int = 900,
    *,
    enabled: bool = True,
    demucs_cli_path: str = "python -m demucs",
    demucs_model: str = "htdemucs_ft",
    demucs_device: str | None = "cuda",
    url_for_path: Callable[[str], str | None] | None = None,
) -> StemSeparationResponse:
    selected_stems = _normalize_stems(stems)
    normalized_engine = (engine or "demucs").strip().lower()
    source = Path(audio_path).expanduser()
    if not source.is_absolute():
        source = (BACKEND_ROOT / source).resolve()
    else:
        source = source.resolve()

    if not enabled:
        return _response(
            status="not_enabled",
            engine=normalized_engine,
            source_audio_path=str(source),
            warnings=["Stem separation is disabled. Set STEMS_ENABLED=true to enable it."],
            diagnostics=GenerationDiagnostics(
                generator_name=normalized_engine,
                status="not_enabled",
                failed_step="stem_separation",
                error_message="Stem separation is disabled.",
                suggested_fix="Set STEMS_ENABLED=true and configure Demucs before separating stems.",
            ),
        )

    if not source.exists() or not source.is_file():
        return _response(
            status="not_found",
            engine=normalized_engine,
            source_audio_path=str(source),
            warnings=["Source audio file does not exist."],
            diagnostics=GenerationDiagnostics(
                generator_name=normalized_engine,
                status="not_found",
                failed_step="stem_separation",
                error_message="Source audio file does not exist.",
                suggested_fix="Generate audio first or provide a valid audio_path.",
            ),
        )

    if normalized_engine != "demucs":
        return _response(
            status="failed",
            engine=normalized_engine,
            source_audio_path=str(source),
            warnings=[f"Stem engine '{normalized_engine}' is not supported in Phase 9."],
            diagnostics=GenerationDiagnostics(
                generator_name=normalized_engine,
                status="failed",
                failed_step="stem_separation",
                error_message=f"Unsupported stem engine: {normalized_engine}",
                suggested_fix="Use STEMS_ENGINE=demucs for Phase 9 stem separation.",
            ),
        )

    started_at = _now()
    resolved_output_dir = resolve_output_dir(output_dir)
    run_id = _safe_name(job_id or source.stem or "stems")
    stems_dir = resolved_output_dir / run_id
    stems_dir.mkdir(parents=True, exist_ok=True)
    command = build_demucs_command(
        demucs_cli_path=demucs_cli_path,
        source_audio_path=source,
        output_dir=stems_dir,
        stems=selected_stems,
        model=demucs_model,
        device=demucs_device,
    )
    command_used = _command_for_display(command)

    if not _command_available(command[0]):
        return _response(
            status="unavailable",
            engine="demucs",
            source_audio_path=str(source),
            stems_dir=str(stems_dir),
            warnings=["Demucs command was not found."],
            diagnostics=GenerationDiagnostics(
                generator_name="demucs",
                status="unavailable",
                started_at=started_at,
                finished_at=_now(),
                duration_seconds=0.0,
                failed_step="stem_separation",
                error_message=f"Demucs command was not found: {command[0]}",
                last_logs=[],
                suggested_fix="Install Demucs or set DEMUCS_CLI_PATH to a working command.",
                command_used=command_used,
            ),
        )

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
            env=_isolated_python_environment(),
        )
    except subprocess.TimeoutExpired as exc:
        finished_at = _now()
        return _response(
            status="failed",
            engine="demucs",
            source_audio_path=str(source),
            stems_dir=str(stems_dir),
            warnings=[f"Demucs timed out after {timeout_seconds} seconds."],
            diagnostics=GenerationDiagnostics(
                generator_name="demucs",
                status="failed",
                started_at=started_at,
                finished_at=finished_at,
                duration_seconds=(finished_at - started_at).total_seconds(),
                failed_step="stem_separation",
                error_message=f"Demucs timed out after {timeout_seconds} seconds.",
                last_logs=_logs_from_output(exc.stdout, exc.stderr)[-40:],
                suggested_fix="Increase STEMS_TIMEOUT_SECONDS or try a shorter audio file.",
                command_used=command_used,
            ),
        )
    except Exception as exc:
        finished_at = _now()
        return _response(
            status="failed",
            engine="demucs",
            source_audio_path=str(source),
            stems_dir=str(stems_dir),
            warnings=[f"Demucs could not start: {exc}"],
            diagnostics=GenerationDiagnostics(
                generator_name="demucs",
                status="failed",
                started_at=started_at,
                finished_at=finished_at,
                duration_seconds=(finished_at - started_at).total_seconds(),
                failed_step="stem_separation",
                error_message=f"Demucs could not start: {exc}",
                last_logs=[],
                suggested_fix="Check DEMUCS_CLI_PATH and the Python environment that contains Demucs.",
                command_used=command_used,
            ),
        )

    finished_at = _now()
    logs = _logs_from_output(completed.stdout, completed.stderr)
    if completed.returncode != 0:
        return _response(
            status="failed",
            engine="demucs",
            source_audio_path=str(source),
            stems_dir=str(stems_dir),
            warnings=[f"Demucs exited with code {completed.returncode}."],
            diagnostics=GenerationDiagnostics(
                generator_name="demucs",
                status="failed",
                started_at=started_at,
                finished_at=finished_at,
                duration_seconds=(finished_at - started_at).total_seconds(),
                failed_step="stem_separation",
                error_message=f"Demucs exited with code {completed.returncode}.",
                last_logs=logs[-40:],
                suggested_fix="Install/configure Demucs, or verify that the input audio file can be decoded.",
                command_used=command_used,
            ),
        )

    discovered = discover_stem_files(stems_dir, selected_stems)
    if not discovered:
        return _response(
            status="failed",
            engine="demucs",
            source_audio_path=str(source),
            stems_dir=str(stems_dir),
            warnings=["Demucs completed but no stem files were found."],
            diagnostics=GenerationDiagnostics(
                generator_name="demucs",
                status="failed",
                started_at=started_at,
                finished_at=finished_at,
                duration_seconds=(finished_at - started_at).total_seconds(),
                failed_step="stem_discovery",
                error_message="Demucs completed but no stem files were found.",
                last_logs=logs[-40:],
                suggested_fix="Check Demucs output folder layout and adapt discover_stem_files() if needed.",
                command_used=command_used,
            ),
        )

    quality_reports: dict[str, QualityReport] = {}
    stem_paths: dict[str, str] = {}
    stem_urls: dict[str, str] = {}
    warnings: list[str] = []
    for stem_name, stem_path in discovered.items():
        stem_paths[stem_name] = str(stem_path)
        if url_for_path:
            stem_url = url_for_path(str(stem_path))
            if stem_url:
                stem_urls[stem_name] = stem_url
        report = validate_audio_file(stem_path, generator_name=f"demucs:{stem_name}")
        quality_reports[stem_name] = report
        warnings.extend(f"{stem_name}: {warning}" for warning in report.warnings)
        warnings.extend(f"{stem_name}: {error}" for error in report.validation_errors)

    missing_stems = [stem for stem in selected_stems if stem not in stem_paths]
    warnings.extend(f"Requested stem was not found: {stem}" for stem in missing_stems)
    valid_count = sum(1 for report in quality_reports.values() if report.passed)
    status = "completed" if not missing_stems and valid_count == len(quality_reports) else "completed_partial"
    if valid_count == 0:
        status = "failed"

    return _response(
        status=status,
        engine="demucs",
        source_audio_path=str(source),
        stems_dir=str(stems_dir),
        stem_paths=stem_paths,
        stem_urls=stem_urls,
        quality_reports=quality_reports,
        warnings=_dedupe(warnings),
        diagnostics=GenerationDiagnostics(
            generator_name="demucs",
            status=status,
            started_at=started_at,
            finished_at=finished_at,
            duration_seconds=(finished_at - started_at).total_seconds(),
            failed_step=None if status == "completed" else "stem_validation",
            error_message=None if status == "completed" else "Some requested stems were missing or failed validation.",
            last_logs=logs[-40:],
            suggested_fix=None if status == "completed" else "Review the warnings and Demucs output layout.",
            command_used=command_used,
        ),
    )


def build_demucs_command(
    *,
    demucs_cli_path: str,
    source_audio_path: str | Path,
    output_dir: str | Path,
    stems: list[str] | None = None,
    model: str = "htdemucs_ft",
    device: str | None = "cuda",
) -> list[str]:
    base = _base_command(demucs_cli_path)
    selected = _normalize_stems(stems)
    command = [*base, "-n", str(model or "htdemucs_ft"), "-o", str(output_dir)]
    if str(device or "").strip():
        command.extend(["-d", str(device).strip()])
    if selected == ["vocals"] or set(selected) == {"vocals", "no_vocals"}:
        command.append("--two-stems=vocals")
    # Demucs CLI flags vary by version. Keep future model, device, and format
    # adaptations centralized in this builder instead of scattering shell strings.
    command.append(str(source_audio_path))
    return command


def discover_stem_files(stems_dir: str | Path, stems: list[str] | None = None) -> dict[str, Path]:
    root = Path(stems_dir)
    selected = _normalize_stems(stems)
    files = sorted(path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in SUPPORTED_AUDIO_SUFFIXES)
    discovered: dict[str, Path] = {}
    for stem_name in selected:
        exact = [path for path in files if path.stem.lower() == stem_name]
        candidates = exact or [path for path in files if stem_name in path.stem.lower() or stem_name in str(path.parent).lower()]
        if candidates:
            discovered[stem_name] = candidates[0]
    return discovered


def resolve_output_dir(output_dir: str | Path) -> Path:
    path = Path(output_dir)
    if not path.is_absolute():
        path = BACKEND_ROOT / path
    return path.resolve()


def _response(
    *,
    status: str,
    engine: str,
    source_audio_path: str | None = None,
    stems_dir: str | None = None,
    stem_paths: dict[str, str] | None = None,
    stem_urls: dict[str, str] | None = None,
    diagnostics: GenerationDiagnostics | None = None,
    quality_reports: dict[str, QualityReport] | None = None,
    warnings: list[str] | None = None,
) -> StemSeparationResponse:
    return StemSeparationResponse(
        status=status,
        engine=engine,
        source_audio_path=source_audio_path,
        stems_dir=stems_dir,
        stem_paths=stem_paths or {},
        stem_urls=stem_urls or {},
        diagnostics=diagnostics,
        quality_reports=quality_reports or {},
        warnings=_dedupe(warnings or []),
    )


def _base_command(command_text: str | None) -> list[str]:
    raw = (command_text or "python -m demucs").strip()
    path_candidate = Path(raw.strip("\"'"))
    if path_candidate.exists():
        return [str(path_candidate)]
    windows_executable = re.match(
        r'^(?:"(?P<quoted>[A-Za-z]:[\\/].*?\.exe)"|(?P<plain>[A-Za-z]:[\\/].*?\.exe))(?:\s+(?P<args>.*))?$',
        raw,
        flags=re.IGNORECASE,
    )
    if windows_executable:
        executable = windows_executable.group("quoted") or windows_executable.group("plain")
        remainder = windows_executable.group("args") or ""
        return [executable, *[part.strip('"') for part in shlex.split(remainder, posix=False)]]
    return shlex.split(raw)


def _command_available(command_head: str) -> bool:
    if Path(command_head).is_file():
        return True
    return shutil.which(command_head) is not None


def _isolated_python_environment() -> dict[str, str]:
    """Prevent the backend's local dependency path from contaminating model venvs."""
    return {
        key: value
        for key, value in os.environ.items()
        if key.upper() not in {"PYTHONPATH", "PYTHONHOME"}
    }


def _logs_from_output(stdout: Any, stderr: Any) -> list[str]:
    logs: list[str] = []
    for value in (stdout, stderr):
        if value is None:
            continue
        if isinstance(value, bytes):
            text = value.decode("utf-8", errors="replace")
        else:
            text = str(value)
        logs.extend(line.strip() for line in text.splitlines() if line.strip())
    return logs


def _command_for_display(command: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in command)


def _normalize_stems(stems: list[str] | None) -> list[str]:
    result: list[str] = []
    for stem in stems or DEFAULT_STEMS:
        normalized = str(stem).strip().lower().replace(" ", "_")
        if normalized and normalized not in result:
            result.append(normalized)
    return result or list(DEFAULT_STEMS)


def _safe_name(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value)[:120] or "stems"


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in result:
            result.append(text)
    return result


def _now() -> datetime:
    return datetime.now(timezone.utc)
