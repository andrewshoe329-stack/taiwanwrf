# CLAUDE.md — Taiwan WRF Forecast Pipeline

> **Keep this file updated.** When you add a module, change the pipeline, update secrets, or fix a bug, update CLAUDE.md in the same commit so it stays in sync with the codebase.

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
  ├─ 2. Stale-run check          → Compare init_utc with prev keelung_summary.json from Firestore
  │     Skip all downstream if same CWA cycle
  │
  ├─ 3a. ecmwf_fetch.py          → ECMWF IFS 0.25° point forecast (Open-Meteo, free)
  │      Output: ecmwf_keelung.json
  ├─ 3b. wave_fetch.py            → ECMWF WAM wave forecast (Open-Meteo marine, free)
  │      Output: wave_keelung.json
  ├─ 3c. tide_predict.py          → Harmonic tide prediction (no API, offline)
  │      Output: tide_keelung.json
  ├─ 3d. cwa_fetch.py             → CWA real-time obs: station + buoy + tide + warnings
  │      Output: cwa_obs.json (requires CWA_OPENDATA_KEY, optional)
  │
  ├─ 4. GRIB2 variable diagnostic → wrf_analyze.py --list-vars
  │
  ├─ 5. ensemble_fetch.py        → GFS/ICON/JMA from Open-Meteo, multi-model spread
  │     Output: ensemble_keelung.json
  │
  ├─ 6. surf_forecast.py         → 7-spot surf ratings + daily planner (parallel API calls)
  │     Outputs: surf_forecast.html, surf_planner.json
  │     Multi-page: --output-dir public → surf.html + spots/<id>.html (7 spot pages)
  │     Note: independently fetches ECMWF+GFS+marine for each of 8 spots
  │
  ├─ 7. wrf_analyze.py           → Extract Keelung point from GRIB2, compare WRF vs ECMWF
  │     Inputs: GRIB2 + ecmwf + wave + tide + surf_planner + ensemble + accuracy_log JSONs
  │     Outputs: keelung_summary_new.json, forecast.html (legacy single-page)
  │     Multi-page: --output-dir public → index.html (dashboard), hourly.html, accuracy.html
  │     Also: downloads accuracy_log.json from Drive for HTML badge display
  │
  ├─ 8. forecast_summary.py      → AI narrative via Anthropic Claude API (3-attempt retry)
  │     Inputs: keelung_summary_new.json + ecmwf + wave + accuracy_log
  │             + cwa_obs.json + ensemble_keelung.json
  │     Output: ai_summary.html (prepended to forecast.html)
  │     Accuracy feedback: receives rolling accuracy metrics so Claude can adjust
  │     for known model biases (e.g. WRF runs warm → temper temperature language)
  │     CWA obs: receives real-time station/buoy data as ground truth reference
  │     Ensemble: receives model spread for confidence calibration
  │
  ├─ 9. notify.py                → Threshold-based alerts via LINE Notify / Telegram
  │
  ├─10. accuracy_track.py        → Compare past forecast vs Open-Meteo + CWA observations
  │     Inputs: keelung_summary_new.json + wave_keelung.json + accuracy_log.json (from step 7)
  │     Output: accuracy_log.json (updated, uploaded to Firestore)
  │     CWA integration: fetches real-time station + buoy obs for archival
  │     Buoy verification: compares wave forecast against live CWA buoy Hs/Tp/dir
  │
  ├─11. firebase_storage.py      → Upload archive to Cloud Storage, summary + accuracy log to Firestore
  │     Retention: only latest run's archive kept; previous archives deleted
  │
  ├─12. wind_grid_fetch.py       → Gridded u/v wind fields for map overlay
  │     Outputs: frontend/public/data/wind_grid_{ecmwf,gfs}.json
  │
  ├─13. React frontend build     → Vite + React SPA (frontend/)
  │     Reads JSON data from frontend/public/data/
  │     Outputs: frontend/dist/ (static assets)
  │
  └─14. Vercel deploy            → React SPA: frontend/dist/
                                    + JSON data files in /data/
```

### Accuracy Feedback Loop

```
accuracy_track.py → accuracy_log.json (rolling 30-day metrics in Firestore)
       ↓               + buoy_verification (CWA buoy vs wave forecast)
wrf_analyze.py    → reads log for HTML accuracy badge
       ↓
forecast_summary.py → feeds bias summary + CWA obs + ensemble spread to Claude
       ↓
AI narrative adjusts confidence based on known model errors,
  real-time observations, and multi-model agreement
```

The AI summary receives a distilled accuracy summary like:
```
Recent model accuracy (last 10 verified runs):
- Temp: MAE 1.2°C (model runs warm by ~0.8°C)
- Wind: MAE 3.5kt (model underforecasts by ~1.1kt)
- Wave Hs: MAE 0.3m
```
Claude uses this to hedge language — e.g. "actual temps will likely be a degree or two cooler than shown."

---

## File Map

| File | Lines | Purpose |
|------|-------|---------|
| `i18n.py` | ~325 | Bilingual translation infrastructure: `T()`, `T_str()`, `bilingual()`, `STRINGS` dict |
| `config.py` | ~398 | Shared constants + utilities: `KEELUNG_LAT/LON`, `SPOT_COORDS`, `SPOT_COUNTY`, `SPOT_REGION`, `deg_to_compass()`, `norm_utc()`, `sunrise_sunset()`, `is_daylight()`, `setup_logging()`, `fetch_json()`, `load_json_file()` |
| `taiwan_wrf_download.py` | ~702 | Download CWA WRF GRIB2 from S3, subset with eccodes, archive with tar.gz |
| `wrf_analyze.py` | ~2410 | GRIB2 point extraction, derived fields, unified HTML table, daily summary cards |
| `ecmwf_fetch.py` | ~258 | Fetch ECMWF IFS from Open-Meteo, 6-hourly conversion, GFS gust/vis backfill |
| `wave_fetch.py` | ~438 | Fetch ECMWF WAM from Open-Meteo marine API, optional CWA wave GRIB2 probe |
| `surf_forecast.py` | ~1796 | 7 surf spots scoring, daily activity planner, matrix + detail HTML |
| `tide_predict.py` | ~323 | Tide prediction: harmonic analysis + CWA-anchored cosine interpolation |
| `accuracy_track.py` | ~736 | Forecast accuracy tracking vs Open-Meteo + CWA observations + tide accuracy |
| `forecast_summary.py` | ~647 | Anthropic API call (3-attempt retry), prompt + accuracy context, HTML + JSON output |
| `ensemble_fetch.py` | ~299 | Fetch GFS/ICON/JMA from Open-Meteo, compute multi-model spread stats |
| `wind_grid_fetch.py` | ~310 | Fetch gridded u/v wind from Open-Meteo for ECMWF/GFS map overlay |
| `notify.py` | ~401 | Threshold-based alerts via LINE Notify and Telegram Bot API |
| `firebase_storage.py` | ~280 | Firebase Firestore + Cloud Storage: read/write JSON docs, upload/cleanup GRIB2 archives |
| `cwa_fetch.py` | ~1167 | CWA Open Data API: per-spot weather stations + wave buoys + tide obs + tide forecast + township forecasts (Keelung/New Taipei/Yilan) + weather warnings |
| `cwa_discover.py` | ~475 | Monthly CWA station/buoy discovery: queries all stations, maps nearest to each spot, writes `cwa_stations.json` |
| `cwa_stations.json` | ~varies | Discovered station/buoy mapping (committed by cwa-discover workflow, read by cwa_fetch.py) |
| `frontend/` | React SPA | Vite + React + TypeScript + MapLibre GL — interactive forecast UI |
| `frontend/src/router.tsx` | ~77 | React Router config: `/`, `/spots`, `/spots/:id`, `/harbours`, `/models` |
| `frontend/src/lib/constants.ts` | ~73 | Shared constants: spot coords, regions, Beaufort scale, data file paths |
| `frontend/src/lib/types.ts` | ~184 | TypeScript interfaces for all JSON data contracts |
| `.github/workflows/wrf.yml` | ~170 | WRF download, subset, analysis — 4x daily |
| `.github/workflows/forecast.yml` | ~220 | Forecast pipeline: ECMWF/wave/ensemble fetch, surf, AI summary — 4x daily |
| `.github/workflows/deploy.yml` | ~70 | Vercel deploy triggered by forecast completion |
| `.github/workflows/cwa-discover.yml` | ~30 | Monthly workflow to discover CWA stations/buoys and commit mapping |
| `html_template.py` | ~171 | Shared page shell: `render_page()` wraps content in full HTML5 doc with header/nav/footer (legacy) |
| `pwa/` | 6 files | Legacy PWA assets (manifest, service worker, icons, styles) — superseded by React frontend |
| `vercel.json` | ~30 | Static site config (rewrites, cache headers) |
| `requirements.txt` | ~7 | `eccodes>=1.5,<2`, `numpy>=1.24,<3`, `anthropic>=0.40,<1`, `firebase-admin>=6.0,<7` |
| `tests/` | 14 files, 428 tests | Unit tests for pure functions (pytest), run in CI/CD |

---

## Key Design Decisions

### Bilingual i18n (`i18n.py`)
The site is fully bilingual English/Traditional Chinese. All user-visible strings are centralised in `i18n.py`:
- `STRINGS` dict maps keys → `{'en': '...', 'zh': '...'}` (80+ keys)
- `T(key)` → returns `<span lang="en">English</span><span lang="zh">中文</span>` for HTML
- `T_str(key, 'en'|'zh')` → plain string for a specific language (prompts, notifications)
- `bilingual(en, zh)` → inline one-off pair for strings not worth a named key
- CSS rule `html:not([lang="zh"]) [lang="zh"] { display: none }` hides inactive language
- JS toggle in page header switches `<html lang>` and saves to `localStorage`
- Browser auto-detection: `navigator.language` starting with `zh` → Chinese default
- **Not translated:** units (kt, m, °C, hPa), compass dirs, model names, Beaufort codes
- AI summary: Claude generates both languages in one API call, separated by `---`

**To add a new translatable string:** Add a key to `STRINGS` in `i18n.py`, then use `T('key')` in HTML generators.

### Shared Config (`config.py`)
All scripts import coordinates, compass functions, and `norm_utc()` from here. **Do not duplicate these** — earlier bugs came from hardcoded coordinates and duplicated utility functions. `SPOT_COORDS` is the single source of truth for spot coordinates (used by `surf_forecast.py`, `cwa_fetch.py`, `cwa_discover.py`). `SPOT_COUNTY` maps each spot to its CWA county for township forecasts.

### GRIB2 Processing
- CWA WRF uses **Lambert Conformal** grid projection (not regular lat/lon)
- eccodes is the primary GRIB2 library; cfgrib/xarray is a fallback
- Grid geometry is **cached per file** — all messages in a WRF file share the same grid
- Cache key: `(grid_type, ni, nj)` in both subsetting and point extraction
- Precipitation is **accumulated** in WRF GRIB2 — must compute 6h increments by differencing consecutive forecast hours. F000 (analysis hour) always gets `precip_mm_6h = 0.0`
- Units: WMO standard may use metres for precip; read the `units` GRIB2 key to decide conversion

### Time Handling
- All times stored as ISO-8601 with explicit `+00:00` offset
- `norm_utc()` in `config.py` canonicalizes Open-Meteo's bare timestamps
- CST display = UTC + 8 hours
- WRF valid times derived from init_time + forecast_hour

### React SPA Frontend (`frontend/`)
The primary UI is a **React single-page application** built with Vite + TypeScript + MapLibre GL:
- `/` — **Now**: current conditions, AI summary, wind map overlay
- `/spots` — **Spots**: surf spot overview with rating matrix and filters
- `/spots/:id` — **Spot Detail**: individual spot with 5-day forecast + hourly breakdown
- `/harbours` — **Harbours**: harbour-focused wind/wave/tide forecast
- `/models` — **Models**: multi-model comparison (WRF vs ECMWF vs ensemble)

Data is served as static JSON files from `frontend/public/data/` (gitignored except `taiwan.geojson`). The pipeline writes JSON outputs there; the React app fetches them at runtime.

### Legacy Multi-Page HTML
The Python scripts (`wrf_analyze.py`, `surf_forecast.py`) still generate static HTML pages via `html_template.render_page()` when `--output-dir public` is passed. This is retained for backwards compatibility but the React frontend is the primary deployment target.

### HTML Generation
- Multi-page output: `--output-dir public` generates complete HTML pages
- Legacy single-page output: `forecast.html` still works for backwards compatibility
- Dark theme: `#0f172a` base, `#1e293b` cards, `#93c5fd` accents
- Color coding: Beaufort wind scale (green→red), temperature, wave height, CAPE
- Shared page template in `html_template.py` replaces the old shell assembly in main.yml
- **Mobile cards**: Hourly forecast cards (`.fc-cards`) visible directly on mobile (≤640px), hidden on desktop. Cards include wind direction arrows and expandable extra metrics.
- **Tide sparklines**: Daily summary cards include inline SVG sparkline (`_tide_sparkline_svg()`) showing 24h tide curve with high/low dots and "now" marker for today. Uses `predict_height()` from `tide_predict.py`.
- **AI summary sections**: Claude returns `[WIND]`/`[WAVES]`/`[OUTLOOK]` markers; `render_html()` parses them into card grid (`.ai-cards`). Falls back to plain text if no markers. Token budget: 1200.
- **Spot filters**: Client-side JS filter (All/Good+/Firing) toggles visibility of matrix rows, detail sections, and best-time rows via `data-best-rating` attributes. Rating levels: 5=firing, 4=good, 3=marginal, 2=poor, 1=flat, 0=dangerous.

### Surf Spot Scoring
Scoring system (0–14 max) evaluates each 6h timestep:
- Swell direction match: +4 (good), +2 (ok), 0 (poor)
- Wind direction (offshore): +3/+1/0
- Wind speed: +2 (light <10kt), +1 (<15kt), -2 (onshore >22kt)
- Swell height: +3 (0.6–2.5m), +1 (>0.3m)
- Wave period: +2 (≥12s), +1 (≥9s)
- Ratings: Firing! (9+), Good (7+), Marginal (4+), Poor (<4)
- Dangerous: swell >4.5m or wind >32kt
- Best-time selection: only daylight windows considered (uses `sunrise_sunset()` from config)
- Sunrise/sunset displayed in "Best Time to Surf" section per day

### API Fetching
- All HTTP calls use `urllib.request` (stdlib only, no requests dependency)
- Shared `fetch_json()` in `config.py` — centralised retry logic used by all fetch modules
- Retry logic: 3 attempts with 5s delay (Open-Meteo), exponential backoff (S3 downloads)
- `surf_forecast.py` fetches all 8 locations (Keelung + 7 spots) in parallel via ThreadPoolExecutor(4)
- GFS data backfills ECMWF gaps (wind gusts, visibility)
- `ensemble_fetch.py` fetches GFS/ICON/JMA in parallel via ThreadPoolExecutor(3)
- `cwa_fetch.py` fetches Keelung station + nearest wave buoy from CWA Open Data API
- `notify.py` sends threshold-based alerts via LINE Notify and Telegram Bot API

### Accuracy Tracking
- `accuracy_track.py` compares past forecasts against Open-Meteo observations (blended CWA/JMA)
- Optionally enriches with direct CWA station/buoy data when `CWA_OPENDATA_KEY` is set
- Metrics: MAE, bias, RMSE for temp, wind speed, wind direction, precipitation, pressure
- Wave metrics: Hs MAE/bias, period MAE, direction circular MAE
- Stratified by forecast horizon: 0-24h, 24-48h, 48-72h, 72h+
- Rolling 30-day log stored in Firebase Firestore as `pipeline_state/accuracy_log`
- CWA snapshots (live station + buoy readings) attached to each log entry for archival
- **Firebase dual-write** (optional): `_write_to_firestore()` writes each log entry to Firestore collection `accuracy_log` when `FIREBASE_PROJECT` env var is set. Requires `firebase-admin` package and service account key via `GOOGLE_APPLICATION_CREDENTIALS`. Graceful skip if not configured.

---

## The 7 Surf Spots

| Spot | Coordinates | Facing | Optimal Wind | Optimal Swell |
|------|-------------|--------|-------------|---------------|
| Jinshan 金山 (中角灣) | 25.241, 121.633 | NE | S, SW | N, NNE, NE, E, ESE |
| Green Bay 翡翠灣 | 25.189, 121.686 | NE | W, SW | E, NE |
| Fulong 福隆 | 25.019, 121.940 | NE/E | S, SW | N, NE, E |
| Daxi 大溪 (蜜月灣) | 24.933, 121.886 | SE | NW, W | SE, SSE, S, E |
| Double Lions 雙獅 (外澳) | 24.881, 121.837 | E | W, SW | ENE, E, SE, SSE |
| Wushih 烏石 (北堤) | 24.871, 121.837 | E | NW, W | E, SE, SSE |
| Chousui 臭水 (大坑沙灘) | 24.855, 121.838 | E | WSW, W | ENE, E, ESE |

---

## External Dependencies & Services

| Service | Usage | Auth |
|---------|-------|------|
| CWA S3 (`cwaopendata.s3.ap-northeast-1.amazonaws.com`) | WRF GRIB2 files | Public, no auth |
| CWA Open Data (`opendata.cwa.gov.tw`) | Station + marine obs + tide forecast + township forecast + warnings | `CWA_OPENDATA_KEY` secret (optional) |
| Open-Meteo (`api.open-meteo.com`) | ECMWF IFS, GFS forecasts | Free, no key, 10k req/day |
| Open-Meteo Marine (`marine-api.open-meteo.com`) | ECMWF WAM wave data | Free, no key |
| Anthropic API | AI forecast summary | `ANTHROPIC_API_KEY` secret |
| LINE Notify (`notify-api.line.me`) | Push alerts | `LINE_NOTIFY_TOKEN` secret (optional) |
| Telegram Bot API (`api.telegram.org`) | Push alerts | `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` (optional) |
| Firebase (Firestore + Cloud Storage) | Pipeline state (summary, accuracy log), GRIB2 archive hosting | `FIREBASE_PROJECT`, `FIREBASE_SA_KEY`, `FIREBASE_STORAGE_BUCKET` |
| Vercel | Static site hosting | `VERCEL_TOKEN`, `VERCEL_ORG_ID`, `VERCEL_PROJECT_ID` |

### CWA Open Data Endpoint IDs

All endpoints use base URL `https://opendata.cwa.gov.tw/api/v1/rest/datastore/{ID}`.

| Endpoint ID | Chinese Name | Usage in cwa_fetch.py |
|-------------|-------------|----------------------|
| **O-A0001-001** | 氣象觀測站-全測站逐時氣象資料 | `STATION_ENDPOINT` — surface weather obs (all stations) |
| **O-A0003-001** | 氣象觀測站-10分鐘綜觀氣象資料 | `STATION_HOURLY_ENDPOINT` — 10-min conventional obs |
| **O-A0002-001** | 雨量觀測站-雨量資料 | `RAIN_GAUGE_ENDPOINT` — automatic rain gauge |
| **O-B0075-001** | 海象監測資料-48小時浮標站與潮位站海況監測資料 | `MARINE_OBS_ENDPOINT` — combined buoy + tide (48h). Replaces deprecated O-A0017-001 (tide), O-A0018-001 (buoy), O-A0019-001 (sea temp). Supports `StationID` query param. REST API returns `Records.SeaSurfaceObs.Location[]` with nested `Station` + `StationObsTimes`. |
| O-B0075-002 | 海象監測資料-30天浮標站與潮位站海況監測資料 | Not used (30-day version of above) |
| **F-A0021-001** | 潮汐預報-未來1個月潮汐預報 | `TIDE_FORECAST_ENDPOINT` — official tide forecast |
| **F-D0047-001** | 鄉鎮天氣預報-宜蘭縣未來3天天氣預報 | `TOWNSHIP_FORECAST_ENDPOINTS["宜蘭縣"]` — Yilan 3-day forecast (Daxi, Wushih, Double Lions, Chousui) |
| **F-D0047-049** | 鄉鎮天氣預報-基隆市未來3天天氣預報 | `TOWNSHIP_FORECAST_ENDPOINT` — Keelung 3-day forecast |
| F-D0047-051 | 鄉鎮天氣預報-基隆市未來1週天氣預報 | Not used (1-week version) |
| **F-D0047-069** | 鄉鎮天氣預報-新北市未來3天天氣預報 | `TOWNSHIP_FORECAST_ENDPOINTS["新北市"]` — New Taipei 3-day forecast (Fulong, Green Bay, Jinshan) |
| **W-C0033-002** | 天氣特報-各別天氣警特報之內容及所影響之區域 | `WARNING_ENDPOINT` — weather warnings & advisories |

**Note on F-D0047 numbering:** Odd numbers are 3-day, even+1 are 1-week. Key city codes: 049=基隆市, 061=臺北市, 069=新北市. Full list at CWA Open Data portal.

**CWA REST API key casing:** Some endpoints use **capitalized** top-level keys (`"Success"`, `"Result"`, `"Records"`) while others use lowercase (`"success"`, `"records"`). All parsing functions check both. For O-B0075-001, `Records` is **top-level** (sibling of `Result`). For F-A0021-001 and F-D0047-049, lowercase `records` is used.

**F-A0021-001 (tide forecast) structure:** `records.TideForecasts[]` is a list where each item wraps a `Location` dict: `TideForecasts[i].Location.{LocationName, TimePeriods.Daily[].Time[].{DateTime, Tide, TideHeights.{AboveLocalMSL, AboveTWVD}}}`. Heights are in **cm** (integers), code converts to metres.

**F-D0047-049 (township forecast) structure:** `records.Locations[].Location[]` — extra `Locations` wrapper array (contains `LocationsName: "基隆市"`, `Location[]` with per-district data). Each Location has `WeatherElement[]` with `ElementName` (Chinese) and `Time[]`.

**O-B0075-001 response structure:**
```
{ "Success": "true",
  "Result": { "ResourceId": "O-B0075-001", "Fields": [...] },
  "Records": { "SeaSurfaceObs": { "Location": [
    { "Station": { "StationID": "C4B01" },
      "StationObsTimes": { "StationObsTime": [
        { "DateTime": "...", "WeatherElements": {
            "TideHeight": "0.44", "TideLevel": "退潮",
            "SeaTemperature": "20.1", "StationPressure": "1014.7",
            "PrimaryAnemometer": { "WindSpeed": "1.8", ... }
        }}
      ]}}
  ]}}}
```

**Marine station IDs:** Keelung tide station = `C4B01` (in O-B0075-001), buoy = `46694A` (龍洞). Code uses `KEELUNG_TIDE_STATION_IDS = {"KL01", "C4B01"}` to match both legacy and REST API IDs.

---

## JSON File Contracts

These are the intermediate JSON files passed between pipeline steps:

### `keelung_summary_new.json` (produced by wrf_analyze.py)
```
{ "meta": { "model_id", "init_utc", "source" },
  "records": [{ "valid_utc", "fh", "temp_c", "wind_kt", "wind_dir",
                "gust_kt", "mslp_hpa", "precip_mm_6h", "cape", ... }] }
```

### `ecmwf_keelung.json` (produced by ecmwf_fetch.py)
```
{ "meta": { "model_id": "ECMWF-IFS", "init_utc", "source" },
  "records": [{ "valid_utc", "wind_kt", "wind_dir", "gust_kt",
                "temp_c", "precip_mm_6h", "vis_km", ... }] }
```

### `wave_keelung.json` (produced by wave_fetch.py)
```
{ "ecmwf_wave": { "meta": {...}, "records": [{
    "valid_utc", "wave_height", "wave_direction", "wave_period",
    "swell_wave_height", "swell_wave_direction", "swell_wave_period",
    "wind_wave_height", "wind_wave_direction", "wind_wave_period" }] },
  "cwa_wave": null | { "meta": {...}, "records": [...] } }
```

### `tide_keelung.json` (produced by tide_predict.py)
```
{ "meta": { "station": "Keelung", "lat", "lon" },
  "predictions": [{ "time_utc", "height_m" }],
  "extrema": [{ "time_utc", "height_m", "type": "high"|"low" }] }
```

### `ensemble_keelung.json` (produced by ensemble_fetch.py)
```
{ "models": { "GFS": {...}, "ICON": {...}, "JMA": {...} },
  "spread": { "wind_spread_kt", "temp_spread_c", ... } }
```

### `cwa_obs.json` (produced by cwa_fetch.py)
```
{ "source": "CWA Open Data", "fetched_utc",
  "station": { "station_id", "obs_time", "temp_c", "wind_kt", "wind_dir",
               "gust_kt", "pressure_hpa", "humidity_pct", "precip_mm" },
  "buoy": { "buoy_id", "obs_time", "wave_height_m", "wave_period_s",
            "wave_dir", "peak_period_s", "water_temp_c" },
  "all_buoys": [{ "buoy_id", "buoy_name", "lat", "lon", "wave_height_m", ... }],
  "spot_obs": {
    "fulong": { "station": { "station_id", "distance_km", "temp_c", ... },
                "buoy": { "buoy_id", "distance_km", "wave_height_m", ... } },
    ...per spot (keelung + 7 surf spots)...
  },
  "tide": { "station_id", "obs_time", "tide_height_m" },
  "township_forecast": { "location", "elements": {...} },
  "township_forecasts": {
    "基隆市": { "location", "elements" },
    "新北市": { "location", "elements" },
    "宜蘭縣": { "location", "elements" }
  },
  "warnings": [{ "type", "severity", "area", "description",
                 "issued_utc", "expires_utc" }] }
```

### `cwa_stations.json` (produced by cwa_discover.py, committed to repo)
```
{ "discovered_utc",
  "spots": {
    "keelung": { "station_id", "station_name", "station_dist_km",
                 "buoy_id", "buoy_name", "buoy_dist_km" },
    ...per spot...
  },
  "all_stations": [{ "station_id", "station_name", "lat", "lon" }],
  "all_buoys": [{ "buoy_id", "buoy_name", "lat", "lon" }] }
```

### `accuracy_log.json` (rolling, on Drive)
```
[{ "init_utc", "verified_utc", "model_id", "n_compared",
   "temp_mae_c", "temp_bias_c", "wind_mae_kt", "wind_bias_kt",
   "wdir_mae_deg", "mslp_mae_hpa",
   "by_horizon": { "0-24h": {...}, "24-48h": {...}, ... },
   "wave": { "hs_mae_m", "hs_bias_m", "tp_mae_s", ... },
   "buoy_verification": { "buoy_id", "hs_obs_m", "hs_fc_m", "hs_error_m",
                           "tp_obs_s", "tp_fc_s", "tp_error_s", ... },
   "tide_accuracy": { "obs_time", "obs_height_m", "harmonic_height_m",
                       "harmonic_error_m", "anchored_height_m", "anchored_error_m" },
   "cwa_snapshot": { "station": {...}, "buoy": {...} } }]
```

### `surf_frontend.json` (produced by surf_forecast.py, consumed by React frontend)
```
{ "meta": { "generated_utc" },
  "spots": [{ "id", "name", "lat", "lon", "facing", "region",
               "days": [{ "date", "label", "score", "best_time",
                          "records": [{ "valid_utc", "sw_hs", "sw_dir", "sw_tp",
                                        "wind", "w_dir", "score", "label" }] }] }] }
```

### `ai_summary.json` (produced by forecast_summary.py)
```
{ "generated_utc", "model_init_utc",
  "sections": { "wind": "...", "waves": "...", "outlook": "..." },
  "full_text": { "en": "...", "zh": "..." } }
```

### `wind_grid_{ecmwf,gfs}.json` (produced by wind_grid_fetch.py)
```
{ "model": "ECMWF-IFS"|"GFS",
  "bounds": { "lat_min", "lat_max", "lon_min", "lon_max" },
  "grid": { "nx", "ny" },
  "timesteps": [{ "valid_utc", "u": [[...]], "v": [[...]] }] }
```

---

## Running Tests

```bash
pip install -r requirements.txt
pip install pytest
python -m pytest tests/ -v
```

428 tests should pass. Tests cover: compass conversion, Beaufort scale, color functions, direction quality scoring, day ratings, sail ratings, time normalization, bbox geometry, GRIB2 constant validation, tide prediction (semidiurnal pattern, extrema detection, CWA-anchored interpolation), accuracy tracking (error metrics, buoy verification, tide accuracy), CWA API parsing (station, buoy, tide, tide forecast, township forecast, warnings), AI summary prompt construction (with CWA obs and ensemble spread), notification alert dedup, and shared HTTP fetch/JSON loading utilities.

**Tests run in CI/CD** — the GitHub Actions workflow runs `python -m pytest tests/ -v` before deployment.

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
    --accuracy-log accuracy_log.json \
    --output ai_summary.html
```

### Test CWA observations locally
```bash
export CWA_OPENDATA_KEY=CWA-XXXX
python cwa_fetch.py --output cwa_obs.json
```

---

## Known Issues & Technical Debt

### Open Bugs
- No known open bugs

### Known Redundancies
- `surf_forecast.py` independently fetches ECMWF+GFS+marine for all 8 spots (24 API calls) even though `ecmwf_keelung.json` and `wave_keelung.json` already cover Keelung. The 7 surf spots need their own coordinates for wave data, but the Keelung fetch is redundant.
- GFS data is fetched 3 times: once in `ecmwf_fetch.py` (gust backfill), once in `ensemble_fetch.py`, once per spot in `surf_forecast.py`.
- These are acceptable because Open-Meteo is free and the calls are fast, but consolidating would save ~15-20s per run.

### Code Quality Debt
- `wrf_analyze.py` `render_unified_html()` is ~440 lines — partially refactored with colorblind + ensemble helpers extracted; `ForecastContext` dataclass introduced to reduce parameter count
- `surf_forecast.py` `generate_full_html()` refactored into `_render_rating_matrix()`, `_render_spot_detail()`, `_render_surf_legend()`
- Missing type hints on many functions
- Shell `find` in workflow step "Download and subset WRF data" is redundant (Python writes to `GITHUB_OUTPUT`)

### UX Debt
- Mobile forecast cards implemented but desktop table (12+ columns) still has horizontal scroll
- Colorblind-safe CSS indicators added (✓/⚠/✗ symbols via `.cb-ok`/`.cb-warn`/`.cb-danger`)
- Stale data detection: timestamp bar + age classes + service worker CACHE_HIT + auto-warning at 12h

### Potential Future Features
1. **Route weather** — interpolate WRF grid along sailing waypoints
2. **Spot webcam links** — embed or link to surf spot cameras
3. **Consolidate surf_forecast.py fetches** — pass pre-fetched ecmwf/wave/ensemble JSONs to avoid redundant API calls
4. **CWA tide API validation** — compare harmonic predictions against official CWA tide tables
5. **Station bias correction** — use CWA station obs at T0 to apply real-time drift correction to WRF forecast
6. **Directional wave scoring** — weight surf spot energy by `cos²(swell_angle - beach_angle)` for realistic quality estimates

---

## Conventions

- **Logging:** All scripts use `config.setup_logging()` + `logging.getLogger(__name__)`
- **CLI:** All scripts have `argparse` CLIs with `--help`
- **Output coordination:** Scripts write to `GITHUB_OUTPUT` for inter-step communication in Actions
- **File naming:** `keelung_summary_new.json` (current run), `keelung_summary.json` (previous, on Drive), `forecast.html` (main HTML output)
- **HTML fragments:** Scripts output HTML fragments, not full documents. The workflow assembles `public/index.html` from `forecast.html`
- **Units:** Wind in knots, temp in Celsius, pressure in hPa, waves in metres, visibility in km, precipitation in mm
- **Time format:** ISO-8601 with `+00:00` offset everywhere (use `norm_utc()` from config)
- **Keep CLAUDE.md updated:** Any commit that changes the pipeline, adds a module, updates secrets, or fixes a bug should also update this file.
