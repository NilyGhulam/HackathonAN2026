# Extraction des citations et positions d'acteurs

Cette brique ajoute une couche utile à la carte des acteurs : elle extrait des citations littérales, les rattache à un acteur, puis les regroupe en positions argumentées sur un sujet.

## Objectif

Produire des objets de ce type :

```json
{
  "actor_id": "PA123456",
  "subject_id": "question-qanr5l17qg1012",
  "stance": "alerte",
  "argument_summary": "L'acteur alerte sur l'insuffisance des moyens.",
  "quote": "Citation exacte issue du texte source.",
  "source_id": "QANR5L17QG1012"
}
```

La citation doit être exacte. Le résumé d'argument peut être synthétique.

## Workflow

```txt
data/processed/normalized_questions.json
→ scripts/build_actor_quote_queue.py
→ data/processed/actor_quote_queue.json
→ scripts/export_actor_quote_batch.py
→ lot envoyé dans ChatGPT
→ lot enrichi retourné en JSON
→ scripts/import_actor_quote_batch.py --apply
→ data/processed/actor_quotes.json
→ data/curated/agoria_raw_extract.json enrichi avec quotes et actor_positions
```

## 1. Construire la queue

Pour toutes les questions normalisées :

```bash
./scripts/build_actor_quote_queue.py
```

Pour limiter aux questions qui ont déjà un résumé LLM importé :

```bash
./scripts/build_actor_quote_queue.py --only-enriched-summaries
```

Pour tester sur un petit volume :

```bash
./scripts/build_actor_quote_queue.py --limit 20
```

## 2. Exporter un batch conversationnel

```bash
./scripts/export_actor_quote_batch.py \
  --skip-done \
  --limit 20 \
  --out llm_batches/actor_quotes_001_input.json
```

Taille conseillée :

- 10 items pour calibrer ;
- 20 items pour un lot normal ;
- 30 items maximum si les textes sont courts.

## 3. Importer le batch enrichi

```bash
./scripts/import_actor_quote_batch.py \
  llm_batches/actor_quotes_001_output.json \
  --apply
```

L'import écrit :

```txt
data/processed/actor_quotes.json
data/curated/agoria_raw_extract.json
```

Une sauvegarde `.bak` du payload curated est créée lors d'un import en place.

## Format de sortie attendu

```json
{
  "items": [
    {
      "id": "extract_actor_quotes:QANR5L17QG1012",
      "task": "extract_actor_quotes",
      "source_id": "QANR5L17QG1012",
      "subject_id": "question-qanr5l17qg1012",
      "status": "ok",
      "output": {
        "quotes": [
          {
            "segment_id": "question",
            "actor_id": "PA123456",
            "actor_name": "Nom de l'acteur",
            "stance": "alerte",
            "argument_summary": "Résumé court de l'argument.",
            "quote": "Citation exacte.",
            "quote_context": "Contexte immédiat.",
            "tags": ["tag"],
            "confidence": 0.85,
            "needs_review": false
          }
        ]
      }
    }
  ]
}
```

## Valeurs de stance

```txt
soutien
opposition
alerte
critique
demande_action
demande_moyens
justification
annonce_mesure
réserve
proposition
défense_bilan
mise_en_cause
```

## Règles de qualité

- Une citation doit être un extrait littéral du segment fourni.
- Ne pas attribuer à l'auteur de la question une phrase de la réponse gouvernementale.
- Ne pas attribuer au ministère une phrase du député.
- Mettre `needs_review=true` si le sens politique ou l'attribution est incertain.
- Une citation utile vaut mieux qu'une liste exhaustive.
