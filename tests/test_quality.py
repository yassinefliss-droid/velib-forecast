"""Tests des règles de qualité. Données SYNTHÉTIQUES : chaque ligne est construite
pour violer (ou non) exactement une règle."""
import sqlite3

import pandas as pd

from velib import etl, quality

TS = 1_700_000_000


def row(station_id, bikes=5, docks=5, cap=10, installed=1, renting=1, returning=1,
        last_reported=TS - 60, info_id="auto"):
    return {
        "snapshot_ts": TS, "station_id": station_id,
        "num_bikes_available": bikes, "num_docks_available": docks,
        "is_installed": installed, "is_renting": renting, "is_returning": returning,
        "last_reported": last_reported,
        "info_id": station_id if info_id == "auto" else info_id, "capacity": cap,
    }


def rules_for(df, station_id):
    issues = quality.find_issues(pd.DataFrame(df))
    return set(issues.loc[issues["station_id"] == station_id, "rule"])


def test_clean_row_has_no_issue():
    assert quality.find_issues(pd.DataFrame([row(1)])).empty


def test_missing_value():
    assert "missing_value" in rules_for([row(1, bikes=None)], 1)


def test_negative_value():
    assert "negative_value" in rules_for([row(1, bikes=-2)], 1)


def test_unknown_station():
    assert "unknown_station" in rules_for([row(1, info_id=None, cap=None)], 1)


def test_invalid_capacity():
    assert "invalid_capacity" in rules_for([row(1, cap=0)], 1)
    assert "invalid_capacity" in rules_for([row(2, cap=None)], 2)


def test_exceeds_capacity():
    assert "bikes_docks_exceed_capacity" in rules_for([row(1, bikes=8, docks=8, cap=10)], 1)


def test_stale_report():
    old = TS - quality.STALE_SECONDS - 1
    assert "stale_report" in rules_for([row(1, last_reported=old)], 1)


def test_out_of_service():
    assert "out_of_service" in rules_for([row(1, installed=0, renting=0, returning=0)], 1)


def test_not_renting_but_installed():
    r = rules_for([row(1, installed=1, renting=0)], 1)
    assert "not_renting_or_returning" in r and "out_of_service" not in r


def test_check_new_snapshots_is_idempotent(tmp_path):
    status = {
        "lastUpdatedOther": TS,
        "data": {"stations": [
            {"station_id": 1, "num_bikes_available": -1, "num_docks_available": 3,
             "is_installed": 1, "is_renting": 1, "is_returning": 1, "last_reported": TS},
        ]},
    }
    with sqlite3.connect(tmp_path / "t.db") as conn:
        conn.executescript(etl.SCHEMA)
        etl.load_status(conn, etl.transform_status(status))
        first = quality.check_new_snapshots(conn)
        assert {"negative_value", "unknown_station"} <= set(first["rule"])
        n = conn.execute("SELECT COUNT(*) FROM data_quality_log").fetchone()[0]
        assert quality.check_new_snapshots(conn).empty      # snapshot déjà contrôlé
        assert conn.execute("SELECT COUNT(*) FROM data_quality_log").fetchone()[0] == n
