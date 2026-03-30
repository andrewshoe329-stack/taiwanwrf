# Technical Manual — Taiwan Sail & Surf Forecast

## System Overview

An automated weather forecasting pipeline for sailing and surfing in northern Taiwan. Covers Keelung harbour and 7 surf spots along the north and northeast coasts.

**Stack:** Python pipeline (GitHub Actions) → JSON data → React SPA (Vercel) + Serverless API

**Update cycle:** Pipeline runs 4x daily at 00:45, 06:45, 12:45, 18:45 UTC. Live observations update every 5 minutes via serverless proxy.

---

## 1. Data Sources

### 1.1 Weather Models (via Open-Meteo, free)
| Source | Endpoint | Resolution | Forecast Range | Used For |
|--------|----------|-----------|----------------|----------|
| ECMWF IFS | `api.open-meteo.com` | 0.25° | 7 days | Primary wind/temp/pressure forecast |
| GFS | `api.open-meteo.com` | 0.25° | 7 days | Gust backfill, ensemble member |
| ICON | `api.open-meteo.com` | 0.25° | 7 days | Ensemble member |
| JMA | `api.open-meteo.com` | 0.25° | 7 days | Ensemble member |
| ECMWF WAM | `marine-api.open-meteo.com` | 0.25° | 7 days | Wave height, swell, period |

### 1.2 CWA WRF Model (via AWS S3, public)
- CWA (Taiwan Central Weather Administration) runs WRF at 3km resolution
- GRIB2 files downloaded from `cwaopendata.s3.ap-northeast-1.amazonaws.com`
- Subset to 50nm around Keelung using eccodes

### 1.3 CWA Open Data API (requires API key)
See `CWA_API_REFERENCE.md` for complete endpoint documentation.

**Endpoints actively used:**

| Endpoint | Purpose | Frequency |
|----------|---------|-----------|
| O-A0001-001 | Weather station observations | 4x daily (pipeline) + every 5min (live) |
| O-B0075-001 | Marine buoy + tide station observations | 4x daily + every 5min (live) |
| O-A0003-001 | 10-min obs (visibility, UV) | Every 5min (live only) |
| F-A0021-001 | Tide forecast (1 month, per township) | 4x daily |
| F-D0047-001/049/069 | Township weather forecast (3-day) | 4x daily |
| F-D0047-003/051/071 | Township weather forecast (1-week) | 4x daily |
| W-C0033-002 | Weather warnings | 4x daily |
| W-C0033-003/004/005 | Specialized rain/cold/heat warnings | 4x daily |
| A-B0062-001 | Sunrise/sunset + civil twilight | Every 5min (live) |

### 1.4 Anthropic Claude API
- Generates bilingual (EN/ZH) AI narrative summary
- Model: claude-sonnet-4-6, 1200 token budget
- Receives: forecast data, accuracy metrics, CWA obs, ensemble spread, monthly climate normals

---

## 2. Pipeline Architecture

### 2.1 GitHub Actions Workflows

**wrf.yml** — WRF Download & Analysis (triggered by cron 4x daily)
1. Download CWA WRF GRIB2 from S3
2. Stale-run check (compare init_utc with previous)
3. Subset to 50nm, extract Keelung point forecast
4. Upload to Firebase (summary + per-spot WRF data)

**forecast.yml** — Forecast Pipeline (triggered by wrf.yml completion)
1. Download WRF summary from Firebase
2. Fetch ECMWF, wave, tide, CWA obs, ensemble (parallel)
3. Fetch wind grids (ECMWF + GFS) and wave grid (parallel)
4. Generate surf forecast (8 locations, parallel API calls)
5. Generate AI summary (Claude API)
6. Send alerts (LINE Notify / Telegram)
7. Track accuracy (compare forecast vs observations)
8. Upload artifacts → trigger deploy

**deploy.yml** — Vercel Deploy (triggered by forecast.yml completion)
1. Download forecast data artifacts
2. Build React SPA (`npm ci && npm run build`)
3. Deploy to Vercel (`vercel deploy --prod`)

### 2.2 Python Scripts

| Script | Input | Output | Key Dependencies |
|--------|-------|--------|-----------------|
| `taiwan_wrf_download.py` | S3 GRIB2 | `wrf_downloads/*.grb2` | eccodes |
| `wrf_analyze.py` | GRIB2 files | `keelung_summary_new.json` | eccodes, numpy |
| `ecmwf_fetch.py` | Open-Meteo API | `ecmwf_keelung.json` | urllib (stdlib) |
| `wave_fetch.py` | Open-Meteo Marine | `wave_keelung.json` | urllib |
| `tide_predict.py` | Harmonic constants | `tide_keelung.json` | math (stdlib) |
| `cwa_fetch.py` | CWA Open Data API | `cwa_obs.json` | urllib, anthropic (optional) |
| `ensemble_fetch.py` | Open-Meteo (3 models) | `ensemble_keelung.json` | urllib |
| `surf_forecast.py` | ECMWF+GFS+Marine+CWA | `surf_frontend.json` | urllib, tide_predict |
| `forecast_summary.py` | All JSONs | `ai_summary.json` | anthropic |
| `wind_grid_fetch.py` | Open-Meteo | `wind_grid_{ecmwf,gfs}.json` | urllib |
| `wave_grid_fetch.py` | Open-Meteo Marine | `wave_grid.json` | urllib |
| `accuracy_track.py` | Forecast + obs | `accuracy_log.json` | urllib |
| `notify.py` | Forecast summary | LINE/Telegram alerts | urllib |
| `firebase_storage.py` | JSON files | Firestore + Cloud Storage | firebase-admin |

### 2.3 Data Flow

```
Pipeline JSON files → frontend/public/data/ → Vercel static files
                                             ↓
                                        React SPA fetches at runtime

/api/live-obs (serverless) → CWA API (4 parallel calls) → JSON response
                                                          ↓
                                                     Frontend polls every 5min
```

**File renaming in workflow:**
```
keelung_summary_new.json → data/keelung.json
ecmwf_keelung.json       → data/ecmwf.json
wave_keelung.json         → data/wave.json
tide_keelung.json         → data/tide.json
ensemble_keelung.json     → data/ensemble.json
cwa_obs.json              → data/cwa_obs.json
accuracy_log.json         → data/accuracy.json
surf_frontend.json        → data/surf.json
ai_summary.json           → data/summary.json
```

---

## 3. Frontend Architecture

### 3.1 Tech Stack
- **React 19** + TypeScript 5.9
- **Vite 8** build tool + Tailwind CSS 4
- **Recharts 3** for data charts
- **i18next** for EN/ZH bilingual
- **Canvas API** for map rendering (no MapLibre GL — custom implementation)

### 3.2 Component Tree
```
App (providers: ForecastData, LiveObs, Timeline, Model, Location)
└── NowPage
    ├── ForecastMap (canvas: wind particles / wave heatmap)
    │   ├── Wind/Waves toggle
    │   ├── Model switcher (WRF/ECMWF/GFS)
    │   ├── Zoom controls
    │   └── Wave height legend
    ├── Location Detail (spot or harbour)
    │   ├── SwellCompass + DataCells (wind, swell, period, tide)
    │   ├── InfoPills (facing, optimal wind, wind type, warning badges)
    │   ├── Live Observations Grid (3-col: temp, wind, pressure, tide, waves, water temp, UV, visibility, currents)
    │   └── Ensemble Confidence + Accuracy Badges
    ├── AI Summary (expandable accordion)
    ├── TimelineScrubber (drag to select timestep)
    ├── ConditionsStrip (5-col stats bar, synced with timeline)
    ├── WeatherWarnings (CWA alert banners)
    └── Charts
        ├── WindChart (WRF + optional ECMWF overlay)
        ├── OceanChart (swell + wind sea + total wave + period)
        ├── TideChart (area chart + extrema reference lines)
        ├── PrecipChart (bar chart, 6h accumulation)
        └── TempChart (line chart)
```

### 3.3 Data Hooks
| Hook | Source | Refresh | Purpose |
|------|--------|---------|---------|
| `useForecastData` | `/data/*.json` | On mount + manual reload | All forecast data (10 JSON files) |
| `useLiveObs` | `/api/live-obs` | Every 5 min | Real-time CWA observations |
| `useTimeline` | Internal state | User interaction | Timeline index (0 to N timesteps) |
| `useModel` | Internal state + `/data/wind_grid_*.json` | Model switch | Wind model selection + grid data |
| `useLocation` | URL `?loc=` param | URL change | Selected spot/harbour |

### 3.4 Map Rendering

The map uses a **custom Canvas renderer** (`WindParticleSystem`) — no map library.

**Wind mode:**
- Animated particles flow along wind vectors
- Speed/color proportional to wind magnitude (dim→white→red)
- Grid data bilinearly interpolated from u/v arrays
- Supports WRF 3km, ECMWF 0.25°, GFS 0.25° grids

**Wave mode:**
- Colored heatmap cells based on significant wave height
- Color ramp: blue (0m) → teal → green → yellow → orange → red (3m+)
- Swell direction arrows at each grid point
- Legend shows 0-3m+ scale

**Projection:** Web Mercator (`log(tan(π/4 + lat/2))`) for correct aspect ratio. Supports zoom (scroll/pinch) and pan (drag). Coastline rendered from `taiwan.geojson` (MultiPolygon fill + stroke).

### 3.5 Chart System

All charts use:
- Numeric X-axis (milliseconds) for cross-chart alignment
- `timeTicks()` generates 4-5 ticks on mobile, 6-8 on desktop
- `MultiLineTick` renders two-line labels (day header + hour)
- `timeRange` prop ensures all charts share the same X domain
- `selectedMs` prop drives a reference line showing the timeline position
- Custom tooltip components with dark theme styling

---

## 4. Serverless Function (`/api/live-obs`)

### 4.1 Architecture
```
Browser → Vercel Edge (5-min cache) → Serverless Function → CWA API (4 parallel calls)
```

### 4.2 CWA Calls (Promise.allSettled — partial failure resilient)
1. **O-B0075-001** — 9 tide stations + 3 buoys → tide height, wave, sea temp, currents
2. **O-A0001-001** — 8 weather stations → temp, wind, gust, pressure, humidity
3. **O-A0003-001** — Keelung station → visibility, UV index
4. **A-B0062-001** — Keelung county → sunrise, sunset, civil twilight

### 4.3 Response Structure
```json
{
  "fetched_utc": "2026-03-30T10:00:00Z",
  "spots": {
    "keelung": {
      "station": { "temp_c": 23.8, "wind_kt": 7.2, "wind_dir": 225, ... },
      "tide": { "tide_height_m": 0.45, "tide_level": "漲潮", "sea_temp_c": 22.1 },
      "buoy": { "wave_height_m": 0.5, "wave_period_s": 5, "sea_temp_c": 21.8, ... }
    },
    "fulong": { ... },
    ...
  },
  "sun": { "sunrise": "05:48", "sunset": "18:12", "civil_twilight_start": "05:23", ... }
}
```

### 4.4 Configuration
- **Memory:** 256MB
- **Timeout:** 30s (individual API calls timeout at 15s)
- **Cache:** `s-maxage=300, stale-while-revalidate=900` (5min fresh, 15min stale)
- **Auth:** `CWA_OPENDATA_KEY` env var in Vercel project settings

---

## 5. Per-Spot Tide System

### 5.1 Tide Forecast (F-A0021-001)
CWA publishes 1-month tide forecasts for every coastal township. We fetch 5 stations in one API call:

| Station | Township | Nearest Spot |
|---------|----------|-------------|
| 基隆市中正區 | Keelung | Keelung harbour |
| 新北市金山區 | Jinshan | Jinshan |
| 新北市萬里區 | Wanli | Green Bay |
| 新北市貢寮區 | Gongliao | Fulong |
| 宜蘭縣頭城鎮 | Toucheng | Daxi, Double Lions, Wushih, Chousui |

### 5.2 Tide Predictions
- `tide_predict.py` uses offline harmonic constants (Keelung datum)
- CWA official extrema anchor the harmonic predictions via cosine interpolation (`predict_height_anchored()`)
- Per-spot: `_tide_height(dt_utc, spot_id)` routes to the correct station's CWA extrema

### 5.3 Tide Observations (O-B0075-001)
Real-time tide height from physical gauges:

| Station | ID | Distance to Spot |
|---------|------|-----------------|
| 基隆 | C4B01 | Keelung 0km |
| 福隆 | C4A05 | Fulong 0.2km |
| 烏石 | C4U02 | Wushih 0.4km |
| 麟山鼻 | C4A03 | Jinshan area |

---

## 6. Surf Spot Scoring

### 6.1 Score Components (0-14 max per timestep)
| Component | Range | How |
|-----------|-------|-----|
| Swell direction match | 0-4 | +4 good, +2 ok, 0 poor |
| Wind direction (offshore) | 0-3 | +3 offshore, +1 cross, 0 onshore |
| Wind speed | -2 to +2 | +2 (<10kt), -2 (onshore >22kt) |
| Swell height | 0-3 | +3 (0.6-2.5m), +1 (>0.3m) |
| Wave period | 0-2 | +2 (≥12s), +1 (≥9s) |
| Tide match | -1 to +1 | Per-spot preference |

### 6.2 Rating Labels
| Score | Label | Conditions |
|-------|-------|-----------|
| 11+ | Firing! | Score 11+ AND swell ≥ 0.8m |
| 9-10 | Great | High scores |
| 7-8 | Good | Solid conditions |
| 4-6 | Marginal | Surfable but not ideal |
| <4 | Poor | Below threshold |
| — | Flat | Swell < 0.3m |
| — | Dangerous | Swell > 4.5m OR wind > 32kt |

### 6.3 Data Sources per Spot
Each spot independently fetches ECMWF + GFS + Marine data at its own coordinates (24 API calls total via ThreadPoolExecutor(4)).

---

## 7. Environment Variables

### 7.1 GitHub Actions Secrets
| Secret | Required | Used By |
|--------|----------|---------|
| `CWA_OPENDATA_KEY` | Optional | cwa_fetch.py, accuracy_track.py |
| `ANTHROPIC_API_KEY` | Optional | forecast_summary.py |
| `FIREBASE_SA_KEY` | Optional | firebase_storage.py |
| `FIREBASE_PROJECT` | Optional | firebase_storage.py |
| `FIREBASE_STORAGE_BUCKET` | Optional | firebase_storage.py |
| `LINE_NOTIFY_TOKEN` | Optional | notify.py |
| `TELEGRAM_BOT_TOKEN` | Optional | notify.py |
| `TELEGRAM_CHAT_ID` | Optional | notify.py |
| `VERCEL_TOKEN` | Required | deploy.yml |
| `VERCEL_ORG_ID` | Required | deploy.yml |
| `VERCEL_PROJECT_ID` | Required | deploy.yml |

### 7.2 Vercel Environment Variables
| Variable | Required | Used By |
|----------|----------|---------|
| `CWA_OPENDATA_KEY` | Required for live data | api/live-obs.js |

---

## 8. Development

### 8.1 Local Setup
```bash
pip install -r requirements.txt
pip install pytest
cd frontend && npm ci
```

### 8.2 Running Tests
```bash
python -m pytest tests/ -v          # 404+ tests, all pure functions
cd frontend && npm run build        # TypeScript type check + Vite build
```

### 8.3 Running Pipeline Locally
```bash
python ecmwf_fetch.py --output ecmwf_keelung.json
python wave_fetch.py --output wave_keelung.json
python tide_predict.py --output tide_keelung.json
export CWA_OPENDATA_KEY=CWA-XXXX
python cwa_fetch.py --output cwa_obs.json
python surf_forecast.py --output-frontend-json surf_frontend.json --cwa-obs cwa_obs.json
export ANTHROPIC_API_KEY=sk-...
python forecast_summary.py --wrf-json keelung_summary_new.json \
  --ecmwf-json ecmwf_keelung.json --wave-json wave_keelung.json \
  --output ai_summary.html --output-json ai_summary.json
```

### 8.4 Frontend Development
```bash
cd frontend
npm run dev              # Vite dev server on localhost:5173
npm run build            # Production build to dist/
npx tsc --noEmit         # Type check only
```

### 8.5 Adding a New Surf Spot
1. Add entry to `SPOTS` list in `surf_forecast.py` with id, name, lat, lon, facing, opt_wind, opt_swell
2. Add to `SPOT_COORDS` in `config.py`
3. Add to `SPOT_COUNTY`, `SPOT_REGION`, `SPOT_TIDE_STATION`, `SPOT_TIDE_OBS_STATION` in `config.py`
4. Add to `SPOTS` array in `frontend/src/lib/constants.ts`
5. Add to `SPOT_TIDE_STATION` and `SPOT_TIDE_OBS_STATION` in `frontend/src/lib/constants.ts`
6. Add to `SPOT_STATIONS` mapping in `api/live-obs.js`

### 8.6 Adding a New CWA Endpoint
1. Document in `CWA_API_REFERENCE.md`
2. Add fetch function to `cwa_fetch.py`
3. Add to parallel batch in `fetch_all()`
4. Add output key to `cwa_obs.json` return dict
5. Add TypeScript type to `frontend/src/lib/types.ts` (CwaObs interface)
6. If live data: add to `api/live-obs.js` Promise.allSettled batch

---

## 9. Deployment

### 9.1 Production
- **Hosting:** Vercel (free tier)
- **Domain:** Configured in Vercel project settings
- **Build:** `cd frontend && npm ci && npm run build`
- **Output:** `frontend/dist/` (static SPA + serverless functions from `api/`)
- **Deploy trigger:** GitHub Actions deploy.yml (on forecast.yml completion)

### 9.2 Cache Strategy
| Path | Cache | Rationale |
|------|-------|-----------|
| `/assets/*` | 1 year immutable | Vite hashed filenames |
| `/data/*.json` | 5 min, must-revalidate | Forecast data updates 4x daily |
| `/index.html` | No cache | SPA entry point |
| `/api/live-obs` | 5 min edge, 15 min stale | Live data updates every 5 min |

### 9.3 Security Headers
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Referrer-Policy: strict-origin-when-cross-origin`

---

## 10. Monitoring

### 10.1 Pipeline Health
- GitHub Actions workflow status
- Firebase Firestore `pipeline_state/accuracy_log` for accuracy trends
- `accuracy_log.json` tracks MAE, bias, RMSE by forecast horizon

### 10.2 Live Data Health
- Vercel runtime logs for `/api/live-obs` errors
- Function returns partial data when individual CWA calls fail (Promise.allSettled)
- Frontend falls back to deploy-time data when serverless unavailable

### 10.3 Key Metrics
| Metric | Source | Target |
|--------|--------|--------|
| Temp MAE | accuracy_log | < 2°C |
| Wind MAE | accuracy_log | < 5kt |
| Wave Hs MAE | accuracy_log | < 0.5m |
| Pipeline runtime | GitHub Actions | < 5 min |
| Live-obs latency | Vercel logs | < 5s |
