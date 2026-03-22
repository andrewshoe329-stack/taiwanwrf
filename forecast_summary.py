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

from config import setup_logging

log = logging.getLogger(__name__)

# ── Prompt template ───────────────────────────────────────────────────────────
SYSTEM_PROMPT = """\
You are a sailing and surf forecaster for northern Taiwan (Keelung harbour \
and nearby surf spots: Fulong, Green Bay, Jinshan, Daxi, Wushih, Double Lions, \
Chousui).

Your audience is English-speaking sailors and surfers based in northern Taiwan.
They care about: wind speed/direction, wave height/period/direction, rain, \
and which days are best for sailing vs surfing.

Rules:
- Write 3–5 sentences maximum. Be direct and specific.
- Lead with the most actionable info: best day/window, then hazards.
- Use knots for wind, metres for waves, compass directions (NE, SSW, etc).
- Mention specific spot names when one stands out.
- If conditions change significantly mid-week, highlight the transition.
- If a storm or frontal passage is coming, say when and what it means.
- Do NOT use headers, bullet points, or markdown. Just flowing prose.
- Do NOT repeat raw numbers excessively — interpret them.
- Use present tense for today, future tense for upcoming days.
- Sign off with one emoji that captures the overall vibe (e.g. ⛵ 🏄 🌊 ⚠️ 🌤️).
"""


def _trim_records(records: list, max_days: int = 7) -> list:
    """Keep only the next `max_days` of records to stay within token budget."""
    if not records:
        return []
    try:
        first = datetime.fromisoformat(records[0].get('valid_utc', ''))
        cutoff = first + timedelta(days=max_days)
        return [r for r in records
                if datetime.fromisoformat(r.get('valid_utc', '')) <= cutoff]
    except (ValueError, TypeError):
        return records[:max_days * 4]  # ~4 records/day at 6h intervals


def build_user_prompt(wrf: dict, ecmwf: dict | None, wave: dict | None) -> str:
    """Assemble forecast data into a compact prompt for the LLM."""
    parts = []

    meta = wrf.get('meta', {})
    init = meta.get('init_utc', 'unknown')
    parts.append(f"Model init: {init}")

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

    parts.append(
        "Write a plain-English forecast summary for the next 3–5 days. "
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

    client = anthropic.Anthropic(api_key=api_key)
    last_exc: Exception = RuntimeError("no attempts made")
    for attempt in range(1, 4):
        try:
            msg = client.messages.create(
                model='claude-sonnet-4-5-latest',
                max_tokens=400,
                system=SYSTEM_PROMPT,
                messages=[{'role': 'user', 'content': user_prompt}],
            )
            return msg.content[0].text.strip()
        except Exception as e:
            last_exc = e
            if attempt < 3:
                delay = 5 * attempt
                log.warning("Anthropic API attempt %d failed (%s); retrying in %ds …",
                            attempt, e, delay)
                time.sleep(delay)
    log.error("Anthropic API failed after 3 attempts: %s", last_exc)
    return ''


def render_html(summary_text: str) -> str:
    """Wrap the AI summary in a styled HTML fragment."""
    import html as html_mod
    escaped = html_mod.escape(summary_text)

    return f"""\
<div style="font-family:Arial,'Helvetica Neue',sans-serif;background:#0f172a;padding:16px;border-radius:8px;margin-bottom:4px">
  <div style="font-size:16px;font-weight:700;margin-bottom:8px;color:#93c5fd">
    <span role="img" aria-label="sparkle">✨</span> AI Forecast Summary
  </div>
  <div style="font-size:14px;line-height:1.6;color:#cbd5e1;background:#1e293b;border-left:3px solid #3b82f6;padding:12px 16px;border-radius:0 6px 6px 0">
    {escaped}
  </div>
  <div style="font-size:10px;color:#475569;margin-top:6px">
    Generated by Claude · Not a substitute for official marine forecasts
  </div>
</div>
"""


def main() -> None:
    ap = argparse.ArgumentParser(description='AI forecast summary')
    ap.add_argument('--wrf-json', required=True, help='WRF summary JSON')
    ap.add_argument('--ecmwf-json', default=None, help='ECMWF JSON')
    ap.add_argument('--wave-json', default=None, help='Wave JSON')
    ap.add_argument('--output', default='ai_summary.html', help='Output HTML fragment')
    args = ap.parse_args()

    # Load data
    try:
        with open(args.wrf_json) as f:
            wrf = json.load(f)
    except Exception as e:
        log.error("Cannot read WRF JSON: %s", e)
        sys.exit(1)

    ecmwf = None
    if args.ecmwf_json:
        try:
            with open(args.ecmwf_json) as f:
                ecmwf = json.load(f)
        except Exception as e:
            log.warning("Could not load ECMWF JSON: %s", e)

    wave = None
    if args.wave_json:
        try:
            with open(args.wave_json) as f:
                wave = json.load(f)
        except Exception as e:
            log.warning("Could not load wave JSON: %s", e)

    # Build prompt and call API
    user_prompt = build_user_prompt(wrf, ecmwf, wave)
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


if __name__ == '__main__':
    setup_logging()
    main()
