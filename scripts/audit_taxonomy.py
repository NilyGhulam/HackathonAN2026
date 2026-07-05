#!/usr/bin/env python3
"""Deterministic taxonomy audit for AgorIA processed/curated data.

This script is intentionally read-only for input data. It builds a category tree
from the current processed payload, checks front-end display constraints, and
emits both machine-readable JSON and a human-readable Markdown report.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from statistics import median
from typing import Any, Iterable

DEFAULT_RULES: dict[str, int] = {
    "max_visible_children": 12,
    "target_visible_children_min": 5,
    "target_visible_children_max": 9,
    "preferred_depth": 3,
    "max_depth": 4,
    "ideal_leaf_subject_min": 20,
    "ideal_leaf_subject_max": 40,
    "split_leaf_subject_threshold": 50,
    "merge_leaf_subject_threshold": 5,
}

VAGUE_LABELS = {
    "autre",
    "autres",
    "divers",
    "diverse",
    "diverses",
    "general",
    "generale",
    "generales",
    "generalite",
    "generalites",
    "tel quel",
    "non classe",
    "non classee",
    "sans categorie",
    "a classer",
    "misc",
    "miscellaneous",
}

STOPWORDS = {
    "a",
    "au",
    "aux",
    "avec",
    "ce",
    "ces",
    "cet",
    "cette",
    "dans",
    "de",
    "des",
    "du",
    "en",
    "et",
    "la",
    "le",
    "les",
    "leur",
    "leurs",
    "l",
    "d",
    "un",
    "une",
    "par",
    "pour",
    "sur",
    "sous",
    "ou",
    "the",
    "of",
    "and",
    "to",
    "loi",
    "projet",
    "proposition",
    "rapport",
    "information",
    "resolution",
    "relative",
    "relatif",
    "visant",
    "portant",
    "tendant",
}


@dataclass(frozen=True)
class SubjectRecord:
    subject_id: str
    title: str
    path: tuple[str, ...]
    source_path: tuple[str, ...] = ()
    confidence: float | None = None


@dataclass
class TaxonomyModel:
    subjects: dict[str, SubjectRecord] = field(default_factory=dict)
    leaf_subjects: dict[tuple[str, ...], dict[str, SubjectRecord]] = field(
        default_factory=lambda: defaultdict(dict)
    )
    children: dict[tuple[str, ...], set[str]] = field(
        default_factory=lambda: defaultdict(set)
    )
    category_paths: set[tuple[str, ...]] = field(default_factory=set)

    def add_subject(self, record: SubjectRecord) -> None:
        if not record.path:
            return
        self.subjects[record.subject_id] = record
        self.leaf_subjects[record.path][record.subject_id] = record
        for depth in range(1, len(record.path) + 1):
            current = record.path[:depth]
            parent = record.path[: depth - 1]
            self.category_paths.add(current)
            self.children[parent].add(record.path[depth - 1])

    def child_path(self, parent: tuple[str, ...], child: str) -> tuple[str, ...]:
        return parent + (child,)

    def leaf_paths(self) -> list[tuple[str, ...]]:
        return sorted(
            path for path in self.category_paths if not self.children.get(path)
        )


def strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def normalize_label(value: str) -> str:
    value = strip_accents(value).lower().strip()
    value = re.sub(r"[’'`´]", " ", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def label_tokens(value: str) -> set[str]:
    return {tok for tok in normalize_label(value).split() if len(tok) > 2 and tok not in STOPWORDS}


def path_tokens(path: Iterable[str]) -> set[str]:
    tokens: set[str] = set()
    for label in path:
        tokens.update(label_tokens(label))
    return tokens


def token_overlap(left: Iterable[str], right: Iterable[str]) -> float:
    left_tokens = path_tokens(left)
    right_tokens = path_tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def clean_path(path: Iterable[Any]) -> tuple[str, ...]:
    cleaned = []
    for item in path:
        if item is None:
            continue
        label = str(item).strip()
        if label:
            cleaned.append(label)
    return tuple(cleaned)


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_rules(path: Path | None) -> dict[str, int]:
    rules = dict(DEFAULT_RULES)
    if path and path.exists():
        loaded = load_json(path)
        if not isinstance(loaded, dict):
            raise ValueError(f"Rules file must contain a JSON object: {path}")
        for key, value in loaded.items():
            if key in DEFAULT_RULES:
                rules[key] = int(value)
    return rules


def iter_subject_records(data: Any) -> Iterable[SubjectRecord]:
    """Extract subject/category records from supported AgorIA payloads.

    Supported inputs:
    - data/curated/agoria_raw_extract.json via subject_updates[].classification
    - data/processed/normalized_subjects.json via items[].taxonomy
    - fallback data/curated taxonomy_links[] for older exports
    """

    if not isinstance(data, dict):
        raise ValueError("Input JSON must be an object.")

    if isinstance(data.get("subject_updates"), list):
        for item in data["subject_updates"]:
            if not isinstance(item, dict):
                continue
            classification = item.get("classification") or {}
            if not isinstance(classification, dict):
                classification = {}
            path = clean_path(
                classification.get("canonical_path")
                or [classification.get("domain_label"), classification.get("subtheme_label")]
            )
            source_path = clean_path(
                [classification.get("domain_label"), classification.get("subtheme_label")]
            )
            subject_id = str(item.get("subject_id") or item.get("id") or item.get("subject_title") or "").strip()
            if not subject_id or not path:
                continue
            yield SubjectRecord(
                subject_id=subject_id,
                title=str(item.get("subject_title") or item.get("title") or ""),
                path=path,
                source_path=source_path,
                confidence=_optional_float(classification.get("confidence")),
            )
        return

    if isinstance(data.get("items"), list):
        for item in data["items"]:
            if not isinstance(item, dict):
                continue
            taxonomy = item.get("taxonomy") or {}
            if not isinstance(taxonomy, dict):
                taxonomy = {}
            path = clean_path(
                taxonomy.get("canonical_path")
                or [taxonomy.get("domain_label"), taxonomy.get("subtheme_label")]
            )
            source_path = clean_path([taxonomy.get("domain_label"), taxonomy.get("subtheme_label")])
            subject_id = str(item.get("id") or item.get("subject_id") or item.get("title") or "").strip()
            if not subject_id or not path:
                continue
            yield SubjectRecord(
                subject_id=subject_id,
                title=str(item.get("title") or item.get("subject_title") or ""),
                path=path,
                source_path=source_path,
                confidence=_optional_float(taxonomy.get("confidence")),
            )
        return

    if isinstance(data.get("taxonomy_links"), list):
        for item in data["taxonomy_links"]:
            if not isinstance(item, dict):
                continue
            path = clean_path([item.get("domain_label"), item.get("subtheme_label")])
            subject_id = str(item.get("subject_id") or item.get("subject_title") or "").strip()
            if not subject_id or not path:
                continue
            yield SubjectRecord(
                subject_id=subject_id,
                title=str(item.get("subject_title") or ""),
                path=path,
                source_path=path,
                confidence=_optional_float(item.get("confidence")),
            )
        return

    raise ValueError(
        "Unsupported input format. Expected subject_updates, items, or taxonomy_links."
    )


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def build_model(records: Iterable[SubjectRecord]) -> TaxonomyModel:
    model = TaxonomyModel()
    for record in records:
        model.add_subject(record)
    return model


def issue(
    severity: str,
    issue_name: str,
    path: tuple[str, ...],
    recommendation: str,
    *,
    subject_count: int | None = None,
    child_count: int | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "severity": severity,
        "issue": issue_name,
        "path": list(path),
        "recommendation": recommendation,
    }
    if subject_count is not None:
        payload["subject_count"] = subject_count
    if child_count is not None:
        payload["child_count"] = child_count
    if details:
        payload["details"] = details
    return payload


def audit_model(model: TaxonomyModel, rules: dict[str, int]) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    max_children = rules["max_visible_children"]
    split_threshold = rules["split_leaf_subject_threshold"]
    merge_threshold = rules["merge_leaf_subject_threshold"]
    max_depth = rules["max_depth"]

    # 1. Categories with too many direct children, including the root circle.
    for path, children in sorted(model.children.items(), key=lambda kv: (len(kv[0]), kv[0])):
        child_count = len(children)
        if child_count > max_children:
            issues.append(
                issue(
                    "error",
                    "too_many_children",
                    path,
                    "split",
                    child_count=child_count,
                    subject_count=count_subjects_under(model, path),
                    details={
                        "limit": max_children,
                        "sample_children": sorted(children)[:20],
                    },
                )
            )

    # 2/3. Leaf size checks.
    for path in model.leaf_paths():
        count = len(model.leaf_subjects.get(path, {}))
        if count > split_threshold:
            issues.append(
                issue(
                    "error",
                    "leaf_too_large",
                    path,
                    "split",
                    subject_count=count,
                    child_count=0,
                    details={"threshold": split_threshold},
                )
            )
        elif 0 < count < merge_threshold:
            issues.append(
                issue(
                    "warning",
                    "leaf_too_small",
                    path,
                    "merge",
                    subject_count=count,
                    child_count=0,
                    details={"threshold": merge_threshold},
                )
            )

    # 4. Excessive depth.
    for path in sorted(model.category_paths, key=lambda p: (len(p), p)):
        if len(path) > max_depth:
            issues.append(
                issue(
                    "error",
                    "depth_too_deep",
                    path,
                    "review",
                    subject_count=count_subjects_under(model, path),
                    child_count=len(model.children.get(path, set())),
                    details={"max_depth": max_depth, "depth": len(path)},
                )
            )

    # 5. Absurd/repetitive paths.
    for path in sorted(model.category_paths, key=lambda p: (len(p), p)):
        normalized = [normalize_label(part) for part in path]
        repeated_adjacent = any(
            normalized[idx] and normalized[idx] == normalized[idx - 1]
            for idx in range(1, len(normalized))
        )
        repeated_anywhere = len([p for p in normalized if p]) != len(set(p for p in normalized if p))
        if repeated_adjacent or repeated_anywhere:
            issues.append(
                issue(
                    "warning",
                    "repeated_path",
                    path,
                    "rename",
                    subject_count=count_subjects_under(model, path),
                    child_count=len(model.children.get(path, set())),
                )
            )

    # 6. Vague labels.
    for path in sorted(model.category_paths, key=lambda p: (len(p), p)):
        for label in path:
            if normalize_label(label) in VAGUE_LABELS:
                issues.append(
                    issue(
                        "warning",
                        "vague_label",
                        path,
                        "rename",
                        subject_count=count_subjects_under(model, path),
                        child_count=len(model.children.get(path, set())),
                        details={"label": label},
                    )
                )
                break

    # 7. Exact and quasi-exact duplicated labels.
    issues.extend(audit_duplicate_labels(model))

    # 8. Categories with apparently incoherent subjects.
    issues.extend(audit_subject_coherence(model))

    # 9. Unbalanced branches.
    issues.extend(audit_unbalanced_branches(model, rules))

    # 10. Source rubrique vs final category mismatch.
    issues.extend(audit_source_mismatches(model))

    issues = sorted(
        issues,
        key=lambda item: (
            0 if item["severity"] == "error" else 1,
            item["issue"],
            item.get("path", []),
        ),
    )
    error_count = sum(1 for item in issues if item["severity"] == "error")
    warning_count = sum(1 for item in issues if item["severity"] == "warning")
    return {
        "summary": {
            "category_count": len(model.category_paths),
            "leaf_count": len(model.leaf_paths()),
            "subject_count": len(model.subjects),
            "error_count": error_count,
            "warning_count": warning_count,
        },
        "rules": rules,
        "issues": issues,
    }


def count_subjects_under(model: TaxonomyModel, path: tuple[str, ...]) -> int:
    if not path:
        return len(model.subjects)
    subject_ids: set[str] = set()
    for leaf_path, subjects in model.leaf_subjects.items():
        if leaf_path[: len(path)] == path:
            subject_ids.update(subjects)
    return len(subject_ids)


def audit_duplicate_labels(model: TaxonomyModel) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    by_normalized: dict[str, list[tuple[str, ...]]] = defaultdict(list)
    label_by_normalized: dict[str, str] = {}
    for path in model.category_paths:
        norm = normalize_label(path[-1])
        if not norm:
            continue
        by_normalized[norm].append(path)
        label_by_normalized.setdefault(norm, path[-1])

    for norm, paths in sorted(by_normalized.items()):
        unique_paths = sorted(set(paths), key=lambda p: (len(p), p))
        if len(unique_paths) > 1:
            for path in unique_paths:
                issues.append(
                    issue(
                        "warning",
                        "duplicate_label",
                        path,
                        "review",
                        subject_count=count_subjects_under(model, path),
                        child_count=len(model.children.get(path, set())),
                        details={
                            "normalized_label": norm,
                            "duplicate_paths": [list(p) for p in unique_paths[:10]],
                        },
                    )
                )

    norms = sorted(by_normalized)
    seen_pairs: set[tuple[str, str]] = set()
    for idx, left in enumerate(norms):
        if len(left) < 5:
            continue
        for right in norms[idx + 1 :]:
            if len(right) < 5:
                continue
            if abs(len(left) - len(right)) > 6:
                continue
            ratio = SequenceMatcher(None, left, right).ratio()
            if ratio < 0.92:
                continue
            pair = (left, right)
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            left_paths = sorted(set(by_normalized[left]), key=lambda p: (len(p), p))
            right_paths = sorted(set(by_normalized[right]), key=lambda p: (len(p), p))
            for path in (left_paths + right_paths)[:10]:
                issues.append(
                    issue(
                        "warning",
                        "near_duplicate_label",
                        path,
                        "review",
                        subject_count=count_subjects_under(model, path),
                        child_count=len(model.children.get(path, set())),
                        details={
                            "labels": [label_by_normalized[left], label_by_normalized[right]],
                            "similarity": round(ratio, 3),
                            "paths": [list(p) for p in (left_paths + right_paths)[:10]],
                        },
                    )
                )
    return issues


def audit_subject_coherence(model: TaxonomyModel) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for path in model.leaf_paths():
        records = list(model.leaf_subjects.get(path, {}).values())
        if len(records) < 5:
            continue
        category_tokens = path_tokens(path)
        if not category_tokens:
            continue
        scores = []
        weak_examples = []
        for record in records:
            title_tokens = label_tokens(record.title)
            if not title_tokens:
                continue
            score = len(category_tokens & title_tokens) / max(1, len(category_tokens))
            scores.append(score)
            if score == 0 and len(weak_examples) < 5:
                weak_examples.append({"id": record.subject_id, "title": record.title[:180]})
        if len(scores) < 5:
            continue
        avg_score = sum(scores) / len(scores)
        zero_ratio = sum(1 for score in scores if score == 0) / len(scores)
        if avg_score < 0.08 and zero_ratio >= 0.7:
            issues.append(
                issue(
                    "warning",
                    "category_subject_mismatch",
                    path,
                    "review",
                    subject_count=len(records),
                    child_count=0,
                    details={
                        "average_label_title_overlap": round(avg_score, 3),
                        "zero_overlap_ratio": round(zero_ratio, 3),
                        "examples": weak_examples,
                    },
                )
            )
    return issues


def audit_unbalanced_branches(model: TaxonomyModel, rules: dict[str, int]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    split_threshold = rules["split_leaf_subject_threshold"]
    for path, children in sorted(model.children.items(), key=lambda kv: (len(kv[0]), kv[0])):
        if len(children) < 2:
            continue
        counts = []
        for child in children:
            child_path = model.child_path(path, child)
            counts.append((child, count_subjects_under(model, child_path)))
        values = [count for _, count in counts if count > 0]
        if len(values) < 2:
            continue
        med = median(values)
        max_child, max_count = max(counts, key=lambda item: item[1])
        if med <= 0:
            continue
        ratio = max_count / med
        if max_count >= split_threshold and ratio >= 3:
            issues.append(
                issue(
                    "warning",
                    "branch_unbalanced",
                    path,
                    "review",
                    subject_count=count_subjects_under(model, path),
                    child_count=len(children),
                    details={
                        "largest_child": max_child,
                        "largest_child_subject_count": max_count,
                        "median_child_subject_count": med,
                        "imbalance_ratio": round(ratio, 2),
                        "top_children": [
                            {"label": label, "subject_count": count}
                            for label, count in sorted(counts, key=lambda item: item[1], reverse=True)[:10]
                        ],
                    },
                )
            )
    return issues


def audit_source_mismatches(model: TaxonomyModel) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for path in model.leaf_paths():
        records = [r for r in model.leaf_subjects.get(path, {}).values() if r.source_path]
        if len(records) < 5:
            continue
        mismatches = []
        source_counter: Counter[tuple[str, ...]] = Counter()
        for record in records:
            source_counter[record.source_path] += 1
            score = token_overlap(record.source_path, path)
            if score < 0.12:
                mismatches.append(record)
        ratio = len(mismatches) / len(records)
        if ratio >= 0.75:
            issues.append(
                issue(
                    "warning",
                    "source_category_mismatch",
                    path,
                    "review",
                    subject_count=len(records),
                    child_count=0,
                    details={
                        "mismatch_ratio": round(ratio, 3),
                        "top_source_paths": [
                            {"path": list(source_path), "subject_count": count}
                            for source_path, count in source_counter.most_common(5)
                        ],
                    },
                )
            )
    return issues


def write_json_report(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
        f.write("\n")


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    issues = report["issues"]
    by_issue = Counter(item["issue"] for item in issues)
    errors = [item for item in issues if item["severity"] == "error"]
    warnings = [item for item in issues if item["severity"] == "warning"]

    lines = [
        "# Audit de taxonomie AgorIA",
        "",
        "## Résumé",
        "",
        f"- Catégories : **{summary['category_count']}**",
        f"- Feuilles : **{summary['leaf_count']}**",
        f"- Sujets : **{summary['subject_count']}**",
        f"- Erreurs : **{summary['error_count']}**",
        f"- Avertissements : **{summary['warning_count']}**",
        "",
        "## Répartition des problèmes",
        "",
    ]
    if by_issue:
        for name, count in by_issue.most_common():
            lines.append(f"- `{name}` : {count}")
    else:
        lines.append("- Aucun problème détecté.")

    lines.extend(["", "## Problèmes bloquants", ""])
    if errors:
        lines.extend(render_issue_table(errors[:80]))
        if len(errors) > 80:
            lines.append(f"\n_{len(errors) - 80} autres erreurs dans le JSON._")
    else:
        lines.append("Aucun problème bloquant détecté.")

    lines.extend(["", "## Avertissements principaux", ""])
    if warnings:
        lines.extend(render_issue_table(warnings[:120]))
        if len(warnings) > 120:
            lines.append(f"\n_{len(warnings) - 120} autres avertissements dans le JSON._")
    else:
        lines.append("Aucun avertissement détecté.")

    lines.extend(
        [
            "",
            "## Recommandations de lecture",
            "",
            "- `too_many_children` : réduire le nombre d’enfants directs pour respecter la limite front de 12.",
            "- `leaf_too_large` : diviser la feuille, car elle agrège trop de sujets.",
            "- `leaf_too_small` : envisager une fusion avec une catégorie voisine.",
            "- `repeated_path` et `vague_label` : renommer ou remapper en priorité, car ces problèmes nuisent directement à la lisibilité.",
            "- `source_category_mismatch` et `category_subject_mismatch` : à relire humainement avant remapping automatique.",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def render_issue_table(issues: list[dict[str, Any]]) -> list[str]:
    lines = ["| Sévérité | Problème | Chemin | Sujets | Enfants | Recommandation |", "|---|---|---|---:|---:|---|"]
    for item in issues:
        path = " > ".join(item.get("path") or ["<racine>"])
        lines.append(
            "| {severity} | `{issue}` | {path} | {subjects} | {children} | {recommendation} |".format(
                severity=item.get("severity", ""),
                issue=item.get("issue", ""),
                path=escape_md(path),
                subjects=item.get("subject_count", ""),
                children=item.get("child_count", ""),
                recommendation=item.get("recommendation", ""),
            )
        )
    return lines


def escape_md(value: str) -> str:
    return value.replace("|", "\\|")


def write_markdown_report(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_markdown(report), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit AgorIA taxonomy consistency without modifying source data.")
    parser.add_argument("--input", required=True, type=Path, help="Input JSON file: curated extract or normalized subjects.")
    parser.add_argument("--rules", type=Path, default=Path("config/taxonomy_rules.json"), help="Rules JSON file.")
    parser.add_argument("--json-out", required=True, type=Path, help="Output JSON report path.")
    parser.add_argument("--md-out", required=True, type=Path, help="Output Markdown report path.")
    parser.add_argument("--fail-on-error", action="store_true", help="Exit with code 2 when blocking errors are found.")
    return parser.parse_args()


def run(input_path: Path, rules_path: Path | None, json_out: Path, md_out: Path) -> dict[str, Any]:
    data = load_json(input_path)
    rules = load_rules(rules_path)
    model = build_model(iter_subject_records(data))
    report = audit_model(model, rules)
    write_json_report(report, json_out)
    write_markdown_report(report, md_out)
    return report


def main() -> int:
    args = parse_args()
    report = run(args.input, args.rules, args.json_out, args.md_out)
    summary = report["summary"]
    print(
        "Audit taxonomy: "
        f"{summary['category_count']} categories, "
        f"{summary['leaf_count']} leaves, "
        f"{summary['subject_count']} subjects, "
        f"{summary['error_count']} errors, "
        f"{summary['warning_count']} warnings."
    )
    if args.fail_on_error and summary["error_count"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
