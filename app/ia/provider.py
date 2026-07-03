from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LLMSettings:
    provider: str = "none"
    base_url: str | None = None
    model: str | None = None


class LLMProvider:
    """Point d'extension pour Albert API ou un endpoint compatible OpenAI.

    Le prototype fonctionne sans IA externe. Cette classe documente l'endroit
    où brancher ensuite un RAG sourcé : embeddings, rerank, génération contrôlée.
    """

    def __init__(self, settings: LLMSettings | None = None) -> None:
        self.settings = settings or LLMSettings()

    def is_enabled(self) -> bool:
        return self.settings.provider != "none"

    def complete(self, prompt: str) -> str:
        raise NotImplementedError(
            "Le prototype ne fait pas encore d'appel LLM. Branchez ici Albert API ou un endpoint compatible OpenAI."
        )
