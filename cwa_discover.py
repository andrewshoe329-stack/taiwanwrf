#!/usr/bin/env python3
"""
cwa_discover.py — Discover all CWA weather stations and wave buoys,
map nearest ones to each surf spot, and write cwa_stations.json.

Run monthly via GitHub Actions (cwa-discover.yml) or manually:
    python cwa_discover.py --api-key CWA-XXXX --output cwa_stations.json

The output file is committed to the repo and read by cwa_fetch.py at runtime
so the main pipeline doesn't need to re-discover stations every run.
"""

import argparse
import json
import logging
import os
from datetime import datetime, timezone

from config import KEELUNG_LAT, KEELUNG_LON, SPOT_COORDS, setup_logging
from cwa_fetch import (
    _cwa_get,
    _haversine_km,
    _parse_buoy_station,
    STATION_ENDPOINT,
    MARINE_OBS_ENDPOINT,
    _group_flat_rows_to_stations,
    norm_utc,
)

log = logging.getLogger(__name__)


# ── Fetch all weather stations ───────────────────────────────────────────────

def fetch_all_weather_stations(api_key: str) -> list[dict]:
    """Fetch ALL CWA automatic weather stations (O-A0001-001) with no filter.

    Returns a list of dicts, each with:
        station_id, station_name, lat, lon
    """
    data = _cwa_get(STATION_ENDPOINT, api_key, params={},
                    label="CWA-AllStations")
    if not data:
        return []

    try:
        records = (data.get("records") or data.get("Records")
                   or data.get("Result") or {})
        stations = records.get("Station", records.get("location", []))
        if not stations:
            log.warning("No station data in CWA all-stations response")
            return []

        result = []
        for stn in stations:
            sid = (stn.get("StationId") or stn.get("stationId")
                   or stn.get("StationID") or "")
            name = stn.get("StationName", stn.get("locationName", ""))

            # Extract lat/lon from GeoInfo or top-level keys
            geo = stn.get("GeoInfo", stn.get("geoInfo", {}))
            lat = _try_float(geo.get("Latitude", geo.get("latitude")))
            lon = _try_float(geo.get("Longitude", geo.get("longitude")))

            # Some formats have coordinates at top level
            if lat is None:
                for k in ("StationLatitude", "Latitude", "lat"):
                    v = _try_float(stn.get(k))
                    if v is not None:
                        lat = v
                        break
            if lon is None:
                for k in ("StationLongitude", "Longitude", "lon"):
                    v = _try_float(stn.get(k))
                    if v is not None:
                        lon = v
                        break

            if sid and lat is not None and lon is not None:
                result.append({
                    "station_id": sid,
                    "station_name": name,
                    "lat": round(lat, 5),
                    "lon": round(lon, 5),
                })

        log.info("Discovered %d weather stations with coordinates", len(result))
        return result

    except Exception as e:
        log.error("Failed to parse all-stations response: %s", e)
        return []


# ── Fetch all marine buoys ───────────────────────────────────────────────────

def fetch_all_marine_buoys(api_key: str) -> list[dict]:
    """Fetch ALL CWA marine buoy/tide stations (O-B0075-001) with no filter.

    Returns a list of dicts, each with:
        buoy_id, buoy_name, lat, lon
    """
    data = _cwa_get(MARINE_OBS_ENDPOINT, api_key, params={},
                    label="CWA-AllMarine")
    if not data:
        return []

    try:
        records = (data.get("records") or data.get("Records")
                   or data.get("Result") or {})

        # Handle flat tabular format
        if isinstance(records, list) and records:
            stations = _group_flat_rows_to_stations(records)
        else:
            # Standard nested format
            stations = None
            sea_obs = records.get("SeaSurfaceObs", {})
            if isinstance(sea_obs, dict):
                stations = sea_obs.get("Location", [])
            if not stations:
                for key in ("Station", "location", "SeaConditionStation",
                            "Location"):
                    v = records.get(key) if isinstance(records, dict) else None
                    if v:
                        stations = v
                        break
            if not stations:
                log.warning("No marine data in CWA all-marine response")
                return []
            if not isinstance(stations, list):
                stations = [stations]

            # Flatten nested structures (same logic as _fetch_marine_stations)
            flattened = []
            for stn in stations:
                if not isinstance(stn, dict):
                    continue
                merged = dict(stn)
                if "Station" in stn and isinstance(stn["Station"], dict):
                    merged.update(stn["Station"])

                obs_times = stn.get("StationObsTimes")
                if obs_times is None:
                    obs_status = stn.get("StationObsStatus") or {}
                    obs_times = obs_status.get("StationObsTimes")
                if isinstance(obs_times, dict):
                    obs_times = obs_times.get("StationObsTime", [])
                if isinstance(obs_times, list) and obs_times:
                    valid_obs = [
                        o for o in obs_times
                        if isinstance(o, dict) and o.get("DateTime")
                    ]
                    valid_obs.sort(
                        key=lambda o: o.get("DateTime", ""), reverse=True)
                    if valid_obs:
                        latest = valid_obs[0]
                        we = latest.get("WeatherElements", {})
                        if isinstance(we, dict):
                            merged["WeatherElement"] = we
                            merged.setdefault(
                                "ObsTime", {"DateTime": latest["DateTime"]})

                for lat_key in ("StationLatitude", "Latitude"):
                    if lat_key in merged:
                        merged.setdefault("GeoInfo", {}).setdefault(
                            "Latitude", merged[lat_key])
                        break
                for lon_key in ("StationLongitude", "Longitude"):
                    if lon_key in merged:
                        merged.setdefault("GeoInfo", {}).setdefault(
                            "Longitude", merged[lon_key])
                        break

                flattened.append(merged)
            stations = flattened

        # Parse each into buoy dict and extract just id/name/lat/lon
        result = []
        seen_ids = set()
        for stn in stations:
            parsed = _parse_buoy_station(stn)
            if parsed and parsed["buoy_id"] not in seen_ids:
                seen_ids.add(parsed["buoy_id"])
                entry = {
                    "buoy_id": parsed["buoy_id"],
                    "buoy_name": parsed.get("buoy_name", ""),
                    "lat": round(parsed["lat"], 5) if parsed.get("lat") else None,
                    "lon": round(parsed["lon"], 5) if parsed.get("lon") else None,
                }
                result.append(entry)

        # Also include tide-only stations (no wave data) for completeness
        for stn in stations:
            sid = (stn.get("StationId") or stn.get("StationID")
                   or stn.get("stationId") or "")
            if sid and sid not in seen_ids:
                geo = stn.get("GeoInfo", {})
                lat = _try_float(geo.get("Latitude", geo.get("latitude")))
                lon = _try_float(geo.get("Longitude", geo.get("longitude")))
                if lat is not None and lon is not None:
                    seen_ids.add(sid)
                    result.append({
                        "buoy_id": sid,
                        "buoy_name": stn.get("StationName",
                                             stn.get("stationName", sid)),
                        "lat": round(lat, 5),
                        "lon": round(lon, 5),
                    })

        log.info("Discovered %d marine stations/buoys", len(result))
        return result

    except Exception as e:
        log.error("Failed to parse all-marine response: %s", e)
        return []


# ── Nearest-match logic ──────────────────────────────────────────────────────

def find_nearest(items: list[dict], lat: float, lon: float,
                 lat_key: str = "lat", lon_key: str = "lon",
                 max_dist_km: float = 100) -> tuple[dict | None, float | None]:
    """Find the nearest item to (lat, lon). Returns (item, distance_km)."""
    best = None
    best_dist = float('inf')
    for item in items:
        item_lat = item.get(lat_key)
        item_lon = item.get(lon_key)
        if item_lat is not None and item_lon is not None:
            dist = _haversine_km(lat, lon, item_lat, item_lon)
            if dist < best_dist:
                best_dist = dist
                best = item
    if best and best_dist <= max_dist_km:
        return best, round(best_dist, 1)
    return None, None


def build_station_mapping(all_stations: list[dict],
                          all_buoys: list[dict]) -> dict:
    """Map each spot to its nearest weather station and buoy.

    Returns a dict keyed by spot ID with station_id, buoy_id, distances.
    """
    spots = {}
    for coord in SPOT_COORDS:
        sid = coord["id"]
        lat, lon = coord["lat"], coord["lon"]

        stn, stn_dist = find_nearest(all_stations, lat, lon,
                                     max_dist_km=50)
        buoy, buoy_dist = find_nearest(all_buoys, lat, lon,
                                       max_dist_km=100)

        entry = {}
        if stn:
            entry["station_id"] = stn["station_id"]
            entry["station_name"] = stn.get("station_name", "")
            entry["station_dist_km"] = stn_dist
        if buoy:
            entry["buoy_id"] = buoy["buoy_id"]
            entry["buoy_name"] = buoy.get("buoy_name", "")
            entry["buoy_dist_km"] = buoy_dist

        spots[sid] = entry

    return spots


# ── Helpers ──────────────────────────────────────────────────────────────────

def _try_float(v) -> float | None:
    """Try to convert a value to float, return None on failure."""
    if v is None or v == "" or v == "-99":
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(
        description="Discover CWA stations/buoys and map to surf spots")
    ap.add_argument("--api-key", default=os.environ.get("CWA_OPENDATA_KEY"),
                    help="CWA Open Data API key (or CWA_OPENDATA_KEY env var)")
    ap.add_argument("--output", default="cwa_stations.json",
                    help="Output JSON file path")
    args = ap.parse_args()

    setup_logging()

    if not args.api_key:
        log.error("No CWA API key provided (--api-key or CWA_OPENDATA_KEY)")
        raise SystemExit(1)

    log.info("Discovering CWA weather stations …")
    all_stations = fetch_all_weather_stations(args.api_key)

    log.info("Discovering CWA marine buoys/tide stations …")
    all_buoys = fetch_all_marine_buoys(args.api_key)

    log.info("Mapping nearest stations/buoys to %d spots …",
             len(SPOT_COORDS))
    spot_mapping = build_station_mapping(all_stations, all_buoys)

    for sid, entry in spot_mapping.items():
        stn_info = (f"stn {entry.get('station_id', '?')} "
                    f"({entry.get('station_dist_km', '?')}km)"
                    if 'station_id' in entry else "no station")
        buoy_info = (f"buoy {entry.get('buoy_id', '?')} "
                     f"({entry.get('buoy_dist_km', '?')}km)"
                     if 'buoy_id' in entry else "no buoy")
        log.info("  %s: %s | %s", sid, stn_info, buoy_info)

    output = {
        "discovered_utc": datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%S+00:00"),
        "spots": spot_mapping,
        "all_stations": all_stations,
        "all_buoys": all_buoys,
    }

    with open(args.output, "w") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    log.info("Wrote %s (%d stations, %d buoys, %d spot mappings)",
             args.output, len(all_stations), len(all_buoys),
             len(spot_mapping))


if __name__ == "__main__":
    main()
