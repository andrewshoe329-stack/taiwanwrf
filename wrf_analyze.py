#!/usr/bin/env python3
"""
wrf_analyze.py
==============
Extract a Keelung point forecast from WRF Keelung-subset GRIB2 files,
compare with the previous run (run-to-run model drift), and emit:

  --output-json  keelung_summary.json   machine-readable, stored on Drive
                                        so the next run can diff against it
  --output-html  email_analysis.html    HTML fragment embedded in the email

Usage:
  python wrf_analyze.py \\
      --rundir wrf_downloads/M-A0064_20260309_00UTC \\
      [--prev-json keelung_summary_prev.json] \\
      [--ecmwf-json ecmwf_keelung.json] \\
      [--output-json keelung_summary.json] \\
      [--output-html email_analysis.html] \\
      [--list-vars]           # diagnostic: list all GRIB2 variables in first file

Requirements: eccodes, numpy  (already installed by the workflow)
"""

import argparse
import json
import logging
import math
import os
import re
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone

import numpy as np

from config import KEELUNG_LAT, KEELUNG_LON, COMPASS_NAMES, deg_to_compass, setup_logging

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
# be captured.  Populate this once you've seen the actual paramIds in the email
# diagnostic (look for lines like:  shortName=unknown  paramId=<N>).
#
# Common NCEP WRF GRIB2 paramIds to try:
#   61  → total precip (APCP)       → 'precip_raw'
#   71  → total cloud cover (%)     → 'cloud_raw'
#   180 → wind gust (m/s)           → 'gust_ms'
#   59  → CAPE (J/kg)               → 'cape'
#   20  → visibility (m)            → 'vis_m'
#
# Example — once you see "shortName=unknown  paramId=61" in the email, add:
#   61: 'precip_raw',
PARAMID_VARS: dict[int, str] = {
    # Add entries here after the next email diagnostic shows actual paramIds.
    # e.g.:  61: 'precip_raw',
}

# Maps raw key → (display unit, conversion function)
DERIVED = {
    'temp_c':    ('°C',  lambda d: d['temp_k'] - 273.15),
    'wind_kt':   ('kt',  lambda d: math.sqrt(d['u10']**2 + d['v10']**2) * 1.94384),
    'wind_dir':  ('°',   lambda d: (270 - math.degrees(math.atan2(d['v10'], d['u10']))) % 360),
    'mslp_hpa':  ('hPa', lambda d: d['mslp_pa'] / 100),
    'precip_mm': ('mm',  lambda d: d['precip_raw']),   # units normalised in read_point()
    'cloud_pct': ('%',   lambda d: d['cloud_raw'] * 100
                                   if d['cloud_raw'] <= 1.01 else d['cloud_raw']),
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
    dist = np.sqrt((lats2d - lat) ** 2 + (lons2d - lon) ** 2)
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
            except Exception as e:
                log.warning("Skipping GRIB message in list_vars: %s", e)
            finally:
                ec.codes_release(msg)


def read_point(grib_path: Path, lat: float, lon: float) -> dict:
    """
    Extract all configured variables at the nearest grid point.
    Returns a dict of raw values keyed by output_key.
    Grid geometry (lat/lon arrays) is cached so it's only computed once per file.
    """
    import eccodes as ec

    # Build shortName → list of (tol_filter, level_filter, key) for fast lookup
    sn_map: dict[str, list] = {}
    for snames, tol, lvl, key in VARS:
        for sn in snames:
            sn_map.setdefault(sn, []).append((tol, lvl, key))

    raw: dict[str, float] = {}
    grid_cache: dict = {}

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
                                    ck2 = (ni2, nj2)
                                    if ck2 not in grid_cache:
                                        lt2 = ec.codes_get_array(msg, 'latitudes').reshape(nj2, ni2)
                                        ln2 = ec.codes_get_array(msg, 'longitudes').reshape(nj2, ni2)
                                        grid_cache[ck2] = nearest_idx(lt2, ln2, lat, lon)
                                    jj, ii = grid_cache[ck2]
                                    vals2 = ec.codes_get_values(msg).reshape(nj2, ni2)
                                    raw[out_key] = float(vals2[jj, ii])
                        except Exception as e:
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
                cache_key = (ni, nj)

                if cache_key not in grid_cache:
                    lats = ec.codes_get_array(msg, 'latitudes').reshape(nj, ni)
                    lons = ec.codes_get_array(msg, 'longitudes').reshape(nj, ni)
                    grid_cache[cache_key] = nearest_idx(lats, lons, lat, lon)

                j, i = grid_cache[cache_key]
                vals = ec.codes_get_values(msg).reshape(nj, ni)
                val  = float(vals[j, i])

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
                        if 0 < val < 0.5:
                            val *= 1000.0

                raw[matched_key] = val

            except Exception as e:
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



# ── Daily summary cards ───────────────────────────────────────────────────────

def _sail_rating(max_wind: float | None, max_gust: float | None,
                 max_hs: float | None, total_rain: float) -> tuple[str, str]:
    """Return (label, bg_color) — go/marginal/no-go sailing suitability."""
    no_go = (
        (max_gust  is not None and max_gust  >= 34) or   # gale gusts
        (max_wind  is not None and max_wind  >= 28) or   # near-gale sustained
        (max_hs    is not None and max_hs    >= 2.5)     # rough-plus seas
    )
    marginal = (
        (max_gust  is not None and max_gust  >= 22) or   # strong breeze gusts
        (max_wind  is not None and max_wind  >= 17) or   # fresh breeze
        (max_hs    is not None and max_hs    >= 1.5) or  # moderate seas
        total_rain >= 15                                  # significant rain
    )
    if no_go:
        return '🔴 No-go', '#3d1515'
    if marginal:
        return '🟡 Marginal', '#3d2e00'
    return '🟢 Good', '#0d2d1a'


def _condition_emoji(max_wind: float, total_rain: float, max_cape: float,
                     max_hs: float, max_gust: float | None = None) -> str:
    if max_hs is not None and max_hs >= 3.5:
        return '🌊'
    if max_cape is not None and max_cape >= 500:
        return '⛈️'
    if total_rain >= 15:
        return '🌧️'
    if total_rain >= 3:
        return '🌦️'
    if max_gust is not None and max_gust >= 34:
        return '💨'
    if max_wind is not None and max_wind >= 25:
        return '💨'
    if max_wind is not None and max_wind >= 15:
        return '🌬️'
    return '🌤️'


def _daily_summary_html(
    wrf_by_valid: dict,
    ec_by_valid:  dict,
    wave_by_valid: dict,
    all_valids: list,
) -> str:
    """
    Compact day-by-day summary cards (one per CST calendar day).
    Uses WRF data where available; falls back to ECMWF for extended days.
    Shows: sailing suitability rating, condition icon, wave, wind, rain, temp.
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

    cards_html = '<div style="display:flex;flex-wrap:wrap;gap:8px;margin:10px 0 14px">\n'

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

        rain_str = f'{total_r:.0f}mm' if total_r > 0 else 'dry'

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

        cards_html += (
            f'<div style="border:1px solid #2d3f5a;border-top:3px solid {card_border};'
            f'border-radius:5px;padding:7px 10px;min-width:120px;background:#111827;'
            f'font-size:12px;line-height:1.5">\n'
            f'  <div style="font-weight:700;color:#e2e8f0;font-size:1em">'
            f'{day_label}&nbsp;<span style="font-size:1.1em">{cond_icon}</span></div>\n'
            f'  <div style="background:{sail_bg};border-radius:3px;padding:1px 5px;'
            f'font-weight:600;font-size:0.9em;margin:2px 0 3px;display:inline-block;color:#e2e8f0">'
            f'{sail_label}</div>\n'
            + (f'  <div style="color:#94a3b8">🌊 {wave_str}</div>\n' if wave_str else '')
            + f'  <div style="color:#94a3b8">💨 {wind_str}</div>\n'
            f'  <div style="color:#94a3b8">🌧️ {rain_str}</div>\n'
            f'  <div style="color:#94a3b8">🌡️ {temp_str}</div>\n'
            + cape_badge
            + f'  <div style="margin-top:4px">'
            f'<span style="background:{src_bg};color:{src_color};font-size:0.72em;'
            f'padding:1px 5px;border-radius:3px">{src_label}</span></div>\n'
            f'</div>\n'
        )

    cards_html += '</div>\n'
    return cards_html


# ── Unified table (all sources, JS-togglable column groups) ──────────────────

def render_email_html(
    meta: dict,
    records: list,
    prev_records: list,
    ecmwf_records: list,
    wave_data: dict | None,
) -> str:
    """
    Compact 7-day sailing summary for Keelung.

    Emits:
      - Daily summary cards (Good/Marginal/No-go) with wind, wave, rain, temp
      - Alerts for significant hazards (gale, heavy rain, rough seas)
      - Model shift note if prev run is available and drift is significant
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
        '<div style="font-family:Arial,sans-serif;font-size:14px;line-height:1.4;'
        'background:#0f172a;color:#e2e8f0;padding:16px;border-radius:8px">\n'
        '<h3 style="margin:0 0 2px;font-size:15px;color:#93c5fd">\n'
        f'  🌏 Keelung Unified Forecast\n'
        f'  <span style="font-weight:normal;font-size:0.85em;color:#94a3b8">'
        f'&nbsp;{KEELUNG_LAT}°N {KEELUNG_LON}°E</span>\n'
        '</h3>\n'
        f'<p style="margin:0 0 4px;color:#475569;font-size:0.88em">'
        f'{meta.get("model_id","?")} · WRF Init: {init_str}{wave_init_str}'
        f'{"&nbsp;·&nbsp; <i>Δ vs prev WRF run in brackets</i>" if has_prev else ""}'
        '</p>\n\n'
    )

    # ── Daily summary cards ───────────────────────────────────────────────────
    html += _daily_summary_html(wrf_by_valid, ec_by_valid, wave_by_valid, all_valids)


    # ── Alerts (WRF primary; ECMWF fills in gust/rain/CAPE) ──────────────────
    alerts = []
    _wrf = records or []
    _ec  = ecmwf_records or []
    # wind/MSLP: WRF primary; gust/rain/CAPE: EC (WRF never publishes these)
    max_wind   = max((r.get('wind_kt')      or 0 for r in _wrf + _ec), default=0)
    max_gust   = max((r.get('gust_kt')      or 0 for r in _wrf + _ec), default=0)
    total_rain = (sum(r.get('precip_mm_6h') or 0 for r in _wrf)
                  or sum(r.get('precip_mm_6h') or 0 for r in _ec))
    min_mslp   = min((r.get('mslp_hpa')     or 9999 for r in _wrf + _ec), default=9999)
    max_cape   = max((r.get('cape')         or 0 for r in _wrf + _ec), default=0)
    if max_wind  >= 34: alerts.append(f'⚠️ <b>Gale-force winds (B8+)</b> — {max_wind:.0f}kt — consider not sailing')
    elif max_wind >= 28: alerts.append(f'⚠️ Near-gale (B7) — {max_wind:.0f}kt — harbour recommended')
    elif max_wind >= 22: alerts.append(f'💨 Strong breeze (B6) — {max_wind:.0f}kt — reef in')
    if max_gust  >= 34: alerts.append(f'⚠️ <b>Gale gusts to {max_gust:.0f}kt</b>')
    elif max_gust >= 28: alerts.append(f'💨 Near-gale gusts to {max_gust:.0f}kt')
    if total_rain >= 50: alerts.append(f'🌧️ <b>Heavy rain</b> — {total_rain:.0f}mm total')
    elif total_rain >= 15: alerts.append(f'🌦️ Moderate rain — {total_rain:.0f}mm total')
    if min_mslp  <= 985: alerts.append(f'🌀 <b>Low MSLP {min_mslp:.0f}hPa</b> — possible tropical influence')
    if max_cape  >= 1000: alerts.append(f'⛈️ High instability — CAPE {max_cape:.0f} J/kg — thunderstorm risk')
    if wave_recs:
        max_hs = max((r.get('wave_height') or 0 for r in wave_recs), default=0)
        if max_hs >= 3.5: alerts.append(f'⚠️ <b>Dangerous seas</b> — Hs {max_hs:.1f}m peak')
        elif max_hs >= 2.0: alerts.append(f'🌊 Rough conditions — Hs {max_hs:.1f}m peak')
        elif max_hs >= 1.0: alerts.append(f'🌊 Moderate seas — Hs {max_hs:.1f}m')
    if alerts:
        html += ('<div style="margin:8px 0 0;padding:8px 10px;background:#2d1515;'
                 'border-left:3px solid #fc8181;font-size:0.9em;color:#fca5a5;border-radius:4px">'
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
                notes.append(f'Peak wind {"+" if pk>0 else ""}{pk:.0f}kt vs prev run')
        dp_total = sum((r.get('precip_mm_6h') or 0) - (p.get('precip_mm_6h') or 0)
                       for r, p in overlapping)
        if abs(dp_total) >= 2:
            notes.append(f'Total rain {"+" if dp_total>0 else ""}{dp_total:.1f}mm vs prev run')
        md = [r.get('mslp_hpa', 0) - p.get('mslp_hpa', 0) for r, p in overlapping
              if r.get('mslp_hpa') is not None and p.get('mslp_hpa') is not None]
        if md:
            pk_m = max(md, key=abs)
            if abs(pk_m) >= 1:
                notes.append(f'Max MSLP shift {"+" if pk_m>0 else ""}{pk_m:.1f}hPa vs prev run')
        if notes:
            html += ('<p style="margin:8px 0 0;padding:6px 10px;background:#2d2200;'
                     'border-left:3px solid #fbd38d;font-size:0.9em;color:#fbd38d;border-radius:4px">'
                     '🔄 <b>Model shift vs prev run:</b> ' + ' · '.join(notes) + '</p>\n')

    html += '</div>\n'
    return html


def render_unified_html(
    meta: dict,
    records: list,
    prev_records: list,
    ecmwf_records: list,
    wave_data: dict | None,
) -> str:
    """
    Full web-app version: daily summary cards + complete hourly table
    (WRF + ECMWF IFS + wave columns) + WRF vs ECMWF agreement stats + legend.
    render_email_html() produces the compact email-only summary.
    """
    # Build lookups (same as render_email_html)
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

    # Start with the email summary (header + daily cards + alerts + model shift),
    # then strip its closing </div> so we can append the full table.
    html = render_email_html(meta, records, prev_records, ecmwf_records, wave_data)
    if html.endswith('</div>\n'):
        html = html[:-len('</div>\n')]

    # ── Source legend ─────────────────────────────────────────────────────────
    html += (
        '<p style="margin:0 0 6px;font-size:0.82em;color:#94a3b8">'
        '<span style="background:#2c4a7c;color:#d0e0ff;padding:1px 5px;border-radius:3px">WRF 3km</span>'
        '&nbsp;'
        '<span style="background:#2d6a4f;color:#d0f0e0;padding:1px 5px;border-radius:3px">ECMWF IFS</span>'
        '&nbsp;— green <sup style="color:#68d391;font-size:0.85em">EC</sup> badge = ECMWF/GFS fills in'
        ' where CWA WRF is absent (gust, rain, cloud, vis, CAPE)'
        '</p>\n'
    )

    # ── Table ─────────────────────────────────────────────────────────────────
    html += '<div style="overflow-x:auto">\n'
    html += '<table style="border-collapse:collapse;font-size:11.5px;white-space:nowrap">\n'
    html += '<thead>\n'

    wrf_th  = 'background:#2c4a7c;color:#d0e0ff'
    ec_th   = 'background:#2d6a4f;color:#d0f0e0'
    wave_th = 'background:#1e4d7a;color:#d0e8ff'
    alrt_th = 'background:#2d3748;color:#e2e8f0'
    html += '<tr style="text-align:center;font-size:0.9em">\n'
    html += f'  <th style="padding:3px 5px;{alrt_th}" title="Per-step sailing alerts">⚠</th>\n'
    html += '  <th style="padding:4px 7px;text-align:left;background:#1a1a2e;color:#fff">UTC</th>\n'
    html += '  <th style="padding:4px 7px;text-align:left;background:#1a1a2e;color:#fff">CST +8</th>\n'
    for lbl, th, tip in [
        ('Wind (kt)', wrf_th, 'Wind speed in knots (1 kt = 1.85 km/h)'),
        ('Gust (kt)', ec_th, 'Maximum wind gust speed in knots'),
    ]:
        html += f'  <th style="padding:3px 5px;{th}" title="{tip}">{lbl}</th>\n'
    if has_wave:
        for lbl, th, tip in [
            ('Waves (m)', wave_th, 'Significant wave height in metres (combined sea state)'),
            ('Period (s)', wave_th, 'Wave period in seconds — longer = more powerful swell'),
            ('Swell (m)', wave_th, 'Swell wave height in metres (long-period waves only)'),
            ('Wave Dir', wave_th, 'Dominant wave direction — where waves come from'),
        ]:
            html += f'  <th style="padding:3px 5px;{th}" title="{tip}">{lbl}</th>\n'
    for lbl, th, tip in [
        ('Pressure', wrf_th, 'Mean sea-level pressure in hPa'),
        ('Rain 6h', ec_th, 'Precipitation accumulated over 6 hours in mm'),
        ('Vis (km)', ec_th, 'Visibility in kilometres'),
        ('Temp (°C)', wrf_th, 'Air temperature at 2m in degrees Celsius'),
        ('Cloud %', ec_th, 'Total cloud cover percentage'),
        ('CAPE', ec_th, 'Convective Available Potential Energy — thunderstorm indicator (J/kg)'),
    ]:
        html += f'  <th style="padding:3px 5px;{th}" title="{tip}">{lbl}</th>\n'
    html += '</tr>\n</thead>\n<tbody>\n'

    _n_wave_cols = 4 if has_wave else 0
    _total_cols  = 3 + 2 + _n_wave_cols + 6 + 1

    # ── Data rows ─────────────────────────────────────────────────────────────
    temp_deltas, wind_deltas, rain_deltas, mslp_deltas = [], [], [], []
    _EC_BADGE = '<sup style="color:#68d391;font-size:0.72em;line-height:1"> EC</sup>'
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
            html += (f'<tr style="background:#2d3748">'
                     f'<td colspan="{_total_cols}" style="padding:4px 10px;'
                     f'font-weight:700;color:#e2e8f0;font-size:0.88em;letter-spacing:0.03em">'
                     f'📅 {cst_date_str} (CST)</td></tr>\n')

        if not has_wrf:
            row_bg    = '#111827' if row_idx % 2 else '#0f172a'
            row_extra = 'color:#94a3b8'
        else:
            row_bg    = '#111827' if row_idx % 2 else '#0f172a'
            row_extra = 'color:#e2e8f0'

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
        _row_alerts = []
        if _eff_gust is not None and _eff_gust >= 34:
            _row_alerts.append('<span style="color:#fc8181;font-weight:700">Gale⚠</span>')
        elif _eff_gust is not None and _eff_gust >= 28:
            _row_alerts.append('<span style="color:#fbd38d">g28+</span>')
        if _eff_wind is not None and _eff_wind >= 34:
            _row_alerts.append('<span style="color:#fc8181;font-weight:700">B8+</span>')
        elif _eff_wind is not None and _eff_wind >= 28:
            _row_alerts.append('<span style="color:#fbd38d">B7</span>')
        elif _eff_wind is not None and _eff_wind >= 22:
            _row_alerts.append('<span style="color:#fbd38d">B6</span>')
        if _eff_hs is not None and _eff_hs >= 2.5:
            _row_alerts.append('<span style="color:#93c5fd">🌊⚠</span>')
        elif _eff_hs is not None and _eff_hs >= 1.5:
            _row_alerts.append('<span style="color:#93c5fd">🌊</span>')
        if _eff_rain is not None and _eff_rain >= 10:
            _row_alerts.append('<span style="color:#93c5fd">🌧</span>')
        _alert_html = '&nbsp;'.join(_row_alerts) if _row_alerts else ''
        _alert_bg   = '#2d1515' if any('⚠' in a or 'Gale' in a for a in _row_alerts) else (
                      '#2d2200' if _row_alerts else row_bg)

        html += f'<tr style="background:{row_bg};{row_extra}">\n'
        html += (f'  <td style="padding:2px 5px;text-align:center;font-size:0.85em;'
                 f'background:{_alert_bg};white-space:nowrap">{_alert_html}</td>\n')
        html += f'  <td style="padding:3px 6px;font-weight:500;white-space:nowrap">{utc_str}</td>\n'
        html += f'  <td style="padding:3px 6px;color:#94a3b8;white-space:nowrap">{cst_str}</td>\n'
        if dt_ is not None: temp_deltas.append(dt_)
        if dw_ is not None: wind_deltas.append(dw_)
        if dr_ is not None: rain_deltas.append(dr_)
        if dp_ is not None: mslp_deltas.append(dp_)

        # Wind
        if ww is not None:
            bf = _beaufort(ww)
            arrow_s = f' {_wind_arrow(wwd)}' if wwd is not None else ''
            dir_s   = f' {deg_to_compass(wwd)}' if wwd is not None else ''
            html += (f'  <td style="padding:3px 5px;text-align:center;background:{_wind_bg(ww)}">'
                     f'{ww:.0f}kt B{bf}{arrow_s}{dir_s}'
                     f'{_delta_span(ww, prev.get("wind_kt"), ".0f", "kt", True)}</td>\n')
        elif ew is not None:
            bf = _beaufort(ew)
            arrow_s = f' {_wind_arrow(ewd)}' if ewd is not None else ''
            dir_s   = f' {deg_to_compass(ewd)}' if ewd is not None else ''
            html += (f'  <td style="padding:3px 5px;text-align:center;background:{_EC_BG}">'
                     f'{ew:.0f}kt B{bf}{arrow_s}{dir_s}{_EC_BADGE}</td>\n')
        else:
            html += '  <td style="padding:3px 5px;text-align:center;color:#475569">—</td>\n'

        # Gust
        g_val = wg if wg is not None else eg
        g_ec  = (wg is None and eg is not None)
        if g_val is not None:
            badge = _EC_BADGE if g_ec else ''
            html += (f'  <td style="padding:3px 5px;text-align:center;background:{_wind_bg(g_val)}">'
                     f'{g_val:.0f}kt{badge}</td>\n')
        else:
            html += '  <td style="padding:3px 5px;text-align:center;color:#475569">—</td>\n'

        # Wave columns
        if has_wave:
            hs   = wav.get('wave_height')       if wav else None
            tp   = wav.get('wave_period')       if wav else None
            swhs = wav.get('swell_wave_height') if wav else None
            wdir = wav.get('wave_direction')    if wav else None
            html += (f'  <td style="padding:3px 5px;text-align:center;background:{_wave_height_bg(hs)}">'
                     f'{_fmt(hs)}</td>\n')
            html += (f'  <td style="padding:3px 5px;text-align:center;background:{_wave_period_bg(tp)}">'
                     f'{_fmt(tp, ".0f", "s") if tp is not None else "—"}</td>\n')
            html += (f'  <td style="padding:3px 5px;text-align:center;background:{_wave_height_bg(swhs)}">'
                     f'{_fmt(swhs)}</td>\n')
            html += (f'  <td style="padding:3px 5px;text-align:center">'
                     f'{_wave_dir_str(wdir)}</td>\n')

        # MSLP
        if wp is not None:
            html += (f'  <td style="padding:3px 5px;text-align:center">'
                     f'{wp:.1f}{_delta_span(wp, prev.get("mslp_hpa"), ".1f", "")}</td>\n')
        elif ep is not None:
            html += (f'  <td style="padding:3px 5px;text-align:center;background:{_EC_BG}">'
                     f'{ep:.1f}{_EC_BADGE}</td>\n')
        else:
            html += '  <td style="padding:3px 5px;text-align:center;color:#475569">—</td>\n'

        # 6h Rain
        r_val = wr if wr is not None else er
        r_ec  = (wr is None and er is not None)
        if r_val is not None:
            badge = _EC_BADGE if r_ec else ''
            delta = _delta_span(wr, prev.get('precip_mm_6h'), '.1f', 'mm', True) if not r_ec else ''
            html += (f'  <td style="padding:3px 5px;text-align:center;background:{_precip_bg(r_val)}">'
                     f'{r_val:.1f}mm{delta}{badge}</td>\n')
        else:
            html += '  <td style="padding:3px 5px;text-align:center;color:#475569">—</td>\n'

        # Vis
        v_val = wvs if wvs is not None else evs
        v_ec  = (wvs is None and evs is not None)
        if v_val is not None:
            bg_v = _EC_BG if v_ec else ''
            badge = _EC_BADGE if v_ec else ''
            bg_style = f';background:{bg_v}' if bg_v else ''
            html += (f'  <td style="padding:3px 5px;text-align:center{bg_style}">'
                     f'{v_val:.0f}km{badge}</td>\n')
        else:
            html += '  <td style="padding:3px 5px;text-align:center;color:#475569">—</td>\n'

        # Temp
        if wt is not None:
            html += (f'  <td style="padding:3px 5px;text-align:center;background:{_temp_bg(wt)}">'
                     f'{wt:.1f}°{_delta_span(wt, prev.get("temp_c"), ".1f", "°")}</td>\n')
        elif et is not None:
            html += (f'  <td style="padding:3px 5px;text-align:center;background:{_EC_BG}">'
                     f'{et:.1f}°{_EC_BADGE}</td>\n')
        else:
            html += '  <td style="padding:3px 5px;text-align:center;color:#475569">—</td>\n'

        # Cloud
        cl_val = wcl if wcl is not None else ecl
        cl_ec  = (wcl is None and ecl is not None)
        if cl_val is not None:
            bg_cl = _EC_BG if cl_ec else ''
            badge = _EC_BADGE if cl_ec else ''
            bg_style = f';background:{bg_cl}' if bg_cl else ''
            html += (f'  <td style="padding:3px 5px;text-align:center{bg_style}">'
                     f'{cl_val:.0f}%{badge}</td>\n')
        else:
            html += '  <td style="padding:3px 5px;text-align:center;color:#475569">—</td>\n'

        # CAPE
        cp_val = wcp if wcp is not None else ecp
        cp_ec  = (wcp is None and ecp is not None)
        if cp_val is not None:
            badge = _EC_BADGE if cp_ec else ''
            html += (f'  <td style="padding:3px 5px;text-align:center;background:{_cape_bg(cp_val)}">'
                     f'{cp_val:.0f}{badge}</td>\n')
        else:
            html += '  <td style="padding:3px 5px;text-align:center;color:#475569">—</td>\n'

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
            html += ('<div style="margin:8px 0 0;padding:8px 12px;background:#1a2744;'
                     'border-left:3px solid #93c5fd;font-size:0.9em;color:#e2e8f0;border-radius:4px">'
                     f'<b>WRF vs ECMWF</b> — {n} overlapping steps: '
                     + ' · '.join(items) + '</div>\n')

    # ── Legend ────────────────────────────────────────────────────────────────
    html += (
        '<p style="margin:8px 0 0;font-size:0.78em;color:#475569">'
        '<b>Wind (Beaufort):</b> '
        '<span style="background:#d4f0c0;padding:1px 3px">B1-3 &lt;11kt</span> '
        '<span style="background:#e8f5c0;padding:1px 3px">B4 11–16</span> '
        '<span style="background:#fff7b0;padding:1px 3px">B5 17–21 reef</span> '
        '<span style="background:#ffd9a0;padding:1px 3px">B6 22–27 reef in</span> '
        '<span style="background:#ffb080;padding:1px 3px">B7 28–33 harbour</span> '
        '<span style="background:#ff6666;color:#fff;padding:1px 3px">B8+ ≥34 gale</span>'
        '&nbsp;&nbsp;<b>Hs:</b> '
        '<span style="background:#d4f0c0;padding:1px 3px">&lt;0.3m</span> '
        '<span style="background:#fff7b0;padding:1px 3px">0.3–1m slight</span> '
        '<span style="background:#ffd9a0;padding:1px 3px">1–2m moderate</span> '
        '<span style="background:#ffb3b3;padding:1px 3px">2–3.5m rough</span> '
        '<span style="background:#ff6666;color:#fff;padding:1px 3px">&gt;3.5m dangerous</span>'
        '&nbsp;&nbsp;<b>Tp:</b> '
        '<span style="background:#fff7b0;padding:1px 3px">&lt;8s wind sea</span> '
        '<span style="background:#d4f0c0;padding:1px 3px">8–12s swell</span> '
        '<span style="background:#b0d9ff;padding:1px 3px">&gt;12s ocean swell</span>'
        '</p>\n'
        '</div>\n'
    )
    return html


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
    p.add_argument('--output-html', default='email_analysis.html',
                   help='Full web-app HTML path (default: email_analysis.html)')
    p.add_argument('--email-html', default='email_analysis_email.html',
                   help='Simple email summary HTML path (default: email_analysis_email.html)')
    p.add_argument('--ecmwf-json',  default=None,
                   help='ECMWF IFS JSON produced by ecmwf_fetch.py (enables comparison table)')
    p.add_argument('--wave-json',   default=None,
                   help='Wave JSON produced by wave_fetch.py (adds wave forecast section to email)')
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
        try:
            with open(args.prev_json) as f:
                prev_data = json.load(f)
            prev_records = prev_data.get('records', [])
            prev_init = prev_data.get('meta', {}).get('init_utc', 'unknown')
            log.info("Previous run: %s (%d records)", prev_init, len(prev_records))
        except Exception as e:
            log.warning("Could not load previous summary: %s", e)

    # ── Write JSON summary ────────────────────────────────────────────────────
    summary = {'meta': meta, 'records': records}
    out_json = Path(args.output_json)
    out_json.write_text(json.dumps(summary, indent=2))
    log.info("Summary → %s", out_json)

    # ── Load ECMWF comparison data ────────────────────────────────────────────
    ecmwf_records = []
    if args.ecmwf_json and Path(args.ecmwf_json).exists():
        try:
            with open(args.ecmwf_json) as f:
                ecmwf_data = json.load(f)
            ecmwf_records = ecmwf_data.get('records', [])
            ecmwf_init = ecmwf_data.get('meta', {}).get('init_utc', 'unknown')
            log.info("ECMWF data: %s (%d records)", ecmwf_init, len(ecmwf_records))
        except Exception as e:
            log.warning("Could not load ECMWF JSON: %s", e)

    # ── Load wave data ────────────────────────────────────────────────────────
    wave_data = None
    if args.wave_json and Path(args.wave_json).exists():
        try:
            with open(args.wave_json) as f:
                wave_data = json.load(f)
            ecmwf_wave_recs = len((wave_data.get('ecmwf_wave') or {}).get('records', []))
            cwa_wave_recs   = len((wave_data.get('cwa_wave')   or {}).get('records', []))
            log.info("Wave data: %d ECMWF steps, %d CWA steps",
                     ecmwf_wave_recs, cwa_wave_recs)
        except Exception as e:
            log.warning("Could not load wave JSON: %s", e)

    # ── Write HTML ────────────────────────────────────────────────────────────
    # Full web-app version (phone drill-down)
    html_full = render_unified_html(meta, records, prev_records, ecmwf_records, wave_data)
    out_html = Path(args.output_html)
    out_html.write_text(html_full)
    log.info("HTML (full)  → %s", out_html)

    # Simple email summary
    html_email = render_email_html(meta, records, prev_records, ecmwf_records, wave_data)
    out_email_html = Path(args.email_html)
    out_email_html.write_text(html_email)
    log.info("HTML (email) → %s", out_email_html)

    # ── Expose to GitHub Actions ──────────────────────────────────────────────
    gha = os.environ.get('GITHUB_OUTPUT')
    if gha:
        with open(gha, 'a') as f:
            f.write(f'analysis_html={out_html.resolve()}\n')
            f.write(f'analysis_json={out_json.resolve()}\n')


if __name__ == '__main__':
    setup_logging()
    main()
