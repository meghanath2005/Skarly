from __future__ import annotations

from training import audit_dataset_readiness as readiness
from training.audio_taxonomy import DEFAULT_HEAD_CLASSES


def complete_row(index: int) -> dict[str, object]:
    languages = DEFAULT_HEAD_CLASSES["language"]
    deliveries = DEFAULT_HEAD_CLASSES["singing_speech"]
    tempos = DEFAULT_HEAD_CLASSES["tempo_family"]
    melodic = DEFAULT_HEAD_CLASSES["melodic_character"]
    return {
        "audio_path": f"clip-{index}.wav",
        "source": "creator_opt_in_vocal",
        "rights_confirmed": True,
        "contributor_id": f"creator-{index}",
        "consent_record_id": f"consent-{index}",
        "copyright_owner": f"creator-{index}",
        "permitted_training_use": "Skarly audio-intelligence training",
        "commercial_use_permission": False,
        "revocation_policy": "Remove from future versions on request",
        "audio_role": "vocal_only",
        "recording_conditions": "reviewed dry vocal",
        "singer_id": f"singer-{index}",
        "dataset_version": "test-v1",
        "label_origin": "creator_confirmed",
        "quality_review_status": "approved",
        "language": languages[index % len(languages)],
        "singing_speech": deliveries[index % len(deliveries)],
        "vocal_techniques": list(DEFAULT_HEAD_CLASSES["vocal_technique"]),
        "moods": list(DEFAULT_HEAD_CLASSES["mood"]),
        "genres": list(DEFAULT_HEAD_CLASSES["genre"]),
        "tempo_family": tempos[index % len(tempos)],
        "melodic_character": melodic[index % len(melodic)],
        "in_distribution": index % 2 == 0,
    }


def test_readiness_audit_can_prove_all_eight_heads(monkeypatch):
    monkeypatch.setattr(readiness, "PRODUCTION_TARGETS", {head: (1, 1) for head in DEFAULT_HEAD_CLASSES})
    report = readiness.audit_rows([complete_row(index) for index in range(12)])
    assert report["metadata_complete"] is True
    assert report["dataset_role_violations"] == []
    assert report["all_eight_heads_production_ready"] is True
    assert report["release_ready"] is True
    assert set(report["heads"]) == set(DEFAULT_HEAD_CLASSES)


def test_readiness_audit_exposes_missing_singers_and_fleurs_role_misuse():
    row = complete_row(0)
    row["source"] = "google_fleurs_cc_by"
    row["singer_id"] = None
    report = readiness.audit_rows([row])
    assert report["release_ready"] is False
    assert report["required_metadata_missing"]["singer_id"] == 1
    assert report["heads"]["language"]["rows_missing_singer_id"] == 1
    assert "genres" in report["dataset_role_violations"][0]["prohibited_labels"]
