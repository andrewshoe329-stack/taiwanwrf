# Comprehensive Improvement Plan

## Pipeline + Frontend — Full CWA API Integration

---

## Phase 1: Per-Spot Tide Observations + Storm Surge Detection

**Goal:** Fetch real-time tide heights from stations at each spot. Detect storm surge by comparing predicted vs observed.

### Pipeline Changes (cwa_fetch.py)

**1a. Add tide obs stations to O-B0075-001 query**
- Current: `StationID=C4B01,46694A,...` (Keelung only for tide)
- New: `StationID=C4B01,C4A05,C4U02,C4A03,...` (add Fulong, Wushih, Jinshan)
- One API call returns all stations
- Parse latest `TideHeight` per station
- Store in `cwa_obs.json` as:
```json
"tide_obs_stations": {
  "C4B01": { "station_name": "基隆", "obs_time": "...", "tide_height_m": 0.45, "tide_level": "退潮", "sea_temp_c": 22.1 },
  "C4A05": { "station_name": "福隆", "obs_time": "...", "tide_height_m": 0.38, "sea_temp_c": 21.8 },
  "C4U02": { "station_name": "烏石", "obs_time": "...", "tide_height_m": 0.42, "sea_temp_c": 22.3 }
}
```

**1b. Storm surge detection (accuracy_track.py or new module)**
- Compare `tide_obs_stations[X].tide_height_m` vs `predict_height_anchored()` at same time
- If `abs(observed - predicted) > 0.3m` → storm surge flag
- Store in `cwa_obs.json` as `"storm_surge": { "C4B01": { "predicted_m": 0.40, "observed_m": 0.75, "surge_m": 0.35 } }`

### Frontend Changes

**1c. Show live tide obs in spot detail**
Already partially done (live obs box). Enhance:
- Show observed tide height alongside predicted
- If storm surge detected, show red warning badge: "⚠ Storm Surge +35cm"

**1d. Tide obs dots on TideChart**
- Plot observed tide heights as dots on the tide prediction curve
- Visual comparison: predicted line vs actual observation dots
- Shows if prediction is tracking reality

### Config
```python
# config.py — already done
SPOT_TIDE_OBS_STATION = {
    "keelung": "C4B01", "jinshan": "C4A03", "greenbay": "C4B01",
    "fulong": "C4A05", "daxi": "C4U02", "doublelions": "C4U02",
    "wushih": "C4U02", "chousui": "C4U02",
}
```

**Effort:** 6-8h | **Impact:** High — ground truth tide data, safety feature

---

## Phase 2: Water Temperature Display

**Goal:** Show sea water temperature prominently. Surfers decide wetsuit thickness based on this.

### Pipeline Changes

**2a. Already available** — `cwa_obs.json` spot_obs already includes buoy `water_temp_c` and tide station `SeaTemperature`. No pipeline changes needed.

### Frontend Changes

**2b. Add water temp to ConditionsStrip (spot mode)**
- Current: Wave Height, Temp, Precip, Pressure (4 cols)
- New: Wave Height, Water Temp, Air Temp, Precip, Pressure (5 cols)
- Or replace Pressure with Water Temp (4 cols, more important for surfers)

**2c. Add water temp to spot detail compass area**
- Show in the live observations box (already added in latest commit)
- Make it more prominent — could be its own DataCell in the 2x2 grid

**2d. Water temp on OceanChart**
- Add as a second Y-axis line (like period) on the ocean chart
- Dashed line, right axis, different color
- Only if buoy data provides a time series (currently just latest obs)

**Effort:** 2-3h | **Impact:** High — surfers need this daily

---

## Phase 3: Visibility for Sailors

**Goal:** Show visibility data from CWA stations. Critical for Keelung harbour sailing.

### Pipeline Changes

**3a. Fetch visibility from O-A0003-001 (10-min obs)**
- New function: `fetch_visibility(api_key, station_id)`
- Query with `WeatherElement=VisibilityDescription`
- O-A0003-001 has `VisibilityDescription` that O-A0001-001 doesn't
- Store in `cwa_obs.json` per-spot: `"visibility_km": 8.5`

### Frontend Changes

**3b. Show visibility in ConditionsStrip (default/harbour mode)**
- Add as a stat: "Vis 8km" or "Vis ∞"
- Only show for Keelung harbour (sailing context) or when < 10km (fog warning)

**3c. Fog warning integration**
- If visibility < 2km, show amber warning card in WeatherWarnings
- "⚠ Low visibility at Keelung: 800m — dense fog"

**Effort:** 3-4h | **Impact:** Medium-High for sailors

---

## Phase 4: UV Index

**Goal:** Show UV exposure risk for outdoor water sports.

### Pipeline Changes

**4a. Fetch UV from O-A0003-001 or O-A0005-001**
- O-A0003-001: real-time `UVIndex` from 10-min obs (during daytime only)
- O-A0005-001: daily max UV per station (published ~2PM)
- Also available from F-D0047-003 (1-week township forecast): `紫外線指數`

**4b. Store in cwa_obs.json**
```json
"uv": { "current": 8, "daily_max": 11, "level": "extreme" }
```

### Frontend Changes

**4c. UV badge on spot detail**
- Color-coded pill: Green (0-2), Yellow (3-5), Orange (6-7), Red (8-10), Purple (11+)
- Show next to info pills: "UV 8 🔴"

**4d. UV in ConditionsStrip** (optional)
- Compact: "UV 8" as one stat column

**Effort:** 3-4h | **Impact:** Medium — summer safety

---

## Phase 5: Ensemble Confidence + Accuracy Display

**Goal:** Show users how much to trust the forecast.

### Pipeline Changes

None needed — `ensemble.json` and `accuracy.json` are already produced and served.

### Frontend Changes

**5a. Confidence badge in spot detail**
Below info pills, show:
- "Forecast confidence: High ★★★" (wind spread < 5kt, temp spread < 2°C)
- "Forecast confidence: Moderate ★★☆" (wind spread 5-10kt)
- "Forecast confidence: Low ★☆☆" (wind spread > 10kt)
Based on `ensemble.json` spread values.

**5b. Accuracy info in expandable section**
Below AI summary or in a new accordion:
- "Model accuracy (last 10 runs): Temp ±1.2°C, Wind ±3.5kt"
- "WRF tends to run warm by ~0.8°C"
- From `accuracy.json` latest entries

**5c. Confidence bands on charts** (stretch goal)
- Shade WindChart with ±spread from ensemble
- Light gray shading around the forecast line
- Shows where models agree vs disagree

**Effort:** 4-6h | **Impact:** Medium — unique feature, builds trust

---

## Phase 6: Batch & Optimize API Calls

**Goal:** Reduce ~15 CWA API calls to ~5. Faster pipeline, less load on CWA.

### Pipeline Changes

**6a. Batch weather station requests**
- Current: `_fetch_spot_stations()` makes 1 call per station (~8 calls)
- New: 1-2 calls with `StationId=C0A940,C0AJ20,C0U860,C0B050,...`
- O-A0001-001 supports comma-separated StationId

**6b. Consolidate township forecasts**
- Current: 3 calls (F-D0047-001, 049, 069)
- New: 1 call to F-D0047-093 with `locationId=F-D0047-001,F-D0047-049,F-D0047-069`

**6c. Add WeatherElement filters**
- O-A0001-001: `WeatherElement=AirTemperature,WindSpeed,WindDirection,GustInfo,AirPressure,RelativeHumidity`
- O-B0075-001: `WeatherElement=TideHeight,TideLevel,WaveHeight,WaveDirection,WavePeriod,SeaTemperature`
- Reduces payload ~30%

**6d. Hardcode station mappings**
- Replace `cwa_discover.py` monthly workflow with static dict in `config.py`
- Move essential mappings from `cwa_stations.json` (5700 lines) to `config.py` (~50 lines)

**Effort:** 3-4h | **Impact:** Medium — pipeline efficiency

---

## Phase 7: 1-Week Extended Forecast

**Goal:** Extend planning horizon from 3 days to 7 days with UV and comfort data.

### Pipeline Changes

**7a. Fetch 1-week township forecasts**
- Add F-D0047-003 (宜蘭 1-week), F-D0047-051 (基隆 1-week), F-D0047-071 (新北 1-week)
- Or use F-D0047-093 with `locationId=F-D0047-003,F-D0047-051,F-D0047-071`
- Extra elements: `紫外線指數`, `最高體感溫度`, `最低體感溫度`, `平均溫度`

**7b. Store as extended forecast in output**
- `township_forecast_week` key in cwa_obs.json
- Or separate `township_week.json` file

### Frontend Changes

**7c. Extended daily summary cards**
- Days 4-7 show: weather icon, min/max temp, UV index, rain probability, wind
- Less detailed than 3-day (12h periods instead of 3h)

**7d. UV forecast in daily planner**
- Show daily max UV for trip planning

**Effort:** 4-6h | **Impact:** Medium — planning

---

## Phase 8: Sea Currents Display

**Goal:** Show ocean current data from buoys for sailing/swimming safety.

### Pipeline Changes

**8a. Parse SeaCurrents from O-B0075-001**
- Buoys with `SeaCurrents` active: 46694A (龍洞), 46708A (龜山島), C6AH2 (富貴角)
- Fields: `CurrentDirection`, `CurrentDirectionDescription`, `CurrentSpeed`, `CurrentSpeedInKnots`
- Store per-buoy in cwa_obs.json

### Frontend Changes

**8b. Current arrow on spot detail**
- Small directional arrow showing current direction + speed
- "Current: 0.8kt NE →"
- Only show if data available from nearest buoy

**8c. Current info in live observations box**
- Add to existing live obs section when spot focused

**Effort:** 3-4h | **Impact:** Medium for sailors

---

## Phase 9: Enhanced Warnings

**Goal:** Township-level severity-graded warnings mapped to specific spots.

### Pipeline Changes

**9a. Fetch specialized warnings**
- W-C0033-003 (heavy rain): filter `CountyName=基隆市,新北市,宜蘭縣`, `expires=true`
- W-C0033-005 (high temp): same counties, `expires=true`
- W-C0033-004 (low temp): same counties, `expires=true`

**9b. Map warnings to spots**
- Match `TownName` in warning to spot's township
- Store per-spot: `"spot_warnings": { "fulong": ["Heavy Rain Warning 🟡"], ... }`

### Frontend Changes

**9c. Spot-specific warning badges**
- Show colored badge on map labels when spot has active warning
- In spot detail: specific warning card with severity level

**9d. Warning overlay on map**
- Highlight affected coastal areas with warning color

**Effort:** 4-6h | **Impact:** Medium — safety

---

## Phase 10: Official Sunrise/Sunset + Moon Phase

**Goal:** Replace computed sunrise/sunset with official CWA data. Add moon for night surf.

### Pipeline Changes

**10a. Fetch A-B0062-001 (sunrise/sunset)**
- Query: `CountyName=基隆市,新北市,宜蘭縣`, `Date=today+7d`
- Get: `SunRiseTime`, `SunSetTime`, `BeginCivilTwilightTime`, `EndCivilTwilightTime`
- More accurate than our simplified solar calculation in config.py

**10b. Fetch A-B0063-001 (moonrise/moonset)**
- Same query params
- Get: `MoonRiseTime`, `MoonSetTime`

### Frontend Changes

**10c. Dawn patrol time in spot detail**
- "First light: 05:23 CST" (civil twilight)
- "Sunrise: 05:48 CST"
- Show in best-time-to-surf section

**10d. Moon phase indicator**
- Small icon showing current moon phase
- Correlates with tidal range (spring/neap)

**Effort:** 3-4h | **Impact:** Low-Medium

---

## Phase 11: 30-Day History for Accuracy

**Goal:** Use CWA 30-day observation data for better forecast verification.

### Pipeline Changes

**11a. Use O-B0075-002 for wave accuracy**
- Fetch 24h of buoy wave obs around verification time
- Compare vs wave forecast for each spot's nearest buoy
- More accurate than Open-Meteo for local wave verification

**11b. Use C-B0024-001 for weather accuracy**
- 30-day station obs with daily statistics (max/min/mean)
- Better than hourly O-A0001-001 for multi-day bias analysis

**11c. Use O-A0002-001 for precipitation accuracy**
- `Past6hr` rainfall directly comparable to `precip_mm_6h` forecast
- More reliable than model-reanalysis obs

### Frontend Changes

**11d. Accuracy trends chart** (stretch goal)
- Show 30-day rolling accuracy for temp, wind, waves
- "Model getting better/worse over time"

**Effort:** 4-6h | **Impact:** Medium — improves AI summary calibration

---

## Phase 12: Monthly Climate Context for AI Summary

**Goal:** Give Claude seasonal context for smarter narrative.

### Pipeline Changes

**12a. Fetch C-B0027-001 monthly averages**
- For Keelung station (466940): monthly mean temp, wind, precip
- Pass to `forecast_summary.py` as context

**12b. Enhance AI prompt**
- "April average: temp 21°C, wind 8kt, precip 150mm"
- "Today's forecast: temp 25°C (above normal), wind 18kt (above normal)"
- Claude uses this to write: "Expect an unusually warm and windy day for early April"

**Effort:** 2-3h | **Impact:** Medium — smarter AI narrative

---

## Implementation Priority

| Phase | Name | Effort | Impact | Dependencies |
|-------|------|--------|--------|-------------|
| 1 | Per-spot tide obs + storm surge | 6-8h | **High** | None |
| 2 | Water temperature display | 2-3h | **High** | Phase 1 data |
| 3 | Visibility for sailors | 3-4h | **High** (sailors) | None |
| 4 | UV index | 3-4h | **Medium** | None |
| 5 | Ensemble confidence + accuracy | 4-6h | **Medium** | None |
| 6 | Batch/optimize API calls | 3-4h | **Medium** | None |
| 7 | 1-week extended forecast | 4-6h | **Medium** | Phase 6 |
| 8 | Sea currents | 3-4h | **Medium** | None |
| 9 | Enhanced warnings | 4-6h | **Medium** | None |
| 10 | Sunrise/sunset + moon | 3-4h | **Low-Med** | None |
| 11 | 30-day history accuracy | 4-6h | **Medium** | None |
| 12 | Monthly climate context | 2-3h | **Medium** | None |

**Recommended order:** 1 → 2 → 3 → 6 → 4 → 5 → 9 → 7 → 8 → 12 → 11 → 10

**Total estimated effort:** ~45-60 hours across all phases
