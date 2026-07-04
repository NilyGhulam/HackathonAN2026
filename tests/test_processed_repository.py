from __future__ import annotations

import json
from pathlib import Path

from app.repositories.processed_repository import ProcessedRepository


def test_processed_repository_maps_payload(tmp_path: Path) -> None:
    payload = {
        "schema_version": "0.1.0",
        "processing": {
            "run_id": "run_test",
            "processed_at": "2026-07-03T12:00:00Z",
            "model": "test",
            "prompt_version": "test",
            "status": "validated",
            "global_confidence": 0.9,
        },
        "raw_source": {
            "id": "source_1",
            "type": "amendment",
            "institution": "assemblee_nationale",
            "date": "2026-07-03",
            "title": "Amendement officiel",
            "url": "https://example.test/source",
            "original_text": "Texte source",
            "metadata": {"speaker": "Députée Exemple"},
        },
        "extracted_traces": [
            {
                "id": "trace_1",
                "source_id": "source_1",
                "summary": "Demande une clarification du calendrier.",
                "argument_role": "clarification",
                "position": "neutral",
                "public_policy_domains": ["sante"],
                "affected_publics": ["patients"],
                "issues": ["calendrier"],
                "evidence": [{"quote": "Quel calendrier ?", "source_url": "https://example.test/source"}],
                "confidence": 0.91,
                "validation_status": "validated",
            }
        ],
        "taxonomy_links": [
            {
                "domain_id": "sante",
                "domain_label": "Santé",
                "subtheme_id": "fin-vie",
                "subtheme_label": "Fin de vie",
                "subject_id": "aide-a-mourir",
                "subject_title": "Aide à mourir",
                "link_strength": "strong",
                "rationale": "test",
                "confidence": 0.9,
            }
        ],
        "subject_updates": [
            {
                "subject_id": "aide-a-mourir",
                "subject_title": "Aide à mourir",
                "summary": "Sujet réel.",
                "context_update": "Contexte réel.",
                "timeline_events": [],
                "actors": [],
                "argument_clusters": [],
            }
        ],
    }
    (tmp_path / "payload.json").write_text(json.dumps(payload), encoding="utf-8")

    repo = ProcessedRepository(curated_dir=tmp_path)
    measures = repo.list_measures()
    traces = repo.list_traces("aide-a-mourir")
    subject = repo.get_subject("aide-a-mourir")

    assert measures[0].id == "aide-a-mourir"
    assert traces[0].argument_role == "clarification"
    assert traces[0].category == "calendrier"
    assert subject is not None
    assert subject["subject"]["title"] == "Aide à mourir"
