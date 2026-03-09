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

KEELUNG_LAT = 25.1276
KEELUNG_LON = 121.7392

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
    # Precipitation — accumulated or 6-hourly
    (['tp', 'apcp', 'APCP', 'prate'], 'surface', None, 'precip_raw'),
    # Total cloud cover
    (['tcc', 'TCDC'], None, None,               'cloud_raw'),
    # Visibility
    (['vis', 'VIS'],  'surface', None,           'vis_m'),
    # Wind gust
    (['gust', 'fg10', 'GUST'], 'heightAboveGround', None, 'gust_ms'),
    # CAPE
    (['cape', 'CAPE'], 'surface', None,          'cape'),
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
</tr>
</thead>
<tbody>
'''

    for i, rec in enumerate(records):
        valid_utc = valid_cst = ''
        if rec.get('valid_utc'):
            dt_u = datetime.fromisoformat(rec['valid_utc'])
            dt_c = dt_u + timedelta(hours=8)
            valid_utc = dt_u.strftime('%m/%d %H:%M')
            valid_cst = dt_c.strftime('%m/%d %H:%M')

        prev = prev_by_valid.get(rec.get('valid_utc', ''), {})

        t   = rec.get('temp_c')
        w   = rec.get('wind_kt')
        wd  = rec.get('wind_dir')
        g   = rec.get('gust_kt')
        p   = rec.get('mslp_hpa')
        pr  = rec.get('precip_mm_6h')
        cl  = rec.get('cloud_pct')
        vis = rec.get('vis_km')

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
</p>
</div>
'''
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

    # ── Write HTML ────────────────────────────────────────────────────────────
    html = render_html(meta, records, prev_records)
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
