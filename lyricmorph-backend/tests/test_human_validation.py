from __future__ import annotations

import json
from itertools import combinations
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.config import Settings
from app.main import app
from app.services import human_validation as human_validation_service
from training import human_validation


client = TestClient(app)


def write_source(backend_root: Path, relative: str, content: bytes) -> str:
    path = backend_root / "outputs" / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return "/" + path.relative_to(backend_root).as_posix()


def generation_payload(backend_root: Path, index: int, *, language: str = "hi") -> dict:
    job_id = f"generation_{index:02d}"
    versions = []
    for version_index in range(1, 6):
        backing_url = write_source(
            backend_root,
            f"skarly/job_{index:02d}/backing_{version_index}.wav",
            f"generation={index};version={version_index}".encode(),
        )
        versions.append({"name": f"Producer {version_index}", "backing_url": backing_url})
    pairs = []
    for left, right in combinations(range(1, 6), 2):
        pairs.append(
            {
                "left_index": left,
                "right_index": right,
                "embedding_similarity": 0.42,
                "drum_onset_similarity": 0.35,
                "chord_change_similarity": 0.38,
                "instrumentation_similarity": 0.4,
                "perceptual_similarity": 0.4,
            }
        )
    return {
        "job_id": job_id,
        "status": "ready",
        "result": {
            "versions": versions,
            "generation_telemetry": {"generation_backend": "cuda", "cpu_fallback": False},
            "arrangement_diversity": {"evaluated_pairs": 10, "pairs": pairs},
            "song_intelligence_map": {
                "duration_seconds": 120.0,
                "language": {"primary": language},
                "phrases": [
                    {"start_seconds": 15.0, "end_seconds": 24.0},
                    {"start_seconds": 55.0, "end_seconds": 66.0},
                    {"start_seconds": 96.0, "end_seconds": 108.0},
                ],
            },
        },
    }


def mix_payload(backend_root: Path, generation_id: str, profile: str) -> dict:
    job_id = f"mix_{generation_id.removeprefix('generation_')}_{profile}"
    final_mix_url = write_source(
        backend_root,
        f"skarly/{generation_id}/{profile}.mp3",
        f"{generation_id}:{profile}".encode(),
    )
    return {
        "job_id": job_id,
        "status": "ready",
        "result": {
            "generation_id": generation_id,
            "mix_profile": profile,
            "final_mix_url": final_mix_url,
            "duration_seconds": 120.0,
        },
    }


def fake_renderer(source: Path, destination: Path, starts, segment_seconds: float) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(source.read_bytes() + repr((tuple(starts), segment_seconds)).encode())


def fake_metrics(left: Path, right: Path) -> dict[str, float]:
    assert left.is_file() and right.is_file()
    return {
        "embedding_similarity": 0.96,
        "drum_onset_similarity": 0.91,
        "chord_change_similarity": 0.9,
        "instrumentation_similarity": 0.97,
        "perceptual_similarity": 0.94,
    }


@pytest.fixture()
def built_panel(tmp_path: Path) -> tuple[dict, Path]:
    backend_root = tmp_path / "backend"
    generations = [
        generation_payload(backend_root, index, language="hi" if index <= 4 else "en")
        for index in range(1, 7)
    ]
    mixes = [
        mix_payload(backend_root, f"generation_{index:02d}", profile)
        for index in range(1, 5)
        for profile in human_validation.MIX_PROFILES
    ]
    output = tmp_path / "panel"
    admin = human_validation.build_panel(
        generation_payloads=generations,
        mix_payloads=mixes,
        backend_root=backend_root,
        output_dir=output,
        renderer=fake_renderer,
        metric_extractor=fake_metrics,
    )
    return admin, output


def completed_ratings(admin: dict, rater_id: str) -> dict:
    return {
        "format": human_validation.RATINGS_FORMAT,
        "panel_id": admin["panel_id"],
        "rater_id": rater_id,
        "completed_at": "2026-07-15T00:00:00Z",
        "clarity": [
            {
                "task_id": task["task_id"],
                **{field: 5 for field in human_validation.CLARITY_FIELDS},
                "acceptable": True,
                "notes": "",
            }
            for task in admin["clarity_tasks"]
        ],
        "diversity": [
            {
                "task_id": task["task_id"],
                "too_similar": bool(task["is_control"]),
                "confidence": 5,
                "notes": "",
            }
            for task in admin["diversity_tasks"]
        ],
    }


def test_panel_is_blinded_complete_and_auditable(built_panel):
    admin, output = built_panel

    assert len(admin["clarity_tasks"]) == 12
    assert len(admin["diversity_tasks"]) == 70
    assert sum(task["is_control"] for task in admin["diversity_tasks"]) == 10
    assert all((output / task["audio_file"]).is_file() for task in admin["clarity_tasks"])
    assert (output / "public" / "index.html").is_file()
    assert (output / "ratings").is_dir()

    review_text = (output / "public" / "review_manifest.json").read_text(encoding="utf-8")
    review = json.loads(review_text)
    assert review["panel_id"] == admin["panel_id"]
    assert "mix_profile" not in review_text
    assert "generation_01" not in review_text
    assert "perceptual_similarity" not in review_text
    assert "is_control" not in review_text


def test_three_complete_reviewers_produce_release_ready_candidate(built_panel, tmp_path):
    admin, _ = built_panel
    ratings = [completed_ratings(admin, f"reviewer-{index}") for index in range(1, 4)]

    report, rows, calibration = human_validation.score_panel(admin, ratings)

    assert report["clarity_gate"]["passed"] is True
    assert report["diversity_gate"]["passed"] is True
    assert report["ready_for_release_review"] is True
    assert report["release_approved"] is False
    assert len(rows) == 210
    assert calibration["ready_for_review"] is True
    assert calibration["approved"] is False
    assert calibration["rater_count"] == 3
    assert calibration["distinct_pair_count"] == 70
    assert calibration["class_counts"] == {"too_similar": 30, "different": 180}

    output = tmp_path / "scores"
    human_validation.write_score_outputs(
        output_dir=output,
        report=report,
        calibration_rows=rows,
        calibration=calibration,
    )
    assert json.loads((output / "human_validation_report.json").read_text())["ready_for_release_review"] is True
    assert len((output / "diversity_ratings.jsonl").read_text().splitlines()) == 210


def test_release_approval_is_explicit_and_requires_passing_clarity(built_panel):
    admin, _ = built_panel
    ratings = [completed_ratings(admin, f"reviewer-{index}") for index in range(1, 4)]

    report, _, calibration = human_validation.score_panel(
        admin,
        ratings,
        approve=True,
        approved_by="release-owner",
    )
    assert report["release_approved"] is True
    assert calibration["approved"] is True
    assert calibration["approved_by"] == "release-owner"

    for item in ratings[0]["clarity"]:
        item.update({field: 2 for field in human_validation.CLARITY_FIELDS})
        item["acceptable"] = False
    with pytest.raises(ValueError, match="Cannot approve human validation"):
        human_validation.score_panel(admin, ratings, approve=True, approved_by="release-owner")


def test_ratings_must_cover_every_task_and_use_independent_ids(built_panel):
    admin, _ = built_panel
    first = completed_ratings(admin, "same-reviewer")
    incomplete = completed_ratings(admin, "reviewer-2")
    incomplete["diversity"].pop()

    with pytest.raises(ValueError, match="every diversity task"):
        human_validation.score_panel(admin, [first, incomplete])
    with pytest.raises(ValueError, match="distinct rater_id"):
        human_validation.score_panel(admin, [first, completed_ratings(admin, "same-reviewer")])


def test_excerpt_selection_prefers_three_phrase_regions():
    song_map = {
        "phrases": [
            {"start_seconds": 12, "end_seconds": 18},
            {"start_seconds": 55, "end_seconds": 65},
            {"start_seconds": 100, "end_seconds": 110},
        ]
    }
    starts = human_validation.select_excerpt_starts(120, song_map=song_map)

    assert starts == [10.0, 55.0, 100.0]
    assert human_validation.select_excerpt_starts(20, song_map=song_map) == [0.0]


def test_only_public_panel_files_are_served(monkeypatch, tmp_path):
    skarly_output = tmp_path / "outputs" / "skarly"
    panel_id = "human_panel_deadbeefdeadbeef"
    panel_root = skarly_output.parent / "validation" / panel_id
    public = panel_root / "public"
    public.mkdir(parents=True)
    (public / "index.html").write_text("<h1>Blinded panel</h1>", encoding="utf-8")
    (public / "clip.mp3").write_bytes(b"0123456789")
    (panel_root / "admin_manifest.json").write_text('{"secret": true}', encoding="utf-8")
    monkeypatch.setattr(main_module, "settings", Settings(skarly_output_dir=str(skarly_output)))

    page = client.get(f"/api/v2/validation-panels/{panel_id}")
    partial_audio = client.get(
        f"/api/v2/validation-panels/{panel_id}/clip.mp3",
        headers={"Range": "bytes=0-3"},
    )
    hidden_admin = client.get(f"/api/v2/validation-panels/{panel_id}/../admin_manifest.json")

    assert page.status_code == 200
    assert page.headers["cache-control"] == "no-store"
    assert partial_audio.status_code == 206
    assert partial_audio.content == b"0123"
    assert hidden_admin.status_code == 404
    assert human_validation_service.public_panel_file(
        skarly_output_dir=skarly_output,
        panel_id=panel_id,
        asset_path="clip.mp3",
    ) == (public / "clip.mp3").resolve()
    with pytest.raises(PermissionError):
        human_validation_service.public_panel_file(
            skarly_output_dir=skarly_output,
            panel_id=panel_id,
            asset_path="../admin_manifest.json",
        )
