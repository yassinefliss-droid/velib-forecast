"""État de la collecte : combien de snapshots, quels trous, quelle fréquence réelle.

Usage : python scripts/collection_report.py [--db data/velib.db] [--gap-min 10]
"""
import argparse
import sqlite3

import pandas as pd

parser = argparse.ArgumentParser()
parser.add_argument("--db", default="data/velib.db")
parser.add_argument("--gap-min", type=int, default=10, help="écart considéré comme un trou")
args = parser.parse_args()

with sqlite3.connect(f"file:{args.db}?mode=ro", uri=True) as conn:
    ts = pd.read_sql_query(
        "SELECT DISTINCT snapshot_ts FROM station_status ORDER BY 1", conn
    )["snapshot_ts"]

t = pd.to_datetime(ts, unit="s", utc=True)
gaps = t.diff().dropna().dt.total_seconds()

print(f"Snapshots distincts : {len(t)}")
print(f"Période (UTC)       : {t.min()}  ->  {t.max()}")
print(f"Durée couverte      : {t.max() - t.min()}")
if len(gaps):
    print("\nÉcart entre snapshots consécutifs (secondes) :")
    print(gaps.describe().round(1).to_string())
    big = gaps[gaps > args.gap_min * 60]
    print(f"\nTrous > {args.gap_min} min : {len(big)}")
    for i in big.index:
        print(f"  {t[i - 1]}  ->  {t[i]}  ({gaps[i] / 60:.0f} min)")
print("\nSnapshots par jour (UTC) :")
print(t.dt.date.value_counts().sort_index().to_string())
