-- Grain : une ligne par station.
-- Une capacité <= 0 est invalide (vu dans les contrôles qualité) : on la passe à NULL
-- plutôt que de la garder, pour éviter des divisions absurdes en aval.
select
    station_id,
    station_code,
    name,
    lat,
    lon,
    if(capacity > 0, capacity, null) as capacity
from {{ source('velib', 'raw_station_information') }}
