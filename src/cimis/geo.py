"""Geospatial helpers for CIMIS stations and weather records.

Distance math is pure Python (haversine); GeoJSON export has no
dependencies. :func:`to_geodataframe` requires the ``geo`` extra
(geopandas).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .models import Station, WeatherRecord

EARTH_RADIUS_KM = 6371.0088

_COORD_RE = re.compile(r"lat=(-?\d+(?:\.\d+)?),\s*lng=(-?\d+(?:\.\d+)?)")


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance between two points in kilometers."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def parse_coordinate(coordinate: str) -> Optional[Tuple[float, float]]:
    """Parse a CIMIS coordinate string like ``"lat=38.57,lng=-121.49"``."""
    match = _COORD_RE.search(coordinate or "")
    if not match:
        return None
    return float(match.group(1)), float(match.group(2))


@dataclass(frozen=True)
class NearbyStation:
    """A station together with its distance from a query point."""

    station: Station
    distance_km: float

    @property
    def distance_miles(self) -> float:
        return self.distance_km * 0.621371


def _located(stations: Iterable[Station]) -> List[Tuple[Station, float, float]]:
    """Stations that have parseable decimal coordinates."""
    out = []
    for st in stations:
        lat, lng = st.latitude, st.longitude
        if lat is not None and lng is not None:
            out.append((st, lat, lng))
    return out


def _filter(
    stations: Iterable[Station], active_only: bool, eto_only: bool
) -> List[Station]:
    return [
        st
        for st in stations
        if (not active_only or st.is_active) and (not eto_only or st.is_eto_station)
    ]


def nearest_stations(
    stations: Iterable[Station],
    lat: float,
    lng: float,
    n: int = 3,
    *,
    active_only: bool = True,
    eto_only: bool = False,
    max_distance_km: Optional[float] = None,
) -> List[NearbyStation]:
    """The ``n`` stations closest to a point, nearest first.

    Stations without parseable coordinates are skipped.
    """
    candidates = _located(_filter(stations, active_only, eto_only))
    ranked = sorted(
        (NearbyStation(st, haversine_km(lat, lng, slat, slng)) for st, slat, slng in candidates),
        key=lambda ns: ns.distance_km,
    )
    if max_distance_km is not None:
        ranked = [ns for ns in ranked if ns.distance_km <= max_distance_km]
    return ranked[:n]


def stations_within(
    stations: Iterable[Station],
    lat: float,
    lng: float,
    radius_km: float,
    *,
    active_only: bool = True,
    eto_only: bool = False,
) -> List[NearbyStation]:
    """All stations within ``radius_km`` of a point, nearest first."""
    return nearest_stations(
        stations,
        lat,
        lng,
        n=10**9,
        active_only=active_only,
        eto_only=eto_only,
        max_distance_km=radius_km,
    )


def stations_in_bbox(
    stations: Iterable[Station],
    min_lat: float,
    min_lng: float,
    max_lat: float,
    max_lng: float,
    *,
    active_only: bool = True,
    eto_only: bool = False,
) -> List[Station]:
    """All stations inside a bounding box."""
    return [
        st
        for st, lat, lng in _located(_filter(stations, active_only, eto_only))
        if min_lat <= lat <= max_lat and min_lng <= lng <= max_lng
    ]


# --------------------------------------------------------------------- #
# GeoJSON / geopandas export
# --------------------------------------------------------------------- #


def _station_properties(station: Station) -> Dict[str, Any]:
    return {
        "station_nbr": station.station_nbr,
        "name": station.name,
        "city": station.city,
        "county": station.county,
        "regional_office": station.regional_office,
        "is_active": station.is_active,
        "is_eto_station": station.is_eto_station,
        "elevation": station.elevation,
        "ground_cover": station.ground_cover,
        "connect_date": station.connect_date.isoformat() if station.connect_date else None,
        "disconnect_date": station.disconnect_date.isoformat() if station.disconnect_date else None,
        "zip_codes": ",".join(station.zip_codes),
    }


def stations_to_geojson(stations: Iterable[Station]) -> Dict[str, Any]:
    """Stations as a GeoJSON FeatureCollection (Point geometry, WGS84).

    Stations without parseable coordinates are skipped.
    """
    features = [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lng, lat]},
            "properties": _station_properties(st),
        }
        for st, lat, lng in _located(stations)
    ]
    return {"type": "FeatureCollection", "features": features}


def _record_point(
    record: WeatherRecord, station_coords: Dict[int, Tuple[float, float]]
) -> Optional[Tuple[float, float]]:
    """(lat, lng) for a record: its own coordinate, else its station's."""
    if record.coordinate:
        parsed = parse_coordinate(record.coordinate)
        if parsed:
            return parsed
    if record.station is not None:
        return station_coords.get(record.station)
    return None


def _station_coord_index(
    stations: Optional[Iterable[Station]],
) -> Dict[int, Tuple[float, float]]:
    if not stations:
        return {}
    return {st.station_nbr: (lat, lng) for st, lat, lng in _located(stations)}


def records_to_geojson(
    records: Iterable[WeatherRecord],
    stations: Optional[Iterable[Station]] = None,
) -> Dict[str, Any]:
    """Weather records as a GeoJSON FeatureCollection.

    Spatial (SCS) records carry their own coordinate. Station (WSN) records
    do not, so pass ``stations`` (e.g. from ``client.get_all_stations()``)
    to locate them by station number. Records that cannot be located are
    skipped. Data item values become feature properties.
    """
    coords = _station_coord_index(stations)
    features = []
    for rec in records:
        point = _record_point(rec, coords)
        if point is None:
            continue
        lat, lng = point
        props: Dict[str, Any] = {
            "date": rec.date.isoformat() if rec.date else None,
            "hour": rec.hour,
            "scope": rec.scope,
            "station": rec.station,
            "standard": rec.standard,
            "provider": rec.provider,
            "address": rec.address,
        }
        for code, dv in rec.items.items():
            props[code] = dv.value
            props[f"{code}-qc"] = dv.qc
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lng, lat]},
                "properties": props,
            }
        )
    return {"type": "FeatureCollection", "features": features}


def stations_to_geodataframe(stations: Sequence[Station]):
    """Stations as a geopandas GeoDataFrame (requires the ``geo`` extra)."""
    import geopandas as gpd
    from shapely.geometry import Point

    located = _located(stations)
    rows = [_station_properties(st) for st, _, _ in located]
    geometry = [Point(lng, lat) for _, lat, lng in located]
    return gpd.GeoDataFrame(rows, geometry=geometry, crs="EPSG:4326")


def records_to_geodataframe(
    records: Sequence[WeatherRecord],
    stations: Optional[Iterable[Station]] = None,
):
    """Weather records as a geopandas GeoDataFrame (requires the ``geo`` extra).

    See :func:`records_to_geojson` for how records are located.
    """
    import geopandas as gpd
    from shapely.geometry import Point

    coords = _station_coord_index(stations)
    rows = []
    geometry = []
    for rec in records:
        point = _record_point(rec, coords)
        if point is None:
            continue
        lat, lng = point
        row: Dict[str, Any] = {
            "date": rec.date,
            "hour": rec.hour,
            "timestamp": rec.timestamp,
            "scope": rec.scope,
            "station": rec.station,
            "standard": rec.standard,
            "provider": rec.provider,
            "address": rec.address,
        }
        for code, dv in rec.items.items():
            row[code] = dv.value
            row[f"{code}-qc"] = dv.qc
        rows.append(row)
        geometry.append(Point(lng, lat))
    return gpd.GeoDataFrame(rows, geometry=geometry, crs="EPSG:4326")
