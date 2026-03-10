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
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────

KEELUNG_LAT = 25.15589534977208
KEELUNG_LON = 121.78782946186699

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

# ECMWF IFS at 0.25° resolution — the global model we compare against WRF 3km.
# Open-Meteo always returns the most recent available ECMWF run (00 or 12 UTC).
ECMWF_MODEL = "ecmwf_ifs025"

# Hourly variables to request. Open-Meteo resamples ECMWF to hourly for us.
HOURLY_VARS = ",".join([
    "temperature_2m",       # °C
    "windspeed_10m",        # requested in knots (wind_speed_unit=kn)
    "winddirection_10m",    # degrees
    "windgusts_10m",        # knots
    "precipitation",        # mm/h  → we sum to 6-hourly
    "cloudcover",           # %
    "pressure_msl",         # hPa  (mean sea level pressure)
    "visibility",           # metres
    "cape",                 # J/kg  (convective available potential energy)
])


# ── Fetch ─────────────────────────────────────────────────────────────────────

_FETCH_RETRIES    = 3
_FETCH_RETRY_DELAY = 5   # seconds between attempts


def fetch_ecmwf_json() -> dict:
    params = {
        "latitude":           KEELUNG_LAT,
        "longitude":          KEELUNG_LON,
        "hourly":             HOURLY_VARS,
        "models":             ECMWF_MODEL,
        "wind_speed_unit":    "kn",
        "temperature_unit":   "celsius",
        "precipitation_unit": "mm",
        "timeformat":         "iso8601",
        "forecast_days":      7,          # int, not string
        "timezone":           "UTC",
    }
    url = OPEN_METEO_URL + "?" + urllib.parse.urlencode(params)
    print("  Fetching ECMWF IFS from Open-Meteo …", flush=True)
    last_exc: Exception = RuntimeError("no attempts made")
    for attempt in range(1, _FETCH_RETRIES + 1):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                return json.load(r)
        except urllib.error.URLError as e:
            last_exc = e
            if attempt < _FETCH_RETRIES:
                print(f"  ↻  Request failed ({e}); retry {attempt}/{_FETCH_RETRIES} "
                      f"in {_FETCH_RETRY_DELAY}s …", file=sys.stderr)
                time.sleep(_FETCH_RETRY_DELAY)
    print(f"  ✗  Open-Meteo request failed after {_FETCH_RETRIES} attempts: {last_exc}",
          file=sys.stderr)
    sys.exit(1)


# ── Process ───────────────────────────────────────────────────────────────────

def _norm_utc(iso: str) -> str:
    """
    Normalise any ISO-8601 string to the same format wrf_analyze uses:
    '2026-03-09T06:00:00+00:00'
    Open-Meteo returns bare 'YYYY-MM-DDTHH:MM' with timezone=UTC, so we add
    the explicit offset so string comparison with WRF valid_utc works directly.
    """
    iso = iso.strip()
    if len(iso) == 16:               # YYYY-MM-DDTHH:MM
        iso += ":00+00:00"
    elif len(iso) == 19:             # YYYY-MM-DDTHH:MM:SS
        iso += "+00:00"
    return iso


def process(raw: dict) -> tuple[dict, list]:
    """
    Convert Open-Meteo hourly response to 6-hourly records.

    For variables measured instantaneously (temperature, wind, pressure, cloud,
    visibility) we sample at the 6-hourly timestamps.

    For precipitation we sum the 6 hourly values *ending* at each 6h timestamp
    to match the WRF 'precip_mm_6h' convention.

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

    records = []
    for i, t in enumerate(times):
        dt = datetime.fromisoformat(t if len(t) >= 19 else t + ':00').replace(tzinfo=timezone.utc)
        if dt.hour % 6 != 0:
            continue

        # Precipitation: sum hours [i-5 .. i] inclusive (6-hour window)
        precip_6h = sum(
            (safe(precip, j) or 0.0)
            for j in range(max(0, i - 5), i + 1)
        )

        # Visibility: metres → km
        vis_val = safe(vis, i)
        vis_km  = round(vis_val / 1000, 1) if vis_val is not None else None

        records.append({
            "valid_utc":    _norm_utc(t),
            "temp_c":       safe(temp,   i),
            "wind_kt":      safe(wspd,   i),
            "wind_dir":     safe(wdir,   i),
            "gust_kt":      safe(gust,   i),
            "mslp_hpa":     safe(mslp,   i),
            "precip_mm_6h": round(precip_6h, 2),
            "cloud_pct":    safe(cloud,  i),
            "vis_km":       vis_km,
            "cape":         safe(cape,   i),
        })

    # ECMWF init time: first time entry in the response
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
    meta, records = process(raw)

    if not records:
        print("  ⚠  No records extracted from Open-Meteo response.", file=sys.stderr)
        sys.exit(1)

    summary = {"meta": meta, "records": records}
    out = Path(args.output)
    out.write_text(json.dumps(summary, indent=2))
    print(f"  📊  ECMWF summary → {out}  ({len(records)} 6-hourly steps)")

    gha = os.environ.get("GITHUB_OUTPUT")
    if gha:
        with open(gha, "a") as f:
            f.write(f"ecmwf_json={out.resolve()}\n")


if __name__ == "__main__":
    main()
