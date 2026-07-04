from __future__ import annotations

import asyncio

import httpx

from app.main import app, repository


def _request(method: str, url: str, **kwargs) -> httpx.Response:
    async def send() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.request(method, url, **kwargs)

    return asyncio.run(send())


def test_homepage_loads():
    response = _request("GET", "/")
    assert response.status_code == 200
    assert "Cartographier le débat public" in response.text
    assert "data-entry-map-data" not in response.text


def test_entry_map_loads_progressively():
    root = _request("GET", "/api/entry-map")
    assert root.status_code == 200
    categories = root.json()["items"]
    assert categories
    assert all("subthemes" not in category for category in categories)

    while categories[0]["kind"] == "category_group":
        group = max(categories, key=lambda item: item["count"])
        group_response = _request("GET", f"/api/entry-map/category-groups/{group['id']}")
        assert group_response.status_code == 200
        categories = group_response.json()["items"]
        assert categories

    category = max(categories, key=lambda item: item["count"])
    category_response = _request("GET", f"/api/entry-map/categories/{category['id']}")
    assert category_response.status_code == 200
    subthemes = category_response.json()["items"]
    assert subthemes

    while subthemes[0]["kind"] == "subtheme_group":
        group = max(subthemes, key=lambda item: item["count"])
        group_response = _request("GET", f"/api/entry-map/categories/{category['id']}/subtheme-groups/{group['id']}")
        assert group_response.status_code == 200
        subthemes = group_response.json()["items"]
        assert subthemes

    subtheme = max(subthemes, key=lambda item: item["count"])
    subtheme_response = _request("GET", f"/api/entry-map/categories/{category['id']}/subthemes/{subtheme['id']}")
    assert subtheme_response.status_code == 200
    payload = subtheme_response.json()
    assert payload["items"]
    if subtheme["count"] > 12:
        assert payload["mode"] == "groups"
        assert payload["items"][0]["kind"] == "group"
        assert all(not item["label"].startswith("Groupe ") for item in payload["items"])
        assert "subjects" not in payload["items"][0]
    else:
        assert payload["mode"] == "subjects"
        assert payload["items"][0]["kind"] == "subject"


def test_prepare_private_draft():
    measure = repository.list_measures()[0]
    response = _request(
        "POST",
        f"/mesures/{measure.id}/preparer",
        data={
            "selected_intent": "auto",
            "user_text": "Je veux demander au Gouvernement quand cette obligation entrera en vigueur.",
        },
    )
    assert response.status_code == 200
    assert "Question à transmettre" in response.text
    assert "n&#39;est pas conservé par défaut" in response.text or "n'est pas conservé par défaut" in response.text


def test_sources_page_loads():
    response = _request("GET", "/sources")
    assert response.status_code == 200
    assert "Sources utilisées par AgorIA" in response.text
    assert "Raw" in response.text
    assert "Processed" in response.text
    assert "Curated" in response.text
