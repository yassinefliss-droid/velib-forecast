-- Aucun nombre de vélos négatif ne doit atteindre les marts.
select station_id, snapshot_ts, bikes
from {{ ref('fct_station_status') }}
where bikes < 0
