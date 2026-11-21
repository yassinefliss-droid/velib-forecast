"""Exploration : profils de disponibilité par heure et jour de semaine.

Usage : python -m velib.explore [--db data/velib.db]
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import pandas as pd

TZ = "Europe/Paris"

# Même idée en SQL pur. Attention : datetime(...,'unixepoch') est en UTC.
# Le passage à l'heure de Paris (heure d'été/hiver) est fait en Pandas.
SQL_HOURLY_UTC = """
SELECT CAST(strftime('%H', snapshot_ts, 'unixepoch') AS INTEGER) AS hour_utc,
       ROUND(AVG(num_bikes_available), 2) AS avg_bikes,
       COUNT(*) AS n
FROM station_status
WHERE is_installed = 1 AND is_renting = 1 AND is_returning = 1
GROUP BY hour_utc ORDER BY hour_utc;
"""


def load(conn: sqlite3.Connection) -> pd.DataFrame:
    """Statuts + capacité, avec heure locale et taux de remplissage."""
    df = pd.read_sql_query(
        """SELECT s.snapshot_ts, s.station_id, s.num_bikes_available AS bikes,
                  s.is_installed, s.is_renting, s.is_returning, i.capacity
           FROM station_status s JOIN station_information i USING (station_id)""",
        conn,
    )
    t = pd.to_datetime(df["snapshot_ts"], unit="s", utc=True).dt.tz_convert(TZ)
    df["hour"] = t.dt.hour
    df["weekday"] = t.dt.day_of_week          # 0 = lundi
    df["date"] = t.dt.date
    # Taux de remplissage : comparable entre stations de tailles différentes.
    # Capacité invalide (<= 0) -> NaN, pas de division par zéro.
    cap = df["capacity"].where(df["capacity"] > 0)
    df["fill_rate"] = df["bikes"] / cap
    return df


def operational(df: pd.DataFrame) -> pd.DataFrame:
    """Stations réellement utilisables. Les autres sont exclues des PROFILS
    (une station fermée fausserait la moyenne), mais restent dans la base."""
    ok = (df["is_installed"] == 1) & (df["is_renting"] == 1) & (df["is_returning"] == 1)
    return df[ok]


def profile(df: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    return (
        operational(df).groupby(by)
        .agg(avg_bikes=("bikes", "mean"), avg_fill=("fill_rate", "mean"),
             n_snapshots=("snapshot_ts", "nunique"))
        .round(3)
    )


def most_variable_stations(df: pd.DataFrame, top: int = 10) -> pd.DataFrame:
    """Stations dont le taux de remplissage varie le plus (candidates 'difficiles')."""
    return (
        operational(df).groupby("station_id")["fill_rate"].agg(["mean", "std"])
        .dropna().sort_values("std", ascending=False).head(top).round(3)
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=Path("data/velib.db"))
    args = parser.parse_args()
    with sqlite3.connect(f"file:{args.db}?mode=ro", uri=True) as conn:
        df = load(conn)
    n_days = df["date"].nunique()
    print(f"{df['snapshot_ts'].nunique()} snapshots sur {n_days} jour(s) (heure de Paris)")
    if n_days < 7:
        print("ATTENTION : moins de 7 jours, les profils jour de semaine sont incomplets.")
    print("\nProfil par heure :\n", profile(df, ["hour"]).to_string())
    print("\nProfil par jour de semaine (0=lundi) :\n", profile(df, ["weekday"]).to_string())
    print("\nStations les plus variables :\n", most_variable_stations(df).to_string())


if __name__ == "__main__":
    main()
