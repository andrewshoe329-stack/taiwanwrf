# CLAUDE.md — Taiwan WRF Forecast Pipeline

## What This Project Is

Automated weather forecasting pipeline for **sailing and surfing in northern Taiwan** (Keelung harbour + 7 surf spots). Downloads CWA WRF model data from AWS S3, combines it with ECMWF IFS/WAM wave forecasts from Open-Meteo, generates HTML reports with an AI summary, and deploys to Vercel.

**Runs 4x daily** via GitHub Actions at 00:45, 06:45, 12:45, 18:45 UTC (45 min after each CWA model cycle).

**Audience:** English-speaking sailors and surfers in northern Taiwan.

---

## Architecture & Data Flow

```
GitHub Actions (cron 4x/day)
  │
  ├─ 1. taiwan_wrf_download.py   → Download CWA WRF GRIB2, subset to 50nm around Keelung
  │     Outputs: wrf_downloads/<model>_<date>_<cycle>UTC/*.grb2, .tar.gz archive
  │
  ├─ 2. Stale-run check          → Compare init_utc with prev keelung_summary.json on Drive
  │     Skip all downstream if same CWA cycle
  │
  ├─ 3a. ecmwf_fetch.py          → ECMWF IFS 0.25° point forecast (Open-Meteo, free)
  │      Output: ecmwf_keelung.json
  ├─ 3b. wave_fetch.py            → ECMWF WAM wave forecast (Open-Meteo marine, free)
  │      Output: wave_keelung.json
  │
  ├─ 4. wrf_analyze.py            → Extract Keelung point from GRIB2, compare WRF vs ECMWF
  │     Outputs: keelung_summary_new.json, forecast.html
  │
  ├─ 5. surf_forecast.py          → 7-spot surf ratings + daily planner (parallel API calls)
  │     Output: surf_forecast.html (appended to forecast.html)
  │
  ├─ 6. forecast_summary.py       → AI narrative via Anthropic Claude API
  │     Output: ai_summary.html (prepended to forecast.html)
  │
  ├─ 7. rclone upload             → Archive + summary JSON to Google Drive
  │
  └─ 8. Vercel deploy             → public/index.html (assembled from all HTML fragments)
```

---

## File Map

| File | Lines | Purpose |
|------|-------|---------|
| `config.py` | ~47 | Shared constants: `KEELUNG_LAT/LON`, `COMPASS_NAMES`, `deg_to_compass()`, `norm_utc()`, `setup_logging()` |
| `taiwan_wrf_download.py` | ~678 | Download CWA WRF GRIB2 from S3, subset with eccodes, archive with tar.gz |
| `wrf_analyze.py` | ~1270 | GRIB2 point extraction, derived fields, unified HTML table, daily summary cards |
| `ecmwf_fetch.py` | ~263 | Fetch ECMWF IFS from Open-Meteo, 6-hourly conversion, GFS gust/vis backfill |
| `wave_fetch.py` | ~452 | Fetch ECMWF WAM from Open-Meteo marine API, optional CWA wave probe |
| `surf_forecast.py` | ~810 | 7 surf spots scoring, daily activity planner, matrix + detail HTML |
| `forecast_summary.py` | ~224 | Anthropic API call, prompt construction, HTML fragment output |
| `.github/workflows/main.yml` | ~340 | Full CI/CD pipeline with concurrency control |
| `vercel.json` | ~8 | Static site config (rewrites `/` → `/index.html`) |
| `requirements.txt` | ~6 | `eccodes>=1.5,<2`, `numpy>=1.24,<3`, `anthropic>=0.40,<1` |
| `tests/` | 6 files, 113 tests | Unit tests for pure functions (pytest) |

---

## Key Design Decisions

### Shared Config (`config.py`)
All scripts import coordinates, compass functions, and `norm_utc()` from here. **Do not duplicate these** — earlier bugs came from hardcoded coordinates and duplicated utility functions.

### GRIB2 Processing
- CWA WRF uses **Lambert Conformal** grid projection (not regular lat/lon)
- eccodes is the primary GRIB2 library; cfgrib/xarray is a fallback
- Grid geometry is **cached per file** — all messages in a WRF file share the same grid
- Cache key: `(grid_type, ni, nj)` in subsetting, `(ni, nj)` in point extraction
- Precipitation is **accumulated** in WRF GRIB2 — must compute 6h increments by differencing consecutive forecast hours. F000 (analysis hour) always gets `precip_mm_6h = 0.0`
- Units: WMO standard may use metres for precip; read the `units` GRIB2 key to decide conversion

### Time Handling
- All times stored as ISO-8601 with explicit `+00:00` offset
- `norm_utc()` in `config.py` canonicalizes Open-Meteo's bare timestamps
- CST display = UTC + 8 hours
- WRF valid times derived from init_time + forecast_hour

### HTML Generation
- Single web-app output: `forecast.html` (with `<style>` blocks, class names, interactive nav)
- Dark theme: `#0f172a` base, `#1e293b` cards, `#93c5fd` accents
- Color coding: Beaufort wind scale (green→red), temperature, wave height, CAPE
- Assembled by concatenation in the workflow (cat surf >> forecast.html), then wrapped in index.html for Vercel

### Surf Spot Scoring
Scoring system (0–14 max) evaluates each 6h timestep:
- Swell direction match: +4 (good), +2 (ok), 0 (poor)
- Wind direction (offshore): +3/+1/0
- Wind speed: +2 (light <10kt), +1 (<15kt), -2 (onshore >22kt)
- Swell height: +3 (0.6–2.5m), +1 (>0.3m)
- Wave period: +2 (≥12s), +1 (≥9s)
- Ratings: Firing! (9+), Good (7+), Marginal (4+), Poor (<4)
- Dangerous: swell >4.5m or wind >32kt

### API Fetching
- All HTTP calls use `urllib.request` (stdlib only, no requests dependency)
- Retry logic: 3 attempts with 5s delay (Open-Meteo), exponential backoff (S3 downloads)
- `surf_forecast.py` fetches all 8 locations (Keelung + 7 spots) in parallel via ThreadPoolExecutor(4)
- GFS data backfills ECMWF gaps (wind gusts, visibility)

---

## The 7 Surf Spots

| Spot | Coordinates | Facing | Optimal Wind | Optimal Swell |
|------|-------------|--------|-------------|---------------|
| Fulong 福隆 | 25.019, 121.940 | NE/E | S, SW | N, NE, E |
| Green Bay 翡翠灣 | 25.189, 121.686 | NE | W, SW | E, NE |
| Jinshan 金山 | 25.238, 121.638 | NE | S, SW | N, NNE, NE, E, ESE |
| Daxi 大溪 | 24.870, 121.930 | SE | NW, W | SE, SSE, S, E |
| Wushih 烏石 | 24.862, 121.921 | E | NW, W | E, SE, SSE |
| Double Lions 雙獅 | 24.847, 121.917 | E | W, SW | ENE, E, SE, SSE |
| Chousui 臭水 | 24.820, 121.899 | E | WSW, W | ENE, E, ESE |

---

## External Dependencies & Services

| Service | Usage | Auth |
|---------|-------|------|
| CWA S3 (`cwaopendata.s3.ap-northeast-1.amazonaws.com`) | WRF GRIB2 files | Public, no auth |
| Open-Meteo (`api.open-meteo.com`) | ECMWF IFS, GFS forecasts | Free, no key, 10k req/day |
| Open-Meteo Marine (`marine-api.open-meteo.com`) | ECMWF WAM wave data | Free, no key |
| Anthropic API | AI forecast summary | `ANTHROPIC_API_KEY` secret |
| Google Drive (via rclone) | Archive storage + persistent summary.json | `RCLONE_CONFIG` secret |
| Vercel | Static site hosting | `VERCEL_TOKEN`, `VERCEL_ORG_ID`, `VERCEL_PROJECT_ID` |

---

## Running Tests

```bash
pip install -r requirements.txt
pip install pytest
python -m pytest tests/ -v
```

All 113 tests should pass. Tests cover: compass conversion, Beaufort scale, color functions, direction quality scoring, day ratings, sail ratings, time normalization, bbox geometry, and GRIB2 constant validation.

**No integration tests exist.** Tests don't require network access or GRIB2 files — they only test pure functions.

---

## Common Development Tasks

### Add a new surf spot
1. Add entry to `SPOTS` list in `surf_forecast.py` with `id`, `name`, `lat`, `lon`, `facing`, `opt_wind`, `opt_swell`, `desc`
2. The HTML generation and scoring work automatically

### Add a new weather variable from WRF GRIB2
1. Add a `(shortName_variants, typeOfLevel, level, output_key)` entry to `VARS` in `wrf_analyze.py`
2. Add a conversion entry to `DERIVED` dict
3. Add the raw key dependency to `_NEEDED_RAW_KEYS`
4. If the shortName decodes as `'unknown'`, use `--list-vars` diagnostic and add the `paramId` to `PARAMID_VARS`

### Change the target location
1. Update `KEELUNG_LAT` and `KEELUNG_LON` in `config.py`
2. All scripts import from there — no other changes needed

### Debug missing GRIB2 variables
Run: `python wrf_analyze.py --rundir <dir> --list-vars`
This prints `(shortName, typeOfLevel, level, paramId)` for f000 and f006. Compare against the `VARS` table.

### Test the AI summary locally
```bash
export ANTHROPIC_API_KEY=sk-...
python forecast_summary.py --wrf-json keelung_summary_new.json \
    --ecmwf-json ecmwf_keelung.json --wave-json wave_keelung.json \
    --output ai_summary.html
```

---

## Known Issues & Technical Debt

### Open Bugs
- **BUG-3**: First 6h precipitation window sums fewer than 6 hours (low severity — only affects the 00:00 record)
- GRIB2 grid cache key `(ni, nj)` in `read_point()` doesn't include grid type (latent bug if mixed projections)

### Code Quality Debt
- `wrf_analyze.py` `render_unified_html()` is ~340 lines of string-concatenated HTML — hard to test structurally
- `surf_forecast.py` `generate_full_html()` similar — mixing data processing and HTML
- Missing type hints on many functions
- Shell `find` in workflow step "Download and subset WRF data" is redundant (Python writes to `GITHUB_OUTPUT`)
- `forecast_summary.py` hardcodes model ID `claude-sonnet-4-5-20250514`

### UX Debt
- Unified forecast table (12+ columns) is not mobile-responsive — needs card layout on narrow viewports
- No accessibility features beyond basic skip-nav and aria-labels (no colorblind-safe indicators yet)
- No way to detect stale data on the Vercel site if the workflow fails silently (timestamp bar helps but isn't a full solution)

### Planned Features (from AUDIT.md)
1. **Tide integration** — CWA tide API or WorldTides; critical for surf/sail accuracy
2. **PWA conversion** — manifest.json, service worker, offline caching
3. **Historical accuracy tracking** — compare forecasts to observations
4. **Multi-model ensemble** — GFS, ICON, JMA via Open-Meteo

---

## Conventions

- **Logging:** All scripts use `config.setup_logging()` + `logging.getLogger(__name__)`
- **CLI:** All scripts have `argparse` CLIs with `--help`
- **Output coordination:** Scripts write to `GITHUB_OUTPUT` for inter-step communication in Actions
- **File naming:** `keelung_summary_new.json` (current run), `keelung_summary.json` (previous, on Drive), `forecast.html` (main HTML output)
- **HTML fragments:** Scripts output HTML fragments, not full documents. The workflow assembles `public/index.html` from `forecast.html`
- **Units:** Wind in knots, temp in Celsius, pressure in hPa, waves in metres, visibility in km, precipitation in mm
- **Time format:** ISO-8601 with `+00:00` offset everywhere (use `norm_utc()` from config)
