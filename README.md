# AgoraLoi — prototype de départ

AgoraLoi est un prototype d'IA civique conçu pour le hackathon de l'Assemblée nationale 2026.

Le cœur du projet : **cartographier le débat public existant** à partir de traces institutionnelles publiques — textes, amendements, débats, questions parlementaires — puis aider le citoyen à comprendre les arguments et à préparer une intervention vers les voies officielles.

## Ce que fait déjà le prototype

- Affiche des mesures de démonstration.
- Produit une fiche claire : ce qui change, publics concernés, obligations, échéances.
- Cartographie les traces publiques par rôle argumentatif : soutien, opposition, nuance, clarification, alternative, alerte d'application.
- Regroupe les traces par catégories de débat configurables : coût, calendrier, faisabilité, libertés publiques, etc.
- Propose un atelier de formulation privé : question, demande de clarification, proposition, pétition, consultation.
- Oriente vers des canaux officiels possibles sans transmettre automatiquement.
- Expose une API JSON minimale pour la carte du débat.

## Ce que le prototype ne fait pas

- Il ne collecte pas d'opinions citoyennes par défaut.
- Il ne publie pas de contributions d'utilisateurs.
- Il ne transmet rien à un élu ou à une plateforme externe.
- Il n'appelle pas encore de LLM externe.
- Il utilise des données fictives de démonstration, prêtes à être remplacées par les ressources ouvertes.

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
./scripts/run.sh
```

Puis ouvrir : http://127.0.0.1:8000

## Tests

```bash
./scripts/test.sh
```

## Architecture

```text
app/core/              modèles, paramètres, taxonomie
app/repositories/      accès aux données démo et canaux officiels
app/debate/            construction de la carte argumentative
app/civic/             aiguillage civique et génération de brouillons privés
app/ia/                point d'extension Albert API / endpoint OpenAI-compatible
app/templates/         interface web Jinja
config/taxonomy.yml    catégories de débat modifiables sans code
data/demo/             mesures et traces publiques de démonstration
hackathon-an-2026/     DEFI.md au format demandé
```

## Brancher les vraies ressources

Le remplacement doit se faire dans `app/repositories/` :

- garder les objets métiers internes `Measure` et `PublicTrace` ;
- remplacer `DemoRepository` par un connecteur API / PostgreSQL / MCP ;
- conserver la même interface de service pour ne pas casser l'interface.

Ressource cible recommandée : API ou base unifiée Parlement / Législation / Service Public.

## Principes de confiance

- Sources publiques et traçables.
- Séparation entre cartographie du débat et brouillon personnel.
- Pas de collecte d'opinions politiques par défaut.
- Pas de transmission automatique.
- Taxonomie explicite, modifiable et vérifiable.
- Futur RAG sourcé avant toute génération IA non triviale.
