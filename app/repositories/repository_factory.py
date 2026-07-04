from __future__ import annotations

import os

from app.repositories.demo_repository import DemoRepository
from app.repositories.processed_repository import ProcessedRepository


def create_repository():
    """Choisit la source de données sans modifier le reste de l'application.

    AGORIA_DATA_MODE=demo      -> données fictives uniquement
    AGORIA_DATA_MODE=processed -> data/curated + data/processed si AGORIA_INCLUDE_AUTOMATIC=1
    AGORIA_DATA_MODE=auto      -> données réelles si présentes, sinon démo
    """

    mode = os.getenv("AGORIA_DATA_MODE", "auto").lower()
    include_automatic = os.getenv("AGORIA_INCLUDE_AUTOMATIC", "0") == "1"
    processed = ProcessedRepository(include_automatic=include_automatic)

    if mode == "demo":
        return DemoRepository()
    if mode == "processed":
        return processed
    if processed.has_payloads():
        return processed
    return DemoRepository()
