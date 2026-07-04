from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from app.core.settings import BASE_DIR


DATA_ROOT = BASE_DIR / "data"
MAX_JSON_SUMMARY_BYTES = 50 * 1024 * 1024


def build_data_inventory(base_dir: Path = BASE_DIR) -> dict[str, Any]:
    """Construit un état lisible des fichiers de données du projet.

    La page Sources ne modifie rien : elle observe ce qui est présent dans
    data/raw, data/processed, data/curated et data/demo pour rendre visible le
    travail fait sur les données officielles.
    """

    data_root = base_dir / "data"
    raw = _raw_directory_section(
        key="raw",
        label="Raw",
        path=data_root / "raw",
        description="Données officielles brutes déposées localement, avant normalisation.",
    )
    processed = _directory_section(
        key="processed",
        label="Processed",
        path=data_root / "processed",
        description="Fichiers intermédiaires générés par les scripts : normalisation, taxonomie, queue LLM et cache d'enrichissement.",
        parse_json=True,
    )
    curated = _directory_section(
        key="curated",
        label="Curated",
        path=data_root / "curated",
        description="Payloads consolidés consommés par l'application quand AGORIA_DATA_MODE=auto ou processed.",
        parse_json=True,
    )
    demo = _directory_section(
        key="demo",
        label="Demo",
        path=data_root / "demo",
        description="Jeu de données fictif conservé comme fallback de démonstration.",
        parse_json=True,
    )

    queue = _llm_queue_stats(data_root / "processed" / "llm_enrichment_queue.json")
    enrichments = _llm_enrichment_stats(data_root / "processed" / "llm_enrichments.json")
    curated_payloads = _curated_payload_stats(data_root / "curated")
    normalized = _normalized_stats(data_root / "processed")

    return {
        "summary": {
            "raw_files": raw["file_count"],
            "raw_size": raw["total_size"],
            "processed_files": processed["file_count"],
            "processed_records": processed["record_count"],
            "curated_files": curated["file_count"],
            "curated_payloads": curated_payloads["payload_count"],
            "curated_subjects": curated_payloads["subject_count"],
            "curated_traces": curated_payloads["trace_count"],
            "llm_queue_total": queue["total"],
            "llm_done_total": enrichments["total"],
        },
        "sections": [raw, processed, curated, demo],
        "queue": queue,
        "enrichments": enrichments,
        "curated_payloads": curated_payloads,
        "normalized": normalized,
    }


def _directory_section(
    *,
    key: str,
    label: str,
    path: Path,
    description: str,
    parse_json: bool,
) -> dict[str, Any]:
    files = _scan_files(path, parse_json=parse_json)
    children = _top_level_breakdown(path)
    return {
        "key": key,
        "label": label,
        "path": _display_path(path),
        "exists": path.exists(),
        "description": description,
        "file_count": len(files),
        "json_count": sum(1 for item in files if item["suffix"] == ".json"),
        "total_size": sum(item["size"] for item in files),
        "total_size_label": _format_bytes(sum(item["size"] for item in files)),
        "record_count": sum(item.get("record_count") or 0 for item in files),
        "children": children,
        "files": files[:24],
        "has_more_files": len(files) > 24,
    }


def _raw_directory_section(
    *,
    key: str,
    label: str,
    path: Path,
    description: str,
) -> dict[str, Any]:
    children = _top_level_breakdown(path, recursive=True)
    file_count = sum(item["file_count"] for item in children)
    json_count = sum(item["json_count"] for item in children)
    total_size = sum(item["size"] for item in children)
    return {
        "key": key,
        "label": label,
        "path": _display_path(path),
        "exists": path.exists(),
        "description": description,
        "file_count": file_count,
        "json_count": json_count,
        "total_size": total_size,
        "total_size_label": _format_bytes(total_size),
        "record_count": 0,
        "children": children,
        "files": [],
        "has_more_files": file_count > 0,
    }


def _scan_files(path: Path, *, parse_json: bool) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    files: list[dict[str, Any]] = []
    for file_path in sorted(p for p in path.rglob("*") if p.is_file()):
        if file_path.name == ".gitkeep":
            continue
        item: dict[str, Any] = {
            "name": file_path.name,
            "relative_path": _display_path(file_path),
            "suffix": file_path.suffix.lower(),
            "size": file_path.stat().st_size,
            "size_label": _format_bytes(file_path.stat().st_size),
        }
        if parse_json and file_path.suffix.lower() == ".json":
            item.update(_json_file_summary(file_path))
        files.append(item)
    return sorted(files, key=lambda item: (item["relative_path"].count("/"), item["relative_path"]))


def _top_level_breakdown(path: Path, *, recursive: bool = False) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    buckets: dict[str, dict[str, Any]] = {}
    if recursive:
        with os.scandir(path) as entries:
            for entry in entries:
                if entry.name == ".gitkeep":
                    continue
                bucket = buckets.setdefault(entry.name, {"name": entry.name, "file_count": 0, "size": 0, "json_count": 0})
                if entry.is_file():
                    _add_file_stats(bucket, Path(entry.name), entry.stat().st_size)
                elif entry.is_dir():
                    for root, _, files in os.walk(entry.path):
                        for filename in files:
                            if filename == ".gitkeep":
                                continue
                            file_path = Path(root) / filename
                            try:
                                size = file_path.stat().st_size
                            except OSError:
                                continue
                            _add_file_stats(bucket, file_path, size)
    else:
        for file_path in sorted(p for p in path.rglob("*") if p.is_file() and p.name != ".gitkeep"):
            try:
                relative = file_path.relative_to(path)
            except ValueError:
                continue
            top = relative.parts[0] if relative.parts else file_path.name
            bucket = buckets.setdefault(top, {"name": top, "file_count": 0, "size": 0, "json_count": 0})
            _add_file_stats(bucket, file_path, file_path.stat().st_size)
    for bucket in buckets.values():
        bucket["size_label"] = _format_bytes(bucket["size"])
    return sorted(buckets.values(), key=lambda item: item["name"])


def _add_file_stats(bucket: dict[str, Any], file_path: Path, size: int) -> None:
    bucket["file_count"] += 1
    bucket["size"] += size
    if file_path.suffix.lower() == ".json":
        bucket["json_count"] += 1


def _json_file_summary(path: Path) -> dict[str, Any]:
    if path.stat().st_size > MAX_JSON_SUMMARY_BYTES:
        return {
            "record_count": 0,
            "json_kind": "too_large",
            "json_error": f"Résumé ignoré au-delà de {_format_bytes(MAX_JSON_SUMMARY_BYTES)}.",
        }
    try:
        with path.open("r", encoding="utf-8") as stream:
            data = json.load(stream)
    except Exception as exc:  # pragma: no cover - défensif pour fichiers locaux incomplets
        return {"record_count": 0, "json_error": str(exc)}

    record_count = _count_records(data)
    summary: dict[str, Any] = {"record_count": record_count, "json_kind": type(data).__name__}
    if isinstance(data, dict):
        summary["top_keys"] = list(data.keys())[:8]
    return summary


def _count_records(data: Any) -> int:
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict):
        for key in ("items", "enrichments", "subjects", "questions", "actors", "mandates", "organs", "nodes"):
            value = data.get(key)
            if isinstance(value, list):
                return len(value)
            if isinstance(value, dict):
                return len(value)
        return len(data)
    return 0


def _llm_queue_stats(path: Path) -> dict[str, Any]:
    stats = {"exists": path.exists(), "total": 0, "by_task": [], "path": _display_path(path)}
    data = _read_json(path)
    items = _items_from_json(data)
    counter = Counter(item.get("task", "unknown") for item in items if isinstance(item, dict))
    stats["total"] = sum(counter.values())
    stats["by_task"] = [{"task": key, "count": value} for key, value in sorted(counter.items())]
    return stats


def _llm_enrichment_stats(path: Path) -> dict[str, Any]:
    stats = {
        "exists": path.exists(),
        "total": 0,
        "by_task": [],
        "by_status": [],
        "needs_review": 0,
        "path": _display_path(path),
    }
    data = _read_json(path)
    items = _items_from_json(data)
    task_counter: Counter[str] = Counter()
    status_counter: Counter[str] = Counter()
    needs_review = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        task = item.get("task") or _task_from_enrichment_id(item.get("id", ""))
        task_counter[task or "unknown"] += 1
        status_counter[item.get("status", "unknown")] += 1
        output = item.get("output", {})
        if isinstance(output, dict) and output.get("needs_review"):
            needs_review += 1
    stats["total"] = sum(task_counter.values())
    stats["by_task"] = [{"task": key, "count": value} for key, value in sorted(task_counter.items())]
    stats["by_status"] = [{"status": key, "count": value} for key, value in sorted(status_counter.items())]
    stats["needs_review"] = needs_review
    return stats


def _curated_payload_stats(path: Path) -> dict[str, Any]:
    stats: dict[str, Any] = {
        "payload_count": 0,
        "subject_count": 0,
        "trace_count": 0,
        "actor_count": 0,
        "by_status": [],
        "by_raw_type": [],
        "by_institution": [],
    }
    status_counter: Counter[str] = Counter()
    raw_type_counter: Counter[str] = Counter()
    institution_counter: Counter[str] = Counter()
    for file_path in sorted(path.glob("*.json")) if path.exists() else []:
        payload = _read_json(file_path)
        if not isinstance(payload, dict):
            continue
        stats["payload_count"] += 1
        status_counter[payload.get("processing", {}).get("status", "unknown")] += 1
        raw = payload.get("raw_source", {})
        raw_type_counter[raw.get("type", "unknown")] += 1
        institution_counter[raw.get("institution", "institution non renseignée")] += 1
        stats["subject_count"] += len(payload.get("subject_updates", []))
        stats["trace_count"] += len(payload.get("extracted_traces", []))
        for subject in payload.get("subject_updates", []):
            stats["actor_count"] += len(subject.get("actors", []))
    stats["by_status"] = [{"label": key, "count": value} for key, value in sorted(status_counter.items())]
    stats["by_raw_type"] = [{"label": key, "count": value} for key, value in sorted(raw_type_counter.items())]
    stats["by_institution"] = [{"label": key, "count": value} for key, value in sorted(institution_counter.items())]
    return stats


def _normalized_stats(path: Path) -> dict[str, Any]:
    files = []
    if path.exists():
        for file_path in sorted(path.glob("normalized_*.json")):
            summary = _json_file_summary(file_path)
            files.append(
                {
                    "name": file_path.name,
                    "record_count": summary.get("record_count", 0),
                    "size_label": _format_bytes(file_path.stat().st_size),
                }
            )
    return {"files": files, "total_records": sum(item["record_count"] for item in files)}


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    if path.stat().st_size > MAX_JSON_SUMMARY_BYTES:
        return None
    try:
        with path.open("r", encoding="utf-8") as stream:
            return json.load(stream)
    except Exception:
        return None


def _items_from_json(data: Any) -> list[Any]:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        items = data.get("items")
        if isinstance(items, list):
            return items
        enrichments = data.get("enrichments")
        if isinstance(enrichments, list):
            return enrichments
        if isinstance(enrichments, dict):
            converted = []
            for key, value in enrichments.items():
                if isinstance(value, dict):
                    converted.append({"id": key, **value})
            return converted
        converted = []
        for key, value in data.items():
            if isinstance(value, dict) and (key.startswith("classify:") or key.startswith("summarize_question:")):
                converted.append({"id": key, **value})
        return converted
    return []


def _task_from_enrichment_id(identifier: str) -> str:
    if identifier.startswith("classify:"):
        return "classify_subject"
    if identifier.startswith("summarize_question:"):
        return "summarize_question_and_answer"
    return "unknown"


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(BASE_DIR))
    except ValueError:
        return str(path)


def _format_bytes(size: int) -> str:
    value = float(size)
    units = ["o", "Ko", "Mo", "Go"]
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == "o":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024
