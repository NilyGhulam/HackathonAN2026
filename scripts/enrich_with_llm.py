#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "0.1.0"
PROMPT_VERSION = "agoria_llm_enrichment_v1"
DEFAULT_MODEL = "gpt-4o-mini"

SYSTEM_PROMPT = """Tu es un assistant de curation de données parlementaires françaises pour AgorIA.
Ta mission est de produire une sortie JSON stricte, sourcée par les champs fournis, sans inventer de fait.
Règles impératives :
- Réponds uniquement avec un objet JSON valide, sans markdown.
- N'invente aucun nom, date, mesure ou citation absent du contexte.
- Utilise des catégories neutres, stables, non militantes.
- Une catégorie sert à rendre la carte mentale lisible ; les nuances politiques vont dans les tags et résumés.
- Choisis un seul chemin canonique principal.
- Ne crée une nouvelle catégorie que si les catégories existantes ne suffisent pas.
- La profondeur recommandée est 3 ; la profondeur maximale est 4.
- Les tags peuvent être transversaux, mais le chemin canonique doit rester unique.
"""


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Enrichit data/processed/llm_enrichment_queue.json avec un LLM ciblé, "
            "puis fusionne les résumés/classifications dans le payload curated."
        )
    )
    parser.add_argument("--processed-dir", type=Path, default=ROOT / "data" / "processed")
    parser.add_argument("--curated-payload", type=Path, default=ROOT / "data" / "curated" / "agoria_raw_extract.json")
    parser.add_argument("--output-payload", type=Path, default=None, help="Par défaut, met à jour --curated-payload en place.")
    parser.add_argument("--provider", choices=["dry-run", "mock", "openai-compatible"], default=os.getenv("AGORIA_LLM_PROVIDER", "dry-run"))
    parser.add_argument("--base-url", default=os.getenv("AGORIA_LLM_BASE_URL", "https://api.openai.com/v1"))
    parser.add_argument("--api-key", default=os.getenv("AGORIA_LLM_API_KEY"))
    parser.add_argument("--model", default=os.getenv("AGORIA_LLM_MODEL", DEFAULT_MODEL))
    parser.add_argument("--limit", type=int, default=0, help="Nombre maximal d'items à traiter. 0 = tout.")
    parser.add_argument("--only-task", choices=["classify_subject", "summarize_question_and_answer"], default=None)
    parser.add_argument("--force", action="store_true", help="Ignore le cache et relance les items déjà enrichis.")
    parser.add_argument("--apply", action="store_true", help="Fusionne les enrichissements réussis dans le payload curated.")
    parser.add_argument("--write-prompts", action="store_true", help="Écrit les prompts dans data/processed/llm_prompts/ pour audit.")
    parser.add_argument("--sleep", type=float, default=0.0, help="Pause entre appels LLM, en secondes.")
    args = parser.parse_args()

    result = enrich_with_llm(
        processed_dir=args.processed_dir,
        curated_payload=args.curated_payload,
        output_payload=args.output_payload,
        provider_name=args.provider,
        base_url=args.base_url,
        api_key=args.api_key,
        model=args.model,
        limit=args.limit or None,
        only_task=args.only_task,
        force=args.force,
        apply=args.apply,
        write_prompts=args.write_prompts,
        sleep_seconds=args.sleep,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


def enrich_with_llm(
    *,
    processed_dir: Path,
    curated_payload: Path,
    output_payload: Path | None = None,
    provider_name: str = "dry-run",
    base_url: str = "https://api.openai.com/v1",
    api_key: str | None = None,
    model: str = DEFAULT_MODEL,
    limit: int | None = None,
    only_task: str | None = None,
    force: bool = False,
    apply: bool = False,
    write_prompts: bool = False,
    sleep_seconds: float = 0.0,
) -> dict[str, Any]:
    queue_path = processed_dir / "llm_enrichment_queue.json"
    enrichments_path = processed_dir / "llm_enrichments.json"
    prompts_dir = processed_dir / "llm_prompts"

    queue_doc = read_json(queue_path)
    items = list(queue_doc.get("items", []))
    if only_task:
        items = [item for item in items if item.get("task") == only_task]
    if limit is not None:
        items = items[:limit]

    cache_doc = read_json(enrichments_path) if enrichments_path.exists() else empty_enrichments_doc()
    cache_by_key = {item.get("cache_key"): item for item in cache_doc.get("items", []) if item.get("cache_key")}
    provider = provider_from_name(provider_name, base_url=base_url, api_key=api_key, model=model)

    processed: list[dict[str, Any]] = []
    skipped = 0
    failed = 0

    if write_prompts:
        prompts_dir.mkdir(parents=True, exist_ok=True)

    for item in items:
        cache_key = item_cache_key(item)
        if not force and cache_key in cache_by_key and cache_by_key[cache_key].get("status") == "ok":
            processed.append(cache_by_key[cache_key])
            skipped += 1
            continue

        prompt = build_prompt(item)
        if write_prompts:
            prompt_path = prompts_dir / f"{safe_filename(item.get('id', cache_key))}.txt"
            prompt_path.write_text(prompt, encoding="utf-8")

        started_at = now_iso()
        try:
            if provider_name == "dry-run":
                output = None
                status = "pending"
                error = "dry-run: prompt généré, aucun appel LLM effectué"
            else:
                output = provider.complete_json(system_prompt=SYSTEM_PROMPT, user_prompt=prompt)
                output = validate_task_output(item, output)
                status = "ok"
                error = ""
        except Exception as exc:  # noqa: BLE001 - on veut journaliser l'erreur de provider.
            output = None
            status = "error"
            error = str(exc)
            failed += 1

        record = {
            "id": item.get("id"),
            "task": item.get("task"),
            "source_id": item.get("source_id"),
            "cache_key": cache_key,
            "status": status,
            "provider": provider_name,
            "model": model if provider_name != "dry-run" else None,
            "prompt_version": PROMPT_VERSION,
            "created_at": started_at,
            "input_fingerprint": fingerprint(item.get("input", {})),
            "output": output,
            "error": error,
        }
        cache_by_key[cache_key] = record
        processed.append(record)
        if sleep_seconds:
            time.sleep(sleep_seconds)

    new_cache_doc = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now_iso(),
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
        "provider": provider_name,
        "queue_items_seen": len(items),
        "cache_path": str(enrichments_path),
        "prompts_dir": str(prompts_dir) if write_prompts else None,
        "counts": {
            "processed_or_loaded": len(processed),
            "cache_hits": skipped,
            "failed": failed,
            "ok_total_in_cache": sum(1 for item in new_cache_doc["items"] if item.get("status") == "ok"),
            "pending_total_in_cache": sum(1 for item in new_cache_doc["items"] if item.get("status") == "pending"),
            "applied_to_payload": applied_count,
        },
        "applied_payload": applied_payload,
        "next_steps": next_steps(provider_name, apply),
    }


class BaseProvider:
    def complete_json(self, *, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        raise NotImplementedError


class MockProvider(BaseProvider):
    def complete_json(self, *, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        payload = json.loads(user_prompt)
        task = payload.get("task")
        data = payload.get("input", {})
        if task == "summarize_question_and_answer":
            title = clean_text(data.get("title")) or "Question parlementaire"
            question_text = clean_text(data.get("question_text"))
            answer_text = clean_text(data.get("answer_text"))
            return {
                "question_summary": excerpt(f"Question sur {title}. {question_text}", 420),
                "answer_summary": excerpt(f"Réponse gouvernementale relative à {title}. {answer_text}", 420),
                "issues": compact_unique([data.get("rubrique"), title]),
                "announced_measures": [],
                "quotes": first_quotes(question_text, answer_text),
                "confidence": 0.35,
                "needs_review": True,
            }
        if task == "classify_subject":
            title = clean_text(data.get("title"))
            current_path = [clean_text(item) for item in data.get("current_path", []) if clean_text(item)]
            path = current_path[:2] or ["Sources parlementaires", "Sujets importés"]
            if title and len(path) < 3:
                path.append(title[:80])
            return {
                "canonical_path": path[:4],
                "tags": compact_unique([title, clean_text(data.get("context"))])[:6],
                "new_category_proposal": {"needed": False},
                "alternative_paths": [],
                "confidence": 0.35,
                "needs_review": True,
                "rationale": "Sortie mock de développement : à remplacer par un vrai LLM ou une relecture.",
            }
        return {"confidence": 0.0, "needs_review": True}


class OpenAICompatibleProvider(BaseProvider):
    def __init__(self, *, base_url: str, api_key: str | None, model: str) -> None:
        if not api_key:
            raise ValueError("AGORIA_LLM_API_KEY ou --api-key est requis pour --provider openai-compatible")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    def complete_json(self, *, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        url = f"{self.base_url}/chat/completions"
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }
        request = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=90) as response:  # noqa: S310 - endpoint choisi par l'utilisateur.
                raw_response = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Erreur HTTP LLM {exc.code}: {details[:1000]}") from exc
        content = raw_response.get("choices", [{}])[0].get("message", {}).get("content", "")
        if not content:
            raise RuntimeError("Réponse LLM vide ou format inattendu")
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Réponse LLM non JSON: {content[:1000]}") from exc
        if not isinstance(parsed, dict):
            raise RuntimeError("La réponse LLM doit être un objet JSON")
        return parsed


def provider_from_name(name: str, *, base_url: str, api_key: str | None, model: str) -> BaseProvider:
    if name == "mock":
        return MockProvider()
    if name == "openai-compatible":
        return OpenAICompatibleProvider(base_url=base_url, api_key=api_key, model=model)
    if name == "dry-run":
        return BaseProvider()
    raise ValueError(f"Provider inconnu: {name}")


def build_prompt(item: dict[str, Any]) -> str:
    task = item.get("task")
    if task == "summarize_question_and_answer":
        instructions = {
            "task": task,
            "goal": "Résumer une question parlementaire et la réponse gouvernementale pour une chronologie et une carte des acteurs.",
            "output_contract": {
                "question_summary": "2 phrases maximum, centrées sur la demande ou l'alerte du parlementaire.",
                "answer_summary": "2 phrases maximum, centrées sur la réponse ou les mesures annoncées par le Gouvernement.",
                "issues": "Liste de 3 à 8 problèmes publics neutres.",
                "announced_measures": "Liste de mesures explicitement présentes dans la réponse, sans invention.",
                "quotes": "0 à 3 citations courtes, chacune avec speaker si identifiable et text.",
                "confidence": "Nombre entre 0 et 1.",
                "needs_review": "Booléen. true si le texte est ambigu, incomplet, polémique ou très long.",
            },
        }
    elif task == "classify_subject":
        instructions = {
            "task": task,
            "goal": "Classer un sujet dans une taxonomie de carte mentale lisible.",
            "classification_rules": [
                "Choisir un seul canonical_path principal.",
                "Niveau 1 = grand domaine public ; niveau 2 = politique publique/sous-domaine ; niveau 3 = sujet concret ; niveau 4 = angle précis facultatif.",
                "Ne pas créer une catégorie à partir d'un parti, d'un acteur, d'une date ou d'une formulation militante.",
                "Si le chemin existant est suffisant, le réutiliser.",
                "Si une catégorie intermédiaire manque pour éviter trop d'enfants visibles, proposer new_category_proposal.needed=true.",
            ],
            "output_contract": {
                "canonical_path": "Liste de 2 à 4 libellés neutres.",
                "tags": "Liste de 3 à 10 tags transversaux.",
                "new_category_proposal": "Objet {needed, level, label, parent_path, reason}.",
                "alternative_paths": "Liste de chemins alternatifs si ambiguïté.",
                "confidence": "Nombre entre 0 et 1.",
                "needs_review": "Booléen.",
                "rationale": "Justification courte à partir des champs fournis.",
            },
        }
    else:
        instructions = {"task": task, "goal": "Retourner un JSON structuré conforme à expected_output."}

    return json.dumps(
        {
            "prompt_version": PROMPT_VERSION,
            **instructions,
            "source_id": item.get("source_id"),
            "input": item.get("input", {}),
            "expected_output_hint": item.get("expected_output", {}),
        },
        ensure_ascii=False,
        indent=2,
    )


def validate_task_output(item: dict[str, Any], output: dict[str, Any]) -> dict[str, Any]:
    task = item.get("task")
    if task == "summarize_question_and_answer":
        return {
            "question_summary": excerpt(output.get("question_summary"), 700),
            "answer_summary": excerpt(output.get("answer_summary"), 700),
            "issues": list_of_short_strings(output.get("issues"), max_items=10),
            "announced_measures": list_of_short_strings(output.get("announced_measures"), max_items=10),
            "quotes": validate_quotes(output.get("quotes")),
            "confidence": clamp_float(output.get("confidence"), default=0.5),
            "needs_review": bool(output.get("needs_review", True)),
        }
    if task == "classify_subject":
        canonical_path = list_of_short_strings(output.get("canonical_path"), max_items=4)
        if len(canonical_path) < 2:
            current_path = item.get("input", {}).get("current_path", [])
            canonical_path = list_of_short_strings(current_path, max_items=4) or ["Sources parlementaires", "Sujets importés"]
        proposal = output.get("new_category_proposal") if isinstance(output.get("new_category_proposal"), dict) else {"needed": False}
        return {
            "canonical_path": canonical_path,
            "tags": list_of_short_strings(output.get("tags"), max_items=12),
            "new_category_proposal": {
                "needed": bool(proposal.get("needed", False)),
                "level": proposal.get("level"),
                "label": excerpt(proposal.get("label"), 120),
                "parent_path": list_of_short_strings(proposal.get("parent_path"), max_items=4),
                "reason": excerpt(proposal.get("reason"), 500),
            },
            "alternative_paths": [list_of_short_strings(path, max_items=4) for path in as_list(output.get("alternative_paths")) if isinstance(path, list)][:5],
            "confidence": clamp_float(output.get("confidence"), default=0.5),
            "needs_review": bool(output.get("needs_review", True)),
            "rationale": excerpt(output.get("rationale"), 700),
        }
    return output


def apply_enrichments_to_payload(payload: dict[str, Any], records: list[dict[str, Any]]) -> tuple[dict[str, Any], int]:
    applied = 0
    subject_updates = payload.get("subject_updates", [])
    traces = payload.get("extracted_traces", [])
    taxonomy_links = payload.get("taxonomy_links", [])

    subjects_by_id = {item.get("subject_id"): item for item in subject_updates}
    traces_by_id = {item.get("id"): item for item in traces}
    taxonomy_by_subject = {item.get("subject_id"): item for item in taxonomy_links}

    for record in records:
        task = record.get("task")
        source_id = record.get("source_id")
        output = record.get("output") or {}
        if task == "summarize_question_and_answer":
            trace = traces_by_id.get(source_id)
            subject_id = None
            if trace:
                subject_id = (trace.get("metadata") or {}).get("subject_id")
                trace["summary"] = output.get("question_summary") or trace.get("summary")
                if output.get("issues"):
                    trace["issues"] = output["issues"]
                trace["confidence"] = output.get("confidence", trace.get("confidence"))
                trace["validation_status"] = "needs_review" if output.get("needs_review", True) else "automatic"
                metadata = trace.setdefault("metadata", {})
                metadata["question_summary"] = output.get("question_summary")
                metadata["answer_summary"] = output.get("answer_summary")
                metadata["announced_measures"] = output.get("announced_measures", [])
                metadata["llm_prompt_version"] = PROMPT_VERSION
                if output.get("quotes"):
                    trace["evidence"] = [
                        {
                            "quote": quote.get("text"),
                            "speaker": quote.get("speaker"),
                            "source_url": (trace.get("evidence") or [{}])[0].get("source_url", "#"),
                            "source_file": (trace.get("evidence") or [{}])[0].get("source_file"),
                        }
                        for quote in output["quotes"]
                        if quote.get("text")
                    ] or trace.get("evidence", [])
                applied += 1
            if subject_id and subject_id in subjects_by_id:
                subject = subjects_by_id[subject_id]
                subject["summary"] = output.get("question_summary") or subject.get("summary")
                for event in subject.get("timeline_events", []):
                    if event.get("source_id") == source_id:
                        event["summary"] = output.get("answer_summary") or event.get("summary")
                        event["question_summary"] = output.get("question_summary")
                        event["answer_summary"] = output.get("answer_summary")
                        event["announced_measures"] = output.get("announced_measures", [])
                for cluster in subject.get("argument_clusters", []):
                    if cluster.get("id") == f"question-{slugify(source_id)}":
                        cluster["summary"] = output.get("question_summary") or cluster.get("summary")
                        cluster["issues"] = output.get("issues", [])
                        cluster.setdefault("response", {})["summary"] = output.get("answer_summary") or cluster.get("response", {}).get("summary")
                        cluster["announced_measures"] = output.get("announced_measures", [])
        elif task == "classify_subject":
            subject = subjects_by_id.get(source_id)
            link = taxonomy_by_subject.get(source_id)
            if not subject:
                continue
            path = output.get("canonical_path") or []
            tags = output.get("tags") or []
            subject["classification"] = {
                **subject.get("classification", {}),
                "canonical_path": path,
                "tags": tags,
                "confidence": output.get("confidence"),
                "needs_review": output.get("needs_review", True),
                "new_category_proposal": output.get("new_category_proposal", {"needed": False}),
                "alternative_paths": output.get("alternative_paths", []),
                "rationale": output.get("rationale", ""),
                "taxonomy_version": PROMPT_VERSION,
            }
            if link and path:
                domain_label = path[0]
                subtheme_label = path[1] if len(path) > 1 else "Sujets importés"
                link["domain_id"] = slugify(domain_label) or "sources-parlementaires"
                link["domain_label"] = domain_label
                link["subtheme_id"] = f"{link['domain_id']}__{slugify(subtheme_label) or 'sujets-importes'}"
                link["subtheme_label"] = subtheme_label
                link["link_strength"] = "high" if output.get("confidence", 0) >= 0.75 else "medium"
                link["rationale"] = output.get("rationale") or "Classification LLM ciblée."
                link["confidence"] = output.get("confidence", link.get("confidence", 0.55))
                link["taxonomy_version"] = PROMPT_VERSION
            applied += 1

    processing = payload.setdefault("processing", {})
    processing["model"] = join_non_empty([processing.get("model"), "llm_enrichment"], separator="+")
    processing["prompt_version"] = PROMPT_VERSION
    processing["llm_enriched_at"] = now_iso()
    notes = processing.setdefault("notes", [])
    if "Payload enrichi par LLM ciblé ; les données gardent un statut de relecture tant qu'elles ne sont pas validées." not in notes:
        notes.append("Payload enrichi par LLM ciblé ; les données gardent un statut de relecture tant qu'elles ne sont pas validées.")
    return payload, applied


def empty_enrichments_doc() -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "generated_at": now_iso(), "prompt_version": PROMPT_VERSION, "items": []}


def item_cache_key(item: dict[str, Any]) -> str:
    return f"{PROMPT_VERSION}:{item.get('task')}:{item.get('source_id')}:{fingerprint(item.get('input', {}))}"


def fingerprint(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:24]


def safe_filename(value: Any) -> str:
    return slugify(value)[:120] or fingerprint(value)


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


def next_steps(provider_name: str, apply: bool) -> list[str]:
    if provider_name == "dry-run":
        return [
            "Relire les prompts générés avec --write-prompts.",
            "Relancer avec --provider mock pour tester la fusion sans appel externe, ou --provider openai-compatible avec une clé API.",
        ]
    if not apply:
        return ["Relancer avec --apply pour fusionner les enrichissements réussis dans data/curated/agoria_raw_extract.json."]
    return ["Lancer AGORIA_DATA_MODE=auto ./scripts/run.sh pour visualiser le payload enrichi."]


def list_of_short_strings(value: Any, *, max_items: int) -> list[str]:
    values = []
    for item in as_list(value):
        text = excerpt(item, 160)
        if text and text not in values:
            values.append(text)
        if len(values) >= max_items:
            break
    return values


def validate_quotes(value: Any) -> list[dict[str, str]]:
    quotes = []
    for item in as_list(value):
        if isinstance(item, str):
            text = excerpt(item, 280)
            speaker = ""
        elif isinstance(item, dict):
            text = excerpt(item.get("text") or item.get("quote"), 280)
            speaker = excerpt(item.get("speaker"), 120)
        else:
            continue
        if text:
            quotes.append({"speaker": speaker, "text": text})
        if len(quotes) >= 3:
            break
    return quotes


def first_quotes(question_text: str, answer_text: str) -> list[dict[str, str]]:
    quotes = []
    for text, speaker in [(question_text, "Auteur de la question"), (answer_text, "Gouvernement")]:
        sentence = first_sentence(text)
        if sentence:
            quotes.append({"speaker": speaker, "text": excerpt(sentence, 220)})
    return quotes


def first_sentence(value: Any) -> str:
    text = clean_text(value)
    if not text:
        return ""
    parts = re.split(r"(?<=[.!?])\s+", text)
    return parts[0] if parts else text


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def clamp_float(value: Any, *, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return max(0.0, min(1.0, number))


def compact_unique(values: list[Any]) -> list[str]:
    output = []
    for value in values:
        text = excerpt(value, 120)
        if text and text not in output:
            output.append(text)
    return output


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return str(value)
    if not isinstance(value, str):
        return ""
    return re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip()


def excerpt(value: Any, max_chars: int = 500) -> str:
    text = clean_text(value)
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def join_non_empty(values: list[Any], *, separator: str) -> str:
    return separator.join(clean_text(value) for value in values if clean_text(value))


def slugify(value: Any) -> str:
    text = clean_text(value).lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:90]


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


if __name__ == "__main__":
    try:
        main()
    except FileNotFoundError as exc:
        print(f"Fichier manquant: {exc}", file=sys.stderr)
        sys.exit(2)
