# Architecture — AgorIA

## Objectif

Construire une application qui organise le débat public documenté autour d'une mesure législative et aide l'utilisateur à préparer une intervention informée vers les canaux officiels.

## Flux principal

```text
Sources publiques
  → Repository métier
  → Mesure + traces publiques normalisées
  → Cartographie argumentative
  → Interface de compréhension
  → Atelier de formulation privé
  → Redirection officielle, sans transmission automatique
```

## Séparation des responsabilités

- `repositories` : accès aux données, sans logique de débat.
- `debate` : regroupement argumentatif des traces publiques.
- `civic` : aide à la formulation et orientation vers des formes d'intervention.
- `ia` : point d'extension pour Albert API, RAG, embeddings, rerank et génération contrôlée.
- `templates` : rendu HTML.

## Évolution prévue

1. Remplacer les données de démonstration par l'API unifiée.
2. Ajouter un index vectoriel pour relier questions/amendements/débats aux mesures.
3. Ajouter un RAG sourcé pour résumer les traces publiques.
4. Ajouter un module de vérification : aucune affirmation sans source.
5. Ajouter des tests d'hallucination, de prompt injection et de traçabilité.
