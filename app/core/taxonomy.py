from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from app.core.settings import CONFIG_DIR


@dataclass(frozen=True)
class Taxonomy:
    raw: dict[str, Any]

    @property
    def argument_roles(self) -> dict[str, Any]:
        return self.raw.get("argument_roles", {})

    @property
    def categories(self) -> dict[str, Any]:
        return self.raw.get("categories", {})

    @property
    def category_themes(self) -> dict[str, Any]:
        return self.raw.get("category_themes", {})

    @property
    def trace_types(self) -> dict[str, Any]:
        return self.raw.get("trace_types", {})

    @property
    def participation_outputs(self) -> dict[str, Any]:
        return self.raw.get("participation_outputs", {})

    def label(self, section: str, key: str) -> str:
        item = self.raw.get(section, {}).get(key)
        if isinstance(item, dict):
            return str(item.get("label") or key)
        if isinstance(item, str):
            return item
        return key

    def description(self, section: str, key: str) -> str:
        item = self.raw.get(section, {}).get(key)
        if isinstance(item, dict):
            return str(item.get("description") or "")
        return ""

    def category_theme(self, category: str) -> str:
        item = self.categories.get(category)
        if isinstance(item, dict):
            return str(item.get("theme") or "autres")
        return "autres"


def load_taxonomy(path: Path | None = None) -> Taxonomy:
    taxonomy_path = path or CONFIG_DIR / "taxonomy.yml"
    with taxonomy_path.open("r", encoding="utf-8") as f:
        return Taxonomy(raw=yaml.safe_load(f) or {})
