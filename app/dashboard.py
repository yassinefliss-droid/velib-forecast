"""Tableau de bord Vélib' (Streamlit).

Lancer :  PYTHONPATH=src streamlit run app/dashboard.py
"""
import time

import altair as alt
import pandas as pd
import pydeck as pdk
import streamlit as st
from google.api_core.exceptions import NotFound
from google.cloud import bigquery

from velib import bq
from velib import dashboard_data as dd

st.set_page_config(page_title="Vélib' : disponibilité", layout="wide")


@st.cache_resource
def client() -> bigquery.Client:
    return bq.get_client()


def ds() -> str:
    return f"`{client().project}.{bq.DATASET}`"


@st.cache_data(ttl=300, show_spinner=False)   # 5 min : évite de relancer BigQuery à chaque clic
def run(sql: str, params: tuple = ()) -> pd.DataFrame:
    cfg = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter(n, t, v) for n, t, v in params]
    )
    return client().query(sql, job_config=cfg).to_dataframe()


def forecast_table_exists() -> bool:
    try:
        client().get_table(f"{client().project}.{bq.DATASET}.{dd.FORECAST_TABLE}")
        return True
    except NotFound:
        return False


st.title("Vélib' Métropole : disponibilité des stations")

# ---------- Santé de la collecte (toujours visible) ----------
health = run(dd.health_sql(ds())).iloc[0]
age = dd.freshness_minutes(int(health["last_ts"]), time.time())
n_24h = int(health["n_24h"])
n_days = int(health["n_days"])

now = run(dd.now_sql(ds()))
now["fill_rate"] = dd.fill_rate(now["bikes"], now["capacity"])
now["color"] = now["fill_rate"].apply(dd.fill_to_rgb)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Fraîcheur des données", f"{age:.0f} min", help="Âge du dernier snapshot chargé dans BigQuery")
c2.metric("Snapshots (24 h)", f"{n_24h}",
          f"{dd.collection_ratio(n_24h):.0%} des {dd.EXPECTED_SNAPSHOTS_PER_DAY} attendus",
          delta_color="off")
c3.metric("Jours de données", n_days)
c4.metric("Stations hors service", int((~now["is_operational"]).sum()), help="Au dernier snapshot")
if age > 15:
    st.warning(f"Dernier snapshot il y a {age:.0f} min : la collecte est peut-être arrêtée.")
if n_days < 7:
    st.info(f"Seulement {n_days} jour(s) de données : les profils par jour de semaine sont incomplets.")

tab_now, tab_profile, tab_model = st.tabs(["Maintenant", "Profils", "Modèle"])

# ---------- Maintenant ----------
with tab_now:
    only_ok = st.toggle("Stations opérationnelles seulement", value=True)
    view = now[now["is_operational"]] if only_ok else now
    k1, k2, k3 = st.columns(3)
    k1.metric("Vélos disponibles", int(view["bikes"].sum()))
    k2.metric("Stations vides", int((view["bikes"] == 0).sum()))
    k3.metric("Stations pleines (0 place)", int((view["docks"] == 0).sum()))
    layer = pdk.Layer(
        "ScatterplotLayer", data=view, get_position="[lon, lat]",
        get_fill_color="color", get_radius=55, pickable=True,
    )
    st.pydeck_chart(pdk.Deck(
        layers=[layer],
        initial_view_state=pdk.ViewState(latitude=48.8566, longitude=2.3522, zoom=10.5),
        tooltip={"text": "{name}\nVélos : {bikes} / capacité {capacity}"},
    ))
    st.caption("Bleu clair = station presque vide, bleu foncé = presque pleine, gris = capacité inconnue.")

# ---------- Profils ----------
with tab_profile:
    prof = run(dd.network_profile_sql(ds()))
    prof["jour"] = prof["weekday_local"].map(dd.weekday_label)
    heat = alt.Chart(prof).mark_rect().encode(
        x=alt.X("hour_local:O", title="Heure (Paris)"),
        y=alt.Y("jour:O", sort=dd.WEEKDAYS, title=None),
        color=alt.Color("fill:Q", title="Taux de remplissage moyen", scale=alt.Scale(scheme="blues")),
        tooltip=["jour", "hour_local", alt.Tooltip("fill:Q", format=".2f"), "n"],
    )
    st.subheader("Réseau : taux de remplissage moyen par heure et jour")
    st.altair_chart(heat, use_container_width=True)

    st.subheader("Une station")
    names = now.sort_values("name")[["station_id", "name"]]
    label = st.selectbox("Station", names["name"])
    sid = int(names.loc[names["name"] == label, "station_id"].iloc[0])
    hours = st.slider("Historique (heures)", 6, 168, 48)
    series = run(dd.series_sql(ds()), (("station", "INT64", sid), ("hours", "INT64", hours)))
    st.line_chart(series.set_index("snapshot_at")["bikes"], y_label="Vélos disponibles")
    sp = run(dd.station_profile_sql(ds()), (("station", "INT64", sid),))
    sp["jour"] = sp["weekday_local"].map(dd.weekday_label)
    st.altair_chart(
        alt.Chart(sp).mark_line().encode(
            x=alt.X("hour_local:Q", title="Heure (Paris)"),
            y=alt.Y("fill:Q", title="Taux de remplissage moyen"),
            color=alt.Color("jour:N", sort=dd.WEEKDAYS),
        ),
        use_container_width=True,
    )

# ---------- Modèle ----------
with tab_model:
    if not forecast_table_exists():
        st.info(
            f"Pas encore de modèle : la table `{dd.FORECAST_TABLE}` n'existe pas dans BigQuery. "
            "Cet onglet affichera l'erreur (MAE) du modèle comparée à la baseline de persistance "
            "dès que les prévisions y seront écrites."
        )
    else:
        err = run(dd.forecast_mae_sql(ds()))
        if err.empty:
            st.info("Des prévisions existent, mais aucune n'a encore été comparée à la réalité.")
        else:
            tot = int(err["n"].sum())
            m_model = (err["mae_model"] * err["n"]).sum() / tot
            m_naive = (err["mae_naive"] * err["n"]).sum() / tot
            a, b, c = st.columns(3)
            a.metric("MAE modèle (vélos)", f"{m_model:.2f}")
            b.metric("MAE baseline (persistance)", f"{m_naive:.2f}")
            c.metric("Prévisions évaluées", tot)
            long = err.melt("hour_local", ["mae_model", "mae_naive"], "série", "MAE")
            st.altair_chart(
                alt.Chart(long).mark_line().encode(
                    x=alt.X("hour_local:Q", title="Heure cible (Paris)"), y="MAE:Q", color="série:N"
                ),
                use_container_width=True,
            )
