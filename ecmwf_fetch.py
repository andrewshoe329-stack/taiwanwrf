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
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from config import KEELUNG_LAT, KEELUNG_LON, norm_utc, setup_logging, aggregate_hourly_to_6h
from config import fetch_json as _fetch_json_shared

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

def _fetch_json(params: dict, label: str) -> dict | None:
    """Fetch from Open-Meteo with retry logic. Delegates to config.fetch_json."""
    url = OPEN_METEO_URL + "?" + urllib.parse.urlencode(params)
    return _fetch_json_shared(url, label=label)


def fetch_ecmwf_json(lat: float = KEELUNG_LAT,
                      lon: float = KEELUNG_LON,
                      label: str = "ECMWF IFS") -> dict | None:
    params = {
        "latitude":           lat,
        "longitude":          lon,
        "hourly":             HOURLY_VARS,
        "models":             ECMWF_MODEL,
        "wind_speed_unit":    "kn",
        "temperature_unit":   "celsius",
        "precipitation_unit": "mm",
        "timeformat":         "iso8601",
        "forecast_days":      7,
        "timezone":           "UTC",
    }
    return _fetch_json(params, label)


def fetch_gfs_gust_vis_json(lat: float = KEELUNG_LAT,
                             lon: float = KEELUNG_LON,
                             label: str = "GFS gust+vis fallback") -> dict | None:
    """GFS fallback for windgusts_10m and visibility (often null in ECMWF IFS)."""
    params = {
        "latitude":        lat,
        "longitude":       lon,
        "hourly":          GFS_FILL_VARS,
        "models":          GFS_MODEL,
        "wind_speed_unit": "kn",
        "timeformat":      "iso8601",
        "forecast_days":   7,
        "timezone":        "UTC",
    }
    return _fetch_json(params, label)


# ── Process ───────────────────────────────────────────────────────────────────



def process(raw: dict, raw_fill: dict | None = None) -> tuple[dict, list]:
    """
    Convert Open-Meteo hourly response to 6-hourly records.

    Delegates core aggregation to ``aggregate_hourly_to_6h`` in config.py,
    then applies GFS backfill for null gust_kt and vis_km values.

    raw_fill: optional secondary Open-Meteo response (e.g. GFS) used to backfill
              null gust_kt and vis_km values that ECMWF IFS may not publish.

    Returns (meta dict, list of record dicts).
    """
    meta, records = aggregate_hourly_to_6h(raw, model_id="ECMWF-IFS-0.25")
    if not records:
        log.warning("ECMWF API response contains no hourly data")
        return {}, []

    # Add lat/lon to meta (ECMWF-specific)
    meta["latitude"] = raw.get("latitude")
    meta["longitude"] = raw.get("longitude")

    # GFS backfill: fill null gust_kt and vis_km from secondary model
    if raw_fill:
        fill_gust_by_time: dict[str, float | None] = {}
        fill_vis_by_time:  dict[str, float | None] = {}
        fh  = raw_fill.get("hourly", {})
        ft  = fh.get("time", [])
        fg  = fh.get("windgusts_10m", [])
        fv  = fh.get("visibility", [])
        for j, ft_entry in enumerate(ft):
            key = norm_utc(ft_entry)
            fill_gust_by_time[key] = fg[j] if fg and j < len(fg) else None
            fill_vis_by_time[key]  = (round(fv[j] / 1000, 1)
                                      if fv and j < len(fv) and fv[j] is not None
                                      else None)

        for rec in records:
            vt = rec["valid_utc"]
            if rec.get("gust_kt") is None and vt in fill_gust_by_time:
                rec["gust_kt"] = fill_gust_by_time[vt]
            if rec.get("vis_km") is None and vt in fill_vis_by_time:
                rec["vis_km"] = fill_vis_by_time[vt]

    return meta, records


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="Fetch ECMWF IFS 0.25° point forecast from Open-Meteo."
    )
    ap.add_argument("--output", default="ecmwf_keelung.json",
                    help="Output JSON path (default: ecmwf_keelung.json)")
    args = ap.parse_args()

    # Always fetch Keelung (primary harbour, used by wrf_analyze comparison)
    raw = fetch_ecmwf_json()
    if raw is None:
        log.error("ECMWF fetch failed — cannot proceed.")
        sys.exit(1)
    meta, records = process(raw)
    if records:
        raw_fill = fetch_gfs_gust_vis_json()
        if raw_fill is not None:
            meta2, records2 = process(raw, raw_fill)
            if records2:
                meta, records = meta2, records2

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
