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
