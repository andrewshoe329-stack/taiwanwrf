"""Shared constants and utilities for the taiwanwrf pipeline."""

import logging


# ── Design system theme tokens ────────────────────────────────────────────────
# Centralised color / spacing / radius constants used by all HTML generators.
# Python scripts reference THEME['key'] instead of hardcoding hex values.
# The canonical CSS definitions live in pwa/styles.css as custom properties.

THEME = {
    # Base backgrounds
    'bg':           '#0f172a',
    'bg_card':      '#1e293b',
    'bg_alt':       '#111827',
    'bg_glass':     'rgba(30, 41, 59, 0.7)',

    # Text
    'text':         '#e2e8f0',
    'text_secondary': '#cbd5e1',
    'text_muted':   '#94a3b8',
    'text_dim':     '#475569',
    'text_dimmer':  '#64748b',

    # Accent
    'accent':       '#93c5fd',
    'accent_bright': '#3b82f6',
    'accent_cyan':  '#06b6d4',

    # Borders
    'border':       '#2d3f5a',
    'border_subtle': '#1e293b',
    'border_dark':  '#151f30',

    # Semantic: good / warning / danger
    'good_bg':      '#0d2d1a',
    'good_text':    '#68d391',
    'good_dark':    '#0d3320',
    'warn_bg':      '#3d2e00',
    'warn_text':    '#fbd38d',
    'warn_dark':    '#2d2200',
    'danger_bg':    '#3d1515',
    'danger_text':  '#fc8181',
    'danger_light': '#fca5a5',
    'danger_dark':  '#2d1515',

    # Model badges
    'wrf_bg':       '#2c4a7c',
    'wrf_text':     '#d0e0ff',
    'ec_bg':        '#2d6a4f',
    'ec_text':      '#d0f0e0',
    'ec_badge':     '#68d391',
    'wave_bg':      '#1e4d7a',
    'wave_text':    '#d0e8ff',

    # Table headers
    'th_bg':        '#1e3a5f',
    'th_text':      '#7db8f0',

    # Misc
    'flat_bg':      '#1a2236',
    'separator_bg': '#2d3748',
    'info_bg':      '#1a2744',
    'time_th_bg':   '#1a1a2e',

    # Temperature scale backgrounds
    'temp_cold':    '#1a3654',
    'temp_cool':    '#1a3328',
    'temp_warm':    '#3d3a00',
    'temp_hot':     '#3d2e00',
    'temp_vhot':    '#3d1515',

    # Wind scale backgrounds (Beaufort)
    'wind_light':   '#0d2d1a',
    'wind_mod':     '#1a3328',
    'wind_fresh':   '#3d3a00',
    'wind_strong':  '#3d2e00',
    'wind_gale7':   '#3d2000',
    'wind_gale8':   '#3d1515',

    # Precipitation scale
    'rain_trace':   '#0d2d1a',
    'rain_light':   '#1a3654',
    'rain_mod':     '#1a2f5a',
    'rain_heavy':   '#1a2060',

    # Wave height scale
    'wave_calm':    '#0d2d1a',
    'wave_slight':  '#3d3a00',
    'wave_mod':     '#3d2e00',
    'wave_rough':   '#3d1515',
    'wave_danger':  '#4a1010',

    # Wave period
    'wp_wind':      '#3d3a00',
    'wp_swell':     '#0d2d1a',
    'wp_ocean':     '#1a3654',

    # CAPE / instability
    'cape_stable':  '#0d2d1a',
    'cape_slight':  '#3d3a00',
    'cape_mod':     '#3d2e00',
    'cape_high':    '#3d1515',
}


def setup_logging(level: int = logging.INFO) -> None:
    """Configure root logger for CLI scripts."""
    logging.basicConfig(
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        level=level,
    )
    logging.getLogger().setLevel(level)


# Keelung harbour target point (WRF grid extraction, ECMWF/wave API queries)
KEELUNG_LAT = 25.15589534977208
KEELUNG_LON = 121.78782946186699

# ── Shared direction / compass utilities ─────────────────────────────────────

COMPASS_NAMES = (
    'N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE',
    'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW',
)


def deg_to_compass(deg: float | None) -> str:
    """Convert degrees (0–360) to a 16-point compass label."""
    if deg is None:
        return '—'
    return COMPASS_NAMES[round(deg / 22.5) % 16]


def norm_utc(iso: str) -> str:
    """
    Normalise a bare or Z-suffixed ISO-8601 UTC timestamp to the canonical
    format used throughout the pipeline: 'YYYY-MM-DDTHH:MM:SS+00:00'.

    Assumes the input is already in UTC.  Open-Meteo returns bare
    'YYYY-MM-DDTHH:MM' with timezone=UTC, so we append the explicit
    offset so string comparison with WRF valid_utc works.

    Does NOT validate date correctness or convert non-UTC offsets.
    """
    iso = iso.strip()
    if iso.endswith('Z'):
        iso = iso[:-1]  # strip Z, then apply length-based rules below
    if len(iso) == 16:       # YYYY-MM-DDTHH:MM
        iso += ":00+00:00"
    elif len(iso) == 19:     # YYYY-MM-DDTHH:MM:SS
        iso += "+00:00"
    return iso
