#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from enrich_with_llm import (  # noqa: E402
    PROMPT_VERSION,
    SCHEMA_VERSION,
    apply_enrichments_to_payload,
    empty_enrichments_doc,
    fingerprint,
    item_cache_key,
    read_json,
    validate_task_output,
    write_json,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Importe un lot enrichi dans data/processed/llm_enrichments.json et peut l'appliquer au payload curated."
    )
    parser.add_argument("batch_output", type=Path)
    parser.add_argument("--processed-dir", type=Path, default=ROOT / "data" / "processed")
    parser.add_argument("--queue", type=Path, default=None)
    parser.add_argument("--curated-payload", type=Path, default=ROOT / "data" / "curated" / "agoria_raw_extract.json")
    parser.add_argument("--output-payload", type=Path, default=None)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--provider-label", default="conversation")
    args = parser.parse_args()

    result = import_batch(
        batch_output=args.batch_output,
        processed_dir=args.processed_dir,
        queue_path=args.queue,
        curated_payload=args.curated_payload,
        output_payload=args.output_payload,
        apply=args.apply,
        provider_label=args.provider_label,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


def import_batch(
    *,
    batch_output: Path,
    processed_dir: Path,
    queue_path: Path | None,
    curated_payload: Path,
    output_payload: Path | None,
    apply: bool,
    provider_label: str,
) -> dict[str, Any]:
    queue_path = queue_path or processed_dir / "llm_enrichment_queue.json"
    enrichments_path = processed_dir / "llm_enrichments.json"

    queue_doc = read_json(queue_path)
    queue_items = list(queue_doc.get("items", []))
    queue_by_id = {item.get("id"): item for item in queue_items}
    queue_by_task_source = {(item.get("task"), item.get("source_id")): item for item in queue_items}

    batch_doc = read_json(batch_output)
    raw_items = batch_doc.get("items", batch_doc.get("enrichments", []))
    if not isinstance(raw_items, list):
        raise ValueError("Le fichier de lot doit contenir une liste `items` ou `enrichments`.")

    cache_doc = read_json(enrichments_path) if enrichments_path.exists() else empty_enrichments_doc()
    cache_by_key = {item.get("cache_key"): item for item in cache_doc.get("items", []) if item.get("cache_key")}

    imported = 0
    skipped = 0
    errors: list[dict[str, str]] = []
    now = now_iso()

    for raw in raw_items:
        if not isinstance(raw, dict):
            skipped += 1
            continue
        if raw.get("status", "ok") != "ok":
            skipped += 1
            continue
        queue_item = queue_by_id.get(raw.get("id")) or queue_by_task_source.get((raw.get("task"), raw.get("source_id")))
        if not queue_item:
            errors.append({"id": str(raw.get("id")), "error": "item introuvable dans la queue locale"})
            continue
        try:
            output = validate_task_output(queue_item, raw.get("output") or {})
        except Exception as exc:  # noqa: BLE001 - on veut continuer à importer les autres items.
            errors.append({"id": str(raw.get("id")), "error": str(exc)})
            continue

        cache_key = item_cache_key(queue_item)
        record = {
            "id": queue_item.get("id"),
            "task": queue_item.get("task"),
            "source_id": queue_item.get("source_id"),
            "cache_key": cache_key,
            "status": "ok",
            "provider": provider_label,
            "model": None,
            "prompt_version": PROMPT_VERSION,
            "created_at": now,
            "input_fingerprint": fingerprint(queue_item.get("input", {})),
            "output": output,
            "error": "",
            "batch_id": batch_doc.get("batch_id"),
            "batch_file": str(batch_output),
        }
        cache_by_key[cache_key] = record
        imported += 1

    new_cache_doc = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now,
        "prompt_version": PROMPT_VERSION,
        "items": sorted(cache_by_key.values(), key=lambda item: item.get("id") or ""),
    }
    write_json(enrichments_path, new_cache_doc)

    applied_payload: str | None = None
    applied_count = 0
    if apply:
        ok_records = [item for item in new_cache_doc["items"] if item.get("status") == "ok" and item.get("output")]
        payload = read_json(curated_payload)
        payload, applied_count = apply_enrichments_to_payload(payload, ok_records)
        target = output_payload or curated_payload
        if target == curated_payload and curated_payload.exists():
            backup_path = curated_payload.with_suffix(curated_payload.suffix + ".bak")
            backup_path.write_text(curated_payload.read_text(encoding="utf-8"), encoding="utf-8")
        write_json(target, payload)
        applied_payload = str(target)

    return {
        "batch_output": str(batch_output),
        "cache_path": str(enrichments_path),
        "imported": imported,
        "skipped": skipped,
        "errors": errors,
        "applied": apply,
        "applied_count": applied_count,
        "applied_payload": applied_payload,
    }


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


if __name__ == "__main__":
    main()
