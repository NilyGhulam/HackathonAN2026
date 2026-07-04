#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description="Télécharge une source officielle brute et la stocke dans data/raw.")
    parser.add_argument("url", help="URL JSON ou texte de la source officielle")
    parser.add_argument("--id", required=True, help="Identifiant stable interne, ex: an_amendement_12345")
    parser.add_argument("--type", default="other", help="Type AgorIA: amendment, bill, public_session_debate...")
    parser.add_argument("--institution", default="assemblee_nationale")
    args = parser.parse_args()

    response = httpx.get(args.url, timeout=30.0, follow_redirects=True)
    response.raise_for_status()
    content_type = response.headers.get("content-type", "")
    try:
        body = response.json()
    except ValueError:
        body = response.text

    out_dir = ROOT / "data" / "raw"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{args.id}.json"
    payload = {
        "id": args.id,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "url": args.url,
        "type": args.type,
        "institution": args.institution,
        "content_type": content_type,
        "body": body,
    }
    with out_path.open("w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(out_path)


if __name__ == "__main__":
    main()
