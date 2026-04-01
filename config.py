"""Shared constants and utilities for the taiwanwrf pipeline."""

import json
import logging
import math
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed


# ── Design system theme tokens ────────────────────────────────────────────────
# Centralised color / spacing / radius constants used by all HTML generators.
# Python scripts reference THEME['key'] instead of hardcoding hex values.
# The canonical CSS definitions live in frontend/public/ as custom properties.

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


# ── Unit conversion constants ────────────────────────────────────────────────
MS_TO_KT = 1.94384   # m/s → knots  (exact: 3600/1852)

# ── Thresholds (single source of truth) ──────────────────────────────────────
# Imported by notify.py, surf_forecast.py, and used by sail_rating() below.
# Each value cites WMO, CWA, or local consensus.
GALE_WIND_KT       = 34    # Beaufort 8 — WMO gale warning
STRONG_WIND_KT     = 22    # Beaufort 6 — WMO small craft advisory
HEAVY_RAIN_MM_6H   = 15    # CWA heavy rain advisory
HIGH_SEAS_M        = 2.5   # CWA rough sea advisory for coastal waters
DANGEROUS_SEAS_M   = 3.5   # CWA dangerous sea warning for coastal waters
GOOD_SURF_M        = 0.6   # Surfable swell minimum (local consensus)
FIRING_SURF_M      = 1.5   # Excellent surf conditions (local consensus)
LIGHT_WIND_KT      = 10    # Good sailing lower bound (Beaufort 3)
SAIL_MAX_GUST_KT   = 30    # Sailing no-go gust (Beaufort 7)
# Surf scoring thresholds
MIN_SWELL_HEIGHT_M = 0.25  # Below → flat
MAX_SWELL_HEIGHT_M = 4.5   # Above → dangerous
MAX_SURF_WIND_KT   = 32    # Above → too windy for surfing
ONSHORE_WIND_KT    = 22    # Above → surf score penalty for onshore wind
STRONG_SURF_WIND_KT = 25   # Above → additional strong wind penalty
# Squall detection (B7)
SQUALL_GUST_FACTOR     = 1.8   # gust/sustained ratio indicating gusty/squall
SQUALL_CAPE_THRESHOLD  = 1000  # J/kg — moderate instability
SQUALL_PRESSURE_DROP   = 3.0   # hPa over 3 hours


class _JsonFormatter(logging.Formatter):
    """Structured JSON log formatter for pipeline observability."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict = {
            'ts': self.formatTime(record, '%Y-%m-%dT%H:%M:%S'),
            'level': record.levelname,
            'logger': record.name,
            'msg': record.getMessage(),
        }
        if record.exc_info and record.exc_info[1]:
            entry['exc'] = self.formatException(record.exc_info)
        # Pass-through extra structured fields
        for k in ('event', 'source', 'records', 'elapsed_s', 'error_type'):
            if hasattr(record, k):
                entry[k] = getattr(record, k)
        return json.dumps(entry, ensure_ascii=False)


def setup_logging(level: int = logging.INFO, *,
                  json_format: bool = False) -> None:
    """Configure root logger for CLI scripts.

    Args:
        level: Logging level (default INFO).
        json_format: If True, emit structured JSON lines to stderr
                     instead of human-readable text (useful in CI/CD).
    """
    if json_format:
        handler = logging.StreamHandler()
        handler.setFormatter(_JsonFormatter())
        logging.root.handlers = [handler]
        logging.root.setLevel(level)
    else:
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
    # North coast (W→E): Jinshan → Green Bay → Fulong
    {"id": "jinshan",     "lat": 25.241, "lon": 121.633},
    {"id": "greenbay",    "lat": 25.189, "lon": 121.686},
    {"id": "fulong",      "lat": 25.019, "lon": 121.940},
    # NE coast (N→S): Daxi → Double Lions → Wushih → Chousui
    {"id": "daxi",        "lat": 24.933, "lon": 121.886},
    {"id": "doublelions", "lat": 24.881, "lon": 121.837},
    {"id": "wushih",      "lat": 24.871, "lon": 121.837},
    {"id": "chousui",     "lat": 24.855, "lon": 121.838},
]

# Spot → county mapping (for township forecast endpoint selection)
SPOT_COUNTY = {
    "keelung": "基隆市", "fulong": "新北市", "greenbay": "新北市",
    "jinshan": "新北市", "daxi": "宜蘭縣", "wushih": "宜蘭縣",
    "doublelions": "宜蘭縣", "chousui": "宜蘭縣",
}

# ── Northern Taiwan coverage ────────────────────────────────────────────────
# Bounding box covering north + northeast Taiwan (Keelung to Yilan coast).

TAIWAN_BBOX = {
    "lat_min": 24.5, "lat_max": 25.5,
    "lon_min": 121.0, "lon_max": 122.5,
}

# Harbour coordinates: id → (lat, lon)
HARBOUR_COORDS = {
    "keelung":   (KEELUNG_LAT, KEELUNG_LON),
}

# Spot → region mapping
SPOT_REGION = {
    "keelung":     "north",
    "fulong":      "north",
    "greenbay":    "north",
    "jinshan":     "north",
    "daxi":        "northeast",
    "wushih":      "northeast",
    "doublelions": "northeast",
    "chousui":     "northeast",
}

# Spot → nearest CWA tide forecast location (F-A0021-001 LocationName)
# Each spot mapped to its closest township tide prediction point.
SPOT_TIDE_STATION = {
    "keelung":     "基隆市中正區",
    "jinshan":     "新北市金山區",
    "greenbay":    "新北市萬里區",
    "fulong":      "新北市貢寮區",
    "daxi":        "宜蘭縣頭城鎮",
    "doublelions": "宜蘭縣頭城鎮",
    "wushih":      "宜蘭縣頭城鎮",
    "chousui":     "宜蘭縣頭城鎮",
}

# All tide station names to fetch from CWA F-A0021-001
TIDE_STATIONS = list(dict.fromkeys(SPOT_TIDE_STATION.values()))

# Spot → nearest CWA tide observation station (O-B0075-001 StationID)
# DEPRECATED: use SPOT_STATIONS["tide"] instead.  Kept temporarily for
# any downstream code that imports it; will be removed in a future cleanup.
SPOT_TIDE_OBS_STATION = {
    "keelung":     "C4B01",   # 基隆潮位站
    "jinshan":     "C4A03",   # 麟山鼻潮位站
    "greenbay":    "C4B01",   # 基隆 (closest active)
    "fulong":      "C4A05",   # 福隆潮位站 (0.2km!)
    "daxi":        "C4U02",   # 烏石潮位站
    "doublelions": "C4U02",   # 烏石潮位站
    "wushih":      "C4U02",   # 烏石潮位站 (0.4km!)
    "chousui":     "C4U02",   # 烏石潮位站
}

# ── Single source of truth for per-spot CWA station mappings ─────────────────
# Used by cwa_fetch.py (deploy-time) and must stay in sync with
# api/live-obs.js SPOT_STATIONS (real-time serverless).
# weather:      O-A0001-001 primary weather station
# weather_alt:  fallback stations if primary has no wind
# tide:         O-B0075-001 tide observation station
# buoy:         O-B0075-001 wave buoy
SPOT_STATIONS = {
    "keelung":     {"weather": "466940", "weather_alt": ["C0B050"],            "tide": "C4B01",  "buoy": "46694A"},
    "jinshan":     {"weather": "C0A940", "weather_alt": ["C0AJ20", "466940"],  "tide": "C4A03",  "buoy": "C6AH2"},
    "greenbay":    {"weather": "C0AJ20", "weather_alt": ["C0B050", "466940"],  "tide": "C4B01",  "buoy": "46694A"},
    "fulong":      {"weather": "C2A880", "weather_alt": ["C0AJ20", "C0U880"],  "tide": "C4A05",  "buoy": "46694A"},
    "daxi":        {"weather": "C0UA80", "weather_alt": ["C0U880", "C0U860"],  "tide": "C4U02",  "buoy": "46708A"},
    "doublelions": {"weather": "C0U860", "weather_alt": ["C0U880", "C0UA80"],  "tide": "C4U02",  "buoy": "46708A"},
    "wushih":      {"weather": "C0U860", "weather_alt": ["C0U880", "C0UA80"],  "tide": "C4U02",  "buoy": "46708A"},
    "chousui":     {"weather": "C0U860", "weather_alt": ["C0U880", "C0UA80"],  "tide": "C4U02",  "buoy": "46708A"},
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
    days_in_year = 366 if (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)) else 365
    gamma = 2 * math.pi / days_in_year * (doy - 1)

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
    Normalise an ISO-8601 timestamp to the canonical UTC format used
    throughout the pipeline: 'YYYY-MM-DDTHH:MM:SS+00:00'.

    Handles:
    - Bare timestamps (assumed UTC): '2026-03-30T12:00' → '2026-03-30T12:00:00+00:00'
    - Z suffix: '2026-03-30T12:00:00Z' → '2026-03-30T12:00:00+00:00'
    - Non-UTC offsets (converted): '2026-03-30T20:00:00+08:00' → '2026-03-30T12:00:00+00:00'
    """
    iso = iso.strip()
    if iso.endswith('Z'):
        iso = iso[:-1]  # strip Z, then apply length-based rules below
    if len(iso) == 16:       # YYYY-MM-DDTHH:MM
        iso += ":00+00:00"
    elif len(iso) == 19:     # YYYY-MM-DDTHH:MM:SS
        iso += "+00:00"
    elif len(iso) >= 25 and ('+' in iso[19:] or '-' in iso[19:]) and not iso.endswith('+00:00'):
        # Non-UTC offset — convert to UTC
        try:
            from datetime import datetime, timezone
            dt = datetime.fromisoformat(iso)
            dt_utc = dt.astimezone(timezone.utc)
            iso = dt_utc.strftime('%Y-%m-%dT%H:%M:%S+00:00')
        except (ValueError, TypeError):
            pass  # malformed — return as-is
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
        (max_gust is not None and max_gust >= GALE_WIND_KT) or
        (max_wind is not None and max_wind >= 28) or
        (max_hs   is not None and max_hs   >= HIGH_SEAS_M)
    )
    marginal = (
        (max_gust is not None and max_gust >= STRONG_WIND_KT) or
        (max_wind is not None and max_wind >= 17) or
        (max_hs   is not None and max_hs   >= FIRING_SURF_M) or
        total_rain >= HEAVY_RAIN_MM_6H
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
                # Exponential backoff; respect Retry-After header on 429
                delay = retry_delay * (2 ** (attempt - 1))
                if isinstance(e, urllib.error.HTTPError) and e.code == 429:
                    ra = e.headers.get('Retry-After') if e.headers else None
                    if ra:
                        try:
                            delay = max(delay, int(ra))
                        except (ValueError, TypeError):
                            pass
                log.warning("Request failed (%s); retry %d/%d in %ds …",
                            e, attempt, retries, delay)
                time.sleep(delay)
    log.error("%s fetch failed after %d attempts: %s",
              label or url, retries, last_exc)
    return None


def load_json_file(path: str, label: str = "") -> dict | list | None:
    """Load and parse a JSON file, returning None on any error."""
    log = logging.getLogger(__name__)
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError, ValueError) as e:
        log.warning("Could not load %s: %s", label or path, e)
        return None


def run_parallel(fn, items, *, max_workers: int = 4,
                 max_fail_pct: float = 30.0,
                 label: str = "parallel tasks"):
    """Run ``fn(item)`` in parallel for each item, with failure tracking.

    Returns a list of (item, result) tuples for successful calls.
    Logs a warning for each failed item. Raises RuntimeError if more than
    ``max_fail_pct`` percent of items fail.

    Args:
        fn: Callable taking a single item and returning a result.
        items: Iterable of items to process.
        max_workers: Maximum number of concurrent threads.
        max_fail_pct: Abort threshold — raise if failure rate exceeds this %.
        label: Human-readable label for log messages.
    """
    log = logging.getLogger(__name__)
    items = list(items)
    if not items:
        return []

    results = []
    failed = []

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(fn, item): item for item in items}
        for future in as_completed(futures):
            item = futures[future]
            try:
                results.append((item, future.result()))
            except Exception as exc:
                failed.append((item, exc))
                log.warning("%s: item %s failed: %s", label, item, exc)

    if failed:
        fail_pct = len(failed) / len(items) * 100
        log.warning("%s: %d/%d failed (%.0f%%)",
                    label, len(failed), len(items), fail_pct)
        if fail_pct > max_fail_pct:
            raise RuntimeError(
                f"{label}: {len(failed)}/{len(items)} failed "
                f"({fail_pct:.0f}%% > {max_fail_pct:.0f}%% threshold)"
            )

    return results


# ── Open-Meteo 6-hourly aggregation ────────────────────────────────────────

def aggregate_hourly_to_6h(raw: dict, *, model_id: str = "ECMWF-IFS",
                           source: str = "open-meteo.com") -> tuple[dict, list]:
    """Convert an Open-Meteo hourly JSON response to 6-hourly forecast records.

    This is the shared implementation used by ecmwf_fetch and ensemble_fetch
    (and potentially other Open-Meteo consumers) to avoid code duplication.

    For instantaneous variables (temperature, wind, pressure, cloud, visibility)
    we sample at the 6-hourly timestamps.  For precipitation we sum the 6 hourly
    values ending at each 6h timestamp.

    Returns (meta dict, list of record dicts).
    """
    from datetime import datetime, timezone

    h = raw.get("hourly", {})
    times = h.get("time", [])
    if not times:
        return {}, []

    def col(key):
        return h.get(key, [])

    temp   = col("temperature_2m")
    wspd   = col("windspeed_10m")
    wdir   = col("winddirection_10m")
    gust   = col("windgusts_10m")
    precip = col("precipitation")
    cloud  = col("cloudcover")
    mslp   = col("pressure_msl")
    vis    = col("visibility")
    cape   = col("cape")

    def safe(arr, i):
        return arr[i] if arr and 0 <= i < len(arr) else None

    records = []
    for i, t in enumerate(times):
        dt = datetime.fromisoformat(t if len(t) >= 19 else t + ':00').replace(tzinfo=timezone.utc)
        if dt.hour % 6 != 0:
            continue

        # Precipitation: sum 6h window [i-5 .. i] inclusive
        window_start = max(0, i - 5)
        precip_6h = sum((safe(precip, j) or 0.0) for j in range(window_start, i + 1))

        # Visibility: metres → km
        vis_val = safe(vis, i)
        vis_km = round(vis_val / 1000, 1) if vis_val is not None else None

        # Gust: max within the 6h window
        gust_vals = [safe(gust, j) for j in range(window_start, i + 1)
                     if safe(gust, j) is not None]
        gust_val = max(gust_vals) if gust_vals else None

        records.append({
            "valid_utc":    norm_utc(t),
            "temp_c":       safe(temp, i),
            "wind_kt":      safe(wspd, i),
            "wind_dir":     safe(wdir, i),
            "gust_kt":      gust_val,
            "mslp_hpa":     safe(mslp, i),
            "precip_mm_6h": round(precip_6h, 2),
            "cloud_pct":    safe(cloud, i),
            "vis_km":       vis_km,
            "cape":         safe(cape, i),
        })

    init_raw = times[0] if times else ""
    meta = {
        "model_id":  model_id,
        "init_utc":  norm_utc(init_raw) if init_raw else None,
        "source":    source,
    }
    return meta, records
