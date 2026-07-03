from __future__ import annotations

import json
from pathlib import Path

from app.core.models import Measure, PublicTrace, SourceRef
from app.core.settings import DATA_DIR


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

    def get_subject(self, subject_id: str) -> dict | None:
        for category in self.list_all_debate_subjects():
            for subtheme in category.get("subthemes", []):
                for subject in subtheme.get("subjects", []):
                    if subject.get("id") == subject_id:
                        measure_id = category.get("measure_id")
                        enriched_subject = {
                            **subject,
                            "timeline_events": self._subject_timeline_events(subject),
                            "argument_map": self._subject_argument_map(subject),
                        }
                        return {
                            "category": category,
                            "subtheme": subtheme,
                            "subject": enriched_subject,
                            "measure": self.get_measure(measure_id) if measure_id else None,
                        }
        return None

    @staticmethod
    def _subject_timeline_events(subject: dict) -> list[dict]:
        legal_events = [
            {
                **item,
                "kind": "Texte ou loi",
            }
            for item in subject.get("legal_texts", [])
        ]
        news_events = [
            {
                **item,
                "kind": "Actualité",
            }
            for item in subject.get("timeline", [])
        ]
        return sorted(
            [*legal_events, *news_events],
            key=lambda item: item.get("date", ""),
            reverse=True,
        )

    @staticmethod
    def _subject_argument_map(subject: dict) -> dict:
        if subject.get("argument_map"):
            argument_map = subject["argument_map"]
            clusters = argument_map.get("clusters", [])
        else:
            labels = {
                "favorable": ("for", "Arguments favorables"),
                "unfavorable": ("against", "Arguments défavorables"),
                "neutral": ("neutral", "Arguments neutres"),
            }
            clusters = []
            for source_key, (position, label) in labels.items():
                actors = []
                for index, argument in enumerate(subject.get("arguments", {}).get(source_key, []), start=1):
                    actors.append(
                        {
                            "name": argument.get("carrier", "Acteur public"),
                            "initials": "".join(part[:1] for part in argument.get("carrier", "AP").split()[:2]),
                            "role": argument.get("carrier", "Acteur public"),
                            "party": "Non renseigné",
                            "photo": "",
                            "quote": argument.get("text", ""),
                            "quote_source": argument.get("source", "Source non renseignée"),
                            "stance_summary": argument.get("text", ""),
                        }
                    )
                if actors:
                    clusters.append(
                        {
                            "id": f"{position}-{len(clusters) + 1}",
                            "axis": "arguments-declares",
                            "position": position,
                            "label": label,
                            "summary": "Arguments regroupés à partir des traces disponibles pour ce sujet.",
                            "actors": actors,
                        }
                    )
            argument_map = {
                "axes": [
                    {
                        "id": "arguments-declares",
                        "label": "Arguments déclarés",
                        "summary": "Axe construit automatiquement à partir des arguments disponibles.",
                    }
                ],
                "clusters": clusters,
            }

        return {
            **argument_map,
            "clusters_by_position": {
                "for": [cluster for cluster in clusters if cluster.get("position") == "for"],
                "against": [cluster for cluster in clusters if cluster.get("position") == "against"],
                "neutral": [cluster for cluster in clusters if cluster.get("position") == "neutral"],
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
