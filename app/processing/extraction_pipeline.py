from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import jsonschema

from app.core.settings import DATA_DIR, SCHEMAS_DIR
from app.ia.provider import LLMProvider, load_base_prompt

SCHEMA_PATH = SCHEMAS_DIR / "agoraloi_processed_payload.schema.json"
KNOWN_TAXONOMY_PATH = DATA_DIR / "debate_subjects.json"


class ExtractionError(Exception):
    pass


def load_known_taxonomy() -> dict:
    categories = json.loads(KNOWN_TAXONOMY_PATH.read_text(encoding="utf-8"))
    domains = []
    for category in categories:
        domains.append(
            {
                "id": category["id"],
                "label": category["label"],
                "subthemes": [
                    {
                        "id": subtheme["id"],
                        "label": subtheme["label"],
                        "subjects": [
                            {"id": subject["id"], "title": subject["title"]}
                            for subject in subtheme.get("subjects", [])
                        ],
                    }
                    for subtheme in category.get("subthemes", [])
                ],
            }
        )
    return {"domains": domains}


def build_extraction_input(source: dict, known_taxonomy: dict) -> dict:
    return {"source": source, "known_taxonomy": known_taxonomy}


def _strip_code_fence(text: str) -> str:
    match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    return match.group(1) if match else text


def _build_raw_source(source: dict) -> dict:
    return {
        "id": source["id"],
        "type": source["type"],
        "institution": source["institution"],
        "date": source["date"],
        "title": source["title"],
        "url": source["url"],
        "official_identifier": source.get("official_identifier", ""),
        "original_text": source["text"],
        "metadata": source["metadata"],
    }


def _build_processing(llm_provider: LLMProvider, global_confidence: float) -> dict:
    return {
        "run_id": f"run_{uuid.uuid4().hex[:12]}",
        "processed_at": datetime.now(timezone.utc).isoformat(),
        "model": llm_provider.settings.model or "unknown",
        "prompt_version": "agoraloi_prompt_v0.2",
        "status": "automatic",
        "global_confidence": global_confidence,
        "warnings": [],
    }


_TAXONOMY_LINK_ALIASES = {"domain": "domain_id", "subtheme": "subtheme_id", "subject": "subject_id"}
_TAXONOMY_LINK_ALLOWED_KEYS = {
    "domain_id",
    "domain_label",
    "subtheme_id",
    "subtheme_label",
    "subject_id",
    "subject_title",
    "link_strength",
    "rationale",
    "confidence",
}


def _normalize_taxonomy_links(links: list[Any]) -> list[dict]:
    normalized = []
    for link in links:
        if not isinstance(link, dict):
            continue
        renamed = {_TAXONOMY_LINK_ALIASES.get(key, key): value for key, value in link.items()}
        normalized.append({key: value for key, value in renamed.items() if key in _TAXONOMY_LINK_ALLOWED_KEYS})
    return normalized


def run_extraction(source: dict, known_taxonomy: dict, llm_provider: LLMProvider) -> dict:
    if not llm_provider.is_enabled():
        raise ExtractionError("Aucun LLM configuré (GROQ_API_KEY manquante) : extraction impossible.")
    extraction_input = build_extraction_input(source, known_taxonomy)
    user_message = "MODE: extraction_documentaire\n\n" + json.dumps(extraction_input, ensure_ascii=False, indent=2)
    raw_output = llm_provider.complete(system_prompt=load_base_prompt(), user_message=user_message)
    try:
        model_output = json.loads(_strip_code_fence(raw_output))
    except json.JSONDecodeError as exc:
        raise ExtractionError(f"Réponse du modèle non conforme JSON : {exc}") from exc

    extracted_traces = model_output.get("extracted_traces", [])
    confidences = [trace.get("confidence", 0.0) for trace in extracted_traces if isinstance(trace, dict)]
    global_confidence = sum(confidences) / len(confidences) if confidences else 0.0

    # raw_source et processing sont reconstruits par le pipeline (voir extraction_prompt.md,
    # Mode A) plutôt que recopiés par le modèle, qui oubliait des champs obligatoires du schéma.
    return {
        "schema_version": "0.1.0",
        "processing": _build_processing(llm_provider, global_confidence),
        "raw_source": _build_raw_source(source),
        "extracted_traces": extracted_traces,
        "taxonomy_links": _normalize_taxonomy_links(model_output.get("taxonomy_links", [])),
        "subject_updates": model_output.get("subject_updates", []),
    }


def validate_payload(payload: dict) -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.validate(instance=payload, schema=schema)


def process_source(
    source: dict,
    known_taxonomy: dict,
    llm_provider: LLMProvider,
    processed_dir: Path,
    failed_dir: Path,
) -> dict:
    try:
        payload = run_extraction(source, known_taxonomy, llm_provider)
        validate_payload(payload)
    except (ExtractionError, jsonschema.ValidationError, httpx.HTTPError) as exc:
        failed_dir.mkdir(parents=True, exist_ok=True)
        (failed_dir / f"{source['id']}.json").write_text(
            json.dumps({"source_id": source["id"], "error": str(exc)}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return {"id": source["id"], "status": "failed", "reason": str(exc)}

    processed_dir.mkdir(parents=True, exist_ok=True)
    (processed_dir / f"{source['id']}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {"id": source["id"], "status": "validated", "reason": ""}
