"""Tests for response caching."""

import datetime as dt
import json
from unittest.mock import MagicMock

import pytest

from cimis import CimisClient, ResponseCache

PAST_PAYLOAD = {
    "Data": {
        "Providers": [
            {
                "Name": "cimis", "Type": "station", "Owner": "water.ca.gov",
                "Records": [
                    {
                        "Date": "2020-01-01", "Julian": "1", "Station": "2",
                        "Standard": "english", "ZipCodes": "93624", "Scope": "daily",
                        "DayAsceEto": {"Value": "0.05", "Qc": " ", "Unit": "(in)"},
                    }
                ],
            }
        ]
    }
}

STATIONS_PAYLOAD = {"Stations": [{"StationNbr": "2", "Name": "FivePoints", "City": "Five Points"}]}


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload
        self.status_code = 200
        self.ok = True
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


def make_client(tmp_path, payload):
    session = MagicMock()
    session.get.return_value = FakeResponse(payload)
    cache = ResponseCache(tmp_path / "cache.sqlite")
    client = CimisClient(app_key="k", session=session, cache=cache)
    return client, session, cache


def test_historical_weather_is_cached(tmp_path):
    client, session, cache = make_client(tmp_path, PAST_PAYLOAD)
    r1 = client.get_data_by_station_numbers(2, "2020-01-01", "2020-01-02")
    r2 = client.get_data_by_station_numbers(2, "2020-01-01", "2020-01-02")
    assert session.get.call_count == 1
    assert r1[0].value("day-asce-eto") == r2[0].value("day-asce-eto") == 0.05

    # A different request misses the cache
    client.get_data_by_station_numbers(2, "2020-01-01", "2020-01-03")
    assert session.get.call_count == 2


def test_cache_persists_across_clients(tmp_path):
    client, session, _ = make_client(tmp_path, PAST_PAYLOAD)
    client.get_data_by_station_numbers(2, "2020-01-01", "2020-01-02")

    session2 = MagicMock()
    client2 = CimisClient(app_key="k", session=session2, cache=tmp_path / "cache.sqlite")
    records = client2.get_data_by_station_numbers(2, "2020-01-01", "2020-01-02")
    session2.get.assert_not_called()
    assert records[0].value("day-asce-eto") == 0.05


def test_current_range_not_cached(tmp_path):
    client, session, _ = make_client(tmp_path, PAST_PAYLOAD)
    today = dt.date.today().isoformat()
    client.get_data_by_station_numbers(2, "2020-01-01", today)
    client.get_data_by_station_numbers(2, "2020-01-01", today)
    assert session.get.call_count == 2


def test_metadata_cached_with_ttl(tmp_path):
    client, session, cache = make_client(tmp_path, STATIONS_PAYLOAD)
    client.get_all_stations()
    client.get_all_stations()
    assert session.get.call_count == 1

    # Expired TTL falls through to the API
    expired = CimisClient(app_key="k", session=session, cache=cache, metadata_ttl=0)
    expired.get_all_stations()
    assert session.get.call_count == 2


def test_cache_clear(tmp_path):
    client, session, cache = make_client(tmp_path, PAST_PAYLOAD)
    client.get_data_by_station_numbers(2, "2020-01-01", "2020-01-02")
    assert cache.clear() == 1
    client.get_data_by_station_numbers(2, "2020-01-01", "2020-01-02")
    assert session.get.call_count == 2


def test_no_cache_by_default(tmp_path):
    session = MagicMock()
    session.get.return_value = FakeResponse(PAST_PAYLOAD)
    client = CimisClient(app_key="k", session=session)
    client.get_data_by_station_numbers(2, "2020-01-01", "2020-01-02")
    client.get_data_by_station_numbers(2, "2020-01-01", "2020-01-02")
    assert session.get.call_count == 2
