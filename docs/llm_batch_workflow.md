# Enrichissement LLM par lots conversationnels

Ce workflow permet d'enrichir les données parlementaires sans dépendre d'une API LLM en production.

## Principe

```txt
data/raw/
→ scripts/build_curated_from_raw.py
→ data/processed/llm_enrichment_queue.json
→ scripts/export_llm_batch.py
→ lot envoyé dans ChatGPT
→ lot enrichi retourné en JSON
→ scripts/import_llm_batch.py --apply
→ data/curated/agoria_raw_extract.json enrichi
```

L'extraction factuelle reste déterministe. Le LLM ne sert qu'à produire des résumés, tags et classifications.

## Exporter un lot

Questions longues : commencer par 10 entrées.

```bash
./scripts/export_llm_batch.py --only-task summarize_question_and_answer --offset 0 --limit 10 --out llm_batches/batch_001_input.json
```

Classifications de sujets : on peut monter à 30 ou 50 entrées.

```bash
./scripts/export_llm_batch.py --only-task classify_subject --offset 0 --limit 30 --out llm_batches/batch_002_input.json
```

Pour éviter de réexporter ce qui a déjà été importé :

```bash
./scripts/export_llm_batch.py --skip-done --limit 20 --out llm_batches/batch_next_input.json
```

## Format attendu en retour

Le fichier retourné peut contenir une clé `items` ou `enrichments`.
Chaque entrée doit reprendre au minimum `id`, `task`, `source_id` et `output`.

Exemple :

```json
{
  "schema_version": "0.1.0",
  "batch_id": "batch_001",
  "items": [
    {
      "id": "summarize_question:QANR5L17QG1",
      "task": "summarize_question_and_answer",
      "source_id": "QANR5L17QG1",
      "status": "ok",
      "output": {
        "question_summary": "...",
        "answer_summary": "...",
        "issues": ["..."],
        "announced_measures": ["..."],
        "quotes": [],
        "confidence": 0.8,
        "needs_review": true
      }
    }
  ]
}
```

## Importer un lot enrichi

```bash
./scripts/import_llm_batch.py llm_batches/batch_001_output.json --apply
```

Le script :

- valide chaque sortie selon la tâche ;
- met à jour `data/processed/llm_enrichments.json` ;
- sauvegarde une copie `.bak` du payload curated avant fusion ;
- fusionne les résumés/classifications dans `data/curated/agoria_raw_extract.json` avec `--apply`.

## Règles de taxonomie

- Le chemin canonique doit être unique.
- Les catégories doivent être neutres, stables et non partisanes.
- Niveau 1 : grand domaine public.
- Niveau 2 : politique publique ou sous-domaine.
- Niveau 3 : sujet concret.
- Niveau 4 : angle précis, facultatif.
- Les tags servent aux notions transversales ; ils ne remplacent pas le chemin canonique.
- Une nouvelle catégorie ne doit être proposée que si aucune catégorie existante ne convient.
