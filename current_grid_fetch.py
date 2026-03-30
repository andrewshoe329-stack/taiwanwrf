#!/usr/bin/env python3
"""
current_grid_fetch.py
=====================
Fetch gridded ocean current data from Open-Meteo marine API for northern Taiwan.

Creates a regular lat/lon grid, fetches ocean_current_velocity and
ocean_current_direction for each point, and writes a JSON file for
frontend animated particle overlay on the map.

Usage:
  python current_grid_fetch.py [--output-dir frontend/public/data]
"""

import argparse
import json
import logging
import sys
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from config import setup_logging, fetch_json, TAIWAN_BBOX

log = logging.getLogger(__name__)

FORECAST_DAYS = 5
MARINE_API_URL = "https://marine-api.open-meteo.com/v1/marine"
RESOLUTION = 0.1  # degrees (~10km)


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


def _fetch_point(lat: float, lon: float) -> tuple[float, float, dict | None]:
    """Fetch ocean current data for a single grid point."""
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "ocean_current_velocity,ocean_current_direction",
        "timeformat": "iso8601",
        "forecast_days": FORECAST_DAYS,
        "timezone": "UTC",
    }
    url = MARINE_API_URL + "?" + urllib.parse.urlencode(params)
    label = f"Current ({lat:.3f},{lon:.3f})"
    raw = fetch_json(url, label=label, retries=3, retry_delay=5)
    return lat, lon, raw


def fetch_current_grid(lats: list[float], lons: list[float]) -> dict | None:
    """Fetch ocean current grid for all points using parallel requests."""
    points = [(lat, lon) for lat in lats for lon in lons]
    log.info("Fetching current grid: %d points (%dx%d)",
             len(points), len(lats), len(lons))

    results = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(_fetch_point, lat, lon): (lat, lon)
                   for lat, lon in points}
        for fut in as_completed(futures):
            lat, lon, raw = fut.result()
            if raw and "hourly" in raw:
                results[(lat, lon)] = raw["hourly"]

    if len(results) < len(points) * 0.5:
        log.warning("Only %d/%d current grid points succeeded",
                    len(results), len(points))
        if not results:
            return None

    sample = next(iter(results.values()))
    times = sample.get("time", [])

    # Filter to 3-hourly timesteps to keep file size down
    timesteps = []
    for ti, t in enumerate(times):
        # Parse hour from ISO timestamp
        try:
            hour = int(t[11:13])
        except (ValueError, IndexError):
            continue
        if hour % 3 != 0:
            continue

        vel_grid = []
        dir_grid = []

        for lat in lats:
            vel_row, dir_row = [], []
            for lon in lons:
                data = results.get((lat, lon))
                if data:
                    vel = data.get("ocean_current_velocity", [])
                    cdir = data.get("ocean_current_direction", [])
                    vel_row.append(vel[ti] if ti < len(vel) else None)
                    dir_row.append(cdir[ti] if ti < len(cdir) else None)
                else:
                    vel_row.append(None)
                    dir_row.append(None)
            vel_grid.append(vel_row)
            dir_grid.append(dir_row)

        timesteps.append({
            "valid_utc": t if t.endswith("+00:00") or t.endswith("Z") else t + "+00:00",
            "velocity": vel_grid,
            "direction": dir_grid,
        })

    return {
        "model": "CMEMS",
        "bounds": {
            "lat_min": lats[0], "lat_max": lats[-1],
            "lon_min": lons[0], "lon_max": lons[-1],
        },
        "grid": {"nx": len(lons), "ny": len(lats)},
        "timesteps": timesteps,
    }


def main():
    ap = argparse.ArgumentParser(description="Fetch gridded ocean current data")
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

    result = fetch_current_grid(lats, lons)
    if not result:
        log.error("Failed to fetch current grid")
        sys.exit(1)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "current_grid.json"
    out_path.write_text(json.dumps(result), encoding="utf-8")
    log.info("Wrote %s (%d timesteps, %.1f KB)",
             out_path, len(result["timesteps"]),
             out_path.stat().st_size / 1024)


if __name__ == "__main__":
    main()
