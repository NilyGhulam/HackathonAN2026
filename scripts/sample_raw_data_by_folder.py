#!/usr/bin/env python3
"""Analyse data/raw et extrait un seul échantillon par dossier de fichiers.

Usage depuis la racine du projet :
    python scripts/sample_raw_data.py

Ou en indiquant explicitement les chemins :
    python scripts/sample_raw_data.py --raw-dir data/raw --out-dir data/samples/raw_samples

Règle d'échantillonnage :
- le script parcourt toute la hiérarchie de data/raw ;
- pour chaque dossier qui contient des fichiers JSON, il prend uniquement le premier fichier JSON ;
- dans ce premier fichier JSON, il extrait une seule entrée logique ;
- il conserve le nom du dossier, le chemin du fichier choisi et les fichiers ignorés dans manifest.json ;
- il génère une archive raw_samples.zip prête à envoyer.

Le script est volontairement autonome et ne dépend pas de l'application.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

DEFAULT_MAX_STRING = 2500
DEFAULT_MAX_LIST_ITEMS = 3
DEFAULT_MAX_DICT_KEYS = 80
JSON_SUFFIXES = {".json"}


@dataclass
class FolderSampleReport:
    relative_dir: str
    json_file_count: int
    sampled_file: str | None
    sample_file: str | None
    status: str
    inferred_entry_path: str | None = None
    top_level_type: str | None = None
    top_level_keys: list[str] | None = None
    ignored_files_preview: list[str] | None = None
    ignored_files_count: int = 0
    error: str | None = None


def truncate(value: Any, max_string: int, max_list_items: int, max_dict_keys: int) -> Any:
    """Réduit les valeurs trop grosses tout en gardant leur structure."""
    if isinstance(value, str):
        if len(value) <= max_string:
            return value
        return value[:max_string] + f"… [truncated {len(value) - max_string} chars]"

    if isinstance(value, list):
        result = [truncate(item, max_string, max_list_items, max_dict_keys) for item in value[:max_list_items]]
        if len(value) > max_list_items:
            result.append({"__truncated_items__": len(value) - max_list_items})
        return result

    if isinstance(value, dict):
        result: dict[str, Any] = {}
        items = list(value.items())
        for key, item in items[:max_dict_keys]:
            result[str(key)] = truncate(item, max_string, max_list_items, max_dict_keys)
        if len(items) > max_dict_keys:
            result["__truncated_keys__"] = len(items) - max_dict_keys
        return result

    return value


def find_first_logical_entry(value: Any, path: str = "$") -> tuple[str, Any]:
    """Trouve une seule entrée utile dans une structure JSON.

    Cas typiques :
    - {"document": {...}} : on garde l'objet wrapper entier ;
    - {"dossierParlementaire": {...}} : idem ;
    - {"question": {...}} : idem ;
    - gros JSON composite avec listes : on descend jusqu'à la première liste non vide ;
    - liste racine : on prend le premier élément.
    """
    if isinstance(value, dict):
        known_wrappers = {
            "document",
            "dossierParlementaire",
            "question",
            "acteur",
            "organe",
            "mandat",
            "amendement",
            "scrutin",
        }
        if any(key in value for key in known_wrappers):
            return path, value

        for key, child in value.items():
            if isinstance(child, list) and child:
                return f"{path}.{key}[0]", child[0]
            if isinstance(child, dict):
                child_path, child_entry = find_first_logical_entry(child, f"{path}.{key}")
                if child_path != f"{path}.{key}":
                    return child_path, child_entry

    if isinstance(value, list) and value:
        return f"{path}[0]", value[0]

    return path, value


def read_json_sample(path: Path, raw_dir: Path, max_string: int, max_list_items: int, max_dict_keys: int) -> tuple[dict[str, Any], str, str, list[str] | None]:
    with path.open("r", encoding="utf-8-sig") as f:
        value = json.load(f)

    entry_path, entry = find_first_logical_entry(value)
    top_level_keys = list(value.keys()) if isinstance(value, dict) else None
    sample = {
        "source_file": str(path.relative_to(raw_dir)),
        "format": "json",
        "top_level_type": type(value).__name__,
        "top_level_keys": top_level_keys,
        "inferred_entry_path": entry_path,
        "sample": truncate(entry, max_string, max_list_items, max_dict_keys),
    }
    return sample, entry_path, type(value).__name__, top_level_keys


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def make_tree(raw_dir: Path, max_files_per_dir: int = 20) -> str:
    """Produit une arborescence compacte avec comptage des JSON par dossier."""
    lines: list[str] = [str(raw_dir)]
    for root, dirs, files in os.walk(raw_dir):
        dirs.sort()
        files.sort()
        root_path = Path(root)
        rel_root = root_path.relative_to(raw_dir)
        depth = 0 if str(rel_root) == "." else len(rel_root.parts)
        indent = "  " * depth
        json_count = sum(1 for f in files if (root_path / f).suffix.lower() in JSON_SUFFIXES)
        if str(rel_root) != ".":
            lines.append(f"{indent}📁 {rel_root}/ — {json_count} JSON")
        else:
            lines.append(f"{indent}📁 ./ — {json_count} JSON")

        visible_files = files[:max_files_per_dir]
        for f in visible_files:
            p = root_path / f
            size = p.stat().st_size
            marker = " [json]" if p.suffix.lower() in JSON_SUFFIXES else ""
            lines.append(f"{indent}  ├── {f} ({size} bytes){marker}")
        if len(files) > max_files_per_dir:
            lines.append(f"{indent}  └── … {len(files) - max_files_per_dir} fichiers masqués")
    return "\n".join(lines) + "\n"


def safe_sample_path(relative_dir: Path, sampled_file: Path) -> Path:
    """Chemin d'échantillon qui conserve le dossier source sans créer 10 000 fichiers."""
    if str(relative_dir) == ".":
        return Path("root.sample.json")
    folder_name = "__".join(relative_dir.parts)
    return Path(folder_name) / (sampled_file.name + ".sample.json")


def zip_directory(source_dir: Path, zip_path: Path) -> None:
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in source_dir.rglob("*"):
            if path == zip_path or path.is_dir():
                continue
            zf.write(path, path.relative_to(source_dir))


def iter_dirs_with_json(raw_dir: Path) -> list[tuple[Path, list[Path]]]:
    """Retourne chaque dossier contenant au moins un JSON direct, avec ses fichiers JSON directs.

    Important : un dossier parent qui ne contient que des sous-dossiers JSON n'est pas échantillonné.
    Exemple : raw/A/B/10000 fichiers JSON => seul raw/A/B produit un échantillon.
    """
    result: list[tuple[Path, list[Path]]] = []
    for root, dirs, files in os.walk(raw_dir):
        dirs.sort()
        root_path = Path(root)
        json_files = sorted(
            root_path / f
            for f in files
            if (root_path / f).is_file() and (root_path / f).suffix.lower() in JSON_SUFFIXES
        )
        if json_files:
            result.append((root_path, json_files))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Échantillonne un JSON par dossier de data/raw pour analyse de schéma.")
    parser.add_argument("--raw-dir", default="data/raw", help="Dossier source à analyser")
    parser.add_argument("--out-dir", default="data/samples/raw_samples", help="Dossier de sortie")
    parser.add_argument("--max-string", type=int, default=DEFAULT_MAX_STRING, help="Longueur max des chaînes dans les échantillons")
    parser.add_argument("--max-list-items", type=int, default=DEFAULT_MAX_LIST_ITEMS, help="Nombre max d'items conservés dans les listes")
    parser.add_argument("--max-dict-keys", type=int, default=DEFAULT_MAX_DICT_KEYS, help="Nombre max de clés conservées dans les objets")
    args = parser.parse_args()

    raw_dir = Path(args.raw_dir)
    out_dir = Path(args.out_dir)

    if not raw_dir.exists() or not raw_dir.is_dir():
        print(f"Erreur : dossier introuvable : {raw_dir}", file=sys.stderr)
        return 1

    if out_dir.exists():
        shutil.rmtree(out_dir)
    samples_dir = out_dir / "samples"
    samples_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "tree.txt").write_text(make_tree(raw_dir), encoding="utf-8")

    reports: list[FolderSampleReport] = []
    dirs_with_json = iter_dirs_with_json(raw_dir)

    for folder, json_files in dirs_with_json:
        relative_dir = folder.relative_to(raw_dir)
        first_file = json_files[0]
        sample_relative = safe_sample_path(relative_dir, first_file)
        sample_path = samples_dir / sample_relative
        ignored = [str(p.relative_to(raw_dir)) for p in json_files[1:]]

        report = FolderSampleReport(
            relative_dir=str(relative_dir),
            json_file_count=len(json_files),
            sampled_file=str(first_file.relative_to(raw_dir)),
            sample_file=str(sample_path.relative_to(out_dir)),
            status="pending",
            ignored_files_preview=ignored[:20],
            ignored_files_count=len(ignored),
        )

        try:
            sample, entry_path, top_type, top_keys = read_json_sample(
                first_file,
                raw_dir,
                args.max_string,
                args.max_list_items,
                args.max_dict_keys,
            )
            sample["sampling_rule"] = "one_first_json_file_per_directory"
            sample["source_directory"] = str(relative_dir)
            sample["directory_json_file_count"] = len(json_files)
            sample["ignored_json_files_count"] = len(ignored)
            sample["ignored_json_files_preview"] = ignored[:20]
            write_json(sample_path, sample)
            report.status = "sampled"
            report.inferred_entry_path = entry_path
            report.top_level_type = top_type
            report.top_level_keys = top_keys
        except Exception as exc:  # volontairement large : on veut un rapport complet
            report.status = "error"
            report.error = f"{type(exc).__name__}: {exc}"

        reports.append(report)

    manifest = {
        "raw_dir": str(raw_dir),
        "out_dir": str(out_dir),
        "sampling_rule": "one_first_json_file_per_directory",
        "directories_with_json": len(reports),
        "sampled_directories": sum(1 for r in reports if r.status == "sampled"),
        "error_directories": sum(1 for r in reports if r.status == "error"),
        "total_json_files_seen": sum(r.json_file_count for r in reports),
        "total_json_files_ignored_by_sampling_rule": sum(r.ignored_files_count for r in reports),
        "folders": [asdict(r) for r in reports],
    }
    write_json(out_dir / "manifest.json", manifest)

    zip_path = out_dir / "raw_samples.zip"
    zip_directory(out_dir, zip_path)

    print(f"OK — {manifest['sampled_directories']} dossiers échantillonnés sur {manifest['directories_with_json']} dossiers contenant des JSON.")
    print(f"JSON vus : {manifest['total_json_files_seen']} ; ignorés par règle d'échantillonnage : {manifest['total_json_files_ignored_by_sampling_rule']}.")
    print(f"Rapport : {out_dir / 'manifest.json'}")
    print(f"Arborescence : {out_dir / 'tree.txt'}")
    print(f"Archive à envoyer : {zip_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
