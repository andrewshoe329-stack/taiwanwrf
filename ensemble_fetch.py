#!/usr/bin/env python3
"""
ensemble_fetch.py
=================
Fetch GFS and JMA global model forecasts from Open-Meteo and compute
multi-model ensemble statistics alongside the existing ECMWF IFS forecast.

Outputs ensemble_keelung.json with per-model records and pre-computed spread
statistics (min, max, mean, spread, n) for each variable at each timestep.

No API key required — Open-Meteo is free up to 10,000 requests/day.
No extra dependencies — uses only stdlib (urllib) + json.

Usage:
  python ensemble_fetch.py [--ecmwf-json ecmwf_keelung.json] [--output ensemble_keelung.json]
"""

import argparse
import json
import logging
import sys
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

from config import (KEELUNG_LAT, KEELUNG_LON, SPOT_COORDS, norm_utc,
                     setup_logging, aggregate_hourly_to_6h, run_parallel)
from config import fetch_json as _fetch_json_shared

log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

HOURLY_VARS = ",".join([
    "temperature_2m",
    "windspeed_10m",
    "winddirection_10m",
    "windgusts_10m",
    "precipitation",
    "cloudcover",
    "pressure_msl",
    "visibility",
    "cape",
])

# Models to fetch (excluding ECMWF which comes from ecmwf_fetch.py)
MODEL_CONFIGS = {
    "gfs_global":    {"id": "GFS-Global",    "om_model": "gfs_global"},
    "icon_global":   {"id": "ICON-Global",   "om_model": "icon_global"},
    "jma_gsm":       {"id": "JMA-GSM",       "om_model": "jma_gsm"},
}

# Variables to compute ensemble stats for
ENSEMBLE_VARS = ["temp_c", "wind_kt", "gust_kt", "mslp_hpa", "precip_mm_6h", "cape"]

# ── Fetch ─────────────────────────────────────────────────────────────────────

def _fetch_json(params: dict, label: str) -> dict | None:
    """Fetch from Open-Meteo with retry logic. Delegates to config.fetch_json."""
    url = OPEN_METEO_URL + "?" + urllib.parse.urlencode(params)
    return _fetch_json_shared(url, label=label)


def fetch_model(model_key: str, lat: float = KEELUNG_LAT,
                lon: float = KEELUNG_LON, label_suffix: str = "") -> dict | None:
    """Fetch a single model's forecast from Open-Meteo."""
    cfg = MODEL_CONFIGS[model_key]
    params = {
        "latitude":           lat,
        "longitude":          lon,
        "hourly":             HOURLY_VARS,
        "models":             cfg["om_model"],
        "wind_speed_unit":    "kn",
        "temperature_unit":   "celsius",
        "precipitation_unit": "mm",
        "timeformat":         "iso8601",
        "forecast_days":      7,
        "timezone":           "UTC",
    }
    label = cfg["id"] + (f" ({label_suffix})" if label_suffix else "")
    return _fetch_json(params, label)


# ── Process ───────────────────────────────────────────────────────────────────

def process_model(raw: dict, model_key: str) -> tuple[dict, list]:
    """Convert Open-Meteo hourly response to 6-hourly records.

    Delegates to shared ``aggregate_hourly_to_6h`` in config.py.
    """
    cfg = MODEL_CONFIGS[model_key]
    return aggregate_hourly_to_6h(raw, model_id=cfg["id"])


# ── Ensemble stats ────────────────────────────────────────────────────────────

def compute_ensemble_stats(
    all_model_records: dict[str, list[dict]],
) -> list[dict]:
    """Compute per-timestep ensemble statistics across all models.

    Args:
        all_model_records: {model_key: [record_dicts]} for each model

    Returns:
        List of dicts with ensemble stats per valid_utc.
    """
    # Collect all valid times across all models
    all_times: set[str] = set()
    for recs in all_model_records.values():
        for r in recs:
            if r.get("valid_utc"):
                all_times.add(r["valid_utc"])

    # Build lookup: {model: {valid_utc: record}}
    lookups = {}
    for model_key, recs in all_model_records.items():
        lookups[model_key] = {r["valid_utc"]: r for r in recs if r.get("valid_utc")}

    ensemble = []
    for vt in sorted(all_times):
        stats: dict = {"valid_utc": vt}
        for var in ENSEMBLE_VARS:
            values = []
            for model_key, lookup in lookups.items():
                rec = lookup.get(vt)
                if rec and rec.get(var) is not None:
                    values.append(rec[var])
            if values:
                stats[var] = {
                    "min":    round(min(values), 2),
                    "max":    round(max(values), 2),
                    "mean":   round(sum(values) / len(values), 2),
                    "spread": round(max(values) - min(values), 2),
                    "n":      len(values),
                }
            else:
                stats[var] = None
        ensemble.append(stats)

    return ensemble


# ── Main ──────────────────────────────────────────────────────────────────────

def _fetch_ensemble_for_point(lat: float, lon: float, label: str,
                               ecmwf_recs: list | None = None) -> dict | None:
    """Fetch all ensemble models for one point, compute stats, return output dict."""
    results: dict[str, dict | None] = {}
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {
            pool.submit(fetch_model, key, lat, lon, label): key
            for key in MODEL_CONFIGS
        }
        for future in as_completed(futures):
            key = futures[future]
            try:
                results[key] = future.result()
            except Exception as e:
                log.error("Failed to fetch %s for %s: %s", key, label, e)
                results[key] = None

    # Map API model keys to human-readable names
    API_TO_HUMAN = {
        "gfs_global": "GFS",
        "icon_global": "ICON",
        "jma_gsm": "JMA",
    }

    models_data: dict = {}
    all_model_records: dict[str, list[dict]] = {}
    for model_key, raw in results.items():
        if raw is None:
            continue
        meta, records = process_model(raw, model_key)
        if not records:
            continue
        human_key = API_TO_HUMAN.get(model_key, model_key)
        models_data[human_key] = {
            "meta": meta,
            "records": records,
        }
        all_model_records[human_key] = records

    # Include ECMWF in models output + ensemble stats when available
    if ecmwf_recs:
        all_model_records["ECMWF"] = ecmwf_recs
        models_data["ECMWF"] = {
            "meta": {"model_id": "ECMWF-IFS", "source": "ecmwf_keelung.json"},
            "records": ecmwf_recs,
        }

    if not all_model_records:
        return None

    ensemble_stats = compute_ensemble_stats(all_model_records)

    # Compute top-level spread summary (average across all timesteps)
    spread: dict = {}
    for var, spread_key in [("wind_kt", "wind_spread_kt"),
                            ("temp_c", "temp_spread_c"),
                            ("precip_mm_6h", "precip_spread_mm")]:
        spreads = [s[var]["spread"] for s in ensemble_stats
                   if s.get(var) and s[var].get("spread") is not None]
        if spreads:
            spread[spread_key] = round(sum(spreads) / len(spreads), 2)

    return {
        "models": models_data,
        "spread": spread,
    }


def _fetch_location(loc: dict) -> tuple[str, dict | None]:
    """Fetch ensemble for a single location. Returns (id, result_dict | None)."""
    loc_id = loc["id"]
    result = _fetch_ensemble_for_point(loc["lat"], loc["lon"], loc_id)
    if result:
        # Strip full records from per-location output to keep file size reasonable.
        # Keep only record_count + spread for non-Keelung locations.
        compact = {
            "models": {
                mk: {"meta": md["meta"], "record_count": len(md.get("records", []))}
                for mk, md in result["models"].items()
            },
            "spread": result["spread"],
        }
        return loc_id, compact
    return loc_id, None


def main() -> None:
    ap = argparse.ArgumentParser(description='Fetch multi-model ensemble forecasts')
    ap.add_argument('--ecmwf-json', default=None,
                    help='Path to ecmwf_keelung.json (include ECMWF in ensemble)')
    ap.add_argument('--all-locations', action='store_true',
                    help='Fetch ensemble for all spots, cities, and harbors')
    ap.add_argument('--output', default='ensemble_keelung.json',
                    help='Output JSON path (default: ensemble_keelung.json)')
    args = ap.parse_args()
    setup_logging()

    # Load ECMWF records for Keelung
    ecmwf_recs = None
    if args.ecmwf_json:
        try:
            ecmwf_data = json.loads(Path(args.ecmwf_json).read_text())
            ecmwf_recs = ecmwf_data.get("records", [])
            if ecmwf_recs:
                log.info("  ECMWF IFS: %d records (from file)", len(ecmwf_recs))
        except (FileNotFoundError, json.JSONDecodeError) as e:
            log.warning("Could not load ECMWF JSON: %s", e)

    # Fetch Keelung ensemble (with full records for chart display)
    output = _fetch_ensemble_for_point(KEELUNG_LAT, KEELUNG_LON, "keelung", ecmwf_recs)
    if output is None:
        log.error("No ensemble models available for Keelung")
        sys.exit(1)

    for mk, mdata in output.get("models", {}).items():
        rc = len(mdata.get("records", []))
        log.info("  %s: %d records", mk, rc)
    log.info("Ensemble spread: %s", output.get("spread", {}))

    # Fetch ensemble for all locations (spots, cities, harbors)
    if args.all_locations:
        non_keelung = [s for s in SPOT_COORDS if s["id"] != "keelung"]
        log.info("Fetching ensemble for %d additional locations…", len(non_keelung))

        results = run_parallel(
            _fetch_location, non_keelung,
            max_workers=4, max_fail_pct=75, label="ensemble-locations",
        )

        locations = {"keelung": {"models": {
            mk: {"meta": md["meta"], "record_count": len(md.get("records", []))}
            for mk, md in output["models"].items()
        }, "spread": output["spread"]}}

        for loc_dict, (loc_id, loc_result) in results:
            if loc_result:
                locations[loc_id] = loc_result
                log.info("  %s: %s", loc_id,
                         {k: v.get("record_count", 0)
                          for k, v in loc_result["models"].items()})
            else:
                log.warning("  %s: no data", loc_id)

        output["locations"] = locations
        log.info("Fetched ensemble for %d/%d locations",
                 sum(1 for v in locations.values() if v), len(SPOT_COORDS))

    Path(args.output).write_text(json.dumps(output, indent=2))
    log.info("Wrote %s", args.output)


if __name__ == "__main__":
    main()
