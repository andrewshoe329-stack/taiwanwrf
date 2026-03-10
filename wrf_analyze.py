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

# Maps raw key → (display unit, conversion function)
DERIVED = {
    'temp_c':    ('°C',  lambda d: d['temp_k'] - 273.15),
    'wind_kt':   ('kt',  lambda d: math.sqrt(d['u10']**2 + d['v10']**2) * 1.94384),
    'wind_dir':  ('°',   lambda d: (270 - math.degrees(math.atan2(d['v10'], d['u10']))) % 360),
    'mslp_hpa':  ('hPa', lambda d: d['mslp_pa'] / 100),
    'precip_mm': ('mm',  lambda d: d['precip_raw'] * 1000
                                   if d['precip_raw'] < 100 else d['precip_raw']),
    'cloud_pct': ('%',   lambda d: d['cloud_raw'] * 100
                                   if d['cloud_raw'] <= 1.01 else d['cloud_raw']),
    'vis_km':    ('km',  lambda d: d['vis_m'] / 1000),
    'gust_kt':   ('kt',  lambda d: d['gust_ms'] * 1.94384),
    'cape':      ('J/kg',lambda d: d['cape']),
}

COMPASS = ['N','NNE','NE','ENE','E','ESE','SE','SSE','S','SSW','SW','WSW','W','WNW','NW','NNW']


def deg_to_compass(deg: float) -> str:
    return COMPASS[round(deg / 22.5) % 16]


# ── Grid helpers ──────────────────────────────────────────────────────────────

def nearest_idx(lats2d, lons2d, lat, lon):
    dist = np.sqrt((lats2d - lat) ** 2 + (lons2d - lon) ** 2)
    return np.unravel_index(dist.argmin(), dist.shape)


# ── GRIB2 reading ─────────────────────────────────────────────────────────────

def list_vars(grib_path: Path) -> None:
    """Print all unique (shortName, typeOfLevel, level) found in a GRIB2 file."""
    import eccodes as ec
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
                    print(f"  shortName={key[0]:<10}  typeOfLevel={key[1]:<25}  level={key[2]}")
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
                raw[matched_key] = float(vals[j, i])

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


def render_html(meta: dict, records: list, prev_records: list) -> str:
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


def render_comparison_html(wrf_records: list, ecmwf_records: list) -> str:
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


def render_wave_html(wave_data: dict) -> str:
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


def _render_cwa_ecmwf_wave_comparison(ecmwf_recs: list, cwa: dict) -> str:
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
        print(f'\nVariables in {grbs[0].name}:\n')
        list_vars(grbs[0])
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
    html = render_html(meta, records, prev_records)
    if ecmwf_records:
        html += render_comparison_html(records, ecmwf_records)
    if wave_data:
        html += render_wave_html(wave_data)
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
