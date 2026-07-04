from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Any

from app.core.models import Measure, PublicTrace, SourceRef
from app.core.settings import BASE_DIR


ROLE_MAP = {
    "support": "soutien",
    "opposition": "opposition",
    "nuance": "nuance",
    "clarification": "clarification",
    "alternative": "alternative",
    "implementation_alert": "alerte_application",
    "evaluation_request": "clarification",
}

TRACE_TYPE_MAP = {
    "law_text": "texte_legislatif",
    "bill": "texte_legislatif",
    "amendment": "amendement",
    "committee_report": "rapport",
    "public_session_debate": "debat_seance",
    "written_question": "question_ecrite",
    "oral_question": "question_orale",
    "government_answer": "reponse_gouvernementale",
    "public_petition": "petition_publique",
    "public_consultation": "petition_publique",
    "other": "texte_legislatif",
}

DEFAULT_CATEGORY_BY_ROLE = {
    "soutien": "evaluation",
    "opposition": "libertes_publiques",
    "nuance": "clarte_juridique",
    "clarification": "clarte_juridique",
    "alternative": "faisabilite",
    "alerte_application": "faisabilite",
}


class ProcessedRepository:
    """Lit les données publiques prétraitées dans data/curated et data/processed.

    Ce dépôt ne fait pas d'appel IA en temps réel. Il consomme uniquement le contrat
    JSON AgorIA produit par le pipeline d'ingestion / extraction / validation.
    """

    def __init__(
        self,
        curated_dir: Path | None = None,
        processed_dir: Path | None = None,
        include_automatic: bool = False,
    ) -> None:
        self.curated_dir = curated_dir or BASE_DIR / "data" / "curated"
        self.processed_dir = processed_dir or BASE_DIR / "data" / "processed"
        self.include_automatic = include_automatic

    def has_payloads(self) -> bool:
        return bool(self._payload_paths())

    def list_measures(self) -> list[Measure]:
        by_id: dict[str, dict[str, Any]] = {}
        for payload in self._payloads():
            raw = payload["raw_source"]
            source = SourceRef(
                label=raw.get("title", "Source officielle"),
                type=TRACE_TYPE_MAP.get(raw.get("type", "other"), "texte_legislatif"),
                url=raw.get("url", "#"),
            )
            for subject in payload.get("subject_updates", []):
                subject_id = subject["subject_id"]
                entry = by_id.setdefault(
                    subject_id,
                    {
                        "id": subject_id,
                        "title": subject.get("subject_title", subject_id.replace("-", " ").title()),
                        "law_title": raw.get("title", "Source officielle"),
                        "article": raw.get("metadata", {}).get("article", raw.get("official_identifier", "")),
                        "status": self._status_label(payload),
                        "summary": subject.get("summary", ""),
                        "changes": [],
                        "audiences": set(),
                        "obligations": set(),
                        "deadlines": set(),
                        "expected_effects": [],
                        "sources": [],
                    },
                )
                if source not in entry["sources"]:
                    entry["sources"].append(source)
                for trace in payload.get("extracted_traces", []):
                    entry["changes"].append(trace.get("summary", ""))
                    entry["expected_effects"].append(trace.get("summary", ""))
                    entry["audiences"].update(trace.get("affected_publics", []))

        measures: list[Measure] = []
        for item in by_id.values():
            measures.append(
                Measure(
                    id=item["id"],
                    title=item["title"],
                    law_title=item["law_title"],
                    article=item["article"],
                    status=item["status"],
                    summary=item["summary"],
                    changes=self._unique_or_placeholder(item["changes"], "À consolider depuis les sources officielles."),
                    audiences=self._unique_or_placeholder(sorted(item["audiences"]), "Publics concernés à préciser."),
                    obligations=self._unique_or_placeholder(sorted(item["obligations"]), "Obligations à préciser depuis le texte."),
                    deadlines=self._unique_or_placeholder(sorted(item["deadlines"]), "Échéances à préciser depuis le texte."),
                    expected_effects=self._unique_or_placeholder(item["expected_effects"], "Effets attendus à préciser."),
                    sources=item["sources"],
                )
            )
        return sorted(measures, key=lambda m: m.title)

    def get_measure(self, measure_id: str) -> Measure | None:
        return next((m for m in self.list_measures() if m.id == measure_id), None)

    def list_traces(self, measure_id: str | None = None) -> list[PublicTrace]:
        traces: list[PublicTrace] = []
        for payload in self._payloads():
            raw = payload["raw_source"]
            subject_ids = [link.get("subject_id") for link in payload.get("taxonomy_links", [])]
            if not subject_ids:
                subject_ids = [s.get("subject_id") for s in payload.get("subject_updates", [])]
            for trace in payload.get("extracted_traces", []):
                evidence = (trace.get("evidence") or [{}])[0]
                role = ROLE_MAP.get(trace.get("argument_role"), "clarification")
                category = self._category_from_trace(trace, role)
                for subject_id in subject_ids:
                    if measure_id is not None and subject_id != measure_id:
                        continue
                    traces.append(
                        PublicTrace(
                            id=f"{subject_id}:{trace['id']}",
                            measure_id=subject_id,
                            trace_type=TRACE_TYPE_MAP.get(raw.get("type", "other"), "texte_legislatif"),
                            institution=raw.get("institution", "institution publique"),
                            date=raw.get("date", ""),
                            speaker=raw.get("metadata", {}).get("speaker", raw.get("institution", "Source publique")),
                            title=raw.get("title", "Source officielle"),
                            excerpt=evidence.get("quote") or trace.get("summary", ""),
                            source_url=evidence.get("source_url") or raw.get("url", "#"),
                            argument_role=role,
                            category=category,
                            problem_type=self._problem_type(role),
                            confidence=self._confidence_label(trace.get("confidence", 0)),
                        )
                    )
        return traces

    def list_debate_subjects(self, measure_id: str) -> list[dict]:
        return [item for item in self.list_all_debate_subjects() if item.get("measure_id") == measure_id]

    def list_all_debate_subjects(self) -> list[dict]:
        grouped: dict[str, dict[str, Any]] = {}
        for payload in self._payloads():
            for link in payload.get("taxonomy_links", []):
                domain_id = link.get("domain_id", "sources-officielles")
                domain_label = link.get("domain_label", "Sources officielles")
                subtheme_id = link.get("subtheme_id", "sujets-importes")
                subtheme_label = link.get("subtheme_label", "Sujets importés")
                subject_id = link.get("subject_id", "sujet-sans-id")
                subject_update = self._subject_update(payload, subject_id)
                category = grouped.setdefault(
                    domain_id,
                    {
                        "id": domain_id,
                        "measure_id": subject_id,
                        "label": domain_label,
                        "summary": "Sujets construits depuis des sources publiques traitées.",
                        "subthemes": [],
                    },
                )
                subtheme = self._get_or_create_subtheme(category, subtheme_id, subtheme_label)
                if not any(s.get("id") == subject_id for s in subtheme["subjects"]):
                    subtheme["subjects"].append(self._subject_card(payload, subject_update, link))
        return list(grouped.values())

    def get_subject(self, subject_id: str) -> dict | None:
        for payload in self._payloads():
            subject_update = self._subject_update(payload, subject_id)
            if subject_update is None:
                continue
            link = next(
                (item for item in payload.get("taxonomy_links", []) if item.get("subject_id") == subject_id),
                {},
            )
            category = {
                "id": link.get("domain_id", "sources-officielles"),
                "label": link.get("domain_label", "Sources officielles"),
            }
            subtheme = {
                "id": link.get("subtheme_id", "sujets-importes"),
                "label": link.get("subtheme_label", "Sujets importés"),
            }
            subject = self._subject_card(payload, subject_update, link)
            subject["timeline_events"] = self._timeline_events(payload, subject_update)
            subject["argument_map"] = self._argument_map(subject_update)
            return {
                "category": category,
                "subtheme": subtheme,
                "subject": subject,
                "measure": self.get_measure(subject_id),
            }
        return None

    def _payload_paths(self) -> list[Path]:
        paths = [*self.curated_dir.glob("*.json")]
        if self.include_automatic:
            paths.extend(self.processed_dir.glob("*.json"))
        return sorted({path.resolve() for path in paths})

    def _payloads(self) -> list[dict]:
        payloads = []
        for path in self._payload_paths():
            with path.open("r", encoding="utf-8") as stream:
                payload = json.load(stream)
            status = payload.get("processing", {}).get("status")
            if status in {"validated", "needs_review"} or self.include_automatic:
                payloads.append(payload)
        return payloads

    @staticmethod
    def _status_label(payload: dict) -> str:
        status = payload.get("processing", {}).get("status", "automatic")
        labels = {
            "validated": "Source traitée et validée",
            "needs_review": "Source réelle à relire",
            "automatic": "Source réelle traitée automatiquement",
            "obsolete": "Source obsolète",
        }
        return labels.get(status, status)

    @staticmethod
    def _unique_or_placeholder(values: list[str], placeholder: str) -> list[str]:
        clean = []
        for value in values:
            if value and value not in clean:
                clean.append(value)
        return clean or [placeholder]

    @staticmethod
    def _category_from_trace(trace: dict, role: str) -> str:
        issues = " ".join(trace.get("issues", [])).lower()
        if "calend" in issues or "délai" in issues or "delai" in issues:
            return "calendrier"
        if "coût" in issues or "cout" in issues or "moyen" in issues or "budget" in issues:
            return "cout"
        if "territ" in issues or "commune" in issues or "rural" in issues:
            return "impact_territorial"
        if "égalité" in issues or "egalite" in issues or "accès" in issues or "acces" in issues:
            return "egalite"
        if "libert" in issues or "droit" in issues:
            return "libertes_publiques"
        if "évalu" in issues or "evalu" in issues or "indicateur" in issues:
            return "evaluation"
        return DEFAULT_CATEGORY_BY_ROLE.get(role, "clarte_juridique")

    @staticmethod
    def _problem_type(role: str) -> str:
        return {
            "clarification": "besoin_clarification",
            "alerte_application": "difficulte_application",
            "alternative": "proposition_evolution",
            "opposition": "divergence_arguments",
            "soutien": "divergence_arguments",
            "nuance": "besoin_clarification",
        }.get(role, "besoin_clarification")

    @staticmethod
    def _confidence_label(score: float) -> str:
        if score >= 0.85:
            return "forte"
        if score >= 0.65:
            return "moyenne"
        return "faible"

    @staticmethod
    def _subject_update(payload: dict, subject_id: str) -> dict | None:
        return next((s for s in payload.get("subject_updates", []) if s.get("subject_id") == subject_id), None)

    @staticmethod
    def _get_or_create_subtheme(category: dict, subtheme_id: str, subtheme_label: str) -> dict:
        for subtheme in category["subthemes"]:
            if subtheme.get("id") == subtheme_id:
                return subtheme
        subtheme = {"id": subtheme_id, "label": subtheme_label, "subjects": []}
        category["subthemes"].append(subtheme)
        return subtheme

    def _subject_card(self, payload: dict, subject_update: dict | None, link: dict) -> dict:
        raw = payload["raw_source"]
        subject_update = subject_update or {}
        return {
            "id": link.get("subject_id") or subject_update.get("subject_id"),
            "title": subject_update.get("subject_title") or link.get("subject_title", "Sujet importé"),
            "summary": subject_update.get("summary", "Sujet construit depuis des sources publiques."),
            "context": subject_update.get("context_update", "Contexte issu des traces publiques traitées."),
            "status": self._status_label(payload),
            "votes": {"for": 0, "against": 0, "neutral": 100},
            "timeline": [],
            "legal_texts": [
                {
                    "date": raw.get("date", ""),
                    "type": TRACE_TYPE_MAP.get(raw.get("type", "other"), "texte_legislatif"),
                    "title": raw.get("title", "Source officielle"),
                    "summary": raw.get("metadata", {}).get("summary", raw.get("title", "")),
                    "url": raw.get("url", "#"),
                }
            ],
        }

    @staticmethod
    def _timeline_events(payload: dict, subject_update: dict) -> list[dict]:
        raw = payload["raw_source"]
        events = [{**event, "kind": event.get("kind", "Source officielle")} for event in subject_update.get("timeline_events", [])]
        if not events:
            events.append(
                {
                    "date": raw.get("date", ""),
                    "type": raw.get("type", "source"),
                    "kind": "Source officielle",
                    "title": raw.get("title", "Source officielle"),
                    "summary": raw.get("title", ""),
                    "url": raw.get("url", "#"),
                }
            )
        return sorted(events, key=lambda item: item.get("date", ""), reverse=True)

    @staticmethod
    def _argument_map(subject_update: dict) -> dict:
        actors = {actor["id"]: actor for actor in subject_update.get("actors", [])}
        clusters = []
        axes = set()
        for cluster in subject_update.get("argument_clusters", []):
            axes.add(cluster.get("axis", "arguments-sources"))
            resolved_actors = []
            for actor_link in cluster.get("actors", []):
                actor = actors.get(actor_link.get("actor_id"), {})
                name = actor.get("name", actor_link.get("actor_id", "Acteur public"))
                resolved_actors.append(
                    {
                        "name": name,
                        "initials": "".join(part[:1] for part in name.split()[:2]) or "AP",
                        "role": actor.get("role", "Acteur public"),
                        "party": actor.get("party", "Non renseigné"),
                        "photo": actor.get("photo_url", ""),
                        "quote": actor_link.get("quote", ""),
                        "quote_source": actor_link.get("quote_source", "Source officielle"),
                        "stance_summary": actor_link.get("stance_summary", actor.get("stance_summary", "")),
                    }
                )
            clusters.append({**cluster, "actors": resolved_actors})
        return {
            "axes": [
                {
                    "id": axis,
                    "label": axis.replace("-", " ").capitalize(),
                    "summary": "Axe construit depuis les sources publiques traitées.",
                }
                for axis in sorted(axes or {"arguments-sources"})
            ],
            "clusters": clusters,
            "clusters_by_position": {
                "for": [cluster for cluster in clusters if cluster.get("position") == "for"],
                "against": [cluster for cluster in clusters if cluster.get("position") == "against"],
                "neutral": [cluster for cluster in clusters if cluster.get("position") == "neutral"],
            },
        }
