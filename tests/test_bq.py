"""Tests hors-ligne des fonctions pures. Le vrai chargement BigQuery se teste à la main."""
import pandas as pd

from velib import bq


def test_missing_snapshots():
    assert bq.missing_snapshots([3, 1, 2, 2], [1]) == [2, 3]
    assert bq.missing_snapshots([1, 2], [1, 2]) == []       # idempotent : rien à charger
    assert bq.missing_snapshots([1], []) == [1]


def test_to_bq_status_types_and_timestamp():
    df = pd.DataFrame({
        "station_id": [1], "snapshot_ts": [1700000000], "num_bikes_available": [3],
        "num_docks_available": [None], "mechanical": [2], "ebike": [1],
        "is_installed": [1], "is_renting": [1], "is_returning": [1], "last_reported": [1699999990],
    })
    out = bq.to_bq_status(df)
    assert list(out.columns) == bq.STATUS_INT_COLS + ["snapshot_at"]
    assert str(out["num_bikes_available"].dtype) == "Int64"
    assert pd.isna(out.loc[0, "num_docks_available"])        # NULL préservé
    assert out.loc[0, "snapshot_at"] == pd.Timestamp("2023-11-14 22:13:20", tz="UTC")
