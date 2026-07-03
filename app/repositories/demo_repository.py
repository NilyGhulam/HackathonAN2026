from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from app.core.models import Measure, PublicTrace, SourceRef
from app.core.settings import DATA_DIR, PROCESSED_DATA_DIR


class DemoRepository:
    """Accès aux données de démonstration.

    Le dépôt est volontairement isolé : lorsqu'une vraie API sera branchée,
    elle devra exposer les mêmes méthodes métier sans modifier les services.
    """

    def __init__(self, data_dir: Path = DATA_DIR) -> None:
        self.data_dir = data_dir

    def list_measures(self) -> list[Measure]:
        items = self._load_json("measures.json")
        return [self._measure_from_dict(item) for item in items]

    def get_measure(self, measure_id: str) -> Measure | None:
        return next((m for m in self.list_measures() if m.id == measure_id), None)

    def list_traces(self, measure_id: str | None = None) -> list[PublicTrace]:
        items = self._load_json("public_traces.json")
        traces = [PublicTrace(**item) for item in items]
        if measure_id is None:
            return traces
        return [trace for trace in traces if trace.measure_id == measure_id]

    def list_debate_subjects(self, measure_id: str) -> list[dict]:
        items = self._load_json("debate_subjects.json")
        return [item for item in items if item.get("measure_id") == measure_id]

    def list_all_debate_subjects(self) -> list[dict]:
        return self._load_json("debate_subjects.json")

    def list_all_debate_subjects_with_status(self) -> list[dict]:
        """Comme list_all_debate_subjects, mais chaque sujet est annoté de has_official_traces
        et official_traces_count, pour signaler sur les vignettes qu'un sujet a de vraies
        données extraites (data/processed/) plutôt que de rester figé sur la démo."""
        grouped = self._processed_updates_by_subject()
        categories = self.list_all_debate_subjects()
        annotated = []
        for category in categories:
            subthemes = []
            for subtheme in category.get("subthemes", []):
                subjects = []
                for subject in subtheme.get("subjects", []):
                    updates = grouped.get(subject.get("id", ""), [])
                    subjects.append(
                        {
                            **subject,
                            "has_official_traces": bool(updates),
                            "official_traces_count": sum(
                                len(update.get("argument_clusters", [])) for update in updates
                            ),
                        }
                    )
                subthemes.append({**subtheme, "subjects": subjects})
            annotated.append({**category, "subthemes": subthemes})
        return annotated

    def get_subject(self, subject_id: str) -> dict | None:
        for category in self.list_all_debate_subjects():
            for subtheme in category.get("subthemes", []):
                for subject in subtheme.get("subjects", []):
                    if subject.get("id") == subject_id:
                        measure_id = category.get("measure_id")
                        processed_updates = self._load_processed_subject_updates(subject.get("id", ""))
                        enriched_subject = {
                            **subject,
                            "timeline_events": self._subject_timeline_events(processed_updates),
                            "argument_map": self._subject_argument_map(processed_updates),
                        }
                        return {
                            "category": category,
                            "subtheme": subtheme,
                            "subject": enriched_subject,
                            "measure": self.get_measure(measure_id) if measure_id else None,
                        }
        return None

    def _processed_updates_by_subject(self) -> dict[str, list[dict]]:
        grouped: dict[str, list[dict]] = defaultdict(list)
        if not PROCESSED_DATA_DIR.exists():
            return grouped
        for path in PROCESSED_DATA_DIR.rglob("*.json"):
            if "_failed" in path.parts:
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            for update in payload.get("subject_updates", []):
                subject_id = update.get("subject_id")
                if subject_id:
                    grouped[subject_id].append(update)
        return grouped

    def _load_processed_subject_updates(self, subject_id: str) -> list[dict]:
        if not subject_id:
            return []
        return self._processed_updates_by_subject().get(subject_id, [])

    @staticmethod
    def _subject_timeline_events(processed_updates: list[dict]) -> list[dict]:
        """Uniquement les traces réelles extraites par le pipeline IA (data/processed/) : pas
        de repli sur la démonstration, pour ne jamais afficher un contenu fictif comme réel."""
        events = [event for update in processed_updates for event in update.get("timeline_events", [])]
        return sorted(events, key=lambda item: item.get("date", ""), reverse=True)

    @staticmethod
    def _subject_argument_map(processed_updates: list[dict]) -> dict:
        """Uniquement les traces réelles extraites par le pipeline IA (data/processed/) : pas
        de repli sur la démonstration, pour ne jamais afficher un contenu fictif comme réel."""
        clusters: list[dict] = []
        for update in processed_updates:
            actors_by_id = {actor["id"]: actor for actor in update.get("actors", []) if actor.get("id")}
            for cluster in update.get("argument_clusters", []):
                actors = []
                for cluster_actor in cluster.get("actors", []):
                    actor = actors_by_id.get(cluster_actor.get("actor_id"), {})
                    name = actor.get("name", "Acteur public")
                    actors.append(
                        {
                            "name": name,
                            "initials": "".join(part[:1] for part in name.split()[:2]),
                            "role": actor.get("role", ""),
                            "party": actor.get("party", "Non renseigné"),
                            "photo": actor.get("photo_url", ""),
                            "quote": cluster_actor.get("quote", ""),
                            "quote_source": cluster_actor.get("quote_source", ""),
                            "stance_summary": cluster_actor.get("stance_summary", ""),
                        }
                    )
                if actors:
                    clusters.append(
                        {
                            "id": cluster.get("id", f"processed-{len(clusters) + 1}"),
                            "axis": cluster.get("axis", "arguments-declares"),
                            "position": cluster.get("position", "neutral"),
                            "label": cluster.get("label", ""),
                            "summary": cluster.get("summary", ""),
                            "actors": actors,
                        }
                    )
        return {
            "axes": [],
            "clusters": clusters,
            "clusters_by_position": {
                "for": [c for c in clusters if c.get("position") == "for"],
                "against": [c for c in clusters if c.get("position") == "against"],
                "neutral": [c for c in clusters if c.get("position") == "neutral"],
            },
        }

    def _load_json(self, filename: str) -> list[dict]:
        path = self.data_dir / filename
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def _measure_from_dict(item: dict) -> Measure:
        sources = [SourceRef(**source) for source in item.get("sources", [])]
        clean = {**item, "sources": sources}
        return Measure(**clean)
