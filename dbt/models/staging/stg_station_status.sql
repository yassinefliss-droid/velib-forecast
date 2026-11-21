-- Grain : une ligne par (station_id, snapshot_ts).
-- Rôle : typer, renommer, convertir en heure de Paris, et dédupliquer au cas où
-- un snapshot aurait été chargé deux fois (BigQuery n'impose pas de clé primaire).
select
    station_id,
    snapshot_ts,
    snapshot_at,
    datetime(snapshot_at, 'Europe/Paris')      as snapshot_local,
    num_bikes_available                        as bikes,
    num_docks_available                        as docks,
    mechanical,
    ebike,
    is_installed,
    is_renting,
    is_returning,
    last_reported
from {{ source('velib', 'raw_station_status') }}
qualify row_number() over (partition by station_id, snapshot_ts order by snapshot_at) = 1
