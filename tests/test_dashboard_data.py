"""Fonctions pures du tableau de bord. Données SYNTHÉTIQUES."""
import math

import pandas as pd

from velib import dashboard_data as dd


def test_freshness_and_ratio():
    assert dd.freshness_minutes(1000, 1000 + 600) == 10
    assert dd.collection_ratio(144) == 0.5


def test_fill_rate_handles_bad_capacity():
    r = dd.fill_rate(pd.Series([5, 5, 5]), pd.Series([10, 0, None]))
    assert r.iloc[0] == 0.5
    assert math.isnan(r.iloc[1]) and math.isnan(r.iloc[2])   # pas de division par zéro


def test_fill_to_rgb():
    assert dd.fill_to_rgb(float("nan")) == [150, 150, 150]
    assert dd.fill_to_rgb(0) == [222, 235, 247]
    assert dd.fill_to_rgb(1) == [8, 48, 107]
    assert dd.fill_to_rgb(5) == dd.fill_to_rgb(1)           # borné à 1
    assert dd.fill_to_rgb(-1) == dd.fill_to_rgb(0)          # borné à 0


def test_weekday_label_monday_is_zero():
    assert dd.weekday_label(0) == "Lun" and dd.weekday_label(6) == "Dim"


def test_sql_is_parametrised_not_formatted():
    ds = "`p.d`"
    assert "@station" in dd.series_sql(ds) and "@hours" in dd.series_sql(ds)
    assert "`p.d`.raw_station_status" in dd.now_sql(ds)
