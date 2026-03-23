#!/usr/bin/env python3
"""
cwa_fetch.py — Fetch real-time observations from CWA Open Data API.

Provides weather station data (Keelung #466940) and wave buoy data
(Keelung harbour) for forecast verification and surf condition display.

CWA Open Data: https://opendata.cwa.gov.tw/
API docs:      https://opendata.cwa.gov.tw/dist/opendata-swagger.html

Usage:
    python cwa_fetch.py --api-key CWA-XXXX --output cwa_obs.json
    python cwa_fetch.py --buoy --api-key CWA-XXXX --output cwa_buoy.json
"""

import argparse
import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from config import KEELUNG_LAT, KEELUNG_LON, norm_utc, setup_logging

log = logging.getLogger(__name__)

# ── CWA Open Data endpoints ─────────────────────────────────────────────────

CWA_BASE = "https://opendata.cwa.gov.tw/api/v1/rest/datastore"

# Automatic weather station — 5-min surface obs (all stations)
STATION_ENDPOINT = "O-A0001-001"
# Conventional weather station — hourly obs
STATION_HOURLY_ENDPOINT = "O-A0003-001"
# Automatic rain gauge — rainfall obs (denser network than weather stations)
RAIN_GAUGE_ENDPOINT = "O-A0002-001"
# Wave buoy observations (Hs, period, direction, water temp)
WAVE_BUOY_ENDPOINT = "O-A0017-001"
# Tide observations (actual sea level at tide stations)
TIDE_OBS_ENDPOINT = "O-A0019-001"
# Official CWA tide forecast — 1 month ahead (high/low times + heights)
TIDE_FORECAST_ENDPOINT = "F-A0021-001"
# Township weather forecast — 7-day (for Keelung-specific CWA forecast text)
TOWNSHIP_FORECAST_ENDPOINT = "F-D0047-061"  # 061 = Keelung City
# Weather warnings & advisories
WARNING_ENDPOINT = "W-C0033-002"

# Keelung station ID (CWA conventional station)
KEELUNG_STATION_ID = "466940"

# Keelung tide station ID (for sea level observations)
KEELUNG_TIDE_STATION_ID = "KL01"
KEELUNG_TIDE_NAMES = ["基隆", "Keelung"]

# Wave buoy station near Keelung
# Longdong buoy (龍洞) is closest to the surf spots on the northeast coast
KEELUNG_BUOY_IDS = ["46694A", "COMC06"]  # try multiple IDs

RETRIES = 3
RETRY_DELAY = 3


# ── API fetch helpers ────────────────────────────────────────────────────────

def _cwa_get(endpoint: str, api_key: str, params: dict | None = None,
             label: str = "CWA") -> dict | None:
    """Fetch from CWA Open Data API with retries."""
    base_params = {"Authorization": api_key}
    if params:
        base_params.update(params)

    url = f"{CWA_BASE}/{endpoint}?{urllib.parse.urlencode(base_params)}"
    last_err = None

    for attempt in range(1, RETRIES + 1):
        try:
            req = urllib.request.Request(url)
            req.add_header("Accept", "application/json")
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.load(r)

            # CWA API wraps response in {"success": "true", "records": {...}}
            if data.get("success") == "true" or data.get("records"):
                return data
            log.warning("%s response missing success flag: %s",
                        label, str(data)[:200])
            return data

        except Exception as e:
            last_err = e
            if attempt < RETRIES:
                log.warning("%s attempt %d failed: %s", label, attempt, e)
                time.sleep(RETRY_DELAY * attempt)

    log.error("%s failed after %d attempts: %s", label, RETRIES, last_err)
    return None


# ── Weather station observations ─────────────────────────────────────────────

def fetch_station_obs(api_key: str,
                      station_id: str = KEELUNG_STATION_ID) -> dict | None:
    """
    Fetch current weather observations from a CWA station.

    Returns a dict with standardised keys:
        obs_time, temp_c, wind_kt, wind_dir, gust_kt, pressure_hpa,
        humidity_pct, precip_mm (hourly), weather_desc
    """
    data = _cwa_get(
        STATION_ENDPOINT, api_key,
        params={"StationId": station_id},
        label=f"CWA-Station-{station_id}",
    )
    if not data:
        return None

    try:
        records = data.get("records", {})
        stations = records.get("Station", records.get("location", []))
        if not stations:
            log.warning("No station data in CWA response")
            return None

        stn = stations[0]

        # CWA nests observation data under different keys depending on
        # which endpoint/format version is used.
        obs = (stn.get("WeatherElement") or stn.get("weatherElement")
               or stn.get("GeoInfo", {}))
        obs_time_raw = stn.get("ObsTime", {}).get("DateTime",
                        stn.get("time", {}).get("obsTime", ""))

        # Extract fields — CWA uses m/s for wind, convert to knots
        def _val(key, fallback_key=None):
            """Extract numeric value from nested CWA structure."""
            v = obs.get(key) or (obs.get(fallback_key) if fallback_key else None)
            if isinstance(v, dict):
                v = v.get("value") or v.get("Value")
            if v is None or v == "" or v == "-99" or v == -99:
                return None
            try:
                return float(v)
            except (ValueError, TypeError):
                return None

        wind_ms = _val("WindSpeed")
        gust_ms = _val("WindGust", "GustSpeed")
        wind_dir_deg = _val("WindDirection")

        wind_kt = round(wind_ms * 1.94384, 1) if wind_ms is not None else None
        gust_kt = round(gust_ms * 1.94384, 1) if gust_ms is not None else None

        result = {
            "station_id": station_id,
            "station_name": stn.get("StationName", stn.get("locationName", "")),
            "obs_time": norm_utc(obs_time_raw) if obs_time_raw else None,
            "temp_c": _val("AirTemperature", "Temperature"),
            "wind_kt": wind_kt,
            "wind_dir": wind_dir_deg,
            "gust_kt": gust_kt,
            "pressure_hpa": _val("AirPressure", "StationPressure"),
            "humidity_pct": _val("RelativeHumidity"),
            "precip_mm": _val("Now", "Precipitation"),
            "weather_desc": (obs.get("Weather") or ""),
        }
        log.info("CWA station %s obs: %.1f°C, %.0fkt %s, %.1fhPa",
                 station_id,
                 result["temp_c"] or 0,
                 result["wind_kt"] or 0,
                 result.get("weather_desc", ""),
                 result["pressure_hpa"] or 0)
        return result

    except Exception as e:
        log.error("Failed to parse CWA station response: %s", e)
        return None


# ── Wave buoy observations ──────────────────────────────────────────────────

def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Approximate distance in km between two lat/lon points."""
    import math
    R = 6371  # Earth radius km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _parse_buoy_station(stn: dict) -> dict | None:
    """Parse a single CWA buoy station record into a standardised dict."""
    obs = (stn.get("WeatherElement") or stn.get("weatherElement") or {})
    obs_time_raw = stn.get("ObsTime", {}).get("DateTime",
                    stn.get("time", {}).get("obsTime", ""))

    def _val(key):
        v = obs.get(key)
        if isinstance(v, dict):
            v = v.get("value") or v.get("Value")
        if v is None or v == "" or v == "-99" or v == "-99.0":
            return None
        try:
            return float(v)
        except (ValueError, TypeError):
            return None

    # Extract lat/lon if available (for distance calculations)
    geo = stn.get("GeoInfo", stn.get("geoInfo", {}))
    lat = None
    lon = None
    for key in ("Latitude", "latitude", "lat"):
        v = geo.get(key) if isinstance(geo, dict) else None
        if v is not None:
            try:
                lat = float(v)
                break
            except (ValueError, TypeError):
                pass
    for key in ("Longitude", "longitude", "lon"):
        v = geo.get(key) if isinstance(geo, dict) else None
        if v is not None:
            try:
                lon = float(v)
                break
            except (ValueError, TypeError):
                pass

    hs = _val("SignificantWaveHeight")
    if hs is None:
        return None  # buoy has no wave data

    return {
        "buoy_id": stn.get("StationId", stn.get("stationId", "")),
        "buoy_name": stn.get("StationName", stn.get("locationName", "")),
        "lat": lat,
        "lon": lon,
        "obs_time": norm_utc(obs_time_raw) if obs_time_raw else None,
        "wave_height_m": hs,
        "wave_period_s": _val("MeanWavePeriod"),
        "wave_dir": _val("MeanWaveDirection"),
        "max_wave_height_m": _val("MaximumWaveHeight"),
        "peak_period_s": _val("PeakWavePeriod"),
        "water_temp_c": _val("SeaTemperature"),
    }


def fetch_buoy_obs(api_key: str,
                   buoy_ids: list[str] | None = None) -> dict | None:
    """
    Fetch current wave buoy observations from CWA.

    Returns the primary (Keelung-area) buoy dict with:
        buoy_id, obs_time, wave_height_m, wave_period_s, wave_dir,
        water_temp_c
    """
    if buoy_ids is None:
        buoy_ids = KEELUNG_BUOY_IDS

    all_buoys = fetch_all_buoys(api_key)
    if not all_buoys:
        return None

    # Find primary buoy by ID match
    for b in all_buoys:
        if b["buoy_id"] in buoy_ids:
            return b

    # Fallback: name match
    for b in all_buoys:
        name = b.get("buoy_name", "")
        if any(kw in name for kw in ("基隆", "龍洞", "Keelung", "Longdong",
                                      "富貴角", "Fuguijiao")):
            return b

    # Last resort: find closest to Keelung
    return find_nearest_buoy(all_buoys, KEELUNG_LAT, KEELUNG_LON)


def fetch_all_buoys(api_key: str) -> list[dict]:
    """
    Fetch ALL available wave buoy observations from CWA.

    Returns a list of parsed buoy dicts, each with:
        buoy_id, buoy_name, lat, lon, obs_time, wave_height_m, wave_period_s,
        wave_dir, max_wave_height_m, peak_period_s, water_temp_c
    """
    data = _cwa_get(
        WAVE_BUOY_ENDPOINT, api_key,
        label="CWA-WaveBuoy",
    )
    if not data:
        return []

    try:
        records = data.get("records", {})
        stations = records.get("Station", records.get("location", []))
        if not stations:
            log.warning("No buoy data in CWA response")
            return []

        buoys = []
        for stn in stations:
            parsed = _parse_buoy_station(stn)
            if parsed:
                buoys.append(parsed)

        log.info("CWA: fetched %d wave buoys with valid data", len(buoys))
        for b in buoys:
            log.debug("  Buoy %s (%s): Hs=%.1fm lat=%s lon=%s",
                      b["buoy_id"], b["buoy_name"],
                      b["wave_height_m"] or 0,
                      b.get("lat"), b.get("lon"))
        return buoys

    except Exception as e:
        log.error("Failed to parse CWA buoy response: %s", e)
        return []


def find_nearest_buoy(buoys: list[dict], lat: float, lon: float,
                      max_dist_km: float = 100) -> dict | None:
    """
    Find the nearest buoy to a given lat/lon from a list of parsed buoys.

    Returns the closest buoy dict, or None if no buoy within max_dist_km.
    Buoys without lat/lon coordinates are skipped for distance calculation
    but still considered as fallback.
    """
    if not buoys:
        return None

    best = None
    best_dist = float('inf')

    for b in buoys:
        b_lat = b.get("lat")
        b_lon = b.get("lon")
        if b_lat is not None and b_lon is not None:
            dist = _haversine_km(lat, lon, b_lat, b_lon)
            if dist < best_dist:
                best_dist = dist
                best = b

    if best and best_dist <= max_dist_km:
        return best

    if best is not None:
        # All buoys had coordinates but none within max_dist_km
        return None

    # If no buoy has coordinates, return the first one with valid wave data
    return buoys[0] if buoys else None


# ── Tide observations ────────────────────────────────────────────────────────

def fetch_tide_obs(api_key: str,
                   station_id: str = KEELUNG_TIDE_STATION_ID) -> dict | None:
    """
    Fetch current tide (sea level) observations from a CWA tide station.

    Returns a dict with:
        station_id, obs_time, tide_height_m, station_name
    """
    data = _cwa_get(
        TIDE_OBS_ENDPOINT, api_key,
        label=f"CWA-Tide-{station_id}",
    )
    if not data:
        return None

    try:
        records = data.get("records", {})
        stations = records.get("Station", records.get("location",
                    records.get("TideStation", records.get("tide", []))))
        if not stations:
            log.warning("No tide station data in CWA response")
            return None

        # Find target station by ID or name
        target = None
        for stn in stations if isinstance(stations, list) else [stations]:
            stn_id = stn.get("StationId", stn.get("stationId", ""))
            stn_name = stn.get("StationName", stn.get("locationName", ""))
            if stn_id == station_id or any(n in stn_name for n in KEELUNG_TIDE_NAMES):
                target = stn
                break

        if target is None:
            avail = [f'{s.get("StationId", "?")}:{s.get("StationName", "?")}'
                     for s in (stations[:10] if isinstance(stations, list) else [])]
            log.warning("Keelung tide station not found. Available: %s", avail)
            return None

        obs = (target.get("WeatherElement") or target.get("weatherElement")
               or target.get("TideData") or target.get("tideData") or {})
        obs_time_raw = (target.get("ObsTime", {}).get("DateTime", "")
                        or target.get("DataTime", "")
                        or target.get("time", {}).get("obsTime", ""))

        def _val(key):
            v = obs.get(key)
            if isinstance(v, dict):
                v = v.get("value") or v.get("Value")
            if v is None or v == "" or v == "-99":
                return None
            try:
                return float(v)
            except (ValueError, TypeError):
                return None

        height = (_val("TideHeights") or _val("TideHeight")
                  or _val("WaterLevel") or _val("SeaLevel"))

        result = {
            "station_id": target.get("StationId", target.get("stationId", "")),
            "station_name": target.get("StationName", target.get("locationName", "")),
            "obs_time": norm_utc(obs_time_raw) if obs_time_raw else None,
            "tide_height_m": height,
        }
        log.info("CWA tide station %s: height=%.2fm at %s",
                 result["station_id"],
                 result["tide_height_m"] or 0,
                 result["obs_time"] or "?")
        return result

    except Exception as e:
        log.error("Failed to parse CWA tide response: %s", e)
        return None


# ── Official CWA tide forecast ───────────────────────────────────────────────

def fetch_tide_forecast(api_key: str,
                        station_name: str = "基隆") -> list[dict]:
    """
    Fetch CWA official tide forecast (high/low tide times + heights).

    This is the authoritative CWA prediction for the next month — more
    accurate than our offline harmonic constants, especially for storm
    surge and seasonal MSL variations.

    Returns a list of dicts with:
        time_utc, height_m, type ('high' or 'low'), station_name
    """
    data = _cwa_get(
        TIDE_FORECAST_ENDPOINT, api_key,
        label="CWA-TideForecast",
    )
    if not data:
        return []

    try:
        records = data.get("records", {})
        # CWA tide forecast structure varies; try common paths
        locations = (records.get("TideForecasts", {}).get("Location", [])
                     or records.get("location", [])
                     or records.get("Location", []))
        if isinstance(locations, dict):
            locations = [locations]

        # Find Keelung station
        target = None
        for loc in locations:
            name = loc.get("LocationName", loc.get("locationName", ""))
            if station_name in name or "基隆" in name or "Keelung" in name:
                target = loc
                break

        if target is None:
            avail = [loc.get("LocationName", loc.get("locationName", "?"))
                     for loc in locations[:10]]
            log.warning("Keelung not found in tide forecast. Available: %s", avail)
            return []

        # Extract tide extrema (high/low)
        extrema = []
        tide_data = (target.get("TimePeriods", {}).get("Daily", [])
                     or target.get("validTime", [])
                     or target.get("TideData", []))

        for day in tide_data if isinstance(tide_data, list) else [tide_data]:
            # Try nested tide extrema within each day
            tides = (day.get("TideInfo", [])
                     or day.get("Time", [])
                     or day.get("tideInfo", []))
            if isinstance(tides, dict):
                tides = [tides]

            for t in tides if isinstance(tides, list) else []:
                time_raw = (t.get("DateTime", "")
                            or t.get("dataTime", "")
                            or t.get("time", ""))
                tide_type = t.get("Tide", t.get("tide", "")).lower()
                # CWA uses 滿潮/乾潮 or high/low
                if "high" in tide_type or "滿" in tide_type:
                    ttype = "high"
                elif "low" in tide_type or "乾" in tide_type:
                    ttype = "low"
                else:
                    continue

                # Height may be in different keys
                height = None
                for hkey in ("AboveLocalMSL", "AboveTWVD", "AboveChartDatum",
                             "TideHeights", "height"):
                    v = t.get(hkey)
                    if isinstance(v, dict):
                        v = v.get("value") or v.get("Value")
                    if v is not None and v != "":
                        try:
                            height = float(v)
                            break
                        except (ValueError, TypeError):
                            pass

                if time_raw:
                    extrema.append({
                        "time_utc": norm_utc(time_raw) if time_raw else None,
                        "height_m": height,
                        "type": ttype,
                        "station_name": target.get("LocationName",
                                        target.get("locationName", "")),
                    })

        log.info("CWA tide forecast: %d extrema for %s", len(extrema), station_name)
        return extrema

    except Exception as e:
        log.error("Failed to parse CWA tide forecast: %s", e)
        return []


# ── Township weather forecast ────────────────────────────────────────────────

def fetch_township_forecast(api_key: str,
                            endpoint: str = TOWNSHIP_FORECAST_ENDPOINT) -> dict | None:
    """
    Fetch CWA official township-level weather forecast for Keelung.

    Returns a dict with daily forecast elements (weather description, min/max
    temp, rain probability, wind) that can supplement model forecasts.
    """
    data = _cwa_get(
        endpoint, api_key,
        label="CWA-Township",
    )
    if not data:
        return None

    try:
        records = data.get("records", {})
        locations = records.get("location", records.get("Location", []))
        if not locations:
            log.warning("No township forecast data")
            return None

        # Take the first location (should be Keelung for endpoint 061)
        loc = locations[0] if isinstance(locations, list) else locations

        # Parse weather elements into a simplified structure
        elements = {}
        wx_list = loc.get("weatherElement", loc.get("WeatherElement", []))
        for el in wx_list:
            name = el.get("elementName", el.get("ElementName", ""))
            times = el.get("time", el.get("Time", []))
            values = []
            for t in times if isinstance(times, list) else [times]:
                param = t.get("elementValue", t.get("value", []))
                if isinstance(param, list) and param:
                    param = param[0]
                val = param.get("value", param) if isinstance(param, dict) else param
                start = t.get("startTime", t.get("dataTime", ""))
                values.append({
                    "time": norm_utc(start) if start else None,
                    "value": val,
                })
            if values:
                elements[name] = values

        result = {
            "location": loc.get("locationName", loc.get("LocationName", "")),
            "elements": elements,
        }
        log.info("CWA township forecast for %s: %d elements",
                 result["location"], len(elements))
        return result

    except Exception as e:
        log.error("Failed to parse CWA township forecast: %s", e)
        return None


# ── Weather warnings ─────────────────────────────────────────────────────────

def fetch_warnings(api_key: str) -> list[dict]:
    """
    Fetch active weather warnings/advisories from CWA.

    Returns a list of dicts with:
        type, severity, area, description, issued_utc, expires_utc
    """
    data = _cwa_get(
        WARNING_ENDPOINT, api_key,
        label="CWA-Warnings",
    )
    if not data:
        return []

    try:
        records = data.get("records", {})
        # CWA warning format nests under different keys depending on version
        warnings_raw = (records.get("record", [])
                        or records.get("Warning", [])
                        or records.get("warning", []))
        if not warnings_raw:
            log.debug("No active CWA warnings")
            return []

        results = []
        now = datetime.now(timezone.utc)
        for w in warnings_raw:
            # Extract warning content
            content = w.get("contents", w.get("content", {}))
            if isinstance(content, str):
                desc = content
            else:
                desc = content.get("content", {}).get("contentText",
                       content.get("text", str(content)[:200]))

            # Check if this warning is relevant to northern Taiwan / Keelung
            area = w.get("affectedAreas", w.get("area", ""))
            if isinstance(area, list):
                area = ", ".join(area)

            # Only include warnings relevant to our area (north coast, Keelung, marine)
            northern_keywords = ("基隆", "北部", "北海岸", "宜蘭", "新北",
                                 "Keelung", "northern", "marine", "海上",
                                 "全臺", "全台", "豪雨", "颱風", "typhoon")
            if area and not any(kw in area for kw in northern_keywords):
                if not any(kw in desc for kw in northern_keywords):
                    continue

            issued = w.get("startTime", w.get("issued_time", ""))
            expires = w.get("endTime", w.get("valid_time", ""))

            results.append({
                "type": w.get("phenomena", w.get("type",
                        w.get("datasetDescription", "Weather Warning"))),
                "severity": w.get("significance", w.get("severity", "advisory")),
                "area": area,
                "description": desc[:500] if isinstance(desc, str) else "",
                "issued_utc": norm_utc(issued) if issued else None,
                "expires_utc": norm_utc(expires) if expires else None,
            })

        log.info("CWA warnings: %d relevant to northern Taiwan", len(results))
        return results

    except Exception as e:
        log.error("Failed to parse CWA warnings response: %s", e)
        return []


# ── Combined fetch (for pipeline use) ────────────────────────────────────────

def fetch_all(api_key: str) -> dict:
    """Fetch all available CWA data sources. Returns combined dict.

    The 'buoy' key holds the primary (Keelung-area) buoy.
    The 'all_buoys' key holds every buoy with valid wave data,
    enabling per-spot nearest-buoy lookups downstream.
    The 'tide_forecast' key holds official CWA tide predictions (high/low).
    The 'township_forecast' key holds CWA's Keelung weather forecast text.
    """
    station = fetch_station_obs(api_key)
    all_buoys = fetch_all_buoys(api_key)
    tide = fetch_tide_obs(api_key)
    tide_forecast = fetch_tide_forecast(api_key)
    township = fetch_township_forecast(api_key)
    warnings = fetch_warnings(api_key)

    # Primary buoy: find Keelung-area match from the full list
    buoy = None
    for b in all_buoys:
        if b["buoy_id"] in KEELUNG_BUOY_IDS:
            buoy = b
            break
    if buoy is None:
        for b in all_buoys:
            name = b.get("buoy_name", "")
            if any(kw in name for kw in ("基隆", "龍洞", "Keelung", "Longdong",
                                          "富貴角", "Fuguijiao")):
                buoy = b
                break
    if buoy is None and all_buoys:
        buoy = find_nearest_buoy(all_buoys, KEELUNG_LAT, KEELUNG_LON)

    return {
        "source": "CWA Open Data",
        "fetched_utc": datetime.now(timezone.utc).isoformat(),
        "station": station,
        "buoy": buoy,
        "all_buoys": all_buoys,
        "tide": tide,
        "tide_forecast": tide_forecast,
        "township_forecast": township,
        "warnings": warnings,
    }


# ── CLI ──────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="Fetch CWA observations")
    ap.add_argument("--api-key", default=os.environ.get("CWA_OPENDATA_KEY"),
                    help="CWA Open Data API key (or set CWA_OPENDATA_KEY env)")
    ap.add_argument("--station", action="store_true",
                    help="Fetch weather station data")
    ap.add_argument("--buoy", action="store_true",
                    help="Fetch wave buoy data")
    ap.add_argument("--tide", action="store_true",
                    help="Fetch tide observation data")
    ap.add_argument("--warnings", action="store_true",
                    help="Fetch active weather warnings")
    ap.add_argument("--all", action="store_true", default=True,
                    help="Fetch all data sources (default)")
    ap.add_argument("--output", default="cwa_obs.json",
                    help="Output JSON path")
    args = ap.parse_args()

    if not args.api_key:
        log.error("No API key. Set CWA_OPENDATA_KEY or use --api-key")
        return

    specific = args.station or args.buoy or args.tide or args.warnings
    if specific:
        result = {}
        if args.station:
            result["station"] = fetch_station_obs(args.api_key)
        if args.buoy:
            result["buoy"] = fetch_buoy_obs(args.api_key)
        if args.tide:
            result["tide"] = fetch_tide_obs(args.api_key)
        if args.warnings:
            result["warnings"] = fetch_warnings(args.api_key)
    else:
        result = fetch_all(args.api_key)

    from pathlib import Path
    out = Path(args.output)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    log.info("CWA observations → %s", out)


if __name__ == "__main__":
    setup_logging()
    main()
