#!/usr/bin/env python3
"""
surf_forecast.py — Taiwan surf spot 7-day forecast
Fetches ECMWF + GFS wind/gust and ECMWF WAM swell data for each spot,
evaluates conditions against each spot's optimal wind/swell directions,
and writes surf_forecast.html for the web app.

Usage:
    python3 surf_forecast.py [--output surf_forecast.html]
"""

import argparse, json, logging, os, sys, time, urllib.request, urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta

from config import (KEELUNG_LAT, KEELUNG_LON, SPOT_COORDS,
                     deg_to_compass, setup_logging, sail_rating,
                     sunrise_sunset, is_daylight)
from config import fetch_json as _config_fetch_json

# Build coordinate lookup from shared SPOT_COORDS (single source of truth)
_COORD_LOOKUP = {s["id"]: (s["lat"], s["lon"]) for s in SPOT_COORDS}
from i18n import T, T_str, bilingual, SPOT_DESC_KEYS
from tide_predict import (predict_height, predict_height_anchored,
                          find_extrema, tide_state)

# CWA official tide forecast extrema — loaded at startup from cwa_obs.json
# when available.  Used by _tide_height() for anchored interpolation.
_CWA_TIDE_EXTREMA: list[dict] | None = None


def _tide_height(dt_utc) -> float | None:
    """Predict tide height using CWA-anchored interpolation when available."""
    if dt_utc is None:
        return None
    return predict_height_anchored(dt_utc, _CWA_TIDE_EXTREMA)

log = logging.getLogger(__name__)

# ── Surf spots ─────────────────────────────────────────────────────────────
# opt_wind  : directions that are offshore / light & favourable
# opt_swell : directions the spot is best exposed to
# Source: swelleye.com spot guides

SPOTS = [
    {
        'id': 'fulong',
        'name': 'Fulong 福隆',
        'lat': _COORD_LOOKUP['fulong'][0], 'lon': _COORD_LOOKUP['fulong'][1],
        'facing': 'NE/E',
        'opt_wind':  ['S', 'SW'],
        'opt_swell': ['N', 'NE', 'E'],
        'opt_tide':  'any',
        'desc': 'Rivermouth beach break · L&R · All levels',
        'desc_zh': '河口沙灘浪型 · 左右跑 · 各級適合',
    },
    {
        'id': 'greenbay',
        'name': 'Green Bay 翡翠灣',
        'lat': _COORD_LOOKUP['greenbay'][0], 'lon': _COORD_LOOKUP['greenbay'][1],
        'facing': 'NE',
        'opt_wind':  ['W', 'SW'],
        'opt_swell': ['E', 'NE'],
        'opt_tide':  'any',
        'desc': 'Beach break · L&R · All levels',
        'desc_zh': '沙灘浪型 · 左右跑 · 各級適合',
    },
    {
        'id': 'jinshan',
        'name': 'Jinshan 金山',
        'lat': _COORD_LOOKUP['jinshan'][0], 'lon': _COORD_LOOKUP['jinshan'][1],
        'facing': 'NE',
        'opt_wind':  ['S', 'SW'],
        'opt_swell': ['N', 'NNE', 'NE', 'E', 'ESE'],
        'opt_tide':  'mid',
        'desc': 'Beach/point · L&R · Mid tide · Beg–Inter',
        'desc_zh': '沙灘/礁岩 · 左右跑 · 中潮 · 初學–中級',
    },
    {
        'id': 'daxi',
        'name': 'Daxi 大溪',
        'lat': _COORD_LOOKUP['daxi'][0], 'lon': _COORD_LOOKUP['daxi'][1],
        'facing': 'SE',
        'opt_wind':  ['NW', 'W'],
        'opt_swell': ['SE', 'SSE', 'S', 'E'],
        'opt_tide':  'mid-high',
        'desc': 'Half-moon beach break · L&R · Mid-high tide · Beg–Inter',
        'desc_zh': '半月形沙灘 · 左右跑 · 中高潮 · 初學–中級',
    },
    {
        'id': 'wushih',
        'name': 'Wushih 烏石',
        'lat': _COORD_LOOKUP['wushih'][0], 'lon': _COORD_LOOKUP['wushih'][1],
        'facing': 'E',
        'opt_wind':  ['NW', 'W'],
        'opt_swell': ['E', 'SE', 'SSE'],
        'opt_tide':  'mid',
        'desc': 'Beach break · L&R · Mid tide · All levels',
        'desc_zh': '沙灘浪型 · 左右跑 · 中潮 · 各級適合',
    },
    {
        'id': 'doublelions',
        'name': 'Double Lions 雙獅',
        'lat': _COORD_LOOKUP['doublelions'][0], 'lon': _COORD_LOOKUP['doublelions'][1],
        'facing': 'E',
        'opt_wind':  ['W', 'SW'],
        'opt_swell': ['ENE', 'E', 'SE', 'SSE'],
        'opt_tide':  'mid-high',
        'desc': 'Beach break · L&R · Mid-high tide · All levels',
        'desc_zh': '沙灘浪型 · 左右跑 · 中高潮 · 各級適合',
    },
    {
        'id': 'chousui',
        'name': 'Chousui 臭水',
        'lat': _COORD_LOOKUP['chousui'][0], 'lon': _COORD_LOOKUP['chousui'][1],
        'facing': 'E',
        'opt_wind':  ['WSW', 'W'],
        'opt_swell': ['ENE', 'E', 'ESE'],
        'opt_tide':  'low-mid',
        'desc': 'Point break · Left · Low-mid tide · Intermediate+',
        'desc_zh': '礁岩浪型 · 左跑 · 低中潮 · 中級以上',
    },
]


def _split_spot_name(full_name: str) -> tuple[str, str]:
    """Split 'Jinshan 金山' → ('Jinshan', '金山'). Works for multi-word English names too."""
    parts = full_name.rsplit(None, 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return full_name, full_name


# ── Safe index access ─────────────────────────────────────────────────────
def _safe_get(lst: list | None, idx: int) -> object | None:
    """Return lst[idx] if in bounds, else None."""
    return lst[idx] if lst and 0 <= idx < len(lst) else None

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
def deg_diff(a: float, b: float) -> float:
    d = abs(a - b) % 360
    return min(d, 360 - d)

compass = deg_to_compass  # local alias

def dir_quality(actual_deg: float | None, optimal_dirs: list[str]) -> str:
    """Returns 'good', 'ok', or 'poor' based on proximity to optimal directions."""
    if actual_deg is None:
        return 'unknown'
    min_diff = min(deg_diff(actual_deg, DIR_DEG[d]) for d in optimal_dirs)
    if min_diff <= 22.5: return 'good'
    if min_diff <= 45.0: return 'ok'
    return 'poor'


# ── Tide classification ───────────────────────────────────────────────────
# Keelung chart datum: MSL ~0.45m.  Classify tide height above chart datum.
_TIDE_LOW_MAX  = 0.30   # below this = low tide
_TIDE_HIGH_MIN = 0.60   # above this = high tide
# Between = mid tide

def classify_tide(height_m: float | None) -> str:
    """Classify tide as 'low', 'mid', or 'high' from height above chart datum."""
    if height_m is None:
        return 'unknown'
    if height_m < _TIDE_LOW_MAX:
        return 'low'
    if height_m > _TIDE_HIGH_MIN:
        return 'high'
    return 'mid'


def tide_score(tide_class: str, opt_tide: str) -> int:
    """Return +1 if tide matches spot preference, -1 if opposite, 0 otherwise."""
    if opt_tide == 'any' or tide_class == 'unknown':
        return 0
    # Build set of acceptable tide states
    acceptable = set()
    if 'low' in opt_tide:
        acceptable.add('low')
    if 'mid' in opt_tide:
        acceptable.add('mid')
    if 'high' in opt_tide:
        acceptable.add('high')
    if not acceptable:
        return 0
    if tide_class in acceptable:
        return 1
    # Opposite: low when needs high, high when needs low
    opposites = {'low': 'high', 'high': 'low'}
    if opposites.get(tide_class) in acceptable and tide_class not in acceptable:
        return -1
    return 0

# ── API fetch ──────────────────────────────────────────────────────────────
OPEN_METEO   = 'https://api.open-meteo.com/v1/forecast'
MARINE_API   = 'https://marine-api.open-meteo.com/v1/marine'
RETRIES      = 3
RETRY_DELAY  = 5

def _get(url: str, label: str) -> dict[str, object]:
    """Fetch JSON from *url* with retry. Returns empty dict on failure."""
    result = _config_fetch_json(url, label=label)
    return result if result is not None else {}

def fetch_spot(lat: float, lon: float) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
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
def process_spot(ec: dict, gfs: dict, mar: dict) -> list[dict[str, object]]:
    eh = ec.get('hourly', {})
    gh = gfs.get('hourly', {})
    mh = mar.get('hourly', {})

    gfs_by_t  = {t: i for i, t in enumerate(gh.get('time', []))}
    wave_by_t = {t: i for i, t in enumerate(mh.get('time', []))}

    records = []
    for i, t in enumerate(eh.get('time', [])):
        # Filter to 6-hourly timestamps by checking the actual hour,
        # not the index — robust if the API response doesn't start at 00:00.
        try:
            _hour = int(t[11:13]) if len(t) >= 13 else -1
        except (ValueError, TypeError):
            _hour = -1
        if _hour % 6 != 0:
            continue

        gust = _safe_get(eh.get('windgusts_10m'), i)
        gi   = gfs_by_t.get(t)
        if gust is None and gi is not None:
            gust = _safe_get(gh.get('windgusts_10m'), gi)

        _precip = eh.get('precipitation', [])
        # Sum the preceding 6 hourly precipitation values.  When fewer than 6
        # values are available (early forecast hours), scale up proportionally
        # so the result always represents a 6-hour equivalent accumulation.
        window_start = max(0, i - 5)
        window_len = i + 1 - window_start          # actual number of values
        raw_sum = sum(
            (_precip[k] or 0) if k < len(_precip) else 0
            for k in range(window_start, i + 1)
        )
        rain6h = raw_sum * (6 / window_len) if window_len < 6 else raw_sum

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

        dt_utc = datetime.fromisoformat(t.replace('Z', '+00:00'))
        if dt_utc.tzinfo is None:
            dt_utc = dt_utc.replace(tzinfo=timezone.utc)
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
KEELUNG = {'lat': KEELUNG_LAT, 'lon': KEELUNG_LON, 'name': 'Keelung'}

# ── Condition scoring ──────────────────────────────────────────────────────
WKDAY = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun']
MONTH = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']

def _score_timestep(r: dict, spot: dict, tide_height_m: float | None = None) -> int:
    """Score a single 6-hourly timestep for a given surf spot. Returns integer score."""
    sw_hs   = r.get('sw_hs') or 0
    sw_dir  = r.get('sw_dir')
    wind_kt = r.get('wind')  or 0
    w_dir   = r.get('w_dir')
    sw_tp   = r.get('sw_tp') or 0

    score = 0

    # Swell direction — weighted by swell height (full credit at ≥0.6m)
    sq = dir_quality(sw_dir, spot['opt_swell'])
    swell_dir_base = {'good': 4, 'ok': 2, 'poor': 0, 'unknown': 1}[sq]
    swell_factor = min(sw_hs / 0.6, 1.0) if sw_hs > 0 else 0
    score += round(swell_dir_base * swell_factor)

    # Wind direction (offshore) — weighted by wind speed (full credit at ≥LIGHT_WIND_KT)
    wq = dir_quality(w_dir, spot['opt_wind'])
    wind_dir_base = {'good': 3, 'ok': 1, 'poor': 0, 'unknown': 1}[wq]
    wind_factor = min(wind_kt / LIGHT_WIND_KT, 1.0) if wind_kt > 0 else 0
    score += round(wind_dir_base * wind_factor)

    # Wind speed (light is better)
    if wind_kt < LIGHT_WIND_KT:   score += 2
    elif wind_kt < 15:            score += 1
    elif wind_kt > ONSHORE_WIND_KT: score -= 2

    # Wave energy — height² × period (replaces independent height + period)
    energy = sw_hs ** 2 * sw_tp
    if energy >= 12:    score += 5   # e.g. 1.0m @ 12s, 1.5m @ 5.3s
    elif energy >= 5:   score += 3   # e.g. 0.7m @ 10s
    elif energy >= 1.5: score += 2   # e.g. 0.5m @ 6s
    elif energy > 0:    score += 1

    # Tide preference
    opt_tide = spot.get('opt_tide', 'any')
    tide_class = classify_tide(tide_height_m)
    score += tide_score(tide_class, opt_tide)

    return score


def day_rating(day_recs: list[dict], spot: dict,
               tide_height_m: float | None = None,
               ensemble_spread: dict | None = None) -> dict[str, object]:
    """
    Evaluate the best conditions available during the day for this spot.
    Returns dict with: label, emoji, bg, col, best_hs, best_period, best_wind,
    and optionally 'confidence'.

    Scoring (max ~16 points):
      Swell direction: 0-4 (weighted by swell height)
      Wind direction:  0-3 (weighted by wind speed)
      Wind speed:      -2 to +2
      Wave energy:     0-5 (height² × period)
      Tide match:      -1 to +1
    """
    if not day_recs:
        return {'label': T_str('no_data', 'en'), 'label_key': 'no_data',
                'emoji': '❓', 'bg': '#2d3748', 'col': '#718096',
                'best_sw_hs': None, 'best_sw_tp': None, 'best_wind': None}

    max_sw_hs   = max((r.get('sw_hs') or 0) for r in day_recs)
    max_wind_kt = max((r.get('wind')  or 0) for r in day_recs)

    if max_sw_hs < MIN_SWELL_HEIGHT_M:
        return {'label': T_str('flat', 'en'), 'label_key': 'flat',
                'emoji': '😴', 'bg': '#1a2236', 'col': '#475569',
                'best_sw_hs': max_sw_hs, 'best_sw_tp': None, 'best_wind': max_wind_kt}

    if max_sw_hs > MAX_SWELL_HEIGHT_M or max_wind_kt > MAX_WIND_KT:
        return {'label': T_str('dangerous', 'en'), 'label_key': 'dangerous',
                'emoji': '🔴', 'bg': '#3d1515', 'col': '#fc8181',
                'best_sw_hs': max_sw_hs, 'best_sw_tp': None, 'best_wind': max_wind_kt}

    # Score each timestep, keep the best
    # Use per-timestep tide height when records have dt_utc, otherwise fall back
    best_score = 0
    best_rec   = None

    for r in day_recs:
        # Compute tide at this timestep if possible
        dt_utc = r.get('dt_utc')
        if dt_utc is not None:
            th = _tide_height(dt_utc)
        else:
            th = tide_height_m

        score = _score_timestep(r, spot, tide_height_m=th)

        if score > best_score:
            best_score = score
            best_rec   = r

    br = best_rec or day_recs[0]

    # Ensemble confidence
    confidence = 'normal'
    if ensemble_spread:
        wind_spread = ensemble_spread.get('wind_kt', {}).get('spread')
        temp_spread = ensemble_spread.get('temp_c', {}).get('spread')
        if (wind_spread is not None and wind_spread > 5) or \
           (temp_spread is not None and temp_spread > 2):
            confidence = 'low'

    base = {'best_sw_hs': br.get('sw_hs'), 'best_sw_tp': br.get('sw_tp'),
             'best_wind': br.get('wind'), 'confidence': confidence}

    if   best_score >= 9:  return {'label': T_str('firing', 'en'), 'label_key': 'firing',  'emoji': '🔥', 'bg': '#0d3320', 'col': '#48bb78', **base}
    elif best_score >= 7:  return {'label': T_str('good', 'en'),    'label_key': 'good',     'emoji': '🟢', 'bg': '#0d2d1a', 'col': '#68d391', **base}
    elif best_score >= 4:  return {'label': T_str('marginal', 'en'), 'label_key': 'marginal', 'emoji': '🟡', 'bg': '#3d2e00', 'col': '#fbd38d', **base}
    else:                  return {'label': T_str('poor', 'en'),    'label_key': 'poor',     'emoji': '🔴', 'bg': '#3d1515', 'col': '#fc8181', **base}


def best_time_for_day(day_recs: list[dict], spot: dict) -> dict[str, object] | None:
    """
    Find the optimal 6-hourly window to surf at *spot* on a given day.

    Returns a dict with timing, conditions, tide info, and score — or None if
    no surfable conditions exist (flat / dangerous / no data).
    """
    if not day_recs:
        return None

    max_sw_hs   = max((r.get('sw_hs') or 0) for r in day_recs)
    max_wind_kt = max((r.get('wind')  or 0) for r in day_recs)
    if max_sw_hs < MIN_SWELL_HEIGHT_M or max_sw_hs > MAX_SWELL_HEIGHT_M or max_wind_kt > MAX_WIND_KT:
        return None

    # Filter to daylight windows only — no point recommending nighttime surfing.
    # A 6h window centred at e.g. 14:00 CST (06:00 UTC) overlaps daylight if
    # ANY part of the window is in daylight, but we use the window midpoint.
    daylight_recs = []
    for r in day_recs:
        dt_utc = r.get('dt_utc')
        if dt_utc is not None:
            # Check if this 6h window has substantial daylight.
            # The window is [dt_utc, dt_utc+6h); check midpoint (dt_utc+3h).
            mid = dt_utc + timedelta(hours=3)
            if is_daylight(mid, spot['lat'], spot['lon'], margin_minutes=0):
                daylight_recs.append(r)
        else:
            daylight_recs.append(r)  # keep if we can't determine time

    # Fall back to all records if no daylight windows (shouldn't happen)
    recs_to_score = daylight_recs if daylight_recs else day_recs

    scored = []
    for r in recs_to_score:
        dt_utc = r.get('dt_utc')
        th = _tide_height(dt_utc) if dt_utc is not None else None
        score = _score_timestep(r, spot, tide_height_m=th)
        scored.append((score, r, th))

    if not scored:
        return None

    scored.sort(key=lambda x: x[0], reverse=True)
    best_score, best_rec, best_tide_h = scored[0]

    dt_utc = best_rec.get('dt_utc')
    dt_cst = best_rec.get('dt_cst')

    # Sunrise/sunset for this day (in CST)
    sunrise_cst = sunset_cst = None
    if dt_utc is not None:
        sr_utc, ss_utc = sunrise_sunset(dt_utc, spot['lat'], spot['lon'])
        sunrise_cst = sr_utc + 8  # UTC → CST
        sunset_cst = ss_utc + 8

    # Label the window as a 6-hour block in CST
    if dt_cst is not None:
        h = dt_cst.hour
        window_lbl = f'{h:02d}:00–{(h+6)%24:02d}:00 CST'
        time_lbl   = dt_cst.strftime('%H:%M CST')
    else:
        window_lbl = '—'
        time_lbl   = '—'

    # Tide info at best time
    tide_class = classify_tide(best_tide_h)
    tide_str = f'{best_tide_h:.2f}m ({tide_class})' if best_tide_h is not None else '—'

    # Nearby tide extrema (high/low) for context
    tide_context = ''
    if dt_utc is not None:
        try:
            nearby_ext = find_extrema(
                dt_utc - timedelta(hours=6),
                dt_utc + timedelta(hours=6),
            )
            tstate = tide_state(dt_utc, nearby_ext)
            tide_context = tstate
            # Find nearest high/low for display
            for ex in nearby_ext:
                tide_context += f' · {ex["type"].title()} {ex["cst"]} ({ex["height_m"]:.2f}m)'
        except Exception:
            pass

    # Wind quality at best time
    wq = dir_quality(best_rec.get('w_dir'), spot['opt_wind'])
    sq = dir_quality(best_rec.get('sw_dir'), spot['opt_swell'])

    return {
        'score': best_score,
        'window': window_lbl,
        'time': time_lbl,
        'sw_hs': best_rec.get('sw_hs'),
        'sw_tp': best_rec.get('sw_tp'),
        'sw_dir': best_rec.get('sw_dir'),
        'sw_dir_compass': compass(best_rec.get('sw_dir')),
        'swell_quality': sq,
        'wind_kt': best_rec.get('wind'),
        'w_dir': best_rec.get('w_dir'),
        'w_dir_compass': compass(best_rec.get('w_dir')),
        'wind_quality': wq,
        'gust_kt': best_rec.get('gust'),
        'tide_height_m': best_tide_h,
        'tide_class': tide_class,
        'tide_str': tide_str,
        'tide_context': tide_context,
        'dt_utc': dt_utc,
        'dt_cst': dt_cst,
        'sunrise_cst': f'{int(sunrise_cst):02d}:{int((sunrise_cst % 1) * 60):02d}' if sunrise_cst is not None else None,
        'sunset_cst': f'{int(sunset_cst):02d}:{int((sunset_cst % 1) * 60):02d}' if sunset_cst is not None else None,
    }


def sail_day_rating(day_recs: list[dict]) -> dict[str, object]:
    """Evaluate daily sailing conditions at Keelung."""
    if not day_recs:
        return {'label': '—',          'emoji': '❓', 'bg': '#1a2236', 'col': '#475569'}
    max_w  = max((r.get('wind')   or 0) for r in day_recs)
    max_g  = max((r.get('gust')   or 0) for r in day_recs)
    max_hs = max((r.get('hs')     or 0) for r in day_recs)
    tot_r  = sum((r.get('rain6h') or 0) for r in day_recs)
    return sail_rating(max_w, max_g, max_hs, tot_r)


def _recommend(sail_rat: dict, best_surf_rat: dict, best_surf_name: str,
               best_surf_name_zh: str = '') -> tuple[str, str]:
    """
    Returns (recommendation_text, background_colour) for the planner table.
    recommendation_text contains bilingual spans.
    best_surf_name: English short name (e.g. "Jinshan")
    best_surf_name_zh: Chinese name (e.g. "金山")
    """
    name_zh = best_surf_name_zh or best_surf_name
    sail_emoji = sail_rat['emoji']   # 🟢 🟡 🔴 ❓
    surf_emoji = best_surf_rat['emoji']  # 🔥 🟢 🟡 🔴 😴 ❓
    can_sail  = sail_emoji == '🟢'
    marg_sail = sail_emoji == '🟡'
    good_surf = surf_emoji in ('🔥', '🟢')
    fire_surf = surf_emoji == '🔥'
    marg_surf = surf_emoji == '🟡'

    if can_sail and fire_surf:
        return bilingual(f'⛵ Sail or 🏄 Surf: {best_surf_name}',
                         f'⛵ 航行或 🏄 衝浪：{name_zh}'), '#0d2d1a'
    if can_sail and good_surf:
        return bilingual(f'⛵ Go sailing or 🏄 Surf: {best_surf_name}',
                         f'⛵ 航行或 🏄 衝浪：{name_zh}'), '#0d2d1a'
    if can_sail:
        return T('rec_sail'), '#0d2d1a'
    if fire_surf:
        return bilingual(f'🏄 Surf: {best_surf_name}',
                         f'🏄 衝浪：{name_zh}'), '#0d3320'
    if good_surf:
        return bilingual(f'🏄 Surf: {best_surf_name}',
                         f'🏄 衝浪：{name_zh}'), '#0d2d1a'
    if marg_sail and marg_surf:
        return bilingual(f'🟡 Marginal — maybe surf: {best_surf_name}',
                         f'🟡 勉強 — 或許可衝：{name_zh}'), '#3d2e00'
    if marg_sail:
        return T('rec_marginal_sail'), '#3d2e00'
    if marg_surf:
        return bilingual(f'🟡 Maybe surf: {best_surf_name}',
                         f'🟡 或許可衝浪：{name_zh}'), '#3d2e00'
    return T('rec_stay_home'), '#3d1515'


# ── Planner JSON output ────────────────────────────────────────────────────

def generate_planner_json(all_spot_data: list[dict], keelung_records: list = None) -> dict:
    """
    Generate machine-readable planner data for each day.
    Returns dict: {"days": {"2026-03-22": {"sail": {...}, "best_surf": {...}, "recommendation": {...}}, ...}}
    """
    all_dks = sorted({r['dk'] for sd in all_spot_data for r in sd['records']})

    keelung_by_day = {}
    if keelung_records:
        for r in keelung_records:
            keelung_by_day.setdefault(r['dk'], []).append(r)

    surf_by_day_spot = {}
    for sd in all_spot_data:
        by_day = {}
        for r in sd['records']:
            by_day.setdefault(r['dk'], []).append(r)
        for dk, recs in by_day.items():
            surf_by_day_spot.setdefault(dk, []).append((sd['spot'], recs))

    days = {}
    for dk in all_dks:
        sail_recs = keelung_by_day.get(dk, [])
        sail_rat = sail_day_rating(sail_recs)

        best_surf_rat = {'label': '—', 'emoji': '😴', 'bg': '#1a2236', 'col': '#475569'}
        best_surf_name = '—'
        best_surf_name_zh = '—'
        rank_order = {'🔥': 4, '🟢': 3, '🟡': 2, '🔴': 1, '😴': 0, '❓': 0}
        best_rank = -1
        for spot, recs in surf_by_day_spot.get(dk, []):
            rat = day_rating(recs, spot)
            rank = rank_order.get(rat['emoji'], 0)
            if rank > best_rank:
                best_rank = rank
                best_surf_rat = rat
                best_surf_name, best_surf_name_zh = _split_spot_name(spot['name'])

        rec_text, rec_bg = _recommend(sail_rat, best_surf_rat, best_surf_name, best_surf_name_zh)

        # Best time per spot for this day
        spot_times = []
        for spot, recs in surf_by_day_spot.get(dk, []):
            bt = best_time_for_day(recs, spot)
            if bt is not None:
                spot_times.append({
                    'spot': spot['name'].split()[0],
                    'window': bt['window'],
                    'score': bt['score'],
                    'sw_hs': bt['sw_hs'],
                    'sw_tp': bt['sw_tp'],
                    'wind_kt': bt['wind_kt'],
                    'tide_height_m': bt['tide_height_m'],
                    'tide_class': bt['tide_class'],
                })
        # Sort by score descending
        spot_times.sort(key=lambda x: x['score'], reverse=True)

        days[dk] = {
            'sail': sail_rat,
            'best_surf': {
                'spot': best_surf_name,
                'label': best_surf_rat['label'],
                'emoji': best_surf_rat['emoji'],
                'bg': best_surf_rat['bg'],
                'col': best_surf_rat['col'],
            },
            'recommendation': {'text': rec_text, 'bg': rec_bg},
            'spot_times': spot_times,
        }

    return {'days': days}


# ── HTML generation ────────────────────────────────────────────────────────
CSS = """
<style>
.surf-section {
  font-family: Arial, 'Helvetica Neue', sans-serif;
  font-size: 14px;
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
/* ── Sticky navigation bar ─────────────────────────────────── */
.surf-nav {
  position: sticky;
  top: 0;
  z-index: 10;
  background: #1e293b;
  padding: 6px 10px;
  margin: 0 -16px 12px;
  overflow-x: auto;
  white-space: nowrap;
  font-size: 12px;
  border-bottom: 1px solid #2d3f5a;
  -webkit-overflow-scrolling: touch;
}
.surf-nav a {
  color: #93c5fd;
  text-decoration: none;
  padding: 3px 8px;
  border-radius: 3px;
}
.surf-nav a:hover { background: #2d3f5a; }
.surf-nav .sep { color: #475569; margin: 0 2px; }
/* ── Tables ────────────────────────────────────────────────── */
.matrix-table {
  border-collapse: collapse;
  width: 100%;
  margin-bottom: 20px;
}
.matrix-table th {
  background: #1e3a5f;
  color: #7db8f0;
  padding: 6px 10px;
  font-size: 11px;
  text-align: center;
  white-space: nowrap;
  border: 1px solid #2d3f5a;
  line-height: 1.4;
}
.matrix-table th.spot-hdr {
  text-align: left;
  min-width: 110px;
}
.matrix-table td {
  padding: 6px 10px;
  text-align: center;
  border: 1px solid #1e293b;
  font-size: 12px;
  white-space: nowrap;
  line-height: 1.4;
  border-radius: 4px;
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
  margin-top: 24px;
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
  font-size: 12px;
  margin-bottom: 16px;
}
.detail-table th {
  background: #1e3a5f;
  color: #7db8f0;
  padding: 5px 8px;
  text-align: center;
  white-space: nowrap;
  border: 1px solid #2d3f5a;
  line-height: 1.4;
}
.detail-table td {
  padding: 4px 8px;
  text-align: center;
  white-space: nowrap;
  border-bottom: 1px solid #151f30;
  background: #0f172a;
  line-height: 1.4;
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
/* ── Mobile responsiveness ─────────────────────────────────── */
@media (max-width: 600px) {
  .surf-section { padding: 8px; font-size: 12px; }
  .matrix-table { display: block; overflow-x: auto; -webkit-overflow-scrolling: touch; }
  .matrix-table th, .matrix-table td { padding: 3px 4px; font-size: 9px; }
  .matrix-table td.spot-name { white-space: normal; min-width: 80px !important; }
  .detail-table { display: block; overflow-x: auto; -webkit-overflow-scrolling: touch; }
  .detail-table th, .detail-table td { padding: 2px 3px; font-size: 9px; }
  .detail-header { font-size: 12px; }
  .surf-nav { font-size: 11px; padding: 5px 8px; }
  .surf-nav a { padding: 4px 10px; }  /* bigger touch targets */
}
/* ── Print-friendly overrides ──────────────────────────────── */
@media print {
  .surf-section { background: #fff !important; color: #000 !important; padding: 8px; }
  .surf-nav { display: none !important; }
  .surf-title, .detail-header { color: #000 !important; }
  .matrix-table th, .detail-table th { background: #eee !important; color: #000 !important; border: 1px solid #ccc !important; }
  .matrix-table td, .detail-table td { background: #fff !important; color: #000 !important; border: 1px solid #ccc !important; }
  .detail-table tr.r-alt td { background: #f5f5f5 !important; }
  .c-good { color: #16a34a !important; }
  .c-warn { color: #ca8a04 !important; }
  .c-danger { color: #dc2626 !important; }
  .legend-block { color: #555 !important; border-color: #ccc !important; }
  .detail-section { page-break-inside: avoid; }
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

def _generate_planner_html(all_spot_data: list[dict], keelung_records: list = None) -> str:
    """
    all_spot_data:    list of { 'spot': spot_dict, 'records': [record, ...] }
    keelung_records:  list of sailing records for Keelung (optional, for planner)
    """
    now_cst = datetime.now(timezone.utc) + timedelta(hours=8)
    gen_str = now_cst.strftime('%Y-%m-%d %H:%M CST')

    # Collect all day keys across all spots
    all_dks = sorted({r['dk'] for sd in all_spot_data for r in sd['records']})

    html = '<section id="surf" class="section surf-section">\n'
    html += '<h2 class="section-title"><span role="img" aria-label="Surfer">🏄</span> Taiwan Surf Forecast</h2>\n'
    html += f'<p class="section-subtitle">Generated {gen_str} · Data: ECMWF IFS025 + GFS + ECMWF WAM (Open-Meteo) · Source: swelleye.com</p>\n'

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

    html += '<div id="planner" style="margin-bottom:20px">\n'
    html += '<h3 style="font-size:14px;font-weight:700;color:#93c5fd;margin:0 0 6px"><span role="img" aria-label="Calendar">📅</span> Daily Activity Planner</h3>\n'
    html += '<div style="overflow-x:auto">\n'
    html += ('<table class="planner-table">\n'
             '<thead><tr>'
             f'<th scope="col" style="text-align:left;min-width:90px">{T("planner_day")}</th>'
             f'<th scope="col" style="min-width:110px">{T("planner_sailing")}</th>'
             f'<th scope="col" style="min-width:130px">{T("planner_best_surf")}</th>'
             f'<th scope="col" style="min-width:160px">{T("planner_rec")}</th>'
             '</tr></thead>\n<tbody>\n')

    for dk in all_dks:
        d    = datetime.strptime(dk, '%Y-%m-%d')
        dlbl = f'{WKDAY[d.weekday()]} {d.day} {MONTH[d.month-1]}'

        # Sailing rating
        sail_recs = keelung_by_day.get(dk, [])
        sail_rat  = sail_day_rating(sail_recs)

        # Best surf spot for this day
        best_surf_rat  = {'label': '—', 'emoji': '😴', 'bg': '#1a2236', 'col': '#475569'}
        best_surf_name = '—'
        best_surf_name_zh = '—'
        rank_order = {'🔥': 4, '🟢': 3, '🟡': 2, '🔴': 1, '😴': 0, '❓': 0}
        best_rank  = -1
        for spot, recs in surf_by_day_spot.get(dk, []):
            rat  = day_rating(recs, spot)
            rank = rank_order.get(rat['emoji'], 0)
            if rank > best_rank:
                best_rank      = rank
                best_surf_rat  = rat
                best_surf_name, best_surf_name_zh = _split_spot_name(spot['name'])

        rec_text, rec_bg = _recommend(sail_rat, best_surf_rat, best_surf_name, best_surf_name_zh)

        # Build details string for sailing cell
        max_w  = sail_rat.get('max_w')
        max_g  = sail_rat.get('max_g')
        max_hs = sail_rat.get('max_hs')
        sail_detail = ''
        if max_w is not None:
            sail_detail = f'<small style="color:#64748b;display:block">{round(max_w)}/{round(max_g)}kt · {max_hs:.1f}m</small>'

        # Bilingual labels for sail and surf ratings
        sail_bi = f'{sail_rat["emoji"]} {bilingual(sail_rat.get("label_en", ""), sail_rat.get("label_zh", ""))}'
        surf_label_key = best_surf_rat.get('label_key', '')
        surf_bi = T(surf_label_key) if surf_label_key else best_surf_rat.get('label', '')

        html += (f'<tr>'
                 f'<td style="text-align:left;font-weight:700;color:#cbd5e1">{dlbl}</td>'
                 f'<td style="background:{sail_rat["bg"]};color:{sail_rat["col"]}">'
                 f'{sail_bi}{sail_detail}</td>'
                 f'<td style="background:{best_surf_rat["bg"]};color:{best_surf_rat["col"]}">'
                 f'{best_surf_rat["emoji"]} {bilingual(best_surf_name, best_surf_name_zh)}'
                 f'<small style="color:#64748b;display:block">{surf_bi}</small></td>'
                 f'<td style="background:{rec_bg};color:#e2e8f0;font-weight:600">{rec_text}</td>'
                 f'</tr>\n')

    html += '</tbody></table>\n</div>\n</div>\n'

    return html


def _render_best_times(all_spot_data: list[dict], all_dks: list[str]) -> str:
    """Render a 'Best Time to Surf' section showing optimal window per spot per day."""
    html = '<div id="best-times" style="margin-bottom:20px">\n'
    html += '<h3 style="font-size:14px;font-weight:700;color:#93c5fd;margin:0 0 6px">'
    html += f'{T("best_time_surf")}</h3>\n'
    html += '<p style="font-size:10px;color:#64748b;margin:0 0 8px">'
    html += f'{T("best_time_desc")}</p>\n'

    for dk in all_dks:
        d = datetime.strptime(dk, '%Y-%m-%d')
        dlbl = f'{WKDAY[d.weekday()]} {d.day} {MONTH[d.month-1]}'

        html += f'<div style="margin-bottom:12px">\n'
        html += f'<h4 style="font-size:12px;font-weight:700;color:#cbd5e1;margin:0 0 4px">{dlbl}</h4>\n'

        # Compute tide extrema for this day (CST-based)
        try:
            day_start = datetime(d.year, d.month, d.day, tzinfo=timezone.utc) - timedelta(hours=8)
            day_end = day_start + timedelta(hours=24)
            day_extrema = find_extrema(day_start, day_end)
            if day_extrema:
                tide_pills = []
                for ex in day_extrema:
                    arrow = '&#9650;' if ex['type'] == 'high' else '&#9660;'
                    clr = '#93c5fd' if ex['type'] == 'high' else '#64748b'
                    tide_pills.append(
                        f'<span style="color:{clr};font-size:10px">'
                        f'{arrow} {ex["type"].title()} {ex["cst"]} ({ex["height_m"]:.2f}m)</span>')
                html += f'<div style="margin-bottom:4px;font-size:10px;color:#475569">Tides: {" · ".join(tide_pills)}</div>\n'
        except Exception:
            pass

        # Sunrise/sunset for this day (use Keelung as representative location)
        try:
            sr_utc, ss_utc = sunrise_sunset(d, KEELUNG_LAT, KEELUNG_LON)
            sr_cst = sr_utc + 8
            ss_cst = ss_utc + 8
            sr_str = f'{int(sr_cst):02d}:{int((sr_cst % 1) * 60):02d}'
            ss_str = f'{int(ss_cst):02d}:{int((ss_cst % 1) * 60):02d}'
            html += (f'<div style="margin-bottom:4px;font-size:10px;color:#475569">'
                     f'Daylight: '
                     f'<span style="color:#fbd38d">&#9788; {sr_str}</span>'
                     f' – '
                     f'<span style="color:#f97316">&#9790; {ss_str}</span>'
                     f'</div>\n')
        except Exception:
            pass

        html += '<div style="overflow-x:auto">\n'
        html += '<table class="detail-table" style="margin-bottom:4px">\n'
        html += ('<thead><tr>'
                 f'<th scope="col" style="text-align:left;min-width:100px">{T("th_spot")}</th>'
                 f'<th scope="col">{T("th_best_window")}</th>'
                 f'<th scope="col">{T("th_rating")}</th>'
                 f'<th scope="col" title="Swell height (m)">{T("th_swell")}</th>'
                 f'<th scope="col" title="Swell period (s)">{T("th_period")}</th>'
                 f'<th scope="col">{T("th_swell_dir")}</th>'
                 f'<th scope="col" title="Wind speed (kt)">{T("th_wind")}</th>'
                 f'<th scope="col">{T("th_wind_dir")}</th>'
                 f'<th scope="col" title="Tide height above chart datum">{T("th_tide")}</th>'
                 f'<th scope="col">{T("th_tide_state")}</th>'
                 '</tr></thead>\n<tbody>\n')

        row_i = 0
        for sd in all_spot_data:
            spot = sd['spot']
            day_recs = [r for r in sd['records'] if r['dk'] == dk]
            bt = best_time_for_day(day_recs, spot)

            cls = 'r-alt' if row_i % 2 else ''

            if bt is None:
                # Flat / dangerous / no data
                rating = day_rating(day_recs, spot)
                label_key = rating.get('label_key', '')
                bi_label = T(label_key) if label_key else rating['label']
                html += (f'<tr class="{cls}">'
                         f'<td style="text-align:left;color:#94a3b8">{spot["name"]}</td>'
                         f'<td colspan="9" style="color:{rating["col"]};background:{rating["bg"]}">'
                         f'{rating["emoji"]} {bi_label}</td></tr>\n')
            else:
                # Determine rating label from score
                s = bt['score']
                if s >= 9:
                    rlbl, remoji, rbg, rcol = T('firing'), '🔥', '#0d3320', '#48bb78'
                elif s >= 7:
                    rlbl, remoji, rbg, rcol = T('good'), '🟢', '#0d2d1a', '#68d391'
                elif s >= 4:
                    rlbl, remoji, rbg, rcol = T('marginal'), '🟡', '#3d2e00', '#fbd38d'
                else:
                    rlbl, remoji, rbg, rcol = T('poor'), '🔴', '#3d1515', '#fc8181'

                # Swell direction styling
                sw_dir_str = bt['sw_dir_compass']
                if bt['swell_quality'] == 'good':
                    sw_dir_str = f'<b class="c-good">{sw_dir_str}</b>'
                elif bt['swell_quality'] == 'poor':
                    sw_dir_str = f'<span class="c-danger">{sw_dir_str}</span>'

                # Wind direction styling
                w_dir_str = bt['w_dir_compass']
                if bt['wind_quality'] == 'good':
                    w_dir_str = f'<b class="c-good">{w_dir_str}</b>'
                elif bt['wind_quality'] == 'poor':
                    w_dir_str = f'<span class="c-warn">{w_dir_str}</span>'

                # Tide class styling
                opt_tide = spot.get('opt_tide', 'any')
                ts = tide_score(bt['tide_class'], opt_tide)
                if ts > 0:
                    tide_cls = 'c-good'
                elif ts < 0:
                    tide_cls = 'c-danger'
                else:
                    tide_cls = ''

                # Tide state (rising/falling)
                tstate = bt.get('tide_context', '').split(' · ')[0] if bt.get('tide_context') else ''

                html += (f'<tr class="{cls}">'
                         f'<td style="text-align:left;color:#94a3b8">{spot["name"]}</td>'
                         f'<td style="font-weight:700;color:#e2e8f0">{bt["window"]}</td>'
                         f'<td style="background:{rbg};color:{rcol}">{remoji} {rlbl}</td>'
                         f'<td class="{_hs_cls(bt["sw_hs"])}">{_f1(bt["sw_hs"])}</td>'
                         f'<td>{_f1(bt["sw_tp"])}</td>'
                         f'<td>{sw_dir_str}</td>'
                         f'<td class="{_wind_cls(bt["wind_kt"])}">{_f0(bt["wind_kt"])}</td>'
                         f'<td>{w_dir_str}</td>'
                         f'<td class="{tide_cls}">{bt["tide_str"]}</td>'
                         f'<td style="font-size:10px;color:#94a3b8">{tstate}</td>'
                         f'</tr>\n')
            row_i += 1

        html += '</tbody></table>\n</div>\n</div>\n'

    html += '</div>\n'
    return html


def _render_rating_matrix(all_spot_data: list[dict], all_dks: list[str]) -> str:
    """Return the 7-day rating matrix table HTML."""
    html = '<div id="matrix" style="overflow-x:auto">\n'
    html += '<table class="matrix-table">\n'
    html += f'<caption class="c-muted" style="caption-side:top;text-align:left;font-size:10px;margin-bottom:4px">{T("rating_caption")}</caption>\n'
    html += '<thead><tr>'
    html += f'<th scope="col" class="spot-hdr">{T("th_spot")}</th>'
    for dk in all_dks:
        d = datetime.strptime(dk, '%Y-%m-%d')
        html += f'<th scope="col">{WKDAY[d.weekday()]}<br>{d.day} {MONTH[d.month-1]}</th>'
    html += '</tr></thead>\n<tbody>\n'

    for sd in all_spot_data:
        spot    = sd['spot']
        records = sd['records']
        by_day  = {}
        for r in records:
            by_day.setdefault(r['dk'], []).append(r)

        html += '<tr>'
        spot_desc_bi = bilingual(spot["desc"], spot.get("desc_zh", spot["desc"]))
        html += (f'<td scope="row" class="spot-name">{spot["name"]}'
                 f'<small>{spot_desc_bi}</small></td>')

        for dk in all_dks:
            day_recs = by_day.get(dk, [])
            rating   = day_rating(day_recs, spot)
            conf_tag = ' <span title="High model uncertainty" style="opacity:0.6">\u00b1</span>' \
                       if rating.get('confidence') == 'low' else ''
            label_key = rating.get('label_key', '')
            bi_label = T(label_key) if label_key else rating['label']
            html += (f'<td style="background:{rating["bg"]};color:{rating["col"]}">'
                     f'<span role="img" aria-label="{rating["label"]}">{rating["emoji"]}</span> {bi_label}{conf_tag}</td>')
        html += '</tr>\n'

    html += '</tbody></table>\n</div>\n'
    return html


def _render_spot_detail(sd: dict) -> str:
    """Return the collapsible detail table HTML for one spot."""
    spot    = sd['spot']
    records = sd['records']
    if not records:
        return ''

    html = f'<details id="spot-{spot["id"]}" class="detail-section">\n'
    html += f'<summary class="detail-header">{spot["name"]} — {T("detailed_forecast")}</summary>\n'
    html += '<div style="overflow-x:auto">\n'
    html += '<table class="detail-table">\n'
    html += ('<thead><tr>'
             '<th scope="col">CST</th>'
             f'<th scope="col">{T("th_rating")}</th>'
             f'<th scope="col" title="Swell wave height in metres">{T("th_swell_m")}</th>'
             f'<th scope="col" title="Wave period in seconds — longer = more powerful">{T("th_t_s")}</th>'
             f'<th scope="col" title="Swell direction — where waves come from">{T("th_sw_dir")}</th>'
             f'<th scope="col" title="Significant wave height in metres (combined sea state)">{T("th_hs_m")}</th>'
             f'<th scope="col" title="Wind speed in knots (1 kt = 1.85 km/h)">{T("th_wind_kt")}</th>'
             f'<th scope="col" title="Wind direction — where wind blows from">{T("th_w_dir")}</th>'
             f'<th scope="col" title="Maximum wind gust speed in knots">{T("th_gust_short")}</th>'
             f'<th scope="col" title="Tide height above chart datum">{T("th_tide")}</th>'
             '</tr></thead>\n<tbody>\n')

    prev_dk = None
    row_i   = 0
    for r in records:
        dk = r['dk']
        if dk != prev_dk:
            prev_dk = dk
            row_i   = 0
            d       = datetime.strptime(dk, '%Y-%m-%d')
            dl      = f'{WKDAY[d.weekday()]} {d.day} {MONTH[d.month-1]}'
            html += f'<tr><td class="date-sep" colspan="10">📅 {dl}</td></tr>\n'

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

        # Tide at this timestep
        dt_utc = r.get('dt_utc')
        tide_h = _tide_height(dt_utc) if dt_utc is not None else None
        tide_cls_str = classify_tide(tide_h)
        opt_tide = spot.get('opt_tide', 'any')
        ts_val = tide_score(tide_cls_str, opt_tide)
        tide_css = 'c-good' if ts_val > 0 else ('c-danger' if ts_val < 0 else '')
        tide_disp = f'{tide_h:.2f}m' if tide_h is not None else '—'

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
                 f'<td class="{tide_css}">{tide_disp}</td>'
                 f'</tr>\n')
        row_i += 1

    html += '</tbody></table>\n</div>\n'  # close table + overflow wrapper
    html += '</details>\n'  # close detail collapsible
    return html


def _render_surf_legend() -> str:
    """Return the surf legend block HTML."""
    return ('<div class="legend-block">'
            f'<b>{T("surf_key")}:</b> '
            f'<span role="img" aria-label="Firing">🔥</span> {T("surf_firing_desc")} · '
            f'<span role="img" aria-label="Good">🟢</span> {T("good")} · '
            f'<span role="img" aria-label="Marginal">🟡</span> {T("marginal")} · '
            f'<span role="img" aria-label="Poor or Dangerous">🔴</span> {T("surf_poor_dangerous")} · '
            f'<span role="img" aria-label="Flat">😴</span> {T("surf_flat_desc")}<br>'
            f'{T("dir_ticks")}: <b class="c-good">✓ {T("dir_optimal")}</b> · '
            f'<span class="c-danger">✗ {T("dir_unfavourable")}</span><br>'
            f'{T("swell_colour")}: <span class="c-good">green 0.6–2.5m</span> · '
            '<span class="c-warn">amber &gt;2.5m</span> · '
            '<span class="c-danger">red &gt;3.5m</span><br>'
            f'<b>{T("legend_wind")}:</b> {T("surf_bf_gentle")} · {T("surf_bf_moderate")} · '
            f'{T("surf_bf_fresh")} · {T("surf_bf_strong")} · {T("surf_bf_near_gale")} · {T("surf_bf_gale")}'
            '</div>\n')


def generate_full_html(all_spot_data: list[dict], keelung_records: list = None) -> str:
    """
    Full HTML: 7-spot rating matrix + per-spot hourly detail tables + legend.
    The planner data is now output as JSON (generate_planner_json) and merged
    into the unified day cards by wrf_analyze.py.
    """
    now_cst = datetime.now(timezone.utc) + timedelta(hours=8)
    gen_str = now_cst.strftime('%Y-%m-%d %H:%M CST')
    all_dks = sorted({r['dk'] for sd in all_spot_data for r in sd['records']})

    html = '<section id="spots" class="section surf-section">\n'
    html += f'<h2 class="section-title"><span role="img" aria-label="Surfer">🏄</span> {T("surf_spots")}</h2>\n'
    html += f'<p class="section-subtitle">Generated {gen_str} · Data: ECMWF IFS025 + GFS + ECMWF WAM (Open-Meteo)</p>\n'

    # ── Best time to surf ─────────────────────────────────────────────────
    html += _render_best_times(all_spot_data, all_dks)

    # ── Rating matrix ──────────────────────────────────────────────────────
    html += _render_rating_matrix(all_spot_data, all_dks)

    # ── Per-spot detail tables ─────────────────────────────────────────────
    html += '<div class="detail-section">\n'
    for sd in all_spot_data:
        html += _render_spot_detail(sd)

    # ── Legend ─────────────────────────────────────────────────────────────
    html += _render_surf_legend()

    html += '</section>\n'  # close spots section
    return html


# ── Main ───────────────────────────────────────────────────────────────────
def main() -> None:
    global _CWA_TIDE_EXTREMA

    ap = argparse.ArgumentParser(description='Taiwan surf forecast')
    ap.add_argument('--output', default='surf_forecast.html',
                    help='Output HTML path (default: surf_forecast.html)')
    ap.add_argument('--output-json', default=None,
                    help='Output planner JSON path (optional, for unified day cards)')
    ap.add_argument('--cwa-obs', default=None,
                    help='CWA obs JSON (for tide forecast anchoring)')
    args = ap.parse_args()

    # Load CWA tide forecast for anchored tide predictions
    if args.cwa_obs:
        from config import load_json_file
        cwa = load_json_file(args.cwa_obs, "CWA obs")
        if cwa and cwa.get("tide_forecast"):
            _CWA_TIDE_EXTREMA = cwa["tide_forecast"]
            log.info("Loaded %d CWA tide extrema for anchored predictions",
                     len(_CWA_TIDE_EXTREMA))
    elif os.path.exists("cwa_obs.json"):
        from config import load_json_file
        cwa = load_json_file("cwa_obs.json", "CWA obs")
        if cwa and cwa.get("tide_forecast"):
            _CWA_TIDE_EXTREMA = cwa["tide_forecast"]
            log.info("Auto-loaded %d CWA tide extrema from cwa_obs.json",
                     len(_CWA_TIDE_EXTREMA))

    # ── Fetch all spots in parallel (Keelung sailing + 7 surf spots) ─────
    def _fetch_and_process(spot_entry):
        lat, lon = spot_entry['lat'], spot_entry['lon']
        name = spot_entry.get('name', 'Keelung')
        log.info("Fetching %s …", name)
        ec, gfs, mar = fetch_spot(lat, lon)
        records = process_spot(ec, gfs, mar)
        log.info("  %s → %d timesteps", name, len(records))
        return spot_entry, records

    all_entries = [{'lat': KEELUNG['lat'], 'lon': KEELUNG['lon'],
                    'name': 'Keelung (sailing)', '_is_keelung': True}]
    all_entries += [{'_is_keelung': False, **s} for s in SPOTS]

    keelung_records = []
    all_spot_data = []
    failed_count = 0
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(_fetch_and_process, e): e for e in all_entries}
        for future in as_completed(futures):
            try:
                entry, records = future.result()
            except Exception as e:
                spot_name = futures[future].get('name', 'unknown')
                log.error("Failed to process %s: %s", spot_name, e)
                failed_count += 1
                continue
            if entry.get('_is_keelung'):
                keelung_records = records
            else:
                # Reconstruct the original spot dict (without internal keys)
                spot = {k: v for k, v in entry.items() if not k.startswith('_')}
                all_spot_data.append({'spot': spot, 'records': records})

    if failed_count > len(all_entries) // 2:
        log.error("More than half of spot fetches failed (%d/%d) — aborting",
                  failed_count, len(all_entries))
        sys.exit(1)
    if not all_spot_data:
        log.error("No surf spot data fetched — aborting")
        sys.exit(1)

    # Preserve original spot ordering
    spot_order = {s['id']: i for i, s in enumerate(SPOTS)}
    all_spot_data.sort(key=lambda d: spot_order.get(d['spot'].get('id'), 99))

    html_full = generate_full_html(all_spot_data, keelung_records=keelung_records)
    with open(args.output, 'w', encoding='utf-8') as f:
        f.write(html_full)
    log.info("Wrote %s (%s chars)", args.output, f"{len(html_full):,}")

    if args.output_json:
        import json as json_mod
        planner_data = generate_planner_json(all_spot_data, keelung_records=keelung_records)
        with open(args.output_json, 'w', encoding='utf-8') as f:
            json_mod.dump(planner_data, f, ensure_ascii=False, indent=2)
        log.info("Wrote planner JSON: %s", args.output_json)

if __name__ == '__main__':
    setup_logging()
    main()
