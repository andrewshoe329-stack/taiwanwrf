# Code Audit Report — Taiwan WRF Forecast Pipeline

**Date:** 2026-03-27
**Scope:** Full codebase audit covering all Python modules, CI/CD workflows, PWA assets, tests, and configuration.

---

## Executive Summary

The codebase is well-structured with good separation of concerns and thorough documentation in CLAUDE.md. However, the audit identified **7 high-severity issues**, **18 medium-severity issues**, and numerous low-severity items across security, correctness, and reliability dimensions.

The most critical findings are:
1. **Accuracy feedback loop is compromised** -- precipitation and wave accuracy metrics are computed incorrectly, feeding bad data to the AI summary
2. **Credential leak in error logs** -- Telegram bot token embedded in URLs appears in exception tracebacks
3. **Silent data corruption** -- falsy-value bugs (`0.0` treated as missing) and a precipitation heuristic that can multiply values by 1000x
4. **Documentation drift** -- CLAUDE.md references a `main.yml` workflow that doesn't exist; actual architecture is 3 separate workflows

---

## High Severity

### H1. Precipitation accuracy comparison is apples-to-oranges
**File:** `accuracy_track.py:264`
The code compares a 6-hour accumulated forecast value against a single 1-hour observation. This systematically inflates precipitation MAE and positive bias. These corrupted metrics are fed to the AI summary via `forecast_summary.py`, causing Claude to adjust its language based on false bias data -- undermining the entire accuracy feedback loop.

### H2. Wave accuracy field name mismatch
**File:** `accuracy_track.py:352-362`
`_compute_wave_accuracy()` looks for short keys (`hs`, `tp`, `dir`) but `wave_keelung.json` uses long keys (`wave_height`, `wave_period`, `wave_direction`). Wave accuracy silently produces no results. The `_compute_buoy_verification` function handles both formats, but `_compute_wave_accuracy` does not, so wave MAE/bias metrics are never computed.

### H3. Falsy `0.0` values silently replaced by ECMWF fallback
**File:** `wrf_analyze.py:1891-1895, 1698-1710`
Pattern: `wind = (wrf.get('wind_kt') if wrf else None) or (ec.get('wind_kt') if ec else None)`
Python's `or` treats `0.0` as falsy. When WRF reports calm wind (0.0 kt), zero temperature, or zero precipitation, the value is silently discarded and replaced by the ECMWF fallback. This is a real data correctness bug affecting calm-weather scenarios.

### H4. Precipitation heuristic can multiply mm values by 1000
**File:** `wrf_analyze.py:296-299`
When the GRIB2 `units` key is missing, a heuristic triggers: `if 0 < val < 0.5: val *= 1000.0`. This assumes the value is in metres and converts to mm. But light rain that is genuinely 0.3 mm (already in mm) gets multiplied to 300 mm -- a catastrophically wrong value. The code logs a warning but applies the conversion anyway.

### H5. Telegram bot token leaked in error logs
**File:** `notify.py:297-299, 313`
The bot token is embedded in the URL path (`https://api.telegram.org/bot{token}/sendMessage`). When an `HTTPError` occurs, line 313 logs the exception which includes the full URL with the embedded token. This is a credential leak in any log aggregation system.

### H6. Daylight window calculation broken for Taiwan's UTC offset
**File:** `surf_forecast.py:551-557`
Sunrise/sunset for Taiwan in UTC wraps past midnight (sunrise ~21:30 UTC previous day, sunset ~10:00 UTC). The linear overlap math (`max(start, sunrise)` to `min(end, sunset)`) produces zero or negative values when the window crosses midnight UTC. The "best time to surf" daylight filter likely falls back to scoring all windows, negating the feature.

### H7. CLAUDE.md references non-existent workflow
**File:** `CLAUDE.md` vs `.github/workflows/`
CLAUDE.md documents a single `.github/workflows/main.yml` with a 4x daily schedule. The actual codebase has three separate workflows: `wrf.yml` (1x daily), `forecast.yml` (2x daily), `deploy.yml` (triggered). This documentation drift means developers working from CLAUDE.md will have incorrect mental models of the pipeline.

---

## Medium Severity

### M1. XSS via `bilingual()` -- html.escape imported but never used
**File:** `i18n.py:343-345, 11`
`bilingual(en, zh)` interpolates parameters directly into HTML without escaping. `html.escape` is imported as `_esc` on line 11 but never used anywhere. If any caller passes externally-sourced strings (CWA station names, spot names from API), this is a stored XSS vector.

### M2. Unescaped HTML in Telegram messages
**File:** `notify.py:300-304, 228`
Messages are sent with `parse_mode: 'HTML'` but `format_notification()` does not HTML-escape alert content. CWA warning descriptions from an external API (line 228) could contain HTML metacharacters, breaking messages or enabling content injection.

### M3. `T()` / `T_str()` crash on missing keys
**File:** `i18n.py:328-340`
Missing keys raise unhandled `KeyError`, which would crash HTML generation mid-render and deploy a broken partial HTML file to Vercel. No compile-time checks exist on string keys.

### M4. Grid cache ignores target coordinates
**File:** `wrf_analyze.py:177`
Module-level `_grid_cache` keys on `(grid_type, ni, nj)` but not on `(lat, lon)`. If `read_point()` is ever called for a different location in the same process, it silently returns the grid point nearest to the first location queried. Currently safe (only Keelung used) but a latent correctness bug.

### M5. Precip accumulation breaks on missing intermediate files
**File:** `wrf_analyze.py:369-382`
`prev_precip_mm` tracking assumes files are processed in consecutive forecast-hour order. If a file is missing (e.g., F012 absent), the delta for F018 spans 12 hours instead of 6, doubling the reported precipitation for that timestep.

### M6. Cloud cover fraction-vs-percent ambiguity at boundary
**File:** `wrf_analyze.py:103-104`
`cloud_raw * 100 if cloud_raw <= 1.0 else cloud_raw` -- a value of exactly 1.0 is ambiguous (100% as fraction, or 1% as percentage). Values like 1.5 (rounding artifact) are passed through as 1.5% instead of 150%.

### M7. Local `fetch_json()` shadows shared config utility
**File:** `taiwan_wrf_download.py:123-125`
Defines its own `fetch_json()` with no retry logic, contradicting the convention that all modules use `config.fetch_json()` with centralized retries. S3 metadata fetches fail on transient errors without retry.

### M8. cfgrib latitude slice direction may be wrong
**File:** `taiwan_wrf_download.py:339-344`
`ds.sel(latitude=slice(lat_lo, lat_hi))` assumes ascending latitude order. If the coordinate is descending (common in meteorological data), the selection returns empty data.

### M9. `norm_utc()` silently passes non-UTC offsets
**File:** `config.py:306-324`
A timestamp with `+08:00` (CST) passes through unchanged without conversion or warning. The docstring says "assumes input is already in UTC" but does not validate this. Any caller mistakenly passing CST gets silently wrong results.

### M10. CWA operator precedence bug in tide observation filter
**File:** `cwa_fetch.py:431-437`
Python `and` binds tighter than `or`, so the `valid_obs` filter allows any observation with `TideHeight != "None"` through regardless of whether it is a dict or has a DateTime.

### M11. Inconsistent cm-to-m conversion in tide forecast
**File:** `cwa_fetch.py:712-735`
Nested `TideHeights` values are divided by 100 (cm to m), but fallback top-level values are used raw. If the fallback receives cm values, heights are 100x too large.

### M12. CWA API returns data even on failure responses
**File:** `cwa_fetch.py:100-107`
`_cwa_get` returns data when the API indicates failure. A warning is logged but callers still receive potentially invalid data.

### M13. Firestore 1 MiB document size limit
**File:** `firebase_storage.py:136`
The entire accuracy log (120+ entries with CWA snapshots) is stored in a single Firestore document. With 4 runs/day for 30 days plus embedded observation data, this will eventually exceed the 1 MiB limit.

### M14. No output file created when Firestore document missing
**File:** `firebase_storage.py:240-243`
When there is no previous summary in Firestore, no file is created. Downstream pipeline steps expecting the file get `FileNotFoundError` instead of a clean signal.

### M15. Accessing private `firebase_admin._apps`
**File:** `firebase_storage.py:66`
`firebase_admin._apps` is a private implementation detail. Could break on library updates.

### M16. Script injection risk in GitHub Actions
**File:** `wrf.yml:81, 101, 129, 156, 158`
Step outputs from `taiwan_wrf_download.py` are interpolated directly into shell commands via `${{ }}` syntax. Should use `env:` blocks to prevent injection.

### M17. `continue-on-error: true` overused in CI
**File:** `forecast.yml` (9 steps)
Pipeline always reports "success" even if most data fetches fail. A run where ECMWF, wave, ensemble, CWA, AI summary, and accuracy tracking all fail still triggers a deploy to Vercel.

### M18. Service worker precache is all-or-nothing
**File:** `pwa/sw.js:25-29`
`cache.addAll(PRECACHE_URLS)` fails entirely if any of the 17 URLs returns 404 during deploy, blocking all service worker updates.

---

## Low Severity

### L1. Unused imports
- `config.py:240` -- `_dt`, `_tz` imported inside `sunrise_sunset()` but never used
- `i18n.py:11` -- `html.escape` imported as `_esc` but never used
- `surf_forecast.py:16` -- `html_mod_escape` imported but never used
- `cwa_discover.py:27` -- `norm_utc` imported but never used

### L2. `sunrise_sunset()` hardcodes 365 days (no leap year)
**File:** `config.py:249`
`gamma = 2 * math.pi / 365 * (doy - 1)` -- off by ~1 minute on leap years.

### L3. `sunrise_sunset()` silently uses Jan 1, 2026 for non-date inputs
**File:** `config.py:244-246`
Should raise `TypeError` instead of masking bugs with a fallback.

### L4. `sail_rating()` missing None guard on `total_rain`
**File:** `config.py:334`
Other parameters are guarded but `total_rain` is not.

### L5. `T_str()` does not validate `lang` parameter
**File:** `i18n.py:340`
`T_str('key', 'fr')` raises unhandled `KeyError`.

### L6. STRINGS contains mixed HTML entities and plain characters
**File:** `i18n.py:21-24 vs 252`
HTML-rendered strings use `&amp;` while notification strings use literal `&`. Using `T()` in the wrong context produces visible entities.

### L7. `strftime('%-d')` not portable
**File:** `wrf_analyze.py:899, 1447, 1685, 1882`
GNU/Linux extension; crashes on Windows.

### L8. Fragile HTML string surgery
**File:** `wrf_analyze.py:1370-1373, 1997-2000`
Stripping closing `</div>` tags by string matching to append content. If formatting changes, the HTML structure silently breaks.

### L9. `avg_metric` and `bias_metric` are identical functions
**File:** `wrf_analyze.py:2069-2075`
Both compute arithmetic mean. Should be consolidated.

### L10. Missing `encoding='utf-8'` on some `write_text()` calls
**File:** `wrf_analyze.py:2249-2250, 2265`
CJK content written without explicit UTF-8 encoding. Works on Linux but could produce mojibake elsewhere.

### L11. ECMWF init_utc derived from first timestamp, not model metadata
**File:** `ecmwf_fetch.py:207-211`
Open-Meteo may start at a different hour than the model init cycle.

### L12. GFS gust backfill uses snapshot, not window max
**File:** `ecmwf_fetch.py:186-188`
ECMWF gusts use max across 6h window; GFS backfill uses point value. Inconsistent.

### L13. Ensemble spread=0 with n=1 is misleading
**File:** `ensemble_fetch.py:190-197`
Downstream interprets spread=0 as "all models agree" rather than "only one model available."

### L14. ECMWF records missing from ensemble `models` output
**File:** `ensemble_fetch.py:239-240`
ECMWF is used in spread calculation but not included in `output["models"]`.

### L15. Extremum detection misses events near boundary
**File:** `tide_predict.py:166`
Loop stops at `end - step`, missing extrema in the last 6 minutes.

### L16. `predict_height_anchored` silent fallback with no logging
**File:** `tide_predict.py:92-98`
Falls back to pure harmonic prediction without logging, making accuracy issues hard to diagnose.

### L17. Global mutable state in surf_forecast.py
**File:** `surf_forecast.py:32-36`
`_CWA_TIDE_EXTREMA` and `_CWA_SPOT_OBS` make the module non-reentrant.

### L18. `--all` flag default=True makes it impossible to disable
**File:** `cwa_fetch.py:1127`
Dead code -- the flag is always True.

### L19. Telegram tokens accepted via CLI args
**File:** `notify.py:325-326`
Visible in `/proc/<pid>/cmdline`. The env var fallback is safer.

### L20. `vercel.json` build command references `frontend/` with Vite
**File:** `vercel.json:2-4`
CLAUDE.md says the site is static HTML from Python. The Vercel config may be for a different setup.

### L21. Render-blocking Google Fonts import
**File:** `pwa/styles.css:4`
`@import` for Google Fonts blocks rendering on slow networks.

### L22. Nav active state never highlights on spot subpages
**File:** `html_template.py:61`
Exact string match means `/spots/fulong` never matches `/surf` nav item.

### L23. `vercel.json` catch-all rewrite masks 404s
**File:** `vercel.json:7`
`/(.*) -> /index.html` serves the dashboard for any non-existent path instead of a 404.

### L24. Firebase SA key written to `/tmp` and never cleaned up
**File:** `wrf.yml:58, forecast.yml:48, deploy.yml:49`
Service account key persists on the runner disk after the job.

### L25. Third-party Actions pinned to major version tags, not SHAs
**File:** All workflows
Supply-chain risk -- a compromised tag update would affect all runs.

### L26. Duplicate timestamp parsing pattern across fetch modules
**File:** `ecmwf_fetch.py:160, wave_fetch.py:143, ensemble_fetch.py:119`
`datetime.fromisoformat(t if len(t) >= 19 else t + ':00')` duplicated in 3 files. Should be a shared utility in `config.py`.

### L27. Accuracy tracking uses raw urllib without shared retry logic
**File:** `accuracy_track.py:65-94`
`fetch_observations` and `fetch_wave_observations` don't use `config.fetch_json()`.

### L28. `cwa_discover.py` sentinel detection is incomplete
**File:** `cwa_discover.py:416`
Only treats `"-99"` as invalid. CWA APIs also use `-999`, `-9999`, `-99.0`.

---

## Test Coverage Gaps

| Area | Status |
|------|--------|
| `html_template.py` | No tests |
| `cwa_discover.py` | No tests |
| `wrf_analyze.py` core GRIB2 extraction | Not tested (only helpers tested) |
| `surf_forecast.py` HTML generation | Not tested |
| `notify.py` send functions | Not tested |
| `ecmwf_fetch.py` | 3 tests (minimal) |
| `wave_fetch.py` | 2 tests (minimal) |
| JSON contract validation between pipeline stages | No tests |
| Integration/end-to-end | No tests |

---

## Recommended Priority Order

1. **Fix H1 + H2** (accuracy feedback loop) -- the AI summary is calibrating against bad data
2. **Fix H3** (falsy 0.0 bug) -- use `is not None` checks instead of `or`
3. **Fix H5** (credential leak) -- sanitize URLs in error logs
4. **Fix H4** (precip heuristic) -- add explicit units validation or remove the heuristic
5. **Fix H6** (daylight calc) -- handle UTC midnight crossing for Taiwan
6. **Fix H7 + M17** (documentation + CI) -- update CLAUDE.md, add deploy gate on critical failures
7. **Fix M1 + M2** (XSS) -- wire up `html.escape` in `bilingual()` and notification formatting
8. **Fix M16** (script injection) -- use `env:` blocks in workflows
9. Address remaining medium items
10. Improve test coverage for untested modules
