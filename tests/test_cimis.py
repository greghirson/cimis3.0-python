"""Tests for the cimis client, run against canned API responses.

The response payloads are taken from the official documentation examples at
https://www.cimis.water.ca.gov/web-api/rest-api/latest
"""

import datetime as dt
import json
from unittest.mock import MagicMock

import pytest

from cimis import (
    CimisAuthError,
    CimisBadRequestError,
    CimisClient,
    CimisDataVolumeError,
    CimisNotFoundError,
    constants,
    to_dataframe,
)

DAILY_STATION_PAYLOAD = {
    "Data": {
        "Providers": [
            {
                "Name": "cimis",
                "Type": "station",
                "Owner": "water.ca.gov",
                "Records": [
                    {
                        "Date": "2010-01-01",
                        "Julian": "1",
                        "Station": "127",
                        "Standard": "english",
                        "ZipCodes": "92275",
                        "Scope": "daily",
                        "DayAirTmpAvg": {"Value": "55.22", "Qc": " ", "Unit": "(F)"},
                        "DayAsceEto": {"Value": None, "Qc": "N", "Unit": "(in)"},
                    },
                    {
                        "Date": "2010-01-02",
                        "Julian": "2",
                        "Station": "127",
                        "Standard": "english",
                        "ZipCodes": "92275",
                        "Scope": "daily",
                        "DayAirTmpAvg": {"Value": "55.02", "Qc": " ", "Unit": "(F)"},
                        "DayAsceEto": {"Value": None, "Qc": "N", "Unit": "(in)"},
                    },
                ],
            }
        ]
    }
}

HOURLY_PAYLOAD = {
    "Data": {
        "Providers": [
            {
                "Name": "cimis",
                "Type": "station",
                "Owner": "water.ca.gov",
                "Records": [
                    {
                        "Date": "2010-01-01",
                        "Julian": "1",
                        "Hour": "0100",
                        "Station": "109",
                        "Standard": "english",
                        "ZipCodes": "94592, 94591, 94503",
                        "Scope": "hourly",
                        "HlyAirTmp": {"Value": "49.06", "Qc": " ", "Unit": "(F)"},
                        "HlyWindDir": {"Value": "4.36", "Qc": " ", "Unit": "(º)"},
                    }
                ],
            }
        ]
    }
}

SPATIAL_PAYLOAD = {
    "Data": {
        "Providers": [
            {
                "Name": "cimis",
                "Type": "spatial",
                "Owner": "water.ca.gov",
                "Records": [
                    {
                        "Date": "2010-01-01",
                        "Julian": "1",
                        "Standard": "english",
                        "ZipCodes": "93560",
                        "Coordinate": "lat=34.99,lng=-118.34",
                        "Address": "",
                        "Scope": "daily",
                        "DayAsceEto": {"Value": "0.06", "Qc": " ", "Unit": "(in)"},
                        "DaySolRadAvg": {"Value": "257.13", "Qc": " ", "Unit": "(Ly/day)"},
                    }
                ],
            }
        ]
    }
}

STATIONS_PAYLOAD = {
    "Stations": [
        {
            "StationNbr": "2",
            "Name": "FivePoints",
            "City": "Five Points",
            "RegionalOffice": "South Central Region Office",
            "County": "Fresno",
            "ConnectDate": "6/7/1982",
            "DisconnectDate": "12/31/2050",
            "IsActive": "True",
            "IsEtoStation": "True",
            "Elevation": "285",
            "GroundCover": "Grass",
            "HmsLatitude": "36º20'10N / 36.336222",
            "HmsLongitude": "-120º6'46W / -120.11291",
            "ZipCodes": ["93624"],
            "SitingDesc": "",
        }
    ]
}

STATION_ZIP_PAYLOAD = {
    "ZipCodes": [
        {
            "StationNbr": 99,
            "ZipCode": "90401",
            "ConnectDate": "12/11/1992",
            "DisconnectDate": "5/8/2050",
            "IsActive": "True",
        }
    ]
}

SPATIAL_ZIP_PAYLOAD = {
    "ZipCodes": [
        {
            "ZipCode": "85328",
            "ConnectDate": "2/20/2003",
            "DisconnectDate": "12/31/2030",
            "IsActive": "True",
        }
    ]
}


class FakeResponse:
    def __init__(self, payload=None, status_code=200, text=""):
        self._payload = payload
        self.status_code = status_code
        self.text = text if text else (json.dumps(payload) if payload else "")
        self.reason = ""
        self.ok = status_code < 400

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


def make_client(response):
    session = MagicMock()
    session.get.return_value = response
    client = CimisClient(app_key="test-key", session=session)
    return client, session


def request_kwargs(session):
    return session.get.call_args.kwargs


def test_requires_app_key(monkeypatch):
    monkeypatch.delenv("CIMIS_APP_KEY", raising=False)
    with pytest.raises(CimisAuthError):
        CimisClient()


def test_app_key_from_env(monkeypatch):
    monkeypatch.setenv("CIMIS_APP_KEY", "env-key")
    assert CimisClient().app_key == "env-key"


def test_daily_station_request():
    client, session = make_client(FakeResponse(DAILY_STATION_PAYLOAD))
    records = client.get_data_by_station_numbers(
        [2, 8, 127],
        start_date=dt.date(2010, 1, 1),
        end_date="2010-01-05",
        data_items=[constants.DAY_AIR_TMP_AVG, constants.DAY_ASCE_ETO],
    )

    url = session.get.call_args.args[0]
    assert url == "https://et.water.ca.gov/StationWeb/GetDataByStationNumber"
    kwargs = request_kwargs(session)
    assert kwargs["params"] == {
        "stationNbrs": "2,8,127",
        "startDate": "2010-01-01",
        "endDate": "2010-01-05",
        "unitOfMeasure": "E",
        "isHourly": "false",
        "dataItems": "day-air-tmp-avg,day-asce-eto",
    }
    assert kwargs["headers"]["Ocp-Apim-Subscription-Key"] == "test-key"
    assert kwargs["headers"]["Accept"] == "application/json"

    assert len(records) == 2
    rec = records[0]
    assert rec.date == dt.date(2010, 1, 1)
    assert rec.station == 127
    assert rec.scope == "daily"
    assert rec.provider == "station"
    assert rec.zip_codes == ["92275"]
    assert rec["day-air-tmp-avg"].value == 55.22
    assert rec["day-air-tmp-avg"].unit == "F"
    assert rec["day-asce-eto"].value is None
    assert rec["day-asce-eto"].qc == "N"
    assert rec.value("day-air-tmp-avg") == 55.22
    assert rec.value("day-precip") is None


def test_hourly_record_timestamp():
    client, session = make_client(FakeResponse(HOURLY_PAYLOAD))
    records = client.get_data_by_station_zip_codes(
        ["93624", "94503"], "2010-01-01", "2010-01-05", hourly=True
    )
    assert request_kwargs(session)["params"]["isHourly"] == "true"
    assert request_kwargs(session)["params"]["zipCodes"] == "93624,94503"
    rec = records[0]
    assert rec.hour == "0100"
    assert rec.timestamp == dt.datetime(2010, 1, 1, 1, 0)
    assert rec.zip_codes == ["94592", "94591", "94503"]


def test_coordinates_formatting():
    client, session = make_client(FakeResponse(SPATIAL_PAYLOAD))
    records = client.get_data_by_coordinates(
        [(34.99, -118.34), (36.45, -118.16)], "2010-01-01", "2010-01-05"
    )
    params = request_kwargs(session)["params"]
    assert params["coordinates"] == "lat=34.99,lng=-118.34;lat=36.45,lng=-118.16"
    rec = records[0]
    assert rec.coordinate == "lat=34.99,lng=-118.34"
    assert rec.provider == "spatial"
    assert rec.value("day-asce-eto") == 0.06


def test_single_coordinate_tuple():
    client, session = make_client(FakeResponse(SPATIAL_PAYLOAD))
    client.get_data_by_coordinates((34.99, -118.34), "2010-01-01", "2010-01-02")
    assert request_kwargs(session)["params"]["coordinates"] == "lat=34.99,lng=-118.34"


def test_addresses_formatting():
    client, session = make_client(FakeResponse(SPATIAL_PAYLOAD))
    client.get_data_by_addresses(
        [("State Capitol", "1315 10th Street Sacramento, CA 95814")],
        "2024-04-17",
        "2024-04-18",
        unit_of_measure="m",
    )
    params = request_kwargs(session)["params"]
    assert params["addresses"] == "addr-name=State Capitol,addr=1315 10th Street Sacramento, CA 95814"
    assert params["unitOfMeasure"] == "M"


def test_geo_station_zip_codes_prefer():
    client, session = make_client(FakeResponse(SPATIAL_PAYLOAD))
    client.get_data_by_zip_codes(["93624"], "2012-01-01", "2012-01-05", prefer="WSN")
    url = session.get.call_args.args[0]
    assert url.endswith("/GeoStationWeb/GetDataByGeoStationZipCodes")
    assert request_kwargs(session)["params"]["prefer"] == "WSN"


def test_invalid_unit_rejected_locally():
    client, _ = make_client(FakeResponse(DAILY_STATION_PAYLOAD))
    with pytest.raises(ValueError):
        client.get_data_by_station_numbers(2, "2010-01-01", "2010-01-02", unit_of_measure="X")


def test_get_all_stations():
    client, session = make_client(FakeResponse(STATIONS_PAYLOAD))
    stations = client.get_all_stations()
    assert session.get.call_args.args[0].endswith("/StationWeb/GetAllStations")
    st = stations[0]
    assert st.station_nbr == 2
    assert st.name == "FivePoints"
    assert st.is_active is True
    assert st.connect_date == dt.date(1982, 6, 7)
    assert st.latitude == pytest.approx(36.336222)
    assert st.longitude == pytest.approx(-120.11291)
    assert st.zip_codes == ["93624"]


def test_get_station_single():
    client, session = make_client(FakeResponse(STATIONS_PAYLOAD))
    st = client.get_station(2)
    assert request_kwargs(session)["params"] == {"stationNbr": "2"}
    assert st.station_nbr == 2


def test_station_zip_codes():
    client, _ = make_client(FakeResponse(STATION_ZIP_PAYLOAD))
    zips = client.get_all_station_zip_codes()
    assert zips[0].station_nbr == 99
    assert zips[0].zip_code == "90401"
    assert zips[0].is_active is True


def test_spatial_zip_codes():
    client, _ = make_client(FakeResponse(SPATIAL_ZIP_PAYLOAD))
    zips = client.get_all_spatial_zip_codes()
    assert zips[0].zip_code == "85328"
    assert zips[0].connect_date == dt.date(2003, 2, 20)


def test_403_raises_auth_error():
    client, _ = make_client(FakeResponse(status_code=403, text="ERR1006-INVALID API KEY"))
    with pytest.raises(CimisAuthError):
        client.get_data_by_station_numbers(2, "2010-01-01", "2010-01-02")


def test_404_raises_not_found_with_code():
    client, _ = make_client(
        FakeResponse(status_code=404, text="[ERR1019-STATION NOT FOUND] Station 9999")
    )
    with pytest.raises(CimisNotFoundError) as excinfo:
        client.get_data_by_station_numbers(9999, "2010-01-01", "2010-01-02")
    assert excinfo.value.error_code == "ERR1019"
    assert excinfo.value.http_status == 404


def test_400_data_volume_error():
    client, _ = make_client(
        FakeResponse(status_code=400, text="[ERR2112-DATA VOLUME VIOLATION] too many records")
    )
    with pytest.raises(CimisDataVolumeError):
        client.get_data_by_station_numbers(2, "1982-06-07", "2025-01-01")


def test_400_bad_request():
    client, _ = make_client(
        FakeResponse(status_code=400, text="[ERR1012-DATE ORDER FAULT] start > end")
    )
    with pytest.raises(CimisBadRequestError) as excinfo:
        client.get_data_by_station_numbers(2, "2010-02-01", "2010-01-01")
    assert excinfo.value.error_code == "ERR1012"


def test_to_dataframe():
    pd = pytest.importorskip("pandas")
    client, _ = make_client(FakeResponse(DAILY_STATION_PAYLOAD))
    records = client.get_data_by_station_numbers(127, "2010-01-01", "2010-01-02")
    df = to_dataframe(records)
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 2
    assert df["day-air-tmp-avg"].tolist() == [55.22, 55.02]
    assert df["day-asce-eto-qc"].tolist() == ["N", "N"]
