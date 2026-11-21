"""Chargement SQLite -> BigQuery (idempotent, par rattrapage).

Usage :
    python -m velib.bq            # charge dans BigQuery les snapshots manquants
Config (variables d'environnement, valeurs par défaut entre parenthèses) :
    VELIB_GCP_KEY   (secrets/gcp-key.json)
    VELIB_BQ_DATASET (velib_data_base)
    VELIB_BQ_LOCATION (US)   <- doit être la région du dataset
"""
from __future__ import annotations

import argparse
import logging
import os
import sqlite3
from pathlib import Path

import pandas as pd
from google.cloud import bigquery
from google.oauth2 import service_account

log = logging.getLogger("velib.bq")

KEY = os.environ.get("VELIB_GCP_KEY", "secrets/gcp-key.json")
DATASET = os.environ.get("VELIB_BQ_DATASET", "velib_data_base")
LOCATION = os.environ.get("VELIB_BQ_LOCATION", "US")

STATUS_TABLE = "raw_station_status"
INFO_TABLE = "raw_station_information"

STATUS_INT_COLS = [
    "station_id", "snapshot_ts", "num_bikes_available", "num_docks_available",
    "mechanical", "ebike", "is_installed", "is_renting", "is_returning", "last_reported",
]
STATUS_SCHEMA = (
    [bigquery.SchemaField(c, "INT64") for c in STATUS_INT_COLS]
    + [bigquery.SchemaField("snapshot_at", "TIMESTAMP")]   # snapshot_ts lisible + partition
)
INFO_SCHEMA = [
    bigquery.SchemaField("station_id", "INT64"),
    bigquery.SchemaField("station_code", "STRING"),
    bigquery.SchemaField("name", "STRING"),
    bigquery.SchemaField("lat", "FLOAT64"),
    bigquery.SchemaField("lon", "FLOAT64"),
    bigquery.SchemaField("capacity", "INT64"),
]


# ---------- Fonctions pures (testables hors-ligne) ----------
def to_bq_status(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for c in STATUS_INT_COLS:
        out[c] = pd.to_numeric(out[c], errors="coerce").astype("Int64")
    out["snapshot_at"] = pd.to_datetime(out["snapshot_ts"].astype("int64"), unit="s", utc=True)
    return out[STATUS_INT_COLS + ["snapshot_at"]]


def missing_snapshots(local, remote) -> list[int]:
    """Snapshots présents en local mais pas encore dans BigQuery, du plus ancien au plus récent."""
    return sorted(set(int(x) for x in local) - set(int(x) for x in remote))


# ---------- BigQuery ----------
def get_client() -> bigquery.Client:
    creds = service_account.Credentials.from_service_account_file(KEY)
    return bigquery.Client(credentials=creds, project=creds.project_id, location=LOCATION)


def _tid(client: bigquery.Client, table: str) -> str:
    return f"{client.project}.{DATASET}.{table}"


def ensure_tables(client: bigquery.Client) -> None:
    status = bigquery.Table(_tid(client, STATUS_TABLE), schema=STATUS_SCHEMA)
    status.time_partitioning = bigquery.TimePartitioning(
        type_=bigquery.TimePartitioningType.DAY, field="snapshot_at"
    )
    client.create_table(status, exists_ok=True)
    client.create_table(bigquery.Table(_tid(client, INFO_TABLE), schema=INFO_SCHEMA), exists_ok=True)


def remote_snapshots(client: bigquery.Client) -> list[int]:
    sql = f"SELECT DISTINCT snapshot_ts FROM `{_tid(client, STATUS_TABLE)}`"
    return [r.snapshot_ts for r in client.query(sql).result()]


def _load(client, df: pd.DataFrame, table: str, schema, disposition: str) -> None:
    cfg = bigquery.LoadJobConfig(schema=schema, write_disposition=disposition)
    client.load_table_from_dataframe(df, _tid(client, table), job_config=cfg).result()


def sync(db_path: Path, client: bigquery.Client | None = None) -> int:
    """Charge dans BigQuery les snapshots SQLite absents. Retourne le nb de snapshots chargés."""
    client = client or get_client()
    ensure_tables(client)
    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
        local = pd.read_sql_query("SELECT DISTINCT snapshot_ts FROM station_status", conn)["snapshot_ts"]
        todo = missing_snapshots(local, remote_snapshots(client))
        info = pd.read_sql_query("SELECT * FROM station_information", conn)
        status = pd.DataFrame()
        if todo:
            marks = ",".join("?" * len(todo))
            status = pd.read_sql_query(
                f"SELECT * FROM station_status WHERE snapshot_ts IN ({marks})", conn, params=todo
            )
    # Dimension : remplacement complet (1 526 lignes), c'est l'état courant des stations
    info["station_id"] = pd.to_numeric(info["station_id"]).astype("Int64")
    _load(client, info, INFO_TABLE, INFO_SCHEMA, "WRITE_TRUNCATE")
    if todo:
        _load(client, to_bq_status(status), STATUS_TABLE, STATUS_SCHEMA, "WRITE_APPEND")
    log.info("BigQuery : %d snapshot(s) chargé(s), %d lignes", len(todo), len(status))
    return len(todo)


def main() -> None:
    parser = argparse.ArgumentParser(description="SQLite -> BigQuery")
    parser.add_argument("--db", type=Path, default=Path("data/velib.db"))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    sync(args.db)


if __name__ == "__main__":
    main()
