# Post-Audit Improvement Plan

## Real Bugs to Fix

### P0 — Broken Features

**1. Recharts tooltip sync is a no-op**
`defaultIndex` is not a real Recharts 3.x prop. The tooltips don't follow the timeline slider.
- **Fix:** Remove `defaultIndex`, implement controlled tooltip via Recharts' `<Tooltip trigger="click" />` or use chart `activeIndex` state. Alternatively, accept that tooltips appear on hover only and remove the broken prop.
- **Files:** All 6 chart components
- **Effort:** 2h (research + implement alternative)

**2. Missing `wave_height` in surf.json ratings**
`r.get('hs')` may return `None` when the marine API doesn't provide total wave height separately from swell. Frontend's `ratingsToWaveRecords()` maps this field, resulting in `undefined` wave_height in OceanChart.
- **Fix:** In `surf_forecast.py`, compute `wave_height = hs if hs else sw_hs` as fallback. Swell height IS total wave height when wind sea is negligible.
- **Files:** surf_forecast.py (line ~813)
- **Effort:** 30min

### P1 — Inconsistencies

**3. Keelung missing current display + margin inconsistency**
Spot detail shows sea currents; Keelung doesn't. Margin `mt-2` in spot section missing from Keelung section.
- **Fix:** Copy current display code to Keelung section, add mt-2.
- **Files:** NowPage.tsx
- **Effort:** 15min

**4. Sunrise fetch not in Promise.allSettled**
If sunrise API call fails, it could crash the entire `/api/live-obs` response (`.catch(() => null)` should handle it but the await could still throw on network errors before the catch).
- **Fix:** Move sunrise fetch into the `Promise.allSettled` array (4th item).
- **Files:** api/live-obs.js
- **Effort:** 15min

**5. Specialized warnings + 1-week forecasts typed but never consumed**
Pipeline produces `specialized_warnings` and `township_forecasts_week` but frontend has no types or UI for them.
- **Fix:** Either add to CwaObs type and display, or remove from pipeline to reduce JSON size.
- **Decision needed:** Display them or remove them?
- **Effort:** 1h if displaying, 15min if removing

### P2 — Type Safety

**6. Missing TypeScript fields**
- `CwaObs` missing `specialized_warnings` and `township_forecasts_week`
- `EnsembleData.spread` missing `precip_spread_mm`
- **Fix:** Add optional fields to interfaces
- **Effort:** 15min

**7. `as any` casts in chart domain**
All charts use `['dataMin', 'dataMax'] as any` for fallback domain.
- **Fix:** Type as `const` assertion or widen the domain type
- **Effort:** 15min

### P3 — Documentation

**8. CLAUDE.md stale**
Missing: wave_grid_fetch.py, wave heatmap feature, per-spot tide stations, live-obs serverless, improvement plan references.
- **Fix:** Update File Map, Architecture, Key Design Decisions
- **Effort:** 30min

---

## New Features to Add

### High Value

**9. Better tooltip sync (if P0-1 fix is "remove defaultIndex")**
Instead of Recharts tooltip sync, add a **floating data card** below the timeline scrubber that shows all values at the selected timestep. This would be more reliable than trying to force Recharts tooltips.
- **Effort:** 3h

**10. Wave map legend**
The wave heatmap has no legend — users don't know what the colors mean.
- **Fix:** Add a small color ramp legend (0-3m) in the bottom-left when wave mode is active.
- **Effort:** 1h

**11. Show specialized CWA warnings per spot**
Pipeline already produces township-level rain/heat/cold warnings. Should display as colored badges on the map and in spot detail.
- **Effort:** 3h

**12. Swell direction arrows on wind map**
When in wave mode, swell arrows are small and hard to see. Consider making them larger or adding a swell direction indicator to the conditions strip.
- **Effort:** 1h

### Medium Value

**13. Show accuracy by forecast horizon**
`accuracy.json` has `by_horizon` (0-24h, 24-48h, etc.) that's never displayed. "Next 24h accuracy: ±2kt wind" is more useful than overall average.
- **Effort:** 2h

**14. Show wave accuracy metrics**
`accuracy.json` has `wave.hs_mae_m` and `wave.hs_bias_m` that's never displayed.
- **Effort:** 1h

**15. Precipitation spread from ensemble**
`precip_spread_mm` is computed but never shown. Could indicate rain forecast confidence.
- **Effort:** 1h

### Low Value

**16. Remove unused wrf_spots.json loading**
Frontend loads it but most spots never have WRF data (WRF runs infrequently). Wastes a fetch call.
- **Effort:** 15min

**17. Hardcode station mappings, remove cwa_discover.py**
Monthly discovery workflow is unnecessary — stations don't move.
- **Effort:** 1h

---

## Priority Order

1. Fix P0 bugs (tooltip sync, wave_height)
2. Fix P1 inconsistencies (Keelung current, sunrise fetch, specialized warnings)
3. Fix P2 type safety
4. Add wave map legend
5. Add floating data card (better tooltip alternative)
6. Show specialized warnings per spot
7. Show accuracy by horizon
8. Update CLAUDE.md
