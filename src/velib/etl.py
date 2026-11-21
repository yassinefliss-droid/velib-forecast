"""ETL Vélib' : API GBFS -> Pandas -> SQLite.

Usage :
    python -m velib.etl            # un seul passage (à planifier avec cron)
    python -m velib.etl --db data/velib.db
"""
from __future__ import annotations

import argparse
import logging
import sqlite3
from pathlib import Path

import pandas as pd
import requests

BASE_URL = "https://velib-metropole-opendata.smovengo.cloud/opendata/Velib_Metropole"
STATUS_URL = f"{BASE_URL}/station_status.json"
INFO_URL = f"{BASE_URL}/station_information.json"
DEFAULT_DB = Path("data/velib.db")

log = logging.getLogger("velib.etl")

SCHEMA = """
CREATE TABLE IF NOT EXISTS station_information (
    station_id INTEGER PRIMARY KEY,
    station_code TEXT,
    name TEXT,
    lat REAL,
    lon REAL,
    capacity INTEGER
);
CREATE TABLE IF NOT EXISTS station_status (
    station_id INTEGER NOT NULL,
    snapshot_ts INTEGER NOT NULL,       -- horodatage du flux (epoch s, UTC)
    num_bikes_available INTEGER,
    num_docks_available INTEGER,
    mechanical INTEGER,
    ebike INTEGER,
    is_installed INTEGER,
    is_renting INTEGER,
    is_returning INTEGER,
    last_reported INTEGER,
    PRIMARY KEY (station_id, snapshot_ts)  -- garantit l'idempotence
);
"""


# ---------- Extract ----------
def fetch_json(url: str, timeout: int = 20) -> dict:
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


# ---------- Transform ----------
def _bike_types(types: list | None) -> tuple[int | None, int | None]:
    """num_bikes_available_types = [{"mechanical": 3}, {"ebike": 5}]"""
    merged: dict = {}
    for d in types or []:
        merged.update(d)
    return merged.get("mechanical"), merged.get("ebike")


def transform_status(payload: dict) -> pd.DataFrame:
    # Horodatage du flux : clé "lastUpdatedOther" (GBFS v1) ou "last_updated" (v2+)
    snapshot_ts = payload.get("lastUpdatedOther") or payload.get("last_updated")
    if snapshot_ts is None:
        raise ValueError("Pas d'horodatage de flux dans la réponse")
    rows = []
    for s in payload["data"]["stations"]:
        mech, ebike = _bike_types(s.get("num_bikes_available_types"))
        rows.append(
            {
                "station_id": s.get("station_id"),
                "snapshot_ts": int(snapshot_ts),
                "num_bikes_available": s.get("num_bikes_available"),
                "num_docks_available": s.get("num_docks_available"),
                "mechanical": mech,
                "ebike": ebike,
                "is_installed": s.get("is_installed"),
                "is_renting": s.get("is_renting"),
                "is_returning": s.get("is_returning"),
                "last_reported": s.get("last_reported"),
            }
        )
    df = pd.DataFrame(rows)
    # Types : "Int64" accepte les NA (contrairement à int64), utile pour l'étape 2
    for col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
    # Station sans identifiant = inexploitable (clé primaire)
    df = df.dropna(subset=["station_id"])
    return df


def transform_info(payload: dict) -> pd.DataFrame:
    df = pd.DataFrame(payload["data"]["stations"])
    df = df.rename(columns={"stationCode": "station_code"})
    keep = ["station_id", "station_code", "name", "lat", "lon", "capacity"]
    df = df.reindex(columns=keep)
    df["station_id"] = pd.to_numeric(df["station_id"], errors="coerce").astype("Int64")
    return df.dropna(subset=["station_id"])


# ---------- Load ----------
def _records(df: pd.DataFrame) -> list[tuple]:
    # NA pandas -> None pour que SQLite stocke NULL
    return [
        tuple(None if pd.isna(v) else (v.item() if hasattr(v, "item") else v) for v in row)
        for row in df.itertuples(index=False, name=None)
    ]


def load_status(conn: sqlite3.Connection, df: pd.DataFrame) -> int:
    cols = list(df.columns)
    sql = (
        f"INSERT OR IGNORE INTO station_status ({','.join(cols)}) "
        f"VALUES ({','.join('?' * len(cols))})"
    )
    before = conn.total_changes
    conn.executemany(sql, _records(df))
    return conn.total_changes - before  # lignes réellement insérées


def load_info(conn: sqlite3.Connection, df: pd.DataFrame) -> None:
    cols = list(df.columns)
    sql = (
        f"INSERT OR REPLACE INTO station_information ({','.join(cols)}) "
        f"VALUES ({','.join('?' * len(cols))})"
    )
    conn.executemany(sql, _records(df))


# ---------- Orchestration ----------
def run(db_path: Path = DEFAULT_DB) -> int:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    status_df = transform_status(fetch_json(STATUS_URL))
    info_df = transform_info(fetch_json(INFO_URL))
    # `with conn` = transaction : tout est validé ou tout est annulé
    with sqlite3.connect(db_path) as conn:
        conn.executescript(SCHEMA)
        load_info(conn, info_df)
        inserted = load_status(conn, status_df)
    log.info("%d stations lues, %d nouvelles lignes insérées", len(status_df), inserted)
    # Qualité : un échec du contrôle ne doit pas faire perdre la collecte (déjà validée)
    try:
        from velib import quality

        with sqlite3.connect(db_path) as conn:
            quality.check_new_snapshots(conn)
    except Exception:
        log.exception("Échec des contrôles qualité (la collecte, elle, est enregistrée)")
    return inserted


def main() -> None:
    parser = argparse.ArgumentParser(description="ETL Vélib' -> SQLite")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    run(args.db)


if __name__ == "__main__":
    main()
