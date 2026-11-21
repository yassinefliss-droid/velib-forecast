{{ config(
    partition_by={'field': 'snapshot_at', 'data_type': 'timestamp', 'granularity': 'day'},
    cluster_by=['station_id']
) }}

-- Grain : une ligne par (station_id, snapshot_ts).
-- is_operational : station installée ET en location ET en retour.
-- fill_rate      : vélos / capacité (NULL si capacité invalide).
select
    s.station_id,
    s.snapshot_ts,
    s.snapshot_at,
    s.snapshot_local,
    s.bikes,
    s.docks,
    s.mechanical,
    s.ebike,
    (s.is_installed = 1 and s.is_renting = 1 and s.is_returning = 1) as is_operational,
    safe_divide(s.bikes, d.capacity)                                  as fill_rate,
    s.snapshot_ts - s.last_reported                                   as report_age_s
from {{ ref('stg_station_status') }} s
left join {{ ref('dim_station') }} d using (station_id)
