"""Shared constants and utilities for the taiwanwrf pipeline."""

import json
import logging
import math
import time
import urllib.error
import urllib.parse
import urllib.request


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

# ── Spot coordinates (single source of truth) ────────────────────────────────
# Used by cwa_fetch.py, cwa_discover.py, and surf_forecast.py.
# Only id/lat/lon live here; full spot metadata (facing, opt_wind, etc.) is in
# surf_forecast.py.

SPOT_COORDS = [
    {"id": "keelung",     "lat": KEELUNG_LAT, "lon": KEELUNG_LON},
    {"id": "fulong",      "lat": 25.019, "lon": 121.940},
    {"id": "greenbay",    "lat": 25.189, "lon": 121.686},
    {"id": "jinshan",     "lat": 25.238, "lon": 121.638},
    {"id": "daxi",        "lat": 24.870, "lon": 121.930},
    {"id": "wushih",      "lat": 24.862, "lon": 121.921},
    {"id": "doublelions", "lat": 24.847, "lon": 121.917},
    {"id": "chousui",     "lat": 24.820, "lon": 121.899},
    # East coast
    {"id": "donghe",      "lat": 22.970, "lon": 121.300},
    {"id": "jinzun",      "lat": 22.970, "lon": 121.280},
    {"id": "chenggong",   "lat": 23.100, "lon": 121.380},
    {"id": "dulan",       "lat": 22.880, "lon": 121.230},
    # South
    {"id": "nanwan",      "lat": 21.955, "lon": 120.765},
    {"id": "jialeshuei",  "lat": 21.990, "lon": 120.850},
    {"id": "baishawan",   "lat": 21.945, "lon": 120.710},
]

# Spot → county mapping (for township forecast endpoint selection)
SPOT_COUNTY = {
    "keelung": "基隆市", "fulong": "新北市", "greenbay": "新北市",
    "jinshan": "新北市", "daxi": "宜蘭縣", "wushih": "宜蘭縣",
    "doublelions": "宜蘭縣", "chousui": "宜蘭縣",
    # East coast
    "donghe": "臺東縣", "jinzun": "臺東縣",
    "chenggong": "臺東縣", "dulan": "臺東縣",
    # South
    "nanwan": "屏東縣", "jialeshuei": "屏東縣", "baishawan": "屏東縣",
}

# ── Full Taiwan coverage ─────────────────────────────────────────────────────
# Bounding box for the entire Taiwan region (main island + Penghu).

TAIWAN_BBOX = {
    "lat_min": 21.5, "lat_max": 25.5,
    "lon_min": 119.0, "lon_max": 122.5,
}

# Major harbour coordinates: id → (lat, lon)
HARBOUR_COORDS = {
    "keelung":   (KEELUNG_LAT, KEELUNG_LON),
    "kaohsiung": (22.615, 120.265),
    "taichung":  (24.280, 120.510),
    "anping":    (22.995, 120.160),
    "magong":    (23.565, 119.580),
}

# Spot → region mapping
SPOT_REGION = {
    "keelung":     "north",
    "fulong":      "northeast",
    "greenbay":    "north",
    "jinshan":     "north",
    "daxi":        "northeast",
    "wushih":      "northeast",
    "doublelions": "northeast",
    "chousui":     "northeast",
    "donghe":      "east",
    "jinzun":      "east",
    "chenggong":   "east",
    "dulan":       "east",
    "nanwan":      "south",
    "jialeshuei":  "south",
    "baishawan":   "south",
}

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


# ── Sunrise / sunset calculation ──────────────────────────────────────────────

def sunrise_sunset(date, lat: float = KEELUNG_LAT, lon: float = KEELUNG_LON
                   ) -> tuple[float, float]:
    """Return (sunrise_hour_utc, sunset_hour_utc) for a given date and location.

    Uses the NOAA solar equations (accurate to ~2 min).  Returns fractional
    hours in UTC — add 8 for CST.

    Parameters
    ----------
    date : datetime.date or datetime.datetime
        The calendar date (only year/month/day are used).
    lat, lon : float
        Location in decimal degrees (default: Keelung).

    Returns
    -------
    (sunrise_utc, sunset_utc) : tuple[float, float]
        Hours since midnight UTC. E.g. 21.5 = 21:30 UTC = 05:30 CST.

    For northern Taiwan (~25°N) the range is roughly:
        Summer: sunrise ~05:05, sunset ~18:45 CST
        Winter: sunrise ~06:35, sunset ~17:15 CST
    """
    if hasattr(date, 'timetuple'):
        doy = date.timetuple().tm_yday
        year = date.year
    else:
        doy = 1
        year = 2026

    # Fractional year (radians)
    gamma = 2 * math.pi / 365 * (doy - 1)

    # Equation of time (minutes)
    eqtime = (229.18 * (0.000075
              + 0.001868 * math.cos(gamma) - 0.032077 * math.sin(gamma)
              - 0.014615 * math.cos(2 * gamma) - 0.04089 * math.sin(2 * gamma)))

    # Solar declination (radians)
    decl = (0.006918
            - 0.399912 * math.cos(gamma) + 0.070257 * math.sin(gamma)
            - 0.006758 * math.cos(2 * gamma) + 0.000907 * math.sin(2 * gamma)
            - 0.002697 * math.cos(3 * gamma) + 0.00148 * math.sin(3 * gamma))

    lat_rad = math.radians(lat)

    # Hour angle at sunrise/sunset (cos of hour angle)
    cos_ha = (-math.sin(math.radians(-0.8333))
              - math.sin(lat_rad) * math.sin(decl)) / (
              math.cos(lat_rad) * math.cos(decl))

    # Clamp for polar regions (shouldn't happen at ~25°N)
    cos_ha = max(-1.0, min(1.0, cos_ha))
    ha = math.degrees(math.acos(cos_ha))  # in degrees

    # Solar noon in minutes from midnight UTC
    snoon = 720 - 4 * lon - eqtime  # minutes UTC

    sunrise_min = snoon - ha * 4  # minutes UTC
    sunset_min = snoon + ha * 4   # minutes UTC

    return (sunrise_min / 60.0, sunset_min / 60.0)


def is_daylight(dt_utc, lat: float = KEELUNG_LAT, lon: float = KEELUNG_LON,
                margin_minutes: float = 30) -> bool:
    """Check if a UTC datetime falls within daylight hours (with margin).

    The margin extends the daylight window before sunrise and after sunset
    to account for civil twilight (~30 min).
    """
    sr, ss = sunrise_sunset(dt_utc, lat, lon)
    hour_utc = dt_utc.hour + dt_utc.minute / 60.0
    margin_h = margin_minutes / 60.0

    # sunrise_sunset returns hours that may be negative (e.g. sunrise at
    # 21:11 UTC previous day → -2.81) or >24.  Normalise to the same
    # 24-hour window as hour_utc by checking multiple offsets.
    sr_lo = sr - margin_h
    ss_hi = ss + margin_h
    # Check if hour_utc falls in [sr_lo, ss_hi] considering day wrapping
    for offset in (0, 24, -24):
        h = hour_utc + offset
        if sr_lo <= h <= ss_hi:
            return True
    return False


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
    elif len(iso) >= 25 and '+' in iso[19:] and not iso.endswith('+00:00'):
        _log = logging.getLogger(__name__)
        _log.warning("norm_utc received non-UTC offset: %s", iso)
    return iso


# ── Sailing suitability rating ────────────────────────────────────────────────

def sail_rating(
    max_wind: float | None,
    max_gust: float | None,
    max_hs: float | None,
    total_rain: float,
) -> dict:
    """
    Evaluate daily sailing suitability at Keelung.

    Returns dict with keys: label, emoji, bg, col, max_w, max_g, max_hs.
    Thresholds: gust≥34 or wind≥28 or Hs≥2.5 → No-go;
                gust≥22 or wind≥17 or Hs≥1.5 or rain≥15 → Marginal;
                otherwise → Good.
    """
    if total_rain is None:
        total_rain = 0.0
    no_go = (
        (max_gust is not None and max_gust >= 34) or
        (max_wind is not None and max_wind >= 28) or
        (max_hs   is not None and max_hs   >= 2.5)
    )
    marginal = (
        (max_gust is not None and max_gust >= 22) or
        (max_wind is not None and max_wind >= 17) or
        (max_hs   is not None and max_hs   >= 1.5) or
        total_rain >= 15
    )
    base = {
        'max_w': max_wind, 'max_g': max_gust, 'max_hs': max_hs,
    }
    if no_go:
        return {**base, 'label': '🔴 No-go', 'label_en': 'No-go',
                'label_zh': '不宜出海', 'emoji': '🔴',
                'bg': THEME['danger_bg'], 'col': THEME['danger_text']}
    if marginal:
        return {**base, 'label': '🟡 Marginal', 'label_en': 'Marginal',
                'label_zh': '勉強', 'emoji': '🟡',
                'bg': THEME['warn_bg'], 'col': THEME['warn_text']}
    return {**base, 'label': '🟢 Good', 'label_en': 'Good',
            'label_zh': '適航', 'emoji': '🟢',
            'bg': THEME['good_bg'], 'col': THEME['good_text']}


# ── Shared HTTP fetch utility ────────────────────────────────────────────────

_DEFAULT_RETRIES = 3
_DEFAULT_RETRY_DELAY = 5  # seconds between attempts


def fetch_json(url: str, *, label: str = "",
               retries: int = _DEFAULT_RETRIES,
               retry_delay: int = _DEFAULT_RETRY_DELAY,
               timeout: int = 30,
               headers: dict | None = None) -> dict | None:
    """Fetch JSON from *url* with retry logic.

    Returns the parsed JSON dict on success, or ``None`` after all retries
    fail.  Catches network errors, HTTP errors, and malformed JSON.
    """
    log = logging.getLogger(__name__)
    if label:
        log.info("Fetching %s …", label)
    last_exc: Exception = RuntimeError("no attempts made")
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url)
            if headers:
                for k, v in headers.items():
                    req.add_header(k, v)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except (urllib.error.HTTPError, urllib.error.URLError,
                json.JSONDecodeError, OSError) as e:
            last_exc = e
            if attempt < retries:
                log.warning("Request failed (%s); retry %d/%d in %ds …",
                            e, attempt, retries, retry_delay)
                time.sleep(retry_delay)
    log.error("%s fetch failed after %d attempts: %s",
              label or url, retries, last_exc)
    return None


def load_json_file(path: str, label: str = "") -> dict | list | None:
    """Load and parse a JSON file, returning None on any error."""
    log = logging.getLogger(__name__)
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError, ValueError) as e:
        log.warning("Could not load %s: %s", label or path, e)
        return None
