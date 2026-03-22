"""Shared constants and utilities for the taiwanwrf pipeline."""

import logging


def setup_logging(level: int = logging.INFO) -> None:
    """Configure root logger for CLI scripts."""
    logging.basicConfig(
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        level=level,
    )


# Keelung harbour target point (WRF grid extraction, ECMWF/wave API queries)
KEELUNG_LAT = 25.15589534977208
KEELUNG_LON = 121.78782946186699

# ── Shared direction / compass utilities ─────────────────────────────────────

COMPASS_NAMES = [
    'N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE',
    'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW',
]


def deg_to_compass(deg: float | None) -> str:
    """Convert degrees (0–360) to a 16-point compass label."""
    if deg is None:
        return '—'
    return COMPASS_NAMES[round(deg / 22.5) % 16]


def norm_utc(iso: str) -> str:
    """
    Normalise any ISO-8601 string to the canonical format used throughout
    the pipeline: 'YYYY-MM-DDTHH:MM:SS+00:00'.

    Open-Meteo returns bare 'YYYY-MM-DDTHH:MM' with timezone=UTC, so we
    add the explicit offset so string comparison with WRF valid_utc works.
    """
    iso = iso.strip()
    if iso.endswith('Z'):
        iso = iso[:-1]  # strip Z, then apply length-based rules below
    if len(iso) == 16:       # YYYY-MM-DDTHH:MM
        iso += ":00+00:00"
    elif len(iso) == 19:     # YYYY-MM-DDTHH:MM:SS
        iso += "+00:00"
    return iso
