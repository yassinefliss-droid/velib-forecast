"""Contrôles de qualité des données Vélib'.

Principe : on SIGNALE les anomalies dans la table `data_quality_log`, on ne
supprime jamais de données (une station hors service est une information réelle).

Usage :
    python -m velib.quality            # contrôle les snapshots pas encore contrôlés
"""
from __future__ import annotations

import argparse
import logging
import sqlite3
from pathlib import Path

import pandas as pd

log = logging.getLogger("velib.quality")

# Seuil de "station silencieuse" : paramètre à CALIBRER après avoir regardé la
# distribution réelle de snapshot_ts - last_reported (étape 3).
STALE_SECONDS = 6 * 3600

SCHEMA = """
CREATE TABLE IF NOT EXISTS data_quality_log (
    snapshot_ts INTEGER NOT NULL,
    station_id  INTEGER NOT NULL,
    rule        TEXT NOT NULL,
    severity    TEXT NOT NULL,          -- error | warning | info
    value       TEXT,                   -- valeur fautive, pour diagnostiquer
    checked_at  TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (snapshot_ts, station_id, rule)   -- idempotent, comme l'ETL
);
CREATE TABLE IF NOT EXISTS quality_checked (
    snapshot_ts INTEGER PRIMARY KEY     -- snapshots déjà contrôlés
);
"""

QUERY = """
SELECT s.snapshot_ts, s.station_id, s.num_bikes_available, s.num_docks_available,
       s.is_installed, s.is_renting, s.is_returning, s.last_reported,
       i.station_id AS info_id, i.capacity
FROM station_status s
LEFT JOIN station_information i USING (station_id)
WHERE s.snapshot_ts NOT IN (SELECT snapshot_ts FROM quality_checked)
"""

OUT_COLS = ["snapshot_ts", "station_id", "rule", "severity", "value"]


def find_issues(df: pd.DataFrame) -> pd.DataFrame:
    """Fonction pure : DataFrame (statut + capacité) -> une ligne par anomalie."""
    bikes = pd.to_numeric(df["num_bikes_available"], errors="coerce")
    docks = pd.to_numeric(df["num_docks_available"], errors="coerce")
    cap = pd.to_numeric(df["capacity"], errors="coerce")
    total = bikes + docks
    age = pd.to_numeric(df["snapshot_ts"]) - pd.to_numeric(df["last_reported"], errors="coerce")
    installed = pd.to_numeric(df["is_installed"], errors="coerce")
    renting = pd.to_numeric(df["is_renting"], errors="coerce")
    returning = pd.to_numeric(df["is_returning"], errors="coerce")

    # (règle, gravité, masque booléen, valeur à journaliser)
    checks = [
        ("missing_value", "error", bikes.isna() | docks.isna(), None),
        ("negative_value", "error", (bikes < 0) | (docks < 0), bikes),
        ("unknown_station", "error", df["info_id"].isna(), None),
        ("invalid_capacity", "warning", cap.isna() | (cap <= 0), cap),
        ("bikes_docks_exceed_capacity", "warning", total > cap, total),
        ("stale_report", "warning", age > STALE_SECONDS, age),
        ("out_of_service", "info", installed == 0, None),
        ("not_renting_or_returning", "info",
         (installed == 1) & ((renting == 0) | (returning == 0)), None),
    ]
    parts = []
    for rule, severity, mask, values in checks:
        mask = mask.fillna(False).astype(bool)
        if not mask.any():
            continue
        part = df.loc[mask, ["snapshot_ts", "station_id"]].copy()
        part["rule"] = rule
        part["severity"] = severity
        part["value"] = values[mask].astype("string") if values is not None else pd.NA
        parts.append(part)
    if not parts:
        return pd.DataFrame(columns=OUT_COLS)
    return pd.concat(parts, ignore_index=True)[OUT_COLS]


def check_new_snapshots(conn: sqlite3.Connection) -> pd.DataFrame:
    """Contrôle les snapshots non encore contrôlés. Retourne les anomalies trouvées."""
    conn.executescript(SCHEMA)
    df = pd.read_sql_query(QUERY, conn)
    if df.empty:
        return pd.DataFrame(columns=OUT_COLS)
    issues = find_issues(df)
    with conn:  # une seule transaction : journal + marquage des snapshots
        conn.executemany(
            "INSERT OR IGNORE INTO data_quality_log "
            "(snapshot_ts, station_id, rule, severity, value) VALUES (?,?,?,?,?)",
            [
                (int(r.snapshot_ts), int(r.station_id), r.rule, r.severity,
                 None if pd.isna(r.value) else str(r.value))
                for r in issues.itertuples(index=False)
            ],
        )
        conn.executemany(
            "INSERT OR IGNORE INTO quality_checked (snapshot_ts) VALUES (?)",
            [(int(t),) for t in df["snapshot_ts"].unique()],
        )
    summary = issues.groupby(["severity", "rule"]).size() if len(issues) else "aucune anomalie"
    log.info("%d snapshot(s) contrôlé(s). Anomalies :\n%s", df["snapshot_ts"].nunique(), summary)
    return issues


def main() -> None:
    parser = argparse.ArgumentParser(description="Contrôles qualité Vélib'")
    parser.add_argument("--db", type=Path, default=Path("data/velib.db"))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    with sqlite3.connect(args.db) as conn:
        check_new_snapshots(conn)


if __name__ == "__main__":
    main()
