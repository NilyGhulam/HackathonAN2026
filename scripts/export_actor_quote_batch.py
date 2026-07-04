#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "0.1.0"
PROMPT_VERSION = "actor_quotes_v1"


def main() -> None:
    parser = argparse.ArgumentParser(description="Exporte un lot conversationnel extract_actor_quotes depuis actor_quote_queue.json.")
    parser.add_argument("--processed-dir", type=Path, default=ROOT / "data" / "processed")
    parser.add_argument("--queue", type=Path, default=None)
    parser.add_argument("--cache", type=Path, default=None, help="Cache actor_quotes.json utilisé par --skip-done.")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--batch-id", default="")
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--skip-done", action="store_true")
    args = parser.parse_args()

    processed_dir = args.processed_dir
    queue_path = args.queue or processed_dir / "actor_quote_queue.json"
    cache_path = args.cache or processed_dir / "actor_quotes.json"
    payload = read_json(queue_path)
    items = payload.get("items", []) if isinstance(payload, dict) else []
    done_ids = load_done_ids(cache_path) if args.skip_done else set()
    candidates = [item for item in items if isinstance(item, dict) and item.get("task") == "extract_actor_quotes"]
    if args.skip_done:
        candidates = [item for item in candidates if clean_text(item.get("id")) not in done_ids]
    selected = candidates[args.offset : args.offset + args.limit]
    generated_at = now_iso()
    batch = {
        "schema_version": SCHEMA_VERSION,
        "batch_id": args.batch_id or f"actor_quotes_{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S')}_{args.offset:04d}",
        "generated_at": generated_at,
        "source_queue": str(queue_path),
        "selection": {
            "offset": args.offset,
            "limit": args.limit,
            "task": "extract_actor_quotes",
            "skip_done": args.skip_done,
            "candidate_count_after_filters": len(candidates),
            "selected_count": len(selected),
        },
        "instructions": [
            "Produire uniquement du JSON valide selon le schéma de sortie AgorIA.",
            "Extraire uniquement des citations exactes présentes dans les segments fournis.",
            "Ne jamais reformuler le champ quote : le champ quote doit être un extrait littéral du segment.",
            "Attribuer les citations seulement à l'acteur du segment correspondant.",
            "Limiter les citations à des extraits utiles, idéalement 15 à 45 mots.",
            "Séparer la citation exacte de l'argument_summary, qui peut être une synthèse.",
            "Utiliser needs_review=true si l'attribution, le sens politique ou le contexte est incertain.",
            "Ne pas chercher à équilibrer artificiellement les positions : extraire ce qui est réellement dans le texte.",
        ],
        "stance_values": [
            "soutien",
            "opposition",
            "alerte",
            "critique",
            "demande_action",
            "demande_moyens",
            "justification",
            "annonce_mesure",
            "réserve",
            "proposition",
            "défense_bilan",
            "mise_en_cause",
        ],
        "items": selected,
        "output_contract": {
            "items": [
                {
                    "id": "identique à l'id de l'item d'entrée",
                    "task": "extract_actor_quotes",
                    "source_id": "identique au source_id d'entrée",
                    "subject_id": "identique au subject_id d'entrée",
                    "status": "ok|needs_review|error",
                    "output": {
                        "quotes": [
                            {
                                "segment_id": "question|answer",
                                "actor_id": "id acteur du segment",
                                "actor_name": "nom acteur du segment",
                                "stance": "valeur stance_values",
                                "argument_summary": "synthèse courte de l'argument",
                                "quote": "citation exacte",
                                "quote_context": "contexte immédiat ou phrase de cadrage",
                                "tags": ["tag court"],
                                "confidence": 0.0,
                                "needs_review": False,
                            }
                        ]
                    },
                }
            ]
        },
    }
    write_json(args.out, batch)
    print(json.dumps({"output": str(args.out), "selected_count": len(selected), "candidate_count_after_filters": len(candidates)}, ensure_ascii=False, indent=2))


def load_done_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    payload = read_json(path)
    records: Iterable[Any]
    if isinstance(payload, dict) and isinstance(payload.get("items"), list):
        records = payload["items"]
    elif isinstance(payload, dict) and isinstance(payload.get("quotes_by_item"), dict):
        return {str(key) for key in payload["quotes_by_item"].keys()}
    elif isinstance(payload, dict):
        records = payload.values()
    elif isinstance(payload, list):
        records = payload
    else:
        records = []
    done: set[str] = set()
    for record in records:
        if isinstance(record, dict):
            item_id = clean_text(record.get("id") or record.get("item_id") or record.get("queue_id"))
            if item_id and clean_text(record.get("status")) != "error":
                done.add(item_id)
    return done


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return str(value)
    return value.strip() if isinstance(value, str) else ""


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


if __name__ == "__main__":
    main()
