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

**B3. Precipitation accumulation reset warning** — FIXED
Added `log.warning()` when precip accumulation decreases (model reset). File: wrf_analyze.py.

### High — FIXED

**B4. Empty API response logging** — FIXED
Added `log.warning()` to ecmwf_fetch.py and wave_fetch.py `process()` when API returns no hourly data.

**B5. Circular wind direction NaN guard** — FIXED
`_circular_diff()` in accuracy_track.py now returns None for non-finite inputs. Callers filter None results.

### Medium — OPEN

**B6. Precip units heuristic fragile** — OPEN
wrf_analyze.py uses magnitude heuristic to detect metres vs mm. Heavy rain events (>500mm/6h) could be misidentified.
- **Effort:** 30min

**B7. Inconsistent thread pool error handling** — OPEN
Some thread pools log+continue, others don't check results.
- **Effort:** 30min

---

## CI/CD Improvements (from March 2026 audit)

**C1. Parallelized fetch steps** — FIXED
forecast.yml now runs ECMWF, wave, tide, CWA, wind grid, wave grid, current grid in parallel. Ensemble runs after ECMWF (dependency).

**C2. Tests in wrf.yml** — FIXED
Added `python -m pytest tests/ -v --tb=short` step to wrf.yml workflow.

**C3. Pip cache key includes Python version** — FIXED
Cache key changed to `pip-${{ runner.os }}-py3.11-${{ hashFiles('requirements.txt') }}`.

**C4. Frontend tests** — OPEN
No vitest/jest configured. Consider adding unit tests for forecast-utils.ts, wind-particles.ts.
- **Effort:** 3h

---

## Frontend Improvements (from March 2026 audit)

**F1. React error boundary** — FIXED
ErrorBoundary component wraps app in main.tsx. Shows reload button on crash.

**F2. Security headers** — FIXED
vercel.json now includes Strict-Transport-Security, Permissions-Policy.

**F3. NowPage.tsx is too large (~500 lines)** — OPEN
renderLiveObs defined inline, recreated every render. Consider extracting to separate component.
- **Effort:** 2h

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

**9. Wave map legend** — OPEN
The wave heatmap has no legend. Add color ramp (0-3m) in bottom-left when wave mode active.
- **Effort:** 1h

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

1. Fix P1-3 (Keelung current display)
2. Fix P1-5 (specialized warning UI)
3. Add wave map legend
4. Show accuracy by horizon
5. Extract NowPage.tsx components (F3)
6. Add frontend tests (C4)
7. Narrow GRIB2 exception catches (Q3)
