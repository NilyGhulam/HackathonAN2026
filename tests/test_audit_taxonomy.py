import json
from pathlib import Path

from scripts.audit_taxonomy import audit_model, build_model, iter_subject_records, load_rules, run


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_iter_subject_records_prefers_canonical_path():
    payload = {
        "subject_updates": [
            {
                "subject_id": "S1",
                "subject_title": "accord de défense",
                "classification": {
                    "domain_label": "Accord international",
                    "subtheme_label": "Projet de loi",
                    "canonical_path": ["Défense", "Coopération internationale", "Accords de défense"],
                    "confidence": 0.91,
                },
            }
        ]
    }

    records = list(iter_subject_records(payload))

    assert records[0].path == ("Défense", "Coopération internationale", "Accords de défense")
    assert records[0].source_path == ("Accord international", "Projet de loi")
    assert records[0].confidence == 0.91


def test_audit_detects_front_limit_and_repeated_path():
    payload = {
        "subject_updates": [
            {
                "subject_id": f"S{i}",
                "subject_title": f"sujet santé {i}",
                "classification": {
                    "canonical_path": ["Racine", f"Enfant {i}"],
                    "domain_label": "Racine",
                    "subtheme_label": f"Enfant {i}",
                },
            }
            for i in range(13)
        ]
    }
    payload["subject_updates"].append(
        {
            "subject_id": "S-repeat",
            "subject_title": "hôpital santé",
            "classification": {
                "canonical_path": ["Santé", "Santé"],
                "domain_label": "Santé",
                "subtheme_label": "Santé",
            },
        }
    )

    model = build_model(iter_subject_records(payload))
    report = audit_model(model, load_rules(None))
    issue_names = [item["issue"] for item in report["issues"]]

    assert "too_many_children" in issue_names
    assert "repeated_path" in issue_names
    too_many = next(item for item in report["issues"] if item["issue"] == "too_many_children" and item["path"] == ["Racine"])
    assert too_many["child_count"] == 13


def test_audit_detects_large_and_small_leaves():
    payload = {"subject_updates": []}
    for i in range(51):
        payload["subject_updates"].append(
            {
                "subject_id": f"BIG-{i}",
                "subject_title": f"logement social {i}",
                "classification": {"canonical_path": ["Logement", "Logement social"]},
            }
        )
    for i in range(4):
        payload["subject_updates"].append(
            {
                "subject_id": f"SMALL-{i}",
                "subject_title": f"forêt {i}",
                "classification": {"canonical_path": ["Environnement", "Forêts"]},
            }
        )

    report = audit_model(build_model(iter_subject_records(payload)), load_rules(None))

    assert any(item["issue"] == "leaf_too_large" and item["path"] == ["Logement", "Logement social"] for item in report["issues"])
    assert any(item["issue"] == "leaf_too_small" and item["path"] == ["Environnement", "Forêts"] for item in report["issues"])


def test_run_writes_json_and_markdown_reports(tmp_path: Path):
    input_path = tmp_path / "agoria_raw_extract.json"
    rules_path = tmp_path / "rules.json"
    json_out = tmp_path / "taxonomy_audit.json"
    md_out = tmp_path / "taxonomy_audit.md"
    write_json(
        input_path,
        {
            "subject_updates": [
                {
                    "subject_id": "S1",
                    "subject_title": "sécurité routière",
                    "classification": {"canonical_path": ["Sécurité", "Routes"]},
                }
            ]
        },
    )
    write_json(
        rules_path,
        {
            "max_visible_children": 12,
            "target_visible_children_min": 5,
            "target_visible_children_max": 9,
            "preferred_depth": 3,
            "max_depth": 4,
            "ideal_leaf_subject_min": 20,
            "ideal_leaf_subject_max": 40,
            "split_leaf_subject_threshold": 50,
            "merge_leaf_subject_threshold": 5,
        },
    )

    report = run(input_path, rules_path, json_out, md_out)

    assert report["summary"]["subject_count"] == 1
    assert json_out.exists()
    assert md_out.exists()
    assert "# Audit de taxonomie AgorIA" in md_out.read_text(encoding="utf-8")
