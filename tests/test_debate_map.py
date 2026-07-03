from app.core.taxonomy import load_taxonomy
from app.debate.map_builder import DebateMapBuilder
from app.repositories.demo_repository import DemoRepository


def test_debate_map_builds_clusters():
    repo = DemoRepository()
    taxonomy = load_taxonomy()
    traces = repo.list_traces("mesure-transparence-algorithmes")
    clusters = DebateMapBuilder(taxonomy).build(traces)
    assert len(clusters) >= 2
    assert any(cluster.role == "clarification" for cluster in clusters)


def test_debate_map_groups_clusters_by_theme():
    repo = DemoRepository()
    taxonomy = load_taxonomy()
    traces = repo.list_traces("mesure-transparence-algorithmes")
    themes = DebateMapBuilder(taxonomy).build_by_theme(traces)
    assert len(themes) >= 1
    assert any(theme.key == "cadre_juridique" for theme in themes)
    assert all(theme.clusters for theme in themes)
