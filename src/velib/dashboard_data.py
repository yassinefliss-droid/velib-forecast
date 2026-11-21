"""Requêtes et fonctions pures du tableau de bord (testables sans BigQuery ni Streamlit).

`ds` = "`projet.dataset`" (identifiant déjà entouré de backticks).
"""
from __future__ import annotations

import pandas as pd

# Attendu SI la collecte tourne toutes les 5 min (24 h * 60 / 5)
EXPECTED_SNAPSHOTS_PER_DAY = 288
WEEKDAYS = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]   # lundi = 0, comme les marts

# La table fct_forecast sera écrite par l'étape 4 avec exactement ce schéma :
#   station_id INT64, made_at TIMESTAMP, target_at TIMESTAMP,
#   y_pred FLOAT64, y_naive FLOAT64, y_true FLOAT64 (NULL tant que l'avenir n'est pas observé)
FORECAST_TABLE = "fct_forecast"


def now_sql(ds: str) -> str:
    """Dernier état connu de chaque station (table brute : toujours fraîche)."""
    return f"""
    SELECT s.station_id, d.name, d.lat, d.lon, d.capacity,
           s.num_bikes_available AS bikes, s.num_docks_available AS docks,
           (s.is_installed = 1 AND s.is_renting = 1 AND s.is_returning = 1) AS is_operational,
           s.snapshot_ts
    FROM {ds}.raw_station_status s
    JOIN {ds}.dim_station d USING (station_id)
    WHERE s.snapshot_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 DAY)
      AND s.snapshot_ts = (
          SELECT MAX(snapshot_ts) FROM {ds}.raw_station_status
          WHERE snapshot_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 DAY))
    """


def health_sql(ds: str) -> str:
    return f"""
    SELECT MAX(snapshot_ts) AS last_ts,
           COUNT(DISTINCT IF(snapshot_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR),
                             snapshot_ts, NULL)) AS n_24h,
           COUNT(DISTINCT DATE(snapshot_at)) AS n_days
    FROM {ds}.raw_station_status
    """


def series_sql(ds: str) -> str:
    return f"""
    SELECT snapshot_at, num_bikes_available AS bikes
    FROM {ds}.raw_station_status
    WHERE station_id = @station
      AND snapshot_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL @hours HOUR)
    ORDER BY snapshot_at
    """


def network_profile_sql(ds: str) -> str:
    return f"""
    SELECT weekday_local, hour_local, AVG(avg_fill_rate) AS fill, SUM(n_observations) AS n
    FROM {ds}.mart_hourly_profile GROUP BY weekday_local, hour_local
    """


def station_profile_sql(ds: str) -> str:
    return f"""
    SELECT weekday_local, hour_local, avg_fill_rate AS fill
    FROM {ds}.mart_hourly_profile WHERE station_id = @station
    """


def forecast_mae_sql(ds: str) -> str:
    return f"""
    SELECT EXTRACT(HOUR FROM target_at AT TIME ZONE 'Europe/Paris') AS hour_local,
           COUNT(*) AS n,
           AVG(ABS(y_pred - y_true))  AS mae_model,
           AVG(ABS(y_naive - y_true)) AS mae_naive
    FROM {ds}.{FORECAST_TABLE} WHERE y_true IS NOT NULL GROUP BY hour_local ORDER BY hour_local
    """


# ---------- Fonctions pures ----------
def freshness_minutes(last_snapshot_ts: int, now_ts: float) -> float:
    return (now_ts - last_snapshot_ts) / 60


def collection_ratio(n_snapshots: int, expected: int = EXPECTED_SNAPSHOTS_PER_DAY) -> float:
    return n_snapshots / expected


def fill_rate(bikes: pd.Series, capacity: pd.Series) -> pd.Series:
    """Taux de remplissage ; capacité manquante ou <= 0 -> NaN (pas de division par zéro)."""
    cap = pd.to_numeric(capacity, errors="coerce")
    return pd.to_numeric(bikes, errors="coerce") / cap.where(cap > 0)


def fill_to_rgb(rate) -> list[int]:
    """Gris si inconnu ; sinon dégradé du bleu clair (vide) au bleu foncé (plein)."""
    if rate is None or pd.isna(rate):
        return [150, 150, 150]
    r = min(max(float(rate), 0.0), 1.0)
    lo, hi = (222, 235, 247), (8, 48, 107)
    return [round(a + (b - a) * r) for a, b in zip(lo, hi)]


def weekday_label(n: int) -> str:
    return WEEKDAYS[int(n)]
