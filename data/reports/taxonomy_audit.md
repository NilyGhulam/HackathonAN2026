# Audit de taxonomie AgorIA

## Résumé

- Catégories : **886**
- Feuilles : **464**
- Sujets : **5323**
- Erreurs : **19**
- Avertissements : **993**

## Répartition des problèmes

- `duplicate_label` : 399
- `leaf_too_small` : 340
- `repeated_path` : 184
- `category_subject_mismatch` : 49
- `leaf_too_large` : 17
- `branch_unbalanced` : 12
- `near_duplicate_label` : 4
- `source_category_mismatch` : 3
- `too_many_children` : 2
- `vague_label` : 2

## Problèmes bloquants

| Sévérité | Problème | Chemin | Sujets | Enfants | Recommandation |
|---|---|---|---:|---:|---|
| error | `leaf_too_large` | Agriculture > Agriculture | 107 | 0 | split |
| error | `leaf_too_large` | Enseignement > Enseignement | 60 | 0 | split |
| error | `leaf_too_large` | Finances publiques > Finances publiques | 61 | 0 | split |
| error | `leaf_too_large` | Industrie > Industrie | 93 | 0 | split |
| error | `leaf_too_large` | Outre-mer > Outre-mer | 129 | 0 | split |
| error | `leaf_too_large` | Politique extérieure > Politique extérieure | 186 | 0 | split |
| error | `leaf_too_large` | Projet de loi > Projet de loi | 52 | 0 | split |
| error | `leaf_too_large` | Proposition de loi > Constitutionnelle | 72 | 0 | split |
| error | `leaf_too_large` | Proposition de loi > Proposition de loi | 1788 | 0 | split |
| error | `leaf_too_large` | Proposition de résolution > En application de Article 34-1 de la Constitution | 178 | 0 | split |
| error | `leaf_too_large` | Proposition de résolution > Sur les travaux conduits par les institutions européennes | 113 | 0 | split |
| error | `leaf_too_large` | Proposition de résolution > Tendant à la création d'une commission d'enquête | 114 | 0 | split |
| error | `leaf_too_large` | Rapport d'information > Tel quel | 81 | 0 | split |
| error | `leaf_too_large` | Santé > Santé | 92 | 0 | split |
| error | `leaf_too_large` | Sécurité des biens et des personnes > Sécurité des biens et des personnes | 93 | 0 | split |
| error | `leaf_too_large` | Énergie et carburants > Énergie et carburants | 80 | 0 | split |
| error | `leaf_too_large` | Établissements de santé > Établissements de santé | 60 | 0 | split |
| error | `too_many_children` | <racine> | 5323 | 190 | split |
| error | `too_many_children` | Parlement | 40 | 13 | split |

## Avertissements principaux

| Sévérité | Problème | Chemin | Sujets | Enfants | Recommandation |
|---|---|---|---:|---:|---|
| warning | `branch_unbalanced` | <racine> | 5323 | 190 | review |
| warning | `branch_unbalanced` | Agriculture | 114 | 7 | review |
| warning | `branch_unbalanced` | Enseignement | 64 | 4 | review |
| warning | `branch_unbalanced` | Finances publiques | 65 | 3 | review |
| warning | `branch_unbalanced` | Outre-mer | 131 | 3 | review |
| warning | `branch_unbalanced` | Politique extérieure | 190 | 4 | review |
| warning | `branch_unbalanced` | Projet de loi | 64 | 6 | review |
| warning | `branch_unbalanced` | Proposition de loi | 1904 | 4 | review |
| warning | `branch_unbalanced` | Rapport d'information | 181 | 7 | review |
| warning | `branch_unbalanced` | Santé | 104 | 10 | review |
| warning | `branch_unbalanced` | Sécurité des biens et des personnes | 96 | 4 | review |
| warning | `branch_unbalanced` | Établissements de santé | 62 | 3 | review |
| warning | `category_subject_mismatch` | Agriculture > Agriculture | 107 | 0 | review |
| warning | `category_subject_mismatch` | Agroalimentaire > Agroalimentaire | 9 | 0 | review |
| warning | `category_subject_mismatch` | Aménagement du territoire > Aménagement du territoire | 15 | 0 | review |
| warning | `category_subject_mismatch` | Assurance maladie maternité > Assurance maladie maternité | 5 | 0 | review |
| warning | `category_subject_mismatch` | Automobiles > Automobiles | 10 | 0 | review |
| warning | `category_subject_mismatch` | Climat > Climat | 15 | 0 | review |
| warning | `category_subject_mismatch` | Commerce extérieur > Commerce extérieur | 14 | 0 | review |
| warning | `category_subject_mismatch` | Crimes, délits et contraventions > Crimes, délits et contraventions | 25 | 0 | review |
| warning | `category_subject_mismatch` | Drogue > Drogue | 22 | 0 | review |
| warning | `category_subject_mismatch` | Enseignement > Enseignement | 60 | 0 | review |
| warning | `category_subject_mismatch` | Enseignement maternel et primaire > Enseignement maternel et primaire | 17 | 0 | review |
| warning | `category_subject_mismatch` | Environnement > Environnement | 21 | 0 | review |
| warning | `category_subject_mismatch` | Handicapés > Handicapés | 10 | 0 | review |
| warning | `category_subject_mismatch` | Impôts et taxes > Impôts et taxes | 24 | 0 | review |
| warning | `category_subject_mismatch` | Impôts locaux > Impôts locaux | 5 | 0 | review |
| warning | `category_subject_mismatch` | Institutions sociales et médico sociales > Institutions sociales et médico sociales | 5 | 0 | review |
| warning | `category_subject_mismatch` | Lieux de privation de liberté > Lieux de privation de liberté | 25 | 0 | review |
| warning | `category_subject_mismatch` | Logement : aides et prêts > Logement : aides et prêts | 11 | 0 | review |
| warning | `category_subject_mismatch` | Mer et littoral > Mer et littoral | 7 | 0 | review |
| warning | `category_subject_mismatch` | Mines et carrières > Mines et carrières | 8 | 0 | review |
| warning | `category_subject_mismatch` | Personnes handicapées > Personnes handicapées | 27 | 0 | review |
| warning | `category_subject_mismatch` | Politique extérieure > Politique extérieure | 186 | 0 | review |
| warning | `category_subject_mismatch` | Politique sociale > Politique sociale | 9 | 0 | review |
| warning | `category_subject_mismatch` | Postes > Postes | 5 | 0 | review |
| warning | `category_subject_mismatch` | Produits dangereux > Produits dangereux | 11 | 0 | review |
| warning | `category_subject_mismatch` | Professions de santé > Professions de santé | 13 | 0 | review |
| warning | `category_subject_mismatch` | Proposition de loi > Constitutionnelle | 72 | 0 | review |
| warning | `category_subject_mismatch` | Proposition de loi > Organique | 43 | 0 | review |
| warning | `category_subject_mismatch` | Proposition de résolution > En application de Article 34-1 de la Constitution | 178 | 0 | review |
| warning | `category_subject_mismatch` | Proposition de résolution > Sur les travaux conduits par les institutions européennes | 113 | 0 | review |
| warning | `category_subject_mismatch` | Proposition de résolution > Tendant à la création d'une commission d'enquête | 114 | 0 | review |
| warning | `category_subject_mismatch` | Questions parlementaires > Questions parlementaires | 10 | 0 | review |
| warning | `category_subject_mismatch` | Rapport > Des offices parlementaires | 16 | 0 | review |
| warning | `category_subject_mismatch` | Rapport d'information > Tel quel | 81 | 0 | review |
| warning | `category_subject_mismatch` | Religions et cultes > Religions et cultes | 6 | 0 | review |
| warning | `category_subject_mismatch` | Sports > Sports | 8 | 0 | review |
| warning | `category_subject_mismatch` | Sécurité des biens et des personnes > Sécurité des biens et des personnes | 93 | 0 | review |
| warning | `category_subject_mismatch` | Sécurité intérieure > Sécurité intérieure | 9 | 0 | review |
| warning | `category_subject_mismatch` | Terrorisme > Terrorisme | 10 | 0 | review |
| warning | `category_subject_mismatch` | Transports aériens > Transports aériens | 16 | 0 | review |
| warning | `category_subject_mismatch` | Transports ferroviaires > Transports ferroviaires | 42 | 0 | review |
| warning | `category_subject_mismatch` | Transports par eau > Transports par eau | 6 | 0 | review |
| warning | `category_subject_mismatch` | Transports routiers > Transports routiers | 18 | 0 | review |
| warning | `category_subject_mismatch` | Urbanisme > Urbanisme | 7 | 0 | review |
| warning | `category_subject_mismatch` | Voirie > Voirie | 14 | 0 | review |
| warning | `category_subject_mismatch` | Économie sociale et solidaire > Économie sociale et solidaire | 6 | 0 | review |
| warning | `category_subject_mismatch` | Élections et référendums > Élections et référendums | 7 | 0 | review |
| warning | `category_subject_mismatch` | Élevage > Élevage | 12 | 0 | review |
| warning | `category_subject_mismatch` | Établissements de santé > Établissements de santé | 60 | 0 | review |
| warning | `duplicate_label` | Accidents du travail et maladies professionnelles | 9 | 1 | review |
| warning | `duplicate_label` | Accidents du travail et maladies professionnelles > Accidents du travail et maladies professionnelles | 9 | 0 | review |
| warning | `duplicate_label` | Administration | 14 | 5 | review |
| warning | `duplicate_label` | Administration > Administration | 10 | 0 | review |
| warning | `duplicate_label` | Agriculture | 114 | 7 | review |
| warning | `duplicate_label` | Agriculture > Agriculture | 107 | 0 | review |
| warning | `duplicate_label` | Agroalimentaire | 9 | 1 | review |
| warning | `duplicate_label` | Agroalimentaire > Agroalimentaire | 9 | 0 | review |
| warning | `duplicate_label` | Aide aux victimes | 11 | 2 | review |
| warning | `duplicate_label` | Aide aux victimes > Aide aux victimes | 10 | 0 | review |
| warning | `duplicate_label` | Aide aux victimes > Indemnisation des victimes | 1 | 1 | review |
| warning | `duplicate_label` | Alcools et boissons alcoolisées | 4 | 1 | review |
| warning | `duplicate_label` | Alcools et boissons alcoolisées > Alcools et boissons alcoolisées | 4 | 0 | review |
| warning | `duplicate_label` | Ambassades et consulats | 1 | 1 | review |
| warning | `duplicate_label` | Ambassades et consulats > Ambassades et consulats | 1 | 0 | review |
| warning | `duplicate_label` | Aménagement du territoire | 16 | 2 | review |
| warning | `duplicate_label` | Aménagement du territoire > Aménagement du territoire | 15 | 0 | review |
| warning | `duplicate_label` | Anciens combattants et victimes de guerre | 6 | 5 | review |
| warning | `duplicate_label` | Anciens combattants et victimes de guerre > Anciens combattants et victimes de guerre | 2 | 0 | review |
| warning | `duplicate_label` | Animaux | 12 | 1 | review |
| warning | `duplicate_label` | Animaux > Animaux | 12 | 0 | review |
| warning | `duplicate_label` | Aquaculture et pêche professionnelle | 17 | 1 | review |
| warning | `duplicate_label` | Aquaculture et pêche professionnelle > Aquaculture et pêche professionnelle | 17 | 0 | review |
| warning | `duplicate_label` | Armes | 5 | 1 | review |
| warning | `duplicate_label` | Armes > Armes | 5 | 0 | review |
| warning | `duplicate_label` | Arts et spectacles | 1 | 1 | review |
| warning | `duplicate_label` | Arts et spectacles > Arts et spectacles | 1 | 0 | review |
| warning | `duplicate_label` | Associations et fondations | 4 | 2 | review |
| warning | `duplicate_label` | Associations et fondations > Associations et fondations | 3 | 0 | review |
| warning | `duplicate_label` | Associations et fondations > Protection des mineurs | 1 | 1 | review |
| warning | `duplicate_label` | Assurance complémentaire | 1 | 1 | review |
| warning | `duplicate_label` | Assurance complémentaire > Assurance complémentaire | 1 | 0 | review |
| warning | `duplicate_label` | Assurance maladie maternité | 6 | 2 | review |
| warning | `duplicate_label` | Assurance maladie maternité > Assurance maladie maternité | 5 | 0 | review |
| warning | `duplicate_label` | Assurances | 4 | 2 | review |
| warning | `duplicate_label` | Assurances > Assurances | 3 | 0 | review |
| warning | `duplicate_label` | Audiovisuel et communication | 8 | 3 | review |
| warning | `duplicate_label` | Audiovisuel et communication > Audiovisuel et communication | 6 | 0 | review |
| warning | `duplicate_label` | Automobiles | 11 | 2 | review |
| warning | `duplicate_label` | Automobiles > Automobiles | 10 | 0 | review |
| warning | `duplicate_label` | Banques et établissements financiers | 8 | 4 | review |
| warning | `duplicate_label` | Banques et établissements financiers > Accès aux services bancaires > Territoires ruraux | 1 | 0 | review |
| warning | `duplicate_label` | Banques et établissements financiers > Banques et établissements financiers | 3 | 0 | review |
| warning | `duplicate_label` | Biodiversité | 6 | 3 | review |
| warning | `duplicate_label` | Biodiversité > Biodiversité | 4 | 0 | review |
| warning | `duplicate_label` | Bioéthique | 3 | 2 | review |
| warning | `duplicate_label` | Bioéthique > Bioéthique | 2 | 0 | review |
| warning | `duplicate_label` | Bois et forêts | 5 | 1 | review |
| warning | `duplicate_label` | Bois et forêts > Bois et forêts | 5 | 0 | review |
| warning | `duplicate_label` | Bâtiment et travaux publics | 1 | 1 | review |
| warning | `duplicate_label` | Bâtiment et travaux publics > Bâtiment et travaux publics | 1 | 0 | review |
| warning | `duplicate_label` | Catastrophes naturelles | 24 | 5 | review |
| warning | `duplicate_label` | Catastrophes naturelles > Catastrophes naturelles | 20 | 0 | review |
| warning | `duplicate_label` | Chambres consulaires | 1 | 1 | review |
| warning | `duplicate_label` | Chambres consulaires > Chambres consulaires | 1 | 0 | review |
| warning | `duplicate_label` | Chasse et pêche | 7 | 1 | review |
| warning | `duplicate_label` | Chasse et pêche > Chasse et pêche | 7 | 0 | review |
| warning | `duplicate_label` | Chômage | 3 | 1 | review |
| warning | `duplicate_label` | Chômage > Chômage | 3 | 0 | review |

_873 autres avertissements dans le JSON._

## Recommandations de lecture

- `too_many_children` : réduire le nombre d’enfants directs pour respecter la limite front de 12.
- `leaf_too_large` : diviser la feuille, car elle agrège trop de sujets.
- `leaf_too_small` : envisager une fusion avec une catégorie voisine.
- `repeated_path` et `vague_label` : renommer ou remapper en priorité, car ces problèmes nuisent directement à la lisibilité.
- `source_category_mismatch` et `category_subject_mismatch` : à relire humainement avant remapping automatique.
