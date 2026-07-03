from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CivicDiagnosis:
    output_type: str
    confidence: str
    reason: str


class CivicRouter:
    """Aiguille une intention vers une forme d'intervention.

    Version MVP : règles simples et transparentes. En production, ce module
    pourra combiner règles, RAG, classification IA et validation humaine.
    """

    def diagnose(self, user_text: str, selected_intent: str | None = None) -> CivicDiagnosis:
        text = user_text.lower()
        if selected_intent and selected_intent != "auto":
            return CivicDiagnosis(
                output_type=selected_intent,
                confidence="fort",
                reason="L'utilisateur a choisi explicitement cette forme d'intervention.",
            )

        if any(word in text for word in ["pétition", "petition", "signatures", "mobiliser"]):
            return CivicDiagnosis("argumentaire_petition", "moyen", "Le texte vise une mobilisation collective ou une pétition.")
        if any(word in text for word in ["modifier", "amender", "changer la loi", "proposer"]):
            return CivicDiagnosis("proposition_modification", "moyen", "Le texte propose une évolution de la règle.")
        if any(word in text for word in ["consultation", "avis public", "enquête publique"]):
            return CivicDiagnosis("contribution_consultation", "moyen", "Le texte ressemble à une contribution à une consultation.")
        if any(word in text for word in ["quand", "comment", "à qui", "qui est concerné", "clarifier", "clarification"]):
            return CivicDiagnosis("demande_clarification", "moyen", "Le texte demande une précision sur l'application de la mesure.")
        if any(word in text for word in ["gouvernement", "ministre", "réponse", "question"]):
            return CivicDiagnosis("question_a_transmettre", "moyen", "Le texte peut être transformé en question à transmettre à un parlementaire.")
        return CivicDiagnosis("message_representant", "faible", "Aucune catégorie forte n'a été détectée ; un message structuré à un représentant est proposé.")
