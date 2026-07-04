# Intégration des vraies données — AgorIA

## Objectif

L'application ne lit plus uniquement les fichiers fictifs de `data/demo`. Elle sait maintenant charger des payloads publics prétraités depuis :

```text
data/curated/    données réelles relues ou prêtes à afficher
data/processed/  données réelles automatiques, activables explicitement
data/raw/        sources officielles brutes, inchangées
```

Le reste de l'application continue à manipuler les objets métier `Measure` et `PublicTrace`.

## Mode de données

Par défaut :

```bash
./scripts/run.sh
```

- si `data/curated/*.json` contient des payloads AgorIA, l'application les affiche ;
- sinon elle revient aux données de démonstration.

Modes explicites :

```bash
AGORIA_DATA_MODE=demo ./scripts/run.sh
AGORIA_DATA_MODE=processed ./scripts/run.sh
AGORIA_DATA_MODE=auto ./scripts/run.sh
```

Pour inclure aussi les sorties automatiques de `data/processed` :

```bash
AGORIA_DATA_MODE=processed AGORIA_INCLUDE_AUTOMATIC=1 ./scripts/run.sh
```

## Importer un payload réel déjà extrait

Le fichier doit respecter le contrat :

```text
data/schemas/agoraloi_processed_payload.schema.json
```

Import en zone relue :

```bash
./scripts/import_processed_payload.py chemin/vers/payload.json --status needs_review --target curated
```

Import validé :

```bash
./scripts/import_processed_payload.py chemin/vers/payload.json --status validated --target curated
```

## Récupérer une source brute officielle

Le script suivant stocke la réponse brute sans l'interpréter :

```bash
./scripts/fetch_official_source.py "https://exemple.api/source/123" \
  --id an_source_123 \
  --type amendment \
  --institution assemblee_nationale
```

La sortie va dans `data/raw/an_source_123.json`. Elle peut ensuite être envoyée au pipeline d'extraction IA décrit dans `docs/api/processing_architecture.md` et `docs/api/extraction_prompt.md`.

## Pipeline conseillé pour le hackathon

1. Télécharger les sources officielles brutes dans `data/raw/`.
2. Extraire / classifier avec le prompt `docs/api/extraction_prompt.md`.
3. Produire un JSON conforme au schéma `agoraloi_processed_payload.schema.json`.
4. Importer en `needs_review` dans `data/curated/`.
5. Relire les citations, URLs, acteurs et rattachements taxonomiques.
6. Passer le statut à `validated` quand la donnée peut être affichée.

## Points importants

- Une citation affichée doit toujours renvoyer vers une source officielle.
- Les fichiers `automatic` ne sont pas affichés par défaut.
- Les données de démonstration restent disponibles pour la présentation hors connexion.
- Le dépôt `ProcessedRepository` est isolé dans `app/repositories/processed_repository.py`, donc on peut remplacer plus tard la lecture de fichiers par PostgreSQL, MCP ou API unifiée sans toucher aux vues.

## Extraction déterministe depuis `data/raw`

Le script `scripts/build_curated_from_raw.py` implémente la première couche du pipeline hybride : il extrait uniquement les champs objectifs des dumps officiels, sans appel LLM.

```bash
./scripts/build_curated_from_raw.py
```

Entrées reconnues dans `data/raw/` :

```text
AMO50_acteurs_mandats_organes_divises.json/acteur
AMO50_acteurs_mandats_organes_divises.json/mandat
AMO50_acteurs_mandats_organes_divises.json/organe
Dossiers_Legislatifs.json/json/document
Dossiers_Legislatifs.json/json/dossierParlementaire
Questions_gouvernement.json/json
Questions_orales_sans_debat.json/json
```

Sorties produites :

```text
data/processed/normalized_actors.json
data/processed/normalized_documents.json
data/processed/normalized_dossiers.json
data/processed/normalized_questions.json
data/processed/normalized_subjects.json
data/processed/taxonomy.json
data/processed/llm_enrichment_queue.json
data/curated/agoria_raw_extract.json
```

La sortie `data/curated/agoria_raw_extract.json` est directement lisible par `ProcessedRepository`, donc l'application peut afficher les premiers vrais sujets, événements de chronologie et traces d'acteurs.

Pour tester sur un petit volume :

```bash
./scripts/build_curated_from_raw.py --limit 50
```

Pour ne générer que les fichiers normalisés, sans alimenter l'application :

```bash
./scripts/build_curated_from_raw.py --no-curated-payload
```

### Rôle du LLM

Le script ne résume pas finement et ne crée pas de taxonomie définitive. Il prépare une file d'enrichissement ciblée :

```text
data/processed/llm_enrichment_queue.json
```

Cette file contient des tâches séparées, par exemple :

- `classify_subject` : rattacher un sujet à une taxonomie lisible ;
- `summarize_question_and_answer` : produire un résumé court de la question, de la réponse, des enjeux et des mesures annoncées.

Cette séparation permet de garder les extractions vérifiables et de limiter l'IA aux endroits où elle apporte vraiment de la valeur : classification, synthèse, regroupement et consolidation taxonomique.

## Enrichissement LLM ciblé

Le pipeline reste hybride : `build_curated_from_raw.py` extrait les champs objectifs par script, puis `enrich_with_llm.py` enrichit uniquement les éléments qui demandent une interprétation : résumé de question/réponse, catégories de carte mentale, tags et propositions de catégories intermédiaires.

Le script lit :

```bash
 data/processed/llm_enrichment_queue.json
```

Il écrit :

```bash
 data/processed/llm_enrichments.json
```

et, avec `--apply`, fusionne les résultats dans :

```bash
 data/curated/agoria_raw_extract.json
```

### Tester sans appel externe

Pour vérifier toute la chaîne sans clé API :

```bash
./scripts/build_curated_from_raw.py --limit 100
./scripts/enrich_with_llm.py --provider mock --limit 20 --apply
AGORIA_DATA_MODE=auto ./scripts/run.sh
```

Le provider `mock` ne produit pas une vraie analyse sémantique. Il sert seulement à vérifier la fusion dans le payload et l'affichage applicatif.

### Auditer les prompts avant appel LLM

```bash
./scripts/enrich_with_llm.py --provider dry-run --limit 10 --write-prompts
```

Les prompts sont écrits dans :

```bash
data/processed/llm_prompts/
```

### Brancher un endpoint compatible OpenAI / Albert

Le script utilise uniquement la bibliothèque standard Python et appelle un endpoint `/chat/completions` compatible OpenAI.

```bash
export AGORIA_LLM_PROVIDER=openai-compatible
export AGORIA_LLM_BASE_URL="https://api.openai.com/v1"
export AGORIA_LLM_MODEL="gpt-4o-mini"
export AGORIA_LLM_API_KEY="..."

./scripts/enrich_with_llm.py --limit 50 --apply
```

Pour un endpoint Albert ou interne compatible OpenAI, remplace `AGORIA_LLM_BASE_URL` et `AGORIA_LLM_MODEL`.

### Cache et reprise

`llm_enrichments.json` sert de cache. À entrée identique, le script ne rappelle pas le LLM. Pour forcer une nouvelle génération :

```bash
./scripts/enrich_with_llm.py --force --limit 50 --apply
```

### Règles de classification

Le prompt impose une taxonomie lisible :

- un seul chemin canonique principal ;
- niveau 1 = grand domaine public ;
- niveau 2 = politique publique ou sous-domaine ;
- niveau 3 = sujet concret ;
- niveau 4 = angle précis facultatif ;
- catégories neutres, non militantes ;
- tags transversaux séparés du chemin canonique ;
- proposition de catégorie intermédiaire uniquement si elle améliore la lisibilité.

Les résultats gardent `needs_review` tant qu'ils ne sont pas validés humainement.

## Enrichissement conversationnel sans API

Pour éviter les frais d'API pendant la préparation de la démo, les items de `data/processed/llm_enrichment_queue.json` peuvent être traités par lots dans une conversation ChatGPT.

Exporter un lot :

```bash
./scripts/export_llm_batch.py --only-task summarize_question_and_answer --limit 10 --out llm_batches/batch_001_input.json
```

Importer le lot enrichi retourné :

```bash
./scripts/import_llm_batch.py llm_batches/batch_001_output.json --apply
```

Les règles détaillées sont dans `docs/llm_batch_workflow.md`. Les schémas de lot sont dans `schemas/llm_batch_input.schema.json` et `schemas/llm_batch_output.schema.json`.
