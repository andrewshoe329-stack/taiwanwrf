# Code Audit Report — Taiwan WRF Forecast Pipeline

**Date:** 2026-03-22
**Scope:** Full codebase audit covering all Python scripts, tests, CI/CD, and PWA files.

---

## Critical Bugs

### 1. `tide_predict.py:48` — Wrong J2000.0 epoch
The J2000.0 epoch is defined as `datetime(2000, 1, 12, 0, 0, 0)` (January 12 at midnight) but the correct value is **January 1 at noon** (`2000-01-01T12:00:00`). This is a 10.5-day offset that shifts all tide predictions. The harmonic constants may have been calibrated against this wrong epoch (masking the error in practice), but the phases are non-standard and non-portable.

### 2. `wrf_analyze.py:802-803` — `total_rain` uses logical `or` instead of conditional
```python
total_rain = (sum(r.get('precip_mm_6h') or 0 for r in _wrf)
              or sum(r.get('precip_mm_6h') or 0 for r in _ec))
```
If WRF predicts exactly 0mm rain (falsy), Python falls through to the ECMWF sum. A dry WRF forecast with 50mm ECMWF rain would trigger false rain warnings. Fix: `sum(... for r in (_wrf if _wrf else _ec))`.

### 3. `wrf_analyze.py:522+` — `_condition_emoji` receives `None` for typed `float` params
The function signature declares `max_wind: float` etc., but callers pass `None` when no data exists. Comparisons like `max_wind >= 25` raise `TypeError` in Python 3 when `max_wind is None`.

### 4. `config.py:42-47` — `norm_utc()` doesn't handle `Z` suffix
Timestamps like `2026-03-22T06:00:00Z` (length 20) fall through unmodified. These won't match `+00:00`-suffixed timestamps in downstream string comparisons, silently breaking time-based joins in `wrf_analyze.py`. Additionally, `datetime.fromisoformat()` doesn't parse `Z` on Python < 3.11.

### 5. `wrf_analyze.py:261-263` — Precipitation unit heuristic can misfire
```python
if 0 < val < 0.5:
    val *= 1000.0
```
Legitimate sub-0.5mm precipitation (light drizzle) would be multiplied to 500mm when the GRIB2 `units` key is missing.

---

## High-Severity Issues

### 6. `wrf_analyze.py:137` — `nearest_idx` uses Euclidean distance on lat/lon
At 25°N, 1° longitude ≈ 100km but 1° latitude ≈ 111km. The distance calculation is biased, potentially selecting the wrong grid point. Fix: weight longitude by `cos(lat)`.

### 7. `ecmwf_fetch.py:73` — `_fetch_json` only catches `URLError`, not `JSONDecodeError`
If the server returns 200 OK with invalid JSON (HTML error page), the function crashes instead of retrying. Same issue in `wave_fetch.py:117`.

### 8. `ecmwf_fetch.py:214-221` — ECMWF init time detection uses observation time
The `current_weather.time` field is the current observation time, not the model initialization time. This produces wrong `init_utc` metadata.

### 9. `surf_forecast.py:800-803` — ThreadPoolExecutor has no exception handling
If any single spot fetch fails, `future.result()` raises an unhandled exception that crashes the entire pipeline. Should catch per-spot failures.

### 10. `.github/workflows/main.yml:34` — `pip install` ignores `requirements.txt` pinning
`pip install --quiet eccodes numpy anthropic` installs latest versions, not the pinned ranges from `requirements.txt`. Could break with numpy 2.x API changes.

### 11. `.github/workflows/main.yml:246-248` — `rclone copy` vs `rclone copyto`
`rclone copy src.json gdrive:path/dest.json` treats the destination as a directory, creating `dest.json/src.json`. Should use `rclone copyto` for single-file rename-and-copy.

---

## Medium-Severity Issues

### 12. `wrf_analyze.py:936` — Column count off by 2
`_total_cols = 3 + 2 + _n_wave_cols + 6 + 1` overcounts columns, causing day-separator `colspan` to be too wide. Browsers tolerate this but it's incorrect.

### 13. `wrf_analyze.py:185` — Grid cache is per-call, not shared
`read_point()` creates a local `grid_cache` dict on each invocation. All 15 Keelung subset files share the same grid, so the expensive lat/lon computation is repeated unnecessarily. A module-level cache would save significant work.

### 14. `ecmwf_fetch.py:243` — GFS fetch runs unconditionally
The GFS backfill fetch happens even when ECMWF data is complete, adding unnecessary latency and API calls.

### 15. `forecast_summary.py:146-148` — Overly broad exception catch on API calls
`except Exception` catches `AuthenticationError` and `PermissionDeniedError` which should not be retried. Only transient errors (rate limits, timeouts) should trigger retry.

### 16. `forecast_summary.py:145` — No bounds check on `msg.content`
`msg.content[0].text.strip()` assumes at least one content block. An empty response (content filter) would raise `IndexError`, caught by the broad except and wasted across all 3 retries.

### 17. `accuracy_track.py:46` — Deprecated API parameter name
Uses `'windspeed_10m'` which Open-Meteo renamed to `'wind_speed_10m'`. May break without warning.

### 18. `accuracy_track.py:207-209` — Corrupted accuracy log silently discarded
`except Exception: pass` when loading the existing log means a corrupted JSON file is silently overwritten, losing all historical data.

### 19. `.github/workflows/main.yml:85` — Shell injection via unquoted step outputs
`NEW_INIT="${{ steps.download.outputs.init_utc }}"` — if the Python script writes a malformed value, this could inject shell commands. Unquoted `${{ }}` in shell `run:` blocks is a known GitHub Actions anti-pattern.

### 20. `.github/workflows/main.yml:373` — Vercel token on command line
`vercel deploy --prod --token=${{ secrets.VERCEL_TOKEN }}` exposes the token in the process list. Vercel CLI reads `VERCEL_TOKEN` from environment automatically.

### 21. `tide_predict.py:79` — Extrema detection misses plateaus
The condition `curr_h >= prev_h and curr_h >= next_h and curr_h != prev_h` has an asymmetry: rise-then-flat is not detected as a high, but flat-then-drop is.

### 22. `surf_forecast.py:213` — Timezone double-set
`datetime.fromisoformat(t.replace('Z', '+00:00')).replace(tzinfo=timezone.utc)` — if the string already has `+00:00`, `.replace(tzinfo=...)` silently overwrites. A non-UTC offset would be discarded without error.

---

## Low-Severity / Code Quality Issues

### 23. No HTML escaping anywhere
All scripts generating HTML use f-strings without escaping. Data comes from APIs (generally numeric) but model metadata or error messages could contain `<`, `>`, `&` — an XSS vector since the output is served via Vercel.

### 24. `wrf_analyze.py:94` — Wind direction for calm winds
`atan2(0, 0)` returns 0 → direction 270° for zero wind. Should return `None` or be suppressed for calm conditions.

### 25. `wrf_analyze.py:97-98` — Cloud cover double-conversion edge case
1% cloud cover (as percentage from GRIB2) would be multiplied by 100 since `1.0 <= 1.01`.

### 26. `taiwan_wrf_download.py:339-341` — cfgrib fallback latitude slice may return empty data
Ascending latitude slice on descending-ordered GRIB2 data returns an empty dataset.

### 27. Duplicated utility functions across modules
`deg_to_compass` and `norm_utc` are duplicated as private functions in `wave_fetch.py`, `surf_forecast.py`, and `wrf_analyze.py` despite being defined in `config.py`. CLAUDE.md warns against this. Tests validate the duplicates rather than the canonical versions.

### 28. `wave_fetch.py:159-160` — Helper function `r2` redefined every loop iteration
Should be defined once outside the loop.

### 29. `tide_predict.py:182-183` — Hardcoded coordinates differ from `config.py`
Output uses `25.156, 121.788` (rounded) instead of importing from `config.py`.

### 30. `tide_predict.py:134` — Truncation instead of rounding
`best_t.replace(second=0, microsecond=0)` truncates, introducing up to 59 seconds of error.

### 31. `.github/workflows/main.yml:24-26` — Cache key missing `requirements.txt` hash
Fixed key `pip-eccodes-numpy-${{ runner.os }}` never updates when dependencies change.

### 32. No `permissions:` block in workflow
Uses default token permissions. Should set `permissions: contents: read` for least-privilege.

### 33. No `timeout-minutes` on download step
If S3 hangs, the job runs for the GitHub Actions default (6 hours).

---

## PWA Issues

### 34. Service worker only caches the root page, not assets
Icons, manifest, and other static assets are not pre-cached. Offline experience will have broken assets.

### 35. Cache version `tw-forecast-v1` is never incremented
Users may get stale cached content. The activate handler's old-cache cleanup never triggers.

### 36. `manifest.json` uses deprecated `"purpose": "any maskable"`
Combined purpose values are deprecated per W3C spec. Should use separate icon entries.

### 37. Generated PWA icons are solid-color rectangles with no visible symbol
Indistinguishable from a broken icon on home screens.

### 38. `orientation: portrait-primary` fights the wide data tables
Locking to portrait makes the already non-responsive forecast tables harder to read on tablets.

---

## Test Coverage Gaps

### 39. No tests for `_condition_emoji` return values
`TestConditionEmoji` only checks the return is a non-empty string, not that the correct emoji is returned.

### 40. No edge-case tests for `day_rating` scoring
Missing: boundary swell values at `MIN_SWELL_HEIGHT_M`/`MAX_SWELL_HEIGHT_M`, `None` fields, mixed conditions.

### 41. No tests for HTML generation functions
Neither `render_unified_html()` nor `generate_full_html()` have structural tests.

### 42. Fragile `_sail_rating` test
`assert 'No-go' in label or 'No go' in label` — should match the implementation precisely.

### 43. Inconsistent `sys.path` manipulation in tests
`test_config.py` doesn't use `sys.path.insert` while all others do. A `conftest.py` would be cleaner.

---

## Recommended Priority

1. **Fix critical bugs** (#1-5) — wrong tide epoch, rain logic, None type errors, Z suffix
2. **Fix high-severity issues** (#6-11) — grid distance, error handling, CI pinning, rclone
3. **Deduplicate utilities** (#27) — remove private copies of `deg_to_compass`/`norm_utc`
4. **Add HTML escaping** (#23) — prevent XSS on Vercel-served pages
5. **Improve error handling** (#7, #9, #15, #18) — catch correct exceptions, handle thread failures
6. **Fix CI/CD** (#10, #11, #19, #20, #31, #32, #33) — pinning, rclone, security
7. **Expand test coverage** (#39-43) — emoji, edge cases, HTML output
8. **PWA improvements** (#34-38) — proper caching, icons, orientation
