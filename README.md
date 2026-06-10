# cimis

Python client for the [CIMIS](https://www.cimis.water.ca.gov/) (California
Irrigation Management Information System) REST Web API — daily and hourly
weather, evapotranspiration (ETo), and station data for California.

Covers all five API groups from the
[official REST documentation](https://www.cimis.water.ca.gov/web-api/rest-api/latest):
weather data (by station, zip code, coordinates, or street address), station
metadata, station zip codes, spatial zip codes, and the combined
station/spatial zip code service.

## Installation

```bash
pip install .            # from this repository
pip install ".[pandas]"  # with DataFrame support
pip install ".[geo]"     # with geopandas/GeoDataFrame support
```

## Authentication

Register at [cimis.water.ca.gov](https://www.cimis.water.ca.gov/) to get an
application key. Pass it as `app_key=` or set the `CIMIS_APP_KEY` environment
variable. The key is sent in the `Ocp-Apim-Subscription-Key` header on every
request.

## Usage

```python
from cimis import CimisClient, constants

client = CimisClient(app_key="your-app-key")  # or set CIMIS_APP_KEY

# Daily weather by station number
records = client.get_data_by_station_numbers(
    [2, 80], start_date="2024-01-01", end_date="2024-01-31"
)
for rec in records:
    print(rec.date, rec.station, rec.value("day-asce-eto"))

# Hourly data, specific items
records = client.get_data_by_station_numbers(
    2,
    start_date="2024-06-01",
    end_date="2024-06-02",
    hourly=True,
    data_items=[constants.HLY_AIR_TMP, constants.HLY_ASCE_ETO],
)

# Spatial CIMIS by coordinates (daily ETo / solar radiation only, max 366 days)
records = client.get_data_by_coordinates(
    [(38.5816, -121.4944)], start_date="2024-01-01", end_date="2024-01-31"
)

# Spatial CIMIS by street address
records = client.get_data_by_addresses(
    [("State Capitol", "1315 10th Street Sacramento, CA 95814")],
    start_date="2024-01-01",
    end_date="2024-01-07",
)

# Zip code data from either provider (WSN and/or Spatial CIMIS)
records = client.get_data_by_zip_codes(
    ["95814"], start_date="2024-01-01", end_date="2024-01-31", prefer="SCS"
)

# Station metadata
stations = client.get_all_stations()
station = client.get_station(2)
print(station.name, station.latitude, station.longitude, station.is_active)

# Supported zip codes
wsn_zips = client.get_all_station_zip_codes()
scs_zips = client.get_all_spatial_zip_codes()
```

### Working with records

Each `WeatherRecord` exposes metadata (`date`, `julian`, `station`, `hour`,
`scope`, `zip_codes`, `coordinate`, `address`, `provider`) and a dict of
`DataValue` items keyed by data item code:

```python
rec = records[0]
dv = rec["day-asce-eto"]   # DataValue(value=0.06, qc=' ', unit='in')
rec.value("day-asce-eto")  # 0.06 (None if missing)
rec.timestamp              # datetime; hour-ending for hourly records
```

A `qc` flag of `" "` means the value passed quality control; `"N"` etc. mark
missing/qualified data (the value will be `None`).

### Pandas

```python
from cimis import to_dataframe

df = to_dataframe(records)  # one row per record, items as numeric columns
```

### Geospatial helpers

Find stations near a point (haversine distance, no extra dependencies):

```python
# Three closest active stations to downtown Sacramento
for ns in client.find_nearest_stations(38.5816, -121.4944, n=3):
    print(ns.station.name, f"{ns.distance_km:.1f} km")

client.stations_within(38.5816, -121.4944, radius_km=40)
client.stations_in_bbox(36.0, -122.0, 39.0, -119.0)

# Fetch data from the nearest station that actually covers the date range
# (skips stations that weren't operating then, falls back to the next nearest)
records, nearest = client.get_data_near(
    38.5816, -121.4944, start_date="2024-06-01", end_date="2024-06-30"
)
print(f"data from {nearest.station.name}, {nearest.distance_km:.1f} km away")
```

Export for mapping (GeoJSON is dependency-free; GeoDataFrames need the
`geo` extra):

```python
from cimis import stations_to_geojson, records_to_geojson
from cimis import stations_to_geodataframe, records_to_geodataframe

geojson = stations_to_geojson(client.get_all_stations())
gdf = records_to_geodataframe(records, stations=client.get_all_stations())
```

Spatial (SCS) records carry their own coordinates; station (WSN) records are
located via the `stations=` list. The same helpers are available as pure
functions in `cimis.geo` if you already have station/record lists.

### Caching

Pass `cache=True` to persist responses in `~/.cache/cimis/cache.sqlite`
(or pass a path). Weather responses whose date range is fully in the past
are cached indefinitely — historical CIMIS data doesn't change — while
ranges touching today are never cached, since recent values may still be
revised by quality control. Station/zip metadata is cached for
`metadata_ttl` seconds (default 24 h).

```python
client = CimisClient(cache=True)               # default location
client = CimisClient(cache="my-cache.sqlite")  # custom path
client.cache.clear()                           # drop everything cached
```

### Units and data items

`unit_of_measure="E"` (English, default) or `"M"` (metric). Available data
item codes are in `cimis.constants` (e.g. `DAY_ASCE_ETO`, `HLY_AIR_TMP`,
`DAILY_DATA_ITEMS`, `HOURLY_DATA_ITEMS`, `SPATIAL_DATA_ITEMS`). Omit
`data_items` to receive the API defaults for the request type.

### Errors

API failures raise typed exceptions carrying `http_status` and the CIMIS
`error_code` (e.g. `ERR1012`):

- `CimisAuthError` — invalid/missing app key (HTTP 401/403, ERR1006)
- `CimisBadRequestError` — bad dates, units, targets (HTTP 400)
- `CimisDataVolumeError` — request exceeds record limits (ERR2112); split the
  date range or reduce targets
- `CimisNotFoundError` — unknown station, unsupported zip, coordinate outside
  California (HTTP 404)

Note: CIMIS data begins 1982-06-07; spatial queries are limited to 366 days;
hourly data is only available from the Weather Station Network.

## Development

```bash
pip install -e ".[dev]"
pytest
```
