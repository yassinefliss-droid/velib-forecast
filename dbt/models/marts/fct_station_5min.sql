-- Grain : une ligne par (station_id, créneau de 5 minutes).
-- Pourquoi : les snapshots ne tombent pas à intervalles exacts. Pour calculer des
-- variables retardées ("il y a 60 min"), on a besoin d'une grille régulière.
-- Si plusieurs snapshots tombent dans un créneau, on garde le plus récent.
select
    station_id,
    timestamp_seconds(300 * div(snapshot_ts, 300)) as bucket_at,
    bikes,
    fill_rate,
    is_operational
from {{ ref('fct_station_status') }}
qualify row_number() over (
    partition by station_id, div(snapshot_ts, 300) order by snapshot_ts desc
) = 1
