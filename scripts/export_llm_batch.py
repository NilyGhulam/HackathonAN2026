#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "0.1.0"

INSTRUCTIONS = [
    "Produire uniquement du JSON valide selon le schéma de sortie AgorIA.",
    "Ne jamais inventer de fait : utiliser uniquement les champs fournis dans chaque item.",
    "Conserver des catégories neutres, stables et non partisanes.",
    "Choisir un seul chemin canonique principal ; placer les notions transversales dans tags.",
    "Proposer une nouvelle catégorie seulement si les catégories existantes ne suffisent pas.",
    "Mettre needs_review=true si l'item est ambigu, polémique, incomplet ou difficile à classer.",
]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Exporte un lot de data/processed/llm_enrichment_queue.json pour enrichissement conversationnel."
    )
    parser.add_argument("--processed-dir", type=Path, default=ROOT / "data" / "processed")
    parser.add_argument("--queue", type=Path, default=None)
    parser.add_argument("--taxonomy", type=Path, default=None)
    parser.add_argument("--enrichments", type=Path, default=None)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--batch-id", default=None)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--only-task", choices=["classify_subject", "summarize_question_and_answer"], default=None)
    parser.add_argument("--skip-done", action="store_true", help="Ignore les items déjà présents avec status=ok dans llm_enrichments.json.")
    args = parser.parse_args()

    result = export_batch(
        processed_dir=args.processed_dir,
        queue_path=args.queue,
        taxonomy_path=args.taxonomy,
        enrichments_path=args.enrichments,
        out_path=args.out,
        batch_id=args.batch_id,
        offset=args.offset,
        limit=args.limit,
        only_task=args.only_task,
        skip_done=args.skip_done,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


def export_batch(
    *,
    processed_dir: Path,
    queue_path: Path | None,
    taxonomy_path: Path | None,
    enrichments_path: Path | None,
    out_path: Path,
    batch_id: str | None,
    offset: int,
    limit: int,
    only_task: str | None,
    skip_done: bool,
) -> dict[str, Any]:
    queue_path = queue_path or processed_dir / "llm_enrichment_queue.json"
    taxonomy_path = taxonomy_path or processed_dir / "taxonomy.json"
    enrichments_path = enrichments_path or processed_dir / "llm_enrichments.json"

    queue_doc = read_json(queue_path)
    items = list(queue_doc.get("items", []))
    if only_task:
        items = [item for item in items if item.get("task") == only_task]

    done_keys = set()
    if skip_done and enrichments_path.exists():
        enrichments_doc = read_json(enrichments_path)
        done_keys = {
            (item.get("task"), item.get("source_id"))
            for item in enrichments_doc.get("items", [])
            if item.get("status") == "ok"
        }
        items = [item for item in items if (item.get("task"), item.get("source_id")) not in done_keys]

    selected = items[offset : offset + limit]
    generated_at = now_iso()
    batch_id = batch_id or f"batch_{generated_at.replace(':', '').replace('-', '').replace('+', '_')}"

    batch = {
        "schema_version": SCHEMA_VERSION,
        "batch_id": batch_id,
        "generated_at": generated_at,
        "source_queue": str(queue_path),
        "selection": {
            "offset": offset,
            "limit": limit,
            "only_task": only_task,
            "skip_done": skip_done,
            "candidate_count_after_filters": len(items),
            "selected_count": len(selected),
        },
        "instructions": INSTRUCTIONS,
        "taxonomy": read_json(taxonomy_path) if taxonomy_path.exists() else None,
        "items": selected,
        "output_contract": {
            "items": [
                {
                    "id": "reprendre l'id de l'item",
                    "task": "reprendre la tâche",
                    "source_id": "reprendre source_id",
                    "status": "ok",
                    "output": "objet conforme à expected_output de l'item",
                }
            ]
        },
    }
    write_json(out_path, batch)
    return {
        "out": str(out_path),
        "batch_id": batch_id,
        "selected_count": len(selected),
        "candidate_count_after_filters": len(items),
        "done_items_skipped": len(done_keys) if skip_done else 0,
    }


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        data = json.load(stream)
    if not isinstance(data, dict):
        raise ValueError(f"{path} doit contenir un objet JSON")
    return data


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


if __name__ == "__main__":
    main()
