# Architecture de prétraitement documentaire AgorIA

## Principe

AgorIA utilise l'IA en amont pour transformer des sources publiques en données structurées, versionnées et sourcées.
L'application publique lit ensuite ces données sans dépendre d'une génération IA en temps réel pour afficher la cartographie.

```text
Sources publiques brutes
→ API de récupération
→ IA de reformattage / extraction / classification
→ JSON structuré validable
→ stockage processed / curated
→ cartographie publique
```

## Séparation recommandée

```text
app/ingestion/
  récupération des sources officielles

app/processing/
  appel API IA, extraction, classification, normalisation JSON

app/curation/
  validation humaine ou semi-automatique, statuts, scores de confiance

app/debate/
  construction de la carte consultable à partir des données structurées

app/civic/
  aide privée à la formulation utilisateur
```

## Données recommandées

```text
data/raw/
  sources officielles brutes, inchangées

data/processed/
  sorties IA automatiques conformes au schéma JSON

data/curated/
  données relues, validées ou prêtes à afficher

data/schemas/
  contrats JSON

data/examples/
  payloads de démonstration
```

## Contrat JSON principal

Schéma :

```text
data/schemas/AgorIA_processed_payload.schema.json
```

Exemple :

```text
data/examples/processed_payload_aide_a_mourir.example.json
```

## Flux API minimal

1. Récupérer une source officielle.
2. Stocker la source brute.
3. Envoyer la source à l'API IA avec le prompt `docs/api/extraction_prompt.md`.
4. Valider la sortie JSON contre le schéma.
5. Stocker la sortie dans `data/processed/`.
6. Marquer `automatic`, `needs_review`, `validated` ou `obsolete`.
7. Agréger les sorties validées dans la taxonomie consultable par l'application.

## Statuts de validation

- `automatic` : produit par IA, pas encore relu.
- `needs_review` : incertitude forte ou rattachement faible.
- `validated` : relu humainement ou confirmé par règles fortes.
- `obsolete` : source officielle modifiée depuis le traitement.

## Règle de confiance

La donnée structurée ne remplace jamais la source officielle.
Chaque trace importante doit conserver :

- l'URL de la source ;
- une citation justificative ;
- le score de confiance ;
- le prompt et le modèle utilisés ;
- la date de traitement ;
- le statut de validation.

## Ce qui reste en IA temps réel

La cartographie publique doit fonctionner sans IA live.
L'IA temps réel peut rester utile pour :

- reformuler une question utilisateur ;
- aider à écrire un brouillon privé ;
- expliquer une notion juridique ponctuelle ;
- interroger la cartographie en langage naturel.

Ces usages doivent rester séparés de la base structurée publiée.
