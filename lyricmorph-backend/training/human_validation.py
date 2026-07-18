"""Build and score blinded human validation panels for Skarly V2.

The release gates in the Skarly V2 specification require human evidence for
Hindi lyric clarity and perceptual arrangement diversity.  This module keeps
that evidence reproducible: it builds an opaque listening panel from persisted
V2 jobs, validates complete ratings from independent reviewers, and emits the
JSONL consumed by ``training/calibrate_diversity.py``.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import random
import re
import shutil
import statistics
import subprocess
from typing import Any, Callable, Iterable, Mapping, Sequence

try:
    from training.calibrate_diversity import calibrate_rows
except ModuleNotFoundError:  # Allows ``python training/human_validation.py``.
    from calibrate_diversity import calibrate_rows


PANEL_FORMAT = "skarly_human_validation_panel_v1"
REVIEW_FORMAT = "skarly_human_validation_review_v1"
RATINGS_FORMAT = "skarly_human_validation_ratings_v1"
REPORT_FORMAT = "skarly_human_validation_report_v1"
MIX_PROFILES = ("vocal_forward", "balanced", "beat_forward")
CLARITY_FIELDS = (
    "lyric_intelligibility",
    "vocal_balance",
    "pronunciation_integrity",
    "pumping_absence",
)
MIN_RATERS = 3
MIN_HINDI_SOURCES = 3
MIN_GENUINE_DIVERSITY_PAIRS = 50
MIN_CONTROL_PAIRS = 10
PANEL_ID_PATTERN = re.compile(r"^human_panel_[a-f0-9]{16}$")


Renderer = Callable[[Path, Path, Sequence[float], float], None]
MetricExtractor = Callable[[Path, Path], dict[str, float]]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def resolve_output_url(backend_root: Path, value: str) -> Path:
    if not value or not str(value).startswith("/outputs/"):
        raise ValueError(f"Expected a persisted /outputs/ URL, received {value!r}")
    root = backend_root.resolve()
    candidate = (root / str(value).lstrip("/")).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"Output URL escapes the backend root: {value}") from exc
    if not candidate.is_file():
        raise FileNotFoundError(candidate)
    return candidate


def phrase_centres(song_map: Mapping[str, Any] | None) -> list[float]:
    centres: list[float] = []
    for phrase in (song_map or {}).get("phrases") or []:
        try:
            start = float(phrase["start_seconds"])
            end = float(phrase["end_seconds"])
        except (KeyError, TypeError, ValueError):
            continue
        if math.isfinite(start) and math.isfinite(end) and end > start:
            centres.append((start + end) / 2.0)
    return sorted(centres)


def select_excerpt_starts(
    duration_seconds: float,
    *,
    song_map: Mapping[str, Any] | None = None,
    alternate: bool = False,
    segment_seconds: float = 10.0,
) -> list[float]:
    """Select beginning/middle/end windows, preferring active vocal phrases."""

    duration = float(duration_seconds)
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("A positive finite duration is required")
    if duration <= segment_seconds * 3:
        return [0.0]
    fractions = (0.28, 0.58, 0.88) if alternate else (0.16, 0.50, 0.82)
    centres = phrase_centres(song_map)
    starts: list[float] = []
    maximum_start = max(0.0, duration - segment_seconds)
    for fraction in fractions:
        target = duration * fraction
        centre = min(centres, key=lambda value: abs(value - target)) if centres else target
        start = min(maximum_start, max(0.0, centre - (segment_seconds / 2.0)))
        starts.append(round(start, 3))
    return starts


def render_review_excerpt(
    source: Path,
    destination: Path,
    starts: Sequence[float],
    segment_seconds: float,
    *,
    ffmpeg_path: str = "ffmpeg",
) -> None:
    """Render a small MP3 montage without changing playback speed or pitch."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    if not starts:
        raise ValueError("At least one excerpt start is required")
    command = [ffmpeg_path, "-y", "-hide_banner", "-loglevel", "error", "-i", str(source)]
    if len(starts) == 1:
        command.extend(["-t", f"{segment_seconds * 3:.3f}", "-map", "0:a:0"])
    else:
        split_outputs = "".join(f"[s{index}]" for index in range(len(starts)))
        filters = [f"[0:a]asplit={len(starts)}{split_outputs}"]
        for index, start in enumerate(starts):
            filters.append(
                f"[s{index}]atrim=start={float(start):.3f}:duration={segment_seconds:.3f},"
                f"asetpts=PTS-STARTPTS[a{index}]"
            )
        concat_inputs = "".join(f"[a{index}]" for index in range(len(starts)))
        filters.append(f"{concat_inputs}concat=n={len(starts)}:v=0:a=1[out]")
        command.extend(["-filter_complex", ";".join(filters), "-map", "[out]"])
    command.extend(["-vn", "-ar", "48000", "-ac", "2", "-c:a", "libmp3lame", "-b:a", "160k", str(destination)])
    completed = subprocess.run(command, capture_output=True, text=True, timeout=180, check=False)
    if completed.returncode != 0 or not destination.is_file() or destination.stat().st_size == 0:
        detail = (completed.stderr or completed.stdout or "FFmpeg produced no output").strip()
        raise RuntimeError(f"Could not render review excerpt for {source.name}: {detail[:500]}")


def control_similarity_metrics(left_path: Path, right_path: Path) -> dict[str, float]:
    """Measure a control pair with the exact evaluator used by generation."""

    import numpy as np
    from app.services import skarly_studio

    features = []
    for path in (left_path, right_path):
        audio, sample_rate = skarly_studio.load_audio_for_profile(path)
        mono = np.asarray(audio, dtype=np.float32).mean(axis=1)
        features.append(skarly_studio.extract_arrangement_audio_features(mono, sample_rate))
    return skarly_studio.arrangement_similarity_metrics(features[0], features[1])


def validate_generation(payload: Mapping[str, Any], *, require_cuda: bool) -> None:
    job_id = str(payload.get("job_id") or "generation")
    if payload.get("status") != "ready":
        raise ValueError(f"{job_id} is not ready")
    result = payload.get("result") or {}
    versions = result.get("versions") or []
    if len(versions) != 5:
        raise ValueError(f"{job_id} must contain exactly five versions")
    diversity = result.get("arrangement_diversity") or {}
    if int(diversity.get("evaluated_pairs") or 0) != 10 or len(diversity.get("pairs") or []) != 10:
        raise ValueError(f"{job_id} does not contain all ten diversity measurements")
    if require_cuda:
        telemetry = result.get("generation_telemetry") or {}
        if telemetry.get("generation_backend") != "cuda" or telemetry.get("cpu_fallback") is not False:
            raise ValueError(f"{job_id} does not prove CUDA generation without CPU fallback")


def validate_mix(payload: Mapping[str, Any]) -> None:
    job_id = str(payload.get("job_id") or "mix")
    if payload.get("status") != "ready":
        raise ValueError(f"{job_id} is not ready")
    result = payload.get("result") or {}
    if result.get("mix_profile") not in MIX_PROFILES:
        raise ValueError(f"{job_id} has an unsupported mix profile")
    if not result.get("generation_id") or not result.get("final_mix_url"):
        raise ValueError(f"{job_id} is missing generation or audio provenance")


def panel_identifier(
    generation_payloads: Sequence[Mapping[str, Any]],
    mix_payloads: Sequence[Mapping[str, Any]],
    seed: int,
) -> str:
    source_ids = sorted(str(payload.get("job_id") or "") for payload in generation_payloads)
    mix_ids = sorted(str(payload.get("job_id") or "") for payload in mix_payloads)
    digest = hashlib.sha256(("|".join(source_ids + mix_ids) + f"|{seed}").encode("utf-8")).hexdigest()
    return f"human_panel_{digest[:16]}"


def build_panel(
    *,
    generation_payloads: Sequence[Mapping[str, Any]],
    mix_payloads: Sequence[Mapping[str, Any]],
    backend_root: Path,
    output_dir: Path,
    seed: int = 5070,
    control_pairs: int = MIN_CONTROL_PAIRS,
    require_cuda: bool = True,
    renderer: Renderer | None = None,
    metric_extractor: MetricExtractor | None = None,
    ffmpeg_path: str = "ffmpeg",
) -> dict[str, Any]:
    """Create a portable, blinded panel plus an admin-only audit manifest."""

    if len(generation_payloads) < 5:
        raise ValueError("At least five five-version generations are required for 50 genuine pairs")
    if control_pairs < MIN_CONTROL_PAIRS:
        raise ValueError(f"At least {MIN_CONTROL_PAIRS} blinded control pairs are required")
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    public_dir = output_dir / "public"
    audio_dir = public_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    renderer = renderer or (lambda source, destination, starts, seconds: render_review_excerpt(
        source, destination, starts, seconds, ffmpeg_path=ffmpeg_path
    ))
    metric_extractor = metric_extractor or control_similarity_metrics
    rng = random.Random(seed)

    generations: dict[str, Mapping[str, Any]] = {}
    source_specs: dict[tuple[str, tuple[float, ...]], dict[str, Any]] = {}
    source_hash_cache: dict[Path, str] = {}

    def source_sha(path: Path) -> str:
        if path not in source_hash_cache:
            source_hash_cache[path] = sha256_file(path)
        return source_hash_cache[path]

    def register_audio(source: Path, starts: Sequence[float], *, duration: float) -> dict[str, Any]:
        key = (str(source.resolve()), tuple(float(value) for value in starts))
        if key in source_specs:
            return source_specs[key]
        identity = hashlib.sha256((key[0] + "|" + ",".join(f"{value:.3f}" for value in key[1])).encode("utf-8")).hexdigest()[:16]
        relative = Path("audio") / f"audio_{identity}.mp3"
        destination = public_dir / relative
        renderer(source, destination, starts, min(10.0, duration))
        spec = {
            "source_path": source,
            "source_sha256": source_sha(source),
            "audio_file": relative.as_posix(),
            "audio_sha256": sha256_file(destination),
            "render_starts_seconds": [float(value) for value in starts],
            "rendered_path": destination,
        }
        source_specs[key] = spec
        return spec

    genuine_tasks: list[dict[str, Any]] = []
    control_candidates: list[dict[str, Any]] = []
    for payload in generation_payloads:
        validate_generation(payload, require_cuda=require_cuda)
        job_id = str(payload["job_id"])
        if job_id in generations:
            raise ValueError(f"Duplicate generation job: {job_id}")
        generations[job_id] = payload
        result = payload["result"]
        song_map = result.get("song_intelligence_map") or {}
        duration = float(song_map.get("duration_seconds") or 0)
        if duration <= 0:
            raise ValueError(f"{job_id} has no decoded duration")
        standard_starts = select_excerpt_starts(duration, song_map=song_map)
        version_audio: dict[int, dict[str, Any]] = {}
        for index, version in enumerate(result["versions"], start=1):
            source = resolve_output_url(backend_root, str(version.get("backing_url") or ""))
            version_audio[index] = register_audio(source, standard_starts, duration=duration)
            control_candidates.append(
                {
                    "job_id": job_id,
                    "version_index": index,
                    "source": source,
                    "standard": version_audio[index],
                    "alternate_starts": select_excerpt_starts(duration, song_map=song_map, alternate=True),
                    "duration": duration,
                }
            )
        for pair in result["arrangement_diversity"]["pairs"]:
            left_index = int(pair["left_index"])
            right_index = int(pair["right_index"])
            metrics = {
                field: float(pair[field])
                for field in (
                    "embedding_similarity",
                    "drum_onset_similarity",
                    "chord_change_similarity",
                    "instrumentation_similarity",
                    "perceptual_similarity",
                )
            }
            genuine_tasks.append(
                {
                    "task_id": f"div_{hashlib.sha256(f'{job_id}:{left_index}:{right_index}'.encode()).hexdigest()[:16]}",
                    "pair_id": f"{job_id}:{left_index}-{right_index}",
                    "generation_id": job_id,
                    "left_version_index": left_index,
                    "right_version_index": right_index,
                    "left": version_audio[left_index],
                    "right": version_audio[right_index],
                    "metrics": metrics,
                    "is_control": False,
                    "control_expected_too_similar": None,
                }
            )

    if len(genuine_tasks) < MIN_GENUINE_DIVERSITY_PAIRS:
        raise ValueError(f"Need at least {MIN_GENUINE_DIVERSITY_PAIRS} genuine arrangement pairs")
    rng.shuffle(control_candidates)
    control_tasks: list[dict[str, Any]] = []
    for candidate in control_candidates[:control_pairs]:
        alternate = register_audio(candidate["source"], candidate["alternate_starts"], duration=candidate["duration"])
        metrics = metric_extractor(candidate["standard"]["rendered_path"], alternate["rendered_path"])
        control_id = f"{candidate['job_id']}:{candidate['version_index']}:same-arrangement-control"
        control_tasks.append(
            {
                "task_id": f"div_{hashlib.sha256(control_id.encode()).hexdigest()[:16]}",
                "pair_id": control_id,
                "generation_id": candidate["job_id"],
                "left_version_index": candidate["version_index"],
                "right_version_index": candidate["version_index"],
                "left": candidate["standard"],
                "right": alternate,
                "metrics": {key: float(value) for key, value in metrics.items()},
                "is_control": True,
                "control_expected_too_similar": True,
            }
        )

    clarity_tasks: list[dict[str, Any]] = []
    seen_clarity: set[tuple[str, str]] = set()
    for payload in mix_payloads:
        validate_mix(payload)
        result = payload["result"]
        generation_id = str(result["generation_id"])
        profile = str(result["mix_profile"])
        unique = (generation_id, profile)
        if unique in seen_clarity:
            raise ValueError(f"Duplicate clarity item for {generation_id} and {profile}")
        seen_clarity.add(unique)
        generation = generations.get(generation_id)
        if generation is None:
            raise ValueError(f"Mix {payload['job_id']} references a generation outside this panel")
        song_map = generation["result"].get("song_intelligence_map") or {}
        language = str((song_map.get("language") or {}).get("primary") or "").casefold()
        if language not in {"hi", "hindi"}:
            continue
        duration = float(result.get("duration_seconds") or song_map.get("duration_seconds") or 0)
        source = resolve_output_url(backend_root, str(result["final_mix_url"]))
        audio = register_audio(source, select_excerpt_starts(duration, song_map=song_map), duration=duration)
        task_identity = f"{payload['job_id']}:{generation_id}:{profile}"
        clarity_tasks.append(
            {
                "task_id": f"clarity_{hashlib.sha256(task_identity.encode()).hexdigest()[:16]}",
                "mix_job_id": str(payload["job_id"]),
                "generation_id": generation_id,
                "mix_profile": profile,
                "language": language,
                "audio": audio,
            }
        )

    hindi_sources = {task["generation_id"] for task in clarity_tasks}
    if len(hindi_sources) < MIN_HINDI_SOURCES:
        raise ValueError(f"Clarity panel needs all three mix modes for at least {MIN_HINDI_SOURCES} Hindi sources")
    for generation_id in hindi_sources:
        profiles = {task["mix_profile"] for task in clarity_tasks if task["generation_id"] == generation_id}
        if profiles != set(MIX_PROFILES):
            raise ValueError(f"Hindi source {generation_id} is missing one or more mix profiles")

    diversity_tasks = genuine_tasks + control_tasks
    rng.shuffle(diversity_tasks)
    rng.shuffle(clarity_tasks)
    for task in diversity_tasks:
        if rng.random() < 0.5:
            task["left"], task["right"] = task["right"], task["left"]

    source_ids = sorted(generations)
    mix_ids = sorted(str(payload["job_id"]) for payload in mix_payloads)
    panel_id = panel_identifier(generation_payloads, mix_payloads, seed)
    admin_manifest = {
        "format": PANEL_FORMAT,
        "panel_id": panel_id,
        "created_at": utc_now(),
        "blinding_seed": seed,
        "source_generation_ids": source_ids,
        "source_mix_job_ids": mix_ids,
        "requirements": {
            "minimum_independent_raters": MIN_RATERS,
            "minimum_hindi_sources": MIN_HINDI_SOURCES,
            "minimum_genuine_diversity_pairs": MIN_GENUINE_DIVERSITY_PAIRS,
            "minimum_control_pairs": MIN_CONTROL_PAIRS,
        },
        "clarity_tasks": [
            {
                "task_id": task["task_id"],
                "mix_job_id": task["mix_job_id"],
                "generation_id": task["generation_id"],
                "mix_profile": task["mix_profile"],
                "language": task["language"],
                "audio_file": (Path("public") / task["audio"]["audio_file"]).as_posix(),
                "source_sha256": task["audio"]["source_sha256"],
                "audio_sha256": task["audio"]["audio_sha256"],
                "render_starts_seconds": task["audio"]["render_starts_seconds"],
            }
            for task in clarity_tasks
        ],
        "diversity_tasks": [
            {
                "task_id": task["task_id"],
                "pair_id": task["pair_id"],
                "generation_id": task["generation_id"],
                "left_version_index": task["left_version_index"],
                "right_version_index": task["right_version_index"],
                "left_audio_file": (Path("public") / task["left"]["audio_file"]).as_posix(),
                "right_audio_file": (Path("public") / task["right"]["audio_file"]).as_posix(),
                "left_audio_sha256": task["left"]["audio_sha256"],
                "right_audio_sha256": task["right"]["audio_sha256"],
                "metrics": task["metrics"],
                "is_control": task["is_control"],
                "control_expected_too_similar": task["control_expected_too_similar"],
            }
            for task in diversity_tasks
        ],
    }
    review_manifest = {
        "format": REVIEW_FORMAT,
        "panel_id": panel_id,
        "instructions": {
            "clarity": "Rate only what you hear. Audio labels are blinded. Montage jumps are intentional and are not mix defects.",
            "diversity": "Choose too similar when both clips sound like the same producer arrangement, even if mastering or song position differs.",
        },
        "clarity_tasks": [
            {"task_id": task["task_id"], "audio_file": task["audio"]["audio_file"]}
            for task in clarity_tasks
        ],
        "diversity_tasks": [
            {
                "task_id": task["task_id"],
                "left_audio_file": task["left"]["audio_file"],
                "right_audio_file": task["right"]["audio_file"],
            }
            for task in diversity_tasks
        ],
    }
    atomic_json(output_dir / "admin_manifest.json", admin_manifest)
    atomic_json(public_dir / "review_manifest.json", review_manifest)
    (public_dir / "index.html").write_text(render_review_html(review_manifest), encoding="utf-8")
    (output_dir / "README.md").write_text(panel_readme(panel_id), encoding="utf-8")
    (output_dir / "ratings").mkdir(exist_ok=True)
    return admin_manifest


def render_review_html(review_manifest: Mapping[str, Any]) -> str:
    embedded = json.dumps(review_manifest, ensure_ascii=False).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">
<title>Skarly blinded listening panel</title>
<style>
:root{{--ink:#172033;--muted:#59657a;--line:#d9deea;--paper:#fff;--wash:#f3f5fa;--accent:#6d4aff}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--wash);color:var(--ink);font:15px/1.5 system-ui,sans-serif}}
main{{max-width:980px;margin:auto;padding:28px 18px 80px}} h1{{margin:0 0 6px;font-size:30px}} h2{{margin-top:34px}}
.notice,.task{{background:var(--paper);border:1px solid var(--line);border-radius:14px;padding:18px;margin:14px 0;box-shadow:0 3px 12px #1720330a}}
.task h3{{margin:0 0 10px}} .muted{{color:var(--muted)}} audio{{width:100%;margin:7px 0 12px}}
.scores{{display:grid;grid-template-columns:repeat(auto-fit,minmax(205px,1fr));gap:12px}} fieldset{{border:1px solid var(--line);border-radius:10px;padding:10px}}
legend{{font-weight:650}} label{{margin-right:10px;white-space:nowrap}} input[type=text]{{width:100%;padding:10px;border:1px solid var(--line);border-radius:8px}}
textarea{{width:100%;min-height:55px;border:1px solid var(--line);border-radius:8px;padding:8px}}
.sticky{{position:sticky;bottom:10px;background:#172033;color:white;padding:12px 14px;border-radius:12px;display:flex;gap:12px;align-items:center;justify-content:space-between}}
button{{border:0;border-radius:9px;background:var(--accent);color:white;font-weight:700;padding:11px 18px;cursor:pointer}} .error{{color:#ffcfcc}}
.pair{{display:grid;grid-template-columns:1fr 1fr;gap:14px}} @media(max-width:650px){{.pair{{grid-template-columns:1fr}}}}
</style></head><body><main>
<h1>Skarly blinded listening panel</h1><p class=\"muted\">Judge the audio, not the label. Use headphones in a quiet room.</p>
<div class=\"notice\"><label><strong>Reviewer ID</strong><input id=\"rater\" type=\"text\" placeholder=\"Use the ID assigned by the study coordinator\"></label>
<p>Do not discuss answers with other reviewers. The clips are short montages from the beginning, middle and end; the montage jumps are intentional.</p></div>
<h2>Hindi vocal clarity</h2><p>Score 1 (poor) to 5 (excellent). “Acceptable” means you would approve this mix for a creator-facing beta.</p><div id=\"clarity\"></div>
<h2>Producer diversity</h2><p>Two clips are <em>too similar</em> when they feel like the same producer arrangement, even if loudness, mastering or song position differs.</p><div id=\"diversity\"></div>
<div class=\"sticky\"><span id=\"status\">Complete every item before export.</span><button id=\"export\">Export ratings JSON</button></div>
</main><script>
const panel={embedded};
const scoreNames={{lyric_intelligibility:'Lyric intelligibility',vocal_balance:'Vocal/music balance',pronunciation_integrity:'Hindi pronunciation intact',pumping_absence:'No distracting pumping'}};
const radio=(name,value,label)=>`<label><input type=\"radio\" name=\"${{name}}\" value=\"${{value}}\">${{label}}</label>`;
const clarity=document.querySelector('#clarity');
panel.clarity_tasks.forEach((task,index)=>{{const el=document.createElement('section');el.className='task';el.dataset.task=task.task_id;el.innerHTML=`<h3>Clarity ${{index+1}} of ${{panel.clarity_tasks.length}}</h3><audio controls preload=\"metadata\" src=\"${{task.audio_file}}\"></audio><div class=\"scores\">${{Object.entries(scoreNames).map(([key,label])=>`<fieldset data-field=\"${{key}}\"><legend>${{label}}</legend>${{[1,2,3,4,5].map(v=>radio(task.task_id+'_'+key,v,v)).join('')}}</fieldset>`).join('')}}<fieldset data-field=\"acceptable\"><legend>Overall beta acceptable?</legend>${{radio(task.task_id+'_acceptable','true','Yes')}}${{radio(task.task_id+'_acceptable','false','No')}}</fieldset></div><p><textarea data-notes placeholder=\"Optional note\"></textarea></p>`;clarity.appendChild(el);}});
const diversity=document.querySelector('#diversity');
panel.diversity_tasks.forEach((task,index)=>{{const el=document.createElement('section');el.className='task';el.dataset.task=task.task_id;el.innerHTML=`<h3>Pair ${{index+1}} of ${{panel.diversity_tasks.length}}</h3><div class=\"pair\"><div><strong>Clip A</strong><audio controls preload=\"metadata\" src=\"${{task.left_audio_file}}\"></audio></div><div><strong>Clip B</strong><audio controls preload=\"metadata\" src=\"${{task.right_audio_file}}\"></audio></div></div><fieldset data-field=\"too_similar\"><legend>Your judgement</legend>${{radio(task.task_id+'_similar','false','Clearly different producer arrangements')}}${{radio(task.task_id+'_similar','true','Too similar / same arrangement')}}</fieldset><fieldset data-field=\"confidence\"><legend>Confidence</legend>${{[1,2,3,4,5].map(v=>radio(task.task_id+'_confidence',v,v)).join('')}}</fieldset><p><textarea data-notes placeholder=\"Optional note\"></textarea></p>`;diversity.appendChild(el);}});
const selected=name=>{{const el=document.querySelector(`input[name=\"${{name}}\"]:checked`);return el?el.value:null}};
document.querySelector('#export').addEventListener('click',()=>{{const rater=document.querySelector('#rater').value.trim();const errors=[];if(!rater)errors.push('Reviewer ID is required.');
const clarityRatings=panel.clarity_tasks.map(task=>{{const item={{task_id:task.task_id}};Object.keys(scoreNames).forEach(key=>{{const value=selected(task.task_id+'_'+key);if(!value)errors.push(`${{task.task_id}}: ${{key}} missing`);item[key]=value?Number(value):null;}});const acceptable=selected(task.task_id+'_acceptable');if(acceptable===null)errors.push(`${{task.task_id}}: acceptable missing`);item.acceptable=acceptable==='true';item.notes=document.querySelector(`[data-task=\"${{task.task_id}}\"] [data-notes]`).value.trim();return item;}});
const diversityRatings=panel.diversity_tasks.map(task=>{{const similar=selected(task.task_id+'_similar'),confidence=selected(task.task_id+'_confidence');if(similar===null)errors.push(`${{task.task_id}}: judgement missing`);if(confidence===null)errors.push(`${{task.task_id}}: confidence missing`);return {{task_id:task.task_id,too_similar:similar==='true',confidence:confidence?Number(confidence):null,notes:document.querySelector(`[data-task=\"${{task.task_id}}\"] [data-notes]`).value.trim()}};}});
const status=document.querySelector('#status');if(errors.length){{status.className='error';status.textContent=`${{errors.length}} answers remain. First: ${{errors[0]}}`;return;}}
const payload={{format:'{RATINGS_FORMAT}',panel_id:panel.panel_id,rater_id:rater,completed_at:new Date().toISOString(),clarity:clarityRatings,diversity:diversityRatings}};const blob=new Blob([JSON.stringify(payload,null,2)+'\\n'],{{type:'application/json'}});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=`${{panel.panel_id}}_${{rater.replace(/[^a-z0-9_-]+/gi,'_')}}.json`;a.click();URL.revokeObjectURL(url);status.className='';status.textContent='Ratings exported. Send the JSON file to the study coordinator.';}});
</script></body></html>"""


def panel_readme(panel_id: str) -> str:
    return f"""# Skarly human validation panel

Panel: `{panel_id}`

1. Open `http://127.0.0.1:8090/api/v2/validation-panels/{panel_id}` while the backend is running.
2. Use headphones, enter the assigned reviewer ID, and complete every item independently.
3. Export the ratings JSON and place it in `ratings/`.
4. After at least three independent reviewers finish, run the score command documented in `training/README.md`.

Only `public/` is served to reviewers. `admin_manifest.json` contains the blinded mappings and machine metrics; keep it with the release evidence and do not show it to reviewers before they finish.
"""


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain one JSON object")
    return payload


def validate_ratings(admin: Mapping[str, Any], payload: Mapping[str, Any], *, source: str = "ratings") -> str:
    if payload.get("format") != RATINGS_FORMAT:
        raise ValueError(f"{source} has an unsupported ratings format")
    if payload.get("panel_id") != admin.get("panel_id"):
        raise ValueError(f"{source} belongs to a different panel")
    rater_id = str(payload.get("rater_id") or "").strip()
    if not rater_id:
        raise ValueError(f"{source} has no rater_id")
    expected_clarity = {task["task_id"] for task in admin["clarity_tasks"]}
    expected_diversity = {task["task_id"] for task in admin["diversity_tasks"]}
    clarity = payload.get("clarity") or []
    diversity = payload.get("diversity") or []
    if {item.get("task_id") for item in clarity} != expected_clarity or len(clarity) != len(expected_clarity):
        raise ValueError(f"{source} does not rate every clarity task exactly once")
    if {item.get("task_id") for item in diversity} != expected_diversity or len(diversity) != len(expected_diversity):
        raise ValueError(f"{source} does not rate every diversity task exactly once")
    for item in clarity:
        for field in CLARITY_FIELDS:
            value = item.get(field)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 1 <= float(value) <= 5:
                raise ValueError(f"{source} {item.get('task_id')} {field} must be 1-5")
        if not isinstance(item.get("acceptable"), bool):
            raise ValueError(f"{source} {item.get('task_id')} acceptable must be boolean")
    for item in diversity:
        if not isinstance(item.get("too_similar"), bool):
            raise ValueError(f"{source} {item.get('task_id')} too_similar must be boolean")
        confidence = item.get("confidence")
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 1 <= float(confidence) <= 5:
            raise ValueError(f"{source} {item.get('task_id')} confidence must be 1-5")
    return rater_id


def rounded_mean(values: Iterable[float]) -> float:
    values = list(values)
    return round(statistics.fmean(values), 4) if values else 0.0


def score_panel(
    admin: Mapping[str, Any],
    ratings: Sequence[Mapping[str, Any]],
    *,
    approve: bool = False,
    approved_by: str | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    if admin.get("format") != PANEL_FORMAT:
        raise ValueError("Unsupported admin panel format")
    rater_ids: list[str] = []
    for index, payload in enumerate(ratings, start=1):
        rater_ids.append(validate_ratings(admin, payload, source=f"ratings[{index}]"))
    if len(set(rater_ids)) != len(rater_ids):
        raise ValueError("Each ratings file must use a distinct rater_id")

    clarity_admin = {task["task_id"]: task for task in admin["clarity_tasks"]}
    diversity_admin = {task["task_id"]: task for task in admin["diversity_tasks"]}
    clarity_by_profile: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    diversity_votes: dict[str, list[bool]] = defaultdict(list)
    calibration_rows: list[dict[str, Any]] = []
    for payload, rater_id in zip(ratings, rater_ids):
        for item in payload["clarity"]:
            clarity_by_profile[clarity_admin[item["task_id"]]["mix_profile"]].append(item)
        for item in payload["diversity"]:
            task = diversity_admin[item["task_id"]]
            diversity_votes[item["task_id"]].append(bool(item["too_similar"]))
            calibration_rows.append(
                {
                    "pair_id": task["pair_id"],
                    "rater_id": rater_id,
                    "too_similar": bool(item["too_similar"]),
                    **{key: float(value) for key, value in task["metrics"].items()},
                }
            )

    rater_ready = len(rater_ids) >= MIN_RATERS
    hindi_sources = {task["generation_id"] for task in admin["clarity_tasks"] if task.get("language") in {"hi", "hindi"}}
    profile_reports: dict[str, Any] = {}
    clarity_reasons: list[str] = []
    for profile in MIX_PROFILES:
        rows = clarity_by_profile.get(profile, [])
        field_medians = {
            field: round(float(statistics.median(float(row[field]) for row in rows)), 4) if rows else 0.0
            for field in CLARITY_FIELDS
        }
        acceptable_rate = rounded_mean(1.0 if row["acceptable"] else 0.0 for row in rows)
        severe_issue_rate = rounded_mean(
            1.0 if min(float(row[field]) for field in CLARITY_FIELDS) <= 2 else 0.0 for row in rows
        )
        profile_passed = bool(rows) and all(value >= 4.0 for value in field_medians.values()) and acceptable_rate >= 0.8 and severe_issue_rate <= 0.1
        if not profile_passed:
            clarity_reasons.append(f"{profile} did not meet median>=4, acceptable>=0.8, and severe-issue<=0.1")
        profile_reports[profile] = {
            "rating_count": len(rows),
            "median_scores": field_medians,
            "acceptable_rate": acceptable_rate,
            "severe_issue_rate": severe_issue_rate,
            "passed": profile_passed,
        }
    if not rater_ready:
        clarity_reasons.append(f"need at least {MIN_RATERS} independent raters")
    if len(hindi_sources) < MIN_HINDI_SOURCES:
        clarity_reasons.append(f"need at least {MIN_HINDI_SOURCES} Hindi sources")
    clarity_passed = not clarity_reasons

    genuine_tasks = [task for task in admin["diversity_tasks"] if not task["is_control"]]
    control_tasks = [task for task in admin["diversity_tasks"] if task["is_control"]]
    majority_agreements: list[float] = []
    for task_id, votes in diversity_votes.items():
        positives = sum(votes)
        majority_agreements.append(max(positives, len(votes) - positives) / len(votes))
    mean_majority_agreement = rounded_mean(majority_agreements)
    control_votes = [
        vote
        for task in control_tasks
        for vote in diversity_votes.get(task["task_id"], [])
        if task.get("control_expected_too_similar") is True
    ]
    control_accuracy = rounded_mean(1.0 if vote else 0.0 for vote in control_votes)
    diversity_reasons: list[str] = []
    if not rater_ready:
        diversity_reasons.append(f"need at least {MIN_RATERS} independent raters")
    if len(genuine_tasks) < MIN_GENUINE_DIVERSITY_PAIRS:
        diversity_reasons.append(f"need at least {MIN_GENUINE_DIVERSITY_PAIRS} genuine pairs")
    if len(control_tasks) < MIN_CONTROL_PAIRS:
        diversity_reasons.append(f"need at least {MIN_CONTROL_PAIRS} control pairs")
    if mean_majority_agreement < 0.8:
        diversity_reasons.append("mean reviewer majority agreement is below 0.8")
    if control_accuracy < 0.9:
        diversity_reasons.append("same-arrangement control accuracy is below 0.9")
    diversity_passed = not diversity_reasons

    ready_for_release_review = clarity_passed and diversity_passed
    if approve and not ready_for_release_review:
        raise ValueError("Cannot approve human validation: " + "; ".join(clarity_reasons + diversity_reasons))
    if approve and not str(approved_by or "").strip():
        raise ValueError("--approved-by is required with --approve")
    calibration = calibrate_rows(
        calibration_rows,
        approve=approve and ready_for_release_review,
        approved_by=approved_by,
    ) if calibration_rows else {
        "approved": False,
        "ready_for_review": False,
        "readiness_errors": ["no diversity ratings"],
    }
    ready_for_release_review = ready_for_release_review and bool(calibration.get("ready_for_review"))
    report = {
        "format": REPORT_FORMAT,
        "panel_id": admin["panel_id"],
        "scored_at": utc_now(),
        "rater_count": len(rater_ids),
        "rater_ids": sorted(rater_ids),
        "clarity_gate": {
            "passed": clarity_passed,
            "hindi_source_count": len(hindi_sources),
            "profiles": profile_reports,
            "reasons": clarity_reasons,
        },
        "diversity_gate": {
            "passed": diversity_passed,
            "genuine_pair_count": len(genuine_tasks),
            "control_pair_count": len(control_tasks),
            "mean_majority_agreement": mean_majority_agreement,
            "control_accuracy": control_accuracy,
            "reasons": diversity_reasons,
        },
        "calibration": {
            "calibration_id": calibration.get("calibration_id"),
            "approved": calibration.get("approved", False),
            "ready_for_review": calibration.get("ready_for_review", False),
            "sample_count": calibration.get("sample_count", 0),
            "class_counts": calibration.get("class_counts", {}),
        },
        "ready_for_release_review": ready_for_release_review,
        "release_approved": bool(calibration.get("approved")) and ready_for_release_review,
        "note": "This report closes only the human clarity/diversity beta gates; consented production training data remains a separate requirement.",
    }
    return report, calibration_rows, calibration


def write_score_outputs(
    *,
    output_dir: Path,
    report: Mapping[str, Any],
    calibration_rows: Sequence[Mapping[str, Any]],
    calibration: Mapping[str, Any],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    atomic_json(output_dir / "human_validation_report.json", report)
    atomic_json(output_dir / "diversity_calibration.json", calibration)
    ratings_path = output_dir / "diversity_ratings.jsonl"
    temporary = ratings_path.with_suffix(".jsonl.tmp")
    temporary.write_text(
        "".join(json.dumps(dict(row), ensure_ascii=False, sort_keys=True) + "\n" for row in calibration_rows),
        encoding="utf-8",
    )
    temporary.replace(ratings_path)


def parse_ids(values: Sequence[str]) -> list[str]:
    return [item.strip() for value in values for item in value.split(",") if item.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build", help="Build a blinded listening panel from ready V2 jobs")
    build.add_argument("--jobs-dir", type=Path, required=True)
    build.add_argument("--backend-root", type=Path, required=True)
    build.add_argument("--generation-ids", nargs="+", required=True)
    build.add_argument("--mix-ids", nargs="+", required=True)
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--seed", type=int, default=5070)
    build.add_argument("--control-pairs", type=int, default=MIN_CONTROL_PAIRS)
    build.add_argument("--ffmpeg", default="ffmpeg")
    build.add_argument("--allow-non-cuda", action="store_true")

    score = subparsers.add_parser("score", help="Validate and score completed reviewer JSON files")
    score.add_argument("--panel", type=Path, required=True, help="Panel directory containing admin_manifest.json")
    score.add_argument("--ratings", type=Path, required=True, help="Directory containing reviewer JSON files")
    score.add_argument("--output", type=Path, required=True)
    score.add_argument("--approve", action="store_true")
    score.add_argument("--approved-by")
    args = parser.parse_args()

    if args.command == "build":
        jobs_dir = args.jobs_dir.resolve()
        generation_ids = parse_ids(args.generation_ids)
        mix_ids = parse_ids(args.mix_ids)
        generations = [load_json(jobs_dir / f"{job_id}.json") for job_id in generation_ids]
        mixes = [load_json(jobs_dir / f"{job_id}.json") for job_id in mix_ids]
        panel_id = panel_identifier(generations, mixes, args.seed)
        requested_output = args.output.resolve()
        actual_output = requested_output if PANEL_ID_PATTERN.fullmatch(requested_output.name) else requested_output / panel_id
        result = build_panel(
            generation_payloads=generations,
            mix_payloads=mixes,
            backend_root=args.backend_root,
            output_dir=actual_output,
            seed=args.seed,
            control_pairs=args.control_pairs,
            require_cuda=not args.allow_non_cuda,
            ffmpeg_path=args.ffmpeg,
        )
        print(json.dumps({
            "panel_id": result["panel_id"],
            "output": str(actual_output),
            "clarity_tasks": len(result["clarity_tasks"]),
            "diversity_tasks": len(result["diversity_tasks"]),
        }, ensure_ascii=False))
        return

    admin = load_json(args.panel.resolve() / "admin_manifest.json")
    rating_paths = sorted(path for path in args.ratings.resolve().glob("*.json") if path.is_file())
    ratings = [load_json(path) for path in rating_paths]
    report, rows, calibration = score_panel(
        admin,
        ratings,
        approve=args.approve,
        approved_by=args.approved_by,
    )
    write_score_outputs(output_dir=args.output.resolve(), report=report, calibration_rows=rows, calibration=calibration)
    print(json.dumps({
        "output": str(args.output.resolve()),
        "rater_count": report["rater_count"],
        "ready_for_release_review": report["ready_for_release_review"],
        "release_approved": report["release_approved"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
