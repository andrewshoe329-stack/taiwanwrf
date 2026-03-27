#!/usr/bin/env python3
"""
wind_grid_fetch.py
==================
Fetch gridded u/v wind components from Open-Meteo for ECMWF IFS, GFS, and
ICON models over a Taiwan-wide bounding box.

Creates a regular lat/lon grid per model, fetches wind_speed_10m and
wind_direction_10m for each grid point via Open-Meteo, converts to u/v
components, and writes one JSON file per model.

No API key required — Open-Meteo is free up to 10,000 requests/day.
No extra dependencies — uses only stdlib (urllib) + json + math.

Usage:
  python wind_grid_fetch.py [--output-dir frontend/public/data]
  python wind_grid_fetch.py --lat-min 24.0 --lat-max 26.0 --lon-min 120.0 --lon-max 122.5
"""

import argparse
import json
import logging
import math
import os
import sys
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from config import fetch_json as _fetch_json_shared
from config import norm_utc, setup_logging

log = logging.getLogger(__name__)

# ── Default bounding box (Taiwan-wide) ───────────────────────────────────────

DEFAULT_LAT_MIN = 21.5
DEFAULT_LAT_MAX = 25.5
DEFAULT_LON_MIN = 119.0
DEFAULT_LON_MAX = 122.5

# ── Model configurations ─────────────────────────────────────────────────────

MODEL_CONFIGS = {
    "ecmwf": {
        "id": "ECMWF-IFS",
        "url": "https://api.open-meteo.com/v1/ecmwf",
        "om_model": "ecmwf_ifs025",
        "resolution": 0.25,
    },
    "gfs": {
        "id": "GFS",
        "url": "https://api.open-meteo.com/v1/forecast",
        "om_model": "gfs_global",
        "resolution": 0.25,
    },
    "icon": {
        "id": "ICON",
        "url": "https://api.open-meteo.com/v1/dwd-icon",
        "om_model": "icon_global",
        "resolution": 0.125,
    },
}

# Forecast hours: every 6h out to 168h (7 days) → 29 timesteps
FORECAST_DAYS = 7

# Max parallel workers for API calls
MAX_WORKERS = 8


# ── Grid generation ──────────────────────────────────────────────────────────

def make_grid(lat_min: float, lat_max: float, lon_min: float, lon_max: float,
              resolution: float) -> tuple[list[float], list[float]]:
    """Generate regular lat/lon grid points within the bounding box.

    Returns (lats, lons) where lats is sorted south→north and lons west→east.
    """
    lats = []
    lat = lat_min
    while lat <= lat_max + 1e-9:
        lats.append(round(lat, 6))
        lat += resolution
    lons = []
    lon = lon_min
    while lon <= lon_max + 1e-9:
        lons.append(round(lon, 6))
        lon += resolution
    return lats, lons


def wind_to_uv(speed: float, direction_deg: float) -> tuple[float, float]:
    """Convert wind speed (m/s) and meteorological direction (degrees) to u/v.

    Meteorological convention: direction is where the wind comes FROM.
      u = -speed * sin(dir)
      v = -speed * cos(dir)
    """
    rad = math.radians(direction_deg)
    u = -speed * math.sin(rad)
    v = -speed * math.cos(rad)
    return round(u, 2), round(v, 2)


# ── Fetching ─────────────────────────────────────────────────────────────────

def _fetch_point(url: str, lat: float, lon: float, om_model: str,
                 ) -> tuple[float, float, dict | None]:
    """Fetch wind data for a single grid point. Returns (lat, lon, raw_json)."""
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "windspeed_10m,winddirection_10m",
        "models": om_model,
        "wind_speed_unit": "ms",
        "timeformat": "iso8601",
        "forecast_days": FORECAST_DAYS,
        "timezone": "UTC",
    }
    full_url = url + "?" + urllib.parse.urlencode(params)
    label = f"{om_model} ({lat:.3f},{lon:.3f})"
    raw = _fetch_json_shared(full_url, label=label, retries=3, retry_delay=5)
    return lat, lon, raw


def fetch_model_grid(model_key: str, lats: list[float], lons: list[float],
                     ) -> dict | None:
    """Fetch wind grid for a single model using parallel point requests.

    Returns the assembled model dict or None on failure.
    """
    cfg = MODEL_CONFIGS[model_key]
    model_id = cfg["id"]
    url = cfg["url"]
    om_model = cfg["om_model"]
    ny = len(lats)
    nx = len(lons)
    total = ny * nx
    log.info("Fetching %s grid: %d x %d = %d points", model_id, nx, ny, total)

    # Fetch all grid points in parallel
    point_data: dict[tuple[float, float], dict] = {}
    failed = 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {}
        for lat in lats:
            for lon in lons:
                f = pool.submit(_fetch_point, url, lat, lon, om_model)
                futures[f] = (lat, lon)

        for future in as_completed(futures):
            lat, lon = futures[future]
            try:
                rlat, rlon, raw = future.result()
                if raw is not None:
                    point_data[(rlat, rlon)] = raw
                else:
                    failed += 1
            except Exception as e:
                log.error("Exception fetching %s (%.3f,%.3f): %s",
                          model_id, lat, lon, e)
                failed += 1

    if failed > 0:
        log.warning("%s: %d/%d points failed", model_id, failed, total)
    if not point_data:
        log.error("%s: no data retrieved", model_id)
        return None

    # Extract timesteps from the first successful point
    sample = next(iter(point_data.values()))
    hourly = sample.get("hourly", {})
    all_times = hourly.get("time", [])
    if not all_times:
        log.error("%s: no time array in response", model_id)
        return None

    # Filter to 6-hourly timesteps
    valid_indices = []
    valid_times = []
    for i, t in enumerate(all_times):
        # Parse hour from ISO timestamp (e.g. "2026-03-27T06:00")
        try:
            dt = datetime.fromisoformat(t.replace('Z', '+00:00'))
            hour = dt.hour
        except (ValueError, TypeError):
            continue
        if hour % 6 == 0:
            valid_indices.append(i)
            valid_times.append(norm_utc(t))

    log.info("%s: %d 6-hourly timesteps from %d hourly values",
             model_id, len(valid_times), len(all_times))

    # Build u/v grids for each timestep
    # Grid layout: u[iy][ix] where iy=0 is lat_min (south), ix=0 is lon_min (west)
    timesteps = []
    for ti, vi in enumerate(valid_indices):
        u_grid = []
        v_grid = []
        for iy, lat in enumerate(lats):
            u_row = []
            v_row = []
            for ix, lon in enumerate(lons):
                raw = point_data.get((lat, lon))
                if raw is None:
                    u_row.append(None)
                    v_row.append(None)
                    continue
                h = raw.get("hourly", {})
                spd_arr = h.get("windspeed_10m", [])
                dir_arr = h.get("winddirection_10m", [])
                spd = spd_arr[vi] if vi < len(spd_arr) else None
                wdir = dir_arr[vi] if vi < len(dir_arr) else None
                if spd is not None and wdir is not None:
                    u, v = wind_to_uv(spd, wdir)
                    u_row.append(u)
                    v_row.append(v)
                else:
                    u_row.append(None)
                    v_row.append(None)
            u_grid.append(u_row)
            v_grid.append(v_row)
        timesteps.append({
            "valid_utc": valid_times[ti],
            "u": u_grid,
            "v": v_grid,
        })

    return {
        "model": model_id,
        "bounds": {
            "lat_min": lats[0],
            "lat_max": lats[-1],
            "lon_min": lons[0],
            "lon_max": lons[-1],
        },
        "grid": {"nx": nx, "ny": ny},
        "timesteps": timesteps,
    }


# ── CLI ──────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(
        description="Fetch gridded u/v wind from Open-Meteo for ECMWF, GFS, ICON."
    )
    ap.add_argument("--output-dir", default="frontend/public/data",
                    help="Output directory (default: frontend/public/data)")
    ap.add_argument("--lat-min", type=float, default=DEFAULT_LAT_MIN,
                    help=f"South boundary (default: {DEFAULT_LAT_MIN})")
    ap.add_argument("--lat-max", type=float, default=DEFAULT_LAT_MAX,
                    help=f"North boundary (default: {DEFAULT_LAT_MAX})")
    ap.add_argument("--lon-min", type=float, default=DEFAULT_LON_MIN,
                    help=f"West boundary (default: {DEFAULT_LON_MIN})")
    ap.add_argument("--lon-max", type=float, default=DEFAULT_LON_MAX,
                    help=f"East boundary (default: {DEFAULT_LON_MAX})")
    ap.add_argument("--models", default="ecmwf,gfs,icon",
                    help="Comma-separated model list (default: ecmwf,gfs,icon)")
    args = ap.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    requested_models = [m.strip() for m in args.models.split(",")]
    for m in requested_models:
        if m not in MODEL_CONFIGS:
            log.error("Unknown model: %s (valid: %s)", m,
                      ", ".join(MODEL_CONFIGS.keys()))
            sys.exit(1)

    success_count = 0

    for model_key in requested_models:
        cfg = MODEL_CONFIGS[model_key]
        resolution = cfg["resolution"]
        lats, lons = make_grid(args.lat_min, args.lat_max,
                               args.lon_min, args.lon_max, resolution)
        log.info("%s grid: %d lats x %d lons (%.3f° resolution)",
                 cfg["id"], len(lats), len(lons), resolution)

        result = fetch_model_grid(model_key, lats, lons)
        if result is None:
            log.error("Failed to fetch %s grid", cfg["id"])
            continue

        out_path = out_dir / f"wind_grid_{model_key}.json"
        out_path.write_text(json.dumps(result, indent=2, allow_nan=False))
        log.info("Wrote %s (%d timesteps, %d x %d grid)",
                 out_path, len(result["timesteps"]),
                 result["grid"]["nx"], result["grid"]["ny"])
        success_count += 1

    if success_count == 0:
        log.error("No models fetched successfully")
        sys.exit(1)

    log.info("Done: %d/%d models written to %s",
             success_count, len(requested_models), out_dir)

    gha = os.environ.get("GITHUB_OUTPUT")
    if gha:
        with open(gha, "a") as f:
            f.write(f"wind_grid_dir={out_dir.resolve()}\n")


if __name__ == "__main__":
    setup_logging()
    main()
