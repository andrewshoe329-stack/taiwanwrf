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
# Wave buoy observations
WAVE_BUOY_ENDPOINT = "O-A0017-001"

# Keelung station ID (CWA conventional station)
KEELUNG_STATION_ID = "466940"

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

def fetch_buoy_obs(api_key: str,
                   buoy_ids: list[str] | None = None) -> dict | None:
    """
    Fetch current wave buoy observations from CWA.

    Returns a dict with:
        buoy_id, obs_time, wave_height_m, wave_period_s, wave_dir,
        water_temp_c
    """
    if buoy_ids is None:
        buoy_ids = KEELUNG_BUOY_IDS

    data = _cwa_get(
        WAVE_BUOY_ENDPOINT, api_key,
        label="CWA-WaveBuoy",
    )
    if not data:
        return None

    try:
        records = data.get("records", {})
        # The wave buoy endpoint returns a list of all buoy stations
        stations = records.get("Station", records.get("location", []))
        if not stations:
            log.warning("No buoy data in CWA response")
            return None

        # Find our target buoy(s) — try each ID
        target = None
        for stn in stations:
            stn_id = stn.get("StationId", stn.get("stationId", ""))
            stn_name = stn.get("StationName", stn.get("locationName", ""))
            if stn_id in buoy_ids or any(bid in stn_name for bid in buoy_ids):
                target = stn
                break

        # If no exact match, find closest to Keelung by name
        if target is None:
            for stn in stations:
                name = stn.get("StationName", stn.get("locationName", ""))
                if any(kw in name for kw in ("基隆", "龍洞", "Keelung", "Longdong",
                                              "富貴角", "Fuguijiao")):
                    target = stn
                    break

        if target is None:
            # Fall back to first station and log all available
            avail = [f'{s.get("StationId","?")}:{s.get("StationName","?")}'
                     for s in stations[:10]]
            log.warning("No Keelung-area buoy found. Available: %s", avail)
            return None

        obs = (target.get("WeatherElement") or target.get("weatherElement") or {})
        obs_time_raw = target.get("ObsTime", {}).get("DateTime",
                        target.get("time", {}).get("obsTime", ""))

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

        result = {
            "buoy_id": target.get("StationId", target.get("stationId", "")),
            "buoy_name": target.get("StationName", target.get("locationName", "")),
            "obs_time": norm_utc(obs_time_raw) if obs_time_raw else None,
            "wave_height_m": _val("SignificantWaveHeight"),
            "wave_period_s": _val("MeanWavePeriod"),
            "wave_dir": _val("MeanWaveDirection"),
            "max_wave_height_m": _val("MaximumWaveHeight"),
            "peak_period_s": _val("PeakWavePeriod"),
            "water_temp_c": _val("SeaTemperature"),
        }
        log.info("CWA buoy %s: Hs=%.1fm T=%.1fs Dir=%.0f° Tw=%.1f°C",
                 result["buoy_id"],
                 result["wave_height_m"] or 0,
                 result["wave_period_s"] or 0,
                 result["wave_dir"] or 0,
                 result["water_temp_c"] or 0)
        return result

    except Exception as e:
        log.error("Failed to parse CWA buoy response: %s", e)
        return None


# ── Combined fetch (for pipeline use) ────────────────────────────────────────

def fetch_all(api_key: str) -> dict:
    """Fetch both station and buoy observations. Returns combined dict."""
    station = fetch_station_obs(api_key)
    buoy = fetch_buoy_obs(api_key)

    return {
        "source": "CWA Open Data",
        "fetched_utc": datetime.now(timezone.utc).isoformat(),
        "station": station,
        "buoy": buoy,
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
    ap.add_argument("--all", action="store_true", default=True,
                    help="Fetch both station and buoy (default)")
    ap.add_argument("--output", default="cwa_obs.json",
                    help="Output JSON path")
    args = ap.parse_args()

    if not args.api_key:
        log.error("No API key. Set CWA_OPENDATA_KEY or use --api-key")
        return

    if args.station and not args.buoy:
        result = {"station": fetch_station_obs(args.api_key)}
    elif args.buoy and not args.station:
        result = {"buoy": fetch_buoy_obs(args.api_key)}
    else:
        result = fetch_all(args.api_key)

    from pathlib import Path
    out = Path(args.output)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    log.info("CWA observations → %s", out)


if __name__ == "__main__":
    setup_logging()
    main()
