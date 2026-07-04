#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fnmatch
import os
import zipfile
from datetime import datetime
from pathlib import Path


DEFAULT_EXCLUDES = [
    # Git / Python / caches
    ".git/**",
    "**/__pycache__/**",
    "**/.pytest_cache/**",
    "**/.mypy_cache/**",
    "**/.ruff_cache/**",
    "**/.DS_Store",
    "**/*.pyc",

    # Environnements locaux
    ".venv/**",
    "venv/**",
    "env/**",
    "node_modules/**",

    # Données brutes lourdes
    "data/raw/**",
    "data/raw/**/*",

    # Queues LLM à ne pas distribuer
    "data/processed/llm_enrichment_queue.json",
    "data/processed/actor_quote_queue.json",
    "data/processed/*queue*.json",

    # Batches LLM temporaires
    "llm_batches/**",
    "llm_batches/**/*",

    # Backups / fichiers temporaires
    "**/*.bak",
    "**/*.tmp",
    "**/*~",

    # Archives déjà générées
    "exports/**",
    "exports/**/*",
    "*.zip",
]


DEFAULT_INCLUDE_HINTS = [
    "app/**",
    "config/**",
    "data/curated/**",
    "data/demo/**",
    "data/processed/actor_quotes.json",
    "data/processed/llm_enrichments.json",
    "docs/**",
    "scripts/**",
    "schemas/**",
    "tests/**",
    "requirements.txt",
    "pytest.ini",
    "README.md",
    "Makefile",
]


def normalize_path(path: Path) -> str:
    return path.as_posix()


def matches_any(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def should_exclude(relative_path: str, excludes: list[str]) -> bool:
    parts = relative_path.split("/")

    if any(part.startswith(".") and part not in {".env.example"} for part in parts):
        if not relative_path.startswith(".github/"):
            return True

    return matches_any(relative_path, excludes)


def iter_files(root: Path, excludes: list[str]):
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue

        relative_path = normalize_path(path.relative_to(root))

        if should_exclude(relative_path, excludes):
            continue

        yield path, relative_path


def create_zip(root: Path, output: Path, excludes: list[str]) -> tuple[int, int]:
    output.parent.mkdir(parents=True, exist_ok=True)

    file_count = 0
    total_size = 0

    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path, relative_path in iter_files(root, excludes):
            archive.write(path, relative_path)
            file_count += 1
            total_size += path.stat().st_size

    return file_count, total_size


def human_size(size: int) -> str:
    units = ["o", "Ko", "Mo", "Go"]
    value = float(size)

    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}"
        value /= 1024

    return f"{size} o"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Exporte une archive ZIP propre du projet, sans raw data ni queues LLM."
    )

    parser.add_argument(
        "--root",
        default=".",
        help="Racine du projet à exporter. Défaut : dossier courant.",
    )

    parser.add_argument(
        "--out",
        default=None,
        help="Chemin du ZIP de sortie. Défaut : exports/agoria_clean_<timestamp>.zip",
    )

    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="Pattern d'exclusion supplémentaire. Peut être utilisé plusieurs fois.",
    )

    parser.add_argument(
        "--include-llm-batches",
        action="store_true",
        help="Inclut llm_batches/ malgré l'exclusion par défaut.",
    )

    parser.add_argument(
        "--include-queues",
        action="store_true",
        help="Inclut les queues LLM malgré l'exclusion par défaut.",
    )

    args = parser.parse_args()

    root = Path(args.root).resolve()

    if not root.exists():
        raise SystemExit(f"Racine introuvable : {root}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    output = (
        Path(args.out).resolve()
        if args.out
        else root / "exports" / f"agoria_clean_{timestamp}.zip"
    )

    excludes = list(DEFAULT_EXCLUDES)

    if args.include_llm_batches:
        excludes = [
            pattern
            for pattern in excludes
            if not pattern.startswith("llm_batches/")
        ]

    if args.include_queues:
        excludes = [
            pattern
            for pattern in excludes
            if "queue" not in pattern
        ]

    excludes.extend(args.exclude)

    file_count, total_size = create_zip(root, output, excludes)

    print(f"Archive créée : {output}")
    print(f"Fichiers inclus : {file_count}")
    print(f"Taille source incluse : {human_size(total_size)}")


if __name__ == "__main__":
    main()
