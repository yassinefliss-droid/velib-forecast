-- Grain : une ligne par station.
select
    station_id,
    station_code,
    name,
    lat,
    lon,
    capacity,
    capacity is not null as has_valid_capacity
from {{ ref('stg_station_information') }}
