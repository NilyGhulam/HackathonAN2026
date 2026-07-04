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


def test_processed_repository_does_not_cross_join_traces_and_subjects(tmp_path: Path) -> None:
    payload = {
        "schema_version": "0.1.0",
        "processing": {"status": "validated"},
        "raw_source": {
            "id": "source_1",
            "type": "written_question",
            "institution": "assemblee_nationale",
            "date": "2026-07-03",
            "title": "Questions officielles",
            "url": "https://example.test/source",
            "metadata": {},
        },
        "extracted_traces": [
            {
                "id": "trace_a_1",
                "summary": "Première trace du sujet A.",
                "argument_role": "clarification",
                "affected_publics": ["public A"],
                "issues": [],
                "evidence": [{"quote": "A1"}],
                "confidence": 0.8,
                "metadata": {"subject_id": "sujet-a"},
            },
            {
                "id": "trace_a_2",
                "summary": "Deuxième trace du sujet A.",
                "argument_role": "support",
                "affected_publics": ["public A"],
                "issues": [],
                "evidence": [{"quote": "A2"}],
                "confidence": 0.8,
                "metadata": {"subject_id": "sujet-a"},
            },
            {
                "id": "trace_b_1",
                "summary": "Trace du sujet B.",
                "argument_role": "opposition",
                "affected_publics": ["public B"],
                "issues": [],
                "evidence": [{"quote": "B1"}],
                "confidence": 0.8,
                "metadata": {"subject_id": "sujet-b"},
            },
        ],
        "taxonomy_links": [
            {
                "domain_id": "sante",
                "domain_label": "Santé",
                "subtheme_id": "sub-a",
                "subtheme_label": "Sous-thème A",
                "subject_id": "sujet-a",
                "subject_title": "Sujet A",
            },
            {
                "domain_id": "justice",
                "domain_label": "Justice",
                "subtheme_id": "sub-b",
                "subtheme_label": "Sous-thème B",
                "subject_id": "sujet-b",
                "subject_title": "Sujet B",
            },
        ],
        "subject_updates": [
            {
                "subject_id": "sujet-a",
                "subject_title": "Sujet A",
                "summary": "Résumé A.",
                "context_update": "Contexte A.",
                "timeline_events": [],
                "actors": [],
                "argument_clusters": [],
            },
            {
                "subject_id": "sujet-b",
                "subject_title": "Sujet B",
                "summary": "Résumé B.",
                "context_update": "Contexte B.",
                "timeline_events": [],
                "actors": [],
                "argument_clusters": [],
            },
        ],
    }
    (tmp_path / "payload.json").write_text(json.dumps(payload), encoding="utf-8")

    repo = ProcessedRepository(curated_dir=tmp_path)
    all_traces = repo.list_traces()
    subject_a_traces = repo.list_traces("sujet-a")
    subject_b_traces = repo.list_traces("sujet-b")
    measures = {measure.id: measure for measure in repo.list_measures()}

    assert len(all_traces) == 3
    assert [trace.id for trace in subject_a_traces] == ["sujet-a:trace_a_1", "sujet-a:trace_a_2"]
    assert [trace.id for trace in subject_b_traces] == ["sujet-b:trace_b_1"]
    assert measures["sujet-a"].changes == ["Première trace du sujet A.", "Deuxième trace du sujet A."]
    assert measures["sujet-b"].changes == ["Trace du sujet B."]


def test_argument_map_uses_selected_actor_quotes_only() -> None:
    subject_update = {
        "actors": [
            {"id": "legacy", "name": "Ancien extrait", "party": "Non renseigné"},
        ],
        "argument_clusters": [
            {
                "id": "question-sujet-test",
                "axis": "arguments-sources",
                "position": "neutral",
                "label": "Ancien extrait",
                "summary": "Ancien résumé.",
                "actors": [
                    {
                        "actor_id": "legacy",
                        "quote": "TITRE DU DÉBAT Mme la présidente. La parole est à...",
                    }
                ],
            },
            {
                "id": "actor-quotes-sujet-test-for-soutien",
                "axis": "citations-acteurs",
                "position": "for",
                "label": "Soutien",
                "summary": "Citation sélectionnée.",
                "actors": [
                    {
                        "actor_id": "selected",
                        "name": "Actrice Sélectionnée",
                        "role": "Députée",
                        "party": "Gauche",
                        "quote": "Cette phrase est le passage clé extrait par le batch.",
                        "quote_source": "Question au Gouvernement, 2026-01-01",
                        "quote_url": "https://example.test/source",
                    }
                ],
            },
        ],
    }

    argument_map = ProcessedRepository._argument_map(subject_update)
    actors = [actor for cluster in argument_map["clusters"] for actor in cluster["actors"]]

    assert len(argument_map["clusters"]) == 1
    assert actors[0]["name"] == "Actrice Sélectionnée"
    assert actors[0]["quote"] == "Cette phrase est le passage clé extrait par le batch."
    assert actors[0]["quote_url"] == "https://example.test/source"


def test_argument_map_drops_legacy_excerpt_when_no_selected_quote() -> None:
    subject_update = {
        "actors": [{"id": "legacy", "name": "Ancien extrait"}],
        "argument_clusters": [
            {
                "id": "question-sujet-test",
                "axis": "arguments-sources",
                "position": "neutral",
                "label": "Ancien extrait",
                "summary": "Ancien résumé.",
                "actors": [{"actor_id": "legacy", "quote": "Début de transcript non sélectionné."}],
            }
        ],
    }

    argument_map = ProcessedRepository._argument_map(subject_update)

    assert argument_map["clusters"] == []
