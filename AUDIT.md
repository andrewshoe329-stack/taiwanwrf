# Taiwan WRF Forecast — Full Program Audit

**Date:** 2026-03-22
**Scope:** Architecture, code quality, bugs, UI/UX, and feature proposals
**Codebase:** ~4,300 lines Python across 7 modules + 113 unit tests

---

## 1. Architecture Assessment

### Strengths

- **Clean pipeline architecture.** Each script is a standalone CLI tool with its own `main()`, composable via GitHub Actions. This makes local development, testing, and debugging straightforward.
- **Graceful degradation.** AI summary skips if no API key; subsetting falls back from eccodes → cfgrib → no-op; CWA wave is optional. The system never hard-fails on optional features.
- **Shared config.** `config.py` centralizes coordinates and logging. All scripts import from it.
- **Stale-run detection.** The workflow compares `init_utc` against the previous run and short-circuits, avoiding duplicate emails and redundant uploads.
- **Good test coverage for pure functions.** Compass conversion, Beaufort scale, color functions, scoring logic — all well tested.

### Weaknesses

- **No integration tests.** The 113 tests are all unit tests for pure functions. There are no tests that exercise the actual GRIB2 reading, API fetching, or HTML generation end-to-end with fixture data.
- **Monolithic HTML generation.** `wrf_analyze.py` (1,267 lines) and `surf_forecast.py` (807 lines) mix data processing with string-concatenated HTML. This is hard to maintain and impossible to unit-test the HTML output structurally.
- **No shared HTTP client.** Three separate retry-capable HTTP fetch functions exist (`taiwan_wrf_download.download_file`, `ecmwf_fetch._fetch_json`, `wave_fetch.fetch_ecmwf_wave`, `surf_forecast._get`). Each has slightly different retry/backoff logic.
- **No data validation layer.** JSON inputs from APIs are consumed directly with `.get()` calls and no schema validation. A malformed API response would silently produce `None` values rather than failing fast.
- **Tight coupling to GitHub Actions.** Several scripts write to `GITHUB_OUTPUT` directly. There is no abstraction for CI vs local execution.

---

## 2. Bugs & Correctness Issues

### BUG-1: Precipitation accumulation first-step handling (wrf_analyze.py:336-343)

```python
if rec.get('precip_mm') is not None and prev_precip_mm is not None:
    if rec['precip_mm'] >= prev_precip_mm:
        rec['precip_mm_6h'] = round(rec['precip_mm'] - prev_precip_mm, 2)
    else:
        rec['precip_mm_6h'] = rec['precip_mm']  # reset — treat as-is
else:
    rec['precip_mm_6h'] = rec.get('precip_mm')  # first step
```

**Problem:** At forecast hour 0 (analysis), `prev_precip_mm` is `None`, so the first record gets `precip_mm_6h = precip_mm` (the raw accumulated value, which is 0 for the analysis hour — usually fine). But if the model starts with a non-zero accumulated precip at F000 (possible with some GRIB2 encodings), this value would be treated as 6h rainfall, which is incorrect.

**Fix:** Explicitly set `precip_mm_6h = 0` for F000 or when `fh == 0`.

### BUG-2: ECMWF init time derived from first hourly timestamp (ecmwf_fetch.py:221)

```python
init_raw = raw.get("hourly", {}).get("time", [""])[0]
```

**Problem:** Open-Meteo's first hourly timestamp is T00:00 of the current day, *not* the model init time. ECMWF IFS initializes at 00Z or 12Z. The reported `init_utc` in the output JSON is therefore always midnight, which is misleading when the actual model run was 12Z.

**Fix:** Use Open-Meteo's `current.time` or `generationtime_ms` fields, or simply don't claim a specific init time. Consider adding `&current=true` to the API request to get actual model run info.

### BUG-3: Precipitation sum edge case in ecmwf_fetch.py:190-193

```python
precip_6h = sum(
    (safe(precip, j) or 0.0)
    for j in range(max(0, i - 5), i + 1)
)
```

**Problem:** For the first 6h window (i=0 to i=5), when `i < 5`, the window is shorter than 6 hours. At i=0 (00:00 UTC), only 1 hourly value is summed. This under-reports the first period. The same issue exists in `surf_forecast.py:193-196`.

**Severity:** Low — the first record at 00:00 always has a partial window, but users see the 06:00 record onward.

### BUG-4: `_norm_utc` duplication

`_norm_utc()` is defined identically in both `ecmwf_fetch.py:117` and `wave_fetch.py:134`. This is a DRY violation and a source of future drift bugs.

**Fix:** Move to `config.py`.

### BUG-5: `surf_forecast.py` rain sum can include `None` values (line 193-196)

```python
rain6h = sum(
    (eh.get('precipitation', [0]) + [0] * 10)[k]
    for k in range(max(0, i - 5), i + 1)
)
```

**Problem:** `eh.get('precipitation', [0])` returns the precipitation array or `[0]`. If the array contains `None` values (which Open-Meteo can return), `sum()` will raise `TypeError`. The `+ [0] * 10` padding is also fragile — it assumes the array isn't too short.

**Fix:** Use `(val or 0)` for each element, matching `ecmwf_fetch.py`'s approach.

### BUG-6: Hardcoded Keelung coordinates in surf_forecast.py:226

```python
KEELUNG = {'lat': 25.128, 'lon': 121.740, 'name': 'Keelung'}
```

These are different from `config.py`'s `KEELUNG_LAT = 25.15589` / `KEELUNG_LON = 121.78782`. The planner's sailing data is fetched for a point ~7 km from the actual Keelung harbour target used everywhere else.

**Fix:** Import from `config.py`.

### BUG-7: `WKDAY` mapping wrong in surf_forecast.py:229

```python
WKDAY = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat']
```

Python's `datetime.weekday()` returns 0=Monday, but this array has 0=Sunday. Every day label in the surf forecast is wrong by one day.

**Fix:** Either use `['Mon','Tue','Wed','Thu','Fri','Sat','Sun']` or switch to `strftime('%a')`.

---

## 3. Code Quality Issues

### CQ-1: Giant HTML string concatenation

`render_unified_html()` in `wrf_analyze.py` is ~340 lines of HTML string building with inline styles. `generate_full_html()` in `surf_forecast.py` is similar. This approach:
- Cannot be tested structurally (e.g., "does the table have N rows?")
- Has no XSS protection (though inputs are numeric)
- Is extremely hard to modify visually

**Recommendation:** Extract HTML generation into a minimal template system (even Python's `string.Template` would be an improvement), or generate from a dict/list structure that can be tested.

### CQ-2: Unpinned dependencies (requirements.txt)

```
eccodes
numpy
anthropic
```

No version pins. A breaking change in any dependency will silently break the workflow. The eccodes Python package has had breaking API changes between versions.

**Fix:** Pin major versions: `eccodes>=1.5,<2`, `numpy>=1.24,<3`, `anthropic>=0.40,<1`.

### CQ-3: No type hints on many functions

Functions like `process_spot()`, `_get()`, `day_rating()` lack return type annotations. Given the codebase complexity, adding `-> dict`, `-> str`, etc. would improve maintainability.

### CQ-4: Duplicated compass/direction code

`COMPASS`, `_WAVE_COMPASS`, `DIR_NAMES`, and compass conversion functions are defined in 3 separate files with identical logic. Should be in `config.py`.

### CQ-5: `wrf_analyze.py` `needed_raw_keys` dict rebuilt on every iteration (line 316-326)

This dictionary is constant but defined inside a loop over every forecast record's derived fields. It should be a module-level constant.

### CQ-6: Shell injection risk in GitHub Actions workflow (main.yml:40)

```yaml
ARCHIVE=$(find wrf_downloads/ -name "*.tar.gz" | sort | tail -1)
```

If a filename contained special characters, this could break. The Python script already writes to `GITHUB_OUTPUT`, so the shell fallback is unnecessary.

---

## 4. UI/UX Assessment

### Strengths

- **Dark theme is well-executed.** The color palette (#0f172a base with #93c5fd accents) is easy on the eyes and appropriate for the maritime audience.
- **Color coding is intuitive.** Beaufort-scale color progression from green → yellow → orange → red maps directly to sailing safety.
- **Daily summary cards are excellent.** The compact card format with emoji condition icons provides at-a-glance actionability.
- **Wind arrows** showing direction-blowing-toward is the correct convention for sailors.
- **Print media queries** in the surf forecast CSS show attention to real-world usage.

### Weaknesses

#### UX-1: No mobile-optimized viewport on the Vercel site

The `public/index.html` built in the workflow has `<meta name="viewport">` but the main content tables have no responsive breakpoints. On a phone:
- The unified forecast table requires horizontal scrolling with 12+ columns
- Column labels truncate or overlap
- Daily summary cards wrap correctly, but the table does not

**Recommendation:** Add a responsive mode that collapses the table into stacked cards on narrow viewports, or reduce columns on mobile.

#### UX-2: No timezone toggle

All times are shown in both UTC and CST+8, which is good. But there's no way for the user to hide one or the other, adding visual clutter.

#### UX-3: The Vercel site has no navigation or timestamp

The deployed page is a raw HTML dump. There's no header showing when it was last updated, no footer, no way to tell if you're looking at stale data.

**Fix:** Add a visible "Last updated: {timestamp}" banner and auto-refresh meta tag.

#### UX-4: No loading/error states

If the workflow fails mid-run, the Vercel site shows whatever was last deployed with no indication it's stale. Users have no way to know the data is outdated.

**Fix:** Add a visible timestamp and a "data age" indicator (e.g., turns yellow after 12h, red after 24h).

#### UX-5: Email HTML relies on `<style>` blocks

`surf_forecast.py`'s full HTML uses `<style>` blocks with class names. Many email clients (notably Gmail) strip `<style>` blocks entirely. The "email" version (`generate_html()`) correctly uses inline styles, but the full version doesn't — and both get appended to `email_analysis.html`.

#### UX-6: Accessibility

- Tables lack `<caption>` elements (except the surf matrix)
- No skip-navigation links for screen readers
- Color alone distinguishes conditions (no patterns or text alternatives for colorblind users)
- Emoji are used for meaning without `aria-label` in many places

---

## 5. Performance & Reliability

### P-1: Sequential API calls in surf_forecast.py

Each of the 7 surf spots makes 3 API calls (ECMWF, GFS, Marine) sequentially = 21 HTTP requests in series. With 5s retry delays, this can take 2+ minutes.

**Fix:** Use `concurrent.futures.ThreadPoolExecutor` to fetch spots in parallel (like `taiwan_wrf_download.py` already does for GRIB files).

### P-2: No caching of Open-Meteo responses

The ECMWF IFS data for Keelung is fetched once by `ecmwf_fetch.py` and again by `surf_forecast.py` (for the Keelung sailing record). Two identical API calls.

**Fix:** Pass the already-fetched JSON into `surf_forecast.py` via CLI argument, or cache responses locally.

### P-3: GRIB2 grid cache key is too broad (wrf_analyze.py)

`cache_key = (ni, nj)` assumes all grids with the same dimensions share the same geometry. If two different GRIB messages had different projections with the same ni/nj, the wrong grid point would be used. Unlikely for CWA data, but a latent bug.

**Fix:** Include `grid_type` or `latitudeOfFirstGridPoint` in the cache key.

### P-4: No workflow concurrency limit

If two workflow runs trigger simultaneously (e.g., manual + scheduled), they could race on Google Drive uploads, corrupting the summary JSON.

**Fix:** Add `concurrency: group: wrf-pipeline, cancel-in-progress: true` to the workflow.

---

## 6. Security

- **No hardcoded secrets.** All credentials are in GitHub Secrets.
- **No user input to HTML.** All rendered values are numeric from APIs or GRIB2 data. XSS risk is negligible.
- **S3 bucket is public read-only.** No write exposure.
- **`forecast_summary.py` properly escapes AI output** via `html.escape()` before injection into HTML. Good.
- **Vercel token in CI** is appropriately scoped to deployment only.

**One concern:** The `rclone.conf` secret is written to disk during the workflow (`~/.config/rclone/rclone.conf`). If a subsequent step logged the filesystem or uploaded artifacts, it could leak. Consider using environment variables instead.

---

## 7. Proposed New Features

### Feature 1: Tide Integration

**Priority: High** — Sailing and surfing are both heavily tide-dependent.

Integrate tide data from the CWA tide API or a free source like WorldTides. Show:
- High/low tide times in the daily summary cards
- Tide state (rising/falling/slack) in the hourly forecast table
- Tide-aware surf ratings (many spots listed have "mid tide" in their descriptions)

### Feature 2: Progressive Web App (PWA)

**Priority: High** — The primary audience checks forecasts on phones.

Convert the Vercel deployment into a PWA:
- Add `manifest.json` with app name, icons, theme color
- Add a service worker for offline caching (show last-fetched data when offline)
- Enable "Add to Home Screen" for iOS/Android
- Auto-refresh data when the app is foregrounded

### Feature 3: Historical Accuracy Tracking

**Priority: Medium** — Builds trust and improves the system over time.

- After each run, fetch actual weather observations from CWA for the previous 24h
- Compare WRF forecast vs actual (wind speed, temperature, rain)
- Store accuracy metrics over time
- Display a "Model accuracy" badge: "WRF was within 3kt of actual wind 85% of the time this week"

### Feature 4: Multi-location Support

**Priority: Medium** — Expand beyond Keelung.

- Make the target location configurable (not hardcoded to Keelung)
- Allow multiple "profiles" (Keelung sailing, Penghu windsurfing, Taitung surfing)
- Each profile generates its own page/email
- Foundation is already there — `config.py` coordinates just need to become a list

### Feature 5: Wind Map / Spatial View

**Priority: Medium** — Visual spatial context is valuable for route planning.

- Instead of just the Keelung point, render a small wind barb map from the WRF subset grid
- Show 50nm-radius wind field at a glance
- Overlay wave direction arrows on a simple coastline outline
- Could be a static SVG or canvas-rendered map

### Feature 6: Push Notifications / Alerts

**Priority: Medium** — Proactive is better than checking.

- When conditions cross thresholds (gale warning, perfect surf), send push notifications
- Options: Web Push API (via PWA), LINE messaging (popular in Taiwan), or Telegram bot
- Configurable per-user alert thresholds
- "Send me a notification when swell > 1m at Fulong with offshore wind"

### Feature 7: Spot Webcam Integration

**Priority: Low** — Real-time visual validation of forecast.

- Embed or link to surf webcams for each spot (several have public cameras)
- Show latest webcam thumbnail alongside the forecast
- "Conditions now" vs "Forecast" side-by-side

### Feature 8: Multi-model Ensemble Display

**Priority: Low** — More models = better confidence assessment.

- Add GFS and ICON model forecasts alongside WRF and ECMWF
- Show a "model spread" indicator for each timestep
- When models agree, confidence is high; when they diverge, flag uncertainty
- Open-Meteo supports GFS, ICON, JMA — all free

### Feature 9: Route Weather for Sailing

**Priority: Low** — Differentiated feature for sailors.

- Allow input of a sailing route (waypoints)
- Interpolate WRF grid along the route
- Show wind/wave conditions at each waypoint/time
- "Keelung → Green Island 10h passage — weather window analysis"

---

## 8. Summary of Priority Actions

| # | Category | Issue | Effort | Impact |
|---|----------|-------|--------|--------|
| 1 | Bug | BUG-7: Weekday mapping off-by-one in surf forecast | 5 min | High — every day label is wrong |
| 2 | Bug | BUG-6: Hardcoded Keelung coords differ from config | 5 min | Medium — 7km offset for sailing data |
| 3 | Bug | BUG-2: ECMWF init time is wrong | 15 min | Medium — misleading metadata |
| 4 | Bug | BUG-5: Rain sum TypeError on None values | 10 min | Medium — potential crash |
| 5 | Quality | CQ-2: Pin dependency versions | 5 min | High — prevents silent breakage |
| 6 | Quality | CQ-4/BUG-4: Deduplicate compass/norm_utc code | 30 min | Medium — reduces maintenance |
| 7 | Perf | P-1: Parallelize surf spot API calls | 30 min | Medium — cuts runtime by 3-4x |
| 8 | Perf | P-4: Add workflow concurrency limit | 5 min | Medium — prevents race conditions |
| 9 | UX | UX-3: Add timestamp to Vercel site | 15 min | High — users can't tell if data is stale |
| 10 | UX | UX-1: Mobile-responsive tables | 2-4 hrs | High — primary audience is mobile |
| 11 | Feature | Tide integration | 1-2 days | High — critical missing data |
| 12 | Feature | PWA conversion | 1-2 days | High — enables offline + home screen |
