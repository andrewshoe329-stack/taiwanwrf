#!/usr/bin/env python3
"""
accuracy_track.py — Track forecast accuracy over time.

Compares the most recent WRF forecast against actual observations from
Open-Meteo's historical weather API (which provides CWA/JMA station data
for Taiwan).  Stores accuracy metrics in accuracy_log.json on Google Drive.

Intended to be run after each forecast cycle to build a rolling accuracy
history.  The pipeline can then display a "model accuracy" badge on the
web app.

Usage:
    python accuracy_track.py \
        --forecast-json keelung_summary.json \
        [--output accuracy_log.json] \
        [--existing-log accuracy_log.json]
"""

import argparse
import json
import logging
import math
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from config import KEELUNG_LAT, KEELUNG_LON, norm_utc, setup_logging

log = logging.getLogger(__name__)

OPEN_METEO_HISTORY = "https://api.open-meteo.com/v1/forecast"


def fetch_observations(start_date: str, end_date: str) -> dict:
    """Fetch recent observed weather from Open-Meteo for the Keelung point.

    Uses the best_match model which blends station observations with model
    reanalysis to give the closest-to-observed values.
    """
    params = {
        'latitude':        KEELUNG_LAT,
        'longitude':       KEELUNG_LON,
        'hourly':          'temperature_2m,wind_speed_10m,wind_direction_10m,precipitation',
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


def compute_accuracy(forecast_records: list, obs_raw: dict) -> dict | None:
    """Compare forecast records against observations, return accuracy metrics."""
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

    for i, t in enumerate(obs_times):
        key = norm_utc(t)
        obs_by_time[key] = {
            'temp_c': obs_temp[i] if i < len(obs_temp) else None,
            'wind_kt': obs_wind[i] if i < len(obs_wind) else None,
            'wind_dir': obs_wdir[i] if i < len(obs_wdir) else None,
            'precip_mm': obs_rain[i] if i < len(obs_rain) else None,
        }

    # Compare at overlapping timestamps
    temp_errors = []
    wind_errors = []
    n_compared = 0

    for rec in forecast_records:
        vt = rec.get('valid_utc')
        if not vt or vt not in obs_by_time:
            continue
        obs = obs_by_time[vt]
        n_compared += 1

        ft = rec.get('temp_c')
        ot = obs.get('temp_c')
        if ft is not None and ot is not None:
            temp_errors.append(ft - ot)

        fw = rec.get('wind_kt')
        ow = obs.get('wind_kt')
        if fw is not None and ow is not None:
            wind_errors.append(fw - ow)

    if not temp_errors and not wind_errors:
        return None

    def _mae(errors):
        return round(sum(abs(e) for e in errors) / len(errors), 2) if errors else None

    def _bias(errors):
        return round(sum(errors) / len(errors), 2) if errors else None

    def _rmse(errors):
        return round(math.sqrt(sum(e**2 for e in errors) / len(errors)), 2) if errors else None

    return {
        'n_compared': n_compared,
        'temp_mae_c': _mae(temp_errors),
        'temp_bias_c': _bias(temp_errors),
        'temp_rmse_c': _rmse(temp_errors),
        'wind_mae_kt': _mae(wind_errors),
        'wind_bias_kt': _bias(wind_errors),
        'wind_rmse_kt': _rmse(wind_errors),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description='Track forecast accuracy')
    ap.add_argument('--forecast-json', required=True,
                    help='WRF forecast summary JSON')
    ap.add_argument('--output', default='accuracy_log.json',
                    help='Output accuracy log JSON (default: accuracy_log.json)')
    ap.add_argument('--existing-log', default=None,
                    help='Existing accuracy log to append to')
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

    # Compute accuracy
    metrics = compute_accuracy(past_records, obs)
    if not metrics:
        log.warning("No overlapping forecast/observation data")
        return

    entry = {
        'init_utc': init_utc,
        'verified_utc': now.isoformat(),
        'model_id': meta.get('model_id', 'unknown'),
        'n_forecast_records': len(past_records),
        **metrics,
    }

    log.info("Accuracy: Temp MAE %.1f°C, Wind MAE %.1fkt (%d steps)",
             metrics.get('temp_mae_c') or 0, metrics.get('wind_mae_kt') or 0,
             metrics['n_compared'])

    # Load existing log and append
    log_entries = []
    if args.existing_log and Path(args.existing_log).exists():
        try:
            with open(args.existing_log) as f:
                log_entries = json.load(f)
        except json.JSONDecodeError as e:
            log.warning("Existing accuracy log corrupted (%s); starting fresh", e)

    # Avoid duplicate entries for the same init_utc
    existing_inits = {e.get('init_utc') for e in log_entries}
    if init_utc not in existing_inits:
        log_entries.append(entry)

    # Keep only last 30 days of entries
    cutoff = (now - timedelta(days=30)).isoformat()
    log_entries = [e for e in log_entries if e.get('verified_utc', '') > cutoff]

    out = Path(args.output)
    out.write_text(json.dumps(log_entries, indent=2))
    log.info("Accuracy log → %s (%d entries)", out, len(log_entries))


if __name__ == '__main__':
    setup_logging()
    main()
