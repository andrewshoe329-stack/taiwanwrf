#!/usr/bin/env python3
"""
notify.py
=========
Send threshold-based alerts when forecast conditions cross user-defined
thresholds. Supports LINE Notify and Telegram Bot API.

No extra dependencies — uses only stdlib (urllib + json).

Usage:
  python notify.py --wrf-json keelung_summary_new.json \
                   --wave-json wave_keelung.json \
                   [--line-token TOKEN] [--telegram-token TOKEN --telegram-chat CHAT_ID]

Environment variables (alternative to CLI args):
  LINE_NOTIFY_TOKEN    — LINE Notify access token
  TELEGRAM_BOT_TOKEN   — Telegram bot token
  TELEGRAM_CHAT_ID     — Telegram chat ID
"""

import argparse
import json
import logging
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from config import setup_logging
from i18n import T_str

log = logging.getLogger(__name__)


# ── Thresholds ────────────────────────────────────────────────────────────────

THRESHOLDS = {
    'gale_wind_kt':     34,   # Beaufort 8+ gale warning
    'strong_wind_kt':   22,   # Beaufort 6+ small craft advisory
    'heavy_rain_mm_6h': 15,   # Heavy rain threshold per 6h
    'high_seas_m':      2.5,  # Rough seas threshold
    'dangerous_seas_m': 3.5,  # Dangerous seas threshold
    'good_surf_m':      0.6,  # Surfable swell minimum
    'firing_surf_m':    1.5,  # Excellent surf conditions
    'light_wind_kt':    10,   # Good sailing lower bound
    'sail_max_gust_kt': 30,   # Sailing no-go gust
}


# ── Alert checks ─────────────────────────────────────────────────────────────

def check_alerts(wrf_data: dict, wave_data: dict | None = None) -> list[dict]:
    """Evaluate forecast data against thresholds.

    Returns a list of alert dicts: {type, severity, message, valid_utc, value}
    """
    alerts = []
    records = wrf_data.get('records', [])

    for rec in records:
        vt = rec.get('valid_utc', '')
        try:
            dt = datetime.fromisoformat(vt)
            cst = dt + timedelta(hours=8)
            time_str = cst.strftime('%a %H:%M CST')
        except (ValueError, TypeError):
            time_str = vt

        wind = rec.get('wind_kt')
        gust = rec.get('gust_kt')
        rain = rec.get('precip_mm_6h')

        if gust is not None and gust >= THRESHOLDS['gale_wind_kt']:
            alerts.append({
                'type': 'gale_warning',
                'severity': 'danger',
                'message': f'Gale warning: {gust:.0f}kt gusts at {time_str}',
                'valid_utc': vt,
                'value': gust,
            })
        elif wind is not None and wind >= THRESHOLDS['strong_wind_kt']:
            alerts.append({
                'type': 'strong_wind',
                'severity': 'warning',
                'message': f'Strong wind: {wind:.0f}kt at {time_str}',
                'valid_utc': vt,
                'value': wind,
            })

        if rain is not None and rain >= THRESHOLDS['heavy_rain_mm_6h']:
            alerts.append({
                'type': 'heavy_rain',
                'severity': 'warning',
                'message': f'Heavy rain: {rain:.1f}mm/6h at {time_str}',
                'valid_utc': vt,
                'value': rain,
            })

    # Wave alerts
    if wave_data:
        wave_recs = wave_data.get('ecmwf_wave', {}).get('records', [])
        for rec in wave_recs:
            vt = rec.get('valid_utc', '')
            hs = rec.get('wave_height')
            try:
                dt = datetime.fromisoformat(vt)
                cst = dt + timedelta(hours=8)
                time_str = cst.strftime('%a %H:%M CST')
            except (ValueError, TypeError):
                time_str = vt

            if hs is not None and hs >= THRESHOLDS['dangerous_seas_m']:
                alerts.append({
                    'type': 'dangerous_seas',
                    'severity': 'danger',
                    'message': f'Dangerous seas: Hs {hs:.1f}m at {time_str}',
                    'valid_utc': vt,
                    'value': hs,
                })
            elif hs is not None and hs >= THRESHOLDS['high_seas_m']:
                alerts.append({
                    'type': 'high_seas',
                    'severity': 'warning',
                    'message': f'Rough seas: Hs {hs:.1f}m at {time_str}',
                    'valid_utc': vt,
                    'value': hs,
                })

    # Great surf conditions — any spot "Firing!" (score >= 9) in the next 24h
    # (surf_planner data is checked separately via check_surf_alerts)

    # Deduplicate: keep only the most severe alert of each type per day
    by_day_type: dict[tuple, dict] = {}
    severity_rank = {'danger': 2, 'warning': 1, 'info': 0}
    for alert in alerts:
        day_key = alert['valid_utc'][:10] if alert['valid_utc'] else 'unknown'
        key = (day_key, alert['type'])
        existing = by_day_type.get(key)
        if existing is None or severity_rank.get(alert['severity'], 0) > severity_rank.get(existing['severity'], 0):
            by_day_type[key] = alert

    return sorted(by_day_type.values(), key=lambda a: a.get('valid_utc', ''))


def check_surf_alerts(surf_planner: dict | None) -> list[dict]:
    """Check surf planner data for 'Firing!' conditions in the next 24h.

    Parameters
    ----------
    surf_planner : dict or None
        Parsed surf_planner.json with per-spot daily data.

    Returns list of alert dicts.
    """
    if not surf_planner:
        return []

    alerts = []
    now_utc = datetime.now(timezone.utc)
    cutoff = now_utc + timedelta(hours=24)

    spots = surf_planner.get('spots', {})
    for spot_id, spot_data in spots.items():
        spot_name = spot_data.get('name', spot_id)
        days = spot_data.get('days', [])
        for day_info in days:
            best = day_info.get('best_time')
            if not best:
                continue
            score = best.get('score', 0)
            if score < 9:
                continue
            window = best.get('window', '')
            day_date = day_info.get('date', '')
            # Check if this is within the next 24h
            try:
                dt = datetime.fromisoformat(day_date + 'T00:00:00+00:00')
                if dt > cutoff:
                    continue
            except (ValueError, TypeError):
                pass  # include if we can't parse date

            try:
                cst_dt = datetime.fromisoformat(day_date + 'T00:00:00+08:00')
                time_str = cst_dt.strftime('%a') + ' ' + window
            except (ValueError, TypeError):
                time_str = f'{day_date} {window}'

            alerts.append({
                'type': 'great_surf',
                'severity': 'info',
                'message': f'Firing surf at {spot_name}: score {score}, {time_str}',
                'valid_utc': day_date,
                'value': score,
            })

    return alerts


def check_cwa_warnings(cwa_obs: dict | None) -> list[dict]:
    """Extract CWA weather warnings from cwa_obs.json and return as alerts."""
    if not cwa_obs:
        return []

    warnings = cwa_obs.get('warnings', [])
    alerts = []
    for w in warnings:
        desc = w.get('description', '')
        wtype = w.get('type', 'Weather warning')
        severity = w.get('severity', 'warning')
        area = w.get('area', '')
        issued = w.get('issued_utc', '')

        try:
            dt = datetime.fromisoformat(issued)
            cst = dt + timedelta(hours=8)
            time_str = cst.strftime('%Y-%m-%d %H:%M CST')
        except (ValueError, TypeError):
            time_str = issued

        sev = 'danger' if severity in ('danger', 'severe', 'extreme') else 'warning'
        msg = f'CWA {wtype}'
        if area:
            msg += f' ({area})'
        msg += f': {desc[:200]}'
        if time_str:
            msg += f' [issued {time_str}]'

        alerts.append({
            'type': 'cwa_warning',
            'severity': sev,
            'message': msg,
            'valid_utc': issued,
            'value': None,
        })

    return alerts


def format_notification(alerts: list[dict], init_utc: str | None = None) -> str:
    """Format alerts into a bilingual notification message (English + Chinese)."""
    if not alerts:
        return ''

    lines = [T_str('notif_title', 'en')]
    lines.append(T_str('notif_title', 'zh'))
    if init_utc:
        try:
            dt = datetime.fromisoformat(init_utc)
            lines.append(f'{T_str("notif_model_run", "en")}: {dt.strftime("%Y-%m-%d %H:%M UTC")}')
        except (ValueError, TypeError):
            pass
    lines.append('')

    danger = [a for a in alerts if a['severity'] == 'danger']
    warning = [a for a in alerts if a['severity'] == 'warning']

    if danger:
        lines.append(f'🔴 {T_str("notif_danger", "en")} / {T_str("notif_danger", "zh")}:')
        for a in danger:
            lines.append(f'  {a["message"]}')
    if warning:
        lines.append(f'🟡 {T_str("notif_warning", "en")} / {T_str("notif_warning", "zh")}:')
        for a in warning:
            lines.append(f'  {a["message"]}')

    info = [a for a in alerts if a['severity'] == 'info']
    if info:
        lines.append(f'🟢 Good conditions:')
        for a in info:
            lines.append(f'  {a["message"]}')

    return '\n'.join(lines)


# ── Notification senders ──────────────────────────────────────────────────────

def send_line_notify(token: str, message: str) -> bool:
    """Send a notification via LINE Notify API."""
    url = 'https://notify-api.line.me/api/notify'
    data = urllib.parse.urlencode({'message': message}).encode()
    req = urllib.request.Request(url, data=data, headers={
        'Authorization': f'Bearer {token}',
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            log.info("LINE Notify sent (status %d)", r.status)
            return True
    except (urllib.error.HTTPError, urllib.error.URLError, OSError) as e:
        log.error("LINE Notify failed: %s", e)
        return False


def send_telegram(token: str, chat_id: str, message: str) -> bool:
    """Send a notification via Telegram Bot API."""
    url = f'https://api.telegram.org/bot{token}/sendMessage'
    data = json.dumps({
        'chat_id': chat_id,
        'text': message,
    }).encode()
    req = urllib.request.Request(url, data=data, headers={
        'Content-Type': 'application/json',
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            log.info("Telegram message sent (status %d)", r.status)
            return True
    except (urllib.error.HTTPError, urllib.error.URLError, OSError) as e:
        log.error("Telegram send failed (HTTP error)")
        return False


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description='Send threshold-based forecast alerts')
    ap.add_argument('--wrf-json', required=True, help='WRF summary JSON')
    ap.add_argument('--wave-json', default=None, help='Wave forecast JSON')
    ap.add_argument('--surf-planner', default=None, help='Surf planner JSON')
    ap.add_argument('--cwa-obs', default=None, help='CWA observations JSON')
    ap.add_argument('--line-token', default=None,
                    help='LINE Notify token (or set LINE_NOTIFY_TOKEN env)')
    ap.add_argument('--telegram-token', default=None,
                    help='Telegram bot token (or set TELEGRAM_BOT_TOKEN env)')
    ap.add_argument('--telegram-chat', default=None,
                    help='Telegram chat ID (or set TELEGRAM_CHAT_ID env)')
    ap.add_argument('--dry-run', action='store_true',
                    help='Print alerts without sending')
    args = ap.parse_args()
    setup_logging()

    # Load data
    try:
        wrf_data = json.loads(Path(args.wrf_json).read_text())
    except (FileNotFoundError, json.JSONDecodeError) as e:
        log.error("Cannot load WRF JSON: %s", e)
        sys.exit(1)

    wave_data = None
    if args.wave_json:
        try:
            wave_data = json.loads(Path(args.wave_json).read_text())
        except (FileNotFoundError, json.JSONDecodeError) as e:
            log.warning("Cannot load wave JSON: %s", e)

    # Load surf planner
    surf_planner = None
    if args.surf_planner:
        try:
            surf_planner = json.loads(Path(args.surf_planner).read_text())
        except (FileNotFoundError, json.JSONDecodeError) as e:
            log.warning("Cannot load surf planner JSON: %s", e)

    # Load CWA observations
    cwa_obs = None
    if args.cwa_obs:
        try:
            cwa_obs = json.loads(Path(args.cwa_obs).read_text())
        except (FileNotFoundError, json.JSONDecodeError) as e:
            log.warning("Cannot load CWA obs JSON: %s", e)

    # Check alerts
    alerts = check_alerts(wrf_data, wave_data)
    alerts.extend(check_surf_alerts(surf_planner))
    alerts.extend(check_cwa_warnings(cwa_obs))
    if not alerts:
        log.info("No alerts triggered")
        return

    init_utc = wrf_data.get('meta', {}).get('init_utc')
    message = format_notification(alerts, init_utc)
    log.info("Generated %d alerts", len(alerts))

    if args.dry_run:
        print(message)
        return

    # Send notifications
    line_token = args.line_token or os.environ.get('LINE_NOTIFY_TOKEN')
    tg_token = args.telegram_token or os.environ.get('TELEGRAM_BOT_TOKEN')
    tg_chat = args.telegram_chat or os.environ.get('TELEGRAM_CHAT_ID')

    sent = False
    if line_token:
        sent = send_line_notify(line_token, message) or sent
    if tg_token and tg_chat:
        sent = send_telegram(tg_token, tg_chat, message) or sent

    if not line_token and not (tg_token and tg_chat):
        log.warning("No notification tokens configured — printing to stdout")
        print(message)

    if sent:
        log.info("Notifications sent successfully")


if __name__ == "__main__":
    main()
