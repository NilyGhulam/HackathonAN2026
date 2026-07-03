from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from app.core.models import CivicChannel
from app.core.settings import CONFIG_DIR


class OfficialChannelsRepository:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or CONFIG_DIR / "official_channels.yml"

    def all(self) -> dict[str, Any]:
        with self.path.open("r", encoding="utf-8") as f:
            return (yaml.safe_load(f) or {}).get("channels", {})

    def find_for_output(self, output_type: str) -> list[CivicChannel]:
        channels = []
        for key, item in self.all().items():
            if output_type in item.get("suitable_for", []):
                channels.append(
                    CivicChannel(
                        key=key,
                        label=item.get("label", key),
                        url=item.get("url", "#"),
                        note=item.get("note", ""),
                    )
                )
        return channels
