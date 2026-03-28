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
)

log = logging.getLogger(__name__)

# Known CWA marine station coordinates (fixed instruments, rarely move).
# These serve as fallback if the API response doesn't include coordinates.
# Source: CWA Open Data portal station metadata
KNOWN_BUOY_COORDS = {
    "46694A": (25.097, 121.925, "龍洞"),     # Longdong buoy
    "46708A": (25.304, 121.532, "富貴角"),    # Fuguijiao buoy
    "46714C": (24.849, 121.838, "蘇澳"),     # Su-ao buoy
    "C6AH2":  (25.159, 121.740, "基隆"),      # Keelung
    "C6W08":  (24.968, 121.924, "頭城"),      # Toucheng
    "COMC06": (25.176, 121.762, "基隆嶼"),    # Keelung Islet
    "C4B01":  (25.133, 121.742, "基隆潮位"),   # Keelung tide station
}

# Known CWA weather station coordinates (for northern Taiwan area).
# Fallback if O-A0001-001 response doesn't include GeoInfo.
KNOWN_STATION_COORDS = {
    "466940": (25.133, 121.740, "基隆"),      # Keelung
    "466950": (25.130, 121.731, "彭佳嶼"),    # Pengjiayu
    "466880": (25.163, 121.529, "板橋"),      # Banqiao
    "466910": (25.038, 121.515, "臺北"),      # Taipei
    "466920": (25.183, 121.530, "淡水"),      # Tamsui
    "C0A520": (25.026, 121.940, "福隆"),      # Fulong
    "C0A530": (25.222, 121.667, "金山"),      # Jinshan
    "C0A580": (25.189, 121.689, "萬里"),      # Wanli (near Green Bay)
    "C0U660": (24.870, 121.838, "蘇澳"),     # Su-ao
    "C0U700": (24.756, 121.757, "宜蘭"),      # Yilan
    "C0A9A0": (25.258, 121.614, "石門"),      # Shimen
    "C0A9F0": (25.135, 121.780, "基隆港"),    # Keelung Harbour
    "C0U620": (24.992, 121.918, "頭城"),      # Toucheng
    "C0U650": (24.854, 121.921, "蘇澳鎮"),   # Suao town (near Wushih)
}


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
            log.warning("No station data in CWA all-stations response "
                        "(records keys: %s)",
                        list(records.keys())[:15]
                        if isinstance(records, dict) else type(records))
            return []

        # Log the first station's structure for debugging
        if stations:
            first = stations[0] if isinstance(stations, list) else stations
            log.debug("First station keys: %s",
                      list(first.keys()) if isinstance(first, dict) else type(first))

        result = []
        for stn in stations:
            sid = (stn.get("StationId") or stn.get("stationId")
                   or stn.get("StationID") or "")
            name = stn.get("StationName", stn.get("locationName", ""))

            # Extract lat/lon — CWA nests coordinates in various structures:
            #   GeoInfo.Coordinates[0].StationLatitude / StationLongitude
            #   GeoInfo.Latitude / Longitude
            #   Top-level StationLatitude / Latitude / lat
            lat, lon = _extract_coords(stn)

            # Fallback to known coordinates if API didn't include them
            if (lat is None or lon is None) and sid in KNOWN_STATION_COORDS:
                lat, lon, _ = KNOWN_STATION_COORDS[sid]

            if sid and lat is not None and lon is not None:
                result.append({
                    "station_id": sid,
                    "station_name": name,
                    "lat": round(lat, 5),
                    "lon": round(lon, 5),
                })

        if not result and stations:
            # Stations were returned but no coordinates extracted — log sample
            first = stations[0] if isinstance(stations, list) else stations
            if isinstance(first, dict):
                log.warning("Stations found but no coordinates. "
                            "Sample keys: %s, GeoInfo: %s",
                            list(first.keys())[:10],
                            str(first.get("GeoInfo", "MISSING"))[:200])

        # If API returned no stations with coordinates, use known stations
        if not result and KNOWN_STATION_COORDS:
            log.info("Using %d known station coordinates as fallback",
                     len(KNOWN_STATION_COORDS))
            for sid, (lat, lon, name) in KNOWN_STATION_COORDS.items():
                result.append({
                    "station_id": sid,
                    "station_name": name,
                    "lat": lat,
                    "lon": lon,
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

        # Extract id/name/lat/lon from all marine stations
        # Use _extract_coords for coordinate extraction (handles nested formats)
        # Also try _parse_buoy_station for wave-data stations with GeoInfo
        result = []
        seen_ids = set()
        for stn in stations:
            sid = (stn.get("StationId") or stn.get("StationID")
                   or stn.get("stationId") or "")
            if not sid or sid in seen_ids:
                continue
            name = (stn.get("StationName") or stn.get("stationName")
                    or stn.get("locationName") or sid)

            lat, lon = _extract_coords(stn)

            # Also try _parse_buoy_station which has its own GeoInfo extraction
            if (lat is None or lon is None):
                parsed = _parse_buoy_station(stn)
                if parsed:
                    if lat is None and parsed.get("lat"):
                        lat = parsed["lat"]
                    if lon is None and parsed.get("lon"):
                        lon = parsed["lon"]

            # Fallback to known coordinates if API didn't include them
            if (lat is None or lon is None) and sid in KNOWN_BUOY_COORDS:
                flat, flon, fname = KNOWN_BUOY_COORDS[sid]
                lat = lat if lat is not None else flat
                lon = lon if lon is not None else flon
                if not name or name == sid:
                    name = fname

            seen_ids.add(sid)
            result.append({
                "buoy_id": sid,
                "buoy_name": name,
                "lat": round(lat, 5) if lat is not None else None,
                "lon": round(lon, 5) if lon is not None else None,
            })

        # Count how many have coordinates vs not
        with_coords = sum(1 for r in result if r["lat"] is not None)
        without_coords = len(result) - with_coords
        if without_coords:
            log.warning("%d marine stations have no coordinates "
                        "(will be skipped during spot mapping)", without_coords)

        # If very few buoys have coordinates, add known ones as fallback
        if with_coords < 3 and KNOWN_BUOY_COORDS:
            log.info("Adding %d known buoy coordinates as fallback",
                     len(KNOWN_BUOY_COORDS))
            for bid, (blat, blon, bname) in KNOWN_BUOY_COORDS.items():
                if bid not in seen_ids:
                    seen_ids.add(bid)
                    result.append({
                        "buoy_id": bid,
                        "buoy_name": bname,
                        "lat": blat,
                        "lon": blon,
                    })

        log.info("Discovered %d marine stations/buoys (%d with coordinates)",
                 len(result), sum(1 for r in result if r["lat"] is not None))
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

def _extract_coords(stn: dict) -> tuple[float | None, float | None]:
    """Extract lat/lon from a CWA station dict, trying multiple structures.

    CWA O-A0001-001 nests coordinates as:
      GeoInfo.Coordinates[0].StationLatitude / StationLongitude
    or GeoInfo.Latitude / Longitude

    O-B0075-001 may have StationLatitude at top level.
    """
    lat = lon = None

    geo = stn.get("GeoInfo", stn.get("geoInfo", {}))
    if isinstance(geo, dict):
        # Try direct GeoInfo.Latitude / Longitude
        lat = _try_float(geo.get("Latitude", geo.get("latitude")))
        lon = _try_float(geo.get("Longitude", geo.get("longitude")))

        # Try GeoInfo.Coordinates[0].StationLatitude etc.
        if lat is None or lon is None:
            coords = geo.get("Coordinates", geo.get("coordinates", []))
            if isinstance(coords, list) and coords:
                c = coords[0] if isinstance(coords[0], dict) else {}
                if lat is None:
                    lat = _try_float(
                        c.get("StationLatitude",
                        c.get("CoordinateLatitude",
                        c.get("Latitude"))))
                if lon is None:
                    lon = _try_float(
                        c.get("StationLongitude",
                        c.get("CoordinateLongitude",
                        c.get("Longitude"))))

        # Try GeoInfo.StationLatitude / StationLongitude
        if lat is None:
            lat = _try_float(geo.get("StationLatitude"))
        if lon is None:
            lon = _try_float(geo.get("StationLongitude"))

    # Fallback: top-level keys on the station dict
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

    return lat, lon


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
