"""Typed models for CIMIS Web API responses."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Mapping, Optional

_PASCAL_RE = re.compile(r"(?<!^)(?=[A-Z])")

# Record-level metadata keys in a weather record; everything else is a data item.
_RECORD_META_KEYS = {
    "Date",
    "Julian",
    "Hour",
    "Station",
    "Standard",
    "ZipCodes",
    "Scope",
    "Coordinate",
    "Address",
}


def _pascal_to_item_code(name: str) -> str:
    """Convert a JSON key like ``DayAirTmpAvg`` to its data item code ``day-air-tmp-avg``."""
    return _PASCAL_RE.sub("-", name).lower()


def _parse_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_bool(value: Any) -> bool:
    return str(value).strip().lower() == "true"


def _parse_iso_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def _parse_us_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%m/%d/%Y").date()
    except ValueError:
        return None


@dataclass(frozen=True)
class DataValue:
    """A single measured/derived value with its QC flag and unit.

    ``qc`` flags: " " means the value passed quality control; other flags
    (e.g. "N", "Y", "M") indicate missing or qualified data.
    """

    value: Optional[float]
    qc: str = " "
    unit: str = ""

    @classmethod
    def from_json(cls, obj: Mapping[str, Any]) -> "DataValue":
        return cls(
            value=_parse_float(obj.get("Value")),
            qc=obj.get("Qc") or " ",
            unit=(obj.get("Unit") or "").strip("()"),
        )

    def __float__(self) -> float:
        if self.value is None:
            raise TypeError("DataValue is missing (None); check the qc flag")
        return self.value


@dataclass
class WeatherRecord:
    """One daily or hourly observation from the WSN or SCS providers.

    Data items are exposed via :attr:`items`, keyed by their data item code
    (e.g. ``"day-asce-eto"``). ``record["day-asce-eto"]`` is a shortcut.
    """

    date: Optional[date]
    julian: Optional[int]
    scope: str
    standard: str
    station: Optional[int] = None
    hour: Optional[str] = None  # "0100".."2400" (hour-ending), hourly records only
    zip_codes: List[str] = field(default_factory=list)
    coordinate: Optional[str] = None
    address: Optional[str] = None
    provider: Optional[str] = None  # "station" (WSN) or "spatial" (SCS)
    items: Dict[str, DataValue] = field(default_factory=dict)

    @classmethod
    def from_json(cls, obj: Mapping[str, Any], provider: Optional[str] = None) -> "WeatherRecord":
        items: Dict[str, DataValue] = {}
        for key, value in obj.items():
            if key in _RECORD_META_KEYS:
                continue
            if isinstance(value, Mapping) and "Value" in value:
                items[_pascal_to_item_code(key)] = DataValue.from_json(value)
        zip_codes = [z.strip() for z in (obj.get("ZipCodes") or "").split(",") if z.strip()]
        return cls(
            date=_parse_iso_date(obj.get("Date")),
            julian=_parse_int(obj.get("Julian")),
            scope=obj.get("Scope", ""),
            standard=obj.get("Standard", ""),
            station=_parse_int(obj.get("Station")),
            hour=obj.get("Hour"),
            zip_codes=zip_codes,
            coordinate=obj.get("Coordinate") or None,
            address=obj.get("Address") or None,
            provider=provider,
            items=items,
        )

    @property
    def timestamp(self) -> Optional[datetime]:
        """Datetime of the observation (hour-ending for hourly records)."""
        if self.date is None:
            return None
        if self.hour is None:
            return datetime(self.date.year, self.date.month, self.date.day)
        hh = int(self.hour[:2])
        base = datetime(self.date.year, self.date.month, self.date.day)
        return base + timedelta(hours=hh)  # "2400" rolls into the next day

    def __getitem__(self, item_code: str) -> DataValue:
        return self.items[item_code]

    def get(self, item_code: str, default: Optional[DataValue] = None) -> Optional[DataValue]:
        return self.items.get(item_code, default)

    def value(self, item_code: str) -> Optional[float]:
        """Numeric value of a data item, or None if absent/missing."""
        dv = self.items.get(item_code)
        return dv.value if dv else None


@dataclass
class Station:
    """A CIMIS weather station."""

    station_nbr: int
    name: str
    city: str
    regional_office: str = ""
    county: str = ""
    connect_date: Optional[date] = None
    disconnect_date: Optional[date] = None
    is_active: bool = False
    is_eto_station: bool = False
    elevation: Optional[float] = None
    ground_cover: str = ""
    hms_latitude: str = ""
    hms_longitude: str = ""
    zip_codes: List[str] = field(default_factory=list)
    siting_desc: str = ""

    @classmethod
    def from_json(cls, obj: Mapping[str, Any]) -> "Station":
        return cls(
            station_nbr=_parse_int(obj.get("StationNbr")) or 0,
            name=obj.get("Name", ""),
            city=obj.get("City", ""),
            regional_office=obj.get("RegionalOffice", ""),
            county=obj.get("County", ""),
            connect_date=_parse_us_date(obj.get("ConnectDate")),
            disconnect_date=_parse_us_date(obj.get("DisconnectDate")),
            is_active=_parse_bool(obj.get("IsActive")),
            is_eto_station=_parse_bool(obj.get("IsEtoStation")),
            elevation=_parse_float(obj.get("Elevation")),
            ground_cover=obj.get("GroundCover", ""),
            hms_latitude=obj.get("HmsLatitude", ""),
            hms_longitude=obj.get("HmsLongitude", ""),
            zip_codes=list(obj.get("ZipCodes") or []),
            siting_desc=obj.get("SitingDesc", ""),
        )

    @staticmethod
    def _decimal_part(hms: str) -> Optional[float]:
        # HmsLatitude looks like "36º48'52N / 36.814444"
        if "/" in hms:
            return _parse_float(hms.rsplit("/", 1)[-1].strip())
        return _parse_float(hms)

    @property
    def latitude(self) -> Optional[float]:
        return self._decimal_part(self.hms_latitude)

    @property
    def longitude(self) -> Optional[float]:
        return self._decimal_part(self.hms_longitude)


@dataclass
class StationZipCode:
    """A zip code supported by the Weather Station Network (WSN)."""

    station_nbr: int
    zip_code: str
    connect_date: Optional[date] = None
    disconnect_date: Optional[date] = None
    is_active: bool = False

    @classmethod
    def from_json(cls, obj: Mapping[str, Any]) -> "StationZipCode":
        return cls(
            station_nbr=_parse_int(obj.get("StationNbr")) or 0,
            zip_code=str(obj.get("ZipCode", "")),
            connect_date=_parse_us_date(obj.get("ConnectDate")),
            disconnect_date=_parse_us_date(obj.get("DisconnectDate")),
            is_active=_parse_bool(obj.get("IsActive")),
        )


@dataclass
class SpatialZipCode:
    """A zip code supported by the Spatial CIMIS System (SCS)."""

    zip_code: str
    connect_date: Optional[date] = None
    disconnect_date: Optional[date] = None
    is_active: bool = False

    @classmethod
    def from_json(cls, obj: Mapping[str, Any]) -> "SpatialZipCode":
        return cls(
            zip_code=str(obj.get("ZipCode", "")),
            connect_date=_parse_us_date(obj.get("ConnectDate")),
            disconnect_date=_parse_us_date(obj.get("DisconnectDate")),
            is_active=_parse_bool(obj.get("IsActive")),
        )


def to_dataframe(records: List[WeatherRecord]):
    """Convert weather records to a pandas DataFrame (one row per record).

    Data item columns hold the numeric values; QC flags are in
    ``<item>-qc`` columns. Requires the ``pandas`` extra.
    """
    import pandas as pd  # lazy: pandas is an optional dependency

    rows = []
    for rec in records:
        row: Dict[str, Any] = {
            "date": rec.date,
            "julian": rec.julian,
            "scope": rec.scope,
            "station": rec.station,
            "hour": rec.hour,
            "timestamp": rec.timestamp,
            "standard": rec.standard,
            "zip_codes": ",".join(rec.zip_codes),
            "coordinate": rec.coordinate,
            "address": rec.address,
        }
        for code, dv in rec.items.items():
            row[code] = dv.value
            row[f"{code}-qc"] = dv.qc
        rows.append(row)
    return pd.DataFrame(rows)
