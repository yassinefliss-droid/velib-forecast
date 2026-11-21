"""DAGs Vélib' (Airflow 2.10).

velib_collect   : toutes les 5 min   API -> SQLite (+ qualité) -> BigQuery
velib_transform : toutes les heures   dbt run -> dbt test

Les tâches appellent le code du projet dans son propre venv (BashOperator) :
pas d'import du projet dans l'interpréteur d'Airflow, donc pas de conflit de dépendances.
"""
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator

PROJECT = "/opt/velib"
PY = "/home/airflow/velib_venv/bin/python"
DBT = "/home/airflow/dbt_venv/bin/dbt"
DBT_ARGS = "--project-dir dbt --profiles-dir dbt"

default_args = {
    "owner": "velib",
    "retries": 2,                          # reprise automatique en cas d'échec transitoire
    "retry_delay": timedelta(minutes=1),
}

with DAG(
    dag_id="velib_collect",
    schedule="*/5 * * * *",
    start_date=datetime(2026, 11, 1),
    catchup=False,                         # pas de rattrapage : l'API ne donne pas le passé
    max_active_runs=1,                     # jamais deux collectes en parallèle (SQLite)
    default_args=default_args,
    tags=["velib"],
) as collect:
    etl = BashOperator(
        task_id="etl_sqlite_and_quality",
        bash_command=f"cd {PROJECT} && PYTHONPATH=src {PY} -m velib.etl",
    )
    sync = BashOperator(
        task_id="sync_bigquery",
        bash_command=f"cd {PROJECT} && PYTHONPATH=src {PY} -m velib.bq",
    )
    etl >> sync

with DAG(
    dag_id="velib_transform",
    schedule="5 * * * *",
    start_date=datetime(2026, 11, 1),
    catchup=False,
    max_active_runs=1,
    default_args=default_args,
    tags=["velib", "dbt"],
) as transform:
    dbt_run = BashOperator(
        task_id="dbt_run",
        bash_command=f"cd {PROJECT} && {DBT} run {DBT_ARGS}",
    )
    dbt_test = BashOperator(
        task_id="dbt_test",
        bash_command=f"cd {PROJECT} && {DBT} test {DBT_ARGS}",
    )
    dbt_run >> dbt_test
