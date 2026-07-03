from app.core.taxonomy import load_taxonomy


def test_taxonomy_loads_categories():
    taxonomy = load_taxonomy()
    assert "clarte_juridique" in taxonomy.categories
    assert "cadre_juridique" in taxonomy.category_themes
    assert taxonomy.category_theme("clarte_juridique") == "cadre_juridique"
    assert taxonomy.label("argument_roles", "clarification") == "Clarification"
