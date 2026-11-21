# Vélib' Forecast

Pipeline de données et de prévision autour des données ouvertes **Vélib' Métropole** (flux GBFS, sans clé d'API).

**Objectif :** collecter la disponibilité des stations toutes les 5 minutes, construire un pipeline reproductible et contrôlé, puis prévoir à 1 heure le nombre de vélos disponibles par station en le comparant à une baseline naïve (persistance).

> **État au 21/11/2026 : le pipeline de collecte, de qualité, d'entrepôt (BigQuery) et de transformation (dbt) fonctionne. Le modèle de prévision n'est pas encore construit : aucune métrique de prévision n'est donnée dans ce document, et aucune ne sera donnée avant d'avoir été mesurée.**

## État d'avancement

| Bloc | État | Preuve |
|---|---|---|
| ETL API → SQLite, idempotent | Fait | 1ʳᵉ exécution : 1526 lignes insérées ; 2ᵉ exécution sur le même flux : 0 |
| Collecte toutes les 5 min (cron) | Actif | 29 snapshots, 44 254 lignes, 1526 stations (période de 3 h 05, collecte en cours) |
| Contrôles qualité + journal | Fait | 20 tests pytest (données synthétiques) ; résultats sur données réelles ci-dessous |
| Chargement BigQuery (bac à sable) | Fait | rattrapage de 5 snapshots (7630 lignes) observé dans les logs |
| Marts dbt | Fait | 7 modèles créés, 8 tests réussis |
| Orchestration Airflow (Docker) | Partiel | image construite, 2 DAG chargés sans erreur, `velib_collect` exécuté avec succès via `airflow dags test` ; `velib_transform` pas encore testé dans Airflow |
| Tableau de bord Streamlit | Code écrit | non encore validé à l'exécution |
| Exploration (profils heure × jour) | Code écrit | pas assez d'historique pour que les profils soient significatifs |
| Modèle de prévision (baseline + XGBoost) | **À faire** | nécessite plusieurs jours de collecte (visé : au moins 7) |
| Dockerfile du projet | **À faire** | seul le Dockerfile d'Airflow existe |

## Architecture

```
API GBFS Vélib'
      │  toutes les 5 min (cron aujourd'hui, DAG velib_collect dans Airflow)
      ▼
 Extract (requests) → Transform (Pandas) → Load SQLite  ──► contrôles qualité (table data_quality_log)
                                              │
                                              │  velib.bq : charge les snapshots absents (rattrapage)
                                              ▼
                                        BigQuery  raw_station_status / raw_station_information
                                              │  dbt, toutes les heures (DAG velib_transform)
                                              ▼
                              stg_*  →  dim_station, fct_station_status, fct_station_5min,
                                        mart_features, mart_hourly_profile
                                              │
                                              ├──► modèle (à venir) ──► fct_forecast
                                              └──► dashboard Streamlit
```

**ETL ou ELT ?** Les deux. La collecte est un petit ETL (Pandas type et aplatit le JSON avant l'écriture). Le chargement dans BigQuery est quasi brut, et les transformations analytiques se font ensuite en SQL avec dbt dans l'entrepôt, donc en ELT.

## Choix de conception

- **Idempotence par l'horodatage du flux.** La clé primaire de `station_status` est `(station_id, snapshot_ts)`, où `snapshot_ts` est le champ `lastUpdatedOther` de l'API, pas l'heure d'exécution. Relancer le script sur le même flux n'ajoute rien (`INSERT OR IGNORE`). `last_reported` n'est pas utilisé comme clé : il reste figé pour une station silencieuse.
- **Une seule convention de nommage.** Le flux duplique certains champs en snake_case et en camelCase (`num_bikes_available` / `numBikesAvailable`). Seule la version snake_case est conservée.
- **Les anomalies sont signalées, pas supprimées.** Une station hors service est une information réelle, utile pour expliquer les erreurs du futur modèle. Chaque anomalie est journalisée avec sa règle, sa gravité et la valeur fautive.
- **SQLite comme tampon local, BigQuery comme entrepôt.** BigQuery n'impose pas de clé primaire : l'idempotence vient du rattrapage (`velib.bq` compare les `snapshot_ts` locaux et distants et charge uniquement les manquants). Ce mécanisme répare aussi seul une panne réseau.
- **Chargement par *load jobs*,** pas en streaming (d'après la documentation, le streaming exige la facturation ; non testé ici). Le fonctionnement des *load jobs* dans le bac à sable a, lui, été vérifié.
- **Grille régulière de 5 minutes** (`fct_station_5min`) avant de calculer des variables retardées : les snapshots ne tombent pas à intervalles exacts. Les retards manquants restent NULL, ils ne sont pas inventés.
- **Deux DAG Airflow** : `velib_collect` (toutes les 5 min) et `velib_transform` (toutes les heures), car reconstruire les marts toutes les 5 min serait du gaspillage. `catchup=False` : l'API ne donne pas le passé, il n'y a rien à rattraper.
- **Dépendances isolées dans l'image Airflow** : un venv pour le code du projet, un autre pour dbt, pour éviter les conflits avec les dépendances d'Airflow.

## Qualité des données : résultats sur les données réelles

Mesurés sur 29 snapshots (44 254 lignes) :

| Règle | Gravité | Lignes | Stations distinctes |
|---|---|---|---|
| `not_renting_or_returning` (installée mais location ou retour désactivé) | info | 1305 | 45 |
| `out_of_service` (non installée) | info | 116 | 4 |
| `bikes_docks_exceed_capacity` (vélos + places > capacité) | warning | 341 | 13 |
| `invalid_capacity` (capacité NULL ou ≤ 0) | warning | 174 | 6 |
| `stale_report` (écart > 6 h entre le flux et `last_reported`) | warning | 667 | 23 |

Aucune valeur manquante, aucune valeur négative, aucune station inconnue dans `station_information`.

Le seuil de 6 h de `stale_report` est arbitraire et reste à calibrer. L'écart maximal observé est de 181 351 511 secondes (environ 5,7 ans) : ce n'est pas un simple retard, mais une valeur par défaut ou aberrante de l'API, à examiner.

## Démarrage rapide

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

PYTHONPATH=src pytest -q                    # tests (données synthétiques)
PYTHONPATH=src python -m velib.etl          # un passage : API -> SQLite + contrôles qualité
python scripts/collection_report.py         # état de la collecte (trous, fréquence)
```

Collecte planifiée (cron), toutes les 5 minutes :

```
*/5 * * * * cd /chemin/vers/velib-forecast && PYTHONPATH=src .venv/bin/python -m velib.etl >> data/etl.log 2>&1
```

**BigQuery** (bac à sable, sans carte bancaire) : créer un projet, un dataset (nom par défaut `velib_data_base`, région `US`), un compte de service avec les rôles *Utilisateur de job BigQuery* et *Éditeur de données BigQuery*, et déposer sa clé dans `secrets/gcp-key.json` (ce dossier est exclu de Git). Variables : `VELIB_GCP_KEY`, `VELIB_BQ_DATASET`, `VELIB_BQ_LOCATION`.

```bash
python scripts/test_bigquery.py             # vérifie auth, dataset, écriture
PYTHONPATH=src python -m velib.bq           # charge les snapshots manquants
pip install "dbt-bigquery==1.12.4" "dbt-core==1.13.0b1"
dbt run  --project-dir dbt --profiles-dir dbt
dbt test --project-dir dbt --profiles-dir dbt
```

**Airflow** (Docker, local) :

```bash
docker compose build && docker compose up -d
cat airflow/home/standalone_admin_password.txt    # identifiant : admin ; interface : http://localhost:8080
```

**Tableau de bord** :

```bash
pip install -r requirements-dashboard.txt
PYTHONPATH=src streamlit run app/dashboard.py
```

## Structure du dépôt

```
src/velib/       etl.py, quality.py, explore.py, bq.py, dashboard_data.py
tests/           tests pytest (données synthétiques)
scripts/         inspect_api.py, collection_report.py, test_bigquery.py
dbt/             modèles staging et marts, tests, profil BigQuery
airflow/         Dockerfile et DAG (velib_collect, velib_transform)
app/             dashboard Streamlit
docs/            documentation détaillée du projet (PDF)
```

## Limites connues

- **La collecte dépend d'une machine allumée.** Cron et Airflow tournent sur un ordinateur portable : orchestration oui, disponibilité 24 h/24 non. Chaque interruption laisse un trou définitif, car l'API ne fournit pas l'historique. Sans carte bancaire, un service d'exécution cloud n'est pas utilisable.
- **Peu d'historique pour l'instant.** Quelques heures de données : les profils par heure et jour de semaine ne sont pas interprétables, et le modèle ne peut pas encore être entraîné ni évalué sérieusement.
- **Bac à sable BigQuery.** Les tables y expirent après une durée limitée (60 jours, d'après ma connaissance de la documentation, à revérifier) et certaines opérations sont restreintes.
- **Airflow « standalone » avec SQLite** est un montage de développement, pas de production.
- **`dbt-core` 1.13.0b1 est une préversion** : les versions sont figées sur celles qui ont fonctionné.
- **Les tests automatiques utilisent des données synthétiques.** Ils valident la logique, pas le format réel de l'API ni le comportement de BigQuery.
- Les contrôles qualité ne couvrent pas encore les trous de collecte (écart anormal entre deux snapshots) ni l'égalité des champs dupliqués camelCase / snake_case (non stockés).

## Prochaines étapes

1. Laisser la collecte tourner (au moins 7 jours) et suivre `scripts/collection_report.py`.
2. Valider `velib_transform` et le tableau de bord à l'exécution.
3. Prévision à 1 h : baseline de persistance, puis XGBoost (variables retardées, heure, jour), validation temporelle glissante, comparaison des MAE, analyse des stations difficiles ; écriture des prévisions dans `fct_forecast`.
4. Dockerfile du projet, puis mise à jour de ce README avec les résultats mesurés.

## Documentation détaillée

`docs/documentation_projet.pdf` : architecture, journal des problèmes rencontrés et de leur résolution, résultats réels, préparation aux questions d'entretien.
