-- Le grain de fct_station_status doit être unique : aucune ligne ne doit sortir.
select station_id, snapshot_ts, count(*) as n
from {{ ref('fct_station_status') }}
group by station_id, snapshot_ts
having count(*) > 1
