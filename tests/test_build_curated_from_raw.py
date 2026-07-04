from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "build_curated_from_raw.py"
spec = importlib.util.spec_from_file_location("build_curated_from_raw", SCRIPT_PATH)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def test_build_curated_from_raw_extracts_subject_timeline_and_question(tmp_path: Path) -> None:
    raw_dir = tmp_path / "data" / "raw"
    processed_dir = tmp_path / "data" / "processed"
    curated_dir = tmp_path / "data" / "curated"

    write_json(
        raw_dir / "AMO50_acteurs_mandats_organes_divises.json" / "acteur" / "PA1.json",
        {
            "acteur": {
                "uid": {"#text": "PA1"},
                "etatCivil": {"ident": {"prenom": "Alice", "nom": "Martin", "civ": "Mme"}},
                "profession": {"libelleCourant": "Députée"},
            }
        },
    )
    write_json(
        raw_dir / "AMO50_acteurs_mandats_organes_divises.json" / "organe" / "PO1.json",
        {"organe": {"uid": "PO1", "libelle": "Groupe Exemple", "libelleAbrege": "GE", "codeType": "GP"}},
    )
    write_json(
        raw_dir / "Dossiers_Legislatifs.json" / "json" / "document" / "DOC1.json",
        {
            "document": {
                "uid": "DOC1",
                "legislature": "17",
                "dossierRef": "DL1",
                "denominationStructurelle": "Projet de loi",
                "provenance": "Texte Déposé",
                "cycleDeVie": {"chrono": {"dateDepot": "2026-01-02T00:00:00.000+01:00"}},
                "titres": {"titrePrincipalCourt": "texte court", "titrePrincipal": "Texte complet"},
                "classification": {
                    "type": {"libelle": "Justice"},
                    "sousType": {"libelle": "Système pénitentiaire"},
                },
            }
        },
    )
    write_json(
        raw_dir / "Dossiers_Legislatifs.json" / "json" / "dossierParlementaire" / "DL1.json",
        {
            "dossierParlementaire": {
                "uid": "DL1",
                "legislature": "17",
                "titreDossier": {"titre": "texte court"},
                "procedureParlementaire": {"libelle": "Projet de loi ordinaire"},
                "actesLegislatifs": {
                    "acteLegislatif": {
                        "uid": "ACT1",
                        "@xsi:type": "DepotInitiative_Type",
                        "codeActe": "AN1-DEPOT",
                        "libelleActe": {"libelleCourt": "Dépôt"},
                        "dateActe": "2026-01-02T00:00:00.000+01:00",
                        "texteAssocie": "DOC1",
                    }
                },
            }
        },
    )
    write_json(
        raw_dir / "Questions_gouvernement.json" / "json" / "Q1.json",
        {
            "question": {
                "uid": "Q1",
                "identifiant": {"numero": "1", "legislature": "17"},
                "type": "QG",
                "indexationAN": {"rubrique": "justice", "analyses": {"analyse": "Situation carcérale"}},
                "auteur": {
                    "identite": {"acteurRef": "PA1", "mandatRef": "PM1"},
                    "groupe": {"organeRef": "PO1", "abrege": "GE", "developpe": "Groupe Exemple"},
                },
                "minInt": {"organeRef": "PO2", "developpe": "Ministère de la justice"},
                "textesReponse": {
                    "texteReponse": {
                        "infoJO": {"dateJO": "2026-01-03", "urlLegifrance": "https://example.test/q1"},
                        "texte": "<strong>Mme Alice Martin.</strong> Question ?<br><strong>Le ministre.</strong> Réponse.",
                    }
                },
                "cloture": {"libelleCloture": "Réponse publiée", "dateCloture": "2026-01-03"},
            }
        },
    )

    result = module.build_curated_from_raw(
        raw_dir=raw_dir,
        processed_dir=processed_dir,
        curated_dir=curated_dir,
        curated_status="needs_review",
    )

    assert result["counts"]["actors"] == 1
    assert result["counts"]["documents"] == 1
    assert result["counts"]["dossiers"] == 1
    assert result["counts"]["questions"] == 1
    assert (processed_dir / "normalized_subjects.json").exists()
    assert (processed_dir / "llm_enrichment_queue.json").exists()
    payload = json.loads((curated_dir / "agoria_raw_extract.json").read_text(encoding="utf-8"))
    subject_ids = {item["subject_id"] for item in payload["subject_updates"]}
    assert "DL1" in subject_ids
    assert "question-q1" in subject_ids
    question_subject = next(item for item in payload["subject_updates"] if item["subject_id"] == "question-q1")
    assert question_subject["actors"][0]["name"] == "Alice Martin"
    assert question_subject["timeline_events"][0]["kind"] == "Question au Gouvernement"
    assert payload["extracted_traces"][0]["metadata"]["target_ministry"] == "Ministère de la justice"
