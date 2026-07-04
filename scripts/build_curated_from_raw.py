#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]

SCHEMA_VERSION = "0.1.0"
MAX_VISIBLE_CATEGORY_CHILDREN = 8

ROLE_FOR_RESOURCE_TYPE = {
    "government_question": "clarification",
    "oral_question_without_debate": "clarification",
}

TRACE_TYPE_BY_RESOURCE = {
    "government_question": "oral_question",
    "oral_question_without_debate": "oral_question",
}


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Extrait les données publiques utiles depuis data/raw, produit des fichiers "
            "normalisés dans data/processed, et génère un payload AgorIA lisible par l'app."
        )
    )
    parser.add_argument("--raw-dir", type=Path, default=ROOT / "data" / "raw")
    parser.add_argument("--processed-dir", type=Path, default=ROOT / "data" / "processed")
    parser.add_argument("--curated-dir", type=Path, default=ROOT / "data" / "curated")
    parser.add_argument("--curated-status", choices=["validated", "needs_review", "automatic"], default="needs_review")
    parser.add_argument("--limit", type=int, default=0, help="Limite par famille de source. 0 = aucune limite.")
    parser.add_argument(
        "--llm-text-max-chars",
        type=int,
        default=12000,
        help="Longueur maximale des textes envoyés dans la queue LLM. 0 = texte complet, sans troncature.",
    )
    parser.add_argument("--no-curated-payload", action="store_true", help="Écrit seulement data/processed/*.json.")
    args = parser.parse_args()

    result = build_curated_from_raw(
        raw_dir=args.raw_dir,
        processed_dir=args.processed_dir,
        curated_dir=args.curated_dir,
        curated_status=args.curated_status,
        limit=args.limit or None,
        write_curated_payload=not args.no_curated_payload,
        llm_text_max_chars=args.llm_text_max_chars,
    )

    print(json.dumps(result, ensure_ascii=False, indent=2))


def build_curated_from_raw(
    *,
    raw_dir: Path,
    processed_dir: Path,
    curated_dir: Path,
    curated_status: str = "needs_review",
    limit: int | None = None,
    write_curated_payload: bool = True,
    llm_text_max_chars: int = 12000,
) -> dict[str, Any]:
    processed_dir.mkdir(parents=True, exist_ok=True)
    curated_dir.mkdir(parents=True, exist_ok=True)

    generated_at = now_iso()
    actor_index = build_actor_index(raw_dir, limit=limit)
    documents = extract_documents(raw_dir, limit=limit)
    dossiers = extract_dossiers(raw_dir, actor_index=actor_index, limit=limit)
    questions = extract_questions(raw_dir, actor_index=actor_index, limit=limit)

    subjects = merge_subjects(documents, dossiers, questions)
    taxonomy = build_taxonomy(subjects)
    llm_queue = build_llm_enrichment_queue(subjects, questions, taxonomy, text_max_chars=llm_text_max_chars)

    write_json(processed_dir / "normalized_actors.json", {"schema_version": SCHEMA_VERSION, "generated_at": generated_at, **actor_index})
    write_json(processed_dir / "normalized_documents.json", envelope(generated_at, documents))
    write_json(processed_dir / "normalized_dossiers.json", envelope(generated_at, dossiers))
    write_json(processed_dir / "normalized_questions.json", envelope(generated_at, questions))
    write_json(processed_dir / "normalized_subjects.json", envelope(generated_at, list(subjects.values())))
    write_json(processed_dir / "taxonomy.json", taxonomy)
    write_json(processed_dir / "llm_enrichment_queue.json", {"schema_version": SCHEMA_VERSION, "generated_at": generated_at, "items": llm_queue})

    curated_payload_path: str | None = None
    if write_curated_payload:
        payload = build_agoria_payload(subjects, questions, taxonomy, generated_at, curated_status)
        out_path = curated_dir / "agoria_raw_extract.json"
        write_json(out_path, payload)
        curated_payload_path = str(out_path)

    return {
        "processed_dir": str(processed_dir),
        "curated_payload": curated_payload_path,
        "counts": {
            "actors": len(actor_index["actors_by_ref"]),
            "organs": len(actor_index["organs_by_ref"]),
            "mandates": len(actor_index["mandates_by_ref"]),
            "documents": len(documents),
            "dossiers": len(dossiers),
            "questions": len(questions),
            "subjects": len(subjects),
            "llm_queue_items": len(llm_queue),
        },
    }


def envelope(generated_at: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "generated_at": generated_at, "items": items}


def build_actor_index(raw_dir: Path, *, limit: int | None = None) -> dict[str, dict[str, Any]]:
    actors_by_ref: dict[str, dict[str, Any]] = {}
    organs_by_ref: dict[str, dict[str, Any]] = {}
    mandates_by_ref: dict[str, dict[str, Any]] = {}

    for path in limited(find_named_json_files(raw_dir, "acteur"), limit):
        data = read_json(path).get("acteur")
        if not isinstance(data, dict):
            continue
        uid = ref_text(data.get("uid"))
        ident = dig(data, "etatCivil", "ident") or {}
        first_name = clean_text(ident.get("prenom"))
        last_name = clean_text(ident.get("nom"))
        name = " ".join(part for part in [first_name, last_name] if part).strip() or uid
        actors_by_ref[uid] = {
            "id": uid,
            "name": name,
            "first_name": first_name,
            "last_name": last_name,
            "civility": clean_text(ident.get("civ")),
            "profession": clean_text(dig(data, "profession", "libelleCourant")),
            "source_file": rel(path, raw_dir),
        }

    for path in limited(find_named_json_files(raw_dir, "organe"), limit):
        data = read_json(path).get("organe")
        if not isinstance(data, dict):
            continue
        uid = ref_text(data.get("uid"))
        organs_by_ref[uid] = {
            "id": uid,
            "label": clean_text(data.get("libelle")) or uid,
            "short_label": clean_text(data.get("libelleAbrege") or data.get("libelleAbrev")),
            "type": clean_text(data.get("codeType")),
            "parent_ref": ref_text(data.get("organeParent")),
            "legislature": clean_text(data.get("legislature")),
            "source_file": rel(path, raw_dir),
        }

    for path in limited(find_named_json_files(raw_dir, "mandat"), limit):
        data = read_json(path).get("mandat")
        if not isinstance(data, dict):
            continue
        uid = ref_text(data.get("uid"))
        org_refs = [ref_text(item) for item in as_list(dig(data, "organes", "organeRef")) if ref_text(item)]
        mandates_by_ref[uid] = {
            "id": uid,
            "actor_ref": ref_text(data.get("acteurRef")),
            "legislature": clean_text(data.get("legislature")),
            "type_organe": clean_text(data.get("typeOrgane")),
            "date_start": date_only(data.get("dateDebut")),
            "date_end": date_only(data.get("dateFin")),
            "quality": clean_text(dig(data, "infosQualite", "libQualite") or dig(data, "infosQualite", "codeQualite")),
            "organ_refs": org_refs,
            "source_file": rel(path, raw_dir),
        }

    return {"actors_by_ref": actors_by_ref, "organs_by_ref": organs_by_ref, "mandates_by_ref": mandates_by_ref}


def extract_documents(raw_dir: Path, *, limit: int | None = None) -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    for path in limited(find_named_json_files(raw_dir, "document"), limit):
        raw = read_json(path).get("document")
        if not isinstance(raw, dict):
            continue
        dossier_ref = clean_text(raw.get("dossierRef"))
        if not dossier_ref:
            continue
        chrono = dig(raw, "cycleDeVie", "chrono") or {}
        classification = raw.get("classification") or {}
        title = title_from_document(raw)
        documents.append(
            {
                "id": clean_text(raw.get("uid")),
                "dossier_ref": dossier_ref,
                "legislature": clean_text(raw.get("legislature")),
                "title": title,
                "title_full": clean_text(dig(raw, "titres", "titrePrincipal")),
                "document_type": clean_text(raw.get("denominationStructurelle")),
                "provenance": clean_text(raw.get("provenance")),
                "date_depot": date_only(chrono.get("dateDepot")),
                "date_publication": date_only(chrono.get("datePublication") or chrono.get("datePublicationWeb")),
                "notice_number": clean_text(dig(raw, "notice", "numNotice")),
                "classification": {
                    "class": clean_text(dig(classification, "famille", "classe", "libelle")),
                    "kind": clean_text(dig(classification, "type", "libelle")),
                    "subkind": clean_text(dig(classification, "sousType", "libelle") or dig(classification, "famille", "espece", "libelle")),
                },
                "author_refs": actor_refs_from_value(dig(raw, "auteurs", "auteur")),
                "source_file": rel(path, raw_dir),
            }
        )
    return documents


def extract_dossiers(raw_dir: Path, *, actor_index: dict[str, Any], limit: int | None = None) -> list[dict[str, Any]]:
    dossiers: list[dict[str, Any]] = []
    for path in limited(find_named_json_files(raw_dir, "dossierParlementaire"), limit):
        raw = read_json(path).get("dossierParlementaire")
        if not isinstance(raw, dict):
            continue
        dossier_id = clean_text(raw.get("uid"))
        if not dossier_id:
            continue
        timeline = [event for event in walk_legislative_events(raw) if is_useful_timeline_event(event)]
        timeline.sort(key=lambda item: item.get("date") or "")
        dossiers.append(
            {
                "id": dossier_id,
                "legislature": clean_text(raw.get("legislature")),
                "title": clean_text(dig(raw, "titreDossier", "titre")) or dossier_id,
                "source_url": clean_text(dig(raw, "titreDossier", "senatChemin")),
                "procedure": clean_text(dig(raw, "procedureParlementaire", "libelle")),
                "initiators": extract_initiators(raw, actor_index),
                "timeline_events": timeline,
                "source_file": rel(path, raw_dir),
            }
        )
    return dossiers


def extract_questions(raw_dir: Path, *, actor_index: dict[str, Any], limit: int | None = None) -> list[dict[str, Any]]:
    questions: list[dict[str, Any]] = []
    source_specs = [
        ("Questions_gouvernement.json", "government_question", "Question au Gouvernement"),
        ("Questions_orales_sans_debat.json", "oral_question_without_debate", "Question orale sans débat"),
    ]
    for source_root, resource_type, resource_label in source_specs:
        for path in limited(find_json_files_under_source(raw_dir, source_root), limit):
            raw = read_json(path).get("question")
            if not isinstance(raw, dict):
                continue
            question_id = clean_text(raw.get("uid"))
            title = question_title(raw) or question_id
            author_ref = clean_text(dig(raw, "auteur", "identite", "acteurRef"))
            group_ref = clean_text(dig(raw, "auteur", "groupe", "organeRef"))
            ministry_ref = clean_text(dig(raw, "minInt", "organeRef")) or clean_text(dig(raw, "minAttribs", "minAttrib", "denomination", "organeRef"))
            question_text = text_from_question_blocks(dig(raw, "textesQuestion"))
            answer_text = text_from_question_blocks(dig(raw, "textesReponse"))
            combined_text = clean_html("\n\n".join(part for part in [question_text, answer_text] if part))
            questions.append(
                {
                    "id": question_id,
                    "resource_type": resource_type,
                    "resource_label": resource_label,
                    "legislature": clean_text(dig(raw, "identifiant", "legislature")),
                    "number": clean_text(dig(raw, "identifiant", "numero")),
                    "title": title,
                    "rubrique": clean_text(dig(raw, "indexationAN", "rubrique")),
                    "analysis": title,
                    "date": date_only(
                        dig(raw, "textesReponse", "texteReponse", "infoJO", "dateJO")
                        or dig(raw, "textesQuestion", "texteQuestion", "infoJO", "dateJO")
                        or dig(raw, "cloture", "dateCloture")
                    ),
                    "closure_label": clean_text(dig(raw, "cloture", "libelleCloture")),
                    "source_url": clean_text(
                        dig(raw, "textesReponse", "texteReponse", "infoJO", "urlLegifrance")
                        or dig(raw, "textesQuestion", "texteQuestion", "infoJO", "urlLegifrance")
                    ),
                    "author": resolve_actor(author_ref, actor_index),
                    "author_ref": author_ref,
                    "group_ref": group_ref,
                    "group_label": clean_text(dig(raw, "auteur", "groupe", "developpe")) or resolve_org(group_ref, actor_index).get("label", ""),
                    "group_short_label": clean_text(dig(raw, "auteur", "groupe", "abrege")) or resolve_org(group_ref, actor_index).get("short_label", ""),
                    "target_ministry_ref": ministry_ref,
                    "target_ministry": clean_text(dig(raw, "minInt", "developpe")) or resolve_org(ministry_ref, actor_index).get("label", ""),
                    "question_text": question_text,
                    "answer_text": answer_text,
                    "text_excerpt": excerpt(combined_text, 900),
                    "question_summary": deterministic_question_summary(title, raw),
                    "answer_summary": deterministic_answer_summary(raw),
                    "source_file": rel(path, raw_dir),
                }
            )
    return questions


def merge_subjects(documents: list[dict[str, Any]], dossiers: list[dict[str, Any]], questions: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    subjects: dict[str, dict[str, Any]] = {}

    for document in documents:
        subject = subjects.setdefault(
            document["dossier_ref"],
            base_subject(
                subject_id=document["dossier_ref"],
                title=document["title"],
                source_family="legislative_document",
                domain=document.get("classification", {}).get("kind") or document.get("document_type") or "Travaux parlementaires",
                subtheme=document.get("classification", {}).get("subkind") or document.get("document_type") or "Documents législatifs",
            ),
        )
        subject["summary"] = subject.get("summary") or deterministic_document_summary(document)
        subject["context_update"] = join_non_empty(
            [
                subject.get("context_update"),
                document.get("document_type"),
                document.get("provenance"),
                document.get("classification", {}).get("subkind"),
            ],
            separator=" · ",
        )
        subject["legal_texts"].append(
            {
                "date": document.get("date_depot") or document.get("date_publication") or "",
                "type": document.get("document_type") or "Document parlementaire",
                "title": document.get("title"),
                "summary": deterministic_document_summary(document),
                "url": "#",
                "source_id": document.get("id"),
            }
        )
        if document.get("date_depot"):
            subject["timeline_events"].append(
                {
                    "date": document["date_depot"],
                    "type": "document",
                    "kind": "Dépôt de texte",
                    "title": document.get("title") or "Dépôt de texte",
                    "summary": deterministic_document_summary(document),
                    "url": "#",
                    "source_id": document.get("id"),
                }
            )

    for dossier in dossiers:
        subject = subjects.setdefault(
            dossier["id"],
            base_subject(
                subject_id=dossier["id"],
                title=dossier.get("title") or dossier["id"],
                source_family="dossier_parlementaire",
                domain="Travaux parlementaires",
                subtheme=dossier.get("procedure") or "Dossiers parlementaires",
            ),
        )
        if not subject.get("title") or subject["title"] == dossier["id"]:
            subject["title"] = dossier.get("title") or dossier["id"]
        subject["summary"] = subject.get("summary") or f"Dossier parlementaire : {dossier.get('title') or dossier['id']}."
        subject["context_update"] = join_non_empty([subject.get("context_update"), dossier.get("procedure")], separator=" · ")
        subject["timeline_events"].extend(dossier.get("timeline_events", []))
        for initiator in dossier.get("initiators", []):
            add_actor(subject, initiator)

    for question in questions:
        subject_id = question_subject_id(question)
        subject = subjects.setdefault(
            subject_id,
            base_subject(
                subject_id=subject_id,
                title=question.get("title") or question["id"],
                source_family=question["resource_type"],
                domain=label_from_rubrique(question.get("rubrique")) or "Questions parlementaires",
                subtheme=question.get("rubrique") or "Questions parlementaires",
            ),
        )
        subject["summary"] = subject.get("summary") or question.get("question_summary") or f"Question parlementaire : {question.get('title')}"
        subject["context_update"] = join_non_empty(
            [subject.get("context_update"), question.get("resource_label"), question.get("target_ministry")],
            separator=" · ",
        )
        add_actor(subject, actor_for_question_author(question))
        if question.get("target_ministry"):
            add_actor(subject, actor_for_question_target(question))
        subject["timeline_events"].append(
            {
                "date": question.get("date") or "",
                "type": question.get("resource_type"),
                "kind": question.get("resource_label"),
                "title": question.get("title"),
                "summary": question.get("answer_summary") or question.get("question_summary"),
                "url": question.get("source_url") or "#",
                "source_id": question.get("id"),
                "author_ref": question.get("author_ref"),
                "target": question.get("target_ministry"),
            }
        )
        subject["argument_clusters"].append(cluster_from_question(question))

    for subject in subjects.values():
        subject["timeline_events"] = unique_events(subject["timeline_events"])
        subject["legal_texts"] = unique_events(subject["legal_texts"], keys=("source_id", "title", "date"))
        subject["actors"] = unique_by(subject["actors"], "id")
        subject["argument_clusters"] = unique_by(subject["argument_clusters"], "id")
        subject["timeline_events"].sort(key=lambda item: item.get("date") or "", reverse=True)

    return subjects


def build_taxonomy(subjects: dict[str, dict[str, Any]]) -> dict[str, Any]:
    nodes: dict[str, dict[str, Any]] = {}
    for subject in subjects.values():
        domain_label = subject.get("taxonomy", {}).get("domain_label") or "Sources parlementaires"
        subtheme_label = subject.get("taxonomy", {}).get("subtheme_label") or "Sujets importés"
        domain_id = slugify(domain_label) or "sources-parlementaires"
        subtheme_id = f"{domain_id}__{slugify(subtheme_label) or 'sujets-importes'}"
        nodes.setdefault(
            domain_id,
            {
                "id": domain_id,
                "label": domain_label,
                "level": 1,
                "parent_id": None,
                "description": "Grand domaine issu des champs officiels ou d'une classification à consolider.",
                "aliases": [],
            },
        )
        nodes.setdefault(
            subtheme_id,
            {
                "id": subtheme_id,
                "label": subtheme_label,
                "level": 2,
                "parent_id": domain_id,
                "description": "Catégorie intermédiaire issue des données brutes. À réévaluer lors de la consolidation taxonomique.",
                "aliases": [],
            },
        )
        subject["taxonomy"] = {
            **subject.get("taxonomy", {}),
            "domain_id": domain_id,
            "domain_label": domain_label,
            "subtheme_id": subtheme_id,
            "subtheme_label": subtheme_label,
            "taxonomy_version": "raw_extraction_v1",
            "needs_llm_review": True,
        }

    children_count: defaultdict[str, int] = defaultdict(int)
    for node in nodes.values():
        if node.get("parent_id"):
            children_count[node["parent_id"]] += 1
    for node in nodes.values():
        node["children_count"] = children_count[node["id"]]
        node["needs_consolidation"] = node["children_count"] > MAX_VISIBLE_CATEGORY_CHILDREN

    return {
        "schema_version": SCHEMA_VERSION,
        "version": "raw_extraction_v1",
        "generated_at": now_iso(),
        "nodes": sorted(nodes.values(), key=lambda item: (item["level"], item["label"])),
        "constraints": {
            "max_visible_children": MAX_VISIBLE_CATEGORY_CHILDREN,
            "preferred_depth": 3,
            "max_depth": 4,
        },
        "notes": [
            "Taxonomie déterministe provisoire : les catégories viennent des champs officiels.",
            "Les résumés fins et les catégories intermédiaires doivent être produits par enrichissement LLM ciblé puis relus.",
        ],
    }


def build_llm_enrichment_queue(
    subjects: dict[str, dict[str, Any]],
    questions: list[dict[str, Any]],
    taxonomy: dict[str, Any],
    *,
    text_max_chars: int = 12000,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    taxonomy_context = [
        {"id": node["id"], "label": node["label"], "level": node["level"], "parent_id": node.get("parent_id")}
        for node in taxonomy.get("nodes", [])
    ]
    for subject in subjects.values():
        items.append(
            {
                "id": f"classify:{subject['id']}",
                "task": "classify_subject",
                "source_id": subject["id"],
                "input": {
                    "title": subject.get("title"),
                    "summary": subject.get("summary"),
                    "context": subject.get("context_update"),
                    "current_path": [
                        subject.get("taxonomy", {}).get("domain_label"),
                        subject.get("taxonomy", {}).get("subtheme_label"),
                    ],
                    "taxonomy_context": taxonomy_context,
                    "constraints": taxonomy.get("constraints", {}),
                },
                "expected_output": {
                    "canonical_path": ["N1", "N2", "N3 optionnel"],
                    "tags": [],
                    "new_category_proposal": {"needed": False},
                    "confidence": 0.0,
                },
            }
        )
    for question in questions:
        items.append(
            {
                "id": f"summarize_question:{question['id']}",
                "task": "summarize_question_and_answer",
                "source_id": question["id"],
                "input": {
                    "title": question.get("title"),
                    "rubrique": question.get("rubrique"),
                    "author": question.get("author", {}).get("name"),
                    "group": question.get("group_label"),
                    "target_ministry": question.get("target_ministry"),
                    "question_text": llm_text(question.get("question_text") or question.get("text_excerpt"), text_max_chars),
                    "answer_text": llm_text(question.get("answer_text") or question.get("text_excerpt"), text_max_chars),
                    "transcript_text": llm_text(question.get("answer_text") or question.get("question_text") or question.get("text_excerpt"), text_max_chars),
                },
                "expected_output": {
                    "question_summary": "",
                    "answer_summary": "",
                    "issues": [],
                    "announced_measures": [],
                    "quotes": [],
                },
            }
        )
    return items


def build_agoria_payload(
    subjects: dict[str, dict[str, Any]],
    questions: list[dict[str, Any]],
    taxonomy: dict[str, Any],
    generated_at: str,
    curated_status: str,
) -> dict[str, Any]:
    question_by_subject = {question_subject_id(question): question for question in questions}
    subject_updates: list[dict[str, Any]] = []
    taxonomy_links: list[dict[str, Any]] = []
    extracted_traces: list[dict[str, Any]] = []

    for subject in subjects.values():
        taxonomy_info = subject.get("taxonomy", {})
        taxonomy_links.append(
            {
                "domain_id": taxonomy_info.get("domain_id", "sources-parlementaires"),
                "domain_label": taxonomy_info.get("domain_label", "Sources parlementaires"),
                "subtheme_id": taxonomy_info.get("subtheme_id", "sujets-importes"),
                "subtheme_label": taxonomy_info.get("subtheme_label", "Sujets importés"),
                "subject_id": subject["id"],
                "subject_title": subject.get("title", subject["id"]),
                "link_strength": "medium",
                "rationale": "Rattachement déterministe depuis les champs officiels ; à consolider par classification LLM.",
                "confidence": 0.55,
                "taxonomy_version": taxonomy.get("version"),
            }
        )
        subject_updates.append(
            {
                "subject_id": subject["id"],
                "subject_title": subject.get("title", subject["id"]),
                "summary": subject.get("summary", "Sujet extrait depuis les données publiques."),
                "context_update": subject.get("context_update", "Contexte à consolider."),
                "timeline_events": subject.get("timeline_events", []),
                "actors": subject.get("actors", []),
                "argument_clusters": subject.get("argument_clusters", []),
                "legal_texts": subject.get("legal_texts", []),
                "classification": taxonomy_info,
            }
        )
        question = question_by_subject.get(subject["id"])
        if question:
            extracted_traces.append(trace_from_question(question, subject["id"]))

    return {
        "schema_version": SCHEMA_VERSION,
        "processing": {
            "run_id": f"raw_extract_{generated_at.replace(':', '').replace('-', '').replace('+', '_')}",
            "processed_at": generated_at,
            "model": "deterministic_script_only",
            "prompt_version": "none_yet_llm_queue_generated",
            "status": curated_status,
            "global_confidence": 0.55,
            "notes": [
                "Payload construit sans appel LLM.",
                "Les résumés, classifications fines et citations doivent être relus/enrichis via data/processed/llm_enrichment_queue.json.",
            ],
        },
        "raw_source": {
            "id": "raw_extract_aggregate",
            "type": "other",
            "institution": "assemblee_nationale",
            "date": generated_at[:10],
            "title": "Extraction déterministe depuis data/raw",
            "url": "#",
            "official_identifier": "data/raw",
            "metadata": {"summary": "Extraction brute structurée des données parlementaires."},
        },
        "extracted_traces": extracted_traces,
        "taxonomy_links": taxonomy_links,
        "subject_updates": subject_updates,
    }


def base_subject(*, subject_id: str, title: str, source_family: str, domain: str, subtheme: str) -> dict[str, Any]:
    return {
        "id": subject_id,
        "title": title,
        "source_family": source_family,
        "summary": "",
        "context_update": "",
        "legal_texts": [],
        "timeline_events": [],
        "actors": [],
        "argument_clusters": [],
        "taxonomy": {
            "domain_label": normalize_category_label(domain) or "Sources parlementaires",
            "subtheme_label": normalize_category_label(subtheme) or "Sujets importés",
        },
    }


def walk_legislative_events(dossier: dict[str, Any]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []

    def visit(acte: dict[str, Any], parents: list[str]) -> None:
        if not isinstance(acte, dict):
            return
        label = clean_text(dig(acte, "libelleActe", "libelleCourt") or dig(acte, "libelleActe", "nomCanonique"))
        code = clean_text(acte.get("codeActe"))
        current_path = [*parents, label or code]
        event = {
            "id": clean_text(acte.get("uid")),
            "date": date_only(acte.get("dateActe")),
            "type": clean_text(acte.get("@xsi:type")) or "acte_legislatif",
            "kind": label or code or "Acte législatif",
            "title": label or code or "Acte législatif",
            "summary": event_summary(acte, current_path),
            "url": "#",
            "code_acte": code,
            "institution_ref": ref_text(acte.get("organeRef")),
            "text_ref": clean_text(acte.get("texteAssocie")),
            "adopted_text_ref": clean_text(dig(acte, "textesAssocies", "texteAssocie", "refTexteAssocie") or acte.get("texteAdopte")),
            "reunion_ref": clean_text(acte.get("reunionRef")),
            "agenda_ref": clean_text(acte.get("odjRef")),
            "vote_refs": [ref_text(item) for item in as_list(acte.get("voteRefs")) if ref_text(item)],
            "status": clean_text(dig(acte, "statutConclusion", "libelle")),
            "rapporteur_refs": actor_refs_from_value(dig(acte, "rapporteurs", "rapporteur")),
            "path": [item for item in current_path if item],
        }
        events.append({key: value for key, value in event.items() if value not in (None, "", [], {})})
        children = dig(acte, "actesLegislatifs", "acteLegislatif")
        for child in as_list(children):
            visit(child, current_path)

    for root in as_list(dig(dossier, "actesLegislatifs", "acteLegislatif")):
        visit(root, [])
    return events


def is_useful_timeline_event(event: dict[str, Any]) -> bool:
    return any(event.get(key) for key in ["date", "text_ref", "adopted_text_ref", "reunion_ref", "vote_refs", "status", "rapporteur_refs"])


def extract_initiators(dossier: dict[str, Any], actor_index: dict[str, Any]) -> list[dict[str, Any]]:
    initiators: list[dict[str, Any]] = []
    for item in as_list(dig(dossier, "initiateur", "acteurs", "acteur")):
        actor_ref = ref_text(item.get("acteurRef") if isinstance(item, dict) else item)
        if actor_ref:
            initiators.append(resolve_actor(actor_ref, actor_index))
    for item in as_list(dig(dossier, "initiateur", "organes", "organe")):
        org_ref = ref_text(dig(item, "organeRef", "uid") if isinstance(item, dict) else item)
        if org_ref:
            org = resolve_org(org_ref, actor_index)
            initiators.append({"id": org_ref, "name": org.get("label", org_ref), "role": "Organe initiateur", "party": org.get("short_label", "")})
    return initiators


def actor_refs_from_value(value: Any) -> list[str]:
    refs: list[str] = []
    for item in as_list(value):
        if not isinstance(item, dict):
            ref = ref_text(item)
        else:
            ref = ref_text(dig(item, "acteur", "acteurRef") or item.get("acteurRef"))
        if ref and ref not in refs:
            refs.append(ref)
    return refs


def text_from_question_blocks(block: Any) -> str:
    texts: list[str] = []
    if not isinstance(block, dict):
        return ""
    for key in ["texteQuestion", "texteReponse"]:
        for item in as_list(block.get(key)):
            if isinstance(item, dict) and item.get("texte"):
                texts.append(clean_html(item["texte"]))
    return "\n\n".join(texts)


def trace_from_question(question: dict[str, Any], subject_id: str) -> dict[str, Any]:
    role = ROLE_FOR_RESOURCE_TYPE.get(question.get("resource_type"), "clarification")
    return {
        "id": question["id"],
        "source_id": question["id"],
        "summary": question.get("question_summary") or question.get("title") or question["id"],
        "argument_role": role,
        "position": "neutral",
        "public_policy_domains": [question.get("rubrique") or "questions_parlementaires"],
        "affected_publics": [],
        "issues": [item for item in [question.get("rubrique"), question.get("analysis")] if item],
        "evidence": [
            {
                "quote": excerpt(question.get("text_excerpt"), 350),
                "source_url": question.get("source_url") or "#",
                "source_file": question.get("source_file"),
            }
        ],
        "confidence": 0.55,
        "validation_status": "needs_review",
        "metadata": {
            "subject_id": subject_id,
            "resource_type": question.get("resource_type"),
            "author_ref": question.get("author_ref"),
            "target_ministry": question.get("target_ministry"),
            "answer_summary": question.get("answer_summary"),
        },
    }


def cluster_from_question(question: dict[str, Any]) -> dict[str, Any]:
    actor_id = question.get("author_ref") or f"author-{question['id']}"
    return {
        "id": f"question-{slugify(question['id'])}",
        "axis": "interpellation-gouvernementale",
        "position": "neutral",
        "label": question.get("title") or "Question parlementaire",
        "summary": question.get("question_summary") or "Question parlementaire à résumer.",
        "actors": [
            {
                "actor_id": actor_id,
                "quote": excerpt(question.get("text_excerpt"), 280),
                "quote_source": join_non_empty([question.get("resource_label"), question.get("date")], separator=" · "),
                "quote_url": question.get("source_url") or "#",
                "stance_summary": question.get("question_summary") or "Interpellation du Gouvernement.",
            }
        ],
        "response": {
            "target": question.get("target_ministry"),
            "summary": question.get("answer_summary"),
        },
    }


def actor_for_question_author(question: dict[str, Any]) -> dict[str, Any]:
    actor = question.get("author") or {}
    return {
        "id": question.get("author_ref") or f"author-{question['id']}",
        "name": actor.get("name") or question.get("author_ref") or "Auteur de la question",
        "type": "deputy",
        "role": "Auteur de la question",
        "party": question.get("group_short_label") or question.get("group_label") or "Non renseigné",
        "photo_url": "",
        "stance_summary": question.get("question_summary") or "Question parlementaire.",
    }


def actor_for_question_target(question: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": question.get("target_ministry_ref") or f"target-{question['id']}",
        "name": question.get("target_ministry") or "Gouvernement",
        "type": "institution",
        "role": "Réponse gouvernementale",
        "party": "Gouvernement",
        "photo_url": "",
        "stance_summary": question.get("answer_summary") or "Réponse à produire par enrichissement.",
    }


def add_actor(subject: dict[str, Any], actor: dict[str, Any]) -> None:
    if actor and actor.get("id"):
        subject["actors"].append(actor)


def resolve_actor(actor_ref: str, actor_index: dict[str, Any]) -> dict[str, Any]:
    actor = actor_index.get("actors_by_ref", {}).get(actor_ref, {})
    return {
        "id": actor_ref,
        "name": actor.get("name") or actor_ref or "Acteur public",
        "type": "public_actor",
        "role": actor.get("profession") or "Acteur public",
        "party": "",
        "photo_url": "",
    }


def resolve_org(org_ref: str, actor_index: dict[str, Any]) -> dict[str, Any]:
    return actor_index.get("organs_by_ref", {}).get(org_ref, {})


def question_subject_id(question: dict[str, Any]) -> str:
    return f"question-{slugify(question.get('id') or question.get('title') or 'sans-id')}"


def question_title(raw: dict[str, Any]) -> str:
    analysis = dig(raw, "indexationAN", "analyses", "analyse")
    if isinstance(analysis, list):
        analysis = analysis[0] if analysis else ""
    return clean_text(analysis or dig(raw, "indexationAN", "teteAnalyse") or raw.get("uid"))


def title_from_document(raw: dict[str, Any]) -> str:
    return clean_text(dig(raw, "titres", "titrePrincipalCourt") or dig(raw, "titres", "titrePrincipal") or dig(raw, "notice", "formule") or raw.get("uid"))


def deterministic_document_summary(document: dict[str, Any]) -> str:
    parts = [document.get("document_type"), document.get("classification", {}).get("subkind"), document.get("title_full") or document.get("title")]
    text = join_non_empty(parts, separator=" — ")
    return excerpt(text, 500) or "Document législatif extrait depuis les données brutes."


def deterministic_question_summary(title: str, raw: dict[str, Any]) -> str:
    rubrique = clean_text(dig(raw, "indexationAN", "rubrique"))
    return join_non_empty(["Question parlementaire", title, f"rubrique {rubrique}" if rubrique else ""], separator=" — ")


def deterministic_answer_summary(raw: dict[str, Any]) -> str:
    closure = clean_text(dig(raw, "cloture", "libelleCloture"))
    ministry = clean_text(dig(raw, "minInt", "developpe"))
    date = date_only(dig(raw, "cloture", "dateCloture") or dig(raw, "textesReponse", "texteReponse", "infoJO", "dateJO"))
    return join_non_empty(["Réponse à résumer par enrichissement LLM", ministry, closure, date], separator=" · ")


def event_summary(acte: dict[str, Any], path: list[str]) -> str:
    pieces = [clean_text(dig(acte, "libelleActe", "libelleCourt") or dig(acte, "libelleActe", "nomCanonique"))]
    status = clean_text(dig(acte, "statutConclusion", "libelle"))
    text_ref = clean_text(acte.get("texteAssocie") or dig(acte, "textesAssocies", "texteAssocie", "refTexteAssocie"))
    if status:
        pieces.append(status)
    if text_ref:
        pieces.append(f"texte {text_ref}")
    if path:
        pieces.append(" > ".join(path[-3:]))
    return join_non_empty(pieces, separator=" · ")


def normalize_category_label(value: str) -> str:
    value = clean_text(value)
    if not value:
        return ""
    aliases = {
        "outre-mer": "Outre-mer",
        "justice": "Justice",
        "santé": "Santé",
        "sante": "Santé",
        "gendarmerie": "Sécurité intérieure",
    }
    return aliases.get(value.lower(), value[:1].upper() + value[1:])


def label_from_rubrique(value: str) -> str:
    return normalize_category_label(value) or "Questions parlementaires"


def unique_events(events: list[dict[str, Any]], keys: tuple[str, ...] = ("id", "date", "title")) -> list[dict[str, Any]]:
    seen: set[tuple[Any, ...]] = set()
    output: list[dict[str, Any]] = []
    for event in events:
        key = tuple(event.get(item) for item in keys)
        if key in seen:
            continue
        seen.add(key)
        output.append(event)
    return output


def unique_by(items: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    seen: set[str] = set()
    output: list[dict[str, Any]] = []
    for item in items:
        value = str(item.get(key, ""))
        if not value or value in seen:
            continue
        seen.add(value)
        output.append(item)
    return output


def find_named_json_files(raw_dir: Path, directory_name: str) -> list[Path]:
    matches = []
    for directory in raw_dir.rglob(directory_name):
        if directory.is_dir():
            matches.extend(sorted(directory.glob("*.json")))
    return sorted(matches)


def find_json_files_under_source(raw_dir: Path, source_name: str) -> list[Path]:
    roots = [path for path in raw_dir.rglob(source_name) if path.is_dir()]
    files: list[Path] = []
    for root in roots:
        json_dir = root / "json"
        if json_dir.is_dir():
            files.extend(sorted(json_dir.rglob("*.json")))
        else:
            files.extend(sorted(root.rglob("*.json")))
    return sorted(files)


def limited(paths: Iterable[Path], limit: int | None) -> list[Path]:
    ordered = sorted(paths)
    if limit is None:
        return ordered
    return ordered[:limit]


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        data = json.load(stream)
    return data if isinstance(data, dict) else {}


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def dig(value: Any, *keys: str) -> Any:
    current = value
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def ref_text(value: Any) -> str:
    if isinstance(value, dict):
        return clean_text(value.get("#text") or value.get("uid") or value.get("ref") or value.get("id"))
    return clean_text(value)


def clean_html(value: Any) -> str:
    text = clean_text(value)
    if not text:
        return ""
    text = re.sub(r"<\s*br\s*/?\s*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</\s*p\s*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text).replace("\xa0", " ")
    return re.sub(r"[ \t\r\f\v]+", " ", re.sub(r"\n{3,}", "\n\n", text)).strip()


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return str(value)
    if not isinstance(value, str):
        return ""
    return html.unescape(value).replace("\xa0", " ").strip()


def date_only(value: Any) -> str:
    text = clean_text(value)
    if not text:
        return ""
    match = re.match(r"(\d{4}-\d{2}-\d{2})", text)
    return match.group(1) if match else text



def llm_text(value: Any, max_chars: int = 12000) -> str:
    """Nettoie un texte destiné à la queue LLM.

    max_chars=0 désactive la troncature. La normalisation des espaces est conservée
    pour éviter des lots conversationnels inutilement volumineux.
    """
    text = re.sub(r"\s+", " ", clean_text(value)).strip()
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"

def excerpt(value: Any, max_chars: int = 500) -> str:
    text = re.sub(r"\s+", " ", clean_text(value)).strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def join_non_empty(values: Iterable[Any], *, separator: str = " ") -> str:
    return separator.join(clean_text(value) for value in values if clean_text(value))


def slugify(value: Any) -> str:
    text = clean_text(value).lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:90]


def rel(path: Path, base: Path) -> str:
    try:
        return str(path.relative_to(base))
    except ValueError:
        return str(path)


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


if __name__ == "__main__":
    main()
