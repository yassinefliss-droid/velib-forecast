-- Grain : une ligne par (station_id, créneau de 5 min) = un exemple d'entraînement.
-- Les retards sont NULL si le créneau correspondant manque (trou de collecte) :
-- on ne les invente pas. target_bikes_t_plus_60 est NULL pour les créneaux
-- trop récents (le futur n'est pas encore observé) : ils servent à prévoir.
with g as (select * from {{ ref('fct_station_5min') }})

select
    g.station_id,
    g.bucket_at,
    g.bikes,
    g.fill_rate,
    g.is_operational,
    l5.bikes  as bikes_lag_5,
    l15.bikes as bikes_lag_15,
    l30.bikes as bikes_lag_30,
    l60.bikes as bikes_lag_60,
    extract(hour from datetime(g.bucket_at, 'Europe/Paris')) as hour_local,
    -- BigQuery : dimanche = 1. On convertit pour avoir lundi = 0 ... dimanche = 6
    mod(extract(dayofweek from datetime(g.bucket_at, 'Europe/Paris')) + 5, 7) as weekday_local,
    d.capacity,
    t.bikes as target_bikes_t_plus_60
from g
left join g l5  on l5.station_id  = g.station_id and l5.bucket_at  = timestamp_sub(g.bucket_at, interval 5 minute)
left join g l15 on l15.station_id = g.station_id and l15.bucket_at = timestamp_sub(g.bucket_at, interval 15 minute)
left join g l30 on l30.station_id = g.station_id and l30.bucket_at = timestamp_sub(g.bucket_at, interval 30 minute)
left join g l60 on l60.station_id = g.station_id and l60.bucket_at = timestamp_sub(g.bucket_at, interval 60 minute)
left join g t   on t.station_id   = g.station_id and t.bucket_at   = timestamp_add(g.bucket_at, interval 60 minute)
left join {{ ref('dim_station') }} d on d.station_id = g.station_id
