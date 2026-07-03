from app.civic.router import CivicRouter


def test_router_detects_petition():
    diagnosis = CivicRouter().diagnose("Je veux lancer une pétition pour modifier cette mesure")
    assert diagnosis.output_type == "argumentaire_petition"


def test_router_respects_explicit_choice():
    diagnosis = CivicRouter().diagnose("texte libre", selected_intent="demande_clarification")
    assert diagnosis.output_type == "demande_clarification"
    assert diagnosis.confidence == "fort"
