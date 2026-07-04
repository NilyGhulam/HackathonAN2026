from __future__ import annotations

import json
import re
import unicodedata
from collections import defaultdict
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

BROAD_CATEGORY_RULES = [
    (
        "institutions-vie-publique",
        "Institutions et vie publique",
        ("parlement", "election", "referendum", "administration", "collectivites", "communes", "intercommunalite", "gouvernement", "lois", "projet de loi", "proposition de loi", "proposition de resolution", "rapport", "elus", "etat", "fonction publique", "fonctionnaires", "services publics", "marches publics", "partis"),
    ),
    (
        "sante-solidarites",
        "Santé et solidarités",
        ("sante", "securite sociale", "famille", "enfants", "handicap", "retraites", "assurance maladie", "assurance complementaire", "bioethique", "maladies", "medecine", "pharmacie", "medicaments", "fin de vie", "dependance", "personnes agees", "institutions sociales", "politique sociale", "pauvrete", "prestations familiales", "sang", "ivg", "interruption volontaire"),
    ),
    (
        "justice-securite",
        "Justice et sécurité",
        ("justice", "securite", "crimes", "delits", "terrorisme", "victimes", "armes", "drogue", "police", "ordre public", "harcelement", "privation de liberte", "professions judiciaires", "decheances", "incapacites"),
    ),
    (
        "economie-finances",
        "Économie et finances",
        ("finances", "impots", "taxes", "taxe", "tva", "banques", "assurances", "commerce", "consommation", "entreprises", "industrie", "politique economique", "pouvoir d'achat", "economie sociale", "propriete"),
    ),
    (
        "travail-emploi",
        "Travail et emploi",
        ("travail", "emploi", "chomage", "formation professionnelle", "apprentissage", "professions et activites sociales"),
    ),
    (
        "environnement-territoires",
        "Environnement et territoires",
        ("environnement", "biodiversite", "climat", "eau", "catastrophes", "amenagement", "territoire", "mer", "littoral", "forets", "dechets", "developpement durable", "pollution", "nuisances", "mines", "carrieres", "ruralite", "urbanisme", "voirie", "montagne", "departements", "regions"),
    ),
    (
        "education-culture-numerique",
        "Éducation, culture et numérique",
        ("enseignement", "education", "culture", "arts", "audiovisuel", "numerique", "communication", "internet", "nouvelles technologies", "presse", "livres", "examens", "concours", "diplomes", "recherche", "innovation", "sports"),
    ),
    (
        "international-defense",
        "International et défense",
        ("defense", "politique exterieure", "accord international", "francais de l'etranger", "organisations internationales", "ambassades", "traites", "conventions", "union europeenne", "frontaliers"),
    ),
    (
        "agriculture-alimentation",
        "Agriculture et alimentation",
        ("agriculture", "agroalimentaire", "alimentation", "aquaculture", "peche", "chasse", "elevage", "mutualite sociale agricole", "alcools", "boissons"),
    ),
    (
        "logement-transports-energie",
        "Logement, transports et énergie",
        ("logement", "transports", "automobiles", "ferroviaires", "aeriens", "energie", "carburants", "batiment", "taxis", "postes", "hotellerie", "tourisme"),
    ),
    (
        "droits-societe",
        "Droits et société",
        ("droits", "discriminations", "associations", "anciens combattants", "animaux", "ceremonies", "femmes", "egalite", "laicite", "religions", "cultes", "gens du voyage", "jeunes", "nationalite", "papiers d'identite", "refugies", "apatrides", "etrangers", "immigration", "sectes"),
    ),
    ("outre-mer", "Outre-mer", ("outre-mer", "mayotte", "guadeloupe", "martinique", "guyane", "réunion", "reunion")),
]


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
        self._payload_cache: list[dict] | None = None
        self._index_cache: dict[str, Any] | None = None

    def has_payloads(self) -> bool:
        return bool(self._payload_paths())

    def list_measures(self) -> list[Measure]:
        by_id: dict[str, dict[str, Any]] = {}
        index = self._index()
        for payload in index["payloads"]:
            raw = payload["raw_source"]
            source = SourceRef(
                label=raw.get("title", "Source officielle"),
                type=TRACE_TYPE_MAP.get(raw.get("type", "other"), "texte_legislatif"),
                url=raw.get("url", "#"),
            )
            for subject in payload.get("subject_updates", []):
                subject_id = subject["subject_id"]
                subject_traces = index["traces_by_subject"].get(subject_id, [])
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
                for trace in subject_traces:
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
        index = self._index()
        if measure_id is not None:
            return [
                self._public_trace(trace, index["payload_by_trace_id"].get(trace.get("id", ""), {}), measure_id)
                for trace in index["traces_by_subject"].get(measure_id, [])
            ]
        return [
            self._public_trace(trace, index["payload_by_trace_id"].get(trace.get("id", ""), {}), subject_id)
            for subject_id, traces in index["traces_by_subject"].items()
            for trace in traces
        ]

    def list_debate_subjects(self, measure_id: str) -> list[dict]:
        return [item for item in self.list_all_debate_subjects() if item.get("measure_id") == measure_id]

    def list_all_debate_subjects(self) -> list[dict]:
        grouped: dict[str, dict[str, Any]] = {}
        index = self._index()
        for payload in index["payloads"]:
            for subject_update in payload.get("subject_updates", []):
                subject_id = subject_update.get("subject_id", "sujet-sans-id")
                link = index["taxonomy_links_by_subject"].get(subject_id, {})
                taxonomy = self._navigation_taxonomy(subject_update, link)
                category = grouped.setdefault(
                    taxonomy["domain_id"],
                    {
                        "id": taxonomy["domain_id"],
                        "measure_id": subject_id,
                        "label": taxonomy["domain_label"],
                        "summary": "Sujets construits depuis des sources publiques traitées.",
                        "subthemes": [],
                    },
                )
                subtheme = self._get_or_create_subtheme(category, taxonomy["subtheme_id"], taxonomy["subtheme_label"])
                if not any(s.get("id") == subject_id for s in subtheme["subjects"]):
                    subtheme["subjects"].append(self._subject_card(payload, subject_update, link))
        for category in grouped.values():
            category["subthemes"].sort(key=lambda item: item.get("label", ""))
            for subtheme in category["subthemes"]:
                subtheme["subjects"].sort(key=lambda item: item.get("title", ""))
        return sorted(grouped.values(), key=lambda item: item.get("label", ""))

    def get_subject(self, subject_id: str) -> dict | None:
        index = self._index()
        subject_update = index["subject_updates_by_id"].get(subject_id)
        if subject_update is None:
            return None
        payload = index["payload_by_subject"].get(subject_id, {})
        link = index["taxonomy_links_by_subject"].get(subject_id, {})
        if payload:
            taxonomy = self._navigation_taxonomy(subject_update, link)
            category = {
                "id": taxonomy["domain_id"],
                "label": taxonomy["domain_label"],
            }
            subtheme = {
                "id": taxonomy["subtheme_id"],
                "label": taxonomy["subtheme_label"],
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
        if self._payload_cache is not None:
            return self._payload_cache
        payloads = []
        for path in self._payload_paths():
            with path.open("r", encoding="utf-8") as stream:
                payload = json.load(stream)
            status = payload.get("processing", {}).get("status")
            if status in {"validated", "needs_review"} or self.include_automatic:
                payloads.append(payload)
        self._payload_cache = payloads
        return payloads

    def _index(self) -> dict[str, Any]:
        if self._index_cache is not None:
            return self._index_cache
        payloads = self._payloads()
        subject_updates_by_id: dict[str, dict] = {}
        taxonomy_links_by_subject: dict[str, dict] = {}
        payload_by_subject: dict[str, dict] = {}
        payload_by_trace_id: dict[str, dict] = {}
        traces_by_subject: dict[str, list[dict]] = defaultdict(list)

        for payload in payloads:
            for subject in payload.get("subject_updates", []):
                subject_id = subject.get("subject_id")
                if subject_id:
                    subject_updates_by_id[subject_id] = subject
                    payload_by_subject[subject_id] = payload
            for link in payload.get("taxonomy_links", []):
                subject_id = link.get("subject_id")
                if subject_id and subject_id not in taxonomy_links_by_subject:
                    taxonomy_links_by_subject[subject_id] = link
                    payload_by_subject.setdefault(subject_id, payload)
            fallback_subject_ids = [subject.get("subject_id") for subject in payload.get("subject_updates", []) if subject.get("subject_id")]
            for trace in payload.get("extracted_traces", []):
                trace_id = trace.get("id", "")
                payload_by_trace_id[trace_id] = payload
                subject_id = trace.get("metadata", {}).get("subject_id")
                subject_ids = [subject_id] if subject_id else fallback_subject_ids
                for linked_subject_id in subject_ids:
                    traces_by_subject[linked_subject_id].append(trace)

        self._index_cache = {
            "payloads": payloads,
            "subject_updates_by_id": subject_updates_by_id,
            "taxonomy_links_by_subject": taxonomy_links_by_subject,
            "payload_by_subject": payload_by_subject,
            "payload_by_trace_id": payload_by_trace_id,
            "traces_by_subject": dict(traces_by_subject),
        }
        return self._index_cache

    def _public_trace(self, trace: dict, payload: dict, subject_id: str) -> PublicTrace:
        raw = payload.get("raw_source", {})
        evidence = (trace.get("evidence") or [{}])[0]
        role = ROLE_MAP.get(trace.get("argument_role"), "clarification")
        category = self._category_from_trace(trace, role)
        return PublicTrace(
            id=f"{subject_id}:{trace.get('id', subject_id)}",
            measure_id=subject_id,
            trace_type=TRACE_TYPE_MAP.get(raw.get("type", "other"), "texte_legislatif"),
            institution=raw.get("institution", "institution publique"),
            date=raw.get("date", ""),
            speaker=evidence.get("speaker") or raw.get("metadata", {}).get("speaker", raw.get("institution", "Source publique")),
            title=raw.get("title", "Source officielle"),
            excerpt=evidence.get("quote") or trace.get("summary", ""),
            source_url=evidence.get("source_url") or raw.get("url", "#"),
            argument_role=role,
            category=category,
            problem_type=self._problem_type(role),
            confidence=self._confidence_label(trace.get("confidence", 0)),
        )

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

    def _navigation_taxonomy(self, subject_update: dict | None, link: dict) -> dict[str, str]:
        subject_update = subject_update or {}
        path = subject_update.get("classification", {}).get("canonical_path") or []
        source_domain = path[0] if path else link.get("domain_label", "Sources officielles")
        source_subtheme = path[1] if len(path) > 1 else link.get("subtheme_label", "Sujets importés")
        domain_id, domain_label = self._broad_category(source_domain)
        subtheme_label = source_domain if source_domain != domain_label else source_subtheme
        return {
            "domain_id": domain_id,
            "domain_label": domain_label,
            "subtheme_id": f"{domain_id}__{self._slugify(subtheme_label) or 'sujets-importes'}",
            "subtheme_label": subtheme_label or "Sujets importés",
        }

    @staticmethod
    def _broad_category(label: str) -> tuple[str, str]:
        normalized = ProcessedRepository._normalize(label)
        for identifier, broad_label, keywords in BROAD_CATEGORY_RULES:
            if any(keyword in normalized for keyword in keywords):
                return identifier, broad_label
        return "autres-politiques-publiques", "Autres politiques publiques"

    @staticmethod
    def _normalize(value: str) -> str:
        normalized = unicodedata.normalize("NFKD", str(value).lower())
        return "".join(char for char in normalized if not unicodedata.combining(char))

    @staticmethod
    def _slugify(value: str) -> str:
        normalized = ProcessedRepository._normalize(value)
        return re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")

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
