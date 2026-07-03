from __future__ import annotations

import json
import uuid
import zipfile
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

ARCHIVE_URL = (
    "https://data.assemblee-nationale.fr/static/openData/repository/17/questions/"
    "questions_ecrites/Questions_ecrites.json.zip"
)
QUESTION_URL_TEMPLATE = "https://questions.assemblee-nationale.fr/q{legislature}/{legislature}-{numero}QE.htm"


def download_archive(cache_path: Path) -> Path:
    """Télécharge l'archive officielle des questions écrites (source : DEFI.md, an-questions-gouvernement-ecrites).

    Ré-utilise le fichier déjà téléchargé s'il existe, pour éviter de re-solliciter le serveur
    de l'Assemblée nationale à chaque exécution du pipeline.
    """
    if cache_path.exists():
        return cache_path
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with httpx.stream("GET", ARCHIVE_URL, follow_redirects=True, timeout=60.0) as response:
        response.raise_for_status()
        with cache_path.open("wb") as f:
            for chunk in response.iter_bytes():
                f.write(chunk)
    return cache_path


def _first(value: Any) -> dict:
    if isinstance(value, list):
        return value[0] if value else {}
    return value or {}


def iter_raw_questions(archive_path: Path) -> Iterator[dict]:
    with zipfile.ZipFile(archive_path) as archive:
        for name in archive.namelist():
            if not name.endswith(".json"):
                continue
            yield json.loads(archive.read(name))


def filter_by_rubrique(questions: Iterator[dict], rubrique: str) -> Iterator[dict]:
    for item in questions:
        question = item.get("question") or {}
        indexation = question.get("indexationAN") or {}
        if (indexation.get("rubrique") or "") == rubrique:
            yield item


def question_url(question: dict) -> str:
    identifiant = question.get("identifiant") or {}
    return QUESTION_URL_TEMPLATE.format(
        legislature=identifiant.get("legislature", ""),
        numero=identifiant.get("numero", ""),
    )


def question_text(question: dict) -> str:
    textes = _first(question.get("textesQuestion"))
    return _first(textes.get("texteQuestion")).get("texte", "") if isinstance(textes, dict) else ""


def response_text(question: dict) -> str:
    textes = question.get("textesReponse")
    if not textes:
        return ""
    textes = _first(textes)
    return _first(textes.get("texteReponse")).get("texte", "") if isinstance(textes, dict) else ""


def question_date(question: dict) -> str:
    textes = _first(question.get("textesQuestion"))
    info_jo = _first(textes.get("texteQuestion")).get("infoJO", {}) if isinstance(textes, dict) else {}
    return info_jo.get("dateJO", "")


def question_analyse(question: dict) -> str:
    indexation = question.get("indexationAN") or {}
    analyses = _first(indexation.get("analyses"))
    if isinstance(analyses, dict):
        return analyses.get("analyse", "")
    return str(indexation.get("analyses") or "")


def save_raw(item: dict, raw_dir: Path) -> Path:
    question = item.get("question") or {}
    uid = question.get("uid", "unknown")
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / f"{uid}.json"
    path.write_text(json.dumps(item, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def normalize_source(raw_item: dict) -> dict:
    question = raw_item.get("question") or {}
    uid = question.get("uid", f"unknown_{uuid.uuid4().hex[:8]}")
    text = question_text(question)
    reply = response_text(question)
    full_text = f"Question : {text}"
    if reply:
        full_text += f"\n\nRéponse du Gouvernement : {reply}"
    identifiant = question.get("identifiant") or {}
    return {
        "id": f"an_qe_{uid}",
        "type": "written_question",
        "institution": "assemblee_nationale",
        "date": question_date(question) or datetime.now(timezone.utc).date().isoformat(),
        "title": question_analyse(question) or f"Question écrite {uid}",
        "url": question_url(question),
        "official_identifier": uid,
        "text": full_text,
        "metadata": {
            "legislature": identifiant.get("legislature", ""),
            "numero": identifiant.get("numero", ""),
            "rubrique": (question.get("indexationAN") or {}).get("rubrique", ""),
            "code_cloture": (question.get("cloture") or {}).get("codeCloture", ""),
        },
    }
