#!/usr/bin/env python3
"""
wrf_analyze.py
==============
Extract a Keelung point forecast from WRF Keelung-subset GRIB2 files,
compare with the previous run (run-to-run model drift), and emit:

  --output-json  keelung_summary.json   machine-readable, stored on Drive
                                        so the next run can diff against it
  --output-html  forecast.html          HTML fragment for the web app

Usage:
  python wrf_analyze.py \\
      --rundir wrf_downloads/M-A0064_20260309_00UTC \\
      [--prev-json keelung_summary_prev.json] \\
      [--ecmwf-json ecmwf_keelung.json] \\
      [--output-json keelung_summary.json] \\
      [--output-html forecast.html] \\
      [--list-vars]           # diagnostic: list all GRIB2 variables in first file

Requirements: eccodes, numpy  (already installed by the workflow)
"""

import argparse
import html as html_mod
import json
import logging
import math
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime, timedelta, timezone

import numpy as np

from config import KEELUNG_LAT, KEELUNG_LON, COMPASS_NAMES, deg_to_compass, setup_logging, sail_rating, load_json_file, norm_utc
from tide_predict import predict_height
from i18n import T, T_str, bilingual
from html_template import render_page

log = logging.getLogger(__name__)

# ── GRIB2 variable matching ───────────────────────────────────────────────────
# Priority-ordered list of (shortName_variants, typeOfLevel, level, output_key)
# typeOfLevel / level can be None to match any.  First match wins per key.

VARS = [
    # 2 m temperature
    (['2t', 'TMP'],   'heightAboveGround', 2,   'temp_k'),
    # 10 m winds
    (['10u', 'UGRD'], 'heightAboveGround', 10,  'u10'),
    (['10v', 'VGRD'], 'heightAboveGround', 10,  'v10'),
    # Mean sea-level pressure
    (['msl', 'prmsl', 'PRMSL'], None, None,     'mslp_pa'),
    # Precipitation — accumulated total; try surface level first, then any typeOfLevel.
    # WRF GRIB2 may use APCP/tp/PRATE; CWA files may use local table shortNames.
    (['tp', 'apcp', 'APCP', 'prate', 'PRATE', 'NCPCP', 'CPCP'], 'surface', None, 'precip_raw'),
    (['tp', 'apcp', 'APCP', 'prate', 'PRATE', 'NCPCP', 'CPCP'], None,      None, 'precip_raw'),
    # Total cloud cover — any typeOfLevel (e.g. entireAtmosphere, atmosphere)
    (['tcc', 'TCDC', 'tcdc', 'TCC', 'ccl', 'cch', 'ccm'],       None,      None, 'cloud_raw'),
    # Visibility — surface first, then any
    (['vis', 'VIS'],  'surface', None,           'vis_m'),
    (['vis', 'VIS'],  None,      None,           'vis_m'),
    # Wind gust — heightAboveGround first, then surface, then any
    (['gust', 'fg10', 'GUST', '10fg', 'WINDGUST'], 'heightAboveGround', None, 'gust_ms'),
    (['gust', 'fg10', 'GUST', '10fg'],             'surface',           None, 'gust_ms'),
    (['gust', 'fg10', 'GUST', '10fg'],             None,                None, 'gust_ms'),
    # CAPE — surface first, then any
    (['cape', 'CAPE'], 'surface', None,          'cape'),
    (['cape', 'CAPE'], None,      None,          'cape'),
]

# ── paramId fallback ──────────────────────────────────────────────────────────
# Some CWA GRIB2 fields decode as shortName='unknown' because eccodes doesn't
# have their local table entries.  Map paramId → output_key so they can still
# be captured.  Populate this once you've seen the actual paramIds in the
# diagnostic (look for lines like:  shortName=unknown  paramId=<N>).
#
# Common NCEP WRF GRIB2 paramIds to try:
#   61  → total precip (APCP)       → 'precip_raw'
#   71  → total cloud cover (%)     → 'cloud_raw'
#   180 → wind gust (m/s)           → 'gust_ms'
#   59  → CAPE (J/kg)               → 'cape'
#   20  → visibility (m)            → 'vis_m'
#
# Example — once you see "shortName=unknown  paramId=61" in the diagnostic, add:
#   61: 'precip_raw',
PARAMID_VARS: dict[int, str] = {
    # Add entries here after the next diagnostic shows actual paramIds.
    # e.g.:  61: 'precip_raw',
}

# Maps raw key → (display unit, conversion function)
DERIVED = {
    'temp_c':    ('°C',  lambda d: d['temp_k'] - 273.15),
    'wind_kt':   ('kt',  lambda d: math.sqrt(d['u10']**2 + d['v10']**2) * 1.94384),
    'wind_dir':  ('°',   lambda d: (270 - math.degrees(math.atan2(d['v10'], d['u10']))) % 360
                                   if math.sqrt(d['u10']**2 + d['v10']**2) * 1.94384 >= 0.5 else None),
    'mslp_hpa':  ('hPa', lambda d: d['mslp_pa'] / 100),
    'precip_mm': ('mm',  lambda d: d['precip_raw']),   # units normalised in read_point()
    'cloud_pct': ('%',   lambda d: d['cloud_raw'] * 100
                                   if d['cloud_raw'] <= 1.0 else d['cloud_raw']),
    'vis_km':    ('km',  lambda d: d['vis_m'] / 1000),
    'gust_kt':   ('kt',  lambda d: d['gust_ms'] * 1.94384),
    'cape':      ('J/kg',lambda d: d['cape']),
}

# Maps each DERIVED key to the raw keys it needs present before computing
_NEEDED_RAW_KEYS: dict[str, list[str]] = {
    'temp_c':    ['temp_k'],
    'wind_kt':   ['u10', 'v10'],
    'wind_dir':  ['u10', 'v10'],
    'mslp_hpa':  ['mslp_pa'],
    'precip_mm': ['precip_raw'],
    'cloud_pct': ['cloud_raw'],
    'vis_km':    ['vis_m'],
    'gust_kt':   ['gust_ms'],
    'cape':      ['cape'],
}

# Unicode arrows showing the direction the wind is blowing TOWARD
# (opposite of the "from" direction stored in the GRIB2 wind_dir field).
# 0° = FROM North → blows southward → ↓, 90° = FROM East → blows west → ←, etc.
_WIND_ARROWS = ['↓', '↙', '←', '↖', '↑', '↗', '→', '↘']


def _wind_arrow(deg: float) -> str:
    """Return a single Unicode arrow for the direction the wind is blowing toward."""
    return _WIND_ARROWS[round(deg / 45) % 8]


def _fmt(v: float | None, fmt: str = '.1f', unit: str = '') -> str:
    """Format *v* with the given format spec and unit suffix, or return '—'."""
    return f'{v:{fmt}}{unit}' if v is not None else '—'


# ── Grid helpers ──────────────────────────────────────────────────────────────

def nearest_idx(lats2d: np.ndarray, lons2d: np.ndarray,
                lat: float, lon: float) -> tuple[int, int]:
    cos_lat = np.cos(np.radians(lat))
    dist = np.sqrt((lats2d - lat) ** 2 + ((lons2d - lon) * cos_lat) ** 2)
    return np.unravel_index(dist.argmin(), dist.shape)


# ── GRIB2 reading ─────────────────────────────────────────────────────────────

def list_vars(grib_path: Path) -> None:
    """Print all unique (shortName, typeOfLevel, level, paramId) found in a GRIB2 file."""
    import eccodes as ec
    seen = set()
    with open(grib_path, 'rb') as f:
        while True:
            msg = ec.codes_grib_new_from_file(f)
            if msg is None:
                break
            try:
                sn  = ec.codes_get(msg, 'shortName')
                tol = ec.codes_get(msg, 'typeOfLevel')
                lev = ec.codes_get(msg, 'level')
                try:
                    pid = ec.codes_get(msg, 'paramId')
                except (KeyError, ValueError):
                    pid = '?'
                key = (sn, tol, lev)
                if key not in seen:
                    seen.add(key)
                    log.info("  shortName=%-12s  typeOfLevel=%-25s  level=%-6s  paramId=%s", sn, tol, lev, pid)
            except (KeyError, ValueError, TypeError, OSError) as e:
                log.warning("Skipping GRIB message in list_vars: %s", e)
            finally:
                ec.codes_release(msg)


_grid_cache: dict = {}  # module-level cache: (grid_type, ni, nj) → (j, i) index


def read_point(grib_path: Path, lat: float, lon: float) -> dict[str, float]:
    """
    Extract all configured variables at the nearest grid point.
    Returns a dict of raw values keyed by output_key.
    Grid geometry (lat/lon arrays) is cached so it's only computed once per file.
    """
    if not grib_path.exists():
        log.warning("GRIB2 file does not exist: %s", grib_path)
        return {}
    if grib_path.stat().st_size == 0:
        log.warning("GRIB2 file is empty: %s", grib_path)
        return {}
    import eccodes as ec

    # Build shortName → list of (tol_filter, level_filter, key) for fast lookup
    sn_map: dict[str, list] = {}
    for snames, tol, lvl, key in VARS:
        for sn in snames:
            sn_map.setdefault(sn, []).append((tol, lvl, key))

    raw: dict[str, float] = {}

    with open(grib_path, 'rb') as f:
        while True:
            msg = ec.codes_grib_new_from_file(f)
            if msg is None:
                break
            try:
                sname = ec.codes_get(msg, 'shortName')
                if sname not in sn_map:
                    # Fallback: when eccodes can't match the local table it returns
                    # shortName='unknown'.  Try the numeric paramId instead.
                    if sname == 'unknown' and PARAMID_VARS:
                        try:
                            pid = ec.codes_get(msg, 'paramId')
                            if pid in PARAMID_VARS:
                                out_key = PARAMID_VARS[pid]
                                if out_key not in raw:
                                    ni2 = ec.codes_get(msg, 'Ni')
                                    nj2 = ec.codes_get(msg, 'Nj')
                                    if ni2 <= 0 or nj2 <= 0:
                                        raise ValueError(f"Invalid grid dims Ni={ni2}, Nj={nj2}")
                                    gt2 = ec.codes_get(msg, 'gridType')
                                    ck2 = (gt2, ni2, nj2)
                                    if ck2 not in _grid_cache:
                                        lt2 = ec.codes_get_array(msg, 'latitudes')
                                        ln2 = ec.codes_get_array(msg, 'longitudes')
                                        if len(lt2) != ni2 * nj2 or len(ln2) != ni2 * nj2:
                                            raise ValueError(f"Grid array size {len(lt2)} != {ni2}*{nj2}")
                                        _grid_cache[ck2] = nearest_idx(lt2.reshape(nj2, ni2),
                                                                       ln2.reshape(nj2, ni2), lat, lon)
                                    jj, ii = _grid_cache[ck2]
                                    vals2 = ec.codes_get_values(msg)
                                    if len(vals2) != ni2 * nj2:
                                        raise ValueError(f"Values array size {len(vals2)} != {ni2}*{nj2}")
                                    raw[out_key] = float(vals2.reshape(nj2, ni2)[jj, ii])
                        except (KeyError, ValueError, TypeError, OSError) as e:
                            log.warning("paramId fallback failed: %s", e)
                    continue

                tol_actual   = ec.codes_get(msg, 'typeOfLevel')
                level_actual = ec.codes_get(msg, 'level')

                matched_key = None
                for (tol_filter, level_filter, key) in sn_map[sname]:
                    if key in raw:
                        continue  # already captured
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
                if ni <= 0 or nj <= 0:
                    log.warning("Invalid grid dims Ni=%s, Nj=%s — skipping", ni, nj)
                    continue
                grid_type = ec.codes_get(msg, 'gridType')
                cache_key = (grid_type, ni, nj)
                expected_size = ni * nj

                if cache_key not in _grid_cache:
                    lats = ec.codes_get_array(msg, 'latitudes')
                    lons = ec.codes_get_array(msg, 'longitudes')
                    if len(lats) != expected_size or len(lons) != expected_size:
                        log.warning("Grid array size %d != %d*%d — skipping",
                                    len(lats), ni, nj)
                        continue
                    _grid_cache[cache_key] = nearest_idx(lats.reshape(nj, ni),
                                                         lons.reshape(nj, ni), lat, lon)

                j, i = _grid_cache[cache_key]
                vals = ec.codes_get_values(msg)
                if len(vals) != expected_size:
                    log.warning("Values array size %d != %d*%d — skipping",
                                len(vals), ni, nj)
                    continue
                val  = float(vals.reshape(nj, ni)[j, i])

                # For precipitation, read the GRIB2 units key to decide whether
                # to convert from metres to mm.  This is more reliable than the
                # old heuristic (val < 100 → multiply) which misfires on heavy rain.
                if matched_key == 'precip_raw':
                    try:
                        units_str = ec.codes_get(msg, 'units')
                        if units_str == 'm':
                            val *= 1000.0   # WMO standard: m → mm
                        # 'kg m**-2' == mm of liquid water, no conversion needed
                    except (KeyError, ValueError):
                        # Units key unavailable: fall back to a conservative
                        # heuristic — only convert if value looks like metres
                        # (i.e. plausibly < 0.5 m of rain in 6 h).
                        log.warning("GRIB2 units key unavailable for precip; using magnitude heuristic")
                        if 0 < val < 0.5:
                            val *= 1000.0

                raw[matched_key] = val

            except (KeyError, ValueError, TypeError, OSError) as e:
                log.warning("Skipping GRIB message in read_point: %s", e)
            finally:
                ec.codes_release(msg)

    return raw


# ── Forecast extraction ───────────────────────────────────────────────────────

def _parse_init_time(dirname: str) -> datetime | None:
    """Extract init datetime from directory name like M-A0064_20260309_00UTC."""
    m = re.search(r'(\d{8})_(\d{2})UTC', dirname)
    if not m:
        return None
    return datetime.strptime(m.group(1) + m.group(2), '%Y%m%d%H').replace(tzinfo=timezone.utc)


def extract_forecast(rundir: Path) -> tuple[dict, list[dict]]:
    """Return (meta dict, list of record dicts sorted by forecast hour)."""
    grb_files = sorted(rundir.glob('*_keelung*.grb2'))
    if not grb_files:
        return {}, []

    init_time = _parse_init_time(rundir.name)
    model_id  = rundir.name.split('_')[0]

    meta = {
        'model_id': model_id,
        'init_utc': init_time.isoformat() if init_time else None,
        'rundir':   str(rundir.resolve()),
    }

    # Track previous precip value for incremental accumulation detection
    prev_precip_mm = None
    records = []

    for grb in grb_files:
        # Parse forecast hour, e.g. M-A0064-048_keelung50nm.grb2 → 48
        m = re.search(r'-(\d{3})_keelung', grb.name)
        if not m:
            continue
        fh = int(m.group(1))
        valid_time = (init_time + timedelta(hours=fh)) if init_time else None

        log.info("  Extracting F%03d …", fh)
        raw = read_point(grb, KEELUNG_LAT, KEELUNG_LON)
        if not raw:
            log.warning("No variables extracted from %s", grb.name)
            continue

        rec: dict = {
            'fh':        fh,
            'valid_utc': valid_time.isoformat() if valid_time else None,
        }

        for key, (unit, fn) in DERIVED.items():
            try:
                if all(k in raw for k in _NEEDED_RAW_KEYS.get(key, [])):
                    val = fn(raw)
                    rec[key] = round(val, 2) if val is not None else None
                else:
                    rec[key] = None
            except (KeyError, ValueError, ZeroDivisionError):
                rec[key] = None

        # Convert accumulated precip to 6-hourly incremental
        if fh == 0:
            # Analysis hour: no accumulation period yet
            rec['precip_mm_6h'] = 0.0
        elif rec.get('precip_mm') is not None and prev_precip_mm is not None:
            if rec['precip_mm'] >= prev_precip_mm:
                rec['precip_mm_6h'] = round(rec['precip_mm'] - prev_precip_mm, 2)
            else:
                # Model resets accumulation — treat as-is
                rec['precip_mm_6h'] = rec['precip_mm']
        else:
            rec['precip_mm_6h'] = rec.get('precip_mm')

        prev_precip_mm = rec.get('precip_mm')
        records.append(rec)

    records.sort(key=lambda r: r['fh'])
    return meta, records


# ── Wind grid extraction (for frontend particle animation) ────────────────────

def extract_wind_grid(rundir: Path, meta: dict) -> dict | None:
    """
    Extract 2D u10/v10 wind fields from all GRIB2 files in the run directory.
    Returns a dict matching the WindGrid JSON schema for the frontend.
    """
    import eccodes as ec

    grb_files = sorted(rundir.glob('*_keelung*.grb2'))
    if not grb_files:
        return None

    init_time = meta.get('init_utc')
    timesteps = []
    grid_info = None

    for grb in grb_files:
        m = re.search(r'-(\d{3})_keelung', grb.name)
        if not m:
            continue
        fh = int(m.group(1))
        # Only use 6-hourly steps
        if fh % 6 != 0:
            continue

        valid_time = None
        if init_time:
            it = datetime.fromisoformat(init_time)
            valid_time = norm_utc((it + timedelta(hours=fh)).isoformat())

        u_field = None
        v_field = None

        with open(grb, 'rb') as f:
            while True:
                msg = ec.codes_grib_new_from_file(f)
                if msg is None:
                    break
                try:
                    sname = ec.codes_get(msg, 'shortName')
                    tol = ec.codes_get(msg, 'typeOfLevel')
                    lvl = ec.codes_get(msg, 'level')

                    if tol == 'heightAboveGround' and lvl == 10:
                        ni = ec.codes_get(msg, 'Ni')
                        nj = ec.codes_get(msg, 'Nj')
                        if ni <= 0 or nj <= 0:
                            continue

                        vals = ec.codes_get_values(msg)
                        if len(vals) != ni * nj:
                            continue

                        field_2d = vals.reshape(nj, ni)

                        if sname in ('10u', 'UGRD'):
                            u_field = field_2d
                        elif sname in ('10v', 'VGRD'):
                            v_field = field_2d

                        # Capture grid geometry once
                        if grid_info is None:
                            lats = ec.codes_get_array(msg, 'latitudes').reshape(nj, ni)
                            lons = ec.codes_get_array(msg, 'longitudes').reshape(nj, ni)
                            grid_info = {
                                'nx': ni, 'ny': nj,
                                'lat_min': float(lats.min()),
                                'lat_max': float(lats.max()),
                                'lon_min': float(lons.min()),
                                'lon_max': float(lons.max()),
                            }

                except (KeyError, ValueError, TypeError, OSError):
                    pass
                finally:
                    ec.codes_release(msg)

        if u_field is not None and v_field is not None:
            # Subsample to reduce JSON size — take every Nth point
            step = max(1, min(u_field.shape[0], u_field.shape[1]) // 50)
            u_sub = u_field[::step, ::step]
            v_sub = v_field[::step, ::step]

            timesteps.append({
                'valid_utc': valid_time or '',
                'u': [[round(float(x), 2) for x in row] for row in u_sub],
                'v': [[round(float(x), 2) for x in row] for row in v_sub],
            })

    if not timesteps or not grid_info:
        return None

    # Update grid dims to match subsampled size
    ny_out = len(timesteps[0]['u'])
    nx_out = len(timesteps[0]['u'][0]) if ny_out > 0 else 0

    return {
        'model': 'WRF-3km',
        'bounds': {
            'lat_min': grid_info['lat_min'],
            'lat_max': grid_info['lat_max'],
            'lon_min': grid_info['lon_min'],
            'lon_max': grid_info['lon_max'],
        },
        'grid': {'nx': nx_out, 'ny': ny_out},
        'timesteps': timesteps,
    }


# ── HTML rendering ────────────────────────────────────────────────────────────

def _temp_bg(t: float | None) -> str:
    if t is None:  return '#1e293b'
    if t < 10:     return '#1a3654'
    if t < 18:     return '#1a3328'
    if t < 24:     return '#3d3a00'
    if t < 29:     return '#3d2e00'
    return '#3d1515'

def _beaufort(kt: float | None) -> int:
    """Return Beaufort force number for a wind speed in knots."""
    if kt is None: return 0
    if kt < 1:  return 0
    if kt < 4:  return 1
    if kt < 7:  return 2
    if kt < 11: return 3
    if kt < 17: return 4
    if kt < 22: return 5
    if kt < 28: return 6
    if kt < 34: return 7
    if kt < 41: return 8
    if kt < 48: return 9
    if kt < 56: return 10
    if kt < 64: return 11
    return 12

def _wind_bg(w: float | None) -> str:
    if w is None:  return '#1e293b'
    if w < 11:     return '#0d2d1a'   # B1-3  gentle/light breeze (comfortable sailing)
    if w < 17:     return '#1a3328'   # B4    moderate breeze
    if w < 22:     return '#3d3a00'   # B5    fresh breeze (start reefing)
    if w < 28:     return '#3d2e00'   # B6    strong breeze (reef in)
    if w < 34:     return '#3d2000'   # B7    near-gale (consider harbour)
    return '#3d1515'                   # B8+   gale or worse (danger)

def _precip_bg(p: float | None) -> str:
    if p is None or p < 0.1: return '#1e293b'
    if p < 2:    return '#0d2d1a'
    if p < 10:   return '#1a3654'
    if p < 25:   return '#1a2f5a'
    return '#1a2060'

def _cape_bg(c: float | None) -> str:
    if c is None:  return '#1e293b'
    if c < 100:    return '#0d2d1a'   # stable
    if c < 500:    return '#3d3a00'   # slightly unstable
    if c < 1500:   return '#3d2e00'   # moderately unstable
    return '#3d1515'                   # very unstable (thunderstorm risk)

def _wave_height_bg(h: float | None) -> str:
    """Background colour for significant wave height (metres)."""
    if h is None: return '#1e293b'
    if h < 0.3:   return '#0d2d1a'   # glassy / rippled
    if h < 1.0:   return '#3d3a00'   # slight
    if h < 2.0:   return '#3d2e00'   # moderate
    if h < 3.5:   return '#3d1515'   # rough / very rough
    return '#4a1010'                  # high / dangerous

def _wave_period_bg(p: float | None) -> str:
    """Background colour for wave period (seconds)."""
    if p is None: return '#1e293b'
    if p < 4:     return '#1e293b'   # very short (local chop)
    if p < 8:     return '#3d3a00'   # moderate wind sea
    if p < 12:    return '#0d2d1a'   # longer period swell
    return '#1a3654'                  # long-period ocean swell

def _delta_span(curr: float | None, prev: float | None,
                fmt: str = '.1f', unit: str = '', positive_bad: bool = False) -> str:
    """Return a small colored delta span, or '' if insignificant."""
    if curr is None or prev is None:
        return ''
    d = curr - prev
    if abs(d) < 0.05:
        return ''
    color = '#c00' if (d > 0) == positive_bad else '#060'
    sign  = '+' if d > 0 else ''
    return f'<span style="color:{color};font-size:0.8em"> ({sign}{d:{fmt}}{unit})</span>'


# NOTE: render_html(), render_comparison_html(), render_wave_html(), and
# _render_cwa_ecmwf_wave_comparison() were removed — superseded by
# render_unified_html() which produces a single consolidated table.
# If you need to restore them, check git history.


# ── WRF vs ECMWF comparison ───────────────────────────────────────────────────

def _delta_cell(d: float | None, thresh: float, positive_bad: bool = False) -> str:
    """Return a <td> element color-coded by disagreement magnitude."""
    if d is None:
        return '<td style="padding:4px 5px;text-align:center;color:#475569">—</td>'
    abs_d = abs(d)
    if abs_d < thresh * 0.5:
        bg, color = '#0d2d1a', '#68d391'   # green  – good agreement
    elif abs_d < thresh:
        bg, color = '#3d2e00', '#fbd38d'   # yellow – moderate
    else:
        bg, color = '#3d1515', '#fc8181'   # red    – large disagreement
    sign = '+' if d > 0 else ''
    return (f'<td style="padding:4px 5px;text-align:center;background:{bg};'
            f'color:{color};font-weight:500">{sign}{d}</td>')


def _wave_dir_str(deg: float | None) -> str:
    return deg_to_compass(deg)


_TD = 'padding:3px 5px;text-align:center'
_EMPTY_TD = f'  <td style="{_TD};color:#475569">—</td>\n'


def _td(content: str, bg: str = '', extra: str = '') -> str:
    """Generate a styled <td> for the unified forecast table."""
    bg_s = f';background:{bg}' if bg else ''
    ex_s = f';{extra}' if extra else ''
    return f'  <td style="{_TD}{bg_s}{ex_s}">{content}</td>\n'


def _row_alerts(wind: float | None, gust: float | None,
                hs: float | None, rain: float | None) -> tuple[str, str]:
    """Return (alert_html, alert_bg) for a forecast row."""
    alerts = []
    if gust is not None and gust >= 34:
        alerts.append('<span style="color:#fc8181;font-weight:700">Gale⚠</span>')
    elif gust is not None and gust >= 28:
        alerts.append('<span style="color:#fbd38d">g28+</span>')
    if wind is not None and wind >= 34:
        alerts.append('<span style="color:#fc8181;font-weight:700">B8+</span>')
    elif wind is not None and wind >= 28:
        alerts.append('<span style="color:#fbd38d">B7</span>')
    elif wind is not None and wind >= 22:
        alerts.append('<span style="color:#fbd38d">B6</span>')
    if hs is not None and hs >= 2.5:
        alerts.append('<span style="color:#93c5fd">🌊⚠</span>')
    elif hs is not None and hs >= 1.5:
        alerts.append('<span style="color:#93c5fd">🌊</span>')
    if rain is not None and rain >= 10:
        alerts.append('<span style="color:#93c5fd">🌧</span>')
    alert_html = '&nbsp;'.join(alerts) if alerts else ''
    alert_bg = ('#2d1515' if any('⚠' in a or 'Gale' in a for a in alerts)
                else '#2d2200' if alerts else '')
    return alert_html, alert_bg



# ── Colorblind-safe helpers ────────────────────────────────────────────────────

def _wind_cb(kt: float | None) -> str:
    """Colorblind-safe CSS class for wind speed."""
    if kt is None: return ''
    if kt < 17:   return 'cb-ok'
    if kt < 28:   return 'cb-warn'
    return 'cb-danger'


def _wave_cb(hs: float | None) -> str:
    """Colorblind-safe CSS class for wave height."""
    if hs is None: return ''
    if hs < 1.0:   return 'cb-ok'
    if hs < 2.5:   return 'cb-warn'
    return 'cb-danger'


def _spread_class(spread: float | None, low_thresh: float, high_thresh: float) -> str:
    """Return CSS class for ensemble spread magnitude."""
    if spread is None: return ''
    if spread < low_thresh:  return 'spread-low'
    if spread < high_thresh: return 'spread-medium'
    return 'spread-high'


def _spread_html(ens_rec: dict | None, var: str, low: float, high: float) -> str:
    """Return inline HTML for ensemble spread indicator, or '' if not available."""
    if not ens_rec:
        return ''
    stats = ens_rec.get(var)
    if not stats or stats.get('n', 0) < 2:
        return ''
    spread = stats.get('spread')
    if spread is None:
        return ''
    cls = _spread_class(spread, low, high)
    return f'<span class="spread-indicator {cls}" title="Model spread: ±{spread:.0f}"> ±{spread:.0f}</span>'


# ── Daily summary cards ───────────────────────────────────────────────────────

def _sail_rating(max_wind: float | None, max_gust: float | None,
                 max_hs: float | None, total_rain: float) -> tuple[str, str]:
    """Return (label, bg_color) — go/marginal/no-go sailing suitability."""
    r = sail_rating(max_wind, max_gust, max_hs, total_rain)
    # Bilingual label: emoji + dual-language text
    bi_label = f'{r["emoji"]} {bilingual(r["label_en"], r["label_zh"])}'
    return bi_label, r['bg']


def _condition_emoji(max_wind: float | None, total_rain: float | None, max_cape: float | None,
                     max_hs: float | None, max_gust: float | None = None) -> str:
    if max_hs is not None and max_hs >= 3.5:
        return '🌊'
    if max_cape is not None and max_cape >= 500:
        return '⛈️'
    if total_rain is not None and total_rain >= 15:
        return '🌧️'
    if total_rain is not None and total_rain >= 3:
        return '🌦️'
    if max_gust is not None and max_gust >= 34:
        return '💨'
    if max_wind is not None and max_wind >= 25:
        return '💨'
    if max_wind is not None and max_wind >= 15:
        return '🌬️'
    return '🌤️'


def _tide_sparkline_svg(cst_date: str, tide_data: dict | None,
                        is_today: bool = False) -> str:
    """Generate an inline SVG sparkline for one day's tide curve.

    Args:
        cst_date: Date string in 'YYYY-MM-DD' format (CST).
        tide_data: Tide JSON with 'extrema' list.
        is_today: If True, draw a 'now' marker line.

    Returns:
        HTML string with inline <svg>, or '' if no tide data.
    """
    if not tide_data or not tide_data.get('extrema'):
        return ''

    # Sample 25 points (hourly 00:00-24:00 CST) by calling predict_height()
    try:
        base_cst = datetime.strptime(cst_date, '%Y-%m-%d')
    except (ValueError, TypeError):
        return ''

    points: list[tuple[float, float]] = []  # (hour_fraction, height_m)
    for h in range(25):
        cst_dt = base_cst.replace(tzinfo=timezone(timedelta(hours=8))) + timedelta(hours=h)
        utc_dt = cst_dt.astimezone(timezone.utc)
        height = predict_height(utc_dt)
        points.append((float(h), height))

    if not points:
        return ''

    # Get extrema for this day
    day_extrema = [ex for ex in tide_data.get('extrema', [])
                   if ex.get('cst', '').startswith(cst_date)]

    # Scale to SVG viewBox (0-120 x 0-32, with 4px padding top/bottom)
    heights = [p[1] for p in points]
    h_min, h_max = min(heights), max(heights)
    h_range = h_max - h_min or 0.1  # avoid division by zero

    def sx(hour: float) -> float:
        return hour / 24.0 * 120.0

    def sy(height: float) -> float:
        # Invert Y (SVG y=0 is top), with 4px padding
        return 28.0 - ((height - h_min) / h_range) * 24.0 + 4.0

    # Build polyline points string
    poly_pts = ' '.join(f'{sx(h):.1f},{sy(ht):.1f}' for h, ht in points)

    # Build SVG
    svg = (
        '<svg class="tide-sparkline" viewBox="0 0 120 32" '
        'width="100%" height="32" preserveAspectRatio="none" '
        'xmlns="http://www.w3.org/2000/svg">'
        # Filled area under curve
        f'<polyline points="0,{sy(points[0][1]):.1f} {poly_pts} 120,{sy(points[-1][1]):.1f}" '
        'fill="none" stroke="#7db8f0" stroke-width="1.5" stroke-linejoin="round"/>'
        f'<polygon points="0,{sy(points[0][1]):.1f} {poly_pts} 120,{sy(points[-1][1]):.1f} 120,32 0,32" '
        'fill="#7db8f0" fill-opacity="0.15"/>'
    )

    # Extrema dots
    for ex in day_extrema:
        try:
            cst_str = ex.get('cst', '')
            # Parse "YYYY-MM-DD HH:MM CST" or just use the hour
            parts = cst_str.split()
            time_parts = parts[1].split(':') if len(parts) >= 2 else []
            ex_hour = int(time_parts[0]) + int(time_parts[1]) / 60.0
            ex_height = ex.get('height_m', 0)
            dot_color = '#93c5fd' if ex.get('type') == 'high' else '#64748b'
            svg += (
                f'<circle cx="{sx(ex_hour):.1f}" cy="{sy(ex_height):.1f}" '
                f'r="2.5" fill="{dot_color}" stroke="#0f172a" stroke-width="0.5"/>'
            )
        except (ValueError, IndexError):
            continue

    # "Now" marker for today
    if is_today:
        now_cst = datetime.now(timezone(timedelta(hours=8)))
        now_hour = now_cst.hour + now_cst.minute / 60.0
        now_x = sx(now_hour)
        svg += (
            f'<line x1="{now_x:.1f}" y1="0" x2="{now_x:.1f}" y2="32" '
            'stroke="#fbd38d" stroke-width="1" stroke-dasharray="2,2" opacity="0.7"/>'
        )

    svg += '</svg>'
    return f'<div class="tide-sparkline-wrap">{svg}</div>\n'


def _daily_summary_html(
    wrf_by_valid: dict,
    ec_by_valid:  dict,
    wave_by_valid: dict,
    all_valids: list,
    tide_data: dict | None = None,
    surf_planner: dict | None = None,
) -> str:
    """
    Unified day cards: sailing + surf + weather + recommendation per day.
    Uses WRF data where available; falls back to ECMWF for extended days.
    Surf planner data (best spot + recommendation) comes from surf_planner JSON.
    """
    from collections import defaultdict

    # Group all valid times by CST date string  (e.g. "2026-03-11")
    day_buckets: dict[str, list] = defaultdict(list)
    for vt in all_valids:
        try:
            cst_date = (datetime.fromisoformat(vt) + timedelta(hours=8)).strftime('%Y-%m-%d')
            day_buckets[cst_date].append(vt)
        except (ValueError, TypeError):
            pass

    if not day_buckets:
        return ''

    cards_html = '<div class="daily-cards">\n'

    for cst_date in sorted(day_buckets):
        valids = day_buckets[cst_date]

        # Gather per-6h values for this day
        temps, winds, wind_dirs, gusts, rains, capes, wave_hs = [], [], [], [], [], [], []
        source_tags = set()

        for vt in valids:
            wrf = wrf_by_valid.get(vt)
            ec  = ec_by_valid.get(vt)
            wav = wave_by_valid.get(vt)

            if wrf: source_tags.add('WRF')
            if ec and not wrf: source_tags.add('EC')

            # Per-field: WRF preferred, ECMWF fallback for missing fields
            def _pick(key):
                w = wrf.get(key) if wrf else None
                e = ec.get(key)  if ec  else None
                return w if w is not None else e

            t_v  = _pick('temp_c')
            w_v  = _pick('wind_kt')
            wd_v = _pick('wind_dir')
            g_v  = _pick('gust_kt')
            r_v  = _pick('precip_mm_6h')
            c_v  = _pick('cape')

            if t_v  is not None: temps.append(t_v)
            if w_v  is not None:
                winds.append(w_v)
                if wd_v is not None: wind_dirs.append((w_v, wd_v))
            if g_v  is not None: gusts.append(g_v)
            if r_v  is not None: rains.append(r_v)
            if c_v  is not None: capes.append(c_v)

            if wav and wav.get('wave_height') is not None:
                wave_hs.append(wav['wave_height'])

        # Summarise
        t_min    = min(temps)  if temps  else None
        t_max    = max(temps)  if temps  else None
        max_wind = max(winds)  if winds  else None
        max_gust = max(gusts)  if gusts  else None
        max_cape = max(capes)  if capes  else None
        total_r  = sum(rains)
        max_hs_v = max(wave_hs) if wave_hs else None

        # Wind direction and arrow at peak wind step
        peak_dir_s  = ''
        peak_arrow  = ''
        peak_deg_v  = None
        if wind_dirs:
            _, peak_deg_v = max(wind_dirs, key=lambda x: x[0])
            peak_dir_s   = f' {deg_to_compass(peak_deg_v)}'
            peak_arrow   = _wind_arrow(peak_deg_v)

        cond_icon = _condition_emoji(max_wind, total_r, max_cape, max_hs_v, max_gust)
        sail_label, sail_bg = _sail_rating(max_wind, max_gust, max_hs_v, total_r)

        # Format day label
        try:
            day_label = datetime.strptime(cst_date, '%Y-%m-%d').strftime('%a %-m/%-d')
        except (ValueError, TypeError):
            day_label = cst_date

        # Source badge colours
        src_label = '+'.join(sorted(source_tags, reverse=True))   # WRF+EC or WRF or EC
        src_bg    = '#1a365d' if 'WRF' in source_tags else '#276749'
        src_color = '#fff'

        # Temp background for the card accent
        card_border = _temp_bg(t_max) if t_max is not None else '#e2e8f0'

        temp_str = f'{t_min:.0f}–{t_max:.0f}°C' if t_min is not None and t_max is not None else '—'

        # Wind: Beaufort force + direction arrow + compass; gust shown when notably higher
        if max_wind is not None:
            bf_day    = _beaufort(max_wind)
            arrow_bit = f' {peak_arrow}' if peak_arrow else ''
            gust_bit  = (f' g{max_gust:.0f}' if max_gust is not None
                         and max_gust >= max_wind * 1.15 and max_gust >= max_wind + 3
                         else '')
            wind_str  = f'{max_wind:.0f}kt B{bf_day}{arrow_bit}{peak_dir_s}{gust_bit}'
        else:
            wind_str  = '—'

        rain_str = f'{total_r:.0f}mm' if total_r > 0 else T('dry')

        # Wave: peak Hs + dominant period from the day's wave records
        if max_hs_v is not None:
            # find peak-period at the step with max Hs
            day_wav_recs = [wave_by_valid.get(vt) for vt in valids if wave_by_valid.get(vt)]
            peak_tp = None
            if day_wav_recs:
                best = max(day_wav_recs, key=lambda r: r.get('wave_height') or 0)
                peak_tp = best.get('wave_period')
            tp_str = f' T{peak_tp:.0f}s' if peak_tp is not None else ''
            wave_str = f'Hs {max_hs_v:.1f}m{tp_str}'
        else:
            wave_str = ''

        # CAPE indicator: ⚡ badge when convective potential is elevated
        cape_badge = ''
        if max_cape is not None and max_cape >= 500:
            cape_level = '⚡⚡' if max_cape >= 1500 else '⚡'
            cape_badge = (
                f'  <div style="color:#fbd38d;font-size:0.85em">'
                f'{cape_level} CAPE {max_cape:.0f} J/kg</div>\n'
            )

        # Tide info for this day
        tide_str = ''
        today_cst = datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d')
        tide_svg = _tide_sparkline_svg(cst_date, tide_data,
                                       is_today=(cst_date == today_cst))
        if tide_data:
            day_tides = [ex for ex in tide_data.get('extrema', [])
                         if ex.get('cst', '').startswith(cst_date)]
            if day_tides:
                parts = []
                for ex in day_tides[:4]:  # max 4 extrema per day
                    arrow = '▲' if ex.get('type') == 'high' else '▼'
                    t_str = html_mod.escape(ex.get('cst', '')[-9:-4])  # "HH:MM"
                    ht = ex.get('height_m', 0)
                    parts.append(f'{arrow}{t_str} {ht:.1f}m')
                tide_str = ' '.join(parts)

        # Surf planner data for this day
        surf_html = ''
        rec_html = ''
        sp_days = (surf_planner or {}).get('days', {})
        sp_day = sp_days.get(cst_date, {})
        if sp_day:
            bs = sp_day.get('best_surf', {})
            if bs.get('spot') and bs.get('emoji') and bs['emoji'] != '😴':
                surf_html = (
                    f'  <div class="surf-pick">'
                    f'<span class="rating-pill" style="background:{bs.get("bg","#1a2236")};color:{bs.get("col","#475569")}">'
                    f'{bs["emoji"]} {bs["spot"]}</span></div>\n'
                )
            elif bs.get('emoji') == '😴':
                surf_html = f'  <div class="surf-pick"><span class="rating-pill rating-flat">😴 {T("flat")}</span></div>\n'
            rec = sp_day.get('recommendation', {})
            if rec.get('text'):
                rec_html = (
                    f'  <div class="recommendation" style="background:{rec.get("bg","#1e293b")}">'
                    f'{rec["text"]}</div>\n'
                )

        cards_html += (
            f'<div class="daily-card unified-day-card" style="border-top:3px solid {card_border}">\n'
            f'  <div class="day-label">'
            f'{day_label}<span class="day-icon">{cond_icon}</span></div>\n'
            f'  <div class="sail-badge" style="background:{sail_bg}">'
            f'⛵ {sail_label}</div>\n'
            + surf_html
            + (f'  <div class="metric">🌊 {wave_str}</div>\n' if wave_str else '')
            + f'  <div class="metric">💨 {wind_str}</div>\n'
            f'  <div class="metric">🌧️ {rain_str}</div>\n'
            f'  <div class="metric">🌡️ {temp_str}</div>\n'
            + (f'  {tide_svg}' if tide_svg else '')
            + (f'  <div class="metric" style="color:#7db8f0;font-size:0.85em">🌙 {tide_str}</div>\n' if tide_str else '')
            + cape_badge
            + rec_html
            + f'  <div style="margin-top:4px">'
            f'<span class="badge" style="background:{src_bg};color:{src_color}">{src_label}</span></div>\n'
            f'</div>\n'
        )

    cards_html += '</div>\n'
    return cards_html


# ── Unified table (all sources, JS-togglable column groups) ──────────────────

def _render_summary_html(
    meta: dict,
    records: list,
    prev_records: list,
    ecmwf_records: list,
    wave_data: dict | None,
    tide_data: dict | None = None,
    surf_planner: dict | None = None,
    cwa_obs: dict | None = None,
) -> str:
    """
    Compact summary section: daily cards, alerts, model shift note.
    Used as the header section of render_unified_html().
    """
    # ── Lookups ───────────────────────────────────────────────────────────────
    init_str = ''
    if meta.get('init_utc'):
        init_str = datetime.fromisoformat(meta['init_utc']).strftime('%Y-%m-%d %H:%M UTC')

    prev_by_valid = {r['valid_utc']: r for r in (prev_records or []) if r.get('valid_utc')}
    has_prev = bool(prev_by_valid)

    ec_by_valid = {r['valid_utc']: r for r in (ecmwf_records or []) if r.get('valid_utc')}
    has_ec = bool(ec_by_valid)

    ecmwf_wave  = (wave_data or {}).get('ecmwf_wave', {})
    wave_recs   = ecmwf_wave.get('records', [])
    wave_meta   = ecmwf_wave.get('meta', {})
    wave_by_valid = {r['valid_utc']: r for r in wave_recs if r.get('valid_utc')}
    has_wave = bool(wave_by_valid)

    wrf_by_valid = {r['valid_utc']: r for r in records if r.get('valid_utc')}

    # Union of all valid times, sorted chronologically
    all_valids = sorted(set(wrf_by_valid) | set(ec_by_valid) | set(wave_by_valid))

    # ── Subtitle bits ─────────────────────────────────────────────────────────
    wave_init_str = ''
    if wave_meta.get('init_utc'):
        try:
            wave_init_str = (' &nbsp;·&nbsp; Wave: '
                + datetime.fromisoformat(wave_meta['init_utc']).strftime('%m/%d %H:%M UTC'))
        except (KeyError, ValueError, TypeError):
            pass

    # ── Helper: add CSS class to a _delta_cell() output string ───────────────
    def _dc(d, thresh, positive_bad=False, cls='grp-delta'):
        return _delta_cell(d, thresh, positive_bad).replace('<td ', f'<td class="{cls}" ', 1)

    # ═════════════════════════════════════════════════════════════════════════
    # HTML construction starts here
    # ═════════════════════════════════════════════════════════════════════════
    html = (
        '<section id="week" class="section">\n'
        '<div class="card-glass">\n'
        '<h2 class="section-title">\n'
        f'  <span role="img" aria-label="Globe">🌏</span> {T("this_week")}\n'
        f'  <span style="font-weight:normal;font-size:0.75em;color:#94a3b8">'
        f'&nbsp;{KEELUNG_LAT}°N {KEELUNG_LON}°E</span>\n'
        '</h2>\n'
        f'<p class="section-subtitle">'
        f'{html_mod.escape(meta.get("model_id","?"))} · WRF Init: {init_str}{wave_init_str}'
        f'{"&nbsp;·&nbsp; <i>" + T("delta_note") + "</i>" if has_prev else ""}'
        '</p>\n\n'
    )

    # ── CWA warning banner (shown only when active warnings exist) ────────────
    if cwa_obs and cwa_obs.get('warnings'):
        warnings_list = cwa_obs['warnings']
        html += (
            '<div class="warning-banner" style="background:#7f1d1d;border:2px solid #ef4444;'
            'border-radius:8px;padding:12px 16px;margin-bottom:16px">\n'
            f'  <h3 style="color:#fca5a5;margin:0 0 6px;font-size:14px">'
            f'{bilingual("Active Weather Warnings", "氣象警特報")}</h3>\n'
        )
        for w in warnings_list:
            w_type = html_mod.escape(str(w.get('type', '')))
            w_desc = html_mod.escape(str(w.get('description', '')))
            if len(w_desc) > 200:
                w_desc = w_desc[:200] + '…'
            w_severity = html_mod.escape(str(w.get('severity', '')))
            sev_color = '#fca5a5' if w_severity.lower() in ('warning', 'severe') else '#fde68a'
            html += (
                f'  <p style="margin:4px 0;font-size:13px;color:{sev_color}">'
                f'<b>{w_type}</b>'
                f'{" — " + w_desc if w_desc else ""}'
                f'</p>\n'
            )
        html += '</div>\n\n'

    # ── Current conditions card (CWA live obs) ────────────────────────────────
    if cwa_obs and (cwa_obs.get('station') or cwa_obs.get('buoy')):
        station = cwa_obs.get('station') or {}
        buoy = cwa_obs.get('buoy') or {}
        html += (
            '<div class="current-conditions" style="background:#1e293b;border-radius:8px;'
            'padding:12px 16px;margin-bottom:16px">\n'
            f'  <h3 style="color:#93c5fd;margin:0 0 8px;font-size:14px">'
            f'{bilingual("Current Conditions (CWA Live)", "即時觀測（中央氣象署）")}</h3>\n'
            '  <div style="display:flex;flex-wrap:wrap;gap:16px;font-size:13px;color:#cbd5e1">\n'
        )
        # Station observations
        if station:
            obs_time = station.get('obs_time', '')
            # Format obs time for display (show CST)
            obs_display = ''
            if obs_time:
                try:
                    dt = datetime.fromisoformat(obs_time)
                    cst = dt + timedelta(hours=8) if dt.tzinfo is None or dt.utcoffset() == timedelta(0) else dt.astimezone(timezone(timedelta(hours=8)))
                    obs_display = cst.strftime('%H:%M CST')
                except (ValueError, TypeError):
                    obs_display = obs_time
            items = []
            if station.get('temp_c') is not None:
                items.append(f'{bilingual("Temp", "氣溫")} {station["temp_c"]:.1f}°C')
            if station.get('wind_kt') is not None:
                wind_dir_str = ''
                if station.get('wind_dir') is not None:
                    wind_dir_str = deg_to_compass(station['wind_dir']) + ' '
                items.append(f'{bilingual("Wind", "風")} {wind_dir_str}{station["wind_kt"]:.0f}kt')
            if station.get('gust_kt') is not None and station['gust_kt'] > 0:
                items.append(f'{bilingual("Gust", "陣風")} {station["gust_kt"]:.0f}kt')
            if station.get('pressure_hpa') is not None:
                items.append(f'{bilingual("Pressure", "氣壓")} {station["pressure_hpa"]:.1f}hPa')
            if station.get('humidity_pct') is not None:
                items.append(f'{bilingual("Humidity", "濕度")} {station["humidity_pct"]:.0f}%')
            if items:
                html += '    <div>'
                html += f'<b>{bilingual("Station", "測站")}</b>'
                if obs_display:
                    html += f' <span style="color:#64748b;font-size:11px">({obs_display})</span>'
                html += '<br>' + ' · '.join(items)
                html += '</div>\n'
        # Buoy observations
        if buoy:
            obs_time = buoy.get('obs_time', '')
            obs_display = ''
            if obs_time:
                try:
                    dt = datetime.fromisoformat(obs_time)
                    cst = dt + timedelta(hours=8) if dt.tzinfo is None or dt.utcoffset() == timedelta(0) else dt.astimezone(timezone(timedelta(hours=8)))
                    obs_display = cst.strftime('%H:%M CST')
                except (ValueError, TypeError):
                    obs_display = obs_time
            items = []
            if buoy.get('wave_height_m') is not None:
                items.append(f'{bilingual("Waves", "浪高")} {buoy["wave_height_m"]:.1f}m')
            if buoy.get('wave_period_s') is not None:
                items.append(f'{bilingual("Period", "週期")} {buoy["wave_period_s"]:.0f}s')
            if buoy.get('peak_period_s') is not None:
                items.append(f'{bilingual("Peak", "尖峰週期")} {buoy["peak_period_s"]:.0f}s')
            if buoy.get('wave_dir') is not None:
                items.append(f'{bilingual("Dir", "浪向")} {deg_to_compass(buoy["wave_dir"])}')
            if buoy.get('water_temp_c') is not None:
                items.append(f'{bilingual("Sea", "海溫")} {buoy["water_temp_c"]:.1f}°C')
            if items:
                html += '    <div>'
                html += f'<b>{bilingual("Buoy", "浮標")}</b>'
                if obs_display:
                    html += f' <span style="color:#64748b;font-size:11px">({obs_display})</span>'
                html += '<br>' + ' · '.join(items)
                html += '</div>\n'
        html += '  </div>\n</div>\n\n'

    # ── Alerts (WRF primary; ECMWF fills in gust/rain/CAPE) ──────────────────
    alerts = []
    _wrf = records or []
    _ec  = ecmwf_records or []
    max_wind   = max((r.get('wind_kt')      or 0 for r in _wrf + _ec), default=0)
    max_gust   = max((r.get('gust_kt')      or 0 for r in _wrf + _ec), default=0)
    total_rain = sum(r.get('precip_mm_6h') or 0 for r in (_wrf if _wrf else _ec))
    min_mslp   = min((r.get('mslp_hpa')     or 9999 for r in _wrf + _ec), default=9999)
    max_cape   = max((r.get('cape')         or 0 for r in _wrf + _ec), default=0)
    if max_wind  >= 34: alerts.append(f'⚠️ <b>{T("alert_gale")}</b> — {max_wind:.0f}kt — {T("alert_consider")}')
    elif max_wind >= 28: alerts.append(f'⚠️ {T("alert_near_gale")} — {max_wind:.0f}kt — {T("alert_harbour")}')
    elif max_wind >= 22: alerts.append(f'💨 {T("alert_strong_breeze")} — {max_wind:.0f}kt — {T("alert_reef_in")}')
    if max_gust  >= 34: alerts.append(f'⚠️ <b>{T("alert_gale_gusts")} {max_gust:.0f}kt</b>')
    elif max_gust >= 28: alerts.append(f'💨 {T("alert_near_gale_gusts")} {max_gust:.0f}kt')
    if total_rain >= 50: alerts.append(f'🌧️ <b>{T("alert_heavy_rain")}</b> — {total_rain:.0f}mm total')
    elif total_rain >= 15: alerts.append(f'🌦️ {T("alert_mod_rain")} — {total_rain:.0f}mm total')
    if min_mslp  <= 985: alerts.append(f'🌀 <b>{T("alert_low_mslp")} {min_mslp:.0f}hPa</b> — {T("alert_tropical")}')
    if max_cape  >= 1000: alerts.append(f'⛈️ {T("alert_high_cape")} — CAPE {max_cape:.0f} J/kg — {T("alert_thunderstorm")}')
    if wave_recs:
        max_hs = max((r.get('wave_height') or 0 for r in wave_recs), default=0)
        if max_hs >= 3.5: alerts.append(f'⚠️ <b>{T("alert_dangerous_seas")}</b> — Hs {max_hs:.1f}m peak')
        elif max_hs >= 2.0: alerts.append(f'🌊 {T("alert_rough")} — Hs {max_hs:.1f}m peak')
        elif max_hs >= 1.0: alerts.append(f'🌊 {T("alert_moderate_seas")} — Hs {max_hs:.1f}m')
    if alerts:
        html += ('<div class="alert-box alert-danger">'
                 + '<br>'.join(alerts) + '</div>\n')

    # ── Model shift vs prev run ───────────────────────────────────────────────
    if has_prev and records:
        overlapping = [(r, prev_by_valid[r['valid_utc']]) for r in records
                       if r.get('valid_utc') in prev_by_valid]
        notes = []
        wd = [r.get('wind_kt', 0) - p.get('wind_kt', 0) for r, p in overlapping
              if r.get('wind_kt') is not None and p.get('wind_kt') is not None]
        if wd:
            pk = max(wd, key=abs)
            if abs(pk) >= 3:
                notes.append(f'Peak wind {"+" if pk>0 else ""}{pk:.0f}kt {T("vs_prev_run")}')
        dp_total = sum((r.get('precip_mm_6h') or 0) - (p.get('precip_mm_6h') or 0)
                       for r, p in overlapping)
        if abs(dp_total) >= 2:
            notes.append(f'Total rain {"+" if dp_total>0 else ""}{dp_total:.1f}mm {T("vs_prev_run")}')
        md = [r.get('mslp_hpa', 0) - p.get('mslp_hpa', 0) for r, p in overlapping
              if r.get('mslp_hpa') is not None and p.get('mslp_hpa') is not None]
        if md:
            pk_m = max(md, key=abs)
            if abs(pk_m) >= 1:
                notes.append(f'Max MSLP shift {"+" if pk_m>0 else ""}{pk_m:.1f}hPa {T("vs_prev_run")}')
        if notes:
            html += ('<div class="alert-box alert-warning">'
                     f'🔄 <b>{T("model_shift")}:</b> ' + ' · '.join(notes) + '</div>\n')

    # ── Unified day cards (sailing + surf + weather) ──────────────────────────
    html += _daily_summary_html(wrf_by_valid, ec_by_valid, wave_by_valid, all_valids,
                                tide_data, surf_planner=surf_planner)

    html += '</div>\n'
    return html


def _render_accuracy_badge(accuracy_log: list) -> str:
    """Render a small accuracy badge from the rolling accuracy log.

    Shows 7-day rolling averages for temp, wind, and wave MAE.
    """
    if not accuracy_log:
        return ''
    from datetime import datetime, timedelta, timezone
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    recent = []
    for e in accuracy_log:
        try:
            vt = datetime.fromisoformat(e.get('verified_utc', ''))
            if vt >= cutoff:
                recent.append(e)
        except (ValueError, TypeError):
            pass
    if not recent:
        return ''

    # Average each metric across recent entries
    def avg_metric(entries, key):
        vals = [e.get(key) for e in entries if e.get(key) is not None]
        return round(sum(vals) / len(vals), 1) if vals else None

    temp_mae = avg_metric(recent, 'temp_mae_c')
    wind_mae = avg_metric(recent, 'wind_mae_kt')
    wdir_mae = avg_metric(recent, 'wdir_mae_deg')
    wave_mae = None
    wave_entries = [e.get('wave', {}) for e in recent if e.get('wave')]
    if wave_entries:
        wave_vals = [w.get('hs_mae_m') for w in wave_entries if w.get('hs_mae_m') is not None]
        wave_mae = round(sum(wave_vals) / len(wave_vals), 2) if wave_vals else None

    def _color(val, green_lt, yellow_lt):
        if val is None:
            return '#94a3b8'
        return '#48bb78' if val < green_lt else '#fbd38d' if val < yellow_lt else '#fc8181'

    parts = []
    if temp_mae is not None:
        c = _color(temp_mae, 1.0, 2.0)
        parts.append(f'<span style="color:{c}">Temp \u00b1{temp_mae}\u00b0C</span>')
    if wind_mae is not None:
        c = _color(wind_mae, 3.0, 5.0)
        parts.append(f'<span style="color:{c}">Wind \u00b1{wind_mae}kt</span>')
    if wdir_mae is not None:
        c = _color(wdir_mae, 20, 40)
        parts.append(f'<span style="color:{c}">Dir \u00b1{wdir_mae}\u00b0</span>')
    if wave_mae is not None:
        c = _color(wave_mae, 0.3, 0.5)
        parts.append(f'<span style="color:{c}">Wave \u00b1{wave_mae}m</span>')

    if not parts:
        return ''

    return (
        '<p style="margin:0 0 6px;font-size:0.82em;color:#94a3b8">'
        f'\U0001f3af <strong>{T("model_accuracy")}</strong> (7d avg): '
        + ' \u00b7 '.join(parts)
        + f' <span style="color:#64748b">({len(recent)} runs)</span>'
        '</p>\n'
    )


@dataclass
class ForecastContext:
    """Bundle of all data needed to render the unified HTML forecast page."""
    meta: dict
    records: list
    prev_records: list = field(default_factory=list)
    ecmwf_records: list = field(default_factory=list)
    wave_data: dict | None = None
    tide_data: dict | None = None
    surf_planner: dict | None = None
    ensemble_data: dict | None = None
    accuracy_log: list | None = None
    cwa_obs: dict | None = None


def render_unified_html(
    meta: dict,
    records: list,
    prev_records: list,
    ecmwf_records: list,
    wave_data: dict | None,
    tide_data: dict | None = None,
    surf_planner: dict | None = None,
    ensemble_data: dict | None = None,
    accuracy_log: list | None = None,
    cwa_obs: dict | None = None,
    *,
    ctx: 'ForecastContext | None' = None,
) -> str:
    """
    Full web-app HTML: daily summary cards + complete hourly table
    (WRF + ECMWF IFS + wave columns) + WRF vs ECMWF agreement stats + legend.
    Optionally includes ensemble spread indicators when ensemble_data is provided.

    Can accept individual args (backwards-compatible) or a ForecastContext via ctx=.
    """
    # Allow callers to pass a ForecastContext instead of individual args
    if ctx is not None:
        meta = ctx.meta
        records = ctx.records
        prev_records = ctx.prev_records
        ecmwf_records = ctx.ecmwf_records
        wave_data = ctx.wave_data
        tide_data = ctx.tide_data
        surf_planner = ctx.surf_planner
        ensemble_data = ctx.ensemble_data
        accuracy_log = ctx.accuracy_log
        cwa_obs = ctx.cwa_obs
    # Build lookups (same as _render_summary_html)
    prev_by_valid = {r['valid_utc']: r for r in (prev_records or []) if r.get('valid_utc')}
    has_prev = bool(prev_by_valid)
    ec_by_valid = {r['valid_utc']: r for r in (ecmwf_records or []) if r.get('valid_utc')}
    has_ec = bool(ec_by_valid)
    ecmwf_wave  = (wave_data or {}).get('ecmwf_wave', {})
    wave_recs   = ecmwf_wave.get('records', [])
    wave_meta   = ecmwf_wave.get('meta', {})
    wave_by_valid = {r['valid_utc']: r for r in wave_recs if r.get('valid_utc')}
    has_wave = bool(wave_by_valid)
    wrf_by_valid = {r['valid_utc']: r for r in records if r.get('valid_utc')}
    all_valids = sorted(set(wrf_by_valid) | set(ec_by_valid) | set(wave_by_valid))

    # Ensemble spread lookup
    ens_by_valid: dict = {}
    if ensemble_data:
        for er in ensemble_data.get('ensemble', {}).get('records', []):
            if er.get('valid_utc'):
                ens_by_valid[er['valid_utc']] = er

    # Start with the summary section (header + daily cards + alerts + model shift),
    # then strip its closing </div> so we can append the full table.
    html = _render_summary_html(meta, records, prev_records, ecmwf_records, wave_data,
                               tide_data, surf_planner=surf_planner, cwa_obs=cwa_obs)
    if html.endswith('</div>\n'):
        html = html[:-len('</div>\n')]

    # ── Source legend ─────────────────────────────────────────────────────────
    html += (
        '<p style="margin:0 0 6px;font-size:0.82em;color:#94a3b8">'
        '<span class="badge badge-wrf">WRF 3km</span>'
        '&nbsp;'
        '<span class="badge badge-ec">ECMWF IFS</span>'
        f'&nbsp;— {T("source_note")}'
        '</p>\n'
    )

    # ── Accuracy badge (optional) ────────────────────────────────────────────
    if accuracy_log:
        html += _render_accuracy_badge(accuracy_log)

    # ── Table (desktop) ──────────────────────────────────────────────────────
    html += '<div class="fc-desktop">\n'
    html += ('<div style="margin-bottom:8px"><button class="col-toggle filter-btn" type="button">'
             + T('show_more_columns') + '</button></div>\n')
    html += '<table class="fc-table">\n'
    html += f'<caption>{T("fc_caption")}</caption>\n'
    html += '<thead>\n'

    html += '<tr>\n'
    html += '  <th class="th-time col-essential" title="Per-step sailing alerts">⚠</th>\n'
    html += '  <th class="th-time col-essential" style="text-align:left">UTC</th>\n'
    html += '  <th class="th-time col-essential" style="text-align:left">CST +8</th>\n'
    for key, cls, tip in [
        ('th_wind', 'th-wrf col-essential', 'Wind speed in knots (1 kt = 1.85 km/h)'),
        ('th_gust', 'th-ec col-essential', 'Maximum wind gust speed in knots'),
    ]:
        html += f'  <th class="{cls}" title="{tip}">{T(key)}</th>\n'
    if has_wave:
        for key, cls, tip in [
            ('th_waves', 'th-wave col-essential', 'Significant wave height in metres (combined sea state)'),
            ('th_period', 'th-wave col-secondary', 'Wave period in seconds — longer = more powerful swell'),
            ('th_swell', 'th-wave col-secondary', 'Swell wave height in metres (long-period waves only)'),
            ('th_wave_dir', 'th-wave col-secondary', 'Dominant wave direction — where waves come from'),
        ]:
            html += f'  <th class="{cls}" title="{tip}">{T(key)}</th>\n'
    for key, cls, tip in [
        ('th_pressure', 'th-wrf col-secondary', 'Mean sea-level pressure in hPa'),
        ('th_rain_6h', 'th-ec col-secondary', 'Precipitation accumulated over 6 hours in mm'),
        ('th_vis', 'th-ec col-secondary', 'Visibility in kilometres'),
        ('th_temp', 'th-wrf col-essential', 'Air temperature at 2m in degrees Celsius'),
        ('th_cloud', 'th-ec col-tertiary', 'Total cloud cover percentage'),
        ('th_cape', 'th-ec col-tertiary', 'Convective Available Potential Energy — thunderstorm indicator (J/kg)'),
    ]:
        html += f'  <th class="{cls}" title="{tip}">{T(key)}</th>\n'
    html += '</tr>\n</thead>\n<tbody>\n'

    _n_wave_cols = 4 if has_wave else 0
    # 3 (alert+UTC+CST) + 2 (wind+gust) + wave_cols + 6 (pressure+rain+vis+temp+cloud+CAPE)
    _total_cols  = 3 + 2 + _n_wave_cols + 6

    # ── Data rows ─────────────────────────────────────────────────────────────
    temp_deltas, wind_deltas, rain_deltas, mslp_deltas = [], [], [], []
    _EC_BADGE = '<sup class="ec-sup"> EC</sup>'
    _EC_BG    = '#0d2d1a'
    _prev_cst_date = None

    for row_idx, vt in enumerate(all_valids):
        wrf  = wrf_by_valid.get(vt)
        ec   = ec_by_valid.get(vt)
        wav  = wave_by_valid.get(vt)
        prev = prev_by_valid.get(vt, {})
        has_wrf = wrf is not None

        try:
            dt_u = datetime.fromisoformat(vt)
            dt_c = dt_u + timedelta(hours=8)
            utc_str      = dt_u.strftime('%H:%M')
            cst_str      = dt_c.strftime('%H:%M')
            cst_date_str = dt_c.strftime('%a %-d %b')
            cst_date_key = dt_c.strftime('%Y-%m-%d')
        except (ValueError, TypeError):
            utc_str, cst_str = vt, ''
            cst_date_str = ''
            cst_date_key = vt[:10]

        if cst_date_key != _prev_cst_date:
            _prev_cst_date = cst_date_key
            html += (f'<tr class="date-sep">'
                     f'<td colspan="{_total_cols}">'
                     f'📅 {cst_date_str} (CST)</td></tr>\n')

        row_cls = 'row-alt' if row_idx % 2 else ''
        row_bg  = '#111827' if row_idx % 2 else '#0f172a'
        if not has_wrf:
            row_extra = 'color:#94a3b8'
        else:
            row_extra = ''

        wt  = wrf.get('temp_c')       if wrf else None
        ww  = wrf.get('wind_kt')      if wrf else None
        wwd = wrf.get('wind_dir')     if wrf else None
        wg  = wrf.get('gust_kt')      if wrf else None
        wp  = wrf.get('mslp_hpa')     if wrf else None
        wr  = wrf.get('precip_mm_6h') if wrf else None
        wcl = wrf.get('cloud_pct')    if wrf else None
        wvs = wrf.get('vis_km')       if wrf else None
        wcp = wrf.get('cape')         if wrf else None

        et  = ec.get('temp_c')       if ec else None
        ew  = ec.get('wind_kt')      if ec else None
        ewd = ec.get('wind_dir')     if ec else None
        eg  = ec.get('gust_kt')      if ec else None
        ep  = ec.get('mslp_hpa')     if ec else None
        er  = ec.get('precip_mm_6h') if ec else None
        ecl = ec.get('cloud_pct')    if ec else None
        evs = ec.get('vis_km')       if ec else None
        ecp = ec.get('cape')         if ec else None

        dt_ = round(wt - et, 1) if wt is not None and et is not None else None
        dw_ = round(ww - ew, 1) if ww is not None and ew is not None else None
        dr_ = round(wr - er, 1) if wr is not None and er is not None else None
        dp_ = round(wp - ep, 1) if wp is not None and ep is not None else None

        _eff_wind = ww if ww is not None else ew
        _eff_gust = wg if wg is not None else eg
        _eff_rain = wr if wr is not None else er
        _eff_hs   = wav.get('wave_height') if wav else None
        _alert_html, _alert_bg = _row_alerts(_eff_wind, _eff_gust, _eff_hs, _eff_rain)
        if not _alert_bg:
            _alert_bg = row_bg

        style_attr = f' style="{row_extra}"' if row_extra else ''
        html += f'<tr class="{row_cls}"{style_attr}>\n'
        html += (f'  <td class="col-essential" style="background:{_alert_bg};font-size:0.85em">{_alert_html}</td>\n')
        html += f'  <td class="col-essential" style="font-weight:500">{utc_str}</td>\n'
        html += f'  <td class="col-essential" style="color:#94a3b8">{cst_str}</td>\n'
        if dt_ is not None: temp_deltas.append(dt_)
        if dw_ is not None: wind_deltas.append(dw_)
        if dr_ is not None: rain_deltas.append(dr_)
        if dp_ is not None: mslp_deltas.append(dp_)

        # Wind
        if ww is not None:
            bf = _beaufort(ww)
            arrow_s = f' {_wind_arrow(wwd)}' if wwd is not None else ''
            dir_s   = f' {deg_to_compass(wwd)}' if wwd is not None else ''
            html += (f'  <td class="col-essential" style="background:{_wind_bg(ww)}">'
                     f'{ww:.0f}kt B{bf}{arrow_s}{dir_s}'
                     f'{_delta_span(ww, prev.get("wind_kt"), ".0f", "kt", True)}</td>\n')
        elif ew is not None:
            bf = _beaufort(ew)
            arrow_s = f' {_wind_arrow(ewd)}' if ewd is not None else ''
            dir_s   = f' {deg_to_compass(ewd)}' if ewd is not None else ''
            html += (f'  <td class="col-essential" style="background:{_EC_BG}">'
                     f'{ew:.0f}kt B{bf}{arrow_s}{dir_s}{_EC_BADGE}</td>\n')
        else:
            html += '  <td class="col-essential c-muted">—</td>\n'

        # Gust
        g_val = wg if wg is not None else eg
        g_ec  = (wg is None and eg is not None)
        if g_val is not None:
            badge = _EC_BADGE if g_ec else ''
            html += (f'  <td class="col-essential" style="background:{_wind_bg(g_val)}">'
                     f'{g_val:.0f}kt{badge}</td>\n')
        else:
            html += '  <td class="col-essential c-muted">—</td>\n'

        # Wave columns
        if has_wave:
            hs   = wav.get('wave_height')       if wav else None
            tp   = wav.get('wave_period')       if wav else None
            swhs = wav.get('swell_wave_height') if wav else None
            wdir = wav.get('wave_direction')    if wav else None
            html += (f'  <td class="col-essential" style="background:{_wave_height_bg(hs)}">'
                     f'{_fmt(hs)}</td>\n')
            html += (f'  <td class="col-secondary" style="background:{_wave_period_bg(tp)}">'
                     f'{_fmt(tp, ".0f", "s") if tp is not None else "—"}</td>\n')
            html += (f'  <td class="col-secondary" style="background:{_wave_height_bg(swhs)}">'
                     f'{_fmt(swhs)}</td>\n')
            html += (f'  <td class="col-secondary">'
                     f'{_wave_dir_str(wdir)}</td>\n')

        # MSLP
        if wp is not None:
            html += (f'  <td class="col-secondary">'
                     f'{wp:.1f}{_delta_span(wp, prev.get("mslp_hpa"), ".1f", "")}</td>\n')
        elif ep is not None:
            html += (f'  <td class="col-secondary" style="background:{_EC_BG}">'
                     f'{ep:.1f}{_EC_BADGE}</td>\n')
        else:
            html += '  <td class="col-secondary c-muted">—</td>\n'

        # 6h Rain
        r_val = wr if wr is not None else er
        r_ec  = (wr is None and er is not None)
        if r_val is not None:
            badge = _EC_BADGE if r_ec else ''
            delta = _delta_span(wr, prev.get('precip_mm_6h'), '.1f', 'mm', True) if not r_ec else ''
            html += (f'  <td class="col-secondary" style="background:{_precip_bg(r_val)}">'
                     f'{r_val:.1f}mm{delta}{badge}</td>\n')
        else:
            html += '  <td class="col-secondary c-muted">—</td>\n'

        # Vis
        v_val = wvs if wvs is not None else evs
        v_ec  = (wvs is None and evs is not None)
        if v_val is not None:
            bg_v = _EC_BG if v_ec else ''
            badge = _EC_BADGE if v_ec else ''
            bg_attr = f' style="background:{bg_v}"' if bg_v else ''
            html += (f'  <td class="col-secondary"{bg_attr}>'
                     f'{v_val:.0f}km{badge}</td>\n')
        else:
            html += '  <td class="col-secondary c-muted">—</td>\n'

        # Temp
        if wt is not None:
            html += (f'  <td class="col-essential" style="background:{_temp_bg(wt)}">'
                     f'{wt:.1f}°{_delta_span(wt, prev.get("temp_c"), ".1f", "°")}</td>\n')
        elif et is not None:
            html += (f'  <td class="col-essential" style="background:{_EC_BG}">'
                     f'{et:.1f}°{_EC_BADGE}</td>\n')
        else:
            html += '  <td class="col-essential c-muted">—</td>\n'

        # Cloud
        cl_val = wcl if wcl is not None else ecl
        cl_ec  = (wcl is None and ecl is not None)
        if cl_val is not None:
            bg_cl = _EC_BG if cl_ec else ''
            badge = _EC_BADGE if cl_ec else ''
            bg_attr = f' style="background:{bg_cl}"' if bg_cl else ''
            html += (f'  <td class="col-tertiary"{bg_attr}>'
                     f'{cl_val:.0f}%{badge}</td>\n')
        else:
            html += '  <td class="col-tertiary c-muted">—</td>\n'

        # CAPE
        cp_val = wcp if wcp is not None else ecp
        cp_ec  = (wcp is None and ecp is not None)
        if cp_val is not None:
            badge = _EC_BADGE if cp_ec else ''
            html += (f'  <td class="col-tertiary" style="background:{_cape_bg(cp_val)}">'
                     f'{cp_val:.0f}{badge}</td>\n')
        else:
            html += '  <td class="col-tertiary c-muted">—</td>\n'

        html += '</tr>\n'

    html += '</tbody></table>\n</div>\n'

    # ── WRF vs ECMWF agreement summary ───────────────────────────────────────
    if has_ec and (temp_deltas or wind_deltas):
        def _mae(d):  return sum(abs(x) for x in d) / len(d) if d else None
        def _bias(d): return sum(d) / len(d) if d else None
        items = []
        for lbl, deltas, unit, thresh in [
            ('Temp', temp_deltas, '°C',  2.0),
            ('Wind', wind_deltas, 'kt',  5.0),
            ('Rain', rain_deltas, 'mm',  5.0),
            ('MSLP', mslp_deltas, 'hPa', 3.0),
        ]:
            mae = _mae(deltas); bias = _bias(deltas)
            if mae is not None:
                icon = '🟢' if mae < thresh * 0.5 else ('🟡' if mae < thresh else '🔴')
                s = '+' if bias > 0 else ''
                items.append(f'{icon} <b>{lbl}</b> MAE {mae:.1f}{unit} (bias {s}{bias:.1f}{unit})')
        if items:
            n = sum(1 for vt in all_valids if vt in wrf_by_valid and vt in ec_by_valid)
            html += ('<div class="alert-box alert-info">'
                     f'<b>{T("wrf_vs_ecmwf")}</b> — {n} {T("overlapping_steps")}: '
                     + ' · '.join(items) + '</div>\n')

    # ── Legend ────────────────────────────────────────────────────────────────
    html += (
        '<div class="legend-block">'
        f'<b>{T("legend_wind")}:</b> '
        f'<span style="background:#d4f0c0;padding:1px 4px;border-radius:3px">{T("legend_bf_light")}</span> '
        f'<span style="background:#e8f5c0;padding:1px 4px;border-radius:3px">{T("legend_bf4")}</span> '
        f'<span style="background:#fff7b0;padding:1px 4px;border-radius:3px">{T("legend_bf5")}</span> '
        f'<span style="background:#ffd9a0;padding:1px 4px;border-radius:3px">{T("legend_bf6")}</span> '
        f'<span style="background:#ffb080;padding:1px 4px;border-radius:3px">{T("legend_bf7")}</span> '
        f'<span style="background:#ff6666;color:#fff;padding:1px 4px;border-radius:3px">{T("legend_bf8")}</span>'
        '&nbsp;&nbsp;<b>Hs:</b> '
        f'<span style="background:#d4f0c0;padding:1px 4px;border-radius:3px">{T("legend_hs_calm")}</span> '
        f'<span style="background:#fff7b0;padding:1px 4px;border-radius:3px">{T("legend_hs_slight")}</span> '
        f'<span style="background:#ffd9a0;padding:1px 4px;border-radius:3px">{T("legend_hs_mod")}</span> '
        f'<span style="background:#ffb3b3;padding:1px 4px;border-radius:3px">{T("legend_hs_rough")}</span> '
        f'<span style="background:#ff6666;color:#fff;padding:1px 4px;border-radius:3px">{T("legend_hs_danger")}</span>'
        '&nbsp;&nbsp;<b>Tp:</b> '
        f'<span style="background:#fff7b0;padding:1px 4px;border-radius:3px">{T("legend_tp_wind")}</span> '
        f'<span style="background:#d4f0c0;padding:1px 4px;border-radius:3px">{T("legend_tp_swell")}</span> '
        f'<span style="background:#b0d9ff;padding:1px 4px;border-radius:3px">{T("legend_tp_ocean")}</span>'
        '</div>\n'
        '</div>\n'  # close card-glass
        '</section>\n'  # close #week section
    )

    # ══════════════════════════════════════════════════════════════════════════
    # #detail section — hourly table (collapsible, at bottom)
    # ══════════════════════════════════════════════════════════════════════════
    html += '<section id="detail" class="section">\n'

    # ── Mobile forecast cards (visible on mobile, hidden on desktop) ─────
    html += '<div class="fc-cards">\n'
    _prev_card_date = None
    for row_idx, vt in enumerate(all_valids):
        wrf  = wrf_by_valid.get(vt)
        ec   = ec_by_valid.get(vt)
        wav  = wave_by_valid.get(vt)

        try:
            dt_u = datetime.fromisoformat(vt)
            dt_c = dt_u + timedelta(hours=8)
            cst_str      = dt_c.strftime('%H:%M')
            cst_date_str = dt_c.strftime('%a %-d %b')
            cst_date_key = dt_c.strftime('%Y-%m-%d')
        except (ValueError, TypeError):
            cst_str = vt
            cst_date_str = ''
            cst_date_key = vt[:10]

        # Date header for cards
        if cst_date_key != _prev_card_date:
            _prev_card_date = cst_date_key
            html += f'<h3 class="fc-cards-date">📅 {cst_date_str}</h3>\n'

        # Effective values
        ww  = (wrf.get('wind_kt')  if wrf else None) or (ec.get('wind_kt')  if ec else None)
        wwd = (wrf.get('wind_dir') if wrf else None) or (ec.get('wind_dir') if ec else None)
        g_v = (wrf.get('gust_kt')  if wrf else None) or (ec.get('gust_kt')  if ec else None)
        wt  = (wrf.get('temp_c')   if wrf else None) or (ec.get('temp_c')   if ec else None)
        r_v = (wrf.get('precip_mm_6h') if wrf else None) or (ec.get('precip_mm_6h') if ec else None)
        hs  = wav.get('wave_height')       if wav else None
        tp  = wav.get('wave_period')       if wav else None
        swh = wav.get('swell_wave_height') if wav else None
        wdr = wav.get('wave_direction')    if wav else None
        wp  = (wrf.get('mslp_hpa')  if wrf else None) or (ec.get('mslp_hpa')  if ec else None)
        vs  = (wrf.get('vis_km')    if wrf else None) or (ec.get('vis_km')    if ec else None)
        cl  = (wrf.get('cloud_pct') if wrf else None) or (ec.get('cloud_pct') if ec else None)
        cp  = (wrf.get('cape')      if wrf else None) or (ec.get('cape')      if ec else None)

        _eff_hs   = hs
        _alert_html, _alert_bg = _row_alerts(ww, g_v, _eff_hs, r_v)

        wind_display = f'{ww:.0f}kt' if ww is not None else '—'
        wind_dir_display = f' {deg_to_compass(wwd)}' if wwd is not None else ''
        bf_display = f' B{_beaufort(ww)}' if ww is not None else ''
        # Wind direction arrow (points in direction wind blows TO = from_deg + 180)
        wind_arrow = ''
        if wwd is not None:
            arrow_deg = (wwd + 180) % 360
            wind_arrow = f'<span class="wind-arrow" style="display:inline-block;transform:rotate({arrow_deg}deg)">↓</span> '
        gust_display = f'{g_v:.0f}kt' if g_v is not None else '—'
        temp_display = f'{wt:.1f}°C' if wt is not None else '—'
        rain_display = f'{r_v:.1f}mm' if r_v is not None else '—'
        wave_display = f'{hs:.1f}m' if hs is not None else '—'
        period_display = f'{tp:.0f}s' if tp is not None else '—'
        swell_display = f'{swh:.1f}m' if swh is not None else '—'
        wave_dir_display = _wave_dir_str(wdr) if wdr is not None else '—'

        card_border_style = f' style="border-left:3px solid {_alert_bg}"' if _alert_bg else ''

        html += f'<div class="fc-card"{card_border_style}>\n'
        html += f'  <div class="fc-card-header">\n'
        html += f'    <span class="fc-card-time">{cst_str} {_alert_html}</span>\n'
        html += f'    <span class="fc-card-date">{cst_date_str}</span>\n'
        html += f'  </div>\n'
        html += f'  <div class="fc-card-metrics">\n'
        html += f'    <div class="fc-card-metric" style="background:{_wind_bg(ww)};padding:6px 8px;border-radius:8px">\n'
        html += f'      <span class="label">{T("card_wind")}</span>\n'
        html += f'      <span class="value">{wind_arrow}{wind_display}{bf_display}<span class="unit">{wind_dir_display}</span></span>\n'
        html += f'    </div>\n'
        html += f'    <div class="fc-card-metric" style="background:{_wind_bg(g_v)};padding:6px 8px;border-radius:8px">\n'
        html += f'      <span class="label">{T("card_gust")}</span>\n'
        html += f'      <span class="value">{gust_display}</span>\n'
        html += f'    </div>\n'
        if has_wave:
            html += f'    <div class="fc-card-metric" style="background:{_wave_height_bg(hs)};padding:6px 8px;border-radius:8px">\n'
            html += f'      <span class="label">{T("card_waves")}</span>\n'
            html += f'      <span class="value">{wave_display} <span class="unit">{period_display}</span></span>\n'
            html += f'    </div>\n'
            html += f'    <div class="fc-card-metric" style="background:{_wave_height_bg(swh)};padding:6px 8px;border-radius:8px">\n'
            html += f'      <span class="label">{T("card_swell")}</span>\n'
            html += f'      <span class="value">{swell_display} <span class="unit">{wave_dir_display}</span></span>\n'
            html += f'    </div>\n'
        html += f'    <div class="fc-card-metric" style="background:{_temp_bg(wt)};padding:6px 8px;border-radius:8px">\n'
        html += f'      <span class="label">{T("card_temp")}</span>\n'
        html += f'      <span class="value">{temp_display}</span>\n'
        html += f'    </div>\n'
        html += f'    <div class="fc-card-metric" style="background:{_precip_bg(r_v)};padding:6px 8px;border-radius:8px">\n'
        html += f'      <span class="label">{T("card_rain")}</span>\n'
        html += f'      <span class="value">{rain_display}</span>\n'
        html += f'    </div>\n'
        html += f'  </div>\n'

        # Expandable details
        pressure_display = f'{wp:.1f} hPa' if wp is not None else '—'
        vis_display = f'{vs:.0f} km' if vs is not None else '—'
        cloud_display = f'{cl:.0f}%' if cl is not None else '—'
        cape_display = f'{cp:.0f} J/kg' if cp is not None else '—'

        html += f'  <details>\n'
        html += f'    <summary></summary>\n'
        html += f'    <div class="extra-metrics">\n'
        html += f'      <span>{T("card_pressure")}: {pressure_display}</span>\n'
        html += f'      <span>{T("card_vis")}: {vis_display}</span>\n'
        html += f'      <span>{T("card_cloud")}: {cloud_display}</span>\n'
        html += f'      <span>{T("th_cape")}: {cape_display}</span>\n'
        html += f'    </div>\n'
        html += f'  </details>\n'
        html += f'</div>\n'

    html += '</div>\n'  # close fc-cards
    html += '</section>\n'  # close #detail section
    return html


# ═══════════════════════════════════════════════════════════════════════════════
# Multi-page rendering: Dashboard, Hourly, Accuracy
# ═══════════════════════════════════════════════════════════════════════════════


def _render_hero_banner(cwa_obs: dict | None) -> str:
    """Current conditions hero banner for the dashboard."""
    if not cwa_obs:
        return ''
    station = cwa_obs.get('station') or {}
    buoy = cwa_obs.get('buoy') or {}
    if not station and not buoy:
        return ''

    metrics = []
    if station.get('temp_c') is not None:
        metrics.append(f'<div class="hero-metric"><div class="value">{station["temp_c"]:.1f}<span class="unit">°C</span></div><div class="label">{T_str("card_temp","en")}</div></div>')
    if station.get('wind_kt') is not None:
        wind_dir_str = ''
        if station.get('wind_dir') is not None:
            wind_dir_str = f' {deg_to_compass(station["wind_dir"])}'
        metrics.append(f'<div class="hero-metric"><div class="value">{station["wind_kt"]:.0f}<span class="unit">kt{wind_dir_str}</span></div><div class="label">{T_str("card_wind","en")}</div></div>')
    if station.get('gust_kt') is not None and station['gust_kt'] > 0:
        metrics.append(f'<div class="hero-metric"><div class="value">{station["gust_kt"]:.0f}<span class="unit">kt</span></div><div class="label">{T_str("card_gust","en")}</div></div>')
    if buoy.get('wave_height_m') is not None:
        tp = buoy.get('wave_period_s')
        tp_str = f' {tp:.0f}s' if tp is not None else ''
        metrics.append(f'<div class="hero-metric"><div class="value">{buoy["wave_height_m"]:.1f}<span class="unit">m{tp_str}</span></div><div class="label">{T_str("card_waves","en")}</div></div>')
    if station.get('pressure_hpa') is not None:
        metrics.append(f'<div class="hero-metric"><div class="value">{station["pressure_hpa"]:.0f}<span class="unit">hPa</span></div><div class="label">{T_str("card_pressure","en")}</div></div>')

    if not metrics:
        return ''

    # Obs time display
    obs_time_str = ''
    obs_t = station.get('obs_time') or buoy.get('obs_time')
    if obs_t:
        try:
            dt = datetime.fromisoformat(obs_t)
            cst = dt + timedelta(hours=8) if dt.tzinfo is None or dt.utcoffset() == timedelta(0) else dt.astimezone(timezone(timedelta(hours=8)))
            obs_time_str = cst.strftime('%H:%M CST')
        except (ValueError, TypeError):
            pass

    return (
        '<div class="hero-banner card-glass">\n'
        f'  <h2 class="section-title" style="border:none;margin-bottom:{8}px">'
        f'{T("current_conditions")}</h2>\n'
        f'  <div class="hero-metrics">\n    ' + '\n    '.join(metrics) + '\n  </div>\n'
        f'  <div class="hero-source">{bilingual("CWA Keelung Station", "CWA 基隆測站")}'
        + (f' &middot; {obs_time_str}' if obs_time_str else '') + '</div>\n'
        '</div>\n'
    )


def _render_quick_glance(ctx: 'ForecastContext') -> str:
    """Compact next-24h table for dashboard."""
    wrf_by_valid = {r['valid_utc']: r for r in ctx.records if r.get('valid_utc')}
    ec_by_valid = {r['valid_utc']: r for r in (ctx.ecmwf_records or []) if r.get('valid_utc')}
    ecmwf_wave = (ctx.wave_data or {}).get('ecmwf_wave', {})
    wave_by_valid = {r['valid_utc']: r for r in ecmwf_wave.get('records', []) if r.get('valid_utc')}
    all_valids = sorted(set(wrf_by_valid) | set(ec_by_valid) | set(wave_by_valid))

    # Filter to next 24h (roughly 4 entries at 6h intervals)
    now = datetime.now(timezone.utc)
    next_24h = [vt for vt in all_valids
                if datetime.fromisoformat(vt) >= now - timedelta(hours=3)
                and datetime.fromisoformat(vt) <= now + timedelta(hours=27)]
    if not next_24h:
        next_24h = all_valids[:5]  # fallback

    html = '<div class="chart-container">\n'
    html += f'<div class="chart-title">{T("quick_glance")}</div>\n'
    html += '<table class="quick-table">\n'
    html += '<thead><tr>'
    html += '<th>CST</th>'
    html += f'<th>{T("th_wind")}</th>'
    html += f'<th>{T("th_gust")}</th>'
    html += f'<th>{T("th_waves")}</th>'
    html += f'<th>{T("th_temp")}</th>'
    html += f'<th>{T("th_rain_6h")}</th>'
    html += '</tr></thead>\n<tbody>\n'

    prev_date = None
    for idx, vt in enumerate(next_24h):
        wrf = wrf_by_valid.get(vt)
        ec = ec_by_valid.get(vt)
        wav = wave_by_valid.get(vt)

        try:
            dt_u = datetime.fromisoformat(vt)
            dt_c = dt_u + timedelta(hours=8)
            cst_str = dt_c.strftime('%H:%M')
            cst_date = dt_c.strftime('%a %-d')
        except (ValueError, TypeError):
            cst_str = vt
            cst_date = ''

        if cst_date != prev_date:
            prev_date = cst_date
            html += f'<tr class="date-sep"><td colspan="6">{cst_date}</td></tr>\n'

        wind = (wrf.get('wind_kt') if wrf else None) or (ec.get('wind_kt') if ec else None)
        wind_dir = (wrf.get('wind_dir') if wrf else None) or (ec.get('wind_dir') if ec else None)
        gust = (wrf.get('gust_kt') if wrf else None) or (ec.get('gust_kt') if ec else None)
        temp = (wrf.get('temp_c') if wrf else None) or (ec.get('temp_c') if ec else None)
        rain = (wrf.get('precip_mm_6h') if wrf else None) or (ec.get('precip_mm_6h') if ec else None)
        hs = wav.get('wave_height') if wav else None

        cls = ' class="row-alt"' if idx % 2 else ''
        dir_s = f' {deg_to_compass(wind_dir)}' if wind_dir is not None else ''
        bf = f' B{_beaufort(wind)}' if wind is not None else ''

        html += f'<tr{cls}>'
        html += f'<td style="font-weight:600">{cst_str}</td>'
        html += f'<td style="background:{_wind_bg(wind)}">{wind:.0f}kt{bf}{dir_s}</td>' if wind is not None else '<td>—</td>'
        html += f'<td style="background:{_wind_bg(gust)}">{gust:.0f}kt</td>' if gust is not None else '<td>—</td>'
        html += f'<td style="background:{_wave_height_bg(hs)}">{hs:.1f}m</td>' if hs is not None else '<td>—</td>'
        html += f'<td style="background:{_temp_bg(temp)}">{temp:.1f}°</td>' if temp is not None else '<td>—</td>'
        html += f'<td style="background:{_precip_bg(rain)}">{rain:.1f}mm</td>' if rain is not None else '<td>—</td>'
        html += '</tr>\n'

    html += '</tbody></table>\n</div>\n'
    return html


def _render_top_spots(surf_planner: dict | None) -> str:
    """Show top 3 surf spots for today on the dashboard."""
    if not surf_planner:
        return ''
    today = datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d')
    sp_days = surf_planner.get('days', {})
    sp_day = sp_days.get(today, {})
    if not sp_day:
        # Try first available day
        for dk in sorted(sp_days.keys()):
            sp_day = sp_days[dk]
            if sp_day:
                break
    if not sp_day:
        return ''

    all_spots = sp_day.get('all_spots', [])
    if not all_spots:
        # Fallback: just show best spot
        bs = sp_day.get('best_surf', {})
        if not bs.get('spot'):
            return ''
        all_spots = [bs]

    # Sort by score descending, take top 3
    sorted_spots = sorted(all_spots, key=lambda s: s.get('score', 0), reverse=True)[:3]

    html = f'<h3 class="section-title" style="font-size:16px">{T("top_spots_today")}</h3>\n'
    html += '<div class="grid grid-3">\n'
    for sp in sorted_spots:
        name = sp.get('spot', '?')
        emoji = sp.get('emoji', '🏄')
        label = sp.get('label', '')
        bg = sp.get('bg', '#1e293b')
        col = sp.get('col', '#94a3b8')
        spot_id = sp.get('id', name.lower().split()[0] if name else '')
        html += (
            f'<a href="/spots/{html_mod.escape(spot_id)}" class="spot-card">\n'
            f'  <div class="spot-card-name">🏄 {html_mod.escape(name)}</div>\n'
            f'  <div class="spot-card-rating" style="color:{col}">{emoji} {html_mod.escape(label)}</div>\n'
            f'  <div class="spot-card-action">{T("view_details")} →</div>\n'
            f'</a>\n'
        )
    html += '</div>\n'
    return html


def render_dashboard_page(ctx: ForecastContext, *, ai_summary_html: str = '',
                          build_utc: str = '', **kw) -> str:
    """Render the dashboard page (index.html): hero + AI summary + daily cards + quick glance."""
    body = ''

    # CWA warnings
    if ctx.cwa_obs and ctx.cwa_obs.get('warnings'):
        warnings_list = ctx.cwa_obs['warnings']
        body += '<div class="alert-box alert-danger" style="margin-bottom:16px">\n'
        body += f'  <h3 style="color:#fca5a5;margin:0 0 6px;font-size:14px">{bilingual("Active Weather Warnings", "氣象警特報")}</h3>\n'
        for w in warnings_list:
            w_type = html_mod.escape(str(w.get('type', '')))
            w_desc = html_mod.escape(str(w.get('description', '')))[:200]
            body += f'  <p style="margin:4px 0;font-size:13px;color:#fca5a5"><b>{w_type}</b> — {w_desc}</p>\n'
        body += '</div>\n'

    # Hero banner with current conditions
    body += _render_hero_banner(ctx.cwa_obs)

    # AI summary (injected from forecast_summary.py output)
    if ai_summary_html:
        body += ai_summary_html + '\n'

    # Daily summary cards (horizontal strip on mobile)
    wrf_by_valid = {r['valid_utc']: r for r in ctx.records if r.get('valid_utc')}
    ec_by_valid = {r['valid_utc']: r for r in (ctx.ecmwf_records or []) if r.get('valid_utc')}
    ecmwf_wave = (ctx.wave_data or {}).get('ecmwf_wave', {})
    wave_by_valid = {r['valid_utc']: r for r in ecmwf_wave.get('records', []) if r.get('valid_utc')}
    all_valids = sorted(set(wrf_by_valid) | set(ec_by_valid) | set(wave_by_valid))

    body += f'<h3 class="section-title" style="font-size:16px">{T("this_week")}</h3>\n'
    body += '<div class="daily-strip">\n'
    cards = _daily_summary_html(wrf_by_valid, ec_by_valid, wave_by_valid, all_valids,
                                ctx.tide_data, surf_planner=ctx.surf_planner)
    # Unwrap the <div class="daily-cards">...</div> to re-wrap in daily-strip
    cards = cards.replace('<div class="daily-cards">', '')
    if cards.rstrip().endswith('</div>'):
        cards = cards.rstrip()
        cards = cards[:-len('</div>')]
    body += cards + '\n</div>\n'

    # Top surf spots
    body += _render_top_spots(ctx.surf_planner)

    # Quick glance (next 24h compact table)
    body += _render_quick_glance(ctx)

    # CTA links
    body += '<div style="display:flex;flex-wrap:wrap;gap:12px;margin-top:16px">\n'
    body += f'  <a href="/hourly" class="cta-link cta-link-primary">{T("see_full_hourly")} →</a>\n'
    body += f'  <a href="/surf" class="cta-link">{T("see_all_spots")} →</a>\n'
    body += '</div>\n'

    return render_page(
        title_key='dashboard_title',
        nav_active='/',
        body_html=body,
        build_utc=build_utc,
        **kw,
    )


def render_hourly_page(ctx: ForecastContext, *, build_utc: str = '', **kw) -> str:
    """Render the hourly forecast page (hourly.html): full table + charts + model comparison."""
    # Re-use the existing render_unified_html which already produces the full table
    inner_html = render_unified_html(
        ctx.meta, ctx.records, ctx.prev_records, ctx.ecmwf_records,
        ctx.wave_data, ctx=ctx,
    )

    return render_page(
        title_key='hourly_title',
        nav_active='/hourly',
        body_html=inner_html,
        build_utc=build_utc,
        **kw,
    )


def render_accuracy_page(accuracy_log: list | None, *, build_utc: str = '', **kw) -> str:
    """Render the accuracy dashboard page (accuracy.html)."""
    body = f'<h2 class="section-title">{T("accuracy_title")}</h2>\n'

    if not accuracy_log:
        body += f'<p class="c-muted">{bilingual("No accuracy data available yet.", "尚無準確度資料。")}</p>\n'
        return render_page(
            title_key='accuracy_title',
            nav_active='/accuracy',
            body_html=body,
            build_utc=build_utc,
            **kw,
        )

    # Recent entries (last 7 days)
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    recent = []
    for e in accuracy_log:
        try:
            vt = datetime.fromisoformat(e.get('verified_utc', ''))
            if vt >= cutoff:
                recent.append(e)
        except (ValueError, TypeError):
            pass
    if not recent:
        recent = accuracy_log[-10:]  # fallback

    # Summary cards
    def avg_metric(entries, key):
        vals = [e.get(key) for e in entries if e.get(key) is not None]
        return round(sum(vals) / len(vals), 2) if vals else None

    def bias_metric(entries, key):
        vals = [e.get(key) for e in entries if e.get(key) is not None]
        return round(sum(vals) / len(vals), 2) if vals else None

    temp_mae = avg_metric(recent, 'temp_mae_c')
    temp_bias = bias_metric(recent, 'temp_bias_c')
    wind_mae = avg_metric(recent, 'wind_mae_kt')
    wind_bias = bias_metric(recent, 'wind_bias_kt')
    wdir_mae = avg_metric(recent, 'wdir_mae_deg')
    mslp_mae = avg_metric(recent, 'mslp_mae_hpa')
    wave_mae = None
    wave_bias = None
    wave_entries = [e.get('wave', {}) for e in recent if e.get('wave')]
    if wave_entries:
        w_vals = [w.get('hs_mae_m') for w in wave_entries if w.get('hs_mae_m') is not None]
        wave_mae = round(sum(w_vals) / len(w_vals), 2) if w_vals else None
        b_vals = [w.get('hs_bias_m') for w in wave_entries if w.get('hs_bias_m') is not None]
        wave_bias = round(sum(b_vals) / len(b_vals), 2) if b_vals else None

    def _color(val, green_lt, yellow_lt):
        if val is None: return '#94a3b8'
        return '#48bb78' if val < green_lt else '#fbd38d' if val < yellow_lt else '#fc8181'

    def _bias_str(bias, unit):
        if bias is None: return ''
        sign = '+' if bias > 0 else ''
        return f'{sign}{bias}{unit}'

    body += f'<p style="color:#94a3b8;font-size:13px;margin-bottom:16px">{bilingual(f"Based on {len(recent)} verified runs in the last 7 days", f"基於過去7天 {len(recent)} 次驗證")}</p>\n'

    body += '<div class="accuracy-summary">\n'
    for label, mae, bias, unit, g, y in [
        ('Temp', temp_mae, temp_bias, '°C', 1.0, 2.0),
        ('Wind', wind_mae, wind_bias, 'kt', 3.0, 5.0),
        ('W.Dir', wdir_mae, None, '°', 20, 40),
        ('MSLP', mslp_mae, None, 'hPa', 1.0, 2.0),
        ('Wave Hs', wave_mae, wave_bias, 'm', 0.3, 0.5),
    ]:
        if mae is None:
            continue
        c = _color(mae, g, y)
        body += (
            f'<div class="accuracy-card card-glass">\n'
            f'  <div class="value" style="color:{c}">&pm;{mae}{unit}</div>\n'
            f'  <div class="metric-bar"><div class="metric-bar-fill" style="width:{min(mae/y*100, 100):.0f}%"></div></div>\n'
            f'  <div class="label">{label} MAE</div>\n'
        )
        if bias is not None:
            body += f'  <div class="bias" style="color:{c}">{_bias_str(bias, unit)} bias</div>\n'
        body += '</div>\n'
    body += '</div>\n'

    # By forecast horizon
    body += f'<h3 class="section-title" style="font-size:16px">{T("by_horizon")}</h3>\n'
    horizons_data = {}
    for e in recent:
        bh = e.get('by_horizon', {})
        for horizon, metrics in bh.items():
            if horizon not in horizons_data:
                horizons_data[horizon] = []
            horizons_data[horizon].append(metrics)

    if horizons_data:
        body += '<div class="chart-container">\n'
        body += '<table class="quick-table">\n<thead><tr>'
        body += '<th>Horizon</th><th>Temp MAE</th><th>Wind MAE</th><th>Dir MAE</th>'
        body += '</tr></thead>\n<tbody>\n'
        for horizon in sorted(horizons_data.keys()):
            entries = horizons_data[horizon]
            t_vals = [m.get('temp_mae_c') for m in entries if m.get('temp_mae_c') is not None]
            w_vals = [m.get('wind_mae_kt') for m in entries if m.get('wind_mae_kt') is not None]
            d_vals = [m.get('wdir_mae_deg') for m in entries if m.get('wdir_mae_deg') is not None]
            t_avg = f'{sum(t_vals)/len(t_vals):.1f}°C' if t_vals else '—'
            w_avg = f'{sum(w_vals)/len(w_vals):.1f}kt' if w_vals else '—'
            d_avg = f'{sum(d_vals)/len(d_vals):.0f}°' if d_vals else '—'
            body += f'<tr><td style="font-weight:600">{horizon}</td><td>{t_avg}</td><td>{w_avg}</td><td>{d_avg}</td></tr>\n'
        body += '</tbody></table>\n</div>\n'

    # Verification history table
    body += f'<h3 class="section-title" style="font-size:16px">{T("verification_history")}</h3>\n'
    body += '<div class="chart-container">\n'
    body += '<table class="quick-table">\n<thead><tr>'
    body += '<th>Init</th><th>Verified</th><th>Temp MAE</th><th>Wind MAE</th><th>Wave MAE</th><th>N</th>'
    body += '</tr></thead>\n<tbody>\n'
    for idx, e in enumerate(reversed(accuracy_log[-20:])):
        cls = ' class="row-alt"' if idx % 2 else ''
        init = e.get('init_utc', '?')[:16]
        verified = e.get('verified_utc', '?')[:16]
        t = f'{e["temp_mae_c"]:.1f}°C' if e.get('temp_mae_c') is not None else '—'
        w = f'{e["wind_mae_kt"]:.1f}kt' if e.get('wind_mae_kt') is not None else '—'
        wv = '—'
        if e.get('wave') and e['wave'].get('hs_mae_m') is not None:
            wv = f'{e["wave"]["hs_mae_m"]:.2f}m'
        n = e.get('n_compared', '?')
        body += f'<tr{cls}><td>{init}</td><td>{verified}</td>'
        body += f'<td style="color:{_color(e.get("temp_mae_c"), 1.0, 2.0)}">{t}</td>'
        body += f'<td style="color:{_color(e.get("wind_mae_kt"), 3.0, 5.0)}">{w}</td>'
        body += f'<td>{wv}</td><td>{n}</td></tr>\n'
    body += '</tbody></table>\n</div>\n'

    return render_page(
        title_key='accuracy_title',
        nav_active='/accuracy',
        body_html=body,
        build_utc=build_utc,
        **kw,
    )


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    p = argparse.ArgumentParser(
        description='Extract Keelung point forecast from WRF GRIB2 subset files.'
    )
    p.add_argument('--rundir',      required=True,
                   help='Directory containing *_keelung*.grb2 files')
    p.add_argument('--prev-json',   default=None,
                   help='Previous run summary JSON for delta comparison')
    p.add_argument('--output-json', default='keelung_summary.json',
                   help='Output summary JSON path (default: keelung_summary.json)')
    p.add_argument('--output-html', default='forecast.html',
                   help='Output HTML path (default: forecast.html)')
    p.add_argument('--ecmwf-json',  default=None,
                   help='ECMWF IFS JSON produced by ecmwf_fetch.py (enables comparison table)')
    p.add_argument('--wave-json',   default=None,
                   help='Wave JSON produced by wave_fetch.py (adds wave forecast section)')
    p.add_argument('--tide-json',   default=None,
                   help='Tide JSON produced by tide_predict.py (adds tide info to daily cards)')
    p.add_argument('--surf-json',   default=None,
                   help='Surf planner JSON produced by surf_forecast.py (adds surf info to day cards)')
    p.add_argument('--ensemble-json', default=None,
                   help='Ensemble JSON produced by ensemble_fetch.py (adds model spread indicators)')
    p.add_argument('--accuracy-log', default=None,
                   help='Accuracy log JSON from accuracy_track.py (adds accuracy badge)')
    p.add_argument('--cwa-obs',     default=None,
                   help='CWA observations JSON from cwa_fetch.py (adds warnings + current conditions)')
    p.add_argument('--output-dir',  default=None,
                   help='Output directory for multi-page HTML (generates index.html, hourly.html, accuracy.html)')
    p.add_argument('--ai-summary',  default=None,
                   help='AI summary HTML fragment to embed in dashboard page')
    p.add_argument('--output-wind-grid', default=None,
                   help='Output wind grid JSON for frontend particle animation')
    p.add_argument('--list-vars',   action='store_true',
                   help='Diagnostic: list all GRIB2 shortNames in the first file and exit')
    args = p.parse_args()

    rundir = Path(args.rundir)
    if not rundir.exists():
        log.error("--rundir %s does not exist", rundir)
        sys.exit(1)

    # ── Diagnostic mode ───────────────────────────────────────────────────────
    if args.list_vars:
        grbs = sorted(rundir.glob('*_keelung*.grb2'))
        if not grbs:
            log.error("No *_keelung*.grb2 files found.")
            sys.exit(1)
        # f000 = init analysis — has pressure levels, 2m/10m, MSLP, but NOT
        # accumulated fields (precip, cloud, gusts, CAPE).
        log.info("=== %s (f000 — init/analysis hour) ===", grbs[0].name)
        list_vars(grbs[0])
        # f006 (or next available) — first forecast hour where accumulated
        # fields (precip, cloud cover, gusts, CAPE) should appear.
        if len(grbs) > 1:
            log.info("=== %s (first forecast hour — check for new vars) ===", grbs[1].name)
            list_vars(grbs[1])
        return

    # ── Main analysis ─────────────────────────────────────────────────────────
    log.info("Analyzing GRIB2 files in %s …", rundir)
    meta, records = extract_forecast(rundir)

    if not records:
        log.warning("No records extracted. Run with --list-vars to diagnose available fields.")
        # Still write empty outputs so downstream steps don't break
        Path(args.output_html).write_text('<p>No forecast data extracted.</p>')
        Path(args.output_json).write_text(json.dumps({'meta': meta, 'records': []}, indent=2))
        sys.exit(0)

    # ── Load previous summary ─────────────────────────────────────────────────
    prev_records = []
    if args.prev_json and Path(args.prev_json).exists():
        prev_data = load_json_file(args.prev_json, "previous summary")
        if prev_data:
            prev_records = prev_data.get('records', [])
            prev_init = prev_data.get('meta', {}).get('init_utc', 'unknown')
            log.info("Previous run: %s (%d records)", prev_init, len(prev_records))

    # ── Write JSON summary ────────────────────────────────────────────────────
    summary = {'meta': meta, 'records': records}
    out_json = Path(args.output_json)
    out_json.write_text(json.dumps(summary, indent=2))
    log.info("Summary → %s", out_json)

    # ── Export wind grid for frontend particle animation ──────────────────────
    if args.output_wind_grid:
        wind_grid = extract_wind_grid(rundir, meta)
        if wind_grid:
            wg_path = Path(args.output_wind_grid)
            wg_path.parent.mkdir(parents=True, exist_ok=True)
            wg_path.write_text(json.dumps(wind_grid))
            log.info("Wind grid → %s (%d timesteps, %dx%d)",
                     wg_path, len(wind_grid['timesteps']),
                     wind_grid['grid']['nx'], wind_grid['grid']['ny'])
        else:
            log.warning("Could not extract wind grid from GRIB2 files")

    # ── Load ECMWF comparison data ────────────────────────────────────────────
    ecmwf_records = []
    if args.ecmwf_json and Path(args.ecmwf_json).exists():
        ecmwf_data = load_json_file(args.ecmwf_json, "ECMWF JSON")
        if ecmwf_data:
            ecmwf_records = ecmwf_data.get('records', [])
            ecmwf_init = ecmwf_data.get('meta', {}).get('init_utc', 'unknown')
            log.info("ECMWF data: %s (%d records)", ecmwf_init, len(ecmwf_records))

    # ── Load wave data ────────────────────────────────────────────────────────
    wave_data = None
    if args.wave_json and Path(args.wave_json).exists():
        wave_data = load_json_file(args.wave_json, "wave JSON")
        if wave_data:
            ecmwf_wave_recs = len((wave_data.get('ecmwf_wave') or {}).get('records', []))
            cwa_wave_recs   = len((wave_data.get('cwa_wave')   or {}).get('records', []))
            log.info("Wave data: %d ECMWF steps, %d CWA steps",
                     ecmwf_wave_recs, cwa_wave_recs)

    # ── Load tide data ──────────────────────────────────────────────────────
    tide_data = None
    if args.tide_json and Path(args.tide_json).exists():
        tide_data = load_json_file(args.tide_json, "tide JSON")
        if tide_data:
            n_extrema = len(tide_data.get('extrema', []))
            log.info("Tide data: %d extrema", n_extrema)

    # ── Load surf planner JSON (optional) ─────────────────────────────────────
    surf_planner = None
    if args.surf_json:
        surf_planner = load_json_file(args.surf_json, "surf JSON")
        if surf_planner:
            log.info("Loaded surf planner JSON: %s", args.surf_json)

    # ── Load ensemble data (optional) ─────────────────────────────────────────
    ensemble_data = None
    if args.ensemble_json and Path(args.ensemble_json).exists():
        ensemble_data = load_json_file(args.ensemble_json, "ensemble JSON")
        if ensemble_data:
            n_models = len(ensemble_data.get('models', {}))
            n_ens = len(ensemble_data.get('ensemble', {}).get('records', []))
            log.info("Ensemble data: %d models, %d timesteps", n_models, n_ens)

    # ── Load accuracy log (optional) ──────────────────────────────────────────
    accuracy_log = None
    if args.accuracy_log and Path(args.accuracy_log).exists():
        accuracy_log = load_json_file(args.accuracy_log, "accuracy log")
        if accuracy_log:
            log.info("Accuracy log: %d entries", len(accuracy_log))

    # ── Load CWA observations (optional) ──────────────────────────────────────
    cwa_obs = None
    if args.cwa_obs and Path(args.cwa_obs).exists():
        cwa_obs = load_json_file(args.cwa_obs, "CWA observations")
        if cwa_obs:
            has_station = bool(cwa_obs.get('station'))
            has_buoy = bool(cwa_obs.get('buoy'))
            n_warnings = len(cwa_obs.get('warnings', []))
            log.info("CWA obs: station=%s buoy=%s warnings=%d",
                     has_station, has_buoy, n_warnings)

    # ── Write HTML ────────────────────────────────────────────────────────────
    fctx = ForecastContext(
        meta=meta, records=records, prev_records=prev_records,
        ecmwf_records=ecmwf_records, wave_data=wave_data,
        tide_data=tide_data, surf_planner=surf_planner,
        ensemble_data=ensemble_data, accuracy_log=accuracy_log,
        cwa_obs=cwa_obs,
    )

    build_utc = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

    if args.output_dir:
        # ── Multi-page output ──────────────────────────────────────────────
        out_dir = Path(args.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        # Load AI summary fragment if provided
        ai_html = ''
        if args.ai_summary and Path(args.ai_summary).exists():
            ai_html = Path(args.ai_summary).read_text(encoding='utf-8')

        # Dashboard (index.html)
        dashboard = render_dashboard_page(fctx, ai_summary_html=ai_html,
                                          build_utc=build_utc)
        (out_dir / 'index.html').write_text(dashboard, encoding='utf-8')
        log.info("Dashboard → %s/index.html", out_dir)

        # Hourly forecast (hourly.html)
        hourly = render_hourly_page(fctx, build_utc=build_utc)
        (out_dir / 'hourly.html').write_text(hourly, encoding='utf-8')
        log.info("Hourly → %s/hourly.html", out_dir)

        # Accuracy dashboard (accuracy.html)
        accuracy = render_accuracy_page(accuracy_log, build_utc=build_utc)
        (out_dir / 'accuracy.html').write_text(accuracy, encoding='utf-8')
        log.info("Accuracy → %s/accuracy.html", out_dir)
    else:
        # ── Legacy single-file output (backwards compatible) ───────────────
        html_full = render_unified_html(meta, records, prev_records, ecmwf_records,
                                        wave_data, ctx=fctx)
        out_html = Path(args.output_html)
        out_html.write_text(html_full)
        log.info("HTML → %s", out_html)

    # ── Expose to GitHub Actions ──────────────────────────────────────────────
    gha = os.environ.get('GITHUB_OUTPUT')
    if gha:
        with open(gha, 'a') as f:
            if args.output_dir:
                f.write(f'analysis_dir={Path(args.output_dir).resolve()}\n')
            else:
                f.write(f'analysis_html={Path(args.output_html).resolve()}\n')
            f.write(f'analysis_json={out_json.resolve()}\n')


if __name__ == '__main__':
    setup_logging()
    main()
