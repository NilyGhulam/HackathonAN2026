from fastapi.testclient import TestClient

from app.main import app


def test_homepage_loads():
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert "Cartographier le débat public" in response.text


def test_prepare_private_draft():
    client = TestClient(app)
    response = client.post(
        "/mesures/mesure-transparence-algorithmes/preparer",
        data={
            "selected_intent": "auto",
            "user_text": "Je veux demander au Gouvernement quand cette obligation entrera en vigueur.",
        },
    )
    assert response.status_code == 200
    assert "Question à transmettre" in response.text
    assert "n&#39;est pas conservé par défaut" in response.text or "n'est pas conservé par défaut" in response.text
