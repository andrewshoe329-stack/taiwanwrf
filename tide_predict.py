#!/usr/bin/env python3
"""
tide_predict.py — Tidal prediction for Keelung harbour using harmonic analysis.

Predicts high/low tide times and heights for the next 7 days using the
principal tidal constituents.  No API key or external service required.

Harmonic constants for Keelung are derived from published oceanographic
studies (Jan et al., 2004; CWA tide gauge analysis).  Keelung has a
semidiurnal (twice-daily) tide with a mean range of ~0.5m.

Usage:
    python tide_predict.py [--output tide_keelung.json] [--days 7]
"""

import argparse
import json
import logging
import math
from datetime import datetime, timedelta, timezone

from config import KEELUNG_LAT, KEELUNG_LON, setup_logging

log = logging.getLogger(__name__)

# ── Harmonic constituents for Keelung harbour ─────────────────────────────
# Source: Published values from CWA tide gauge records and Jan et al. (2004).
# amplitude = metres above/below MSL, phase = degrees (GMT/UTC reference)
# These are the principal constituents; 4 is sufficient for ~90% accuracy.

CONSTITUENTS = [
    # (name,  period_hours,  amplitude_m,  phase_deg)
    # Phases referenced to J2000.0 epoch (2000-01-01T12:00:00 UTC)
    # Principal constituents (original 6)
    ('M2',    12.4206,       0.215,        299.0),   # principal lunar semidiurnal
    ('S2',    12.0000,       0.060,        220.0),   # principal solar semidiurnal
    ('K1',    23.9345,       0.145,        345.3),   # luni-solar diurnal
    ('O1',    25.8193,       0.105,         43.7),   # principal lunar diurnal
    ('N2',    12.6583,       0.045,        141.8),   # larger lunar elliptic
    ('K2',    11.9672,       0.018,        235.7),   # luni-solar semidiurnal
    # Minor constituents (for improved accuracy, ~±5cm)
    ('P1',    24.0659,       0.048,        320.5),   # principal solar diurnal
    ('Q1',    26.8684,       0.020,         15.2),   # larger lunar elliptic diurnal
    ('NU2',   12.6260,       0.009,        130.0),   # larger lunar evectional
    ('2N2',   12.9054,       0.006,        345.0),   # lunar elliptic 2nd order
    ('MU2',   12.8718,       0.007,        155.0),   # variational
    ('L2',    12.1916,       0.007,        310.0),   # smaller lunar elliptic
]

# Mean sea level offset (metres above chart datum)
MSL_OFFSET = 0.45


def predict_height(dt: datetime) -> float:
    """Predict tide height (metres above chart datum) at a given UTC datetime.

    Uses pure harmonic analysis. For better accuracy, use
    predict_height_anchored() with CWA official extrema.
    """
    # Hours since epoch (J2000.0 = 2000-01-01T12:00:00 UTC)
    epoch = datetime(2000, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    hours = (dt - epoch).total_seconds() / 3600.0

    height = MSL_OFFSET
    for _name, period, amplitude, phase_deg in CONSTITUENTS:
        omega = 2 * math.pi / period  # radians per hour
        phase_rad = math.radians(phase_deg)
        height += amplitude * math.cos(omega * hours - phase_rad)

    return round(height, 3)


def predict_height_anchored(dt: datetime,
                            cwa_extrema: list[dict] | None = None) -> float:
    """Predict tide height using CWA official extrema as anchor points.

    Between two CWA high/low points, interpolates with a cosine curve
    (the natural tidal shape).  Falls back to pure harmonic prediction
    when CWA data is unavailable or doesn't bracket the requested time.

    Parameters
    ----------
    dt : datetime (UTC)
        Time to predict height for.
    cwa_extrema : list of dicts from fetch_tide_forecast()
        Each dict has: time_utc (ISO str), height_m (float), type ('high'|'low')

    Returns
    -------
    float : height in metres above chart datum
    """
    if not cwa_extrema:
        return predict_height(dt)

    # Parse extrema into (datetime, height, type) tuples, sorted by time
    parsed = _parse_extrema(cwa_extrema)
    if len(parsed) < 2:
        return predict_height(dt)

    # Find the two extrema bracketing dt
    prev_ex = None
    next_ex = None
    for ex_dt, ex_h, ex_type in parsed:
        if ex_dt <= dt:
            prev_ex = (ex_dt, ex_h, ex_type)
        elif next_ex is None:
            next_ex = (ex_dt, ex_h, ex_type)
            break

    if prev_ex is None or next_ex is None:
        return predict_height(dt)

    # Cosine interpolation between prev and next extrema
    prev_dt, prev_h, prev_type = prev_ex
    next_dt, next_h, next_type = next_ex

    total_seconds = (next_dt - prev_dt).total_seconds()
    if total_seconds <= 0:
        return predict_height(dt)

    elapsed = (dt - prev_dt).total_seconds()
    fraction = elapsed / total_seconds

    # Cosine interpolation: 0 at prev extremum, 1 at next
    # cos(0) = 1 (prev value), cos(π) = -1 (next value)
    cos_frac = (1 - math.cos(math.pi * fraction)) / 2
    height = prev_h + (next_h - prev_h) * cos_frac

    return round(height, 3)


def _parse_extrema(cwa_extrema: list[dict]) -> list[tuple]:
    """Parse CWA extrema list into sorted (datetime, height_m, type) tuples."""
    result = []
    for ex in cwa_extrema:
        time_str = ex.get("time_utc", "")
        height = ex.get("height_m")
        etype = ex.get("type", "")
        if not time_str or height is None or etype not in ("high", "low"):
            continue
        try:
            dt = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            result.append((dt, float(height), etype))
        except (ValueError, TypeError):
            continue
    result.sort(key=lambda x: x[0])
    return result


def find_extrema(start: datetime, end: datetime,
                 step_minutes: int = 6) -> list[dict]:
    """
    Find all high and low tides between start and end (UTC).
    Uses a simple 3-point extremum detection with refinement.
    """
    step = timedelta(minutes=step_minutes)
    extrema = []

    prev_t = start
    prev_h = predict_height(prev_t)
    curr_t = start + step
    curr_h = predict_height(curr_t)

    while curr_t + step <= end:
        next_t = curr_t + step
        next_h = predict_height(next_t)

        # Local maximum (high tide) — trigger at the end of any plateau
        # (curr differs from next) to avoid duplicate detections.
        if curr_h >= prev_h and curr_h > next_h:
            refined_t, refined_h = _refine_extremum(curr_t, step)
            extrema.append({
                'type': 'high',
                'time_utc': refined_t.isoformat(),
                'utc': refined_t.isoformat(),
                'cst': (refined_t + timedelta(hours=8)).strftime('%Y-%m-%d %H:%M CST'),
                'height_m': refined_h,
            })
        # Local minimum (low tide)
        elif curr_h <= prev_h and curr_h < next_h:
            refined_t, refined_h = _refine_extremum(curr_t, step)
            extrema.append({
                'type': 'low',
                'time_utc': refined_t.isoformat(),
                'utc': refined_t.isoformat(),
                'cst': (refined_t + timedelta(hours=8)).strftime('%Y-%m-%d %H:%M CST'),
                'height_m': refined_h,
            })

        prev_t, prev_h = curr_t, curr_h
        curr_t, curr_h = next_t, next_h

    return extrema


def _refine_extremum(approx_t: datetime, search_window: timedelta,
                     precision_minutes: float = 1.0) -> tuple[datetime, float]:
    """Refine an extremum to ~1-minute precision using golden section search."""
    a = approx_t - search_window
    b = approx_t + search_window
    gr = (math.sqrt(5) + 1) / 2

    # Determine if we're looking for max or min
    mid_h = predict_height(approx_t)
    left_h = predict_height(a)
    is_max = mid_h > left_h

    target_seconds = precision_minutes * 60
    while (b - a).total_seconds() > target_seconds:
        c = b - (b - a) / gr
        d = a + (b - a) / gr
        hc = predict_height(c)
        hd = predict_height(d)
        if is_max:
            if hc > hd:
                b = d
            else:
                a = c
        else:
            if hc < hd:
                b = d
            else:
                a = c

    best_t = a + (b - a) / 2
    # Round to nearest minute
    if best_t.second >= 30:
        best_t += timedelta(minutes=1)
    best_t = best_t.replace(second=0, microsecond=0)
    return best_t, predict_height(best_t)


def generate_predictions(start: datetime, end: datetime,
                         step_hours: int = 1) -> list[dict]:
    """Generate hourly tide height predictions for the given period.

    Returns a list of dicts with 'time_utc' (ISO string) and 'height_m' (float).
    """
    predictions = []
    step = timedelta(hours=step_hours)
    t = start
    while t <= end:
        predictions.append({
            'time_utc': t.isoformat(),
            'height_m': predict_height(t),
        })
        t += step
    return predictions


def tide_state(dt: datetime, extrema: list[dict]) -> str:
    """Return 'rising', 'falling', 'high', or 'low' at the given time."""
    if not extrema:
        return 'unknown'

    iso = dt.isoformat()
    # Find the surrounding extrema
    prev_ex = None
    next_ex = None
    for ex in extrema:
        if ex.get('time_utc', ex.get('utc', '')) <= iso:
            prev_ex = ex
        elif next_ex is None:
            next_ex = ex
            break

    if prev_ex is None:
        return 'rising' if next_ex and next_ex['type'] == 'high' else 'falling'
    if next_ex is None:
        return 'falling' if prev_ex['type'] == 'high' else 'rising'

    # Between two extrema
    if prev_ex['type'] == 'low':
        return 'rising'
    return 'falling'


# ── CLI ───────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description='Predict tides at Keelung harbour')
    ap.add_argument('--output', default='tide_keelung.json',
                    help='Output JSON path (default: tide_keelung.json)')
    ap.add_argument('--days', type=int, default=7,
                    help='Number of days to predict (default: 7)')
    args = ap.parse_args()

    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    end = now + timedelta(days=args.days)

    extrema = find_extrema(now, end)
    predictions = generate_predictions(now, end, step_hours=1)

    result = {
        'meta': {
            'station': 'Keelung Harbour',
            'lat': KEELUNG_LAT,
            'lon': KEELUNG_LON,
            'generated_utc': now.isoformat(),
            'method': 'harmonic_analysis',
            'constituents': len(CONSTITUENTS),
            'datum': 'chart_datum',
        },
        'predictions': predictions,
        'extrema': extrema,
    }

    from pathlib import Path
    out = Path(args.output)
    out.write_text(json.dumps(result, indent=2))
    log.info("Tide prediction → %s  (%d predictions, %d extrema over %d days)",
             out, len(predictions), len(extrema), args.days)

    # Preview
    for ex in extrema[:8]:
        arrow = '▲' if ex['type'] == 'high' else '▼'
        log.info("  %s %s  %.2fm  %s", arrow, ex['type'].upper(), ex['height_m'], ex['cst'])


if __name__ == '__main__':
    setup_logging()
    main()
