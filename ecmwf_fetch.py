#!/usr/bin/env python3
"""
ecmwf_fetch.py
==============
Fetch the ECMWF IFS 0.25° point forecast for Keelung from the Open-Meteo API
and save it as a JSON file compatible with wrf_analyze.py's comparison input.

No API key required — Open-Meteo is free up to 10,000 requests/day.
No extra dependencies — uses only stdlib (urllib) + json.

Usage:
  python ecmwf_fetch.py [--output ecmwf_keelung.json]
"""

import argparse
import json
import logging
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from config import KEELUNG_LAT, KEELUNG_LON, norm_utc, setup_logging

log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

# ECMWF IFS at 0.25° resolution — the global model we compare against WRF 3km.
# Open-Meteo always returns the most recent available ECMWF run (00 or 12 UTC).
ECMWF_MODEL = "ecmwf_ifs025"

# Hourly variables to request. Open-Meteo resamples ECMWF to hourly for us.
HOURLY_VARS = ",".join([
    "temperature_2m",       # °C
    "windspeed_10m",        # requested in knots (wind_speed_unit=kn)
    "winddirection_10m",    # degrees
    "windgusts_10m",        # knots  (may be null for ECMWF IFS on Open-Meteo)
    "precipitation",        # mm/h  → we sum to 6-hourly
    "cloudcover",           # %
    "pressure_msl",         # hPa  (mean sea level pressure)
    "visibility",           # metres (may be null for ECMWF IFS on Open-Meteo)
    "cape",                 # J/kg  (convective available potential energy)
])

# GFS fallback: windgusts and visibility are often missing from ECMWF IFS on
# Open-Meteo.  We make a second call to GFS global and fill in any null values.
GFS_MODEL     = "gfs_global"
GFS_FILL_VARS = "windgusts_10m,visibility"


# ── Fetch ─────────────────────────────────────────────────────────────────────

_FETCH_RETRIES    = 3
_FETCH_RETRY_DELAY = 5   # seconds between attempts


def _fetch_json(params: dict, label: str) -> dict | None:
    """Low-level fetch helper with retry logic.

    Returns parsed JSON dict on success, or ``None`` on failure (so callers
    can distinguish a network/API error from an empty-but-valid response).
    """
    url = OPEN_METEO_URL + "?" + urllib.parse.urlencode(params)
    log.info("Fetching %s from Open-Meteo …", label)
    last_exc: Exception = RuntimeError("no attempts made")
    for attempt in range(1, _FETCH_RETRIES + 1):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                return json.load(r)
        except (urllib.error.HTTPError, urllib.error.URLError,
                json.JSONDecodeError) as e:
            last_exc = e
            if attempt < _FETCH_RETRIES:
                log.warning("Request failed (%s); retry %d/%d in %ds …",
                            e, attempt, _FETCH_RETRIES, _FETCH_RETRY_DELAY)
                time.sleep(_FETCH_RETRY_DELAY)
    log.error("%s fetch failed after %d attempts: %s",
              label, _FETCH_RETRIES, last_exc)
    return None


def fetch_ecmwf_json() -> dict | None:
    params = {
        "latitude":           KEELUNG_LAT,
        "longitude":          KEELUNG_LON,
        "hourly":             HOURLY_VARS,
        "models":             ECMWF_MODEL,
        "wind_speed_unit":    "kn",
        "temperature_unit":   "celsius",
        "precipitation_unit": "mm",
        "timeformat":         "iso8601",
        "forecast_days":      7,
        "timezone":           "UTC",
    }
    return _fetch_json(params, "ECMWF IFS")


def fetch_gfs_gust_vis_json() -> dict | None:
    """GFS fallback for windgusts_10m and visibility (often null in ECMWF IFS)."""
    params = {
        "latitude":        KEELUNG_LAT,
        "longitude":       KEELUNG_LON,
        "hourly":          GFS_FILL_VARS,
        "models":          GFS_MODEL,
        "wind_speed_unit": "kn",
        "timeformat":      "iso8601",
        "forecast_days":   7,
        "timezone":        "UTC",
    }
    return _fetch_json(params, "GFS gust+vis fallback")


# ── Process ───────────────────────────────────────────────────────────────────

_norm_utc = norm_utc  # local alias for backward compatibility


def process(raw: dict, raw_fill: dict | None = None) -> tuple[dict, list]:
    """
    Convert Open-Meteo hourly response to 6-hourly records.

    For variables measured instantaneously (temperature, wind, pressure, cloud,
    visibility) we sample at the 6-hourly timestamps.

    For precipitation we sum the 6 hourly values *ending* at each 6h timestamp
    to match the WRF 'precip_mm_6h' convention.

    raw_fill: optional secondary Open-Meteo response (e.g. GFS) used to backfill
              null gust_kt and vis_km values that ECMWF IFS may not publish.

    Returns (meta dict, list of record dicts).
    """
    h = raw.get("hourly", {})
    times = h.get("time", [])
    if not times:
        return {}, []

    def col(key):
        return h.get(key, [])

    temp   = col("temperature_2m")
    wspd   = col("windspeed_10m")
    wdir   = col("winddirection_10m")
    gust   = col("windgusts_10m")
    precip = col("precipitation")
    cloud  = col("cloudcover")
    mslp   = col("pressure_msl")
    vis    = col("visibility")
    cape   = col("cape")

    def safe(arr, i):
        return arr[i] if arr and 0 <= i < len(arr) else None

    # Build lookup index for GFS fill data keyed by normalised time string
    fill_gust_by_time: dict[str, float | None] = {}
    fill_vis_by_time:  dict[str, float | None] = {}
    if raw_fill:
        fh  = raw_fill.get("hourly", {})
        ft  = fh.get("time", [])
        fg  = fh.get("windgusts_10m", [])
        fv  = fh.get("visibility", [])
        for j, ft_entry in enumerate(ft):
            key = _norm_utc(ft_entry)
            fill_gust_by_time[key] = fg[j] if fg and j < len(fg) else None
            fill_vis_by_time[key]  = (round(fv[j] / 1000, 1)
                                      if fv and j < len(fv) and fv[j] is not None
                                      else None)

    records = []
    for i, t in enumerate(times):
        dt = datetime.fromisoformat(t if len(t) >= 19 else t + ':00').replace(tzinfo=timezone.utc)
        if dt.hour % 6 != 0:
            continue

        # Precipitation: sum hours [i-5 .. i] inclusive (6-hour window).
        # Note: at i=0 (first record), the window is only 1 hour — this is
        # inherent to the first available timestamp and matches WRF convention
        # where F000 typically reports near-zero accumulation.
        precip_6h = sum(
            (safe(precip, j) or 0.0)
            for j in range(max(0, i - 5), i + 1)
        )

        # Visibility: metres → km
        vis_val = safe(vis, i)
        vis_km  = round(vis_val / 1000, 1) if vis_val is not None else None

        # Gust from ECMWF; fall back to GFS fill if null
        gust_val = safe(gust, i)
        norm_t   = _norm_utc(t)
        if gust_val is None and norm_t in fill_gust_by_time:
            gust_val = fill_gust_by_time[norm_t]
        if vis_km is None and norm_t in fill_vis_by_time:
            vis_km = fill_vis_by_time[norm_t]

        records.append({
            "valid_utc":    norm_t,
            "temp_c":       safe(temp,   i),
            "wind_kt":      safe(wspd,   i),
            "wind_dir":     safe(wdir,   i),
            "gust_kt":      gust_val,
            "mslp_hpa":     safe(mslp,   i),
            "precip_mm_6h": round(precip_6h, 2),
            "cloud_pct":    safe(cloud,  i),
            "vis_km":       vis_km,
            "cape":         safe(cape,   i),
        })

    # ECMWF init time: use the first hourly timestamp (model cycle start).
    # Note: current/current_weather.time is the observation time, not the
    # model init time, so we don't use it.
    init_raw = raw.get("hourly", {}).get("time", [""])[0]
    meta = {
        "model_id":  "ECMWF-IFS-0.25",
        "init_utc":  _norm_utc(init_raw) if init_raw else None,
        "source":    "open-meteo.com",
        "latitude":  raw.get("latitude"),
        "longitude": raw.get("longitude"),
    }
    return meta, records


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="Fetch ECMWF IFS 0.25° point forecast from Open-Meteo."
    )
    ap.add_argument("--output", default="ecmwf_keelung.json",
                    help="Output JSON path (default: ecmwf_keelung.json)")
    args = ap.parse_args()

    raw = fetch_ecmwf_json()
    if raw is None:
        log.error("ECMWF fetch failed — cannot proceed.")
        sys.exit(1)
    meta, records = process(raw)
    # Only fetch GFS backfill if ECMWF returned data
    if records:
        raw_fill = fetch_gfs_gust_vis_json()
        if raw_fill is not None:
            meta, records = process(raw, raw_fill)

    if not records:
        log.error("No records extracted from Open-Meteo response.")
        sys.exit(1)

    summary = {"meta": meta, "records": records}
    out = Path(args.output)
    out.write_text(json.dumps(summary, indent=2))
    log.info("ECMWF summary → %s  (%d 6-hourly steps)", out, len(records))

    gha = os.environ.get("GITHUB_OUTPUT")
    if gha:
        with open(gha, "a") as f:
            f.write(f"ecmwf_json={out.resolve()}\n")


if __name__ == "__main__":
    setup_logging()
    main()
