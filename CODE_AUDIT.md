# Code Audit Report — Taiwan WRF Forecast Pipeline

**Date:** 2026-03-22
**Scope:** Full codebase audit covering all Python modules, tests, CI/CD, and PWA files.

---

## Executive Summary

Audited 10 Python modules (~4,900 LOC), 8 test files (140 tests), 1 CI/CD workflow, and PWA assets. Found **68 issues** across severity levels:

| Severity | Count | Description |
|----------|-------|-------------|
| Critical | 6     | Bugs, security issues, or missing safeguards that affect correctness or CI reliability |
| High     | 12    | Logic errors, missing error handling, or resilience gaps |
| Medium   | 22    | Code quality, validation, performance, or UX issues |
| Low      | 28    | Style, documentation, minor robustness improvements |

---

## Critical Issues

### C1. `setup_logging()` cannot reconfigure log level (config.py:8-11)
`logging.basicConfig()` only takes effect on the **first** call. Subsequent calls with different levels are silently ignored. If multiple scripts or tests call `setup_logging()` with different levels, only the first wins.

**Fix:** Call `logging.getLogger().setLevel(level)` after `basicConfig()`.

### C2. `norm_utc()` performs zero validation (config.py:34-49)
- Accepts invalid dates like `2026-13-01T06:00` without error
- Does not convert non-UTC offsets (e.g., `+05:30` passes through unchanged)
- Docstring claims normalization but only does string concatenation

**Fix:** Add minimal validation with `datetime.fromisoformat()` or update docstring to document limitations.

### C3. HTTPError not caught in API fetch functions (ecmwf_fetch.py:73, wave_fetch.py:118)
Both files catch `URLError` and `JSONDecodeError` but not `HTTPError` explicitly. While `HTTPError` is a subclass of `URLError`, some urllib usage patterns require explicit handling. Server 4xx/5xx responses may not retry properly.

**Fix:** Add `urllib.error.HTTPError` to exception tuples.

### C4. `_download_file()` in wave_fetch.py has no error handling (wave_fetch.py:209-212)
Bare `urllib.request.urlopen()` and `.read()` with no try/except, no retry logic. Any HTTP error or timeout crashes the script.

**Fix:** Add try/except with retry logic consistent with other fetchers.

### C5. Rclone config written without restrictive file permissions (.github/workflows/main.yml:62-63)
```bash
printf '%s' "$RCLONE_CONFIG_CONTENT" > ~/.config/rclone/rclone.conf
```
No `chmod 600` — credentials file may be world-readable on the runner.

**Fix:** Add `chmod 600 ~/.config/rclone/rclone.conf` after writing.

### C6. npm install without version pinning (.github/workflows/main.yml:376)
`npm install -g vercel` installs latest version without a lock file. Supply chain risk and potential for breaking changes.

**Fix:** Pin to a specific version: `npm install -g vercel@<version>`.

---

## High-Severity Issues

### H1. `--force` flag doesn't force re-subsetting of GRIB2 (taiwan_wrf_download.py:401)
```python
if subset_dest.exists() and subset_dest.suffix != ".nc" and not force:
```
The `.suffix != ".nc"` condition means GRIB2 files (`.grb2`) are always skipped when they exist, regardless of `--force`. The `not force` check is ANDed, not a separate condition.

**Fix:** Simplify to `if subset_dest.exists() and not force:`.

### H2. No retry logic on S3 metadata fetch (taiwan_wrf_download.py:170)
`fetch_json()` for the S3 model run JSON has no retry/error handling, unlike `download_file()` which has 3-attempt retry with exponential backoff.

### H3. Rain 6h calculation uses wrong window size (surf_forecast.py:196-199)
```python
for k in range(max(0, i - 5), i + 1)
```
`range(i-5, i+1)` is 6 elements (indices i-5 through i inclusive), but this sums hourly precip for indices 0-based. When `i < 5`, the window shrinks silently, producing underestimates for early records.

### H4. Fragile time format detection (ecmwf_fetch.py:173, wave_fetch.py:156-157)
```python
datetime.fromisoformat(t if len(t) >= 19 else t + ':00')
```
Doesn't handle `Z` suffix, fractional seconds, or non-UTC offsets. Should use `norm_utc()` from config.py instead of ad-hoc parsing.

### H5. Grid cache key missing grid_type in wave_fetch.py (wave_fetch.py:312)
Cache key is `(ni, nj)` only — known latent bug per CLAUDE.md. If messages have different projections with same dimensions, cached grid coordinates would be wrong.

### H6. Silent error masking in ecmwf_fetch.py (ecmwf_fetch.py:81)
`_fetch_json()` returns `{}` on failure, which is indistinguishable from "no data available." Downstream code logs "No records extracted" without knowing the API actually failed.

### H7. ThreadPoolExecutor silently drops failed spots (surf_forecast.py:804-818)
If the Keelung fetch fails, `keelung_records` stays empty, producing a blank sailing forecast with no user-visible warning.

### H8. No timeouts on most CI workflow steps (.github/workflows/main.yml)
Only the download step has `timeout-minutes: 30`. All other network-dependent steps (ECMWF fetch, wave fetch, AI summary, rclone upload, Vercel deploy) have no timeout, risking 6-hour runner hangs.

### H9. `_trim_records()` silent fallback on malformed dates (forecast_summary.py:52-58)
When `datetime.fromisoformat()` fails, falls back to `records[:max_days * 4]` — invalid records with malformed `valid_utc` pass through to the LLM prompt.

### H10. Array reshape without size validation (wrf_analyze.py:213-214, 246-251)
`codes_get_array().reshape(nj, ni)` will raise `ValueError` if array size doesn't match `ni*nj`, caught only by a broad `except Exception`.

### H11. No validation of Ni/Nj grid dimensions (wrf_analyze.py:240-241)
If GRIB2 returns zero or negative dimensions, reshape produces wrong results.

### H12. Anthropic API retry doesn't catch all network errors (forecast_summary.py:148-149)
Only catches `APIConnectionError`, `RateLimitError`, `InternalServerError`, and `ValueError`. Misses `socket.timeout`, `ssl.SSLError`, and generic `OSError`.

---

## Medium-Severity Issues

### M1. `deg_to_compass()` rounding ambiguity at boundaries (config.py:31)
Python's `round()` uses banker's rounding. At exact boundaries (11.25, 33.75, etc.), direction assignment is unpredictable.

### M2. COMPASS_NAMES is mutable list (config.py:21-24)
Could be accidentally mutated. Should be a tuple.

### M3. `norm_utc()` doesn't handle non-UTC offsets (config.py:43-49)
Input `2026-03-09T06:00:00+05:30` passes through unchanged — violates the function's contract.

### M4. Double-processing of ECMWF data on GFS backfill (ecmwf_fetch.py:236-240)
`process(raw, raw_fill)` rebuilds all records from scratch instead of just backfilling.

### M5. No JSON schema validation on input files (wrf_analyze.py:1265-1295)
External JSON files are loaded without type/structure checks.

### M6. Unescaped tide data in HTML output (wrf_analyze.py:695-696)
Tide `cst` field from JSON embedded in HTML without `html.escape()`.

### M7. Fragile string slicing for time extraction (wrf_analyze.py:695)
`ex.get('cst', '')[-9:-4]` assumes exact string format — breaks silently if format changes.

### M8. No validation of --radius and --workers args (taiwan_wrf_download.py:587, 610)
Negative radius or zero workers would cause runtime errors instead of user-friendly validation.

### M9. Mutually exclusive flags not enforced (taiwan_wrf_download.py:579-582)
`--keelung-only` and `--full-domain` can both be passed; behavior is ambiguous.

### M10. Inconsistent logging wrapper usage (taiwan_wrf_download.py:116-118)
`_log()` wrapper defined but used inconsistently alongside direct `log.info()` calls.

### M11. Missing return type hints on many functions
Scattered across all modules. Reduces IDE support and type-checking.

### M12. Broad exception catching (wave_fetch.py:204, 260, 325)
`except Exception` swallows real errors like KeyboardInterrupt (Python < 3.8).

### M13. No retry logic for CWA wave probe/download (wave_fetch.py:196, 211)
Unlike ECMWF fetch, S3 downloads have no retry logic.

### M14. isoformat() may lack +00:00 offset (wave_fetch.py:354)
If `init_time` is naive datetime, output won't include UTC offset.

### M15. Incomplete regex for GRIB2 filename (wave_fetch.py:343)
`r'-(\d{3})\.grb2$'` requires exactly 3 digits — non-zero-padded filenames silently skipped.

### M16. Service worker may serve stale forecasts offline (pwa/sw.js:27-42)
Network-first with cache fallback, but no staleness warning if data is >6 hours old.

### M17. Duplicate init_utc check prevents forecast updates (accuracy_track.py:210-212)
Same `init_utc` with different `verified_utc` — newer accuracy data is discarded.

### M18. String-based date cutoff comparison (accuracy_track.py:215-216)
ISO string comparison works but fragile with varying formats.

### M19. Non-portable strftime format (wrf_analyze.py:637)
`%-m` and `%-d` flags don't work on Windows.

### M20. HTML generation via 340+ lines of string concatenation (wrf_analyze.py:860-1183)
Acknowledged in CLAUDE.md — hard to test, maintain, and prone to typos.

### M21. Thread-safety gap in grid cache (taiwan_wrf_download.py:112-113, 264)
Shared `_grid_cache` dict is written by multiple threads without locking.

### M22. Missing test suite for forecast_summary.py
Zero test coverage for the AI summary module — prompt building, API retry, HTML output all untested.

---

## Low-Severity Issues (Summary)

| ID | File | Issue |
|----|------|-------|
| L1 | config.py | `deg_to_compass()` accepts booleans silently |
| L2 | config.py | Magic numbers (22.5, 16) not extracted as constants |
| L3 | config.py | `norm_utc()` docstring overstates guarantees |
| L4 | wrf_analyze.py | Module-level `_grid_cache` grows unbounded |
| L5 | wrf_analyze.py | Repeated `.get()` calls in wave data (minor perf) |
| L6 | wrf_analyze.py | Incomplete docstring for `render_unified_html()` |
| L7 | wrf_analyze.py | Unescaped model_id in HTML (low risk in practice) |
| L8 | taiwan_wrf_download.py | Misleading RuntimeError init in download_file() |
| L9 | taiwan_wrf_download.py | Redundant file existence check (line 387) |
| L10 | taiwan_wrf_download.py | Hardcoded timeout (120s) not configurable |
| L11 | taiwan_wrf_download.py | Magic numbers (chunk_size, MB conversion) |
| L12 | taiwan_wrf_download.py | Missing failure mode documentation |
| L13 | taiwan_wrf_download.py | `__import__()` instead of `importlib.import_module()` |
| L14 | ecmwf_fetch.py | Unsafe array indexing for first timestamp |
| L15 | ecmwf_fetch.py | No coordinate proximity validation |
| L16 | wave_fetch.py | Semicolons as statement separators (style) |
| L17 | wave_fetch.py | Missing return type annotations |
| L18 | wave_fetch.py | No coordinate validation on API response |
| L19 | surf_forecast.py | Config import alias (`compass = deg_to_compass`) |
| L20 | surf_forecast.py | Spot ordering silently handles unknown IDs |
| L21 | surf_forecast.py | Missing HTML entity escaping throughout |
| L22 | surf_forecast.py | Recommendation logic uses emoji string comparison |
| L23 | surf_forecast.py | 600px mobile breakpoint is arbitrary |
| L24 | tide_predict.py | String comparison instead of datetime in tide_state() |
| L25 | tide_predict.py | No runtime validation of CONSTITUENTS phases |
| L26 | accuracy_track.py | Mismatched observation array lengths handled silently |
| L27 | forecast_summary.py | Empty summary writes empty file (no error indicator) |
| L28 | forecast_summary.py | Hardcoded model ID inconsistent with CLAUDE.md |

---

## Test Coverage Gaps

| Module | Covered | Not Covered |
|--------|---------|-------------|
| config.py | `deg_to_compass`, `norm_utc` | `setup_logging` reconfiguration |
| wrf_analyze.py | Formatting helpers, emoji, colors | `read_point`, `extract_forecast`, `render_unified_html`, `nearest_idx` |
| taiwan_wrf_download.py | Geometry helpers, constants | `download_file`, `_subset_eccodes`, `_make_archive`, `run()` |
| ecmwf_fetch.py | GFS backfill null handling | Network errors, timeouts, rate limits |
| wave_fetch.py | Basic processing (1 test) | Null fields, missing swell data, timezone handling |
| surf_forecast.py | Scoring, ratings, compass (34 tests) | HTML generation, `_recommend()`, thread pool |
| tide_predict.py | Semidiurnal pattern, extrema | `tide_state()`, edge cases |
| accuracy_track.py | Error metrics | Observation fetch, stale data pruning |
| **forecast_summary.py** | **NONE** | **Everything** |

---

## Top 10 Priority Fixes

1. **C1** — Fix `setup_logging()` to actually set the level
2. **C3** — Add `HTTPError` to fetch exception handlers
3. **C5** — `chmod 600` on rclone config in CI
4. **H1** — Fix `--force` flag logic in download script
5. **H4** — Use `norm_utc()` instead of ad-hoc time parsing
6. **H5** — Include grid_type in wave_fetch cache key
7. **H8** — Add timeout-minutes to all CI workflow steps
8. **C2** — Add validation to `norm_utc()` or update docstring
9. **H6** — Distinguish fetch failure from empty data in ecmwf_fetch
10. **M22** — Create test suite for forecast_summary.py
