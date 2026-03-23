#!/usr/bin/env python3
"""
accuracy_track.py — Track forecast accuracy over time.

Compares the most recent WRF forecast against actual observations from
Open-Meteo's historical weather API (which provides CWA/JMA station data
for Taiwan).  Optionally compares wave forecasts against Open-Meteo marine
observations.  Stores accuracy metrics in accuracy_log.json on Google Drive.

Intended to be run after each forecast cycle to build a rolling accuracy
history.  The pipeline can then display a "model accuracy" badge on the
web app.

Usage:
    python accuracy_track.py \
        --forecast-json keelung_summary.json \
        [--wave-json wave_keelung.json] \
        [--output accuracy_log.json] \
        [--existing-log accuracy_log.json]
"""

import argparse
import json
import logging
import math
import os
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from config import KEELUNG_LAT, KEELUNG_LON, norm_utc, setup_logging

log = logging.getLogger(__name__)

OPEN_METEO_HISTORY = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_MARINE = "https://marine-api.open-meteo.com/v1/marine"

# Forecast-hour bin edges (hours)
HORIZON_BINS = [
    ("0-24h",  0,  24),
    ("24-48h", 24, 48),
    ("48-72h", 48, 72),
    ("72h+",   72, 9999),
]


def fetch_observations(start_date: str, end_date: str) -> dict:
    """Fetch recent observed weather from Open-Meteo for the Keelung point.

    Uses the best_match model which blends station observations with model
    reanalysis to give the closest-to-observed values.
    """
    params = {
        'latitude':        KEELUNG_LAT,
        'longitude':       KEELUNG_LON,
        'hourly':          'temperature_2m,wind_speed_10m,wind_direction_10m,'
                           'precipitation,pressure_msl',
        'wind_speed_unit': 'kn',
        'timezone':        'UTC',
        'start_date':      start_date,
        'end_date':        end_date,
        'models':          'best_match',
    }
    url = OPEN_METEO_HISTORY + '?' + urllib.parse.urlencode(params)
    log.info("Fetching observations %s → %s …", start_date, end_date)
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return json.load(r)
    except Exception as e:
        log.error("Failed to fetch observations: %s", e)
        return {}


def fetch_wave_observations(start_date: str, end_date: str) -> dict:
    """Fetch recent wave observations from Open-Meteo marine API."""
    params = {
        'latitude':   KEELUNG_LAT,
        'longitude':  KEELUNG_LON,
        'hourly':     'wave_height,wave_period,wave_direction',
        'timezone':   'UTC',
        'start_date': start_date,
        'end_date':   end_date,
    }
    url = OPEN_METEO_MARINE + '?' + urllib.parse.urlencode(params)
    log.info("Fetching wave observations %s → %s …", start_date, end_date)
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return json.load(r)
    except Exception as e:
        log.error("Failed to fetch wave observations: %s", e)
        return {}


def fetch_cwa_observations(api_key: str) -> dict | None:
    """Fetch current CWA station + buoy observations for live verification.

    Returns a dict that can overlay/supplement Open-Meteo obs, keyed the same
    way as the Open-Meteo obs_by_time dict.  If the CWA API is unavailable,
    returns None (caller falls back to Open-Meteo).
    """
    try:
        from cwa_fetch import fetch_station_obs, fetch_buoy_obs
    except ImportError:
        log.debug("cwa_fetch module not available")
        return None

    result = {"station": None, "buoy": None}

    station = fetch_station_obs(api_key)
    if station and station.get("obs_time"):
        result["station"] = station
        log.info("CWA station obs: %s at %s", station.get("station_name"),
                 station["obs_time"])

    buoy = fetch_buoy_obs(api_key)
    if buoy and buoy.get("obs_time"):
        result["buoy"] = buoy
        log.info("CWA buoy obs: %s Hs=%.1fm",
                 buoy.get("buoy_name"), buoy.get("wave_height_m") or 0)

    return result


# ── Metric helpers ────────────────────────────────────────────────────────

def _mae(errors: list) -> float | None:
    return round(sum(abs(e) for e in errors) / len(errors), 2) if errors else None


def _bias(errors: list) -> float | None:
    return round(sum(errors) / len(errors), 2) if errors else None


def _rmse(errors: list) -> float | None:
    return round(math.sqrt(sum(e**2 for e in errors) / len(errors)), 2) if errors else None


def _circular_diff(a: float, b: float) -> float:
    """Signed angular difference in range [-180, 180]."""
    d = (a - b) % 360
    return d - 360 if d > 180 else d


def _circular_mae(errors_deg: list) -> float | None:
    """MAE for angular values (0-360)."""
    if not errors_deg:
        return None
    return round(sum(abs(e) for e in errors_deg) / len(errors_deg), 2)


def _fh_bin(fh: int) -> str:
    """Map forecast hour to bin label."""
    for label, lo, hi in HORIZON_BINS:
        if lo <= fh < hi:
            return label
    return "72h+"


def _compute_bin_metrics(bin_errors: dict) -> dict:
    """Compute metrics for a single forecast-hour bin."""
    result = {'n': bin_errors.get('n', 0)}
    for var in ('temp', 'wind', 'wdir', 'precip', 'mslp'):
        errs = bin_errors.get(var, [])
        if var == 'wdir':
            result[f'{var}_mae'] = _circular_mae(errs)
        else:
            result[f'{var}_mae'] = _mae(errs)
            result[f'{var}_bias'] = _bias(errs)
    return result


# ── Main accuracy computation ─────────────────────────────────────────────

def compute_accuracy(forecast_records: list, obs_raw: dict,
                     wave_forecast: list | None = None,
                     wave_obs_raw: dict | None = None) -> dict | None:
    """Compare forecast records against observations, return accuracy metrics.

    Returns a dict with 'overall' and 'by_horizon' keys containing expanded
    metrics for temperature, wind speed, wind direction, precipitation, and
    pressure.  Optionally includes wave metrics if wave data is provided.
    """
    obs_h = obs_raw.get('hourly', {})
    obs_times = obs_h.get('time', [])
    if not obs_times or not forecast_records:
        return None

    # Build observation lookup by normalised time
    obs_by_time = {}
    obs_temp = obs_h.get('temperature_2m', [])
    obs_wind = obs_h.get('wind_speed_10m', [])
    obs_wdir = obs_h.get('wind_direction_10m', [])
    obs_rain = obs_h.get('precipitation', [])
    obs_mslp = obs_h.get('pressure_msl', [])

    for i, t in enumerate(obs_times):
        key = norm_utc(t)
        obs_by_time[key] = {
            'temp_c':    obs_temp[i] if i < len(obs_temp) else None,
            'wind_kt':   obs_wind[i] if i < len(obs_wind) else None,
            'wind_dir':  obs_wdir[i] if i < len(obs_wdir) else None,
            'precip_mm': obs_rain[i] if i < len(obs_rain) else None,
            'mslp_hpa':  obs_mslp[i] if i < len(obs_mslp) else None,
        }

    # Error accumulators — overall and per-bin
    temp_errors = []
    wind_errors = []
    wdir_errors = []
    precip_errors = []
    mslp_errors = []
    n_compared = 0

    bins = {label: {'n': 0, 'temp': [], 'wind': [], 'wdir': [],
                     'precip': [], 'mslp': []}
            for label, _, _ in HORIZON_BINS}

    for rec in forecast_records:
        vt = rec.get('valid_utc')
        if not vt or vt not in obs_by_time:
            continue
        obs = obs_by_time[vt]
        n_compared += 1

        fh = rec.get('fh', 0)
        bk = _fh_bin(fh)

        # Temperature
        ft = rec.get('temp_c')
        ot = obs.get('temp_c')
        if ft is not None and ot is not None:
            err = ft - ot
            temp_errors.append(err)
            bins[bk]['temp'].append(err)

        # Wind speed
        fw = rec.get('wind_kt')
        ow = obs.get('wind_kt')
        if fw is not None and ow is not None:
            err = fw - ow
            wind_errors.append(err)
            bins[bk]['wind'].append(err)

        # Wind direction (circular)
        fd = rec.get('wind_dir')
        od = obs.get('wind_dir')
        if fd is not None and od is not None:
            err = _circular_diff(fd, od)
            wdir_errors.append(err)
            bins[bk]['wdir'].append(err)

        # Precipitation
        fp = rec.get('precip_mm_6h')
        op = obs.get('precip_mm')
        if fp is not None and op is not None:
            # Obs is hourly; forecast is 6h total — compare directly
            # (obs at 6h mark represents that hour only, but it's the best
            # point comparison available without summing hourly obs)
            err = fp - op
            precip_errors.append(err)
            bins[bk]['precip'].append(err)

        # Pressure
        fm = rec.get('mslp_hpa')
        om = obs.get('mslp_hpa')
        if fm is not None and om is not None:
            err = fm - om
            mslp_errors.append(err)
            bins[bk]['mslp'].append(err)

        bins[bk]['n'] += 1

    if not temp_errors and not wind_errors:
        return None

    overall = {
        'n_compared':    n_compared,
        'temp_mae_c':    _mae(temp_errors),
        'temp_bias_c':   _bias(temp_errors),
        'temp_rmse_c':   _rmse(temp_errors),
        'wind_mae_kt':   _mae(wind_errors),
        'wind_bias_kt':  _bias(wind_errors),
        'wind_rmse_kt':  _rmse(wind_errors),
        'wdir_mae_deg':  _circular_mae(wdir_errors),
        'precip_mae_mm': _mae(precip_errors),
        'precip_bias_mm': _bias(precip_errors),
        'mslp_mae_hpa':  _mae(mslp_errors),
        'mslp_bias_hpa': _bias(mslp_errors),
    }

    by_horizon = {}
    for label, _, _ in HORIZON_BINS:
        bdata = bins[label]
        if bdata['n'] > 0:
            by_horizon[label] = _compute_bin_metrics(bdata)

    result = {'overall': overall, 'by_horizon': by_horizon}

    # Wave verification (optional)
    if wave_forecast and wave_obs_raw:
        wave_metrics = _compute_wave_accuracy(wave_forecast, wave_obs_raw)
        if wave_metrics:
            result['wave'] = wave_metrics

    return result


def _compute_wave_accuracy(wave_forecast: list, wave_obs_raw: dict) -> dict | None:
    """Compare wave forecast against marine observations."""
    obs_h = wave_obs_raw.get('hourly', {})
    obs_times = obs_h.get('time', [])
    if not obs_times:
        return None

    obs_hs = obs_h.get('wave_height', [])
    obs_tp = obs_h.get('wave_period', [])
    obs_wd = obs_h.get('wave_direction', [])

    obs_by_time = {}
    for i, t in enumerate(obs_times):
        key = norm_utc(t)
        obs_by_time[key] = {
            'hs': obs_hs[i] if i < len(obs_hs) else None,
            'tp': obs_tp[i] if i < len(obs_tp) else None,
            'wd': obs_wd[i] if i < len(obs_wd) else None,
        }

    hs_errors = []
    tp_errors = []
    wd_errors = []

    for rec in wave_forecast:
        vt = rec.get('valid_utc')
        if not vt or vt not in obs_by_time:
            continue
        obs = obs_by_time[vt]

        fhs = rec.get('hs')
        ohs = obs.get('hs')
        if fhs is not None and ohs is not None:
            hs_errors.append(fhs - ohs)

        ftp = rec.get('tp') or rec.get('sw_tp')
        otp = obs.get('tp')
        if ftp is not None and otp is not None:
            tp_errors.append(ftp - otp)

        fwd = rec.get('dir') or rec.get('sw_dir')
        owd = obs.get('wd')
        if fwd is not None and owd is not None:
            wd_errors.append(_circular_diff(fwd, owd))

    if not hs_errors:
        return None

    return {
        'n_compared':     len(hs_errors),
        'hs_mae_m':       _mae(hs_errors),
        'hs_bias_m':      _bias(hs_errors),
        'tp_mae_s':       _mae(tp_errors),
        'tp_bias_s':      _bias(tp_errors),
        'wdir_mae_deg':   _circular_mae(wd_errors),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description='Track forecast accuracy')
    ap.add_argument('--forecast-json', required=True,
                    help='WRF forecast summary JSON')
    ap.add_argument('--wave-json', default=None,
                    help='Wave forecast JSON (optional)')
    ap.add_argument('--output', default='accuracy_log.json',
                    help='Output accuracy log JSON (default: accuracy_log.json)')
    ap.add_argument('--existing-log', default=None,
                    help='Existing accuracy log to append to')
    ap.add_argument('--cwa-key', default=os.environ.get('CWA_OPENDATA_KEY'),
                    help='CWA Open Data API key (or set CWA_OPENDATA_KEY env)')
    args = ap.parse_args()

    # Load forecast
    try:
        with open(args.forecast_json) as f:
            forecast = json.load(f)
    except Exception as e:
        log.error("Cannot read forecast JSON: %s", e)
        return

    meta = forecast.get('meta', {})
    records = forecast.get('records', [])
    init_utc = meta.get('init_utc')

    if not records or not init_utc:
        log.warning("No forecast records or init_utc — skipping accuracy check")
        return

    # Only compare records that are now in the past
    now = datetime.now(timezone.utc)
    past_records = []
    for r in records:
        try:
            vt = datetime.fromisoformat(r['valid_utc'])
            if vt < now - timedelta(hours=1):  # at least 1h old
                past_records.append(r)
        except (ValueError, KeyError):
            pass

    if not past_records:
        log.info("No past forecast records to verify yet")
        return

    # Determine observation window
    first_vt = min(r['valid_utc'] for r in past_records)
    last_vt = max(r['valid_utc'] for r in past_records)
    start_date = first_vt[:10]
    end_date = last_vt[:10]

    # Fetch observations
    obs = fetch_observations(start_date, end_date)
    if not obs:
        return

    # Optionally load wave forecast and fetch wave observations
    wave_forecast = None
    wave_obs = None
    if args.wave_json:
        try:
            with open(args.wave_json) as f:
                wave_data = json.load(f)
            wave_records = wave_data.get('ecmwf_wave', {}).get('records', [])
            if wave_records:
                wave_forecast = wave_records
                wave_obs = fetch_wave_observations(start_date, end_date)
        except Exception as e:
            log.warning("Could not load wave JSON: %s", e)

    # Fetch CWA real-time observations (station + buoy) if API key available
    cwa_obs = None
    if args.cwa_key:
        cwa_obs = fetch_cwa_observations(args.cwa_key)
        if cwa_obs:
            log.info("CWA observations fetched successfully")
    else:
        log.debug("No CWA API key — using Open-Meteo observations only")

    # Compute accuracy
    metrics = compute_accuracy(past_records, obs, wave_forecast, wave_obs)
    if not metrics:
        log.warning("No overlapping forecast/observation data")
        return

    overall = metrics['overall']
    entry = {
        'init_utc': init_utc,
        'verified_utc': now.isoformat(),
        'model_id': meta.get('model_id', 'unknown'),
        'n_forecast_records': len(past_records),
        **overall,
        'by_horizon': metrics.get('by_horizon', {}),
    }
    if 'wave' in metrics:
        entry['wave'] = metrics['wave']

    # Attach CWA real-time snapshot for archiving
    if cwa_obs:
        entry['cwa_snapshot'] = {}
        if cwa_obs.get('station'):
            stn = cwa_obs['station']
            entry['cwa_snapshot']['station'] = {
                'obs_time': stn.get('obs_time'),
                'temp_c': stn.get('temp_c'),
                'wind_kt': stn.get('wind_kt'),
                'wind_dir': stn.get('wind_dir'),
                'gust_kt': stn.get('gust_kt'),
                'pressure_hpa': stn.get('pressure_hpa'),
                'humidity_pct': stn.get('humidity_pct'),
            }
        if cwa_obs.get('buoy'):
            buoy = cwa_obs['buoy']
            entry['cwa_snapshot']['buoy'] = {
                'obs_time': buoy.get('obs_time'),
                'wave_height_m': buoy.get('wave_height_m'),
                'wave_period_s': buoy.get('wave_period_s'),
                'wave_dir': buoy.get('wave_dir'),
                'water_temp_c': buoy.get('water_temp_c'),
            }

    log.info("Accuracy: Temp MAE %.1f°C, Wind MAE %.1fkt, WDir MAE %.0f° (%d steps)",
             overall.get('temp_mae_c') or 0,
             overall.get('wind_mae_kt') or 0,
             overall.get('wdir_mae_deg') or 0,
             overall['n_compared'])

    # Load existing log and append
    log_entries = []
    if args.existing_log and Path(args.existing_log).exists():
        try:
            with open(args.existing_log) as f:
                log_entries = json.load(f)
        except json.JSONDecodeError as e:
            log.warning("Existing accuracy log corrupted (%s); starting fresh", e)

    # Update existing entry for same init_utc (re-verification with more data),
    # or append new entry
    updated = False
    for i, existing in enumerate(log_entries):
        if existing.get('init_utc') == init_utc:
            log_entries[i] = entry
            updated = True
            break
    if not updated:
        log_entries.append(entry)

    # Keep only last 30 days of entries (robust datetime comparison)
    cutoff = now - timedelta(days=30)
    pruned = []
    for e in log_entries:
        try:
            verified = datetime.fromisoformat(e.get('verified_utc', ''))
            if verified >= cutoff:
                pruned.append(e)
        except (ValueError, TypeError):
            pruned.append(e)  # keep entries we can't parse
    log_entries = pruned

    out = Path(args.output)
    out.write_text(json.dumps(log_entries, indent=2))
    log.info("Accuracy log → %s (%d entries)", out, len(log_entries))


if __name__ == '__main__':
    setup_logging()
    main()
