#!/usr/bin/env python3
"""Récolte les questions écrites de l'Assemblée nationale (DEFI.md : an-questions-gouvernement-ecrites)
et les transforme en traces structurées via le pipeline app/processing (Mode A de
docs/api/extraction_prompt.md), conformes à data/schemas/agoraloi_processed_payload.schema.json.

Usage :
    .venv/bin/python scripts/ingest_an_questions.py --rubrique "fin de vie et soins palliatifs" --limit 5
"""
from __future__ import annotations

import argparse
import itertools
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.settings import BASE_DIR, PROCESSED_DATA_DIR, RAW_DATA_DIR
from app.ia.provider import LLMProvider
from app.ingestion.an_questions_ecrites import (
    download_archive,
    filter_by_rubrique,
    iter_raw_questions,
    normalize_source,
    save_raw,
)
from app.processing.extraction_pipeline import load_known_taxonomy, process_source

ARCHIVE_CACHE = RAW_DATA_DIR / "_cache" / "an_questions_ecrites.json.zip"
SOURCE_NAME = "an_questions_ecrites"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rubrique", default="fin de vie et soins palliatifs")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--delay", type=float, default=25.0, help="secondes entre deux appels LLM")
    parser.add_argument("--force", action="store_true", help="retraiter même les sources déjà validées")
    args = parser.parse_args()

    llm_provider = LLMProvider()
    if not llm_provider.is_enabled():
        print("GROQ_API_KEY manquante (.env) : impossible de lancer la transformation IA.", file=sys.stderr)
        return 1

    print(f"Téléchargement/vérification de l'archive ({ARCHIVE_CACHE})...")
    archive_path = download_archive(ARCHIVE_CACHE)

    known_taxonomy = load_known_taxonomy()
    raw_dir = RAW_DATA_DIR / SOURCE_NAME
    processed_dir = PROCESSED_DATA_DIR / SOURCE_NAME
    failed_dir = PROCESSED_DATA_DIR / SOURCE_NAME / "_failed"

    questions = filter_by_rubrique(iter_raw_questions(archive_path), args.rubrique)
    selected = list(itertools.islice(questions, args.limit))
    print(f"{len(selected)} question(s) sélectionnée(s) pour la rubrique « {args.rubrique} ».")

    results = []
    is_first_call = True
    for item in selected:
        uid = (item.get("question") or {}).get("uid", "")
        already_done = processed_dir / f"an_qe_{uid}.json"
        if already_done.exists() and not args.force:
            print(f"  - an_qe_{uid}: skipped (déjà validée)")
            continue
        if not is_first_call:
            time.sleep(args.delay)  # reste sous la limite de tokens/minute de Groq
        is_first_call = False
        save_raw(item, raw_dir)
        source = normalize_source(item)
        result = process_source(source, known_taxonomy, llm_provider, processed_dir, failed_dir)
        results.append(result)
        print(f"  - {result['id']}: {result['status']}" + (f" ({result['reason']})" if result["reason"] else ""))

    validated = sum(1 for r in results if r["status"] == "validated")
    failed = sum(1 for r in results if r["status"] == "failed")
    print(f"\nTerminé : {validated} validée(s), {failed} échouée(s).")
    print(f"Sources brutes : {raw_dir.relative_to(BASE_DIR)}")
    print(f"Sorties structurées : {processed_dir.relative_to(BASE_DIR)}")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
