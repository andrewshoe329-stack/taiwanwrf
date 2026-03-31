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

**3. Keelung missing current display** — OPEN
Spot detail shows sea currents; Keelung doesn't.
- **Files:** NowPage.tsx
- **Effort:** 15min

**4. Sunrise fetch not in Promise.allSettled** — FIXED
Already in `Promise.allSettled` array in api/live-obs.js.

**5. Specialized warnings typed but UI incomplete** — OPEN
`specialized_warnings` and `township_forecasts_week` are typed but not fully surfaced in UI.
- **Decision:** Display them as per-spot warning pills.
- **Effort:** 1h

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

### Medium — OPEN

**B9. Precip units heuristic fragile** — OPEN
wrf_analyze.py uses magnitude heuristic to detect metres vs mm. Heavy rain events (>500mm/6h) could be misidentified.
- **Effort:** 30min

---

## CI/CD Improvements (from March 2026 audit)

**C1. Parallelized fetch steps** — FIXED
forecast.yml now runs ECMWF, wave, tide, CWA, wind grid, wave grid, current grid in parallel. Ensemble runs after ECMWF (dependency).

**C2. Tests in wrf.yml** — FIXED
Added `python -m pytest tests/ -v --tb=short` step to wrf.yml workflow.

**C3. Pip cache key includes Python version** — FIXED
Cache key changed to `pip-${{ runner.os }}-py3.11-${{ hashFiles('requirements.txt') }}`.

**C4. Frontend tests** — FIXED
Vitest configured with 50 tests covering forecast-utils.ts (degToCompass, windType, sailDecision, surfDecision, groupByDay, etc.).

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

---

## Code Quality (from March 2026 audit)

**Q1. Stale backward-compat aliases removed** — FIXED
`_norm_utc = norm_utc` removed from ecmwf_fetch.py and wave_fetch.py.

**Q2. Threshold documentation** — FIXED
notify.py thresholds now cite WMO/CWA sources.

**Q3. Overly broad exception catches** — OPEN
wrf_analyze.py GRIB2 processing catches (KeyError, ValueError, TypeError, OSError).
- **Effort:** 30min

---

## New Features to Add

### High Value

**9. Wave map legend** — FIXED
Color ramp legend (0-3+m) rendered on canvas in wave heatmap mode.

**10. Show specialized CWA warnings per spot** — OPEN
Display township-level rain/heat/cold warnings as colored badges on map and in spot detail.
- **Effort:** 3h

### Medium Value

**11. Show accuracy by forecast horizon** — OPEN
`accuracy.json` has `by_horizon` data. Show "24h accuracy: ±2kt wind" which is more useful than overall.
- **Effort:** 2h

**12. Precipitation spread from ensemble** — OPEN
`precip_spread_mm` computed but never shown. Could indicate rain confidence.
- **Effort:** 1h

### Low Value

**13. Floating data card** — OPEN
Alternative to Recharts tooltip sync: show all values at selected timestep below timeline.
- **Effort:** 3h

---

## Priority Order (remaining work)

1. Route weather — interpolate WRF grid along sailing waypoints
2. CWA tide API validation — compare harmonic predictions against official tables
