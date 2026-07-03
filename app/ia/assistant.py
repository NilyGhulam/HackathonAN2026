from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.models import Measure
from app.ia.provider import LLMProvider, load_base_prompt

_STOPWORDS = {
    "le", "la", "les", "de", "des", "du", "un", "une", "et", "ou", "est", "que", "qui", "quoi",
    "a", "à", "dans", "pour", "sur", "en", "ce", "cette", "ces", "au", "aux", "se", "ne", "pas",
    "plus", "comment", "quand", "pourquoi", "avec", "sans", "par", "être", "son", "sa", "ses",
    "il", "elle", "ils", "elles", "je", "tu", "nous", "vous", "on", "donc", "car", "mais",
}


def _tokenize(text: str) -> set[str]:
    words = re.findall(r"[a-zàâäéèêëïîôöùûüç]+", text.lower())
    return {word for word in words if len(word) > 2 and word not in _STOPWORDS}


@dataclass(frozen=True)
class AssistantLink:
    label: str
    url: str
    note: str = ""


@dataclass(frozen=True)
class AssistantAnswer:
    question: str
    answer: str
    links: list[AssistantLink]
    disclaimer: str = (
        "Cette synthèse rassemble des arguments publics déjà répertoriés sur AgoraLoi. "
        "Elle ne représente pas une prise de position et ne remplace pas les sources officielles."
    )


@dataclass
class _IndexedItem:
    tokens: set[str]
    excerpt: str
    link: AssistantLink
    family: str
    position: str = ""


class AssistantService:
    """Assistant de navigation : répond à une question et pointe vers les sections pertinentes.

    Les traces publiques déjà cartographiées (arguments, chronologie) servent d'index de
    recherche par mots-clés pour sélectionner un contexte sourcé. Si un LLM est configuré
    (GROQ_API_KEY), ce contexte est envoyé au modèle avec le prompt `docs/api/extraction_prompt.md`
    (Mode B1) pour rédiger la réponse ; sinon, une synthèse déterministe prend le relais. Dans
    les deux cas, les liens affichés viennent uniquement de l'index, jamais du modèle.
    """

    def __init__(self, llm_provider: LLMProvider | None = None) -> None:
        self.llm_provider = llm_provider or LLMProvider()

    def answer(
        self,
        *,
        subject_id: str,
        subject: dict,
        measure: Measure | None,
        question: str,
    ) -> AssistantAnswer:
        items = self._build_index(subject_id, subject, measure)
        matches = self._rank(question, items)
        top = matches[:4] if matches else self._default_selection(items)
        links = self._dedupe_links([item.link for item in top])
        text = self._compose_with_llm(subject, question, top) if self.llm_provider.is_enabled() else None
        if text is None:
            text = self._compose(subject, top)
        return AssistantAnswer(question=question, answer=text, links=links)

    def _compose_with_llm(self, subject: dict, question: str, top: list[_IndexedItem]) -> str | None:
        context_lines = [
            f"- ({item.family} · {item.position or 'n/a'}) {item.excerpt}" for item in top if item.excerpt
        ]
        context = "\n".join(context_lines) if context_lines else "(aucun élément sourcé trouvé)"
        user_message = (
            "MODE: assistant_conversationnel\n"
            "SOUS_MODE: question\n"
            f"SUJET: {subject.get('title', '')} — {subject.get('summary', '')}\n"
            f"CONTEXTE_SOURCE:\n{context}\n"
            f"QUESTION: {question}"
        )
        try:
            return self.llm_provider.complete(system_prompt=load_base_prompt(), user_message=user_message)
        except Exception:
            return None

    def _build_index(self, subject_id: str, subject: dict, measure: Measure | None) -> list[_IndexedItem]:
        items: list[_IndexedItem] = []
        argument_map = subject.get("argument_map") or {}

        for cluster in argument_map.get("clusters", []):
            position = cluster.get("position", "neutral")
            position_label = {
                "for": "Argument favorable",
                "against": "Argument défavorable",
            }.get(position, "Élément neutre / clarification")
            excerpt = cluster.get("summary") or cluster.get("label") or ""
            text = " ".join([cluster.get("label", ""), cluster.get("summary", "")])
            for actor in cluster.get("actors", []):
                text += " " + actor.get("quote", "") + " " + actor.get("stance_summary", "")
            items.append(
                _IndexedItem(
                    tokens=_tokenize(text),
                    excerpt=excerpt,
                    link=AssistantLink(
                        label=f"{position_label} — {cluster.get('label', 'Carte des arguments')}",
                        url=f"/sujets/{subject_id}#argument-map",
                        note=excerpt[:140],
                    ),
                    family="argument",
                    position=position,
                )
            )

        for event in subject.get("timeline_events", []):
            text = " ".join([event.get("title", ""), event.get("summary", ""), event.get("kind", "")])
            items.append(
                _IndexedItem(
                    tokens=_tokenize(text),
                    excerpt=event.get("summary", ""),
                    link=AssistantLink(
                        label=f"{event.get('date', '')} · {event.get('title', 'Repère chronologique')}",
                        url=event.get("url") or f"/sujets/{subject_id}#timeline-block",
                        note=event.get("summary", "")[:140],
                    ),
                    family="timeline",
                )
            )

        if measure is not None:
            measure_text = " ".join(
                [
                    measure.title,
                    measure.summary,
                    " ".join(measure.changes),
                    " ".join(measure.obligations),
                    " ".join(measure.deadlines),
                    " ".join(measure.audiences),
                ]
            )
            items.append(
                _IndexedItem(
                    tokens=_tokenize(measure_text),
                    excerpt=measure.summary,
                    link=AssistantLink(
                        label=f"Fiche mesure — {measure.title}",
                        url=f"/mesures/{measure.id}",
                        note="Ce qui change, publics concernés, obligations et échéances.",
                    ),
                    family="measure",
                )
            )
        return items

    def _rank(self, question: str, items: list[_IndexedItem]) -> list[_IndexedItem]:
        question_tokens = _tokenize(question)
        if not question_tokens:
            return []
        scored = [(len(question_tokens & item.tokens), item) for item in items]
        scored = [pair for pair in scored if pair[0] > 0]
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [item for _, item in scored]

    def _default_selection(self, items: list[_IndexedItem]) -> list[_IndexedItem]:
        selection: list[_IndexedItem] = []
        for position in ("for", "against", "neutral"):
            match = next(
                (item for item in items if item.family == "argument" and item.position == position),
                None,
            )
            if match:
                selection.append(match)
        timeline_items = [item for item in items if item.family == "timeline"][:2]
        selection.extend(timeline_items)
        return selection[:4]

    def _compose(self, subject: dict, top: list[_IndexedItem]) -> str:
        favorable = [item.excerpt for item in top if item.position == "for" and item.excerpt]
        defavorable = [item.excerpt for item in top if item.position == "against" and item.excerpt]
        neutral = [
            item.excerpt
            for item in top
            if item.family == "argument" and item.position == "neutral" and item.excerpt
        ]
        timeline = [item.excerpt for item in top if item.family == "timeline" and item.excerpt]

        parts = [f"Voici ce que les traces publiques disponibles indiquent sur « {subject.get('title', 'ce sujet')} »."]
        if favorable:
            parts.append("Arguments favorables recensés : " + " ".join(favorable))
        if defavorable:
            parts.append("Arguments défavorables recensés : " + " ".join(defavorable))
        if neutral:
            parts.append("Éléments de clarification : " + " ".join(neutral))
        if timeline:
            parts.append("Repères chronologiques utiles : " + " ".join(timeline))
        if len(parts) == 1:
            parts.append(subject.get("summary") or subject.get("context") or "")
        parts.append(
            "Cette synthèse ne prend pas parti : elle rassemble des positions publiques déjà répertoriées "
            "pour vous aider à vous forger votre propre avis. Consultez les pages liées ci-dessous pour aller plus loin."
        )
        return "\n\n".join(part for part in parts if part)

    def _dedupe_links(self, links: list[AssistantLink]) -> list[AssistantLink]:
        merged: dict[str, AssistantLink] = {}
        order: list[str] = []
        for link in links:
            existing = merged.get(link.url)
            if existing is None:
                merged[link.url] = link
                order.append(link.url)
            elif link.note and link.note not in existing.note:
                merged[link.url] = AssistantLink(
                    label=existing.label,
                    url=existing.url,
                    note=f"{existing.note} · {link.note}" if existing.note else link.note,
                )
        return [merged[url] for url in order]
