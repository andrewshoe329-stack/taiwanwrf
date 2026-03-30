# Data Pipeline & Frontend Improvement Plan

Based on a full audit of the pipeline, frontend, and CWA API capabilities.

---

## Phase 1: Per-Spot Real-Time Tide Observations

**Problem:** We fetch tide *forecasts* per-spot (F-A0021-001) but only fetch tide *observations* for Keelung (C4B01). There are tide stations within 200-400m of our spots that we're ignoring.

**Available tide stations (O-B0075-001):**
| Station | Lat | Lon | Nearest Spot | Distance |
|---------|-----|-----|-------------|----------|
| C4A03 麟山鼻 | 25.284 | 121.510 | Jinshan | ~15km |
| C4B01 基隆 | 25.155 | 121.752 | Keelung | 0km |
| C4B03 長潭里 | 25.141 | 121.800 | Keelung alt | 0.5km |
| C4A02 龍洞 | 25.098 | 121.918 | Fulong area | 8km |
| C4A05 福隆 | 25.022 | 121.950 | **Fulong** | **0.2km** |
| C4U02 烏石 | 24.869 | 121.840 | **Wushih** | **0.4km** |
| C4U01 蘇澳 | 24.593 | 121.866 | — | — |

**Changes needed:**

### 1a. Add tide observation station mapping (config.py)
```python
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
```

### 1b. Fetch per-spot tide observations (cwa_fetch.py)
- Query O-B0075-001 with `StationID=C4B01,C4A05,C4U02,C4A03`
- One API call returns all 4 stations
- Parse latest TideHeight for each
- Store as `tide_observations: { "C4B01": {...}, "C4A05": {...}, ... }`

### 1c. Pass to frontend (cwa_obs.json)
- Add `tide_obs_stations` to cwa_obs.json output
- Frontend shows real-time observed tide alongside predicted

### 1d. Use for tide anchoring (surf_forecast.py)
- `_tide_height()` can use live obs to correct harmonic predictions in real-time
- Compare predicted vs observed → detect storm surge

**Estimated effort:** 4-6 hours
**Impact:** High — accurate real-time tide for all spots

---

## Phase 2: Batch & Optimize CWA API Calls

**Problem:** Pipeline makes ~15+ individual CWA API calls when 3-5 would suffice.

### 2a. Batch weather station requests
**Current:** `_fetch_spot_stations()` makes 1 API call per unique station (~8 calls)
**Fix:** Combine into 1-2 calls using comma-separated `StationId=C0A940,C0AJ20,C0U860,...`

### 2b. Add WeatherElement filters
**Current:** All O-A0001-001 calls fetch every element
**Fix:** Add `WeatherElement=AirTemperature,WindSpeed,WindDirection,GustInfo,AirPressure,RelativeHumidity` — reduces payload ~30%

### 2c. Use F-D0047-093 for township forecasts
**Current:** 3 separate calls (F-D0047-001, 049, 069)
**Fix:** 1 call to F-D0047-093 with `locationId=F-D0047-001,F-D0047-049,F-D0047-069`

### 2d. Hardcode station mappings, eliminate cwa_discover.py
**Current:** Monthly workflow discovers stations, writes cwa_stations.json (5700 lines)
**Fix:** Static dict in config.py (~50 lines). Stations rarely change. Remove cwa-discover.yml workflow.

**Estimated effort:** 3-4 hours
**Impact:** Medium — faster pipeline execution, fewer API calls

---

## Phase 3: Frontend — Show Real-Time CWA Observations

**Problem:** `cwa_obs.json` contains per-spot real-time weather/buoy observations that are loaded but never displayed.

### 3a. Real-time observation badges on location cards
When a spot is focused, show:
- **Station obs:** "Now: 22°C, W 8kt G12, 1013hPa" (from spot_obs.station)
- **Buoy obs:** "Waves: 1.2m 7s NE, Water: 22°C" (from spot_obs.buoy)
- **Tide obs:** "Tide: 0.45m (rising)" (from tide_obs_stations)
- Each with "updated X min ago" timestamp

### 3b. Observation markers on charts
- Add observed data points as dots on WindChart, OceanChart, TideChart
- Visual comparison: forecast line vs actual observation dots

### 3c. Sea temperature display
- `cwa_obs.buoy.water_temp_c` is available but never shown
- Add to spot detail panel or ConditionsStrip

**Estimated effort:** 6-8 hours
**Impact:** High — ground truth alongside forecasts

---

## Phase 4: Fix Spot-Specific Chart Data

**Problem:** When a spot is focused, several charts show incomplete or Keelung data.

### 4a. OceanChart wave_height gap
`ratingsToWaveRecords()` maps `r.wave_height` but SpotRating may not always have it.
**Fix:** In `surf_forecast.py`, ensure `wave_height` (total) is computed and included in ratings output. Currently swell_height is provided but total wave height (swell + wind sea) is sometimes missing.

### 4b. Tide extrema for spots
When a spot is focused, tide extrema (H/L markers) are empty.
**Fix:** The F-A0021-001 per-station tide forecast already has high/low times. Pass `tide_forecast_stations` data through to the frontend JSON so each spot can show its own tide H/L markers.

### 4c. ConditionsStrip fallback
When spot selected, `wave_height` and `temp_c` fall back to Keelung if undefined in spot rating.
**Fix:** Ensure surf_forecast.py populates all fields consistently. The SpotRating already has `temp_c`, `mslp_hpa`, `precip_mm_6h` fields — verify the pipeline fills them.

**Estimated effort:** 4-6 hours
**Impact:** High — consistent per-spot data

---

## Phase 5: Use Ensemble & Accuracy Data in UI

**Problem:** `ensemble.json` and `accuracy.json` are loaded but never displayed.

### 5a. Confidence indicators from ensemble spread
- Show wind/temp spread as shaded range on charts
- "Low confidence" badge when spread is high (wind_spread_kt > 8, temp_spread_c > 3)

### 5b. Model accuracy badges
- Show "Model accuracy: MAE 1.2°C temp, 3.5kt wind" from accuracy.json
- Per-horizon breakdown: "Next 24h: good | 48-72h: moderate"
- Help users gauge how much to trust the forecast

**Estimated effort:** 4-6 hours
**Impact:** Medium — builds user trust, unique feature

---

## Phase 6: 1-Week Township Forecasts

**Problem:** We only fetch 3-day township forecasts. CWA has 1-week versions.

### 6a. Add F-D0047-003/051/071 (1-week endpoints)
- Same structure as 3-day but with different elements
- Includes UV index, comfort index, feels-like temperature
- Extends forecast horizon for planning

### 6b. UV index display
- Available from 1-week township forecasts (`紫外線指數`)
- Valuable for surfers/sailors planning sun exposure
- Could show as simple badge or daily max

**Estimated effort:** 3-4 hours
**Impact:** Medium — longer planning horizon, UV safety

---

## Phase 7: Map Enhancements

### 7a. Warning zones on map
- Color overlay showing which spots are under active warnings
- Link warning areas to specific spot locations

### 7b. Buoy/tide station markers
- Show real-time buoy and tide station locations on map
- Click to see latest observation

**Estimated effort:** 4-6 hours
**Impact:** Low-medium — visual richness

---

## Priority Summary

| Phase | Effort | Impact | Dependencies |
|-------|--------|--------|-------------|
| 1. Per-spot tide obs | 4-6h | **High** | None |
| 2. Batch API calls | 3-4h | Medium | None |
| 3. Show real-time obs | 6-8h | **High** | Phase 1 |
| 4. Fix chart data | 4-6h | **High** | None |
| 5. Ensemble/accuracy UI | 4-6h | Medium | None |
| 6. 1-week forecasts | 3-4h | Medium | None |
| 7. Map enhancements | 4-6h | Low-med | Phase 3 |

**Recommended order:** Phase 4 → Phase 1 → Phase 2 → Phase 3 → Phase 5 → Phase 6 → Phase 7

Phase 4 first because it fixes existing broken behavior. Phase 1 next because it unlocks Phase 3's real-time display.
