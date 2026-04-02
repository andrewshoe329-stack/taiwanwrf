#!/usr/bin/env python3
"""
forecast_summary.py — AI-generated plain-English forecast narrative.

Reads the WRF/ECMWF/wave JSON outputs and calls the Anthropic API
to produce a concise, context-aware sailing & surf summary.
Writes an HTML fragment that gets prepended to the final page.

Usage:
    python forecast_summary.py \
        --wrf-json keelung_summary_new.json \
        [--wave-json wave_keelung.json] \
        [--ecmwf-json ecmwf_keelung.json] \
        --output ai_summary.html
"""

import argparse, json, logging, os, sys, time
from datetime import datetime, timedelta, timezone

from config import setup_logging, load_json_file
from i18n import T, T_str

log = logging.getLogger(__name__)

# ── Prompt template ───────────────────────────────────────────────────────────
SYSTEM_PROMPT = """\
You are a sailing and surf forecaster for northern Taiwan — covering \
Keelung harbour and 7 surf spots across 2 regions: North coast (Fulong, \
Green Bay, Jinshan) and Northeast/Yilan coast (Daxi, Wushih, Double Lions, \
Chousui).

Your audience is English-speaking sailors and surfers in northern Taiwan.
They care about: wind speed/direction, wave height/period/direction, rain, \
and which days and spots are best for sailing vs surfing.

Rules:
- Write your response in TWO halves, separated by a line containing only "---".
- Half 1: English forecast. Half 2: Same in natural Traditional Chinese.
- Each half has exactly 3 labelled sections:
  [WIND] 1-2 sentences about wind & sailing conditions.
  [WAVES] 1-2 sentences about swell, surf, and sea state.
  [OUTLOOK] 1-2 sentences: overall outlook, best days/windows, hazards.
- Keep it SHORT and punchy. Each section should be 1-2 sentences max. \
Avoid filler words. Lead with the key number or action item.
- Example format (English half):
  [WIND] Moderate NE flow at 12-15kt through Wednesday...
  [WAVES] NE swell building to 1.5m with 10s period...
  [OUTLOOK] Thursday looks best for sailing with lighter winds...
- The Chinese section should NOT be a literal translation of the English. \
Write it as a native Taiwanese speaker would, using local sailing/surfing \
terminology natural to Taiwan's water sports community (e.g. 浪況, 湧浪, 離岸風).
- Be direct and specific in both languages.
- Lead with the most actionable info: best day/window, then hazards.
- Use knots for wind, metres for waves, compass directions (NE, SSW, etc).
- Mention specific spot names when one stands out. Use both English and \
Chinese names (e.g. "Fulong 福隆").
- If conditions change significantly mid-week, highlight the transition.
- If a storm or frontal passage is coming, say when and what it means.
- Do NOT use headers, bullet points, or markdown within sections. Just flowing prose.
- Do NOT repeat raw numbers excessively — interpret them.
- Use present tense for today, future tense for upcoming days.
- Sign off each section with one emoji that captures the overall vibe \
(e.g. ⛵ 🏄 🌊 ⚠️ 🌤️).
- If accuracy data is provided, use the known biases to temper your language. \
For example, if temperature bias is +1.5°C, actual temps will likely be ~1.5° \
cooler than the model shows. If wind MAE is high (>5kt), hedge your confidence. \
Don't quote the raw error numbers — just let them inform your interpretation.
- If real-time CWA observations are provided (station + buoy), use them as \
ground truth to validate or contrast the model forecast. If the station reads \
20°C but the model says 23°C, note the discrepancy and lean toward reality.
- If ensemble model spread is provided, use it to assess confidence. \
High wind spread (>5kt) means models disagree — hedge your language. \
Low spread (<2kt) means high confidence. Same for temperature and waves.
- If active CWA weather warnings exist, mention them prominently.

North/Northeast Taiwan seasonal weather context:
- Typhoon season: June–November. Tropical cyclone swells can arrive days before \
a storm makes landfall, creating dangerous surf and harbour conditions. Watch for \
rapid pressure drops and backing winds.
- NE monsoon: October–March. Persistent 10–20kt NE winds dominate, with cold \
surges bringing stronger gusts. NE-facing spots (Fulong, Green Bay, Jinshan) get \
consistent swell but often onshore wind. Yilan coast (Daxi, Wushih, Double Lions, \
Chousui) can be partially sheltered depending on wind angle.
- Spring transition: March–May. Winds become variable as the monsoon weakens. \
Thermal convection builds afternoon thunderstorms, especially over mountains. \
Morning windows are often best.
- SW monsoon: May–September. Lighter winds and smaller NE swell. Occasional SW \
flow brings confused seas to the north coast. Mei-yu (plum rain, May–June) brings \
frontal rain bands, reduced visibility, gusty SW flow. Sailing conditions \
deteriorate; surf can be messy but fun.
"""


def _trim_records(records: list, max_days: int = 7) -> list:
    """Keep only the next `max_days` of records to stay within token budget.

    Uses the first record's valid_utc as the reference time. On malformed
    timestamps, falls back to ``max_days * 4`` entries (assumes 6-hourly data,
    so ~4 records per day).
    """
    if not records:
        return []
    try:
        first = datetime.fromisoformat(records[0].get('valid_utc', ''))
        cutoff = first + timedelta(days=max_days)
        trimmed = [r for r in records
                   if datetime.fromisoformat(r.get('valid_utc', '')) <= cutoff]
        if len(trimmed) < len(records):
            log.info("Trimmed forecast records from %d to %d (max %d days)",
                     len(records), len(trimmed), max_days)
        return trimmed
    except (ValueError, TypeError):
        log.warning("Malformed valid_utc in records — falling back to first %d entries",
                    max_days * 4)
        return records[:max_days * 4]  # ~4 records/day at 6h intervals


def _summarise_accuracy(log_entries: list) -> str | None:
    """Distil recent accuracy log into a compact bias summary for the LLM.

    Returns a short text block like:
        Recent model accuracy (last 10 runs):
        - Temp: MAE 1.2°C, bias +0.8°C (model runs warm)
        - Wind: MAE 3.5kt, bias -1.1kt (model underforecasts)
        - WDir: MAE 28°
        - Pressure: MAE 0.9hPa
        - Wave Hs: MAE 0.3m, bias +0.1m

    Returns None if no usable data.
    """
    if not log_entries:
        return None

    # Use the most recent entries (up to 10)
    recent = log_entries[-10:]

    # Aggregate across recent runs
    def _avg(key):
        vals = [e.get(key) for e in recent if e.get(key) is not None]
        return round(sum(vals) / len(vals), 2) if vals else None

    temp_mae = _avg('temp_mae_c')
    temp_bias = _avg('temp_bias_c')
    wind_mae = _avg('wind_mae_kt')
    wind_bias = _avg('wind_bias_kt')
    wdir_mae = _avg('wdir_mae_deg')
    mslp_mae = _avg('mslp_mae_hpa')

    # Wave metrics (nested under 'wave' key)
    wave_entries = [e.get('wave', {}) for e in recent if e.get('wave')]
    hs_mae = None
    hs_bias = None
    if wave_entries:
        vals = [w.get('hs_mae_m') for w in wave_entries if w.get('hs_mae_m') is not None]
        hs_mae = round(sum(vals) / len(vals), 2) if vals else None
        vals = [w.get('hs_bias_m') for w in wave_entries if w.get('hs_bias_m') is not None]
        hs_bias = round(sum(vals) / len(vals), 2) if vals else None

    if temp_mae is None and wind_mae is None:
        return None

    lines = [f"Recent model accuracy (last {len(recent)} verified runs):"]

    def _bias_note(bias, unit, high_word="overforecasts", low_word="underforecasts"):
        if bias is None:
            return ""
        direction = high_word if bias > 0 else low_word
        return f" (model {direction} by ~{abs(bias)}{unit})"

    if temp_mae is not None:
        lines.append(f"- Temp: MAE {temp_mae}°C{_bias_note(temp_bias, '°C', 'runs warm', 'runs cool')}")
    if wind_mae is not None:
        lines.append(f"- Wind: MAE {wind_mae}kt{_bias_note(wind_bias, 'kt')}")
    if wdir_mae is not None:
        lines.append(f"- Wind direction: MAE {wdir_mae}°")
    if mslp_mae is not None:
        lines.append(f"- Pressure: MAE {mslp_mae}hPa")
    if hs_mae is not None:
        lines.append(f"- Wave Hs: MAE {hs_mae}m{_bias_note(hs_bias, 'm')}")

    return '\n'.join(lines)


# Keelung monthly climate normals (30-year averages from CWA C-B0027-001)
# Used to give the AI seasonal context for smarter narrative
KEELUNG_MONTHLY_NORMALS = {
    1:  {"temp_c": 15.3, "wind_kt": 12, "precip_mm": 337, "desc": "cool, wet, NE monsoon"},
    2:  {"temp_c": 15.5, "wind_kt": 11, "precip_mm": 340, "desc": "cool, wet, NE monsoon"},
    3:  {"temp_c": 17.0, "wind_kt": 10, "precip_mm": 298, "desc": "warming, wet"},
    4:  {"temp_c": 20.3, "wind_kt": 8,  "precip_mm": 229, "desc": "mild, spring rains"},
    5:  {"temp_c": 23.5, "wind_kt": 7,  "precip_mm": 274, "desc": "warm, plum rains"},
    6:  {"temp_c": 26.3, "wind_kt": 7,  "precip_mm": 236, "desc": "hot, early typhoon season"},
    7:  {"temp_c": 28.8, "wind_kt": 7,  "precip_mm": 140, "desc": "hot, typhoon season"},
    8:  {"temp_c": 28.6, "wind_kt": 7,  "precip_mm": 220, "desc": "hot, typhoon season, afternoon storms"},
    9:  {"temp_c": 26.6, "wind_kt": 9,  "precip_mm": 360, "desc": "warm, typhoon + NE monsoon transition"},
    10: {"temp_c": 23.2, "wind_kt": 12, "precip_mm": 380, "desc": "cooling, NE monsoon onset, wet"},
    11: {"temp_c": 20.0, "wind_kt": 12, "precip_mm": 348, "desc": "cool, NE monsoon, wet"},
    12: {"temp_c": 16.8, "wind_kt": 12, "precip_mm": 310, "desc": "cold, NE monsoon"},
}


def build_user_prompt(wrf: dict, ecmwf: dict | None, wave: dict | None,
                      accuracy_log: list | None = None,
                      cwa_obs: dict | None = None,
                      ensemble: dict | None = None) -> str:
    """Assemble forecast data into a compact prompt for the LLM."""
    parts = []

    meta = wrf.get('meta', {})
    init = meta.get('init_utc', 'unknown')
    parts.append(f"Model init: {init}")

    # Seasonal climate context
    try:
        from datetime import datetime
        month = datetime.fromisoformat(init.replace('Z', '+00:00')).month
        normals = KEELUNG_MONTHLY_NORMALS.get(month)
        if normals:
            parts.append(
                f"Seasonal context (Keelung {month:02d} normals): "
                f"avg temp {normals['temp_c']}°C, avg wind {normals['wind_kt']}kt, "
                f"precip {normals['precip_mm']}mm/month — {normals['desc']}. "
                f"Note if forecast is notably above/below normal."
            )
    except (ValueError, AttributeError):
        pass

    # CWA real-time observations — ground truth for the AI to reference
    if cwa_obs:
        obs_parts = []
        stn = cwa_obs.get('station')
        if stn and stn.get('obs_time'):
            obs_parts.append(
                f"CWA Keelung station ({stn.get('obs_time', '?')}): "
                f"temp={stn.get('temp_c')}°C, wind={stn.get('wind_kt')}kt "
                f"dir={stn.get('wind_dir')}°, gust={stn.get('gust_kt')}kt, "
                f"pressure={stn.get('pressure_hpa')}hPa, "
                f"humidity={stn.get('humidity_pct')}%"
            )
        # Include all available buoys for per-spot context
        all_buoys = cwa_obs.get('all_buoys', [])
        if all_buoys:
            for buoy in all_buoys:
                if buoy.get('obs_time') and buoy.get('wave_height_m') is not None:
                    obs_parts.append(
                        f"CWA buoy {buoy.get('buoy_name', '?')} "
                        f"({buoy.get('buoy_id', '?')}, "
                        f"{buoy.get('obs_time', '?')}): "
                        f"Hs={buoy.get('wave_height_m')}m, "
                        f"Tp={buoy.get('peak_period_s') or buoy.get('wave_period_s')}s, "
                        f"dir={buoy.get('wave_dir')}°, "
                        f"water temp={buoy.get('water_temp_c')}°C"
                    )
        else:
            buoy = cwa_obs.get('buoy')
            if buoy and buoy.get('obs_time'):
                obs_parts.append(
                    f"CWA wave buoy ({buoy.get('buoy_name', '?')}, "
                    f"{buoy.get('obs_time', '?')}): "
                    f"Hs={buoy.get('wave_height_m')}m, "
                    f"Tp={buoy.get('peak_period_s') or buoy.get('wave_period_s')}s, "
                    f"dir={buoy.get('wave_dir')}°, "
                    f"water temp={buoy.get('water_temp_c')}°C"
                )
        warnings = cwa_obs.get('warnings', [])
        if warnings:
            for w in warnings[:3]:
                obs_parts.append(
                    f"CWA WARNING: {w.get('type', 'Advisory')} — "
                    f"{w.get('description', '')[:200]}"
                )
        # CWA official township forecast (Keelung)
        township = cwa_obs.get('township_forecast')
        if township and township.get('elements'):
            elements = township['elements']
            # Extract key elements for compact summary
            tw_parts = [f"CWA official Keelung forecast ({township.get('location', '?')}):"]
            for key in ('Wx', 'MaxT', 'MinT', 'PoP12h', 'WS'):
                if key in elements and isinstance(elements[key], list):
                    vals = elements[key][:4]  # first 4 time periods
                    tw_parts.append(f"  {key}: {', '.join(str(v.get('value','?')) for v in vals)}")
            if len(tw_parts) > 1:
                obs_parts.append("\n".join(tw_parts))
        # Per-spot CWA observations (from cwa_stations.json mapping)
        spot_obs = cwa_obs.get('spot_obs', {})
        if spot_obs:
            spot_lines = []
            for spot_id, obs in spot_obs.items():
                line_parts = []
                stn_obs = obs.get('station')
                if stn_obs and stn_obs.get('obs_time'):
                    dist = stn_obs.get('distance_km', '?')
                    dist_str = f"{dist:.0f}km" if isinstance(dist, (int, float)) else f"{dist}km"
                    line_parts.append(
                        f"stn {stn_obs.get('station_id', '?')}: "
                        f"{stn_obs.get('temp_c')}°C, "
                        f"{stn_obs.get('wind_kt')}kt "
                        f"({dist_str})")
                buoy_obs = obs.get('buoy')
                if buoy_obs and buoy_obs.get('obs_time'):
                    dist = buoy_obs.get('distance_km', '?')
                    dist_str = f"{dist:.0f}km" if isinstance(dist, (int, float)) else f"{dist}km"
                    line_parts.append(
                        f"buoy {buoy_obs.get('buoy_id', '?')}: "
                        f"Hs={buoy_obs.get('wave_height_m')}m "
                        f"({dist_str})")
                if line_parts:
                    spot_lines.append(f"  {spot_id}: {' | '.join(line_parts)}")
            if spot_lines:
                obs_parts.append(
                    "Per-spot CWA obs:\n" + "\n".join(spot_lines))

        # Per-county township forecasts
        township_fcs = cwa_obs.get('township_forecasts', {})
        if township_fcs:
            for county, fc in township_fcs.items():
                if fc and fc.get('elements'):
                    elements = fc['elements']
                    tw_parts = [f"CWA {county} forecast ({fc.get('location', '?')}):"]
                    for key in ('Wx', 'MaxT', 'MinT', 'PoP12h', 'WS'):
                        if key in elements and isinstance(elements[key], list):
                            vals = elements[key][:4]
                            tw_parts.append(
                                f"  {key}: {', '.join(str(v.get('value','?')) for v in vals)}")
                    if len(tw_parts) > 1:
                        obs_parts.append("\n".join(tw_parts))

        if obs_parts:
            parts.append("Real-time observations:\n" + "\n".join(obs_parts))

    # WRF records (trimmed)
    wrf_recs = _trim_records(wrf.get('records', []))
    if wrf_recs:
        # Only keep the fields the LLM needs
        slim = []
        for r in wrf_recs:
            slim.append({
                k: r[k] for k in (
                    'valid_utc', 'temp_c', 'wind_kt', 'wind_dir',
                    'gust_kt', 'mslp_hpa', 'precip_mm_6h', 'cape',
                ) if k in r and r[k] is not None
            })
        parts.append(f"WRF Keelung forecast (6-hourly):\n{json.dumps(slim, indent=None)}")

    # Pressure trends from WRF records
    if wrf_recs:
        trend_lines = []
        rapid_fall = False
        for i in range(1, len(wrf_recs)):
            prev_p = wrf_recs[i - 1].get('mslp_hpa')
            curr_p = wrf_recs[i].get('mslp_hpa')
            if prev_p is not None and curr_p is not None:
                delta = round(curr_p - prev_p, 1)
                vt = wrf_recs[i].get('valid_utc', '?')
                trend_lines.append(f"  {vt}: {delta:+.1f} hPa/6h")
                if delta < -2:
                    rapid_fall = True
        if trend_lines:
            header = "Pressure trends (hPa/6h):"
            if rapid_fall:
                header = "PRESSURE FALLING RAPIDLY — " + header
            parts.append(header + "\n" + "\n".join(trend_lines))

    # ECMWF records
    if ecmwf:
        ec_recs = _trim_records(ecmwf.get('records', []))
        if ec_recs:
            slim = []
            for r in ec_recs:
                slim.append({
                    k: r[k] for k in (
                        'valid_utc', 'wind_kt', 'wind_dir', 'gust_kt',
                        'precip_mm_6h',
                    ) if k in r and r[k] is not None
                })
            parts.append(f"ECMWF IFS Keelung (6-hourly):\n{json.dumps(slim, indent=None)}")

    # Wave data
    if wave:
        wave_recs = _trim_records(
            (wave.get('ecmwf_wave') or {}).get('records', [])
        )
        if wave_recs:
            slim = []
            for r in wave_recs:
                slim.append({
                    k: r[k] for k in (
                        'valid_utc', 'wave_height', 'wave_period',
                        'wave_direction', 'swell_wave_height',
                        'swell_wave_period', 'swell_wave_direction',
                    ) if k in r and r[k] is not None
                })
            parts.append(f"ECMWF WAM waves at Keelung (6-hourly):\n{json.dumps(slim, indent=None)}")

    # Ensemble spread — model agreement indicators with per-model values
    if ensemble:
        spread = ensemble.get('spread', {})
        models = ensemble.get('models', {})

        # Extract per-model average values for the first 24h (up to 4 records)
        model_avgs: dict[str, dict[str, float]] = {}
        MODEL_LABELS = {
            'GFS': 'GFS',
            'JMA': 'JMA', 'ECMWF': 'ECMWF',
        }
        # Note: ensemble_fetch.py stores only meta + record_count per model
        # (raw records are used for spread stats then discarded from JSON).
        # Per-model averages are not available in the output file.

        if spread or model_avgs:
            spread_lines = ["Multi-model ensemble spread (GFS/JMA/ECMWF):"]
            wind_spread = spread.get('wind_spread_kt')
            temp_spread = spread.get('temp_spread_c')
            rain_spread = spread.get('precip_spread_mm')
            if wind_spread is not None:
                confidence = "high" if wind_spread < 3 else "moderate" if wind_spread < 6 else "low"
                line = f"- Wind: ±{wind_spread}kt spread ({confidence} confidence)"
                wind_vals = {m: a['wind_kt'] for m, a in model_avgs.items() if 'wind_kt' in a}
                if wind_vals:
                    line += " — 24h avg: " + ", ".join(f"{m}: {v}kt" for m, v in wind_vals.items())
                spread_lines.append(line)
            if temp_spread is not None:
                confidence = "high" if temp_spread < 1.5 else "moderate" if temp_spread < 3 else "low"
                line = f"- Temp: ±{temp_spread}°C spread ({confidence} confidence)"
                temp_vals = {m: a['temp_c'] for m, a in model_avgs.items() if 'temp_c' in a}
                if temp_vals:
                    line += " — 24h avg: " + ", ".join(f"{m}: {v}°C" for m, v in temp_vals.items())
                spread_lines.append(line)
            if rain_spread is not None:
                spread_lines.append(f"- Precip: ±{rain_spread}mm spread")
            # Add gust comparison if available
            gust_vals = {m: a['gust_kt'] for m, a in model_avgs.items() if 'gust_kt' in a}
            if gust_vals:
                spread_lines.append(
                    "- Gust 24h avg: " + ", ".join(f"{m}: {v}kt" for m, v in gust_vals.items()))
            if len(spread_lines) > 1:
                parts.append("\n".join(spread_lines))

    # Accuracy context — lets the LLM adjust confidence based on known biases
    if accuracy_log:
        acc_summary = _summarise_accuracy(accuracy_log)
        if acc_summary:
            parts.append(acc_summary)

    parts.append(
        "Write a bilingual forecast summary (English then --- then Chinese) "
        "for the next 3–5 days. "
        "Focus on sailing out of Keelung and surfing at the north coast spots."
    )

    return '\n\n'.join(parts)


def call_api(user_prompt: str) -> str:
    """Call the Anthropic API and return the summary text."""
    try:
        import anthropic
    except ImportError:
        log.error("anthropic package not installed — pip install anthropic")
        return ''

    api_key = os.environ.get('ANTHROPIC_API_KEY', '')
    if not api_key:
        log.warning("ANTHROPIC_API_KEY not set — skipping AI summary")
        return ''

    model_name = os.environ.get('CLAUDE_MODEL', 'claude-sonnet-4-6')
    client = anthropic.Anthropic(api_key=api_key, max_retries=5)
    last_exc: Exception = RuntimeError("no attempts made")
    for attempt in range(1, 4):
        try:
            msg = client.messages.create(
                model=model_name,
                max_tokens=800,
                system=SYSTEM_PROMPT,
                messages=[{'role': 'user', 'content': user_prompt}],
            )
            if not msg.content or not getattr(msg.content[0], 'text', ''):
                raise ValueError("Empty response from API")
            return msg.content[0].text.strip()
        except (anthropic.APIConnectionError, anthropic.RateLimitError,
                anthropic.InternalServerError, anthropic.APIStatusError,
                ValueError, OSError, TimeoutError) as e:
            last_exc = e
            if isinstance(e, (anthropic.AuthenticationError,
                              anthropic.BadRequestError)):
                log.error("Non-retryable API error: %s", e)
                return ''
            if attempt < 3:
                import random
                delay = 10 * (2 ** (attempt - 1)) + random.randint(0, 5)
                log.warning("Anthropic API attempt %d failed (%s); retrying in %ds …",
                            attempt, e, delay)
                time.sleep(delay)
    log.error("Anthropic API failed after 3 attempts: %s", last_exc)
    return ''


_AI_SECTIONS = [
    ('WIND',    '\U0001f4a8', 'ai_wind'),     # 💨
    ('WAVES',   '\U0001f30a', 'ai_waves'),     # 🌊
    ('OUTLOOK', '\U0001f4cb', 'ai_outlook'),   # 📋
]


def _parse_sections(text: str) -> list[tuple[str, str]]:
    """Parse [WIND]/[WAVES]/[OUTLOOK] markers from AI text.

    Returns list of (section_key, body_text) tuples.
    Falls back to [('', full_text)] if no markers found.
    """
    import re
    pattern = r'\[(WIND|WAVES|OUTLOOK)\]\s*'
    parts = re.split(pattern, text.strip())
    # re.split with group: ['before', 'KEY1', 'body1', 'KEY2', 'body2', ...]
    sections: list[tuple[str, str]] = []
    if len(parts) >= 3:
        i = 1
        while i < len(parts) - 1:
            key = parts[i].strip()
            body = parts[i + 1].strip()
            if body:
                sections.append((key, body))
            i += 2
    return sections if sections else [('', text.strip())]


def render_html(summary_text: str) -> str:
    """Wrap the AI summary in a styled HTML fragment.

    Parses [WIND]/[WAVES]/[OUTLOOK] section markers into styled cards.
    If the summary contains a '---' separator, splits into English and
    Chinese sections wrapped in <div lang="en/zh"> for the language toggle.
    Falls back to unstructured display if no markers found.
    """
    import html as html_mod

    # Split bilingual content
    halves = summary_text.split('---', 1)
    en_raw = halves[0].strip()
    zh_raw = halves[1].strip() if len(halves) > 1 else None

    en_sections = _parse_sections(en_raw)
    zh_sections = _parse_sections(zh_raw) if zh_raw else None

    def _format_body(text: str) -> str:
        """Escape and convert sentences to readable paragraphs.

        Splits on sentence-ending punctuation followed by a space to create
        separate <p> tags, making the text scannable instead of a wall.
        """
        import re
        escaped = html_mod.escape(text)
        # Split on sentence boundaries: period/exclamation/question + space + uppercase
        # or Chinese sentence-ending punctuation
        sentences = re.split(r'(?<=[.!?。！？])\s+', escaped)
        if len(sentences) <= 1:
            return f'<p>{escaped}</p>'
        return '\n'.join(f'<p>{s.strip()}</p>' for s in sentences if s.strip())

    def _render_half(sections: list[tuple[str, str]], lang: str) -> str:
        """Render one language half as either structured cards or plain text."""
        # Check if structured (has named sections)
        has_structure = any(key for key, _ in sections)

        if has_structure:
            cards = ''
            for key, body in sections:
                formatted = _format_body(body)
                # Find matching section config
                icon, title_key = '', ''
                for skey, sicon, stitle in _AI_SECTIONS:
                    if skey == key:
                        icon, title_key = sicon, stitle
                        break
                if title_key:
                    title = T(title_key)
                    cards += (
                        f'    <div class="ai-card">\n'
                        f'      <div class="ai-card-header"><span class="ai-card-icon">{icon}</span> {title}</div>\n'
                        f'      <div class="ai-card-body">{formatted}</div>\n'
                        f'    </div>\n'
                    )
                else:
                    cards += f'    <div class="ai-card"><div class="ai-card-body">{formatted}</div></div>\n'
            lang_attr = f' lang="{lang}"' if lang else ''
            return f'  <div{lang_attr} class="ai-cards">\n{cards}  </div>\n'
        else:
            # Fallback: plain text (legacy format)
            formatted = _format_body(sections[0][1])
            lang_attr = f' lang="{lang}"' if lang else ''
            return f'  <div{lang_attr} class="ai-content">\n    {formatted}\n  </div>\n'

    content = _render_half(en_sections, 'en')
    if zh_sections:
        content += _render_half(zh_sections, 'zh')

    return f"""\
<section id="summary" class="section">
<div class="ai-summary card-glass">
  <h2 class="section-title">
    <span role="img" aria-label="sparkle">&#10024;</span> {T('ai_summary_title')}
  </h2>
{content}\
  <div class="ai-disclaimer">
    {T('ai_disclaimer')}
  </div>
</div>
</section>
"""


def main() -> None:
    ap = argparse.ArgumentParser(description='AI forecast summary')
    ap.add_argument('--wrf-json', required=True, help='WRF summary JSON')
    ap.add_argument('--ecmwf-json', default=None, help='ECMWF JSON')
    ap.add_argument('--wave-json', default=None, help='Wave JSON')
    ap.add_argument('--accuracy-log', default=None,
                    help='Accuracy log JSON (rolling verification metrics)')
    ap.add_argument('--cwa-obs', default=None,
                    help='CWA observations JSON (real-time station + buoy)')
    ap.add_argument('--ensemble-json', default=None,
                    help='Ensemble spread JSON (multi-model agreement)')
    ap.add_argument('--output', default='ai_summary.html', help='Output HTML fragment')
    ap.add_argument('--output-json', default=None,
                    help='Output JSON with structured bilingual sections')
    args = ap.parse_args()

    # Load data
    wrf = load_json_file(args.wrf_json, "WRF JSON")
    if wrf is None:
        log.error("Cannot read WRF JSON — aborting.")
        sys.exit(1)

    ecmwf = load_json_file(args.ecmwf_json, "ECMWF JSON") if args.ecmwf_json else None
    wave = load_json_file(args.wave_json, "wave JSON") if args.wave_json else None
    accuracy_log = load_json_file(args.accuracy_log, "accuracy log") if args.accuracy_log else None
    cwa_obs = load_json_file(args.cwa_obs, "CWA obs JSON") if args.cwa_obs else None
    ensemble = load_json_file(args.ensemble_json, "ensemble JSON") if args.ensemble_json else None

    # Build prompt and call API
    user_prompt = build_user_prompt(wrf, ecmwf, wave, accuracy_log,
                                    cwa_obs=cwa_obs, ensemble=ensemble)
    log.info("Prompt size: %d chars", len(user_prompt))

    summary = call_api(user_prompt)

    if not summary:
        log.warning("No AI summary generated — writing empty file")
        with open(args.output, 'w') as f:
            f.write('')
        return

    log.info("AI summary: %s", summary[:120])

    html = render_html(summary)
    with open(args.output, 'w', encoding='utf-8') as f:
        f.write(html)
    log.info("Wrote %s (%d chars)", args.output, len(html))

    if args.output_json:
        # Parse bilingual sections into structured JSON for the React frontend
        halves = summary.split('---', 1)
        en_raw = halves[0].strip()
        zh_raw = halves[1].strip() if len(halves) > 1 else en_raw

        en_secs = {k.lower(): v for k, v in _parse_sections(en_raw) if k}
        zh_secs = {k.lower(): v for k, v in _parse_sections(zh_raw) if k}

        json_data = {
            'wind':    {'en': en_secs.get('wind', ''),    'zh': zh_secs.get('wind', '')},
            'waves':   {'en': en_secs.get('waves', ''),   'zh': zh_secs.get('waves', '')},
            'outlook': {'en': en_secs.get('outlook', ''), 'zh': zh_secs.get('outlook', '')},
        }

        with open(args.output_json, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2)
        log.info("Wrote %s", args.output_json)


if __name__ == '__main__':
    setup_logging()
    main()
