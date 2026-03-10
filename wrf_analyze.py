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
import math
import os
import re
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone

import numpy as np

# ── Target point ─────────────────────────────────────────────────────────────

KEELUNG_LAT = 25.15589534977208
KEELUNG_LON = 121.78782946186699

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

COMPASS = ['N','NNE','NE','ENE','E','ESE','SE','SSE','S','SSW','SW','WSW','W','WNW','NW','NNW']

# Unicode arrows showing the direction the wind is blowing TOWARD
# (opposite of the "from" direction stored in the GRIB2 wind_dir field).
# 0° = FROM North → blows southward → ↓, 90° = FROM East → blows west → ←, etc.
_WIND_ARROWS = ['↓', '↙', '←', '↖', '↑', '↗', '→', '↘']


def deg_to_compass(deg: float) -> str:
    return COMPASS[round(deg / 22.5) % 16]


def _wind_arrow(deg: float) -> str:
    """Return a single Unicode arrow for the direction the wind is blowing toward."""
    return _WIND_ARROWS[round(deg / 45) % 8]


def _fmt(v, fmt='.1f', unit=''):
    """Format *v* with the given format spec and unit suffix, or return '—'."""
    return f'{v:{fmt}}{unit}' if v is not None else '—'


# ── Grid helpers ──────────────────────────────────────────────────────────────

def nearest_idx(lats2d, lons2d, lat, lon):
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
                except Exception:
                    pid = '?'
                key = (sn, tol, lev)
                if key not in seen:
                    seen.add(key)
                    print(f"  shortName={sn:<12}  typeOfLevel={tol:<25}  level={lev:<6}  paramId={pid}")
            except Exception:
                pass
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
                        except Exception:
                            pass
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
                    except Exception:
                        # Units key unavailable: fall back to a conservative
                        # heuristic — only convert if value looks like metres
                        # (i.e. plausibly < 0.5 m of rain in 6 h).
                        if 0 < val < 0.5:
                            val *= 1000.0

                raw[matched_key] = val

            except Exception:
                pass
            finally:
                ec.codes_release(msg)

    return raw


# ── Forecast extraction ───────────────────────────────────────────────────────

def _parse_init_time(dirname: str):
    """Extract init datetime from directory name like M-A0064_20260309_00UTC."""
    m = re.search(r'(\d{8})_(\d{2})UTC', dirname)
    if not m:
        return None
    return datetime.strptime(m.group(1) + m.group(2), '%Y%m%d%H').replace(tzinfo=timezone.utc)


def extract_forecast(rundir: Path) -> tuple:
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

        print(f"    Extracting F{fh:03d} …", flush=True)
        raw = read_point(grb, KEELUNG_LAT, KEELUNG_LON)
        if not raw:
            print(f"    ⚠  No variables extracted from {grb.name}")
            continue

        rec: dict = {
            'fh':        fh,
            'valid_utc': valid_time.isoformat() if valid_time else None,
        }

        for key, (unit, fn) in DERIVED.items():
            try:
                needed_raw_keys = {
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
                if all(k in raw for k in needed_raw_keys.get(key, [])):
                    val = fn(raw)
                    rec[key] = round(val, 2) if val is not None else None
                else:
                    rec[key] = None
            except Exception:
                rec[key] = None

        # Convert accumulated precip to 6-hourly incremental
        if rec.get('precip_mm') is not None and prev_precip_mm is not None:
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

def _temp_bg(t):
    if t is None:  return '#eee'
    if t < 10:     return '#b3d9ff'
    if t < 18:     return '#d4f0c0'
    if t < 24:     return '#fff7b0'
    if t < 29:     return '#ffd9a0'
    return '#ffb3b3'

def _wind_bg(w):
    if w is None:  return '#f4f4f4'
    if w < 10:     return '#d4f0c0'
    if w < 20:     return '#fff7b0'
    if w < 30:     return '#ffd9a0'
    if w < 40:     return '#ffb3b3'
    return '#ff6666'

def _precip_bg(p):
    if p is None or p < 0.1: return '#f8f8f8'
    if p < 2:    return '#d4f0c0'
    if p < 10:   return '#b0d9ff'
    if p < 25:   return '#6cb0ff'
    return '#3070dd'

def _cape_bg(c):
    if c is None:  return '#f4f4f4'
    if c < 100:    return '#d4f0c0'   # stable
    if c < 500:    return '#fff7b0'   # slightly unstable
    if c < 1500:   return '#ffd9a0'   # moderately unstable
    return '#ffb3b3'                   # very unstable (thunderstorm risk)

def _wave_height_bg(h):
    """Background colour for significant wave height (metres)."""
    if h is None: return '#f4f4f4'
    if h < 0.3:   return '#d4f0c0'   # glassy / rippled
    if h < 1.0:   return '#fff7b0'   # slight
    if h < 2.0:   return '#ffd9a0'   # moderate
    if h < 3.5:   return '#ffb3b3'   # rough / very rough
    return '#ff6666'                  # high / dangerous

def _wave_period_bg(p):
    """Background colour for wave period (seconds)."""
    if p is None: return '#f4f4f4'
    if p < 4:     return '#f4f4f4'   # very short (local chop)
    if p < 8:     return '#fff7b0'   # moderate wind sea
    if p < 12:    return '#d4f0c0'   # longer period swell
    return '#b0d9ff'                  # long-period ocean swell

def _delta_span(curr, prev, fmt='.1f', unit='', positive_bad=False):
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


def _render_html_DEPRECATED(meta: dict, records: list, prev_records: list) -> str:  # noqa
    # DEAD CODE — kept only as reference; not called by main().
    init_str = ''
    if meta.get('init_utc'):
        dt = datetime.fromisoformat(meta['init_utc'])
        init_str = dt.strftime('%Y-%m-%d %H:%M UTC')

    # Index previous records by valid_utc for O(1) lookup
    prev_by_valid: dict[str, dict] = {
        r['valid_utc']: r for r in (prev_records or []) if r.get('valid_utc')
    }
    has_prev = bool(prev_by_valid)

    # ── Table ─────────────────────────────────────────────────────────────────
    html = f'''<div style="font-family:Arial,sans-serif;font-size:13px;line-height:1.4">
<h3 style="margin:0 0 2px;font-size:15px">
  📍 Keelung Point Forecast
  <span style="font-weight:normal;font-size:0.85em;color:#555">
    &nbsp;{KEELUNG_LAT}°N {KEELUNG_LON}°E
  </span>
</h3>
<p style="margin:0 0 8px;color:#666;font-size:0.88em">
  {meta.get("model_id","?")} · Init: {init_str}
  {"· <i>Δ vs prev run shown in brackets</i>" if has_prev else ""}
</p>

<table style="border-collapse:collapse;width:100%;font-size:12px">
<thead>
<tr style="background:#1a365d;color:#fff;text-align:center">
  <th style="padding:5px 6px;text-align:left">Valid UTC</th>
  <th style="padding:5px 6px;text-align:left">CST +8</th>
  <th style="padding:5px 6px">Temp</th>
  <th style="padding:5px 6px">Wind</th>
  <th style="padding:5px 6px">Gusts</th>
  <th style="padding:5px 6px">MSLP</th>
  <th style="padding:5px 6px">6h Rain</th>
  <th style="padding:5px 6px">Cloud</th>
  <th style="padding:5px 6px">Vis</th>
  <th style="padding:5px 6px">CAPE</th>
</tr>
</thead>
<tbody>
'''

    for i, rec in enumerate(records):
        valid_utc = valid_cst = ''
        if rec.get('valid_utc'):
            dt_u = datetime.fromisoformat(rec['valid_utc'])
            dt_c = dt_u + timedelta(hours=8)
            valid_utc = dt_u.strftime('%a %m/%d %H:%M')
            valid_cst = dt_c.strftime('%a %m/%d %H:%M')

        prev = prev_by_valid.get(rec.get('valid_utc', ''), {})

        t    = rec.get('temp_c')
        w    = rec.get('wind_kt')
        wd   = rec.get('wind_dir')
        g    = rec.get('gust_kt')
        p    = rec.get('mslp_hpa')
        pr   = rec.get('precip_mm_6h')
        cl   = rec.get('cloud_pct')
        vis  = rec.get('vis_km')
        cape = rec.get('cape')

        wind_str = ''
        if w is not None:
            dir_str = f' {deg_to_compass(wd)}' if wd is not None else ''
            wind_str = f'{w:.0f}kt{dir_str}'

        row_bg = '#f5f7fa' if i % 2 else '#ffffff'

        html += f'''<tr style="background:{row_bg}">
  <td style="padding:4px 6px;white-space:nowrap;font-weight:500">{valid_utc or f"F{rec['fh']:03d}"}</td>
  <td style="padding:4px 6px;white-space:nowrap;color:#666">{valid_cst}</td>
  <td style="padding:4px 6px;text-align:center;background:{_temp_bg(t)}">{f"{t:.1f}°C" if t is not None else "—"}{_delta_span(t, prev.get("temp_c"), ".1f", "°")}</td>
  <td style="padding:4px 6px;text-align:center;background:{_wind_bg(w)}">{wind_str or "—"}{_delta_span(w, prev.get("wind_kt"), ".0f", "kt", positive_bad=True)}</td>
  <td style="padding:4px 6px;text-align:center;background:{_wind_bg(g)}">{f"{g:.0f}kt" if g is not None else "—"}</td>
  <td style="padding:4px 6px;text-align:center">{f"{p:.1f}" if p is not None else "—"}{_delta_span(p, prev.get("mslp_hpa"), ".1f", "")}</td>
  <td style="padding:4px 6px;text-align:center;background:{_precip_bg(pr)}">{f"{pr:.1f}mm" if pr is not None else "—"}{_delta_span(pr, prev.get("precip_mm_6h"), ".1f", "mm", positive_bad=True)}</td>
  <td style="padding:4px 6px;text-align:center">{f"{cl:.0f}%" if cl is not None else "—"}</td>
  <td style="padding:4px 6px;text-align:center">{f"{vis:.0f}km" if vis is not None else "—"}</td>
  <td style="padding:4px 6px;text-align:center;background:{_cape_bg(cape)}">{f"{cape:.0f}" if cape is not None else "—"}</td>
</tr>
'''

    html += '</tbody></table>\n'

    # ── Notable changes summary ────────────────────────────────────────────────
    if has_prev:
        overlapping = [
            (r, prev_by_valid[r['valid_utc']])
            for r in records
            if r.get('valid_utc') in prev_by_valid
        ]
        notes = []

        wind_deltas = [
            r.get('wind_kt', 0) - p.get('wind_kt', 0)
            for r, p in overlapping
            if r.get('wind_kt') is not None and p.get('wind_kt') is not None
        ]
        if wind_deltas:
            peak = max(wind_deltas, key=abs)
            if abs(peak) >= 3:
                notes.append(f'Peak wind {"+" if peak>0 else ""}{peak:.0f}kt vs prev run')

        precip_deltas = [
            (r.get('precip_mm_6h') or 0) - (p.get('precip_mm_6h') or 0)
            for r, p in overlapping
        ]
        total_Δp = sum(precip_deltas)
        if abs(total_Δp) >= 2:
            notes.append(f'Total rain {"+" if total_Δp>0 else ""}{total_Δp:.1f}mm vs prev run')

        mslp_deltas = [
            r.get('mslp_hpa', 0) - p.get('mslp_hpa', 0)
            for r, p in overlapping
            if r.get('mslp_hpa') is not None and p.get('mslp_hpa') is not None
        ]
        if mslp_deltas:
            peak_mslp = max(mslp_deltas, key=abs)
            if abs(peak_mslp) >= 1:
                notes.append(f'Max MSLP shift {"+" if peak_mslp>0 else ""}{peak_mslp:.1f}hPa vs prev run')

        if notes:
            html += (
                '<p style="margin:8px 0 0;padding:6px 10px;background:#fffbeb;'
                'border-left:3px solid #d69e2e;font-size:0.9em">'
                '🔄 <b>Model shift vs prev run:</b> ' + ' · '.join(notes) +
                '</p>\n'
            )

    # ── Alert thresholds ──────────────────────────────────────────────────────
    alerts = []
    max_wind = max((r.get('wind_kt') or 0 for r in records), default=0)
    max_gust = max((r.get('gust_kt') or 0 for r in records), default=0)
    total_rain = sum(r.get('precip_mm_6h') or 0 for r in records)
    min_mslp = min((r.get('mslp_hpa') or 9999 for r in records), default=9999)
    max_cape  = max((r.get('cape') or 0 for r in records), default=0)

    if max_wind >= 34:
        alerts.append(f'⚠️ <b>Gale-force winds</b> forecast — {max_wind:.0f}kt peak')
    elif max_wind >= 22:
        alerts.append(f'💨 Strong winds expected — {max_wind:.0f}kt peak')
    if max_gust >= 40:
        alerts.append(f'⚠️ <b>Gusts to {max_gust:.0f}kt</b>')
    if total_rain >= 50:
        alerts.append(f'🌧️ <b>Heavy rain</b> — {total_rain:.0f}mm over 84h')
    elif total_rain >= 15:
        alerts.append(f'🌦️ Moderate rain — {total_rain:.0f}mm over 84h')
    if min_mslp <= 985:
        alerts.append(f'🌀 <b>Low MSLP {min_mslp:.0f}hPa</b> — possible tropical influence')
    if max_cape >= 1000:
        alerts.append(f'⛈️ High instability — CAPE {max_cape:.0f} J/kg')

    if alerts:
        html += (
            '<div style="margin:8px 0 0;padding:8px 10px;background:#fff5f5;'
            'border-left:3px solid #e53e3e;font-size:0.9em">'
            + '<br>'.join(alerts) +
            '</div>\n'
        )

    # ── Color legend ──────────────────────────────────────────────────────────
    html += '''<p style="margin:8px 0 0;font-size:0.78em;color:#888">
Wind scale:
<span style="background:#d4f0c0;padding:1px 4px">&lt;10kt</span>&nbsp;
<span style="background:#fff7b0;padding:1px 4px">10–20kt</span>&nbsp;
<span style="background:#ffd9a0;padding:1px 4px">20–30kt</span>&nbsp;
<span style="background:#ffb3b3;padding:1px 4px">30–40kt</span>&nbsp;
<span style="background:#ff6666;color:#fff;padding:1px 4px">&gt;40kt</span>
&nbsp;&nbsp;
CAPE (J/kg):
<span style="background:#d4f0c0;padding:1px 4px">&lt;100</span>&nbsp;
<span style="background:#fff7b0;padding:1px 4px">100–500</span>&nbsp;
<span style="background:#ffd9a0;padding:1px 4px">500–1500</span>&nbsp;
<span style="background:#ffb3b3;padding:1px 4px">&gt;1500</span>
</p>
</div>
'''
    return html


# ── WRF vs ECMWF comparison ───────────────────────────────────────────────────

def _delta_cell(d, thresh, positive_bad=False):
    """Return a <td> element color-coded by disagreement magnitude."""
    if d is None:
        return '<td style="padding:4px 5px;text-align:center;color:#aaa">—</td>'
    abs_d = abs(d)
    if abs_d < thresh * 0.5:
        bg, color = '#c6f6d5', '#276749'   # green  – good agreement
    elif abs_d < thresh:
        bg, color = '#fefcbf', '#744210'   # yellow – moderate
    else:
        bg, color = '#fed7d7', '#9b2335'   # red    – large disagreement
    sign = '+' if d > 0 else ''
    return (f'<td style="padding:4px 5px;text-align:center;background:{bg};'
            f'color:{color};font-weight:500">{sign}{d}</td>')


def _render_comparison_html_DEPRECATED(wrf_records: list, ecmwf_records: list) -> str:  # noqa
    # DEAD CODE — not called by main().  Superseded by render_unified_html().
    """
    Side-by-side WRF vs ECMWF IFS comparison table.
    Aligns rows by valid_utc.  Appended after the main WRF table in the email.
    """
    if not wrf_records or not ecmwf_records:
        return ('<div style="font-family:Arial,sans-serif;font-size:13px;'
                'color:#888;margin-top:12px">'
                '<i>No ECMWF data available for comparison.</i></div>\n')

    ec_by_valid = {r['valid_utc']: r for r in ecmwf_records if r.get('valid_utc')}
    paired = [
        (r, ec_by_valid[r['valid_utc']])
        for r in wrf_records
        if r.get('valid_utc') and r['valid_utc'] in ec_by_valid
    ]

    if not paired:
        return ('<div style="font-family:Arial,sans-serif;font-size:13px;'
                'color:#888;margin-top:12px">'
                '<i>No overlapping time steps between WRF and ECMWF.</i></div>\n')

    html = '''<div style="font-family:Arial,sans-serif;font-size:13px;line-height:1.4;margin-top:20px">
<h3 style="margin:0 0 2px;font-size:15px">
  📊 WRF vs ECMWF IFS Comparison
  <span style="font-weight:normal;font-size:0.85em;color:#555">
    &nbsp;{lat}°N {lon}°E
  </span>
</h3>
<p style="margin:0 0 8px;color:#666;font-size:0.88em">
  WRF CWA-3 km vs ECMWF IFS 0.25° &nbsp;·&nbsp; Δ&nbsp;=&nbsp;WRF&nbsp;−&nbsp;ECMWF
</p>

<table style="border-collapse:collapse;width:100%;font-size:12px">
<thead>
<tr style="background:#2d3748;color:#fff;text-align:center">
  <th style="padding:5px 6px;text-align:left" rowspan="2">Valid UTC</th>
  <th style="padding:5px 6px;text-align:left" rowspan="2">CST +8</th>
  <th colspan="3" style="padding:4px 6px;border-bottom:1px solid #4a5568">Temp (°C)</th>
  <th colspan="3" style="padding:4px 6px;border-bottom:1px solid #4a5568">Wind (kt)</th>
  <th colspan="3" style="padding:4px 6px;border-bottom:1px solid #4a5568">6h Rain (mm)</th>
  <th colspan="3" style="padding:4px 6px;border-bottom:1px solid #4a5568">MSLP (hPa)</th>
</tr>
<tr style="background:#4a5568;color:#e2e8f0;text-align:center">
  <th style="padding:3px 5px">WRF</th><th style="padding:3px 5px">EC</th><th style="padding:3px 5px">Δ</th>
  <th style="padding:3px 5px">WRF</th><th style="padding:3px 5px">EC</th><th style="padding:3px 5px">Δ</th>
  <th style="padding:3px 5px">WRF</th><th style="padding:3px 5px">EC</th><th style="padding:3px 5px">Δ</th>
  <th style="padding:3px 5px">WRF</th><th style="padding:3px 5px">EC</th><th style="padding:3px 5px">Δ</th>
</tr>
</thead>
<tbody>
'''.format(lat=KEELUNG_LAT, lon=KEELUNG_LON)

    temp_deltas, wind_deltas, rain_deltas, mslp_deltas = [], [], [], []

    def _fmt(v, fmt, unit=''):
        return f'{v:{fmt}}{unit}' if v is not None else '—'

    for i, (wrf, ec) in enumerate(paired):
        valid_utc = valid_cst = ''
        if wrf.get('valid_utc'):
            dt_u = datetime.fromisoformat(wrf['valid_utc'])
            dt_c = dt_u + timedelta(hours=8)
            valid_utc = dt_u.strftime('%a %m/%d %H:%M')
            valid_cst = dt_c.strftime('%a %m/%d %H:%M')

        row_bg = '#f5f7fa' if i % 2 else '#ffffff'

        wt = wrf.get('temp_c');       et = ec.get('temp_c')
        ww = wrf.get('wind_kt');      ew = ec.get('wind_kt')
        wr = wrf.get('precip_mm_6h'); er = ec.get('precip_mm_6h')
        wp = wrf.get('mslp_hpa');     ep = ec.get('mslp_hpa')

        dt = round(wt - et, 1) if wt is not None and et is not None else None
        dw = round(ww - ew, 1) if ww is not None and ew is not None else None
        dr = round(wr - er, 1) if wr is not None and er is not None else None
        dp = round(wp - ep, 1) if wp is not None and ep is not None else None

        if dt is not None: temp_deltas.append(dt)
        if dw is not None: wind_deltas.append(dw)
        if dr is not None: rain_deltas.append(dr)
        if dp is not None: mslp_deltas.append(dp)

        html += (
            f'<tr style="background:{row_bg}">\n'
            f'  <td style="padding:4px 6px;white-space:nowrap;font-weight:500">{valid_utc}</td>\n'
            f'  <td style="padding:4px 6px;white-space:nowrap;color:#666">{valid_cst}</td>\n'
            f'  <td style="padding:4px 5px;text-align:center;background:{_temp_bg(wt)}">{_fmt(wt,".1f","°")}</td>\n'
            f'  <td style="padding:4px 5px;text-align:center;background:{_temp_bg(et)}">{_fmt(et,".1f","°")}</td>\n'
            f'  {_delta_cell(dt, 2.0)}\n'
            f'  <td style="padding:4px 5px;text-align:center;background:{_wind_bg(ww)}">{_fmt(ww,".0f","kt")}</td>\n'
            f'  <td style="padding:4px 5px;text-align:center;background:{_wind_bg(ew)}">{_fmt(ew,".0f","kt")}</td>\n'
            f'  {_delta_cell(dw, 5.0, positive_bad=True)}\n'
            f'  <td style="padding:4px 5px;text-align:center;background:{_precip_bg(wr)}">{_fmt(wr,".1f","mm")}</td>\n'
            f'  <td style="padding:4px 5px;text-align:center;background:{_precip_bg(er)}">{_fmt(er,".1f","mm")}</td>\n'
            f'  {_delta_cell(dr, 5.0, positive_bad=True)}\n'
            f'  <td style="padding:4px 5px;text-align:center">{_fmt(wp,".1f")}</td>\n'
            f'  <td style="padding:4px 5px;text-align:center">{_fmt(ep,".1f")}</td>\n'
            f'  {_delta_cell(dp, 3.0)}\n'
            f'</tr>\n'
        )

    # ── ECMWF-only rows beyond WRF range (extended 7-day outlook) ────────────
    wrf_valids = {r['valid_utc'] for r in wrf_records if r.get('valid_utc')}
    ecmwf_only = sorted(
        [r for r in ecmwf_records if r.get('valid_utc') and r['valid_utc'] not in wrf_valids],
        key=lambda r: r['valid_utc'],
    )
    if ecmwf_only:
        html += (
            '<tr><td colspan="14" style="padding:3px 6px;background:#e2e8f0;'
            'color:#4a5568;font-size:0.82em;text-align:center;font-style:italic">'
            '— ECMWF extended outlook (beyond WRF range) —</td></tr>\n'
        )
        for j, ec in enumerate(ecmwf_only):
            valid_utc = valid_cst = ''
            if ec.get('valid_utc'):
                dt_u = datetime.fromisoformat(ec['valid_utc'])
                dt_c = dt_u + timedelta(hours=8)
                valid_utc = dt_u.strftime('%a %m/%d %H:%M')
                valid_cst = dt_c.strftime('%a %m/%d %H:%M')
            row_bg = '#f0f4ff' if j % 2 else '#f8f9ff'
            et = ec.get('temp_c');       ew = ec.get('wind_kt')
            er = ec.get('precip_mm_6h'); ep = ec.get('mslp_hpa')
            html += (
                f'<tr style="background:{row_bg};color:#555">\n'
                f'  <td style="padding:4px 6px;white-space:nowrap;font-weight:500">{valid_utc}</td>\n'
                f'  <td style="padding:4px 6px;white-space:nowrap;color:#666">{valid_cst}</td>\n'
                f'  <td style="padding:4px 5px;text-align:center;color:#bbb">—</td>\n'
                f'  <td style="padding:4px 5px;text-align:center;background:{_temp_bg(et)}">{_fmt(et,".1f","°")}</td>\n'
                f'  <td style="padding:4px 5px;text-align:center;color:#bbb">—</td>\n'
                f'  <td style="padding:4px 5px;text-align:center;color:#bbb">—</td>\n'
                f'  <td style="padding:4px 5px;text-align:center;background:{_wind_bg(ew)}">{_fmt(ew,".0f","kt")}</td>\n'
                f'  <td style="padding:4px 5px;text-align:center;color:#bbb">—</td>\n'
                f'  <td style="padding:4px 5px;text-align:center;color:#bbb">—</td>\n'
                f'  <td style="padding:4px 5px;text-align:center;background:{_precip_bg(er)}">{_fmt(er,".1f","mm")}</td>\n'
                f'  <td style="padding:4px 5px;text-align:center;color:#bbb">—</td>\n'
                f'  <td style="padding:4px 5px;text-align:center">{_fmt(ep,".1f")}</td>\n'
                f'  <td style="padding:4px 5px;text-align:center;color:#bbb">—</td>\n'
                f'</tr>\n'
            )

    html += '</tbody></table>\n'

    # ── Agreement summary (WRF overlap period only) ───────────────────────────
    def _mae(deltas):
        return sum(abs(d) for d in deltas) / len(deltas) if deltas else None

    def _bias(deltas):
        return sum(deltas) / len(deltas) if deltas else None

    items = []
    for label, deltas, unit, thresh in [
        ('Temp', temp_deltas, '°C',  2.0),
        ('Wind', wind_deltas, 'kt',  5.0),
        ('Rain', rain_deltas, 'mm',  5.0),
        ('MSLP', mslp_deltas, 'hPa', 3.0),
    ]:
        mae  = _mae(deltas)
        bias = _bias(deltas)
        if mae is not None:
            icon = '🟢' if mae < thresh * 0.5 else ('🟡' if mae < thresh else '🔴')
            sign = '+' if bias > 0 else ''
            items.append(f'{icon} <b>{label}</b> MAE&nbsp;{mae:.1f}{unit}'
                         f' (bias&nbsp;{sign}{bias:.1f}{unit})')

    if items:
        html += (
            '<div style="margin:10px 0 0;padding:8px 12px;background:#ebf8ff;'
            'border-left:3px solid #3182ce;font-size:0.9em">'
            f'<b>Model Agreement</b> — WRF vs ECMWF over {len(paired)} steps:<br>'
            + ' &nbsp;·&nbsp; '.join(items) +
            '</div>\n'
        )

    # ── Delta legend ──────────────────────────────────────────────────────────
    html += (
        '<p style="margin:6px 0 0;font-size:0.78em;color:#888">'
        'Δ shading: '
        '<span style="background:#c6f6d5;color:#276749;padding:1px 4px">good agreement</span>'
        '&nbsp;'
        '<span style="background:#fefcbf;color:#744210;padding:1px 4px">moderate</span>'
        '&nbsp;'
        '<span style="background:#fed7d7;color:#9b2335;padding:1px 4px">large</span>'
        '</p>\n'
        '</div>\n'
    )
    return html


# ── Wave forecast rendering ───────────────────────────────────────────────────

_WAVE_COMPASS = ['N','NNE','NE','ENE','E','ESE','SE','SSE',
                 'S','SSW','SW','WSW','W','WNW','NW','NNW']

def _wave_dir_str(deg):
    if deg is None:
        return '—'
    return _WAVE_COMPASS[round(deg / 22.5) % 16]


def _render_wave_html_DEPRECATED(wave_data: dict) -> str:  # noqa
    # DEAD CODE — not called by main().  Superseded by render_unified_html().
    """
    Render the wave-forecast section from wave_keelung.json.
    wave_data keys: 'ecmwf_wave' (always), 'cwa_wave' (may be None).
    """
    ecmwf = wave_data.get('ecmwf_wave', {})
    cwa   = wave_data.get('cwa_wave')

    ecmwf_recs = ecmwf.get('records', [])
    ecmwf_meta = ecmwf.get('meta', {})

    if not ecmwf_recs:
        return ('<div style="font-family:Arial,sans-serif;font-size:13px;'
                'color:#888;margin-top:12px">'
                '<i>No wave data available.</i></div>\n')

    init_str = ''
    if ecmwf_meta.get('init_utc'):
        try:
            dt = datetime.fromisoformat(ecmwf_meta['init_utc'])
            init_str = dt.strftime('%Y-%m-%d %H:%M UTC')
        except Exception:
            init_str = ecmwf_meta['init_utc']

    # ── ECMWF wave forecast table ──────────────────────────────────────────────
    html = (
        '<div style="font-family:Arial,sans-serif;font-size:13px;line-height:1.4;margin-top:20px">\n'
        '<h3 style="margin:0 0 2px;font-size:15px">\n'
        '  🌊 Wave Forecast\n'
        f'  <span style="font-weight:normal;font-size:0.85em;color:#555">'
        f'&nbsp;{KEELUNG_LAT}°N {KEELUNG_LON}°E</span>\n'
        '</h3>\n'
        f'<p style="margin:0 0 8px;color:#666;font-size:0.88em">'
        f'ECMWF WAM (Open-Meteo marine) &nbsp;·&nbsp; Init: {init_str}</p>\n'
        '\n'
        '<table style="border-collapse:collapse;width:100%;font-size:12px">\n'
        '<thead>\n'
        '<tr style="background:#1a5276;color:#fff;text-align:center">\n'
        '  <th style="padding:5px 6px;text-align:left">Valid UTC</th>\n'
        '  <th style="padding:5px 6px;text-align:left">CST +8</th>\n'
        '  <th style="padding:5px 6px">Hs (m)</th>\n'
        '  <th style="padding:5px 6px">T (s)</th>\n'
        '  <th style="padding:5px 6px">Dir</th>\n'
        '  <th style="padding:5px 6px">Swell Hs</th>\n'
        '  <th style="padding:5px 6px">Swell T</th>\n'
        '  <th style="padding:5px 6px">Swell Dir</th>\n'
        '  <th style="padding:5px 6px">Wind Sea</th>\n'
        '</tr>\n'
        '</thead>\n'
        '<tbody>\n'
    )

    max_hs   = 0.0
    max_swell = 0.0

    for i, rec in enumerate(ecmwf_recs):
        valid_utc = valid_cst = ''
        if rec.get('valid_utc'):
            try:
                dt_u = datetime.fromisoformat(rec['valid_utc'])
                dt_c = dt_u + timedelta(hours=8)
                valid_utc = dt_u.strftime('%a %m/%d %H:%M')
                valid_cst = dt_c.strftime('%a %m/%d %H:%M')
            except Exception:
                pass

        hs   = rec.get('wave_height')
        tp   = rec.get('wave_period')
        wdir = rec.get('wave_direction')
        swh  = rec.get('swell_wave_height')
        swt  = rec.get('swell_wave_period')
        swd  = rec.get('swell_wave_direction')
        wwh  = rec.get('wind_wave_height')

        if hs  is not None: max_hs    = max(max_hs,    hs)
        if swh is not None: max_swell = max(max_swell, swh)

        row_bg = '#f5f7fa' if i % 2 else '#ffffff'

        def _fmt(v, decimals=1, suffix=''):
            return f'{v:.{decimals}f}{suffix}' if v is not None else '—'

        html += (
            f'<tr style="background:{row_bg}">\n'
            f'  <td style="padding:4px 6px;white-space:nowrap;font-weight:500">{valid_utc}</td>\n'
            f'  <td style="padding:4px 6px;white-space:nowrap;color:#666">{valid_cst}</td>\n'
            f'  <td style="padding:4px 6px;text-align:center;background:{_wave_height_bg(hs)}">{_fmt(hs)}</td>\n'
            f'  <td style="padding:4px 6px;text-align:center;background:{_wave_period_bg(tp)}">{_fmt(tp)}</td>\n'
            f'  <td style="padding:4px 6px;text-align:center">{_wave_dir_str(wdir)}</td>\n'
            f'  <td style="padding:4px 6px;text-align:center;background:{_wave_height_bg(swh)}">{_fmt(swh)}</td>\n'
            f'  <td style="padding:4px 6px;text-align:center;background:{_wave_period_bg(swt)}">{_fmt(swt)}</td>\n'
            f'  <td style="padding:4px 6px;text-align:center">{_wave_dir_str(swd)}</td>\n'
            f'  <td style="padding:4px 6px;text-align:center;background:{_wave_height_bg(wwh)}">{_fmt(wwh)}</td>\n'
            f'</tr>\n'
        )

    html += '</tbody></table>\n'

    # ── Wave alerts ────────────────────────────────────────────────────────────
    wave_alerts = []
    if max_hs >= 3.5:
        wave_alerts.append(f'⚠️ <b>Dangerous sea state</b> — Hs {max_hs:.1f}m peak')
    elif max_hs >= 2.0:
        wave_alerts.append(f'🌊 Rough conditions expected — Hs {max_hs:.1f}m peak')
    if max_swell >= 1.5:
        wave_alerts.append(f'🌀 Significant swell — {max_swell:.1f}m peak swell height')

    if wave_alerts:
        html += (
            '<div style="margin:8px 0 0;padding:8px 10px;background:#ebf8ff;'
            'border-left:3px solid #2b6cb0;font-size:0.9em">'
            + '<br>'.join(wave_alerts) +
            '</div>\n'
        )

    # ── Wave legend ────────────────────────────────────────────────────────────
    html += (
        '<p style="margin:8px 0 0;font-size:0.78em;color:#888">'
        'Hs: '
        '<span style="background:#d4f0c0;padding:1px 4px">&lt;0.3m calm</span>&nbsp;'
        '<span style="background:#fff7b0;padding:1px 4px">0.3–1m slight</span>&nbsp;'
        '<span style="background:#ffd9a0;padding:1px 4px">1–2m moderate</span>&nbsp;'
        '<span style="background:#ffb3b3;padding:1px 4px">2–3.5m rough</span>&nbsp;'
        '<span style="background:#ff6666;color:#fff;padding:1px 4px">&gt;3.5m high</span>'
        '&nbsp;&nbsp;'
        'Period: '
        '<span style="background:#fff7b0;padding:1px 4px">4–8s wind sea</span>&nbsp;'
        '<span style="background:#d4f0c0;padding:1px 4px">8–12s swell</span>&nbsp;'
        '<span style="background:#b0d9ff;padding:1px 4px">&gt;12s long swell</span>'
        '</p>\n'
    )

    # ── CWA vs ECMWF wave comparison ──────────────────────────────────────────
    if cwa and cwa.get('records'):
        html += _render_cwa_ecmwf_wave_comparison(ecmwf_recs, cwa)

    html += '</div>\n'
    return html


def _render_cwa_ecmwf_wave_comparison_DEPRECATED(ecmwf_recs: list, cwa: dict) -> str:  # noqa
    # DEAD CODE — not called by main().  CWA has no public wave model.
    """Side-by-side CWA wave model vs ECMWF WAM comparison."""
    cwa_recs = cwa.get('records', [])
    cwa_meta = cwa.get('meta', {})
    if not cwa_recs:
        return ''

    ec_by_valid = {r['valid_utc']: r for r in ecmwf_recs if r.get('valid_utc')}
    paired = [
        (cwa_r, ec_by_valid[cwa_r['valid_utc']])
        for cwa_r in cwa_recs
        if cwa_r.get('valid_utc') and cwa_r['valid_utc'] in ec_by_valid
    ]
    if not paired:
        return ''

    cwa_model_id = cwa_meta.get('model_id', 'CWA-Wave')

    html = (
        '<div style="margin-top:20px">\n'
        '<h3 style="margin:0 0 2px;font-size:15px">\n'
        f'  📊 {cwa_model_id} vs ECMWF WAM — Wave Comparison\n'
        f'  <span style="font-weight:normal;font-size:0.85em;color:#555">'
        f'&nbsp;{KEELUNG_LAT}°N {KEELUNG_LON}°E</span>\n'
        '</h3>\n'
        '<p style="margin:0 0 8px;color:#666;font-size:0.88em">'
        f'{cwa_model_id} (3–15km) vs ECMWF WAM (0.25°) &nbsp;·&nbsp; '
        'Δ&nbsp;=&nbsp;CWA&nbsp;−&nbsp;ECMWF</p>\n'
        '\n'
        '<table style="border-collapse:collapse;width:100%;font-size:12px">\n'
        '<thead>\n'
        '<tr style="background:#2d3748;color:#fff;text-align:center">\n'
        '  <th style="padding:5px 6px;text-align:left" rowspan="2">Valid UTC</th>\n'
        '  <th style="padding:5px 6px;text-align:left" rowspan="2">CST +8</th>\n'
        '  <th colspan="3" style="padding:4px 6px;border-bottom:1px solid #4a5568">Hs (m)</th>\n'
        '  <th colspan="3" style="padding:4px 6px;border-bottom:1px solid #4a5568">Period (s)</th>\n'
        '  <th colspan="3" style="padding:4px 6px;border-bottom:1px solid #4a5568">Swell Hs (m)</th>\n'
        '</tr>\n'
        '<tr style="background:#4a5568;color:#e2e8f0;text-align:center">\n'
        '  <th style="padding:3px 5px">CWA</th><th style="padding:3px 5px">EC</th>'
        '<th style="padding:3px 5px">Δ</th>\n'
        '  <th style="padding:3px 5px">CWA</th><th style="padding:3px 5px">EC</th>'
        '<th style="padding:3px 5px">Δ</th>\n'
        '  <th style="padding:3px 5px">CWA</th><th style="padding:3px 5px">EC</th>'
        '<th style="padding:3px 5px">Δ</th>\n'
        '</tr>\n'
        '</thead>\n'
        '<tbody>\n'
    )

    hs_deltas, tp_deltas, sw_deltas = [], [], []

    def _fmtw(v, dec=1, suf=''):
        return f'{v:.{dec}f}{suf}' if v is not None else '—'

    for i, (cwa_r, ec_r) in enumerate(paired):
        valid_utc = valid_cst = ''
        if cwa_r.get('valid_utc'):
            try:
                dt_u = datetime.fromisoformat(cwa_r['valid_utc'])
                dt_c = dt_u + timedelta(hours=8)
                valid_utc = dt_u.strftime('%a %m/%d %H:%M')
                valid_cst = dt_c.strftime('%a %m/%d %H:%M')
            except Exception:
                pass

        row_bg = '#f5f7fa' if i % 2 else '#ffffff'

        ch = cwa_r.get('wave_height');      eh = ec_r.get('wave_height')
        ct = cwa_r.get('wave_period');      et = ec_r.get('wave_period')
        cs = cwa_r.get('swell_wave_height'); es = ec_r.get('swell_wave_height')

        dh = round(ch - eh, 2) if ch is not None and eh is not None else None
        dt_ = round(ct - et, 1) if ct is not None and et is not None else None
        ds = round(cs - es, 2) if cs is not None and es is not None else None

        if dh  is not None: hs_deltas.append(dh)
        if dt_ is not None: tp_deltas.append(dt_)
        if ds  is not None: sw_deltas.append(ds)

        html += (
            f'<tr style="background:{row_bg}">\n'
            f'  <td style="padding:4px 6px;white-space:nowrap;font-weight:500">{valid_utc}</td>\n'
            f'  <td style="padding:4px 6px;white-space:nowrap;color:#666">{valid_cst}</td>\n'
            f'  <td style="padding:4px 5px;text-align:center;background:{_wave_height_bg(ch)}">{_fmtw(ch)}</td>\n'
            f'  <td style="padding:4px 5px;text-align:center;background:{_wave_height_bg(eh)}">{_fmtw(eh)}</td>\n'
            f'  {_delta_cell(dh, 0.5)}\n'
            f'  <td style="padding:4px 5px;text-align:center;background:{_wave_period_bg(ct)}">{_fmtw(ct)}</td>\n'
            f'  <td style="padding:4px 5px;text-align:center;background:{_wave_period_bg(et)}">{_fmtw(et)}</td>\n'
            f'  {_delta_cell(dt_, 2.0)}\n'
            f'  <td style="padding:4px 5px;text-align:center;background:{_wave_height_bg(cs)}">{_fmtw(cs)}</td>\n'
            f'  <td style="padding:4px 5px;text-align:center;background:{_wave_height_bg(es)}">{_fmtw(es)}</td>\n'
            f'  {_delta_cell(ds, 0.5)}\n'
            f'</tr>\n'
        )

    html += '</tbody></table>\n'

    # Summary
    def _mae(d): return sum(abs(x) for x in d) / len(d) if d else None
    def _bias(d): return sum(d) / len(d) if d else None

    items = []
    for label, deltas, unit, thresh in [
        ('Hs',     hs_deltas, 'm',  0.5),
        ('Period', tp_deltas, 's',  2.0),
        ('Swell',  sw_deltas, 'm',  0.5),
    ]:
        mae  = _mae(deltas)
        bias = _bias(deltas)
        if mae is not None:
            icon = '🟢' if mae < thresh * 0.5 else ('🟡' if mae < thresh else '🔴')
            sign = '+' if bias > 0 else ''
            items.append(f'{icon} <b>{label}</b> MAE&nbsp;{mae:.2f}{unit}'
                         f' (bias&nbsp;{sign}{bias:.2f}{unit})')

    if items:
        html += (
            '<div style="margin:10px 0 0;padding:8px 12px;background:#ebf8ff;'
            'border-left:3px solid #3182ce;font-size:0.9em">'
            f'<b>Wave Model Agreement</b> — CWA vs ECMWF over {len(paired)} steps:<br>'
            + ' &nbsp;·&nbsp; '.join(items) +
            '</div>\n'
        )

    html += (
        '<p style="margin:6px 0 0;font-size:0.78em;color:#888">'
        'Δ shading: '
        '<span style="background:#c6f6d5;color:#276749;padding:1px 4px">good agreement</span>'
        '&nbsp;'
        '<span style="background:#fefcbf;color:#744210;padding:1px 4px">moderate</span>'
        '&nbsp;'
        '<span style="background:#fed7d7;color:#9b2335;padding:1px 4px">large</span>'
        '</p>\n'
        '</div>\n'
    )
    return html


# ── Daily summary cards ───────────────────────────────────────────────────────

def _daily_summary_html(
    wrf_by_valid: dict,
    ec_by_valid:  dict,
    wave_by_valid: dict,
    all_valids: list,
) -> str:
    """
    Compact day-by-day summary cards (one per CST calendar day).
    Uses WRF data where available; falls back to ECMWF for extended days.
    Shows: condition icon, temp range, max wind + direction, total rain,
           peak wave height, and the data source tag.
    """
    from collections import defaultdict

    # Group all valid times by CST date string  (e.g. "2026-03-11")
    day_buckets: dict[str, list] = defaultdict(list)
    for vt in all_valids:
        try:
            cst_date = (datetime.fromisoformat(vt) + timedelta(hours=8)).strftime('%Y-%m-%d')
            day_buckets[cst_date].append(vt)
        except Exception:
            pass

    if not day_buckets:
        return ''

    def _condition_emoji(max_wind, total_rain, max_cape, max_hs, max_gust=None):
        if max_hs is not None and max_hs >= 3.5:
            return '🌊'
        if max_cape is not None and max_cape >= 500:
            return '⛈️'
        if total_rain >= 15:
            return '🌧️'
        if total_rain >= 3:
            return '🌦️'
        # Gusts ≥ 34 kt (gale) → strong wind icon regardless of mean
        if max_gust is not None and max_gust >= 34:
            return '💨'
        if max_wind is not None and max_wind >= 25:
            return '💨'
        if max_wind is not None and max_wind >= 15:
            return '🌬️'
        return '🌤️'

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

            # Pick atmospheric source: WRF preferred
            atm = wrf if wrf else ec
            if atm:
                tag = 'WRF' if wrf else 'EC'
                source_tags.add(tag)
                if atm.get('temp_c')       is not None: temps.append(atm['temp_c'])
                if atm.get('wind_kt')      is not None:
                    winds.append(atm['wind_kt'])
                    if atm.get('wind_dir') is not None: wind_dirs.append((atm['wind_kt'], atm['wind_dir']))
                if atm.get('gust_kt')      is not None: gusts.append(atm['gust_kt'])
                if atm.get('precip_mm_6h') is not None: rains.append(atm['precip_mm_6h'])
                if atm.get('cape')         is not None: capes.append(atm['cape'])

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

        # Format day label
        try:
            day_label = datetime.strptime(cst_date, '%Y-%m-%d').strftime('%a %-m/%-d')
        except Exception:
            day_label = cst_date

        # Source badge colours
        src_label = '+'.join(sorted(source_tags, reverse=True))   # WRF+EC or WRF or EC
        src_bg    = '#1a365d' if 'WRF' in source_tags else '#276749'
        src_color = '#fff'

        # Temp background for the card accent
        card_border = _temp_bg(t_max) if t_max is not None else '#e2e8f0'

        temp_str = f'{t_min:.0f}–{t_max:.0f}°C' if t_min is not None and t_max is not None else '—'

        # Wind: mean + direction arrow + compass; gust shown when notably higher
        if max_wind is not None:
            arrow_bit = f' {peak_arrow}' if peak_arrow else ''
            gust_bit  = (f' (g{max_gust:.0f})' if max_gust is not None
                         and max_gust >= max_wind * 1.15 and max_gust >= max_wind + 3
                         else '')
            wind_str  = f'{max_wind:.0f}kt{arrow_bit}{peak_dir_s}{gust_bit}'
        else:
            wind_str  = '—'

        rain_str = f'{total_r:.0f}mm' if total_r > 0 else 'dry'
        wave_str = f'Hs {max_hs_v:.1f}m' if max_hs_v is not None else ''

        # CAPE indicator: ⚡ badge when convective potential is elevated
        cape_badge = ''
        if max_cape is not None and max_cape >= 500:
            cape_level = '⚡⚡' if max_cape >= 1500 else '⚡'
            cape_badge = (
                f'  <div style="color:#b7600a;font-size:0.85em">'
                f'{cape_level} CAPE {max_cape:.0f} J/kg</div>\n'
            )

        cards_html += (
            f'<div style="border:1px solid #ddd;border-top:3px solid {card_border};'
            f'border-radius:5px;padding:7px 10px;min-width:115px;background:#fafafa;'
            f'font-size:12px;line-height:1.5">\n'
            f'  <div style="font-weight:600;color:#333;font-size:0.95em">'
            f'{day_label}&nbsp;<span style="font-size:1.1em">{cond_icon}</span></div>\n'
            f'  <div style="color:#555">🌡️ {temp_str}</div>\n'
            f'  <div style="color:#555">💨 {wind_str}</div>\n'
            f'  <div style="color:#555">🌧️ {rain_str}</div>\n'
            + (f'  <div style="color:#555">🌊 {wave_str}</div>\n' if wave_str else '')
            + cape_badge
            + f'  <div style="margin-top:4px">'
            f'<span style="background:{src_bg};color:{src_color};font-size:0.72em;'
            f'padding:1px 5px;border-radius:3px">{src_label}</span></div>\n'
            f'</div>\n'
        )

    cards_html += '</div>\n'
    return cards_html


# ── Unified table (all sources, JS-togglable column groups) ──────────────────

def render_unified_html(
    meta: dict,
    records: list,
    prev_records: list,
    ecmwf_records: list,
    wave_data: dict | None,
) -> str:
    """
    Single wide table combining WRF, ECMWF IFS, and Wave data.

    Column groups (each togglable via JS buttons):
      grp-wrf   — 8 WRF atmospheric columns (Temp Wind Gust MSLP Rain Cloud Vis CAPE)
      grp-ec    — 4 ECMWF IFS columns       (Temp Wind Rain MSLP)
      grp-delta — 4 Δ WRF−ECMWF columns    (ΔT ΔW ΔR ΔP)
      grp-wave  — 7 ECMWF WAM wave columns  (Hs T Dir SwHs SwT SwDir WSea)

    Rows are aligned by valid_utc.  Steps where WRF has no data (ECMWF-only,
    beyond the ~84 h WRF range) are shown with blue-tinted background.
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
        except Exception:
            pass

    # ── Helper: add CSS class to a _delta_cell() output string ───────────────
    def _dc(d, thresh, positive_bad=False, cls='grp-delta'):
        return _delta_cell(d, thresh, positive_bad).replace('<td ', f'<td class="{cls}" ', 1)

    # ═════════════════════════════════════════════════════════════════════════
    # HTML construction starts here
    # ═════════════════════════════════════════════════════════════════════════
    html = (
        '<div style="font-family:Arial,sans-serif;font-size:13px;line-height:1.4">\n'
        '<h3 style="margin:0 0 2px;font-size:15px">\n'
        f'  🌏 Keelung Unified Forecast\n'
        f'  <span style="font-weight:normal;font-size:0.85em;color:#555">'
        f'&nbsp;{KEELUNG_LAT}°N {KEELUNG_LON}°E</span>\n'
        '</h3>\n'
        f'<p style="margin:0 0 4px;color:#666;font-size:0.88em">'
        f'{meta.get("model_id","?")} · WRF Init: {init_str}{wave_init_str}'
        f'{"&nbsp;·&nbsp; <i>Δ vs prev WRF run in brackets</i>" if has_prev else ""}'
        '</p>\n\n'
    )

    # ── Daily summary cards ───────────────────────────────────────────────────
    html += _daily_summary_html(wrf_by_valid, ec_by_valid, wave_by_valid, all_valids)

    # ── JavaScript toggle ────────────────────────────────────────────────────
    html += (
        '<script>\n'
        'function toggleGrp(cls){\n'
        '  var els=document.querySelectorAll("."+cls);\n'
        '  var hide=els.length&&els[0].style.display!=="none";\n'
        '  for(var i=0;i<els.length;i++) els[i].style.display=hide?"none":"";\n'
        '  var b=document.getElementById("btn-"+cls);\n'
        '  if(b) b.style.opacity=hide?"0.4":"1";\n'
        '}\n'
        '</script>\n'
    )

    # ── Toggle buttons ────────────────────────────────────────────────────────
    btn_base = ('display:inline-block;padding:3px 10px;border:1px solid;'
                'border-radius:4px;cursor:pointer;font-size:0.82em;background:#fff')
    html += '<div style="margin:0 0 8px;display:flex;flex-wrap:wrap;gap:6px;align-items:center">\n'
    html += '<span style="font-size:0.82em;color:#666">Toggle columns:</span>\n'
    html += (f'<button id="btn-grp-wrf" onclick="toggleGrp(\'grp-wrf\')" '
             f'style="{btn_base};border-color:#1a365d;color:#1a365d">🔵 WRF</button>\n')
    if has_ec:
        html += (f'<button id="btn-grp-ec" onclick="toggleGrp(\'grp-ec\')" '
                 f'style="{btn_base};border-color:#276749;color:#276749">🟢 ECMWF</button>\n')
        html += (f'<button id="btn-grp-delta" onclick="toggleGrp(\'grp-delta\')" '
                 f'style="{btn_base};border-color:#744210;color:#744210">Δ Diff</button>\n')
    if has_wave:
        html += (f'<button id="btn-grp-wave" onclick="toggleGrp(\'grp-wave\')" '
                 f'style="{btn_base};border-color:#1a5276;color:#1a5276">🌊 Wave</button>\n')
    html += '</div>\n\n'

    # ── Table ─────────────────────────────────────────────────────────────────
    html += '<div style="overflow-x:auto">\n'
    html += '<table style="border-collapse:collapse;font-size:11.5px;white-space:nowrap">\n'
    html += '<thead>\n'

    # Header row 1 — group labels
    html += '<tr style="background:#1a1a2e;color:#fff;text-align:center">\n'
    html += ('  <th rowspan="2" style="padding:4px 6px;text-align:left">Valid UTC</th>\n'
             '  <th rowspan="2" style="padding:4px 6px;text-align:left">CST +8</th>\n')
    html += ('  <th colspan="8" class="grp-wrf" style="padding:4px 8px;background:#1a365d;'
             'border-left:2px solid #4a5568;border-right:2px solid #4a5568">'
             'WRF Forecast (3km)</th>\n')
    if has_ec:
        html += ('  <th colspan="4" class="grp-ec" style="padding:4px 8px;background:#276749;'
                 'border-right:2px solid #4a5568">ECMWF IFS</th>\n')
        html += ('  <th colspan="4" class="grp-delta" style="padding:4px 8px;background:#744210;'
                 'border-right:2px solid #4a5568">Δ WRF−EC</th>\n')
    if has_wave:
        html += ('  <th colspan="7" class="grp-wave" style="padding:4px 8px;background:#1a5276">'
                 'Wave (ECMWF WAM)</th>\n')
    html += '</tr>\n'

    # Header row 2 — sub-labels
    wrf_th   = 'background:#2c4a7c;color:#d0e0ff'
    ec_th    = 'background:#2d6a4f;color:#d0f0e0'
    delta_th = 'background:#8b5e2f;color:#fff8ee'
    wave_th  = 'background:#1e4d7a;color:#d0e8ff'
    html += '<tr style="text-align:center;font-size:0.9em">\n'
    for lbl in ['Temp', 'Wind', 'Gust', 'MSLP', '6hRain', 'Cloud', 'Vis', 'CAPE']:
        html += f'  <th class="grp-wrf" style="padding:3px 4px;{wrf_th}">{lbl}</th>\n'
    if has_ec:
        for lbl in ['Temp', 'Wind', '6hRain', 'MSLP']:
            html += f'  <th class="grp-ec" style="padding:3px 4px;{ec_th}">{lbl}</th>\n'
        for lbl in ['ΔT°', 'ΔW', 'ΔR', 'ΔP']:
            html += f'  <th class="grp-delta" style="padding:3px 4px;{delta_th}">{lbl}</th>\n'
    if has_wave:
        for lbl in ['Hs m', 'T s', 'Dir', 'SwHs', 'SwT', 'SwDir', 'WSea']:
            html += f'  <th class="grp-wave" style="padding:3px 4px;{wave_th}">{lbl}</th>\n'
    html += '</tr>\n'
    html += '</thead>\n<tbody>\n'

    # ── Data rows ─────────────────────────────────────────────────────────────
    temp_deltas, wind_deltas, rain_deltas, mslp_deltas = [], [], [], []

    for row_idx, vt in enumerate(all_valids):
        wrf  = wrf_by_valid.get(vt)
        ec   = ec_by_valid.get(vt)
        wav  = wave_by_valid.get(vt)
        prev = prev_by_valid.get(vt, {})

        has_wrf = wrf is not None

        try:
            dt_u = datetime.fromisoformat(vt)
            dt_c = dt_u + timedelta(hours=8)
            utc_str = dt_u.strftime('%a %m/%d %H:%M')
            cst_str = dt_c.strftime('%a %m/%d %H:%M')
        except Exception:
            utc_str, cst_str = vt, ''

        # Row background: blue-tinted for ECMWF-only rows, white/grey for WRF rows
        if not has_wrf:
            row_bg    = '#f0f4ff' if row_idx % 2 else '#f8f9ff'
            row_extra = 'color:#556'
        else:
            row_bg    = '#f5f7fa' if row_idx % 2 else '#ffffff'
            row_extra = ''

        html += f'<tr style="background:{row_bg};{row_extra}">\n'
        html += f'  <td style="padding:3px 6px;font-weight:500">{utc_str}</td>\n'
        html += f'  <td style="padding:3px 6px;color:#666">{cst_str}</td>\n'

        # ── WRF cells ─────────────────────────────────────────────────────────
        if has_wrf:
            wt  = wrf.get('temp_c')
            ww  = wrf.get('wind_kt')
            wwd = wrf.get('wind_dir')
            wg  = wrf.get('gust_kt')
            wp  = wrf.get('mslp_hpa')
            wr  = wrf.get('precip_mm_6h')
            wcl = wrf.get('cloud_pct')
            wvs = wrf.get('vis_km')
            wcp = wrf.get('cape')

            dir_s  = f' {deg_to_compass(wwd)}' if wwd is not None else ''
            wind_s = f'{ww:.0f}kt{dir_s}' if ww is not None else '—'

            html += (f'  <td class="grp-wrf" style="padding:3px 5px;text-align:center;background:{_temp_bg(wt)}">'
                     f'{_fmt(wt,".1f","°")}{_delta_span(wt, prev.get("temp_c"), ".1f", "°")}</td>\n')
            html += (f'  <td class="grp-wrf" style="padding:3px 5px;text-align:center;background:{_wind_bg(ww)}">'
                     f'{wind_s}{_delta_span(ww, prev.get("wind_kt"), ".0f", "kt", True)}</td>\n')
            html += (f'  <td class="grp-wrf" style="padding:3px 5px;text-align:center;background:{_wind_bg(wg)}">'
                     f'{_fmt(wg,".0f","kt")}</td>\n')
            html += (f'  <td class="grp-wrf" style="padding:3px 5px;text-align:center">'
                     f'{_fmt(wp,".1f")}{_delta_span(wp, prev.get("mslp_hpa"), ".1f", "")}</td>\n')
            html += (f'  <td class="grp-wrf" style="padding:3px 5px;text-align:center;background:{_precip_bg(wr)}">'
                     f'{_fmt(wr,".1f","mm")}{_delta_span(wr, prev.get("precip_mm_6h"), ".1f", "mm", True)}</td>\n')
            html += (f'  <td class="grp-wrf" style="padding:3px 5px;text-align:center">'
                     f'{_fmt(wcl,".0f","%")}</td>\n')
            html += (f'  <td class="grp-wrf" style="padding:3px 5px;text-align:center">'
                     f'{_fmt(wvs,".0f","km")}</td>\n')
            html += (f'  <td class="grp-wrf" style="padding:3px 5px;text-align:center;background:{_cape_bg(wcp)}">'
                     f'{_fmt(wcp,".0f")}</td>\n')
        else:
            # ECMWF-extended row: WRF columns blank
            for _ in range(8):
                html += '  <td class="grp-wrf" style="padding:3px 5px;text-align:center;color:#bbb">—</td>\n'

        # ── ECMWF cells ───────────────────────────────────────────────────────
        if has_ec:
            et = ec.get('temp_c')       if ec else None
            ew = ec.get('wind_kt')      if ec else None
            er = ec.get('precip_mm_6h') if ec else None
            ep = ec.get('mslp_hpa')     if ec else None

            html += (f'  <td class="grp-ec" style="padding:3px 5px;text-align:center;background:{_temp_bg(et)}">'
                     f'{_fmt(et,".1f","°")}</td>\n')
            html += (f'  <td class="grp-ec" style="padding:3px 5px;text-align:center;background:{_wind_bg(ew)}">'
                     f'{_fmt(ew,".0f","kt")}</td>\n')
            html += (f'  <td class="grp-ec" style="padding:3px 5px;text-align:center;background:{_precip_bg(er)}">'
                     f'{_fmt(er,".1f","mm")}</td>\n')
            html += (f'  <td class="grp-ec" style="padding:3px 5px;text-align:center">'
                     f'{_fmt(ep,".1f")}</td>\n')

            # Delta cells (WRF − ECMWF; blank for ECMWF-only rows)
            dt_ = round(wt - et, 1) if has_wrf and wt is not None and et is not None else None
            dw_ = round(ww - ew, 1) if has_wrf and ww is not None and ew is not None else None
            dr_ = round(wr - er, 1) if has_wrf and wr is not None and er is not None else None
            dp_ = round(wp - ep, 1) if has_wrf and wp is not None and ep is not None else None

            if dt_ is not None: temp_deltas.append(dt_)
            if dw_ is not None: wind_deltas.append(dw_)
            if dr_ is not None: rain_deltas.append(dr_)
            if dp_ is not None: mslp_deltas.append(dp_)

            html += f'  {_dc(dt_, 2.0)}\n'
            html += f'  {_dc(dw_, 5.0, True)}\n'
            html += f'  {_dc(dr_, 5.0, True)}\n'
            html += f'  {_dc(dp_, 3.0)}\n'

        # ── Wave cells ────────────────────────────────────────────────────────
        if has_wave:
            hs   = wav.get('wave_height')          if wav else None
            tp_  = wav.get('wave_period')          if wav else None
            wdir = wav.get('wave_direction')       if wav else None
            swh  = wav.get('swell_wave_height')    if wav else None
            swt  = wav.get('swell_wave_period')    if wav else None
            swd  = wav.get('swell_wave_direction') if wav else None
            wwh  = wav.get('wind_wave_height')     if wav else None

            html += (f'  <td class="grp-wave" style="padding:3px 5px;text-align:center;background:{_wave_height_bg(hs)}">'
                     f'{_fmt(hs)}</td>\n')
            html += (f'  <td class="grp-wave" style="padding:3px 5px;text-align:center;background:{_wave_period_bg(tp_)}">'
                     f'{_fmt(tp_)}</td>\n')
            html += (f'  <td class="grp-wave" style="padding:3px 5px;text-align:center">'
                     f'{_wave_dir_str(wdir)}</td>\n')
            html += (f'  <td class="grp-wave" style="padding:3px 5px;text-align:center;background:{_wave_height_bg(swh)}">'
                     f'{_fmt(swh)}</td>\n')
            html += (f'  <td class="grp-wave" style="padding:3px 5px;text-align:center;background:{_wave_period_bg(swt)}">'
                     f'{_fmt(swt)}</td>\n')
            html += (f'  <td class="grp-wave" style="padding:3px 5px;text-align:center">'
                     f'{_wave_dir_str(swd)}</td>\n')
            html += (f'  <td class="grp-wave" style="padding:3px 5px;text-align:center;background:{_wave_height_bg(wwh)}">'
                     f'{_fmt(wwh)}</td>\n')

        html += '</tr>\n'

    html += '</tbody></table>\n</div>\n'

    # ── Alerts ────────────────────────────────────────────────────────────────
    alerts = []
    if records:
        max_wind   = max((r.get('wind_kt')      or 0 for r in records), default=0)
        max_gust   = max((r.get('gust_kt')      or 0 for r in records), default=0)
        total_rain = sum( r.get('precip_mm_6h') or 0 for r in records)
        min_mslp   = min((r.get('mslp_hpa')     or 9999 for r in records), default=9999)
        max_cape   = max((r.get('cape')          or 0 for r in records), default=0)
        if max_wind  >= 34: alerts.append(f'⚠️ <b>Gale-force winds</b> — {max_wind:.0f}kt peak')
        elif max_wind >= 22: alerts.append(f'💨 Strong winds — {max_wind:.0f}kt peak')
        if max_gust  >= 40: alerts.append(f'⚠️ <b>Gusts to {max_gust:.0f}kt</b>')
        if total_rain >= 50: alerts.append(f'🌧️ <b>Heavy rain</b> — {total_rain:.0f}mm total')
        elif total_rain >= 15: alerts.append(f'🌦️ Moderate rain — {total_rain:.0f}mm total')
        if min_mslp  <= 985: alerts.append(f'🌀 <b>Low MSLP {min_mslp:.0f}hPa</b> — possible tropical influence')
        if max_cape  >= 1000: alerts.append(f'⛈️ High instability — CAPE {max_cape:.0f} J/kg')
    if wave_recs:
        max_hs = max((r.get('wave_height') or 0 for r in wave_recs), default=0)
        if max_hs >= 3.5: alerts.append(f'⚠️ <b>Dangerous seas</b> — Hs {max_hs:.1f}m peak')
        elif max_hs >= 2.0: alerts.append(f'🌊 Rough conditions — Hs {max_hs:.1f}m peak')
    if alerts:
        html += ('<div style="margin:8px 0 0;padding:8px 10px;background:#fff5f5;'
                 'border-left:3px solid #e53e3e;font-size:0.9em">'
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
            html += ('<p style="margin:8px 0 0;padding:6px 10px;background:#fffbeb;'
                     'border-left:3px solid #d69e2e;font-size:0.9em">'
                     '🔄 <b>Model shift vs prev run:</b> ' + ' · '.join(notes) + '</p>\n')

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
            html += ('<div style="margin:8px 0 0;padding:8px 12px;background:#ebf8ff;'
                     'border-left:3px solid #3182ce;font-size:0.9em">'
                     f'<b>WRF vs ECMWF</b> — {n} overlapping steps: '
                     + ' · '.join(items) + '</div>\n')

    # ── Legend ────────────────────────────────────────────────────────────────
    html += (
        '<p style="margin:8px 0 0;font-size:0.78em;color:#888">'
        'Wind: '
        '<span style="background:#d4f0c0;padding:1px 3px">&lt;10kt</span> '
        '<span style="background:#fff7b0;padding:1px 3px">10–20</span> '
        '<span style="background:#ffd9a0;padding:1px 3px">20–30</span> '
        '<span style="background:#ffb3b3;padding:1px 3px">30–40</span> '
        '<span style="background:#ff6666;color:#fff;padding:1px 3px">&gt;40</span>'
        '&nbsp; Hs: '
        '<span style="background:#d4f0c0;padding:1px 3px">&lt;0.3m</span> '
        '<span style="background:#fff7b0;padding:1px 3px">0.3–1m</span> '
        '<span style="background:#ffd9a0;padding:1px 3px">1–2m</span> '
        '<span style="background:#ffb3b3;padding:1px 3px">2–3.5m</span> '
        '<span style="background:#ff6666;color:#fff;padding:1px 3px">&gt;3.5m</span>'
        '&nbsp; Δ shading: '
        '<span style="background:#c6f6d5;color:#276749;padding:1px 3px">good</span> '
        '<span style="background:#fefcbf;color:#744210;padding:1px 3px">moderate</span> '
        '<span style="background:#fed7d7;color:#9b2335;padding:1px 3px">large</span>'
        '</p>\n'
        '</div>\n'
    )
    return html


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
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
                   help='Output HTML path (default: email_analysis.html)')
    p.add_argument('--ecmwf-json',  default=None,
                   help='ECMWF IFS JSON produced by ecmwf_fetch.py (enables comparison table)')
    p.add_argument('--wave-json',   default=None,
                   help='Wave JSON produced by wave_fetch.py (adds wave forecast section to email)')
    p.add_argument('--list-vars',   action='store_true',
                   help='Diagnostic: list all GRIB2 shortNames in the first file and exit')
    args = p.parse_args()

    rundir = Path(args.rundir)
    if not rundir.exists():
        print(f'ERROR: --rundir {rundir} does not exist', file=sys.stderr)
        sys.exit(1)

    # ── Diagnostic mode ───────────────────────────────────────────────────────
    if args.list_vars:
        grbs = sorted(rundir.glob('*_keelung*.grb2'))
        if not grbs:
            print('No *_keelung*.grb2 files found.')
            sys.exit(1)
        # f000 = init analysis — has pressure levels, 2m/10m, MSLP, but NOT
        # accumulated fields (precip, cloud, gusts, CAPE).
        print(f'\n=== {grbs[0].name} (f000 — init/analysis hour) ===\n')
        list_vars(grbs[0])
        # f006 (or next available) — first forecast hour where accumulated
        # fields (precip, cloud cover, gusts, CAPE) should appear.
        if len(grbs) > 1:
            print(f'\n=== {grbs[1].name} (first forecast hour — check for new vars) ===\n')
            list_vars(grbs[1])
        return

    # ── Main analysis ─────────────────────────────────────────────────────────
    print(f'\n  Analyzing GRIB2 files in {rundir} …')
    meta, records = extract_forecast(rundir)

    if not records:
        print('  ⚠  No records extracted. Run with --list-vars to diagnose available fields.')
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
            print(f'  Previous run: {prev_init} ({len(prev_records)} records)')
        except Exception as e:
            print(f'  ⚠  Could not load previous summary: {e}')

    # ── Write JSON summary ────────────────────────────────────────────────────
    summary = {'meta': meta, 'records': records}
    out_json = Path(args.output_json)
    out_json.write_text(json.dumps(summary, indent=2))
    print(f'  📊  Summary → {out_json}')

    # ── Load ECMWF comparison data ────────────────────────────────────────────
    ecmwf_records = []
    if args.ecmwf_json and Path(args.ecmwf_json).exists():
        try:
            with open(args.ecmwf_json) as f:
                ecmwf_data = json.load(f)
            ecmwf_records = ecmwf_data.get('records', [])
            ecmwf_init = ecmwf_data.get('meta', {}).get('init_utc', 'unknown')
            print(f'  ECMWF data: {ecmwf_init} ({len(ecmwf_records)} records)')
        except Exception as e:
            print(f'  ⚠  Could not load ECMWF JSON: {e}')

    # ── Load wave data ────────────────────────────────────────────────────────
    wave_data = None
    if args.wave_json and Path(args.wave_json).exists():
        try:
            with open(args.wave_json) as f:
                wave_data = json.load(f)
            ecmwf_wave_recs = len((wave_data.get('ecmwf_wave') or {}).get('records', []))
            cwa_wave_recs   = len((wave_data.get('cwa_wave')   or {}).get('records', []))
            print(f'  Wave data: {ecmwf_wave_recs} ECMWF steps, '
                  f'{cwa_wave_recs} CWA steps')
        except Exception as e:
            print(f'  ⚠  Could not load wave JSON: {e}')

    # ── Write HTML ────────────────────────────────────────────────────────────
    html = render_unified_html(meta, records, prev_records, ecmwf_records, wave_data)
    out_html = Path(args.output_html)
    out_html.write_text(html)
    print(f'  📧  HTML    → {out_html}')

    # ── Expose to GitHub Actions ──────────────────────────────────────────────
    gha = os.environ.get('GITHUB_OUTPUT')
    if gha:
        with open(gha, 'a') as f:
            f.write(f'analysis_html={out_html.resolve()}\n')
            f.write(f'analysis_json={out_json.resolve()}\n')


if __name__ == '__main__':
    main()
