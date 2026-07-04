from __future__ import annotations

import json
from pathlib import Path

from scripts.enrich_with_llm import enrich_with_llm


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def test_enrich_with_llm_mock_applies_question_and_classification(tmp_path: Path) -> None:
    processed = tmp_path / "processed"
    curated = tmp_path / "curated" / "agoria_raw_extract.json"
    question_id = "Q1"
    subject_id = "question-q1"
    write_json(
        processed / "llm_enrichment_queue.json",
        {
            "schema_version": "0.1.0",
            "items": [
                {
                    "id": f"summarize_question:{question_id}",
                    "task": "summarize_question_and_answer",
                    "source_id": question_id,
                    "input": {
                        "title": "Situation à Mayotte",
                        "rubrique": "outre-mer",
                        "question_text": "Mayotte est en situation d'urgence vitale. Que comptez-vous faire ?",
                        "answer_text": "Nous confirmerons les renforts de sécurité.",
                    },
                },
                {
                    "id": f"classify:{subject_id}",
                    "task": "classify_subject",
                    "source_id": subject_id,
                    "input": {
                        "title": "Situation à Mayotte",
                        "summary": "Question parlementaire.",
                        "context": "Question au Gouvernement · Ministère de l'intérieur",
                        "current_path": ["Outre-mer", "outre-mer"],
                    },
                },
            ],
        },
    )
    write_json(
        curated,
        {
            "schema_version": "0.1.0",
            "processing": {"status": "needs_review", "model": "deterministic_script_only"},
            "raw_source": {"id": "raw_extract_aggregate", "type": "other"},
            "extracted_traces": [
                {
                    "id": question_id,
                    "summary": "Question parlementaire — Situation à Mayotte",
                    "issues": ["outre-mer"],
                    "evidence": [{"quote": "extrait", "source_url": "#"}],
                    "metadata": {"subject_id": subject_id},
                }
            ],
            "taxonomy_links": [
                {
                    "domain_id": "outre-mer",
                    "domain_label": "Outre-mer",
                    "subtheme_id": "outre-mer__outre-mer",
                    "subtheme_label": "outre-mer",
                    "subject_id": subject_id,
                }
            ],
            "subject_updates": [
                {
                    "subject_id": subject_id,
                    "subject_title": "Situation à Mayotte",
                    "summary": "Question parlementaire.",
                    "timeline_events": [{"source_id": question_id, "summary": "à résumer"}],
                    "argument_clusters": [{"id": "question-q1", "summary": "à résumer", "response": {"summary": "à résumer"}}],
                    "classification": {},
                }
            ],
        },
    )

    result = enrich_with_llm(
        processed_dir=processed,
        curated_payload=curated,
        provider_name="mock",
        apply=True,
    )

    assert result["counts"]["ok_total_in_cache"] == 2
    assert result["counts"]["applied_to_payload"] == 2
    payload = json.loads(curated.read_text(encoding="utf-8"))
    subject = payload["subject_updates"][0]
    assert "Situation à Mayotte" in subject["summary"]
    assert subject["timeline_events"][0]["answer_summary"]
    assert subject["classification"]["canonical_path"][:2] == ["Outre-mer", "outre-mer"]
    assert payload["extracted_traces"][0]["metadata"]["answer_summary"]
    assert (curated.with_suffix(curated.suffix + ".bak")).exists()


def test_enrich_with_llm_dry_run_writes_prompts_without_apply(tmp_path: Path) -> None:
    processed = tmp_path / "processed"
    curated = tmp_path / "curated" / "agoria_raw_extract.json"
    write_json(
        processed / "llm_enrichment_queue.json",
        {
            "schema_version": "0.1.0",
            "items": [
                {
                    "id": "classify:s1",
                    "task": "classify_subject",
                    "source_id": "s1",
                    "input": {"title": "T", "current_path": ["A", "B"]},
                }
            ],
        },
    )
    write_json(curated, {"schema_version": "0.1.0", "processing": {}, "subject_updates": [], "taxonomy_links": [], "extracted_traces": []})

    result = enrich_with_llm(
        processed_dir=processed,
        curated_payload=curated,
        provider_name="dry-run",
        apply=False,
        write_prompts=True,
    )

    assert result["counts"]["pending_total_in_cache"] == 1
    assert (processed / "llm_prompts" / "classify-s1.txt").exists()
    cache = json.loads((processed / "llm_enrichments.json").read_text(encoding="utf-8"))
    assert cache["items"][0]["status"] == "pending"
