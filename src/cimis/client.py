"""HTTP client for the CIMIS REST Web API.

Documentation: https://www.cimis.water.ca.gov/web-api/rest-api/latest

All requests are authenticated with an application key passed in the
``Ocp-Apim-Subscription-Key`` header. Register at https://www.cimis.water.ca.gov
to obtain one.
"""

from __future__ import annotations

import os
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Union

import requests

from . import geo
from .cache import ResponseCache
from .exceptions import (
    CimisApiError,
    CimisAuthError,
    CimisBadRequestError,
    CimisDataVolumeError,
    CimisError,
    CimisNotFoundError,
)
from .models import (
    SpatialZipCode,
    Station,
    StationZipCode,
    WeatherRecord,
)

DEFAULT_BASE_URL = "https://et.water.ca.gov"
APP_KEY_ENV_VAR = "CIMIS_APP_KEY"

DateLike = Union[str, date, datetime]
Coordinate = Union[str, Tuple[float, float]]
Address = Union[str, Tuple[str, str]]

_ERR_CODE_RE = re.compile(r"ERR\d{4}")


def _format_date(value: DateLike) -> str:
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _join(values: Union[str, int, Iterable[Union[str, int]]]) -> str:
    if isinstance(values, (str, int)):
        return str(values)
    return ",".join(str(v) for v in values)


def _format_coordinates(coordinates: Union[Coordinate, Sequence[Coordinate]]) -> str:
    if isinstance(coordinates, str) or (
        isinstance(coordinates, tuple) and len(coordinates) == 2 and not isinstance(coordinates[0], str)
    ):
        coordinates = [coordinates]  # type: ignore[list-item]
    parts = []
    for coord in coordinates:
        if isinstance(coord, str):
            parts.append(coord)
        else:
            lat, lng = coord
            parts.append(f"lat={lat},lng={lng}")
    return ";".join(parts)


def _format_addresses(addresses: Union[Address, Sequence[Address]]) -> str:
    if isinstance(addresses, (str, tuple)):
        addresses = [addresses]  # type: ignore[list-item]
    parts = []
    for entry in addresses:
        if isinstance(entry, str):
            parts.append(entry if entry.startswith("addr-name=") else f"addr-name={entry},addr={entry}")
        else:
            name, addr = entry
            parts.append(f"addr-name={name},addr={addr}")
    return ";".join(parts)


class CimisClient:
    """Client for the CIMIS Web API.

    Args:
        app_key: Your CIMIS application key. Falls back to the
            ``CIMIS_APP_KEY`` environment variable.
        base_url: API host, defaults to ``https://et.water.ca.gov``.
        timeout: Per-request timeout in seconds.
        session: Optional pre-configured :class:`requests.Session`.
        cache: Enable on-disk response caching. ``True`` uses
            ``~/.cache/cimis/cache.sqlite``; a path or
            :class:`~cimis.cache.ResponseCache` may also be given. Weather
            responses whose date range is fully in the past are cached
            indefinitely (historical CIMIS data is immutable); station and
            zip code metadata is cached for ``metadata_ttl`` seconds.
        metadata_ttl: Maximum age in seconds for cached metadata responses.

    Example::

        from cimis import CimisClient

        client = CimisClient(app_key="...")
        records = client.get_data_by_station_numbers(
            [2, 80], start_date="2024-01-01", end_date="2024-01-31"
        )
        for rec in records:
            print(rec.date, rec.station, rec.value("day-asce-eto"))
    """

    def __init__(
        self,
        app_key: Optional[str] = None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 60.0,
        session: Optional[requests.Session] = None,
        cache: Union[bool, str, Path, ResponseCache, None] = None,
        metadata_ttl: float = 86400.0,
    ):
        self.app_key = app_key or os.environ.get(APP_KEY_ENV_VAR)
        if not self.app_key:
            raise CimisAuthError(
                "A CIMIS application key is required. Pass app_key= or set the "
                f"{APP_KEY_ENV_VAR} environment variable. Register for a key at "
                "https://www.cimis.water.ca.gov"
            )
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._session = session or requests.Session()
        self.metadata_ttl = metadata_ttl
        if isinstance(cache, ResponseCache):
            self.cache: Optional[ResponseCache] = cache
        elif cache is True:
            self.cache = ResponseCache()
        elif cache:
            self.cache = ResponseCache(cache)
        else:
            self.cache = None
        self._stations_memo: Optional[List[Station]] = None

    # ------------------------------------------------------------------ #
    # Weather data
    # ------------------------------------------------------------------ #

    def get_data_by_station_numbers(
        self,
        station_numbers: Union[int, str, Iterable[Union[int, str]]],
        start_date: DateLike,
        end_date: DateLike,
        *,
        hourly: bool = False,
        unit_of_measure: str = "E",
        data_items: Optional[Union[str, Iterable[str]]] = None,
    ) -> List[WeatherRecord]:
        """Daily or hourly WSN weather data for one or more station numbers."""
        params = self._weather_params(start_date, end_date, unit_of_measure, data_items)
        params["stationNbrs"] = _join(station_numbers)
        params["isHourly"] = _bool_str(hourly)
        return self._get_weather("/StationWeb/GetDataByStationNumber", params)

    def get_data_by_station_zip_codes(
        self,
        zip_codes: Union[str, Iterable[str]],
        start_date: DateLike,
        end_date: DateLike,
        *,
        hourly: bool = False,
        unit_of_measure: str = "E",
        data_items: Optional[Union[str, Iterable[str]]] = None,
    ) -> List[WeatherRecord]:
        """Daily or hourly WSN weather data for stations in the given zip codes."""
        params = self._weather_params(start_date, end_date, unit_of_measure, data_items)
        params["zipCodes"] = _join(zip_codes)
        params["isHourly"] = _bool_str(hourly)
        return self._get_weather("/StationWeb/GetDataByStationZipCodes", params)

    def get_data_by_coordinates(
        self,
        coordinates: Union[Coordinate, Sequence[Coordinate]],
        start_date: DateLike,
        end_date: DateLike,
        *,
        unit_of_measure: str = "E",
        data_items: Optional[Union[str, Iterable[str]]] = None,
    ) -> List[WeatherRecord]:
        """Daily SCS (Spatial CIMIS) data for decimal-degree coordinates.

        ``coordinates`` may be a ``(lat, lng)`` tuple, a list of tuples, or
        pre-formatted strings like ``"lat=34.99,lng=-118.34"``. Spatial data
        supports only ``day-asce-eto`` and ``day-sol-rad-avg``, and queries
        must not exceed 366 days.
        """
        params = self._weather_params(start_date, end_date, unit_of_measure, data_items)
        params["coordinates"] = _format_coordinates(coordinates)
        return self._get_weather("/SpatialWeb/GetDataBySpatialCoordinates", params)

    def get_data_by_addresses(
        self,
        addresses: Union[Address, Sequence[Address]],
        start_date: DateLike,
        end_date: DateLike,
        *,
        unit_of_measure: str = "E",
        data_items: Optional[Union[str, Iterable[str]]] = None,
    ) -> List[WeatherRecord]:
        """Daily SCS (Spatial CIMIS) data for street addresses.

        ``addresses`` may be ``(name, address)`` tuples or plain address
        strings. Spatial data supports only ``day-asce-eto`` and
        ``day-sol-rad-avg``.
        """
        params = self._weather_params(start_date, end_date, unit_of_measure, data_items)
        params["addresses"] = _format_addresses(addresses)
        return self._get_weather("/SpatialWeb/GetDataByAddresses", params)

    def get_data_by_spatial_zip_codes(
        self,
        zip_codes: Union[str, Iterable[str]],
        start_date: DateLike,
        end_date: DateLike,
        *,
        unit_of_measure: str = "E",
        data_items: Optional[Union[str, Iterable[str]]] = None,
    ) -> List[WeatherRecord]:
        """Daily SCS (Spatial CIMIS) data for California zip codes."""
        params = self._weather_params(start_date, end_date, unit_of_measure, data_items)
        params["zipCodes"] = _join(zip_codes)
        params["isHourly"] = "false"  # SCS has no hourly data
        return self._get_weather("/SpatialWeb/GetDataBySpatialZipCodes", params)

    def get_data_by_zip_codes(
        self,
        zip_codes: Union[str, Iterable[str]],
        start_date: DateLike,
        end_date: DateLike,
        *,
        hourly: bool = False,
        unit_of_measure: str = "E",
        prefer: str = "SCS",
        data_items: Optional[Union[str, Iterable[str]]] = None,
    ) -> List[WeatherRecord]:
        """Weather data by zip code from either provider (WSN and/or SCS).

        For each zip code the API picks the provider based on support and the
        ``prefer`` flag ("SCS" or "WSN"). Hourly requests are always served
        by the WSN since SCS has no hourly data.
        """
        params = self._weather_params(start_date, end_date, unit_of_measure, data_items)
        params["zipCodes"] = _join(zip_codes)
        params["isHourly"] = _bool_str(hourly)
        params["prefer"] = prefer
        return self._get_weather("/GeoStationWeb/GetDataByGeoStationZipCodes", params)

    # ------------------------------------------------------------------ #
    # Station metadata
    # ------------------------------------------------------------------ #

    def get_all_stations(self) -> List[Station]:
        """All CIMIS weather stations (active and inactive)."""
        payload = self._get("/StationWeb/GetAllStations", {}, cache_policy="ttl")
        return [Station.from_json(s) for s in payload.get("Stations", [])]

    def get_station(self, station_number: Union[int, str]) -> Optional[Station]:
        """A single station by its station number, or None if absent."""
        payload = self._get(
            "/StationWeb/GetStationByStationNumber",
            {"stationNbr": str(station_number)},
            cache_policy="ttl",
        )
        stations = payload.get("Stations", [])
        return Station.from_json(stations[0]) if stations else None

    # ------------------------------------------------------------------ #
    # Zip code support lists
    # ------------------------------------------------------------------ #

    def get_all_station_zip_codes(self) -> List[StationZipCode]:
        """All zip codes supported by the Weather Station Network."""
        payload = self._get("/StationWeb/GetAllStationsZipCodes", {}, cache_policy="ttl")
        return [StationZipCode.from_json(z) for z in payload.get("ZipCodes", [])]

    def get_station_zip_code_info(self, zip_code: str) -> List[StationZipCode]:
        """WSN station/zip associations for a single zip code."""
        payload = self._get(
            "/StationWeb/GetStationZipCodeInfoByZipCode",
            {"zipCode": str(zip_code)},
            cache_policy="ttl",
        )
        return [StationZipCode.from_json(z) for z in payload.get("ZipCodes", [])]

    def get_all_spatial_zip_codes(self) -> List[SpatialZipCode]:
        """All zip codes supported by the Spatial CIMIS System."""
        payload = self._get("/SpatialWeb/GetAllSpatialZipCodes", {}, cache_policy="ttl")
        return [SpatialZipCode.from_json(z) for z in payload.get("ZipCodes", [])]

    def get_spatial_zip_code_info(self, zip_code: str) -> List[SpatialZipCode]:
        """SCS support details for a single zip code."""
        payload = self._get(
            "/SpatialWeb/GetSpatialZipCodeInfoByZipCode",
            {"zipCode": str(zip_code)},
            cache_policy="ttl",
        )
        return [SpatialZipCode.from_json(z) for z in payload.get("ZipCodes", [])]

    # ------------------------------------------------------------------ #
    # Geospatial conveniences
    # ------------------------------------------------------------------ #

    def _stations(self, refresh: bool = False) -> List[Station]:
        """Station list memoized for the lifetime of the client."""
        if self._stations_memo is None or refresh:
            self._stations_memo = self.get_all_stations()
        return self._stations_memo

    def find_nearest_stations(
        self,
        lat: float,
        lng: float,
        n: int = 3,
        *,
        active_only: bool = True,
        eto_only: bool = False,
        max_distance_km: Optional[float] = None,
        refresh: bool = False,
    ) -> List[geo.NearbyStation]:
        """The ``n`` weather stations closest to a point, nearest first."""
        return geo.nearest_stations(
            self._stations(refresh),
            lat,
            lng,
            n,
            active_only=active_only,
            eto_only=eto_only,
            max_distance_km=max_distance_km,
        )

    def stations_within(
        self,
        lat: float,
        lng: float,
        radius_km: float,
        *,
        active_only: bool = True,
        eto_only: bool = False,
        refresh: bool = False,
    ) -> List[geo.NearbyStation]:
        """All weather stations within ``radius_km`` of a point, nearest first."""
        return geo.stations_within(
            self._stations(refresh),
            lat,
            lng,
            radius_km,
            active_only=active_only,
            eto_only=eto_only,
        )

    def stations_in_bbox(
        self,
        min_lat: float,
        min_lng: float,
        max_lat: float,
        max_lng: float,
        *,
        active_only: bool = True,
        eto_only: bool = False,
        refresh: bool = False,
    ) -> List[Station]:
        """All weather stations inside a bounding box."""
        return geo.stations_in_bbox(
            self._stations(refresh),
            min_lat,
            min_lng,
            max_lat,
            max_lng,
            active_only=active_only,
            eto_only=eto_only,
        )

    def get_data_near(
        self,
        lat: float,
        lng: float,
        start_date: DateLike,
        end_date: DateLike,
        *,
        hourly: bool = False,
        unit_of_measure: str = "E",
        data_items: Optional[Union[str, Iterable[str]]] = None,
        eto_only: bool = False,
        max_distance_km: Optional[float] = None,
        candidates: int = 5,
    ) -> Tuple[List[WeatherRecord], geo.NearbyStation]:
        """WSN weather data from the nearest station covering the date range.

        Walks the ``candidates`` closest stations (including inactive ones,
        which still serve their historical data), skipping any whose
        connect/disconnect dates don't span the requested range or that
        return no records, and uses the first that has data. Returns the
        records plus the :class:`~cimis.geo.NearbyStation` that served them.
        Raises :class:`~cimis.exceptions.CimisError` if no station qualifies.
        """
        start_iso, end_iso = _format_date(start_date), _format_date(end_date)
        nearby = self.find_nearest_stations(
            lat,
            lng,
            candidates,
            active_only=False,
            eto_only=eto_only,
            max_distance_km=max_distance_km,
        )
        for candidate in nearby:
            st = candidate.station
            if st.connect_date and start_iso < st.connect_date.isoformat():
                continue
            if st.disconnect_date and end_iso > st.disconnect_date.isoformat():
                continue
            records = self.get_data_by_station_numbers(
                st.station_nbr,
                start_date,
                end_date,
                hourly=hourly,
                unit_of_measure=unit_of_measure,
                data_items=data_items,
            )
            if records:
                return records, candidate
        raise CimisError(
            f"No station with data for {start_iso}..{end_iso} found near ({lat}, {lng})"
            + (f" within {max_distance_km} km" if max_distance_km is not None else "")
        )

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #

    @staticmethod
    def _weather_params(
        start_date: DateLike,
        end_date: DateLike,
        unit_of_measure: str,
        data_items: Optional[Union[str, Iterable[str]]],
    ) -> Dict[str, str]:
        unit = unit_of_measure.upper()
        if unit not in ("E", "M"):
            raise ValueError("unit_of_measure must be 'E' (English) or 'M' (Metric)")
        params = {
            "startDate": _format_date(start_date),
            "endDate": _format_date(end_date),
            "unitOfMeasure": unit,
        }
        if data_items is not None:
            params["dataItems"] = _join(data_items)
        return params

    @staticmethod
    def _weather_cache_policy(params: Dict[str, str]) -> Optional[str]:
        """Historical data (range fully in the past) never changes -> cache forever.

        Ranges touching today are left uncached: recent values may still be
        revised by CIMIS quality control.
        """
        return "immutable" if params["endDate"] < date.today().isoformat() else None

    def _get_weather(self, path: str, params: Dict[str, str]) -> List[WeatherRecord]:
        payload = self._get(path, params, cache_policy=self._weather_cache_policy(params))
        return _parse_weather(payload)

    def _get(
        self, path: str, params: Dict[str, str], cache_policy: Optional[str] = None
    ) -> Dict[str, Any]:
        if self.cache is not None and cache_policy is not None:
            key = ResponseCache.make_key(path, params)
            max_age = self.metadata_ttl if cache_policy == "ttl" else None
            cached = self.cache.get(key, max_age=max_age)
            if cached is not None:
                return cached
            payload = self._fetch(path, params)
            self.cache.set(key, path, params, payload)
            return payload
        return self._fetch(path, params)

    def _fetch(self, path: str, params: Dict[str, str]) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        headers = {
            "Ocp-Apim-Subscription-Key": self.app_key,
            "Accept": "application/json",
        }
        try:
            response = self._session.get(url, params=params, headers=headers, timeout=self.timeout)
        except requests.RequestException as exc:
            raise CimisError(f"Request to {url} failed: {exc}") from exc

        if response.ok:
            try:
                return response.json()
            except ValueError as exc:
                raise CimisApiError(
                    f"Could not decode JSON response from {url}",
                    http_status=response.status_code,
                ) from exc
        raise self._error_from_response(response)

    @staticmethod
    def _error_from_response(response: requests.Response) -> CimisApiError:
        body = response.text or ""
        match = _ERR_CODE_RE.search(body)
        error_code = match.group(0) if match else None
        message = body.strip()[:500] or response.reason or "Unknown CIMIS API error"
        status = response.status_code

        if status in (401, 403) or error_code == "ERR1006":
            return CimisAuthError(f"[HTTP {status}] {message}")
        if error_code == "ERR2112":
            return CimisDataVolumeError(message, http_status=status, error_code=error_code)
        if status == 400:
            return CimisBadRequestError(message, http_status=status, error_code=error_code)
        if status == 404:
            return CimisNotFoundError(message, http_status=status, error_code=error_code)
        return CimisApiError(message, http_status=status, error_code=error_code)


def _bool_str(value: bool) -> str:
    return "true" if value else "false"


def _parse_weather(payload: Dict[str, Any]) -> List[WeatherRecord]:
    records: List[WeatherRecord] = []
    providers = (payload.get("Data") or {}).get("Providers") or []
    for provider in providers:
        ptype = provider.get("Type")
        for rec in provider.get("Records") or []:
            records.append(WeatherRecord.from_json(rec, provider=ptype))
    return records
