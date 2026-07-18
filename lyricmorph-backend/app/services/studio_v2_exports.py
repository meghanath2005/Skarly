from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import json
import shutil
import subprocess
from typing import Callable
from urllib.parse import quote, unquote
from uuid import uuid4
import zipfile

from ..models import SkarlyV2ExportResponse, StemSeparationResponse
from . import skarly_studio


def create_export_bundle(
    generation_job: dict,
    *,
    version_index: int,
    include_optional_stems: bool,
    exports_dir: str | Path,
    skarly_output_dir: str | Path,
    ffmpeg_path: str,
    timeout_sec: int,
    stem_separator: Callable[[Path, str], StemSeparationResponse] | None = None,
) -> SkarlyV2ExportResponse:
    result = generation_job.get("result") or {}
    versions = list(result.get("versions") or [])
    if version_index < 0 or version_index >= len(versions):
        raise ValueError("Selected arrangement is unavailable")
    version = versions[version_index]
    duration = float((result.get("song_intelligence_map") or {}).get("duration_seconds") or 0)
    if duration <= 0:
        raise ValueError("The generation is missing its decoded vocal duration")

    export_id = f"skarly_export_{uuid4().hex}"
    export_root = Path(exports_dir).expanduser().resolve()
    export_dir = (export_root / export_id).resolve()
    export_dir.relative_to(export_root)
    export_dir.mkdir(parents=True, exist_ok=False)

    source_final = skarly_path_from_url(str(version.get("final_mix_url") or ""), skarly_output_dir)
    source_backing = skarly_path_from_url(str(version.get("backing_url") or ""), skarly_output_dir)
    source_vocal = skarly_path_from_url(
        str(version.get("input_vocal_url") or result.get("vocal_url") or ""),
        skarly_output_dir,
    )
    final_wav = export_dir / "final_mix.wav"
    final_mp3 = export_dir / "final_mix.mp3"
    instrumental = export_dir / "instrumental.wav"
    processed_vocal = export_dir / "processed_vocal.wav"
    render_audio(source_final, final_wav, output_format="wav", ffmpeg_path=ffmpeg_path, timeout_sec=timeout_sec)
    render_audio(source_final, final_mp3, output_format="mp3", ffmpeg_path=ffmpeg_path, timeout_sec=timeout_sec)
    render_audio(source_backing, instrumental, output_format="wav", ffmpeg_path=ffmpeg_path, timeout_sec=timeout_sec)
    render_audio(source_vocal, processed_vocal, output_format="wav", ffmpeg_path=ffmpeg_path, timeout_sec=timeout_sec)

    durations: dict[str, float] = {}
    for name, path in {
        "final_wav": final_wav,
        "final_mp3": final_mp3,
        "instrumental": instrumental,
        "processed_vocal": processed_vocal,
    }.items():
        durations[name] = validate_export_duration(name, path, duration)

    analysis_path = export_dir / "analysis.json"
    analysis_url = str(result.get("analysis_url") or "")
    if analysis_url:
        shutil.copy2(skarly_path_from_url(analysis_url, skarly_output_dir), analysis_path)
    else:
        analysis_path.write_text(json.dumps(result.get("detected") or {}, indent=2, ensure_ascii=False), encoding="utf-8")
    song_map_path = export_dir / "song_map.json"
    song_map_path.write_text(
        json.dumps(result.get("song_intelligence_map") or {}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    metadata_path = export_dir / "ai_generation_metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "schema": "skarly-ai-generation-disclosure-v1",
                "generation_id": generation_job.get("job_id"),
                "analysis_id": generation_job.get("analysis_id"),
                "arrangement_index": version_index,
                "arrangement_name": version.get("name"),
                "arrangement_profile": version.get("style_family"),
                "producer_blueprint": version.get("blueprint") or {},
                "instruments": version.get("instruments") or [],
                "seed": version.get("seed"),
                "decoded_vocal_duration_seconds": duration,
                "model": (result.get("generation_telemetry") or {}).get("model"),
                "generation_backend": (result.get("generation_telemetry") or {}).get("generation_backend"),
                "cuda_device": (result.get("generation_telemetry") or {}).get("device"),
                "cpu_fallback": (result.get("generation_telemetry") or {}).get("cpu_fallback"),
                "arrangement_diversity": result.get("arrangement_diversity"),
                "disclosure": {
                    "human_performance": "The lead vocal is the creator's uploaded performance.",
                    "ai_generated_content": "The instrumental backing was generated with AI and mixed around the uploaded vocal.",
                    "voice_cloning": False,
                },
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    warnings: list[str] = []
    optional_files: dict[str, Path] = {}
    if include_optional_stems:
        stem_urls = version.get("stem_urls") or {}
        if isinstance(stem_urls, dict) and stem_urls:
            for raw_name, raw_url in stem_urls.items():
                source = skarly_path_from_url(str(raw_url), skarly_output_dir)
                add_optional_stem(
                    raw_name,
                    source,
                    export_dir=export_dir,
                    duration=duration,
                    ffmpeg_path=ffmpeg_path,
                    timeout_sec=timeout_sec,
                    optional_files=optional_files,
                    durations=durations,
                )
        elif stem_separator is not None:
            try:
                separated = stem_separator(
                    source_backing,
                    f"{generation_job.get('job_id') or 'generation'}_version_{version_index + 1}",
                )
                warnings.extend(separated.warnings)
                if separated.status in {"completed", "completed_partial"}:
                    for stem_name in ("drums", "bass", "other"):
                        source_value = separated.stem_paths.get(stem_name)
                        if not source_value:
                            continue
                        add_optional_stem(
                            stem_name,
                            Path(source_value).expanduser().resolve(),
                            export_dir=export_dir,
                            duration=duration,
                            ffmpeg_path=ffmpeg_path,
                            timeout_sec=timeout_sec,
                            optional_files=optional_files,
                            durations=durations,
                        )
                missing = [name for name in ("drums", "bass", "other") if f"stem_{name}" not in optional_files]
                if missing:
                    warnings.append(f"Optional separated stems were unavailable: {', '.join(missing)}.")
            except Exception as exc:
                warnings.append(f"Optional stem separation failed; core exports were preserved: {str(exc)[:240]}")
        else:
            warnings.append("Optional drums, bass, and other separated stems were not available; configure Demucs to create them on export.")

    artifacts: dict[str, Path] = {
        "final_wav": final_wav,
        "final_mp3": final_mp3,
        "instrumental": instrumental,
        "processed_vocal": processed_vocal,
        "analysis_json": analysis_path,
        "song_map_json": song_map_path,
        "ai_generation_metadata": metadata_path,
        **optional_files,
    }
    bundle_path = export_dir / "skarly_export_bundle.zip"
    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in artifacts.values():
            archive.write(path, arcname=path.name)
    artifacts["bundle_zip"] = bundle_path

    urls = {
        name: f"/outputs/exports/{quote(export_id, safe='')}/{quote(path.name, safe='')}"
        for name, path in artifacts.items()
    }
    hashes = {name: file_sha256(path) for name, path in artifacts.items()}
    return SkarlyV2ExportResponse(
        export_id=export_id,
        generation_id=str(generation_job.get("job_id") or ""),
        version_index=version_index,
        arrangement_name=str(version.get("name") or f"Arrangement {version_index + 1}"),
        duration_seconds=duration,
        files=urls,
        sha256=hashes,
        durations_seconds=durations,
        warnings=warnings,
    )


def skarly_path_from_url(value: str, output_dir: str | Path) -> Path:
    prefix = "/outputs/skarly/"
    decoded = unquote(str(value or "").split("?", 1)[0]).replace("\\", "/")
    if not decoded.startswith(prefix):
        raise ValueError("Expected a Skarly output URL")
    relative = decoded.removeprefix(prefix).lstrip("/")
    root = Path(output_dir).expanduser().resolve()
    candidate = (root / relative).resolve()
    candidate.relative_to(root)
    if not candidate.is_file():
        raise FileNotFoundError(candidate)
    return candidate


def render_audio(
    source: Path,
    target: Path,
    *,
    output_format: str,
    ffmpeg_path: str,
    timeout_sec: int,
) -> None:
    if source.suffix.lower() == f".{output_format}":
        shutil.copy2(source, target)
        return
    codec_args = ["-c:a", "pcm_s24le", "-ar", "44100"] if output_format == "wav" else ["-c:a", "libmp3lame", "-b:a", "320k"]
    completed = subprocess.run(
        [str(ffmpeg_path), "-y", "-hide_banner", "-loglevel", "error", "-i", str(source), "-vn", *codec_args, str(target)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=max(10, int(timeout_sec)),
        check=False,
    )
    if completed.returncode != 0 or not target.is_file():
        detail = " ".join(line.strip() for line in completed.stderr.splitlines() if line.strip())[-400:]
        raise RuntimeError(f"FFmpeg could not create {target.name}: {detail or 'unknown error'}")


def add_optional_stem(
    raw_name: object,
    source: Path,
    *,
    export_dir: Path,
    duration: float,
    ffmpeg_path: str,
    timeout_sec: int,
    optional_files: dict[str, Path],
    durations: dict[str, float],
) -> None:
    """Render one separated source as an exact-duration, DAW-ready WAV stem."""
    safe_name = "".join(
        character
        for character in str(raw_name).lower()
        if character.isalnum() or character in {"_", "-"}
    )
    if not safe_name:
        return
    if not source.is_file():
        raise FileNotFoundError(source)
    artifact_name = f"stem_{safe_name}"
    target = export_dir / f"{artifact_name}.wav"
    render_audio(source, target, output_format="wav", ffmpeg_path=ffmpeg_path, timeout_sec=timeout_sec)
    durations[artifact_name] = validate_export_duration(artifact_name, target, duration)
    optional_files[artifact_name] = target


def validate_export_duration(name: str, path: Path, duration: float) -> float:
    """Validate one exported audio artifact against the decoded vocal duration."""
    output_duration = float(skarly_studio.safe_duration_seconds(path) or 0)
    tolerance = max(0.08, duration * 0.001)
    if abs(output_duration - duration) > tolerance:
        raise RuntimeError(
            f"Export {name} duration {output_duration:.3f}s did not match decoded vocal duration {duration:.3f}s"
        )
    return round(output_duration, 6)


def file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
