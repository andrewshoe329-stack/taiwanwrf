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
from i18n import T, T_str

log = logging.getLogger(__name__)

# ── Prompt template ───────────────────────────────────────────────────────────
SYSTEM_PROMPT = """\
You are a sailing and surf forecaster for northern Taiwan (Keelung harbour \
and nearby surf spots: Fulong, Green Bay, Jinshan, Daxi, Wushih, Double Lions, \
Chousui).

Your audience is sailors and surfers based in northern Taiwan.
They care about: wind speed/direction, wave height/period/direction, rain, \
and which days are best for sailing vs surfing.

Rules:
- Write your response in TWO sections, separated by a line containing only "---".
- Section 1: English forecast (3–5 sentences).
- Section 2: The same forecast in natural Traditional Chinese (3–5 sentences).
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
- Do NOT use headers, bullet points, or markdown. Just flowing prose.
- Do NOT repeat raw numbers excessively — interpret them.
- Use present tense for today, future tense for upcoming days.
- Sign off each section with one emoji that captures the overall vibe \
(e.g. ⛵ 🏄 🌊 ⚠️ 🌤️).
- If accuracy data is provided, use the known biases to temper your language. \
For example, if temperature bias is +1.5°C, actual temps will likely be ~1.5° \
cooler than the model shows. If wind MAE is high (>5kt), hedge your confidence. \
Don't quote the raw error numbers — just let them inform your interpretation.
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


def build_user_prompt(wrf: dict, ecmwf: dict | None, wave: dict | None,
                      accuracy_log: list | None = None) -> str:
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

    client = anthropic.Anthropic(api_key=api_key)
    last_exc: Exception = RuntimeError("no attempts made")
    for attempt in range(1, 4):
        try:
            msg = client.messages.create(
                model='claude-sonnet-4-6',
                max_tokens=700,
                system=SYSTEM_PROMPT,
                messages=[{'role': 'user', 'content': user_prompt}],
            )
            if not msg.content:
                raise ValueError("Empty response from API")
            return msg.content[0].text.strip()
        except (anthropic.APIConnectionError, anthropic.RateLimitError,
                anthropic.InternalServerError, ValueError, OSError) as e:
            last_exc = e
            if attempt < 3:
                delay = 5 * attempt
                log.warning("Anthropic API attempt %d failed (%s); retrying in %ds …",
                            attempt, e, delay)
                time.sleep(delay)
        except (anthropic.AuthenticationError, anthropic.BadRequestError) as e:
            log.error("Non-retryable API error: %s", e)
            return ''
    log.error("Anthropic API failed after 3 attempts: %s", last_exc)
    return ''


def render_html(summary_text: str) -> str:
    """Wrap the AI summary in a styled HTML fragment.

    If the summary contains a '---' separator, splits into English and
    Chinese sections wrapped in <div lang="en/zh"> for the language toggle.
    Falls back to English-only if no separator found.
    """
    import html as html_mod

    # Split bilingual content
    parts = summary_text.split('---', 1)
    en_text = html_mod.escape(parts[0].strip())
    zh_text = html_mod.escape(parts[1].strip()) if len(parts) > 1 else None

    if zh_text:
        content = (
            f'  <div lang="en" class="ai-content">\n    {en_text}\n  </div>\n'
            f'  <div lang="zh" class="ai-content">\n    {zh_text}\n  </div>\n'
        )
    else:
        content = f'  <div class="ai-content">\n    {en_text}\n  </div>\n'

    return f"""\
<section id="summary" class="section">
<div class="ai-summary">
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

    accuracy_log = None
    if args.accuracy_log:
        try:
            with open(args.accuracy_log) as f:
                accuracy_log = json.load(f)
        except Exception as e:
            log.warning("Could not load accuracy log: %s", e)

    # Build prompt and call API
    user_prompt = build_user_prompt(wrf, ecmwf, wave, accuracy_log)
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
