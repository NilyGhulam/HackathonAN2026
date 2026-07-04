#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description="Importe un payload AgorIA traité dans data/curated ou data/processed.")
    parser.add_argument("payload", type=Path, help="Chemin du fichier JSON conforme au schéma AgorIA.")
    parser.add_argument("--status", choices=["validated", "needs_review", "automatic"], default="needs_review")
    parser.add_argument("--target", choices=["curated", "processed"], default="curated")
    args = parser.parse_args()

    with args.payload.open("r", encoding="utf-8") as stream:
        payload = json.load(stream)

    required = {"schema_version", "processing", "raw_source", "extracted_traces", "taxonomy_links", "subject_updates"}
    missing = required - set(payload)
    if missing:
        raise SystemExit(f"Payload incomplet, clés manquantes: {', '.join(sorted(missing))}")

    payload["processing"]["status"] = args.status
    raw_id = payload["raw_source"].get("id", args.payload.stem)
    out_dir = ROOT / "data" / args.target
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{raw_id}.json"
    with out_path.open("w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(out_path)


if __name__ == "__main__":
    main()
