"""Tests for geospatial helpers and client geo conveniences."""

import datetime as dt
import json
from unittest.mock import MagicMock

import pytest

from cimis import CimisClient, CimisError, geo
from cimis.models import Station, WeatherRecord

# Approximate real station locations.
FIVE_POINTS = Station(
    station_nbr=2, name="FivePoints", city="Five Points",
    is_active=True, is_eto_station=True,
    hms_latitude="36º20'10N / 36.336222", hms_longitude="-120º6'46W / -120.11291",
)
DAVIS = Station(
    station_nbr=6, name="Davis", city="Davis",
    is_active=True, is_eto_station=True,
    hms_latitude="38º32'9N / 38.535694", hms_longitude="-121º46'32W / -121.776360",
)
INACTIVE_SAC = Station(
    station_nbr=131, name="Fair Oaks", city="Sacramento",
    is_active=False, is_eto_station=True,
    hms_latitude="38º38'N / 38.633", hms_longitude="-121º13'W / -121.216",
)
NO_COORDS = Station(station_nbr=999, name="Mystery", city="", is_active=True)

ALL = [FIVE_POINTS, DAVIS, INACTIVE_SAC, NO_COORDS]

SACRAMENTO = (38.5816, -121.4944)


def test_haversine_known_distance():
    # Sacramento to Los Angeles is ~580 km
    d = geo.haversine_km(38.5816, -121.4944, 34.0522, -118.2437)
    assert d == pytest.approx(580, abs=10)
    assert geo.haversine_km(38.5, -121.5, 38.5, -121.5) == 0.0


def test_parse_coordinate():
    assert geo.parse_coordinate("lat=38.57,lng=-121.49") == (38.57, -121.49)
    assert geo.parse_coordinate("lat=38.576429909364,lng=-121.493714852954") == pytest.approx(
        (38.576429909364, -121.493714852954)
    )
    assert geo.parse_coordinate("") is None
    assert geo.parse_coordinate("garbage") is None


def test_nearest_stations_orders_and_filters():
    lat, lng = SACRAMENTO
    nearest = geo.nearest_stations(ALL, lat, lng, n=2)
    assert [ns.station.station_nbr for ns in nearest] == [6, 2]  # Davis first
    assert nearest[0].distance_km < 30
    assert nearest[0].distance_miles == pytest.approx(nearest[0].distance_km * 0.621371)

    # Inactive stations included when requested; Fair Oaks is closest to Sacramento
    with_inactive = geo.nearest_stations(ALL, lat, lng, n=1, active_only=False)
    assert with_inactive[0].station.station_nbr == 131


def test_nearest_stations_max_distance():
    lat, lng = SACRAMENTO
    close = geo.nearest_stations(ALL, lat, lng, n=5, max_distance_km=50)
    assert [ns.station.station_nbr for ns in close] == [6]


def test_stations_within_radius():
    lat, lng = SACRAMENTO
    hits = geo.stations_within(ALL, lat, lng, 300)
    assert [ns.station.station_nbr for ns in hits] == [6, 2]


def test_stations_in_bbox():
    # Central Valley box containing Davis but not Five Points
    hits = geo.stations_in_bbox(ALL, 38.0, -122.5, 39.0, -121.0)
    assert [st.station_nbr for st in hits] == [6]


def test_stations_to_geojson():
    gj = geo.stations_to_geojson(ALL)
    assert gj["type"] == "FeatureCollection"
    assert len(gj["features"]) == 3  # NO_COORDS skipped
    feat = next(f for f in gj["features"] if f["properties"]["station_nbr"] == 6)
    lng, lat = feat["geometry"]["coordinates"]
    assert lat == pytest.approx(38.535694)
    assert lng == pytest.approx(-121.776360)
    json.dumps(gj)  # must be serializable


def make_record(**kwargs):
    defaults = dict(date=dt.date(2024, 6, 1), julian=153, scope="daily", standard="english")
    defaults.update(kwargs)
    return WeatherRecord(**defaults)


def test_records_to_geojson_spatial_and_station():
    spatial = make_record(coordinate="lat=38.57,lng=-121.49", provider="spatial")
    station_rec = make_record(station=6, provider="station")
    unlocatable = make_record(station=12345)

    gj = geo.records_to_geojson([spatial, station_rec, unlocatable], stations=ALL)
    assert len(gj["features"]) == 2
    assert gj["features"][0]["geometry"]["coordinates"] == [-121.49, 38.57]
    assert gj["features"][1]["geometry"]["coordinates"][0] == pytest.approx(-121.776360)


def test_geodataframe_export():
    pytest.importorskip("geopandas")
    gdf = geo.stations_to_geodataframe(ALL)
    assert len(gdf) == 3
    assert gdf.crs.to_epsg() == 4326

    rec = make_record(coordinate="lat=38.57,lng=-121.49")
    rec.items["day-asce-eto"] = __import__("cimis").DataValue(0.25, " ", "in")
    rgdf = geo.records_to_geodataframe([rec])
    assert rgdf.iloc[0]["day-asce-eto"] == 0.25
    assert rgdf.iloc[0].geometry.x == pytest.approx(-121.49)


# --------------------------------------------------------------------- #
# Client conveniences
# --------------------------------------------------------------------- #

STATIONS_PAYLOAD = {
    "Stations": [
        {
            "StationNbr": "6", "Name": "Davis", "City": "Davis",
            "IsActive": "True", "IsEtoStation": "True",
            "HmsLatitude": "38º32'9N / 38.535694",
            "HmsLongitude": "-121º46'32W / -121.776360",
            "ZipCodes": ["95616"],
        },
        {
            "StationNbr": "2", "Name": "FivePoints", "City": "Five Points",
            "IsActive": "True", "IsEtoStation": "True",
            "HmsLatitude": "36º20'10N / 36.336222",
            "HmsLongitude": "-120º6'46W / -120.11291",
            "ZipCodes": ["93624"],
        },
    ]
}

DATA_PAYLOAD = {
    "Data": {
        "Providers": [
            {
                "Name": "cimis", "Type": "station", "Owner": "water.ca.gov",
                "Records": [
                    {
                        "Date": "2024-06-01", "Julian": "153", "Station": "6",
                        "Standard": "english", "ZipCodes": "95616", "Scope": "daily",
                        "DayAsceEto": {"Value": "0.25", "Qc": " ", "Unit": "(in)"},
                    }
                ],
            }
        ]
    }
}


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload
        self.status_code = 200
        self.ok = True
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


def test_client_find_nearest_and_get_data_near():
    session = MagicMock()
    session.get.side_effect = [FakeResponse(STATIONS_PAYLOAD), FakeResponse(DATA_PAYLOAD)]
    client = CimisClient(app_key="k", session=session)

    records, nearest = client.get_data_near(38.58, -121.49, "2024-06-01", "2024-06-01")
    assert nearest.station.station_nbr == 6
    assert nearest.distance_km < 30
    assert records[0].value("day-asce-eto") == 0.25

    # Station list is memoized: only one GetAllStations call
    urls = [c.args[0] for c in session.get.call_args_list]
    assert sum("GetAllStations" in u for u in urls) == 1

    nearby = client.find_nearest_stations(38.58, -121.49, n=1)
    assert nearby[0].station.name == "Davis"
    assert sum("GetAllStations" in c.args[0] for c in session.get.call_args_list) == 1


def test_client_get_data_near_no_station_in_range():
    session = MagicMock()
    session.get.return_value = FakeResponse(STATIONS_PAYLOAD)
    client = CimisClient(app_key="k", session=session)
    with pytest.raises(CimisError, match="No station with data"):
        client.get_data_near(38.58, -121.49, "2024-06-01", "2024-06-01", max_distance_km=1)


def test_client_get_data_near_skips_station_without_coverage():
    # Nearest station (Davis) connected after the requested range; the next
    # nearest (FivePoints) must serve the data instead.
    stations = {
        "Stations": [
            dict(STATIONS_PAYLOAD["Stations"][0], ConnectDate="11/1/2024"),
            STATIONS_PAYLOAD["Stations"][1],
        ]
    }
    session = MagicMock()
    session.get.side_effect = [FakeResponse(stations), FakeResponse(DATA_PAYLOAD)]
    client = CimisClient(app_key="k", session=session)

    _, nearest = client.get_data_near(38.58, -121.49, "2024-06-01", "2024-06-01")
    assert nearest.station.station_nbr == 2
    data_call = session.get.call_args_list[1]
    assert data_call.kwargs["params"]["stationNbrs"] == "2"


def test_client_stations_within_and_bbox():
    session = MagicMock()
    session.get.return_value = FakeResponse(STATIONS_PAYLOAD)
    client = CimisClient(app_key="k", session=session)
    assert [ns.station.station_nbr for ns in client.stations_within(38.58, -121.49, 100)] == [6]
    assert [st.station_nbr for st in client.stations_in_bbox(36.0, -121.0, 37.0, -119.0)] == [2]
