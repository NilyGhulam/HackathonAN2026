from __future__ import annotations

import os
import time
from dataclasses import dataclass

import httpx

from app.core.settings import ASSISTANT_PROMPT_PATH

DEFAULT_GROQ_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"


@dataclass(frozen=True)
class LLMSettings:
    provider: str = "none"
    base_url: str | None = None
    model: str | None = None
    api_key: str | None = None

    @classmethod
    def from_env(cls) -> "LLMSettings":
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            return cls()
        return cls(
            provider="groq",
            base_url=os.environ.get("GROQ_BASE_URL", DEFAULT_GROQ_BASE_URL),
            model=os.environ.get("GROQ_MODEL", DEFAULT_GROQ_MODEL),
            api_key=api_key,
        )


def load_base_prompt() -> str:
    return ASSISTANT_PROMPT_PATH.read_text(encoding="utf-8")


class LLMProvider:
    """Point d'extension pour un LLM externe (Groq par défaut, endpoint compatible OpenAI).

    Sans GROQ_API_KEY définie, reste désactivé : les services appelants retombent alors sur
    leur logique déterministe (mots-clés, taxonomie), ce qui garde le prototype fonctionnel
    sans dépendance réseau ni clé API.
    """

    def __init__(self, settings: LLMSettings | None = None) -> None:
        self.settings = settings or LLMSettings.from_env()

    def is_enabled(self) -> bool:
        return self.settings.provider != "none" and bool(self.settings.api_key)

    def complete(self, *, system_prompt: str, user_message: str, max_retries: int = 3) -> str:
        if not self.is_enabled():
            raise NotImplementedError(
                "Aucun fournisseur IA configuré : définissez GROQ_API_KEY pour activer l'appel LLM."
            )
        last_error: Exception | None = None
        for attempt in range(max_retries):
            response = httpx.post(
                f"{self.settings.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.settings.api_key}"},
                json={
                    "model": self.settings.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message},
                    ],
                    "temperature": 0.2,
                },
                timeout=30.0,
            )
            if response.status_code == 429 and attempt < max_retries - 1:
                wait_seconds = min(float(response.headers.get("retry-after", 15 * (attempt + 1))), 40.0)
                last_error = httpx.HTTPStatusError(
                    f"429 rate limited (tentative {attempt + 1}/{max_retries})",
                    request=response.request,
                    response=response,
                )
                time.sleep(wait_seconds)
                continue
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"].strip()
        raise last_error or RuntimeError("Groq: échec après plusieurs tentatives")
