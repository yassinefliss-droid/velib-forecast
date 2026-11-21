-- Grain : une ligne par (station_id, jour de semaine, heure) en heure de Paris.
-- Seules les observations de stations opérationnelles entrent dans les moyennes.
select
    station_id,
    mod(extract(dayofweek from snapshot_local) + 5, 7) as weekday_local,   -- lundi = 0
    extract(hour from snapshot_local)                   as hour_local,
    avg(bikes)                                          as avg_bikes,
    avg(fill_rate)                                      as avg_fill_rate,
    count(*)                                            as n_observations
from {{ ref('fct_station_status') }}
where is_operational
group by station_id, weekday_local, hour_local
