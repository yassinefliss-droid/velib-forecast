"""Test de fumée hors-ligne : données SYNTHÉTIQUES, il ne valide que la logique
(idempotence, types), pas le vrai format de l'API."""
import sqlite3

from velib import etl

STATUS = {
    "lastUpdatedOther": 1700000000,
    "data": {"stations": [
        {"station_id": 1, "num_bikes_available": 3, "num_docks_available": 7,
         "num_bikes_available_types": [{"mechanical": 2}, {"ebike": 1}],
         "is_installed": 1, "is_renting": 1, "is_returning": 1, "last_reported": 1699999990},
        {"station_id": 2, "num_bikes_available": None, "num_docks_available": 10},
    ]},
}


def test_load_is_idempotent(tmp_path):
    df = etl.transform_status(STATUS)
    with sqlite3.connect(tmp_path / "t.db") as conn:
        conn.executescript(etl.SCHEMA)
        assert etl.load_status(conn, df) == 2
        assert etl.load_status(conn, df) == 0  # 2e passage : rien de nouveau
        assert conn.execute("SELECT COUNT(*) FROM station_status").fetchone()[0] == 2
