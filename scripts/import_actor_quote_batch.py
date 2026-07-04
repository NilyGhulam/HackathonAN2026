#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import datetime as dt
import json
import re
import unicodedata
import urllib.parse
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "0.1.0"
PROMPT_VERSION = "actor_quotes_v1"

STANCE_TO_POSITION = {
    "soutien": "for",
    "proposition": "for",
    "justification": "for",
    "annonce_mesure": "for",
    "défense_bilan": "for",
    "opposition": "against",
    "critique": "against",
    "mise_en_cause": "against",
    "alerte": "neutral",
    "demande_action": "neutral",
    "demande_moyens": "neutral",
    "réserve": "neutral",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Importe un batch extract_actor_quotes et fusionne les citations dans le payload curated.")
    parser.add_argument("batch_output", type=Path)
    parser.add_argument("--processed-dir", type=Path, default=ROOT / "data" / "processed")
    parser.add_argument("--cache", type=Path, default=None, help="Par défaut: data/processed/actor_quotes.json")
    parser.add_argument("--queue", type=Path, default=None, help="Queue actor_quote_queue.json utilisée pour réhydrater les métadonnées.")
    parser.add_argument("--curated-payload", type=Path, default=ROOT / "data" / "curated" / "agoria_raw_extract.json")
    parser.add_argument("--output-payload", type=Path, default=None)
    parser.add_argument("--apply", action="store_true", help="Fusionne aussi dans le payload curated.")
    parser.add_argument("--provider-label", default="conversation")
    args = parser.parse_args()

    cache_path = args.cache or args.processed_dir / "actor_quotes.json"
    queue_path = args.queue or args.processed_dir / "actor_quote_queue.json"
    queue_lookup = load_queue_lookup(queue_path)
    batch = read_json(args.batch_output)
    imported = normalize_batch_items(batch, batch_file=args.batch_output, provider_label=args.provider_label, queue_lookup=queue_lookup)
    cache = merge_cache(cache_path, imported)
    write_json(cache_path, cache)

    applied_path = None
    if args.apply:
        output_payload = args.output_payload or args.curated_payload
        payload = read_json(args.curated_payload)
        merged = apply_to_curated_payload(payload, imported)
        if output_payload == args.curated_payload and args.curated_payload.exists():
            backup = args.curated_payload.with_suffix(args.curated_payload.suffix + ".bak")
            backup.write_text(args.curated_payload.read_text(encoding="utf-8"), encoding="utf-8")
        write_json(output_payload, merged)
        applied_path = str(output_payload)

    print(json.dumps({"cache": str(cache_path), "items_imported": len(imported), "quotes_imported": sum(len(item.get('quotes', [])) for item in imported), "applied_payload": applied_path}, ensure_ascii=False, indent=2))


def normalize_batch_items(batch: Any, *, batch_file: Path, provider_label: str, queue_lookup: dict[str, dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    raw_items = []
    if isinstance(batch, dict):
        raw_items = batch.get("items") or batch.get("enrichments") or []
        batch_id = clean_text(batch.get("batch_id"))
    elif isinstance(batch, list):
        raw_items = batch
        batch_id = ""
    else:
        raw_items = []
        batch_id = ""

    imported: list[dict[str, Any]] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        item_id = clean_text(item.get("id") or item.get("queue_id"))
        queue_item = (queue_lookup or {}).get(item_id) or (queue_lookup or {}).get(clean_text(item.get("source_id")))
        queue_input = queue_item.get("input", {}) if isinstance(queue_item, dict) and isinstance(queue_item.get("input"), dict) else {}
        source_id = clean_text(item.get("source_id")) or clean_text(queue_item.get("source_id")) if isinstance(queue_item, dict) else clean_text(item.get("source_id"))
        subject_id = clean_text(item.get("subject_id")) or clean_text(queue_item.get("subject_id")) if isinstance(queue_item, dict) else clean_text(item.get("subject_id"))
        status = clean_text(item.get("status")) or "ok"
        output = item.get("output") if isinstance(item.get("output"), dict) else {}
        quotes = output.get("quotes") if isinstance(output, dict) else item.get("quotes")
        normalized_quotes = normalize_quotes(
            quotes or [],
            item_id=item_id,
            source_id=source_id,
            subject_id=subject_id,
            source_meta=source_metadata(queue_input),
            actors_by_id=actors_by_id(queue_input),
        )
        imported.append(
            {
                "id": item_id,
                "task": "extract_actor_quotes",
                "source_id": source_id,
                "subject_id": subject_id,
                "status": status,
                "quotes": normalized_quotes,
                "metadata": {
                    "batch_id": batch_id,
                    "batch_file": str(batch_file),
                    "provider": provider_label,
                    "prompt_version": PROMPT_VERSION,
                    "imported_at": now_iso(),
                },
            }
        )
    return imported


def normalize_quotes(
    quotes: Any,
    *,
    item_id: str,
    source_id: str,
    subject_id: str,
    source_meta: dict[str, str] | None = None,
    actors_by_id: dict[str, dict[str, str]] | None = None,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    source_meta = source_meta or {}
    actors_by_id = actors_by_id or {}
    for index, quote in enumerate(quotes if isinstance(quotes, list) else [], start=1):
        if not isinstance(quote, dict):
            continue
        quote_text = clean_text(quote.get("quote"))
        if not quote_text:
            continue
        stance = normalize_stance(quote.get("stance"))
        actor_id = clean_text(quote.get("actor_id")) or "unknown_actor"
        actor_meta = actors_by_id.get(actor_id, {})
        quote_id = f"quote:{source_id}:{slugify(actor_id)}:{index}"
        output.append(
            {
                "id": quote_id,
                "item_id": item_id,
                "source_id": source_id,
                "subject_id": subject_id,
                "segment_id": clean_text(quote.get("segment_id")) or "unknown",
                "actor_id": actor_id,
                "actor_name": clean_text(quote.get("actor_name")) or actor_id,
                "actor_role": clean_text(actor_meta.get("role")),
                "actor_party": clean_text(actor_meta.get("party")),
                "actor_type": clean_text(actor_meta.get("type")),
                "stance": stance,
                "position": STANCE_TO_POSITION.get(stance, "neutral"),
                "argument_summary": clean_text(quote.get("argument_summary")),
                "quote": quote_text,
                "quote_context": clean_text(quote.get("quote_context")),
                "source_label": source_meta.get("source_label", ""),
                "source_date": source_meta.get("source_date", ""),
                "source_url": source_meta.get("source_url", ""),
                "source_type": source_meta.get("source_type", ""),
                "rubrique": source_meta.get("rubrique", ""),
                "subject_title": source_meta.get("subject_title", ""),
                "tags": [clean_text(tag) for tag in quote.get("tags", []) if clean_text(tag)] if isinstance(quote.get("tags"), list) else [],
                "confidence": float_or_default(quote.get("confidence"), 0.0),
                "needs_review": bool(quote.get("needs_review")),
            }
        )
    return output


def load_queue_lookup(queue_path: Path) -> dict[str, dict[str, Any]]:
    if not queue_path.exists():
        return {}
    payload = read_json(queue_path)
    items = payload.get("items", []) if isinstance(payload, dict) else []
    lookup: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        item_id = clean_text(item.get("id"))
        source_id = clean_text(item.get("source_id"))
        if item_id:
            lookup[item_id] = item
        if source_id:
            lookup[source_id] = item
    return lookup


def source_metadata(queue_input: dict[str, Any]) -> dict[str, str]:
    source_id = clean_text(queue_input.get("source_id"))
    source_label = clean_text(queue_input.get("source_label")) or source_id
    return {
        "source_label": source_label,
        "source_date": clean_text(queue_input.get("date")),
        "source_url": clean_url(queue_input.get("source_url")) or fallback_source_url(source_id, source_label),
        "source_type": clean_text(queue_input.get("source_type")),
        "rubrique": clean_text(queue_input.get("rubrique")),
        "subject_title": clean_text(queue_input.get("subject_title")),
    }


def actors_by_id(queue_input: dict[str, Any]) -> dict[str, dict[str, str]]:
    actors: dict[str, dict[str, str]] = {}
    for actor in queue_input.get("known_actors", []) if isinstance(queue_input.get("known_actors"), list) else []:
        if isinstance(actor, dict) and clean_text(actor.get("id")):
            actors[clean_text(actor["id"])] = normalize_actor_meta(actor)
    for segment in queue_input.get("segments", []) if isinstance(queue_input.get("segments"), list) else []:
        actor = segment.get("actor") if isinstance(segment, dict) else None
        if isinstance(actor, dict) and clean_text(actor.get("id")):
            actors[clean_text(actor["id"])] = normalize_actor_meta(actor)
    return actors


def normalize_actor_meta(actor: dict[str, Any]) -> dict[str, str]:
    return {
        "role": clean_text(actor.get("role")),
        "party": clean_text(actor.get("party")),
        "type": clean_text(actor.get("type")),
    }


def merge_cache(cache_path: Path, imported: list[dict[str, Any]]) -> dict[str, Any]:
    if cache_path.exists():
        cache = read_json(cache_path)
        if not isinstance(cache, dict):
            cache = {}
    else:
        cache = {}
    existing_items = {item.get("id"): item for item in cache.get("items", []) if isinstance(item, dict) and item.get("id")}
    for item in imported:
        if item.get("id"):
            existing_items[item["id"]] = item
    all_quotes = []
    quotes_by_id = {}
    for item in existing_items.values():
        for quote in item.get("quotes", []):
            if quote.get("id"):
                quotes_by_id[quote["id"]] = quote
    all_quotes = sorted(quotes_by_id.values(), key=lambda item: (item.get("source_id", ""), item.get("id", "")))
    return {
        "schema_version": SCHEMA_VERSION,
        "prompt_version": PROMPT_VERSION,
        "updated_at": now_iso(),
        "items": sorted(existing_items.values(), key=lambda item: item.get("id", "")),
        "quotes": all_quotes,
        "counts": {
            "items": len(existing_items),
            "quotes": len(all_quotes),
        },
    }


def apply_to_curated_payload(payload: dict[str, Any], imported: list[dict[str, Any]]) -> dict[str, Any]:
    merged = copy.deepcopy(payload)
    quotes = merge_unique_by_id(merged.get("quotes", []), [quote for item in imported for quote in item.get("quotes", [])])
    positions = build_actor_positions(quotes)
    merged["quotes"] = quotes
    merged["actor_positions"] = merge_unique_by_id(merged.get("actor_positions", []), positions)

    updates = merged.get("subject_updates", [])
    if isinstance(updates, list):
        quotes_by_subject: dict[str, list[dict[str, Any]]] = {}
        positions_by_subject: dict[str, list[dict[str, Any]]] = {}
        for quote in quotes:
            quotes_by_subject.setdefault(quote.get("subject_id", ""), []).append(quote)
        for position in merged["actor_positions"]:
            positions_by_subject.setdefault(position.get("subject_id", ""), []).append(position)
        for subject in updates:
            if not isinstance(subject, dict):
                continue
            subject_id = clean_text(subject.get("subject_id"))
            if not subject_id:
                continue
            subject_quotes = quotes_by_subject.get(subject_id, [])
            if not subject_quotes:
                continue
            subject["quotes"] = merge_unique_by_id(subject.get("quotes", []), subject_quotes)
            subject["actor_positions"] = merge_unique_by_id(subject.get("actor_positions", []), positions_by_subject.get(subject_id, []))
            subject["argument_clusters"] = merge_unique_by_id(
                subject.get("argument_clusters", []),
                build_argument_clusters_for_subject(subject_id, subject_quotes),
            )
    processing = merged.setdefault("processing", {}) if isinstance(merged, dict) else {}
    notes = processing.setdefault("notes", []) if isinstance(processing, dict) else []
    if isinstance(notes, list) and "Citations d'acteurs importées depuis les batches extract_actor_quotes." not in notes:
        notes.append("Citations d'acteurs importées depuis les batches extract_actor_quotes.")
    return merged


def build_actor_positions(quotes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for quote in quotes:
        key = (quote.get("actor_id", ""), quote.get("subject_id", ""), quote.get("stance", ""))
        if all(key):
            grouped.setdefault(key, []).append(quote)
    positions: list[dict[str, Any]] = []
    for (actor_id, subject_id, stance), items in grouped.items():
        best = max(items, key=lambda item: item.get("confidence", 0.0))
        positions.append(
            {
                "id": f"position:{slugify(actor_id)}:{slugify(subject_id)}:{slugify(stance)}",
                "actor_id": actor_id,
                "actor_name": best.get("actor_name", actor_id),
                "actor_role": best.get("actor_role", ""),
                "actor_party": best.get("actor_party", ""),
                "subject_id": subject_id,
                "stance": stance,
                "position": STANCE_TO_POSITION.get(stance, "neutral"),
                "summary": best.get("argument_summary") or "Position extraite depuis une citation source.",
                "quote_ids": [item["id"] for item in items if item.get("id")],
                "source_ids": sorted({item.get("source_id", "") for item in items if item.get("source_id")}),
                "source_urls": sorted({item.get("source_url", "") for item in items if item.get("source_url")}),
                "confidence": round(sum(float(item.get("confidence", 0.0)) for item in items) / max(len(items), 1), 3),
                "needs_review": any(bool(item.get("needs_review")) for item in items),
            }
        )
    return sorted(positions, key=lambda item: item.get("id", ""))


def build_argument_clusters_for_subject(subject_id: str, quotes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for quote in quotes:
        position = quote.get("position") or "neutral"
        stance = quote.get("stance") or "position"
        grouped.setdefault((position, stance), []).append(quote)
    clusters: list[dict[str, Any]] = []
    for (position, stance), items in grouped.items():
        clusters.append(
            {
                "id": f"actor-quotes-{slugify(subject_id)}-{slugify(position)}-{slugify(stance)}",
                "axis": "citations-acteurs",
                "position": position,
                "label": label_for_stance(stance),
                "summary": "Positions extraites de citations littérales issues des sources parlementaires.",
                "actors": [
                    {
                        "actor_id": item.get("actor_id"),
                        "name": item.get("actor_name"),
                        "initials": initials(item.get("actor_name") or item.get("actor_id")),
                        "role": item.get("actor_role") or item.get("actor_name"),
                        "party": item.get("actor_party") or "",
                        "photo": "",
                        "quote": item.get("quote"),
                        "quote_source": join_non_empty([item.get("source_label") or item.get("source_id"), item.get("source_date")], separator=", "),
                        "quote_url": item.get("source_url") or "#",
                        "quote_context": item.get("quote_context"),
                        "quote_id": item.get("id"),
                        "quote_confidence": item.get("confidence"),
                        "stance_summary": item.get("argument_summary"),
                    }
                    for item in items[:8]
                ],
            }
        )
    return clusters


def merge_unique_by_id(existing: Any, new_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for item in existing if isinstance(existing, list) else []:
        if isinstance(item, dict) and item.get("id"):
            merged[item["id"]] = item
    for item in new_items:
        if isinstance(item, dict) and item.get("id"):
            merged[item["id"]] = item
    return sorted(merged.values(), key=lambda item: item.get("id", ""))


def join_non_empty(values: Iterable[Any], *, separator: str = " · ") -> str:
    return separator.join(clean_text(value) for value in values if clean_text(value))


def label_for_stance(stance: str) -> str:
    labels = {
        "soutien": "Soutien",
        "opposition": "Opposition",
        "alerte": "Alerte",
        "critique": "Critique",
        "demande_action": "Demande d'action",
        "demande_moyens": "Demande de moyens",
        "justification": "Justification gouvernementale",
        "annonce_mesure": "Annonce de mesure",
        "réserve": "Réserve",
        "proposition": "Proposition",
        "défense_bilan": "Défense du bilan",
        "mise_en_cause": "Mise en cause",
    }
    return labels.get(stance, stance.replace("_", " ").title())


def normalize_stance(value: Any) -> str:
    stance = clean_text(value).lower().replace(" ", "_")
    aliases = {
        "demande": "demande_action",
        "action": "demande_action",
        "annonce": "annonce_mesure",
        "bilan": "défense_bilan",
        "defense_bilan": "défense_bilan",
        "reserve": "réserve",
    }
    return aliases.get(stance, stance if stance in STANCE_TO_POSITION else "alerte")


def initials(value: Any) -> str:
    text = clean_text(value)
    parts = [part for part in re.split(r"\s+", text) if part]
    return "".join(part[:1].upper() for part in parts[:2]) or "AP"


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def float_or_default(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return str(value)
    return value.replace("\xa0", " ").strip() if isinstance(value, str) else ""


def clean_url(value: Any) -> str:
    url = clean_text(value)
    return "" if url in {"", "#"} else url


def fallback_source_url(source_id: str, source_label: str) -> str:
    if not source_id:
        return ""
    label = clean_text(source_label).lower()
    if source_id.startswith("QANR") or "question" in label:
        query = urllib.parse.quote_plus(source_id)
        return f"https://www.assemblee-nationale.fr/dyn/recherche-resultats?search_term={query}"
    return ""


def slugify(value: Any) -> str:
    text = clean_text(value).lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:90]


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


if __name__ == "__main__":
    main()
