from __future__ import annotations

import json
from pathlib import Path

from scripts.export_llm_batch import export_batch
from scripts.import_llm_batch import import_batch


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def test_export_llm_batch_selects_items(tmp_path: Path) -> None:
    processed = tmp_path / "processed"
    queue = {
        "schema_version": "0.1.0",
        "items": [
            {"id": "classify:s1", "task": "classify_subject", "source_id": "s1", "input": {"title": "Sujet 1"}},
            {"id": "summarize_question:q1", "task": "summarize_question_and_answer", "source_id": "q1", "input": {"title": "Question 1"}},
        ],
    }
    write_json(processed / "llm_enrichment_queue.json", queue)
    write_json(processed / "taxonomy.json", {"nodes": [], "constraints": {}})

    out = tmp_path / "batch.json"
    result = export_batch(
        processed_dir=processed,
        queue_path=None,
        taxonomy_path=None,
        enrichments_path=None,
        out_path=out,
        batch_id="batch_test",
        offset=0,
        limit=10,
        only_task="summarize_question_and_answer",
        skip_done=False,
    )

    batch = json.loads(out.read_text(encoding="utf-8"))
    assert result["selected_count"] == 1
    assert batch["batch_id"] == "batch_test"
    assert batch["items"][0]["source_id"] == "q1"
    assert batch["taxonomy"] == {"nodes": [], "constraints": {}}


def test_import_llm_batch_updates_cache(tmp_path: Path) -> None:
    processed = tmp_path / "processed"
    curated = tmp_path / "curated" / "agoria_raw_extract.json"
    queue = {
        "schema_version": "0.1.0",
        "items": [
            {
                "id": "classify:s1",
                "task": "classify_subject",
                "source_id": "s1",
                "input": {"title": "Sujet 1", "current_path": ["Justice", "Prisons"]},
            }
        ],
    }
    batch = {
        "schema_version": "0.1.0",
        "batch_id": "batch_test",
        "items": [
            {
                "id": "classify:s1",
                "task": "classify_subject",
                "source_id": "s1",
                "status": "ok",
                "output": {
                    "canonical_path": ["Justice", "Système pénitentiaire", "Conditions de détention"],
                    "tags": ["prison"],
                    "new_category_proposal": {"needed": False},
                    "confidence": 0.8,
                    "needs_review": False,
                    "rationale": "Titre et chemin existant.",
                },
            }
        ],
    }
    payload = {
        "processing": {},
        "subject_updates": [{"subject_id": "s1", "classification": {}}],
        "taxonomy_links": [{"subject_id": "s1"}],
        "extracted_traces": [],
    }
    write_json(processed / "llm_enrichment_queue.json", queue)
    write_json(tmp_path / "batch_output.json", batch)
    write_json(curated, payload)

    result = import_batch(
        batch_output=tmp_path / "batch_output.json",
        processed_dir=processed,
        queue_path=None,
        curated_payload=curated,
        output_payload=None,
        apply=True,
        provider_label="conversation",
    )

    cache = json.loads((processed / "llm_enrichments.json").read_text(encoding="utf-8"))
    updated_payload = json.loads(curated.read_text(encoding="utf-8"))
    assert result["imported"] == 1
    assert cache["items"][0]["batch_id"] == "batch_test"
    assert updated_payload["subject_updates"][0]["classification"]["canonical_path"][0] == "Justice"
    assert updated_payload["taxonomy_links"][0]["domain_label"] == "Justice"
