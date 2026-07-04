#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "0.1.0"
PROMPT_VERSION = "actor_quotes_v1"


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Construit une queue LLM dédiée à l'extraction de citations, positions et arguments "
            "d'acteurs à partir des questions parlementaires normalisées."
        )
    )
    parser.add_argument("--processed-dir", type=Path, default=ROOT / "data" / "processed")
    parser.add_argument("--questions", type=Path, default=None, help="Fichier normalized_questions.json. Par défaut: data/processed/normalized_questions.json")
    parser.add_argument("--enrichments", type=Path, default=None, help="Fichier llm_enrichments.json, utilisé avec --only-enriched-summaries")
    parser.add_argument("--out", type=Path, default=None, help="Fichier de sortie. Par défaut: data/processed/actor_quote_queue.json")
    parser.add_argument("--limit", type=int, default=0, help="Limite le nombre de questions sources. 0 = aucune limite.")
    parser.add_argument(
        "--only-enriched-summaries",
        action="store_true",
        help="Ne crée des tâches que pour les questions déjà enrichies par summarize_question_and_answer.",
    )
    parser.add_argument(
        "--text-max-chars",
        type=int,
        default=12000,
        help="Longueur max par segment envoyé au batch. 0 = pas de troncature.",
    )
    args = parser.parse_args()

    processed_dir = args.processed_dir
    questions_path = args.questions or processed_dir / "normalized_questions.json"
    enrichments_path = args.enrichments or processed_dir / "llm_enrichments.json"
    out_path = args.out or processed_dir / "actor_quote_queue.json"

    queue = build_actor_quote_queue(
        questions_path=questions_path,
        enrichments_path=enrichments_path,
        only_enriched_summaries=args.only_enriched_summaries,
        limit=args.limit or None,
        text_max_chars=args.text_max_chars,
    )
    write_json(out_path, queue)
    print(json.dumps({"output": str(out_path), "items": len(queue.get("items", []))}, ensure_ascii=False, indent=2))


def build_actor_quote_queue(
    *,
    questions_path: Path,
    enrichments_path: Path,
    only_enriched_summaries: bool = False,
    limit: int | None = None,
    text_max_chars: int = 12000,
) -> dict[str, Any]:
    questions_payload = read_json(questions_path)
    questions = questions_payload.get("items", []) if isinstance(questions_payload, dict) else []
    done_summaries = load_done_summary_ids(enrichments_path) if only_enriched_summaries else set()

    items: list[dict[str, Any]] = []
    for question in questions:
        if not isinstance(question, dict):
            continue
        question_id = clean_text(question.get("id"))
        if not question_id:
            continue
        if only_enriched_summaries and f"summarize_question:{question_id}" not in done_summaries:
            continue
        segments = build_segments(question, text_max_chars=text_max_chars)
        if not segments:
            continue
        subject_id = question_subject_id(question)
        items.append(
            {
                "id": f"extract_actor_quotes:{question_id}",
                "task": "extract_actor_quotes",
                "source_id": question_id,
                "subject_id": subject_id,
                "input": {
                    "source_id": question_id,
                    "source_type": question.get("resource_type") or "question_parlementaire",
                    "source_label": question.get("resource_label") or "Question parlementaire",
                    "subject_id": subject_id,
                    "subject_title": question.get("title") or question_id,
                    "date": question.get("date") or "",
                    "rubrique": question.get("rubrique") or "",
                    "source_url": question.get("source_url") or "#",
                    "segments": segments,
                    "known_actors": [segment["actor"] for segment in segments],
                },
                "expected_output": {
                    "quotes": [
                        {
                            "segment_id": "question|answer",
                            "actor_id": "PA... ou organeRef",
                            "actor_name": "Nom affichable",
                            "stance": "alerte|demande_action|critique|justification|annonce_mesure|proposition|soutien|opposition|réserve|mise_en_cause|défense_bilan",
                            "argument_summary": "Résumé court de l'argument porté par la citation.",
                            "quote": "Citation exacte courte extraite du segment.",
                            "quote_context": "Contexte immédiat, sans inventer.",
                            "tags": [],
                            "confidence": 0.0,
                            "needs_review": False,
                        }
                    ]
                },
            }
        )
        if limit is not None and len(items) >= limit:
            break

    return {
        "schema_version": SCHEMA_VERSION,
        "prompt_version": PROMPT_VERSION,
        "generated_at": now_iso(),
        "source_questions": str(questions_path),
        "selection": {
            "only_enriched_summaries": only_enriched_summaries,
            "limit": limit or 0,
            "selected_count": len(items),
        },
        "items": items,
    }


def build_segments(question: dict[str, Any], *, text_max_chars: int) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    author = question.get("author") or {}
    author_id = clean_text(question.get("author_ref")) or f"author-{question.get('id', '')}"
    question_text = llm_text(question.get("question_text") or question.get("text_excerpt"), text_max_chars)
    if question_text:
        segments.append(
            {
                "id": "question",
                "kind": "question",
                "actor": {
                    "id": author_id,
                    "name": clean_text(author.get("name")) or author_id or "Auteur de la question",
                    "role": "Député / auteur de la question",
                    "party": clean_text(question.get("group_short_label") or question.get("group_label")),
                    "type": "deputy",
                },
                "text": question_text,
            }
        )
    ministry_id = clean_text(question.get("target_ministry_ref")) or f"target-{question.get('id', '')}"
    answer_text = llm_text(question.get("answer_text") or "", text_max_chars)
    if answer_text:
        segments.append(
            {
                "id": "answer",
                "kind": "answer",
                "actor": {
                    "id": ministry_id,
                    "name": clean_text(question.get("target_ministry")) or "Gouvernement",
                    "role": "Ministère / réponse gouvernementale",
                    "party": "Gouvernement",
                    "type": "institution",
                },
                "text": answer_text,
            }
        )
    return segments


def load_done_summary_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    payload = read_json(path)
    records: Iterable[Any]
    if isinstance(payload, dict) and isinstance(payload.get("enrichments"), dict):
        records = payload["enrichments"].values()
    elif isinstance(payload, dict) and isinstance(payload.get("items"), list):
        records = payload["items"]
    elif isinstance(payload, dict):
        records = payload.values()
    elif isinstance(payload, list):
        records = payload
    else:
        records = []
    done: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            continue
        item_id = clean_text(record.get("id") or record.get("item_id") or record.get("queue_id"))
        task = clean_text(record.get("task"))
        source_id = clean_text(record.get("source_id"))
        status = clean_text(record.get("status") or record.get("validation_status"))
        if item_id.startswith("summarize_question:") and status != "error":
            done.add(item_id)
        elif task == "summarize_question_and_answer" and source_id and status != "error":
            done.add(f"summarize_question:{source_id}")
    return done


def question_subject_id(question: dict[str, Any]) -> str:
    return f"question-{slugify(question.get('id') or question.get('title') or 'sans-id')}"


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
    if not isinstance(value, str):
        return ""
    return value.replace("\xa0", " ").strip()


def llm_text(value: Any, max_chars: int) -> str:
    text = re.sub(r"\s+", " ", clean_text(value)).strip()
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


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
