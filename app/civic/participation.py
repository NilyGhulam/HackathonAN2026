from __future__ import annotations

from dataclasses import dataclass

from app.civic.router import CivicRouter
from app.core.models import CivicChannel
from app.core.taxonomy import Taxonomy
from app.ia.provider import LLMProvider, load_base_prompt
from app.repositories.official_channels import OfficialChannelsRepository


@dataclass(frozen=True)
class ParticipationResult:
    output_type: str
    output_label: str
    reason: str
    channels: list[CivicChannel]


class ParticipationService:
    """Oriente un citoyen qui veut agir vers les canaux publics adaptés à son initiative.

    Contrairement à DraftService, ce service ne génère pas de brouillon : il se limite à
    indiquer les personnes et sites officiels pertinents (député, pétitions, consultations...).
    Le diagnostic et la liste de canaux restent toujours déterministes (CivicRouter, taxonomie) ;
    si un LLM est configuré (GROQ_API_KEY), il ne fait que reformuler l'explication à partir de
    cette liste fermée (Mode B2 du prompt `docs/api/extraction_prompt.md`), sans jamais inventer
    de canal.
    """

    def __init__(
        self,
        taxonomy: Taxonomy,
        channels_repository: OfficialChannelsRepository,
        router: CivicRouter | None = None,
        llm_provider: LLMProvider | None = None,
    ) -> None:
        self.taxonomy = taxonomy
        self.channels_repository = channels_repository
        self.router = router or CivicRouter()
        self.llm_provider = llm_provider or LLMProvider()

    def orient(self, *, initiative_text: str) -> ParticipationResult:
        diagnosis = self.router.diagnose(initiative_text)
        channels = self.channels_repository.find_for_output(diagnosis.output_type)
        reason = diagnosis.reason
        if self.llm_provider.is_enabled():
            explanation = self._explain_with_llm(initiative_text, diagnosis.output_type, channels)
            if explanation:
                reason = explanation
        return ParticipationResult(
            output_type=diagnosis.output_type,
            output_label=self.taxonomy.label("participation_outputs", diagnosis.output_type),
            reason=reason,
            channels=channels,
        )

    def _explain_with_llm(self, initiative_text: str, output_type: str, channels: list[CivicChannel]) -> str | None:
        channels_lines = [f"- {channel.label} ({channel.url}) : {channel.note}" for channel in channels]
        channels_block = "\n".join(channels_lines) if channels_lines else "(aucun canal disponible)"
        user_message = (
            "MODE: assistant_conversationnel\n"
            "SOUS_MODE: participer\n"
            f"INITIATIVE: {initiative_text}\n"
            f"DIAGNOSTIC: {output_type}\n"
            f"CANAUX_DISPONIBLES:\n{channels_block}"
        )
        try:
            return self.llm_provider.complete(system_prompt=load_base_prompt(), user_message=user_message)
        except Exception:
            return None
