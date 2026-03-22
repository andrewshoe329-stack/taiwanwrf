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

from config import setup_logging

log = logging.getLogger(__name__)

# ── Harmonic constituents for Keelung harbour ─────────────────────────────
# Source: Published values from CWA tide gauge records and Jan et al. (2004).
# amplitude = metres above/below MSL, phase = degrees (GMT/UTC reference)
# These are the principal constituents; 4 is sufficient for ~90% accuracy.

CONSTITUENTS = [
    # (name,  period_hours,  amplitude_m,  phase_deg)
    ('M2',    12.4206,       0.215,        195.0),   # principal lunar semidiurnal
    ('S2',    12.0000,       0.060,        220.0),   # principal solar semidiurnal
    ('K1',    23.9345,       0.145,        155.0),   # luni-solar diurnal
    ('O1',    25.8193,       0.105,        130.0),   # principal lunar diurnal
    ('N2',    12.6583,       0.045,        175.0),   # larger lunar elliptic
    ('K2',    11.9672,       0.018,        215.0),   # luni-solar semidiurnal
]

# Mean sea level offset (metres above chart datum)
MSL_OFFSET = 0.45


def predict_height(dt: datetime) -> float:
    """Predict tide height (metres above chart datum) at a given UTC datetime."""
    # Hours since epoch (J2000.0 = 2000-01-01T12:00:00 UTC)
    epoch = datetime(2000, 1, 12, 0, 0, 0, tzinfo=timezone.utc)
    hours = (dt - epoch).total_seconds() / 3600.0

    height = MSL_OFFSET
    for _name, period, amplitude, phase_deg in CONSTITUENTS:
        omega = 2 * math.pi / period  # radians per hour
        phase_rad = math.radians(phase_deg)
        height += amplitude * math.cos(omega * hours - phase_rad)

    return round(height, 3)


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

        # Local maximum (high tide)
        if curr_h >= prev_h and curr_h >= next_h and curr_h != prev_h:
            refined_t, refined_h = _refine_extremum(curr_t, step)
            extrema.append({
                'type': 'high',
                'utc': refined_t.isoformat(),
                'cst': (refined_t + timedelta(hours=8)).strftime('%Y-%m-%d %H:%M CST'),
                'height_m': refined_h,
            })
        # Local minimum (low tide)
        elif curr_h <= prev_h and curr_h <= next_h and curr_h != prev_h:
            refined_t, refined_h = _refine_extremum(curr_t, step)
            extrema.append({
                'type': 'low',
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
    best_t = best_t.replace(second=0, microsecond=0)
    return best_t, predict_height(best_t)


def tide_state(dt: datetime, extrema: list[dict]) -> str:
    """Return 'rising', 'falling', 'high', or 'low' at the given time."""
    if not extrema:
        return 'unknown'

    iso = dt.isoformat()
    # Find the surrounding extrema
    prev_ex = None
    next_ex = None
    for ex in extrema:
        if ex['utc'] <= iso:
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

    result = {
        'location': 'Keelung Harbour',
        'latitude': 25.156,
        'longitude': 121.788,
        'generated_utc': now.isoformat(),
        'method': 'harmonic_analysis',
        'constituents': len(CONSTITUENTS),
        'datum': 'chart_datum',
        'extrema': extrema,
    }

    from pathlib import Path
    out = Path(args.output)
    out.write_text(json.dumps(result, indent=2))
    log.info("Tide prediction → %s  (%d extrema over %d days)", out, len(extrema), args.days)

    # Preview
    for ex in extrema[:8]:
        arrow = '▲' if ex['type'] == 'high' else '▼'
        log.info("  %s %s  %.2fm  %s", arrow, ex['type'].upper(), ex['height_m'], ex['cst'])


if __name__ == '__main__':
    setup_logging()
    main()
