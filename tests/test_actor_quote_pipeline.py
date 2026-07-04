import json
import subprocess
import sys
from pathlib import Path


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def test_actor_quote_queue_export_and_import(tmp_path: Path):
    root = Path(__file__).resolve().parents[1]
    processed = tmp_path / "processed"
    curated = tmp_path / "curated"
    batches = tmp_path / "batches"
    write_json(
        processed / "normalized_questions.json",
        {
            "items": [
                {
                    "id": "Q1",
                    "resource_type": "government_question",
                    "resource_label": "Question au Gouvernement",
                    "title": "hébergement d'urgence",
                    "date": "2026-01-01",
                    "rubrique": "Logement",
                    "author_ref": "PA1",
                    "author": {"name": "Camille Test"},
                    "group_label": "Groupe A",
                    "target_ministry_ref": "ORG1",
                    "target_ministry": "Ministère du logement",
                    "question_text": "Madame la ministre, des enfants dorment dehors. Que compte faire le Gouvernement ?",
                    "answer_text": "Le Gouvernement a ouvert des places supplémentaires et mobilise les préfets.",
                    "source_url": "https://questions.assemblee-nationale.fr/test",
                }
            ]
        },
    )
    write_json(
        curated / "agoria_raw_extract.json",
        {
            "schema_version": "0.1.0",
            "processing": {"notes": []},
            "subject_updates": [
                {
                    "subject_id": "question-q1",
                    "subject_title": "hébergement d'urgence",
                    "argument_clusters": [],
                }
            ],
        },
    )

    subprocess.run(
        [sys.executable, str(root / "scripts" / "build_actor_quote_queue.py"), "--processed-dir", str(processed)],
        check=True,
    )
    queue = json.loads((processed / "actor_quote_queue.json").read_text(encoding="utf-8"))
    assert queue["items"][0]["task"] == "extract_actor_quotes"
    assert queue["items"][0]["subject_id"] == "question-q1"
    assert len(queue["items"][0]["input"]["segments"]) == 2

    subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "export_actor_quote_batch.py"),
            "--processed-dir",
            str(processed),
            "--limit",
            "1",
            "--out",
            str(batches / "actor_quotes_001_input.json"),
        ],
        check=True,
    )
    batch = json.loads((batches / "actor_quotes_001_input.json").read_text(encoding="utf-8"))
    assert batch["selection"]["selected_count"] == 1

    write_json(
        batches / "actor_quotes_001_output.json",
        {
            "batch_id": batch["batch_id"],
            "items": [
                {
                    "id": "extract_actor_quotes:Q1",
                    "task": "extract_actor_quotes",
                    "source_id": "Q1",
                    "subject_id": "question-q1",
                    "status": "ok",
                    "output": {
                        "quotes": [
                            {
                                "segment_id": "question",
                                "actor_id": "PA1",
                                "actor_name": "Camille Test",
                                "stance": "alerte",
                                "argument_summary": "Alerte sur des enfants sans hébergement.",
                                "quote": "des enfants dorment dehors",
                                "quote_context": "Question au Gouvernement",
                                "tags": ["logement"],
                                "confidence": 0.9,
                                "needs_review": False,
                            }
                        ]
                    },
                }
            ],
        },
    )
    subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "import_actor_quote_batch.py"),
            str(batches / "actor_quotes_001_output.json"),
            "--processed-dir",
            str(processed),
            "--curated-payload",
            str(curated / "agoria_raw_extract.json"),
            "--apply",
        ],
        check=True,
    )
    cache = json.loads((processed / "actor_quotes.json").read_text(encoding="utf-8"))
    assert cache["counts"]["quotes"] == 1
    payload = json.loads((curated / "agoria_raw_extract.json").read_text(encoding="utf-8"))
    assert payload["quotes"][0]["actor_id"] == "PA1"
    assert payload["quotes"][0]["actor_party"] == "Groupe A"
    assert payload["quotes"][0]["source_url"] == "https://questions.assemblee-nationale.fr/test"
    assert payload["actor_positions"][0]["stance"] == "alerte"
    actor = payload["subject_updates"][0]["argument_clusters"][0]["actors"][0]
    assert actor["party"] == "Groupe A"
    assert actor["quote_url"] == "https://questions.assemblee-nationale.fr/test"
