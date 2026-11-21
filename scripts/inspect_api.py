"""Inspecte le format JSON réel de l'API Vélib' (à lancer à la main).

Usage : python scripts/inspect_api.py
"""
import json
from datetime import datetime, timezone

import requests

BASE = "https://velib-metropole-opendata.smovengo.cloud/opendata/Velib_Metropole"


def show(name: str) -> None:
    url = f"{BASE}/{name}.json"
    print("=" * 70)
    print(url)
    resp = requests.get(url, timeout=20)
    print("HTTP", resp.status_code)
    resp.raise_for_status()
    d = resp.json()

    print("\nClés de premier niveau :", list(d.keys()))
    for k, v in d.items():
        if k != "data":
            print(f"  {k} = {v!r}")
            if isinstance(v, int) and v > 1_000_000_000:
                print("     -> en date UTC :", datetime.fromtimestamp(v, timezone.utc))

    stations = d["data"]["stations"]
    print(f"\nNombre de stations : {len(stations)}")
    print("Clés d'une station :", list(stations[0].keys()))
    print("\nPremière station (JSON complet) :")
    print(json.dumps(stations[0], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    show("station_status")
    show("station_information")
