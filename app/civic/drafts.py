from __future__ import annotations

from app.core.models import DraftResult, Measure
from app.core.taxonomy import Taxonomy
from app.repositories.official_channels import OfficialChannelsRepository
from app.civic.router import CivicDiagnosis, CivicRouter


class DraftService:
    def __init__(
        self,
        taxonomy: Taxonomy,
        channels_repository: OfficialChannelsRepository,
        router: CivicRouter | None = None,
    ) -> None:
        self.taxonomy = taxonomy
        self.channels_repository = channels_repository
        self.router = router or CivicRouter()

    def prepare(
        self,
        *,
        measure: Measure,
        user_text: str,
        selected_intent: str | None = None,
    ) -> DraftResult:
        diagnosis = self.router.diagnose(user_text, selected_intent)
        output_label = self.taxonomy.label("participation_outputs", diagnosis.output_type)
        title = self._title_for(diagnosis, measure)
        draft = self._draft_for(diagnosis, measure, user_text)
        channels = self.channels_repository.find_for_output(diagnosis.output_type)
        return DraftResult(
            output_type=diagnosis.output_type,
            output_label=output_label,
            title=title,
            draft=draft,
            channels=channels,
            privacy_notice=(
                "Ce brouillon est généré à la demande et n'est pas conservé par défaut. "
                "Aucune transmission n'est effectuée automatiquement."
            ),
        )

    def _title_for(self, diagnosis: CivicDiagnosis, measure: Measure) -> str:
        if diagnosis.output_type == "question_a_transmettre":
            return f"Question à transmettre - {measure.article}"
        if diagnosis.output_type == "demande_clarification":
            return f"Demande de clarification - {measure.article}"
        if diagnosis.output_type == "proposition_modification":
            return f"Proposition d'évolution - {measure.article}"
        if diagnosis.output_type == "argumentaire_petition":
            return f"Argumentaire de pétition - {measure.title}"
        if diagnosis.output_type == "contribution_consultation":
            return f"Contribution à consultation - {measure.title}"
        return f"Message à un représentant - {measure.title}"

    def _draft_for(self, diagnosis: CivicDiagnosis, measure: Measure, user_text: str) -> str:
        intro = (
            f"Je souhaite attirer votre attention sur la mesure suivante : {measure.title} "
            f"({measure.article}, {measure.law_title})."
        )
        context = (
            "D'après les éléments publics consultés, cette mesure concerne notamment : "
            + ", ".join(measure.audiences)
            + "."
        )
        user_part = f"Mon constat, ma question ou ma proposition est le suivant : {user_text.strip()}"

        if diagnosis.output_type == "demande_clarification":
            closing = "Je souhaiterais donc obtenir une clarification sur le champ d'application, le calendrier ou les obligations concrètes prévues."
        elif diagnosis.output_type == "question_a_transmettre":
            closing = "Cette question pourrait-elle être relayée auprès du Gouvernement ou des services compétents afin d'obtenir une réponse publique ?"
        elif diagnosis.output_type == "proposition_modification":
            closing = "Je propose que cette difficulté soit examinée dans la perspective d'une évolution, d'une précision ou d'un amendement futur."
        elif diagnosis.output_type == "argumentaire_petition":
            closing = "Cette formulation peut servir de base à une pétition institutionnelle, à compléter par une demande précise et vérifiable."
        elif diagnosis.output_type == "contribution_consultation":
            closing = "Cette contribution peut être adaptée aux exigences de la consultation publique concernée."
        else:
            closing = "Je vous remercie par avance de l'attention portée à cette demande et des suites que vous pourrez lui donner."

        return "\n\n".join([intro, context, user_part, closing])
