"""Python client for the CIMIS (California Irrigation Management Information
System) REST Web API.

Quick start::

    from cimis import CimisClient

    client = CimisClient(app_key="your-app-key")  # or set CIMIS_APP_KEY
    records = client.get_data_by_station_numbers(
        [2, 80], start_date="2024-01-01", end_date="2024-01-31"
    )
"""

from . import constants, geo
from .cache import ResponseCache
from .client import CimisClient, DEFAULT_BASE_URL
from .geo import (
    NearbyStation,
    haversine_km,
    nearest_stations,
    records_to_geodataframe,
    records_to_geojson,
    stations_in_bbox,
    stations_to_geodataframe,
    stations_to_geojson,
    stations_within,
)
from .exceptions import (
    CimisApiError,
    CimisAuthError,
    CimisBadRequestError,
    CimisDataVolumeError,
    CimisError,
    CimisNotFoundError,
)
from .models import (
    DataValue,
    SpatialZipCode,
    Station,
    StationZipCode,
    WeatherRecord,
    to_dataframe,
)

__version__ = "0.1.0"

__all__ = [
    "CimisClient",
    "DEFAULT_BASE_URL",
    "ResponseCache",
    "NearbyStation",
    "haversine_km",
    "nearest_stations",
    "stations_within",
    "stations_in_bbox",
    "stations_to_geojson",
    "records_to_geojson",
    "stations_to_geodataframe",
    "records_to_geodataframe",
    "geo",
    "CimisError",
    "CimisApiError",
    "CimisAuthError",
    "CimisBadRequestError",
    "CimisDataVolumeError",
    "CimisNotFoundError",
    "DataValue",
    "WeatherRecord",
    "Station",
    "StationZipCode",
    "SpatialZipCode",
    "to_dataframe",
    "constants",
    "__version__",
]
