"""Data item codes and defaults for the CIMIS Web API.

WSN (Weather Station Network) supports all daily and hourly data items.
SCS (Spatial CIMIS System) supports only ASCE ETo and Average Solar
Radiation (plus Average Wind Speed for spatial zip code requests).
"""

from __future__ import annotations

# --- Daily data items (WSN unless noted) ---
DAY_AIR_TMP_AVG = "day-air-tmp-avg"
DAY_AIR_TMP_MAX = "day-air-tmp-max"
DAY_AIR_TMP_MIN = "day-air-tmp-min"
DAY_DEW_PNT = "day-dew-pnt"
DAY_ASCE_ETO = "day-asce-eto"  # WSN & SCS
DAY_ASCE_ETR = "day-asce-etr"
DAY_PRECIP = "day-precip"
DAY_REL_HUM_AVG = "day-rel-hum-avg"
DAY_REL_HUM_MAX = "day-rel-hum-max"
DAY_REL_HUM_MIN = "day-rel-hum-min"
DAY_SOIL_TMP_AVG = "day-soil-tmp-avg"
DAY_SOIL_TMP_MAX = "day-soil-tmp-max"
DAY_SOIL_TMP_MIN = "day-soil-tmp-min"
DAY_SOL_RAD_AVG = "day-sol-rad-avg"  # WSN & SCS
DAY_SOL_RAD_NET = "day-sol-rad-net"
DAY_VAP_PRES_MAX = "day-vap-pres-max"
DAY_VAP_PRES_AVG = "day-vap-pres-avg"
DAY_WIND_ENE = "day-wind-ene"
DAY_WIND_ESE = "day-wind-ese"
DAY_WIND_NNE = "day-wind-nne"
DAY_WIND_NNW = "day-wind-nnw"
DAY_WIND_RUN = "day-wind-run"
DAY_WIND_SPD_AVG = "day-wind-spd-avg"  # WSN & SCS
DAY_WIND_SSW = "day-wind-ssw"
DAY_WIND_WNW = "day-wind-wnw"
DAY_WIND_WSW = "day-wind-wsw"

# --- Hourly data items (WSN only) ---
HLY_AIR_TMP = "hly-air-tmp"
HLY_DEW_PNT = "hly-dew-pnt"
HLY_NET_RAD = "hly-net-rad"
HLY_ASCE_ETO = "hly-asce-eto"
HLY_ASCE_ETR = "hly-asce-etr"
HLY_PRECIP = "hly-precip"
HLY_REL_HUM = "hly-rel-hum"
HLY_RES_WIND = "hly-res-wind"
HLY_SOIL_TMP = "hly-soil-tmp"
HLY_SOL_RAD = "hly-sol-rad"
HLY_VAP_PRES = "hly-vap-pres"
HLY_WIND_DIR = "hly-wind-dir"
HLY_WIND_SPD = "hly-wind-spd"

DAILY_DATA_ITEMS = frozenset(
    {
        DAY_AIR_TMP_AVG,
        DAY_AIR_TMP_MAX,
        DAY_AIR_TMP_MIN,
        DAY_DEW_PNT,
        DAY_ASCE_ETO,
        DAY_ASCE_ETR,
        DAY_PRECIP,
        DAY_REL_HUM_AVG,
        DAY_REL_HUM_MAX,
        DAY_REL_HUM_MIN,
        DAY_SOIL_TMP_AVG,
        DAY_SOIL_TMP_MAX,
        DAY_SOIL_TMP_MIN,
        DAY_SOL_RAD_AVG,
        DAY_SOL_RAD_NET,
        DAY_VAP_PRES_MAX,
        DAY_VAP_PRES_AVG,
        DAY_WIND_ENE,
        DAY_WIND_ESE,
        DAY_WIND_NNE,
        DAY_WIND_NNW,
        DAY_WIND_RUN,
        DAY_WIND_SPD_AVG,
        DAY_WIND_SSW,
        DAY_WIND_WNW,
        DAY_WIND_WSW,
    }
)

HOURLY_DATA_ITEMS = frozenset(
    {
        HLY_AIR_TMP,
        HLY_DEW_PNT,
        HLY_NET_RAD,
        HLY_ASCE_ETO,
        HLY_ASCE_ETR,
        HLY_PRECIP,
        HLY_REL_HUM,
        HLY_RES_WIND,
        HLY_SOIL_TMP,
        HLY_SOL_RAD,
        HLY_VAP_PRES,
        HLY_WIND_DIR,
        HLY_WIND_SPD,
    }
)

ALL_DATA_ITEMS = DAILY_DATA_ITEMS | HOURLY_DATA_ITEMS

# Data items supported by the Spatial CIMIS System (SCS).
SPATIAL_DATA_ITEMS = frozenset({DAY_ASCE_ETO, DAY_SOL_RAD_AVG, DAY_WIND_SPD_AVG})

# Items returned when dataItems is omitted or set to "default".
DEFAULT_DAILY_ITEMS = (
    DAY_ASCE_ETO,
    DAY_PRECIP,
    DAY_SOL_RAD_AVG,
    DAY_VAP_PRES_AVG,
    DAY_AIR_TMP_MAX,
    DAY_AIR_TMP_MIN,
    DAY_AIR_TMP_AVG,
    DAY_REL_HUM_MAX,
    DAY_REL_HUM_MIN,
    DAY_REL_HUM_AVG,
    DAY_DEW_PNT,
    DAY_WIND_SPD_AVG,
    DAY_WIND_RUN,
    DAY_SOIL_TMP_AVG,
)

DEFAULT_HOURLY_ITEMS = (
    HLY_AIR_TMP,
    HLY_DEW_PNT,
    HLY_NET_RAD,
    HLY_ASCE_ETO,
    HLY_ASCE_ETR,
    HLY_PRECIP,
    HLY_REL_HUM,
    HLY_RES_WIND,
    HLY_SOIL_TMP,
    HLY_SOL_RAD,
    HLY_VAP_PRES,
    HLY_WIND_DIR,
    HLY_WIND_SPD,
)

DEFAULT_SPATIAL_ITEMS = (DAY_ASCE_ETO, DAY_SOL_RAD_AVG, DAY_WIND_SPD_AVG)

# Earliest date for which CIMIS data exists.
CIMIS_ORIGIN_DATE = "1982-06-07"
