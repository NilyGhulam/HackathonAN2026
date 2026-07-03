from __future__ import annotations

from collections import defaultdict

from app.core.models import DebateCluster, DebateTheme, PublicTrace
from app.core.taxonomy import Taxonomy


class DebateMapBuilder:
    """Construit une cartographie argumentative à partir de traces publiques.

    Ce service ne classe pas des citoyens : il regroupe des sources publiques
    par rôle argumentatif et par catégorie de débat.
    """

    def __init__(self, taxonomy: Taxonomy) -> None:
        self.taxonomy = taxonomy

    def build(self, traces: list[PublicTrace]) -> list[DebateCluster]:
        grouped: dict[tuple[str, str], list[PublicTrace]] = defaultdict(list)
        for trace in traces:
            grouped[(trace.argument_role, trace.category)].append(trace)

        clusters: list[DebateCluster] = []
        for (role, category), items in sorted(grouped.items(), key=lambda x: (x[0][0], x[0][1])):
            clusters.append(
                DebateCluster(
                    role=role,
                    category=category,
                    label=self.taxonomy.label("argument_roles", role),
                    category_label=self.taxonomy.label("categories", category),
                    traces=items,
                )
            )
        return clusters

    def build_by_theme(self, traces: list[PublicTrace]) -> list[DebateTheme]:
        grouped: dict[str, list[DebateCluster]] = defaultdict(list)
        for cluster in self.build(traces):
            grouped[self.taxonomy.category_theme(cluster.category)].append(cluster)

        themes: list[DebateTheme] = []
        for theme_key, clusters in sorted(
            grouped.items(),
            key=lambda item: self.taxonomy.label("category_themes", item[0]),
        ):
            themes.append(
                DebateTheme(
                    key=theme_key,
                    label=self.taxonomy.label("category_themes", theme_key),
                    description=self.taxonomy.description("category_themes", theme_key),
                    clusters=clusters,
                )
            )
        return themes

    def stats(self, traces: list[PublicTrace]) -> dict[str, int]:
        return {
            "traces": len(traces),
            "roles": len({t.argument_role for t in traces}),
            "categories": len({t.category for t in traces}),
            "institutions": len({t.institution for t in traces}),
        }
