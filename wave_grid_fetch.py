#!/usr/bin/env python3
"""
wave_grid_fetch.py
==================
Fetch gridded wave data from Open-Meteo marine API for northern Taiwan.

Creates a regular lat/lon grid, fetches wave_height, swell_wave_height,
swell_wave_direction, swell_wave_period for each point, and writes
JSON files for frontend heatmap/arrow overlay on the map.

Usage:
  python wave_grid_fetch.py [--output-dir frontend/public/data]
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

from config import setup_logging, fetch_json, TAIWAN_BBOX

log = logging.getLogger(__name__)

# ── Grid generation ─────────────────────────────────────────────────────────

FORECAST_DAYS = 5
MARINE_API_URL = "https://marine-api.open-meteo.com/v1/marine"
RESOLUTION = 0.25  # degrees (~25km)


def make_grid(lat_min, lat_max, lon_min, lon_max, resolution=RESOLUTION):
    """Generate regular lat/lon grid arrays."""
    lats, lons = [], []
    lat = lat_min
    while lat <= lat_max + 1e-9:
        lats.append(round(lat, 6))
        lat += resolution
    lon = lon_min
    while lon <= lon_max + 1e-9:
        lons.append(round(lon, 6))
        lon += resolution
    return lats, lons


# ── Fetching ────────────────────────────────────────────────────────────────

def _fetch_point(lat: float, lon: float) -> tuple[float, float, dict | None]:
    """Fetch wave data for a single grid point."""
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "wave_height,swell_wave_height,swell_wave_direction,swell_wave_period",
        "timeformat": "iso8601",
        "forecast_days": FORECAST_DAYS,
        "timezone": "UTC",
    }
    url = MARINE_API_URL + "?" + urllib.parse.urlencode(params)
    label = f"Marine ({lat:.3f},{lon:.3f})"
    raw = fetch_json(url, label=label, retries=3, retry_delay=5)
    return lat, lon, raw


def fetch_wave_grid(lats: list[float], lons: list[float]) -> dict | None:
    """Fetch wave grid for all points using parallel requests."""
    points = [(lat, lon) for lat in lats for lon in lons]
    log.info("Fetching wave grid: %d points (%dx%d)",
             len(points), len(lats), len(lons))

    results = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(_fetch_point, lat, lon): (lat, lon)
                   for lat, lon in points}
        for fut in as_completed(futures):
            lat, lon, raw = fut.result()
            if raw and "hourly" in raw:
                results[(lat, lon)] = raw["hourly"]

    if len(results) < len(points) * 0.5:
        log.warning("Only %d/%d wave grid points succeeded",
                    len(results), len(points))
        if not results:
            return None

    # Build timestep arrays
    # Use first successful point to get time axis
    sample = next(iter(results.values()))
    times = sample.get("time", [])

    timesteps = []
    for ti, t in enumerate(times):
        # Build 2D arrays [lat_idx][lon_idx]
        hs_grid = []
        swell_h_grid = []
        swell_dir_grid = []
        swell_p_grid = []

        for lat in lats:
            hs_row, sh_row, sd_row, sp_row = [], [], [], []
            for lon in lons:
                data = results.get((lat, lon))
                if data and ti < len(data.get("wave_height", [])):
                    hs_row.append(data["wave_height"][ti])
                    sh_row.append(data.get("swell_wave_height", [None] * (ti + 1))[ti])
                    sd_row.append(data.get("swell_wave_direction", [None] * (ti + 1))[ti])
                    sp_row.append(data.get("swell_wave_period", [None] * (ti + 1))[ti])
                else:
                    hs_row.append(None)
                    sh_row.append(None)
                    sd_row.append(None)
                    sp_row.append(None)
            hs_grid.append(hs_row)
            swell_h_grid.append(sh_row)
            swell_dir_grid.append(sd_row)
            swell_p_grid.append(sp_row)

        timesteps.append({
            "valid_utc": t if t.endswith("+00:00") or t.endswith("Z") else t + "+00:00",
            "wave_height": hs_grid,
            "swell_height": swell_h_grid,
            "swell_direction": swell_dir_grid,
            "swell_period": swell_p_grid,
        })

    return {
        "model": "ECMWF-WAM",
        "bounds": {
            "lat_min": lats[0], "lat_max": lats[-1],
            "lon_min": lons[0], "lon_max": lons[-1],
        },
        "grid": {"nx": len(lons), "ny": len(lats)},
        "timesteps": timesteps,
    }


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Fetch gridded wave data")
    ap.add_argument("--output-dir", default="frontend/public/data",
                    help="Output directory for JSON files")
    ap.add_argument("--lat-min", type=float, default=TAIWAN_BBOX["lat_min"])
    ap.add_argument("--lat-max", type=float, default=TAIWAN_BBOX["lat_max"])
    ap.add_argument("--lon-min", type=float, default=TAIWAN_BBOX["lon_min"])
    ap.add_argument("--lon-max", type=float, default=TAIWAN_BBOX["lon_max"])
    ap.add_argument("--resolution", type=float, default=RESOLUTION)
    args = ap.parse_args()

    setup_logging()

    lats, lons = make_grid(args.lat_min, args.lat_max,
                           args.lon_min, args.lon_max, args.resolution)
    log.info("Grid: %d lats x %d lons = %d points",
             len(lats), len(lons), len(lats) * len(lons))

    result = fetch_wave_grid(lats, lons)
    if not result:
        log.error("Failed to fetch wave grid")
        sys.exit(1)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "wave_grid.json"

    with open(out_path, "w") as f:
        json.dump(result, f, separators=(",", ":"))
    log.info("Wrote %s (%d timesteps, %.1fKB)",
             out_path, len(result["timesteps"]),
             out_path.stat().st_size / 1024)


if __name__ == "__main__":
    main()
