"""Données SYNTHÉTIQUES : on teste la logique (exclusion, fuseau, division), pas la réalité."""
import pandas as pd

from velib import explore


def make(rows):
    return pd.DataFrame(rows, columns=["snapshot_ts", "station_id", "bikes", "is_installed",
                                       "is_renting", "is_returning", "capacity"])


def test_load_local_hour_and_fill_rate():
    import sqlite3
    from velib import etl
    # 2026-01-15 11:00 UTC = 12:00 à Paris (hiver, UTC+1)
    ts = int(pd.Timestamp("2026-01-15 11:00", tz="UTC").timestamp())
    with sqlite3.connect(":memory:") as conn:
        conn.executescript(etl.SCHEMA)
        conn.execute("INSERT INTO station_information VALUES (1,'a','x',0,0,10)")
        conn.execute("INSERT INTO station_information VALUES (2,'b','y',0,0,0)")
        conn.execute("INSERT INTO station_status (station_id,snapshot_ts,num_bikes_available,"
                     "is_installed,is_renting,is_returning) VALUES (1,?,5,1,1,1)", (ts,))
        conn.execute("INSERT INTO station_status (station_id,snapshot_ts,num_bikes_available,"
                     "is_installed,is_renting,is_returning) VALUES (2,?,3,1,1,1)", (ts,))
        df = explore.load(conn).set_index("station_id")
    assert df.loc[1, "hour"] == 12
    assert df.loc[1, "fill_rate"] == 0.5
    assert pd.isna(df.loc[2, "fill_rate"])       # capacité 0 -> pas de division par zéro


def test_profile_excludes_non_operational():
    df = make([(1, 1, 10, 1, 1, 1, 20), (1, 2, 0, 0, 0, 0, 20)])
    df["hour"] = 8
    df["fill_rate"] = df["bikes"] / df["capacity"]
    assert explore.profile(df, ["hour"]).loc[8, "avg_bikes"] == 10   # la station fermée est exclue
