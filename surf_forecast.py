#!/usr/bin/env python3
"""
surf_forecast.py — Taiwan surf spot 7-day forecast
Fetches ECMWF + GFS wind/gust and ECMWF WAM swell data for each spot,
evaluates conditions against each spot's optimal wind/swell directions,
and writes surf_forecast.html for appending to the email report.

Usage:
    python3 surf_forecast.py [--output surf_forecast.html]
"""

import argparse, json, sys, time, urllib.request, urllib.parse
from datetime import datetime, timezone, timedelta

# ── Surf spots ─────────────────────────────────────────────────────────────
# opt_wind  : directions that are offshore / light & favourable
# opt_swell : directions the spot is best exposed to
# Source: swelleye.com spot guides

SPOTS = [
    {
        'id': 'fulong',
        'name': 'Fulong 福隆',
        'lat': 25.019, 'lon': 121.940,
        'facing': 'NE/E',
        'opt_wind':  ['S', 'SW'],
        'opt_swell': ['N', 'NE', 'E'],
        'desc': 'Rivermouth beach break · L&R · All levels',
    },
    {
        'id': 'greenbay',
        'name': 'Green Bay 翡翠灣',
        'lat': 25.189, 'lon': 121.686,
        'facing': 'NE',
        'opt_wind':  ['W', 'SW'],
        'opt_swell': ['E', 'NE'],
        'desc': 'Beach break · L&R · All levels',
    },
    {
        'id': 'jinshan',
        'name': 'Jinshan 金山',
        'lat': 25.238, 'lon': 121.638,
        'facing': 'NE',
        'opt_wind':  ['S', 'SW'],
        'opt_swell': ['N', 'NNE', 'NE', 'E', 'ESE'],
        'desc': 'Beach/point · L&R · Mid tide · Beg–Inter',
    },
    {
        'id': 'daxi',
        'name': 'Daxi 大溪',
        'lat': 24.870, 'lon': 121.930,
        'facing': 'SE',
        'opt_wind':  ['NW', 'W'],
        'opt_swell': ['SE', 'SSE', 'S', 'E'],
        'desc': 'Half-moon beach break · L&R · Mid-high tide · Beg–Inter',
    },
    {
        'id': 'wushih',
        'name': 'Wushih 烏石',
        'lat': 24.862, 'lon': 121.921,
        'facing': 'E',
        'opt_wind':  ['NW', 'W'],
        'opt_swell': ['E', 'SE', 'SSE'],
        'desc': 'Beach break · L&R · Mid tide · All levels',
    },
    {
        'id': 'doublelions',
        'name': 'Double Lions 雙獅',
        'lat': 24.847, 'lon': 121.917,
        'facing': 'E',
        'opt_wind':  ['W', 'SW'],
        'opt_swell': ['ENE', 'E', 'SE', 'SSE'],
        'desc': 'Beach break · L&R · Mid-high tide · All levels',
    },
    {
        'id': 'chousui',
        'name': 'Chousui 臭水',
        'lat': 24.820, 'lon': 121.899,
        'facing': 'E',
        'opt_wind':  ['WSW', 'W'],
        'opt_swell': ['ENE', 'E', 'ESE'],
        'desc': 'Point break · Left · Low-mid tide · Intermediate+',
    },
]

# ── Safe index access ─────────────────────────────────────────────────────
def _safe_get(lst, idx):
    """Return lst[idx] if in bounds, else None."""
    return lst[idx] if lst and idx < len(lst) else None

# ── Rating thresholds ─────────────────────────────────────────────────────
MIN_SWELL_HEIGHT_M = 0.25   # below this → flat
MAX_SWELL_HEIGHT_M = 4.5    # above this → dangerous
MAX_WIND_KT        = 32     # above this → too windy
LIGHT_WIND_KT      = 10     # below this → light wind bonus
ONSHORE_WIND_KT    = 22     # above this → surf score penalty
STRONG_WIND_KT     = 25     # above this → strong wind penalty

# ── Direction helpers ──────────────────────────────────────────────────────
DIR_DEG = {
    'N': 0, 'NNE': 22, 'NE': 45, 'ENE': 67,
    'E': 90, 'ESE': 112, 'SE': 135, 'SSE': 157,
    'S': 180, 'SSW': 202, 'SW': 225, 'WSW': 247,
    'W': 270, 'WNW': 292, 'NW': 315, 'NNW': 337,
}
DIR_NAMES = ['N','NNE','NE','ENE','E','ESE','SE','SSE',
             'S','SSW','SW','WSW','W','WNW','NW','NNW']

def deg_diff(a: float, b: float) -> float:
    d = abs(a - b) % 360
    return min(d, 360 - d)

def compass(deg):
    if deg is None: return '—'
    return DIR_NAMES[round(deg / 22.5) % 16]

def dir_quality(actual_deg, optimal_dirs: list) -> str:
    """Returns 'good', 'ok', or 'poor' based on proximity to optimal directions."""
    if actual_deg is None:
        return 'unknown'
    min_diff = min(deg_diff(actual_deg, DIR_DEG[d]) for d in optimal_dirs)
    if min_diff <= 22.5: return 'good'
    if min_diff <= 45.0: return 'ok'
    return 'poor'

# ── API fetch ──────────────────────────────────────────────────────────────
OPEN_METEO   = 'https://api.open-meteo.com/v1/forecast'
MARINE_API   = 'https://marine-api.open-meteo.com/v1/marine'
RETRIES      = 3
RETRY_DELAY  = 5

def _get(url: str, label: str) -> dict:
    last_err = RuntimeError('no attempts')
    for attempt in range(1, RETRIES + 1):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                return json.load(r)
        except Exception as e:
            last_err = e
            if attempt < RETRIES:
                time.sleep(RETRY_DELAY)
    print(f'  ⚠  {label} failed: {last_err}', file=sys.stderr)
    return {}

def fetch_spot(lat: float, lon: float) -> tuple[dict, dict, dict]:
    common = {
        'latitude': lat, 'longitude': lon,
        'timeformat': 'iso8601', 'forecast_days': 7, 'timezone': 'UTC',
    }
    ec_params = urllib.parse.urlencode({
        **common,
        'hourly': 'windspeed_10m,winddirection_10m,windgusts_10m,precipitation',
        'wind_speed_unit': 'kn', 'models': 'ecmwf_ifs025',
    })
    gfs_params = urllib.parse.urlencode({
        **common,
        'hourly': 'windgusts_10m',
        'wind_speed_unit': 'kn', 'models': 'gfs_global',
    })
    mar_params = urllib.parse.urlencode({
        **common,
        'hourly': ('wave_height,wave_period,wave_direction,'
                   'swell_wave_height,swell_wave_period,swell_wave_direction'),
    })
    ec  = _get(f'{OPEN_METEO}?{ec_params}',  'ECMWF')
    gfs = _get(f'{OPEN_METEO}?{gfs_params}', 'GFS')
    mar = _get(f'{MARINE_API}?{mar_params}',  'Marine')
    return ec, gfs, mar

# ── Data processing ────────────────────────────────────────────────────────
def process_spot(ec: dict, gfs: dict, mar: dict) -> list[dict]:
    eh = ec.get('hourly', {})
    gh = gfs.get('hourly', {})
    mh = mar.get('hourly', {})

    gfs_by_t  = {t: i for i, t in enumerate(gh.get('time', []))}
    wave_by_t = {t: i for i, t in enumerate(mh.get('time', []))}

    records = []
    for i, t in enumerate(eh.get('time', [])):
        if i % 6 != 0:
            continue  # 6-hourly only

        gust = _safe_get(eh.get('windgusts_10m'), i)
        gi   = gfs_by_t.get(t)
        if gust is None and gi is not None:
            gust = _safe_get(gh.get('windgusts_10m'), gi)

        rain6h = sum(
            (eh.get('precipitation', [0]) + [0] * 10)[k]
            for k in range(max(0, i - 5), i + 1)
        )

        wi = wave_by_t.get(t)
        wv = {}
        if wi is not None:
            wv = {
                'hs':    _safe_get(mh.get('wave_height'),          wi),
                'tp':    _safe_get(mh.get('wave_period'),          wi),
                'dir':   _safe_get(mh.get('wave_direction'),       wi),
                'sw_hs': _safe_get(mh.get('swell_wave_height'),    wi),
                'sw_tp': _safe_get(mh.get('swell_wave_period'),    wi),
                'sw_dir':_safe_get(mh.get('swell_wave_direction'), wi),
            }

        dt_utc = datetime.fromisoformat(t.replace('Z', '+00:00')).replace(tzinfo=timezone.utc)
        dt_cst = dt_utc + timedelta(hours=8)

        records.append({
            'dt_utc': dt_utc,
            'dt_cst': dt_cst,
            'dk':     dt_cst.strftime('%Y-%m-%d'),
            'wind':   _safe_get(eh.get('windspeed_10m'),     i),
            'w_dir':  _safe_get(eh.get('winddirection_10m'), i),
            'gust':   gust,
            'rain6h': rain6h,
            **wv,
        })
    return records

# ── Sailing location (for daily planner) ───────────────────────────────────
KEELUNG = {'lat': 25.128, 'lon': 121.740, 'name': 'Keelung'}

# ── Condition scoring ──────────────────────────────────────────────────────
WKDAY = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat']
MONTH = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']

def day_rating(day_recs: list, spot: dict) -> dict:
    """
    Evaluate the best conditions available during the day for this spot.
    Returns dict with: label, emoji, bg, col, best_hs, best_period, best_wind.
    """
    if not day_recs:
        return {'label': 'No data', 'emoji': '❓', 'bg': '#2d3748', 'col': '#718096',
                'best_sw_hs': None, 'best_sw_tp': None, 'best_wind': None}

    max_sw_hs   = max((r.get('sw_hs') or 0) for r in day_recs)
    max_wind_kt = max((r.get('wind')  or 0) for r in day_recs)

    if max_sw_hs < MIN_SWELL_HEIGHT_M:
        return {'label': 'Flat',      'emoji': '😴', 'bg': '#1a2236', 'col': '#475569',
                'best_sw_hs': max_sw_hs, 'best_sw_tp': None, 'best_wind': max_wind_kt}

    if max_sw_hs > MAX_SWELL_HEIGHT_M or max_wind_kt > MAX_WIND_KT:
        return {'label': 'Dangerous', 'emoji': '🔴', 'bg': '#3d1515', 'col': '#fc8181',
                'best_sw_hs': max_sw_hs, 'best_sw_tp': None, 'best_wind': max_wind_kt}

    # Score each timestep, keep the best
    best_score = 0
    best_rec   = None

    for r in day_recs:
        sw_hs   = r.get('sw_hs') or 0
        sw_dir  = r.get('sw_dir')
        wind_kt = r.get('wind')  or 0
        w_dir   = r.get('w_dir')
        sw_tp   = r.get('sw_tp') or 0

        score = 0
        # Swell direction
        sq = dir_quality(sw_dir, spot['opt_swell'])
        score += {'good': 4, 'ok': 2, 'poor': 0, 'unknown': 1}[sq]
        # Wind direction (offshore)
        wq = dir_quality(w_dir, spot['opt_wind'])
        score += {'good': 3, 'ok': 1, 'poor': 0, 'unknown': 1}[wq]
        # Wind speed (light is better)
        if wind_kt < LIGHT_WIND_KT:   score += 2
        elif wind_kt < 15:            score += 1
        elif wind_kt > ONSHORE_WIND_KT: score -= 2
        # Swell height
        if 0.6 <= sw_hs <= 2.5: score += 3
        elif sw_hs > 0.3:        score += 1
        # Period
        if sw_tp >= 12: score += 2
        elif sw_tp >= 9: score += 1

        if score > best_score:
            best_score = score
            best_rec   = r

    br = best_rec or day_recs[0]

    if   best_score >= 9:  return {'label': 'Firing!',  'emoji': '🔥', 'bg': '#0d3320', 'col': '#48bb78', 'best_sw_hs': br.get('sw_hs'), 'best_sw_tp': br.get('sw_tp'), 'best_wind': br.get('wind')}
    elif best_score >= 7:  return {'label': 'Good',     'emoji': '🟢', 'bg': '#0d2d1a', 'col': '#68d391', 'best_sw_hs': br.get('sw_hs'), 'best_sw_tp': br.get('sw_tp'), 'best_wind': br.get('wind')}
    elif best_score >= 4:  return {'label': 'Marginal', 'emoji': '🟡', 'bg': '#3d2e00', 'col': '#fbd38d', 'best_sw_hs': br.get('sw_hs'), 'best_sw_tp': br.get('sw_tp'), 'best_wind': br.get('wind')}
    else:                  return {'label': 'Poor',     'emoji': '🔴', 'bg': '#3d1515', 'col': '#fc8181', 'best_sw_hs': br.get('sw_hs'), 'best_sw_tp': br.get('sw_tp'), 'best_wind': br.get('wind')}


def sail_day_rating(day_recs: list) -> dict:
    """Evaluate daily sailing conditions at Keelung."""
    if not day_recs:
        return {'label': '—',          'emoji': '❓', 'bg': '#1a2236', 'col': '#475569'}
    max_w  = max((r.get('wind')   or 0) for r in day_recs)
    max_g  = max((r.get('gust')   or 0) for r in day_recs)
    max_hs = max((r.get('hs')     or 0) for r in day_recs)
    tot_r  = sum((r.get('rain6h') or 0) for r in day_recs)
    if max_g >= 34 or max_w >= 28 or max_hs >= 2.5:
        return {'label': '🔴 No-go',   'emoji': '🔴', 'bg': '#3d1515', 'col': '#fc8181',
                'max_w': max_w, 'max_g': max_g, 'max_hs': max_hs}
    if max_g >= 22 or max_w >= 17 or max_hs >= 1.5 or tot_r >= 15:
        return {'label': '🟡 Marginal', 'emoji': '🟡', 'bg': '#3d2e00', 'col': '#fbd38d',
                'max_w': max_w, 'max_g': max_g, 'max_hs': max_hs}
    return {'label': '🟢 Good',    'emoji': '🟢', 'bg': '#0d2d1a', 'col': '#68d391',
            'max_w': max_w, 'max_g': max_g, 'max_hs': max_hs}


def _recommend(sail_rat: dict, best_surf_rat: dict, best_surf_name: str) -> tuple[str, str]:
    """
    Returns (recommendation_text, background_colour) for the planner table.
    """
    sail_emoji = sail_rat['emoji']   # 🟢 🟡 🔴 ❓
    surf_emoji = best_surf_rat['emoji']  # 🔥 🟢 🟡 🔴 😴 ❓
    can_sail  = sail_emoji == '🟢'
    marg_sail = sail_emoji == '🟡'
    good_surf = surf_emoji in ('🔥', '🟢')
    fire_surf = surf_emoji == '🔥'
    marg_surf = surf_emoji == '🟡'

    if can_sail and fire_surf:
        return f'⛵ Sail or 🏄 Surf: {best_surf_name}', '#0d2d1a'
    if can_sail and good_surf:
        return f'⛵ Go sailing or 🏄 Surf: {best_surf_name}', '#0d2d1a'
    if can_sail:
        return '⛵ Go sailing', '#0d2d1a'
    if fire_surf:
        return f'🏄 Surf: {best_surf_name}', '#0d3320'
    if good_surf:
        return f'🏄 Surf: {best_surf_name}', '#0d2d1a'
    if marg_sail and marg_surf:
        return f'🟡 Marginal — maybe surf: {best_surf_name}', '#3d2e00'
    if marg_sail:
        return '🟡 Marginal sailing only', '#3d2e00'
    if marg_surf:
        return f'🟡 Maybe surf: {best_surf_name}', '#3d2e00'
    return '🔴 Stay home', '#3d1515'


# ── HTML generation ────────────────────────────────────────────────────────
CSS = """
<style>
.surf-section {
  font-family: Arial, 'Helvetica Neue', sans-serif;
  font-size: 13px;
  color: #e2e8f0;
  background: #0f172a;
  padding: 16px;
  border-radius: 8px;
  margin-top: 20px;
}
.surf-title {
  font-size: 16px;
  font-weight: 700;
  margin-bottom: 4px;
  color: #93c5fd;
}
.surf-subtitle {
  font-size: 11px;
  color: #475569;
  margin-bottom: 14px;
}
.matrix-table {
  border-collapse: collapse;
  width: 100%;
  margin-bottom: 20px;
}
.matrix-table th {
  background: #1e3a5f;
  color: #7db8f0;
  padding: 6px 8px;
  font-size: 11px;
  text-align: center;
  white-space: nowrap;
  border: 1px solid #2d3f5a;
}
.matrix-table th.spot-hdr {
  text-align: left;
  min-width: 110px;
}
.matrix-table td {
  padding: 5px 8px;
  text-align: center;
  border: 1px solid #1e293b;
  font-size: 12px;
  white-space: nowrap;
}
.matrix-table td.spot-name {
  text-align: left;
  font-size: 11px;
  color: #94a3b8;
  background: #111827;
}
.matrix-table td.spot-name small {
  display: block;
  font-size: 9px;
  color: #475569;
}
.detail-section {
  margin-top: 16px;
}
.detail-header {
  font-size: 13px;
  font-weight: 700;
  color: #93c5fd;
  border-bottom: 1px solid #2d3f5a;
  padding-bottom: 4px;
  margin-bottom: 8px;
}
.detail-table {
  border-collapse: collapse;
  width: 100%;
  font-size: 11px;
  margin-bottom: 12px;
}
.detail-table th {
  background: #1e3a5f;
  color: #7db8f0;
  padding: 4px 6px;
  text-align: center;
  white-space: nowrap;
  border: 1px solid #2d3f5a;
}
.detail-table td {
  padding: 3px 6px;
  text-align: center;
  white-space: nowrap;
  border-bottom: 1px solid #151f30;
  background: #0f172a;
}
.detail-table tr.r-alt td { background: #111827; }
.detail-table td.date-sep {
  background: #1a2f4a;
  color: #7db8f0;
  font-weight: 700;
  text-align: left;
  padding: 4px 8px;
}
.c-good   { color: #68d391; font-weight: 700; }
.c-warn   { color: #fbd38d; }
.c-danger { color: #fc8181; font-weight: 700; }
.c-muted  { color: #475569; }
.legend-block {
  font-size: 10px;
  color: #475569;
  margin-top: 10px;
  border-top: 1px solid #1e293b;
  padding-top: 8px;
}
</style>
"""

def _f1(v): return '—' if v is None else f'{v:.1f}'
def _f0(v): return '—' if v is None else str(round(v))

def _wind_cls(kt):
    if kt is None: return ''
    if kt >= 28: return 'c-danger'
    if kt >= 18: return 'c-warn'
    return ''

def _hs_cls(hs, is_swell=True):
    if hs is None: return ''
    if hs > 3.5: return 'c-danger'
    if hs > 2.5: return 'c-warn'
    if 0.6 <= hs <= 2.5: return 'c-good'
    if hs < 0.3: return 'c-muted'
    return ''

def generate_html(all_spot_data: list[dict], keelung_records: list = None) -> str:
    """
    all_spot_data:    list of { 'spot': spot_dict, 'records': [record, ...] }
    keelung_records:  list of sailing records for Keelung (optional, for planner)
    """
    now_cst = datetime.now(timezone.utc) + timedelta(hours=8)
    gen_str = now_cst.strftime('%Y-%m-%d %H:%M CST')

    # Collect all day keys across all spots
    all_dks = sorted({r['dk'] for sd in all_spot_data for r in sd['records']})

    html = CSS
    html += '<div class="surf-section">\n'
    html += f'<div class="surf-title">🏄 Taiwan Surf Forecast</div>\n'
    html += f'<div class="surf-subtitle">Generated {gen_str} · Data: ECMWF IFS025 + GFS + ECMWF WAM (Open-Meteo) · Source: swelleye.com</div>\n'

    # ── Daily Activity Planner ─────────────────────────────────────────────
    # Pre-bucket keelung records and surf records by day
    keelung_by_day = {}
    if keelung_records:
        for r in keelung_records:
            keelung_by_day.setdefault(r['dk'], []).append(r)

    surf_by_day_spot = {}  # dk → list of (spot, records_for_day)
    for sd in all_spot_data:
        by_day = {}
        for r in sd['records']:
            by_day.setdefault(r['dk'], []).append(r)
        for dk, recs in by_day.items():
            surf_by_day_spot.setdefault(dk, []).append((sd['spot'], recs))

    html += '<div style="margin-bottom:20px">\n'
    html += '<div style="font-size:14px;font-weight:700;color:#93c5fd;margin-bottom:6px">📅 Daily Activity Planner</div>\n'
    html += ('<table class="matrix-table">\n'
             '<tr>'
             '<th class="spot-hdr" style="text-align:left;min-width:90px">Day</th>'
             '<th style="min-width:110px">⛵ Keelung Sailing</th>'
             '<th style="min-width:130px">🏄 Best Surf Spot</th>'
             '<th style="min-width:160px">Recommendation</th>'
             '</tr>\n')

    for dk in all_dks:
        d    = datetime.strptime(dk, '%Y-%m-%d')
        dlbl = f'{WKDAY[d.weekday()]} {d.day} {MONTH[d.month-1]}'

        # Sailing rating
        sail_recs = keelung_by_day.get(dk, [])
        sail_rat  = sail_day_rating(sail_recs)

        # Best surf spot for this day
        best_surf_rat  = {'label': '—', 'emoji': '😴', 'bg': '#1a2236', 'col': '#475569'}
        best_surf_name = '—'
        rank_order = {'🔥': 4, '🟢': 3, '🟡': 2, '🔴': 1, '😴': 0, '❓': 0}
        best_rank  = -1
        for spot, recs in surf_by_day_spot.get(dk, []):
            rat  = day_rating(recs, spot)
            rank = rank_order.get(rat['emoji'], 0)
            if rank > best_rank:
                best_rank      = rank
                best_surf_rat  = rat
                best_surf_name = spot['name'].split()[0]  # short name (e.g. "Fulong")

        rec_text, rec_bg = _recommend(sail_rat, best_surf_rat, best_surf_name)

        # Build details string for sailing cell
        max_w  = sail_rat.get('max_w')
        max_g  = sail_rat.get('max_g')
        max_hs = sail_rat.get('max_hs')
        sail_detail = ''
        if max_w is not None:
            sail_detail = f'<small style="color:#64748b;display:block">{round(max_w)}/{round(max_g)}kt · {max_hs:.1f}m</small>'

        html += (f'<tr>'
                 f'<td class="spot-name" style="font-weight:700;color:#cbd5e1">{dlbl}</td>'
                 f'<td style="background:{sail_rat["bg"]};color:{sail_rat["col"]};text-align:center">'
                 f'{sail_rat["label"]}{sail_detail}</td>'
                 f'<td style="background:{best_surf_rat["bg"]};color:{best_surf_rat["col"]};text-align:center">'
                 f'{best_surf_rat["emoji"]} {best_surf_name}'
                 f'<small style="color:#64748b;display:block">{best_surf_rat["label"]}</small></td>'
                 f'<td style="background:{rec_bg};color:#e2e8f0;font-weight:600;padding:6px 10px">{rec_text}</td>'
                 f'</tr>\n')

    html += '</table>\n</div>\n'

    html += '</div>\n'  # surf-section
    return html


def generate_full_html(all_spot_data: list[dict], keelung_records: list = None) -> str:
    """
    Full web-app version: Daily Activity Planner + 7-spot rating matrix
    + per-spot hourly detail tables + legend.  Used for the phone web app.
    generate_html() produces the compact email-only summary.
    """
    # Start with the email summary (planner table)
    html = generate_html(all_spot_data, keelung_records=keelung_records)

    # Strip the closing </div> (surf-section) so we can append more content
    if html.endswith('</div>\n'):
        html = html[:-len('</div>\n')]

    now_cst = datetime.now(timezone.utc) + timedelta(hours=8)
    all_dks = sorted({r['dk'] for sd in all_spot_data for r in sd['records']})

    # ── Rating matrix ──────────────────────────────────────────────────────
    html += '<table class="matrix-table">\n<tr>'
    html += '<th class="spot-hdr">Spot</th>'
    for dk in all_dks:
        d = datetime.strptime(dk, '%Y-%m-%d')
        html += f'<th>{WKDAY[d.weekday()]}<br>{d.day} {MONTH[d.month-1]}</th>'
    html += '</tr>\n'

    for sd in all_spot_data:
        spot    = sd['spot']
        records = sd['records']
        by_day  = {}
        for r in records:
            by_day.setdefault(r['dk'], []).append(r)

        html += '<tr>'
        html += (f'<td class="spot-name">{spot["name"]}'
                 f'<small>{spot["desc"]}</small></td>')

        for dk in all_dks:
            day_recs = by_day.get(dk, [])
            rating   = day_rating(day_recs, spot)
            html += (f'<td style="background:{rating["bg"]};color:{rating["col"]}">'
                     f'{rating["emoji"]} {rating["label"]}</td>')
        html += '</tr>\n'

    html += '</table>\n'

    # ── Per-spot detail tables ─────────────────────────────────────────────
    html += '<div class="detail-section">\n'

    for sd in all_spot_data:
        spot    = sd['spot']
        records = sd['records']
        if not records:
            continue

        html += f'<div class="detail-header">{spot["name"]} — Detailed Forecast</div>\n'
        html += '<table class="detail-table">\n'
        html += ('<tr><th>CST</th>'
                 '<th>Rating</th>'
                 '<th>Swell m</th><th>T s</th><th>Sw Dir</th>'
                 '<th>Hs m</th>'
                 '<th>Wind kt</th><th>W Dir</th><th>Gust</th></tr>\n')

        prev_dk = None
        row_i   = 0
        for r in records:
            dk = r['dk']
            if dk != prev_dk:
                prev_dk = dk
                row_i   = 0
                d       = datetime.strptime(dk, '%Y-%m-%d')
                dl      = f'{WKDAY[d.weekday()]} {d.day} {MONTH[d.month-1]}'
                html += f'<tr><td class="date-sep" colspan="9">📅 {dl}</td></tr>\n'

            rating = day_rating([r], spot)
            tstr   = r['dt_cst'].strftime('%H:%M')
            cls    = 'r-alt' if row_i % 2 else ''

            sw_hs  = r.get('sw_hs')
            sw_tp  = r.get('sw_tp')
            sw_dir = r.get('sw_dir')
            hs     = r.get('hs')
            wind   = r.get('wind')
            w_dir  = r.get('w_dir')
            gust   = r.get('gust')

            sq = dir_quality(sw_dir, spot['opt_swell'])
            wq = dir_quality(w_dir,  spot['opt_wind'])
            sw_dir_str = f'{compass(sw_dir)}'
            if sq == 'good': sw_dir_str = f'<b class="c-good">{sw_dir_str}✓</b>'
            elif sq == 'poor': sw_dir_str = f'<span class="c-danger">{sw_dir_str}✗</span>'

            w_dir_str = compass(w_dir)
            if wq == 'good': w_dir_str = f'<b class="c-good">{w_dir_str}✓</b>'
            elif wq == 'poor': w_dir_str = f'<span class="c-warn">{w_dir_str}</span>'

            html += (f'<tr class="{cls}">'
                     f'<td><b>{tstr}</b></td>'
                     f'<td style="background:{rating["bg"]};color:{rating["col"]}">{rating["emoji"]}</td>'
                     f'<td class="{_hs_cls(sw_hs)}">{_f1(sw_hs)}</td>'
                     f'<td>{_f1(sw_tp)}</td>'
                     f'<td>{sw_dir_str}</td>'
                     f'<td class="{_hs_cls(hs)}">{_f1(hs)}</td>'
                     f'<td class="{_wind_cls(wind)}">{_f0(wind)}</td>'
                     f'<td>{w_dir_str}</td>'
                     f'<td class="{_wind_cls(gust)}">{_f0(gust)}</td>'
                     f'</tr>\n')
            row_i += 1

        html += '</table>\n'

    html += '</div>\n'  # detail-section

    # ── Legend ─────────────────────────────────────────────────────────────
    html += ('<div class="legend-block">'
             '<b>Surf conditions key:</b> '
             '🔥 Firing (optimal dir + good swell + light wind) · '
             '🟢 Good · 🟡 Marginal · 🔴 Poor/Dangerous · 😴 Flat (&lt;0.25m swell)<br>'
             'Direction ticks: <b class="c-good">✓ optimal</b> · '
             '<span class="c-danger">✗ unfavourable</span><br>'
             'Swell colour: <span class="c-good">green 0.6–2.5m</span> · '
             '<span class="c-warn">amber &gt;2.5m</span> · '
             '<span class="c-danger">red &gt;3.5m</span>'
             '</div>\n')

    html += '</div>\n'  # surf-section
    return html


# ── Main ───────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description='Taiwan surf forecast for email')
    ap.add_argument('--output', default='surf_forecast.html',
                    help='Full web-app HTML (default: surf_forecast.html)')
    ap.add_argument('--email-output', default='surf_forecast_email.html',
                    help='Simple email summary HTML (default: surf_forecast_email.html)')
    args = ap.parse_args()

    # ── Fetch Keelung sailing data (for daily planner) ─────────────────────
    print(f'  Fetching Keelung sailing (for daily planner) …', flush=True)
    ec_k, gfs_k, mar_k = fetch_spot(KEELUNG['lat'], KEELUNG['lon'])
    keelung_records = process_spot(ec_k, gfs_k, mar_k)
    print(f'    → {len(keelung_records)} timesteps', flush=True)

    # ── Fetch each surf spot ────────────────────────────────────────────────
    all_spot_data = []
    for spot in SPOTS:
        print(f'  Fetching {spot["name"]} …', flush=True)
        ec, gfs, mar = fetch_spot(spot['lat'], spot['lon'])
        records      = process_spot(ec, gfs, mar)
        print(f'    → {len(records)} timesteps', flush=True)
        all_spot_data.append({'spot': spot, 'records': records})

    # Full web-app version (phone drill-down)
    html_full = generate_full_html(all_spot_data, keelung_records=keelung_records)
    with open(args.output, 'w', encoding='utf-8') as f:
        f.write(html_full)
    print(f'  ✅ Wrote {args.output} ({len(html_full):,} chars)', flush=True)

    # Simple email summary
    html_email = generate_html(all_spot_data, keelung_records=keelung_records)
    with open(args.email_output, 'w', encoding='utf-8') as f:
        f.write(html_email)
    print(f'  ✅ Wrote {args.email_output} ({len(html_email):,} chars)', flush=True)

if __name__ == '__main__':
    main()
