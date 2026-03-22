#!/usr/bin/env python3
"""
wave_fetch.py
=============
Fetch wave forecasts for the Keelung point.

Source: ECMWF WAM via the Open-Meteo *marine* API (no key required).

Outputs wave_keelung.json, which wrf_analyze.py ingests via --wave-json to
render a wave-forecast table in the HTML output.

Note on CWA wave data
---------------------
  CWA does NOT publish a wave model on their public S3 bucket.  The models
  available at cwaopendata.s3.ap-northeast-1.amazonaws.com/Model/ are:

    M-A0060  Global atmospheric (0.25°, GRIB2)
    M-A0061  Regional 15 km WRF (GRIB2)
    M-A0064  Regional  3 km WRF (GRIB2)   ← main forecast model
    M-B0071  OCM — 3-D ocean *current* model (NetCDF, not waves)

  M-B0071 ("三維海流作業化模式") carries currents and SSH — not wave height,
  period, or direction.  ECMWF WAM from Open-Meteo is therefore the only
  freely available wave source for this pipeline.

  The --cwa-wave-model flag is retained in case CWA publishes a wave product
  in the future (e.g. SWAN output).

Usage
-----
  python wave_fetch.py [--output wave_keelung.json]
"""

import argparse
import json
import logging
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from config import KEELUNG_LAT, KEELUNG_LON, deg_to_compass, norm_utc, setup_logging

log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

MARINE_API_URL = "https://marine-api.open-meteo.com/v1/marine"
CWA_S3_BASE    = "https://cwaopendata.s3.ap-northeast-1.amazonaws.com/Model"

# ── GRIB2 wave variable matching ──────────────────────────────────────────────
# (shortName_variants, typeOfLevel_filter, level_filter, output_key)
# None = match any.  First match per key wins.

WAVE_VARS = [
    # Significant combined wave height
    (['swh', 'SWH', 'htsgw', 'HTSGW'],                None, None, 'wave_height'),
    # Mean / dominant wave period
    (['mwp', 'MWP', 'perpw', 'PERPW', 'pp1d'],        None, None, 'wave_period'),
    # Mean wave direction
    (['mwd', 'MWD', 'dirpw', 'DIRPW'],                 None, None, 'wave_direction'),
    # Wind-sea (local chop) height
    (['shww', 'SHWW', 'wvhgt', 'WVHGT'],               None, None, 'wind_wave_height'),
    # Wind-sea period
    (['mpww', 'MPWW', 'wvper', 'WVPER', 'perpww'],     None, None, 'wind_wave_period'),
    # Wind-sea direction
    (['mcww', 'MCWW', 'dirww', 'DIRWW', 'wvdir'],      None, None, 'wind_wave_direction'),
    # Primary swell height
    (['swh1', 'SWH1', 'swell', 'SWELL', 'shts', 'SHTS'], None, None, 'swell_wave_height'),
    # Primary swell period
    (['swp1', 'SWP1', 'swper', 'SWPER', 'perps'],      None, None, 'swell_wave_period'),
    # Primary swell direction
    (['swd1', 'SWD1', 'swdir', 'SWDIR', 'dirsw'],      None, None, 'swell_wave_direction'),
]

_deg_to_compass = deg_to_compass  # local alias for backward compatibility


# ── ECMWF via Open-Meteo marine API ──────────────────────────────────────────

_FETCH_RETRIES     = 3
_FETCH_RETRY_DELAY = 5   # seconds between attempts

_HOURLY_WAVE_VARS = ",".join([
    "wave_height",
    "wave_direction",
    "wave_period",
    "wind_wave_height",
    "wind_wave_direction",
    "wind_wave_period",
    "swell_wave_height",
    "swell_wave_direction",
    "swell_wave_period",
])


def fetch_ecmwf_wave() -> dict:
    """Fetch ECMWF WAM wave forecast from the Open-Meteo marine API (with retry)."""
    params = {
        "latitude":      KEELUNG_LAT,
        "longitude":     KEELUNG_LON,
        "hourly":        _HOURLY_WAVE_VARS,
        "timezone":      "UTC",
        "forecast_days": 7,   # int, not string
    }
    url = MARINE_API_URL + "?" + urllib.parse.urlencode(params)
    log.info("Fetching ECMWF WAM wave from Open-Meteo marine …")
    last_exc: Exception = RuntimeError("no attempts made")
    for attempt in range(1, _FETCH_RETRIES + 1):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                return json.load(r)
        except urllib.error.URLError as e:
            last_exc = e
            if attempt < _FETCH_RETRIES:
                log.warning("Request failed (%s); retry %d/%d in %ds …",
                            e, attempt, _FETCH_RETRIES, _FETCH_RETRY_DELAY)
                time.sleep(_FETCH_RETRY_DELAY)
    raise RuntimeError(
        f"Open-Meteo marine request failed after {_FETCH_RETRIES} attempts: {last_exc}"
    )


_norm_utc = norm_utc  # local alias for backward compatibility


def process_ecmwf_wave(raw: dict) -> tuple[dict, list[dict]]:
    """Convert Open-Meteo hourly marine response to 6-hourly records."""
    h     = raw.get("hourly", {})
    times = h.get("time", [])
    if not times:
        return {}, []

    def col(k):
        return h.get(k, [])

    def safe(arr, i):
        return arr[i] if arr and 0 <= i < len(arr) else None

    wh  = col("wave_height");         wd  = col("wave_direction")
    wp  = col("wave_period");         wwh = col("wind_wave_height")
    wwd = col("wind_wave_direction"); wwp = col("wind_wave_period")
    swh = col("swell_wave_height");   swd = col("swell_wave_direction")
    swp = col("swell_wave_period")

    records = []
    for i, t in enumerate(times):
        dt = datetime.fromisoformat(
            t if len(t) >= 19 else t + ':00'
        ).replace(tzinfo=timezone.utc)
        if dt.hour % 6 != 0:
            continue

        def r2(v):
            return round(v, 2) if v is not None else None

        records.append({
            "valid_utc":           _norm_utc(t),
            "wave_height":         r2(safe(wh,  i)),
            "wave_direction":      r2(safe(wd,  i)),
            "wave_period":         r2(safe(wp,  i)),
            "wind_wave_height":    r2(safe(wwh, i)),
            "wind_wave_direction": r2(safe(wwd, i)),
            "wind_wave_period":    r2(safe(wwp, i)),
            "swell_wave_height":   r2(safe(swh, i)),
            "swell_wave_direction":r2(safe(swd, i)),
            "swell_wave_period":   r2(safe(swp, i)),
        })

    init_raw = times[0] if times else ""
    meta = {
        "model_id":  "ECMWF-WAM",
        "init_utc":  _norm_utc(init_raw) if init_raw else None,
        "source":    "marine-api.open-meteo.com",
        "latitude":  raw.get("latitude"),
        "longitude": raw.get("longitude"),
    }
    return meta, records


# ── CWA wave model (optional) ─────────────────────────────────────────────────

def probe_cwa_wave_model(model_id: str) -> dict | None:
    """
    Probe the CWA S3 bucket for a wave model by fetching the forecast-hour-000
    JSON sidecar.  Returns run-info dict if found, None otherwise.
    """
    url = f"{CWA_S3_BASE}/{model_id}-000.json"
    log.info("Probing CWA S3 for wave model %s …", model_id)
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            raw = json.load(r)
        info    = raw["cwaopendata"]["dataset"]["datasetInfo"]
        init_dt = datetime.strptime(
            info["InitialTime"], "%Y%m%d%H%M"
        ).replace(tzinfo=timezone.utc)
        log.info("Found %s — init %s", model_id, init_dt.isoformat())
        return {"model_id": model_id, "init_time": init_dt}
    except Exception as e:
        log.warning("%s not found / not parseable: %s", model_id, e)
        return None


def _download_file(url: str, dest: Path) -> None:
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=120) as resp:
        dest.write_bytes(resp.read())


def download_cwa_wave_grib(model_id: str, forecast_hours: list[int], outdir: Path) -> list[Path]:
    """Download CWA wave GRIB2 files for the specified forecast hours."""
    outdir.mkdir(parents=True, exist_ok=True)
    paths = []
    for fh in forecast_hours:
        fname = f"{model_id}-{fh:03d}.grb2"
        url   = f"{CWA_S3_BASE}/{fname}"
        dest  = outdir / fname
        if dest.exists():
            paths.append(dest)
            continue
        log.info("Downloading %s …", fname)
        try:
            _download_file(url, dest)
            paths.append(dest)
            log.info("%s  (%.1f MB)", fname, dest.stat().st_size / 1e6)
        except Exception as e:
            log.warning("Failed to download %s: %s", fname, e)
    return paths


def list_wave_vars(grib_path: Path) -> None:
    """Print all unique (shortName, typeOfLevel, level) in a wave GRIB2 file."""
    try:
        import eccodes as ec
    except ImportError:
        log.error("eccodes not available — install with: pip install eccodes")
        return

    seen = set()
    with open(grib_path, 'rb') as f:
        while True:
            msg = ec.codes_grib_new_from_file(f)
            if msg is None:
                break
            try:
                key = (
                    ec.codes_get(msg, 'shortName'),
                    ec.codes_get(msg, 'typeOfLevel'),
                    ec.codes_get(msg, 'level'),
                )
                if key not in seen:
                    seen.add(key)
                    log.info("  shortName=%-12s  typeOfLevel=%-20s  level=%s", key[0], key[1], key[2])
            except Exception as e:
                log.warning("Skipping GRIB message: %s", e)
            finally:
                ec.codes_release(msg)


def read_wave_point(grib_path: Path, lat: float, lon: float) -> dict:
    """Extract wave variables at the nearest grid point using eccodes."""
    try:
        import eccodes as ec
        import numpy as np
    except ImportError:
        log.warning("eccodes/numpy not available — cannot read CWA wave GRIB2")
        return {}

    # Build shortName → [(tol_filter, level_filter, key)] map
    sn_map: dict = {}
    for snames, tol, lvl, key in WAVE_VARS:
        for sn in snames:
            sn_map.setdefault(sn, []).append((tol, lvl, key))

    raw: dict = {}
    grid_cache: dict = {}

    with open(grib_path, 'rb') as f:
        while True:
            msg = ec.codes_grib_new_from_file(f)
            if msg is None:
                break
            try:
                sname = ec.codes_get(msg, 'shortName')
                if sname not in sn_map:
                    continue

                tol_actual   = ec.codes_get(msg, 'typeOfLevel')
                level_actual = ec.codes_get(msg, 'level')

                matched_key = None
                for (tol_filter, level_filter, key) in sn_map[sname]:
                    if key in raw:
                        continue
                    if tol_filter and tol_actual != tol_filter:
                        continue
                    if level_filter is not None and level_actual != level_filter:
                        continue
                    matched_key = key
                    break

                if not matched_key:
                    continue

                ni = ec.codes_get(msg, 'Ni')
                nj = ec.codes_get(msg, 'Nj')
                cache_key = (ni, nj)

                if cache_key not in grid_cache:
                    lats = ec.codes_get_array(msg, 'latitudes').reshape(nj, ni)
                    lons = ec.codes_get_array(msg, 'longitudes').reshape(nj, ni)
                    dist = np.sqrt((lats - lat) ** 2 + (lons - lon) ** 2)
                    j, i = np.unravel_index(dist.argmin(), dist.shape)
                    grid_cache[cache_key] = (int(j), int(i))

                j, i = grid_cache[cache_key]
                vals = ec.codes_get_values(msg).reshape(nj, ni)
                raw[matched_key] = float(vals[j, i])

            except Exception as e:
                log.warning("Skipping GRIB message in read_wave_point: %s", e)
            finally:
                ec.codes_release(msg)

    return raw


def extract_cwa_wave_forecast(model_id: str, run_info: dict,
                               outdir: Path) -> tuple:
    """Download and parse the full CWA wave forecast at the Keelung point."""
    all_hours = list(range(0, 85, 6))    # 0–84h in 6h steps
    init_time = run_info["init_time"]

    grib_paths = download_cwa_wave_grib(model_id, all_hours, outdir)

    records = []
    for grb in sorted(grib_paths):
        m = re.search(r'-(\d{3})\.grb2$', grb.name)
        if not m:
            continue
        fh         = int(m.group(1))
        valid_time = init_time + timedelta(hours=fh)

        log.info("  CWA wave F%03d …", fh)
        raw = read_wave_point(grb, KEELUNG_LAT, KEELUNG_LON)
        if not raw:
            continue

        rec = {"valid_utc": valid_time.isoformat(), "fh": fh}
        for key in [
            'wave_height', 'wave_direction', 'wave_period',
            'wind_wave_height', 'wind_wave_direction', 'wind_wave_period',
            'swell_wave_height', 'swell_wave_direction', 'swell_wave_period',
        ]:
            v = raw.get(key)
            rec[key] = round(v, 2) if v is not None else None

        records.append(rec)

    records.sort(key=lambda r: r['fh'])
    meta = {
        "model_id": model_id,
        "init_utc": init_time.isoformat(),
        "source":   "cwaopendata.s3.ap-northeast-1.amazonaws.com",
    }
    return meta, records


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="Fetch wave forecasts for Keelung (ECMWF always; CWA optional)."
    )
    ap.add_argument("--output", default="wave_keelung.json",
                    help="Output JSON path (default: wave_keelung.json)")
    ap.add_argument("--cwa-wave-model", default=None, metavar="MODEL_ID",
                    help="CWA S3 wave model ID to try (e.g. M-W0061). "
                         "Omit to skip CWA wave data and use ECMWF only.")
    ap.add_argument("--cwa-outdir", default="wave_downloads",
                    help="Directory for CWA wave GRIB2 downloads (default: wave_downloads)")
    ap.add_argument("--list-wave-vars", action="store_true",
                    help="Diagnostic: list GRIB2 shortNames in the first CWA wave file, then exit")
    args = ap.parse_args()

    # ── Always: ECMWF wave from Open-Meteo marine API ─────────────────────────
    try:
        ecmwf_raw = fetch_ecmwf_wave()
    except RuntimeError as e:
        log.error("%s", e)
        sys.exit(1)
    ecmwf_meta, ecmwf_recs = process_ecmwf_wave(ecmwf_raw)
    log.info("ECMWF WAM: %d 6-hourly records", len(ecmwf_recs))

    result = {
        "ecmwf_wave": {"meta": ecmwf_meta, "records": ecmwf_recs},
        "cwa_wave":   None,
    }

    # ── Optional: CWA wave from S3 GRIB2 ─────────────────────────────────────
    if args.cwa_wave_model:
        run_info = probe_cwa_wave_model(args.cwa_wave_model)
        if run_info:
            outdir = Path(args.cwa_outdir)

            if args.list_wave_vars:
                paths = download_cwa_wave_grib(args.cwa_wave_model, [0], outdir)
                if paths:
                    log.info("Wave GRIB2 variables in %s:", paths[0].name)
                    list_wave_vars(paths[0])
                return

            cwa_meta, cwa_recs = extract_cwa_wave_forecast(
                args.cwa_wave_model, run_info, outdir
            )
            if cwa_recs:
                result["cwa_wave"] = {"meta": cwa_meta, "records": cwa_recs}
                log.info("CWA wave: %d records", len(cwa_recs))
            else:
                log.warning("CWA wave: no records extracted "
                            "(run --list-wave-vars to diagnose GRIB2 variable names)")

    # ── Write output ──────────────────────────────────────────────────────────
    out = Path(args.output)
    out.write_text(json.dumps(result, indent=2))
    log.info("Wave data → %s  (%d ECMWF steps)", out, len(ecmwf_recs))

    gha = os.environ.get("GITHUB_OUTPUT")
    if gha:
        with open(gha, "a") as f:
            f.write(f"wave_json={out.resolve()}\n")


if __name__ == "__main__":
    setup_logging()
    main()
