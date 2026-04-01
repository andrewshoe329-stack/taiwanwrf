# Post-Audit Improvement Plan

## Status Legend
- FIXED = resolved and committed
- OPEN = still needs work
- WONTFIX = investigated and determined unnecessary

---

## Real Bugs to Fix

### P0 — Broken Features

**1. Recharts tooltip sync is a no-op** — FIXED
`defaultIndex` was removed; tooltips work on hover only.

**2. Missing `wave_height` in surf.json ratings** — FIXED
`wave_height = hs if hs else sw_hs` fallback added at surf_forecast.py line ~986.

### P1 — Inconsistencies

**3. Keelung missing current display** — FIXED
Keelung harbour now receives CWA warnings and sea comfort display via expanded `KeelungDetail` props.

**4. Sunrise fetch not in Promise.allSettled** — FIXED
Already in `Promise.allSettled` array in api/live-obs.js.

**5. Specialized warnings typed but UI incomplete** — FIXED
Per-spot CWA warning pills now displayed in `SpotDetail` (filtered by `SPOT_COUNTY`) and `KeelungDetail` (filtered by 基隆). Rain/heat/cold warnings shown as colored badges.

### P2 — Type Safety

**6. Missing TypeScript fields** — FIXED
`CwaObs.specialized_warnings`, `township_forecasts_week`, `EnsembleData.spread.precip_spread_mm` all present.

**7. `as any` casts in chart domain** — OPEN
- **Effort:** 15min

---

## Backend Robustness (from March 2026 audit)

### Critical — FIXED

**B1. TOCTOU race conditions** — FIXED
Removed redundant `.exists()` checks before `load_json_file()` calls (which already handles FileNotFoundError via OSError). Files: wrf_analyze.py, accuracy_track.py.

**B2. Silent data loss in WRF download thread pool** — FIXED
Added failure counter in taiwan_wrf_download.py. Pipeline aborts if >30% of forecast hours fail.

**B3. Precipitation accumulation reset** — FIXED
When precip accumulation resets (model restart), 6h precip is now set to `None` instead of using the raw value. Log warning added. File: wrf_analyze.py (both single-point and all-spots paths).

### High — FIXED

**B4. Empty API response logging** — FIXED
Added `log.warning()` to ecmwf_fetch.py and wave_fetch.py `process()` when API returns no hourly data.

**B5. Circular wind direction NaN guard** — FIXED
`_circular_diff()` in accuracy_track.py now returns None for non-finite inputs. Callers filter None results.

**B6. GRIB2 file TOCTOU** — FIXED
Replaced `.exists()` + `.stat()` with try/except `FileNotFoundError` in `read_point()`.

**B7. Wave fetch empty response guard** — FIXED
`wave_fetch.py` now exits non-zero if ECMWF WAM returns no records after processing.

**B8. Shared `run_parallel()` utility** — FIXED
Added `config.run_parallel()` for standardized thread pool execution with failure tracking and threshold-based abort.

### Medium — FIXED

**B9. Precip units heuristic fragile** — FIXED
Changed threshold from 0.5 to 0.01 in wrf_analyze.py to avoid 1000x multiplying legitimate drizzle values (0.3mm).

---

## CI/CD Improvements (from March 2026 audit)

**C1. Parallelized fetch steps** — FIXED
forecast.yml now runs ECMWF, wave, tide, CWA, wind grid, wave grid, current grid in parallel. Ensemble runs after ECMWF (dependency).

**C2. Tests in wrf.yml** — FIXED
Added `python -m pytest tests/ -v --tb=short` step to wrf.yml workflow.

**C3. Pip cache key includes Python version** — FIXED
Cache key changed to `pip-${{ runner.os }}-py3.11-${{ hashFiles('requirements.txt') }}`.

**C4. Frontend tests** — FIXED
Vitest configured with 68 tests covering forecast-utils.ts (degToCompass, windType, sailDecision, surfDecision, groupByDay, gustFactor, seaComfort, etc.).

---

## Frontend Improvements (from March 2026 audit)

**F1. React error boundary** — FIXED
ErrorBoundary component wraps app in main.tsx. Shows reload button on crash.

**F2. Security headers** — FIXED
vercel.json now includes Strict-Transport-Security, Permissions-Policy, Content-Security-Policy.

**F3. NowPage.tsx decomposition** — FIXED
Extracted 4 components: LiveObsCard, SpotDetail, KeelungDetail, EnsembleAccuracyPills. NowPage reduced from ~725 to ~440 lines.

**F4. useLiveObs retry/backoff** — FIXED
Exponential backoff on consecutive failures: 5m → 10m → 20m (capped). Resets on success.

**F5. Wave map legend** — FIXED
Color ramp legend (0-3+m) drawn in bottom-left corner when wave heatmap mode is active.

**F6. Rate limiting on /api/live-obs** — FIXED
In-memory token bucket rate limiter (20 req/min per IP) added to serverless function. Edge cache (s-maxage=300) provides additional dedup.

---

## Code Quality (from March 2026 audit)

**Q1. Stale backward-compat aliases removed** — FIXED
`_norm_utc = norm_utc` removed from ecmwf_fetch.py and wave_fetch.py.

**Q2. Threshold documentation** — FIXED
notify.py thresholds now cite WMO/CWA sources.

**Q3. Overly broad exception catches** — OPEN
wrf_analyze.py GRIB2 processing catches (KeyError, ValueError, TypeError, OSError).
- **Effort:** 30min

**Q4. Duplicated 6-hourly aggregation** — FIXED
Shared `aggregate_hourly_to_6h()` in config.py used by both ecmwf_fetch.py and ensemble_fetch.py.

**Q5. Scattered threshold constants** — FIXED
All 15+ threshold constants consolidated into config.py with source citations.

**Q6. Magic number MS_TO_KT** — FIXED
`MS_TO_KT = 1.94384` constant in config.py replaces all hardcoded occurrences.

---

## New Features Added (April 2026 audit)

**N1. Wind Gust Factor & Squall Alerts (B7)** — FIXED
- `gust_factor` computed as `gust_kt / max(0.5, wind_kt)` in wrf_analyze.py
- Squall risk detection: GF > 1.8 + CAPE > 1000 J/kg + 3h pressure drop > 3 hPa
- Frontend: squall risk badge in SpotDetail, gust factor in ConditionsStrip
- Alerts: squall risk notifications in notify.py

**N2. Sea State Comfort Index (B8)** — FIXED
- Wave steepness = Hs / (1.56 × Tp²) computed in wave_fetch.py
- 5-level comfort rating (Smooth→Very Rough) with star display
- Frontend: comfort stars in ConditionsStrip, SpotDetail DataCell, KeelungDetail pill

**N3. Historical Conditions Archive (B9)** — FIXED (backend)
- `archive_daily_summary()` in firebase_storage.py writes daily min/max/avg for temp, wind, gust, precip, pressure, wave
- `DailyArchive` TypeScript interface added
- CI step added to forecast.yml

**N4. Structured Logging & Pipeline Health (B10)** — FIXED
- JSON log formatter in config.py with event/source/elapsed_s fields
- `record_pipeline_health()` writes per-run health status to Firestore
- CI step added to forecast.yml

---

## Priority Order (remaining work)

1. Route weather — interpolate WRF grid along sailing waypoints
2. CWA tide API validation — compare harmonic predictions against official tables
3. `as any` casts in chart domain (Q3/7) — minor type safety improvement
4. Historical archive frontend (B9) — history page + serverless API
