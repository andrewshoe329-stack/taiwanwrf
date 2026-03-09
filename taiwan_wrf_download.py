#!/usr/bin/env python3
"""
taiwan_wrf_download.py
======================
Download the latest Taiwan WRF GRIB2 forecast files from the
Central Weather Administration (CWA) Open Data AWS S3 bucket.

Data source: s3://cwaopendata  (public, no credentials needed)
  M-A0064 — 3km High-Resolution WRF (best for Taiwan)  ~170 MB/file
  M-A0061 — 15km Regional WRF      (wider Asia domain)  ~55 MB/file
Each model: 15 forecast files at 6-hour intervals (0 → 84 h), updated 4×/day.

Usage examples
--------------
  # Download all forecast hours of the 3km WRF (default)
  python3 taiwan_wrf_download.py

  # Download only 0h, 6h, and 12h forecasts
  python3 taiwan_wrf_download.py --hours 0 6 12

  # Download AND produce a 50nm-around-Keelung subset GRIB2 per file
  python3 taiwan_wrf_download.py --keelung

  # Keelung subset only, skip saving the full-domain files
  python3 taiwan_wrf_download.py --keelung-only

  # Use the 15km model, custom output dir, custom radius
  python3 taiwan_wrf_download.py --model M-A0061 --keelung --radius 75 --outdir ~/weather/wrf

  # Print current model run info and exit
  python3 taiwan_wrf_download.py --info

Subsetting requirements (optional — only needed for --keelung)
--------------------------------------------------------------
  pip install eccodes          # GRIB2 → GRIB2 subset  (recommended)
  pip install cfgrib xarray    # GRIB2 → NetCDF subset (fallback)
  If neither is installed the full-domain GRIB2 is kept as-is.
"""

import argparse
import json
import math
import os
import sys
import shutil
import tarfile
import threading
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from datetime import datetime, timezone

# ── Constants ────────────────────────────────────────────────────────────────

S3_BASE = "https://cwaopendata.s3.ap-northeast-1.amazonaws.com/Model"

MODELS = {
    "M-A0064": {
        "name": "3km High-Resolution WRF",
        "resolution": "3 km",
        "max_hours": 84,
        "approx_mb": 170,
    },
    "M-A0061": {
        "name": "15km Regional WRF",
        "resolution": "15 km",
        "max_hours": 84,
        "approx_mb": 55,
    },
}

DEFAULT_MODEL = "M-A0064"
FORECAST_INTERVAL = 6   # hours between files

# Keelung, Taiwan  (Port of Keelung)
KEELUNG_LAT = 25.1276
KEELUNG_LON = 121.7392
DEFAULT_RADIUS_NM = 50

# ── Geometry helpers ─────────────────────────────────────────────────────────

def nm_to_km(nm: float) -> float:
    return nm * 1.852


def bbox_from_point(lat: float, lon: float, radius_nm: float) -> dict:
    """
    Return a lat/lon bounding box (square envelope) around a point.
    The square fully contains the circle of the given radius.
    """
    km = nm_to_km(radius_nm)
    lat_delta = km / 111.12
    lon_delta = km / (111.12 * math.cos(math.radians(lat)))
    return {
        "lat_min": lat - lat_delta,
        "lat_max": lat + lat_delta,
        "lon_min": lon - lon_delta,
        "lon_max": lon + lon_delta,
    }


def bbox_contains_point(bbox: dict, lat: float, lon: float) -> bool:
    return (
        bbox["lat_min"] <= lat <= bbox["lat_max"]
        and bbox["lon_min"] <= lon <= bbox["lon_max"]
    )


# ── Thread safety ────────────────────────────────────────────────────────────

_print_lock = threading.Lock()   # serialise console output across threads
# Note: no global eccodes lock — each thread uses its own independent file
# handles and GRIB message objects, so concurrent subsetting is safe.


def _log(msg: str) -> None:
    with _print_lock:
        print(msg, flush=True)


# ── Network helpers ──────────────────────────────────────────────────────────

def fetch_json(url: str, timeout: int = 15) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.load(r)


def download_file(url: str, dest: Path) -> None:
    """Stream-download url → dest (atomic rename on completion)."""
    tmp = dest.with_suffix(dest.suffix + ".part")
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=120) as resp:
            chunk_size = 1 << 17  # 128 KB
            with open(tmp, "wb") as f:
                while True:
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
        tmp.rename(dest)
    except Exception:
        if tmp.exists():
            tmp.unlink()
        raise


# ── CWA model metadata ───────────────────────────────────────────────────────

def get_run_info(model_id: str) -> dict:
    """Fetch the JSON sidecar for forecast hour 000 to discover the current run."""
    url = f"{S3_BASE}/{model_id}-000.json"
    raw = fetch_json(url)
    info = raw["cwaopendata"]["dataset"]["datasetInfo"]
    init_dt = datetime.strptime(info["InitialTime"], "%Y%m%d%H%M").replace(
        tzinfo=timezone.utc
    )
    return {
        "model_id":   model_id,
        "init_time":  init_dt,
        "resolution": info["GridResolution"],
        "grid_x":     int(info["GridDimensionX"]),
        "grid_y":     int(info["GridDimensionY"]),
        "lat_start":  float(info["StartPointLatitude"]),
        "lon_start":  float(info["StartPointLongitude"]),
        "lat_end":    float(info["EndPointLatitude"]),
        "lon_end":    float(info["EndPointLongitude"]),
    }


# ── GRIB2 subsetting ─────────────────────────────────────────────────────────

def subset_grib2(src: Path, dst: Path, bbox: dict) -> Path:
    """
    Crop all GRIB2 messages in src to the given bounding box and write dst.

    Priority:
      1. eccodes Python package  →  GRIB2 output  (sailing-app compatible)
      2. cfgrib + xarray         →  NetCDF output (with .nc suffix)
      3. Neither available       →  returns src unchanged with a warning
    """
    try:
        import eccodes as ec
        return _subset_eccodes(src, dst, bbox, ec)
    except (ImportError, RuntimeError):
        pass

    try:
        import cfgrib
        import xarray as xr
        nc_dst = dst.with_suffix(".nc")
        return _subset_cfgrib(src, nc_dst, bbox, cfgrib, xr)
    except ImportError:
        pass

    print(
        "    ⚠  No subsetting library found.\n"
        "       Full-domain file kept. To enable subsetting install:\n"
        "         pip install eccodes        (GRIB2 output)\n"
        "         pip install cfgrib xarray  (NetCDF fallback)"
    )
    return src   # caller handles the fallback path


def _subset_eccodes(src: Path, dst: Path, bbox: dict, ec) -> Path:
    """
    Subset using the eccodes Python bindings — produces a valid GRIB2 file.

    Handles both regular lat/lon grids (regular_ll) and Lambert Conformal
    grids (lambert) which is what CWA Taiwan WRF uses.

    Performance: all messages in a WRF file share the same grid geometry, so
    the expensive lat/lon array extraction and numpy mask computation are cached
    after the first message and reused for every subsequent message in the file.
    """
    import numpy as np

    lat_min = bbox["lat_min"]
    lat_max = bbox["lat_max"]
    lon_min = bbox["lon_min"]
    lon_max = bbox["lon_max"]

    n_in = n_out = 0

    # Cache keyed by (grid_type, ni, nj).
    # Value: None  → bbox misses this grid entirely (skip all such messages)
    #        tuple → (j_min, j_max, i_min, i_max, new_lat1, new_lon1, extra)
    _grid_cache: dict = {}

    with open(src, "rb") as fin, open(dst, "wb") as fout:
        while True:
            msg = ec.codes_grib_new_from_file(fin)
            if msg is None:
                break
            n_in += 1
            try:
                grid_type = ec.codes_get(msg, "gridType")
                ni = ec.codes_get(msg, "Ni")
                nj = ec.codes_get(msg, "Nj")

                if ni <= 1 or nj <= 1:
                    ec.codes_write(msg, fout)
                    n_out += 1
                    continue

                cache_key = (grid_type, ni, nj)

                if cache_key not in _grid_cache:
                    # First time we see this grid: compute lat/lon arrays and
                    # derive the sub-grid slice indices.  This is the expensive
                    # step (reads ~800 K floats from the C library + numpy mask).
                    all_lats = ec.codes_get_array(msg, "latitudes").reshape(nj, ni)
                    all_lons = ec.codes_get_array(msg, "longitudes").reshape(nj, ni)

                    mask = (
                        (all_lats >= lat_min) & (all_lats <= lat_max) &
                        (all_lons >= lon_min) & (all_lons <= lon_max)
                    )
                    rows, cols = np.where(mask)

                    if len(rows) == 0:
                        _grid_cache[cache_key] = None   # bbox outside this grid
                    else:
                        j_min, j_max = int(rows.min()), int(rows.max())
                        i_min, i_max = int(cols.min()), int(cols.max())
                        extra = {}
                        if grid_type == "regular_ll":
                            extra["lat2"] = float(all_lats[j_max, i_max])
                            extra["lon2"] = float(all_lons[j_max, i_max])
                        _grid_cache[cache_key] = (
                            j_min, j_max, i_min, i_max,
                            float(all_lats[j_min, i_min]),
                            float(all_lons[j_min, i_min]),
                            extra,
                        )

                entry = _grid_cache[cache_key]
                if entry is None:
                    ec.codes_release(msg)
                    continue

                j_min, j_max, i_min, i_max, new_lat1, new_lon1, extra = entry
                new_ni = i_max - i_min + 1
                new_nj = j_max - j_min + 1

                # Slice data values (only the per-message work remaining)
                vals = ec.codes_get_values(msg)
                vals_2d = vals.reshape(nj, ni)
                sub = vals_2d[j_min: j_max + 1, i_min: i_max + 1].flatten()

                # Build output message
                clone = ec.codes_clone(msg)
                ec.codes_set(clone, "Ni", new_ni)
                ec.codes_set(clone, "Nj", new_nj)
                ec.codes_set(clone, "latitudeOfFirstGridPointInDegrees",  new_lat1)
                ec.codes_set(clone, "longitudeOfFirstGridPointInDegrees", new_lon1)

                if grid_type == "regular_ll":
                    ec.codes_set(clone, "latitudeOfLastGridPointInDegrees",  extra["lat2"])
                    ec.codes_set(clone, "longitudeOfLastGridPointInDegrees", extra["lon2"])

                ec.codes_set_values(clone, sub)
                ec.codes_write(clone, fout)
                ec.codes_release(clone)
                n_out += 1

            except Exception as e:
                print(f"\n    ⚠  Skipped message ({type(e).__name__}): {e}")
            finally:
                ec.codes_release(msg)

    print(f"    ✂  Subset: {n_out}/{n_in} messages written → {dst.name}")
    return dst


def _subset_cfgrib(src: Path, dst: Path, bbox: dict, cfgrib, xr) -> Path:
    """Fallback: read with cfgrib, crop, save as NetCDF."""
    datasets = cfgrib.open_datasets(str(src), errors="ignore")
    merged = []
    for ds in datasets:
        lat_k = "latitude" if "latitude" in ds.dims else "lat"
        lon_k = "longitude" if "longitude" in ds.dims else "lon"
        sub = ds.sel(
            {lat_k: slice(bbox["lat_min"], bbox["lat_max"]),
             lon_k: slice(bbox["lon_min"], bbox["lon_max"])}
        )
        merged.append(sub)
    xr.merge(merged, compat="override").to_netcdf(dst)
    print(f"    ✂  Saved NetCDF subset → {dst.name}")
    return dst


def _make_archive(files: list, archive_path: Path) -> Path:
    """
    Pack a list of files into a gzip-compressed tar archive.
    Each file is stored with only its basename (no directory prefix).
    GRIB2 data is already compressed internally, so we use the fastest
    gzip level (1) — this mainly gives us a single-file container.
    """
    with tarfile.open(archive_path, "w:gz", compresslevel=1) as tar:
        for f in sorted(files):
            if Path(f).exists():
                tar.add(f, arcname=Path(f).name)
    return archive_path


# ── Per-file worker (runs in thread pool) ────────────────────────────────────

def _process_file(
    fh: int,
    model_id: str,
    outdir: Path,
    bbox: dict,
    keelung_only: bool,
    force: bool,
    radius_nm: float,
) -> Path:
    """Download one forecast file, subset it, optionally delete the full grib."""
    filename   = f"{model_id}-{fh:03d}.grb2"
    url        = f"{S3_BASE}/{filename}"
    dest       = outdir / filename
    tag        = f"[F{fh:03d}]"

    # ── Download ──────────────────────────────────────────────────────────────
    if dest.exists() and not force:
        size_mb = dest.stat().st_size / 1_048_576
        _log(f"  {tag}  ⏭  {filename}  ({size_mb:.0f} MB) already exists — skipping")
    else:
        if dest.exists():
            dest.unlink()
        _log(f"  {tag}  ⬇  Downloading {filename} …")
        download_file(url, dest)
        size_mb = dest.stat().st_size / 1_048_576
        _log(f"  {tag}  ✓  {filename}  {size_mb:.0f} MB saved")

    if not bbox:
        return dest

    # ── Keelung subset ────────────────────────────────────────────────────────
    subset_name = f"{model_id}-{fh:03d}_keelung{int(radius_nm)}nm.grb2"
    subset_dest = outdir / subset_name

    if subset_dest.exists() and subset_dest.suffix != ".nc" and not force:
        _log(f"  {tag}  ⏭  Subset exists — skipping")
        result = subset_dest
    else:
        if subset_dest.exists():
            subset_dest.unlink()
        _log(f"  {tag}  ✂  Subsetting to Keelung {radius_nm} nm …")
        result = subset_grib2(dest, subset_dest, bbox)
        if result.exists():
            sub_mb = result.stat().st_size / 1_048_576
            _log(f"  {tag}  ✂  Done → {result.name}  ({sub_mb:.1f} MB)")

    # ── Cleanup ───────────────────────────────────────────────────────────────
    if keelung_only and dest.exists():
        if subset_dest.exists() and subset_dest != dest:
            dest.unlink()
            _log(f"  {tag}  🗑  Removed full-domain file")
        else:
            _log(f"  {tag}  ⚠  Full-domain file kept (no subsetting library available)")

    return result


# ── Main download orchestrator ────────────────────────────────────────────────

def run(
    model_id: str,
    hours: list,
    outdir: Path,
    force: bool = False,
    keelung: bool = True,
    keelung_only: bool = False,
    radius_nm: float = DEFAULT_RADIUS_NM,
    workers: int = 3,
) -> list:
    outdir.mkdir(parents=True, exist_ok=True)
    bbox = bbox_from_point(KEELUNG_LAT, KEELUNG_LON, radius_nm) if keelung else None

    # ── Header ────────────────────────────────────────────────────────────────
    sep = "─" * 62
    print(f"\n{sep}")
    print(f"  Taiwan WRF Downloader  ·  {MODELS[model_id]['name']}")
    print(sep)

    print("\n  Fetching current model run info …")
    run_info = get_run_info(model_id)
    init = run_info["init_time"]

    # Each run gets its own subfolder. If the folder already exists (re-run
    # within the same 6-hour cycle), append an incrementing number.
    base = outdir / f"{model_id}_{init.strftime('%Y%m%d_%H')}UTC"
    outdir = base
    counter = 2
    while outdir.exists():
        outdir = base.parent / f"{base.name}_{counter}"
        counter += 1
    outdir.mkdir(parents=True, exist_ok=True)

    total_files = len(hours)
    approx_total_mb = total_files * MODELS[model_id]["approx_mb"]

    print(f"  Model      : {model_id}  ({run_info['resolution']})")
    print(f"  Init time  : {init.strftime('%Y-%m-%d %H:%M UTC')}  "
          f"(local +8: {(init.hour+8)%24:02d}:00 CST)")
    print(f"  Grid       : {run_info['grid_x']} × {run_info['grid_y']} pts")
    print(f"  Forecasts  : {total_files} files  "
          f"({hours[0]}h → {hours[-1]}h in {FORECAST_INTERVAL}h steps)")
    print(f"  Est. size  : ~{approx_total_mb:,} MB total")
    print(f"  Output dir : {outdir.resolve()}")

    if bbox:
        print(
            f"\n  ┌─ Keelung subset  ({radius_nm} nm radius) ──────────────────┐\n"
            f"  │  Center : {KEELUNG_LAT}°N  {KEELUNG_LON}°E\n"
            f"  │  Lat    : {bbox['lat_min']:.3f}° → {bbox['lat_max']:.3f}°N\n"
            f"  │  Lon    : {bbox['lon_min']:.3f}° → {bbox['lon_max']:.3f}°E\n"
            f"  └───────────────────────────────────────────────────────────┘"
        )
        if keelung_only:
            print("  (--keelung-only: full-domain files will be deleted after subsetting)")

    print(f"  Workers    : {workers} parallel (download + subset)")
    print(f"\n{sep}")

    results = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(
                _process_file, fh, model_id, outdir,
                bbox, keelung_only, force, radius_nm
            ): fh
            for fh in hours
        }
        for future in as_completed(futures):
            fh = futures[future]
            try:
                results.append(future.result())
            except Exception as exc:
                _log(f"  [F{fh:03d}]  ✗  Failed: {exc}")

    # ── Compress subsets into a single archive ────────────────────────────────
    archive = None
    if bbox and results:
        archive_name = (
            f"{model_id}_{init.strftime('%Y%m%d_%H')}UTC"
            f"_keelung{int(radius_nm)}nm.tar.gz"
        )
        archive = _make_archive(results, outdir / archive_name)

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{sep}")
    total_size = sum(p.stat().st_size for p in results if p.exists()) / 1_048_576
    print(f"  ✅  Done! {len(results)} files  ·  {total_size:.0f} MB on disk")
    if archive and archive.exists():
        arc_mb = archive.stat().st_size / 1_048_576
        print(f"  📦  Archive → {archive.name}  ({arc_mb:.1f} MB)")
    print(f"  📂  {outdir.resolve()}")
    print(sep + "\n")
    return results


# ── CLI ───────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="taiwan_wrf_download.py",
        description="Download the latest Taiwan CWA WRF GRIB2 forecast files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 taiwan_wrf_download.py                       # download + Keelung subset (default)
  python3 taiwan_wrf_download.py --keelung-only        # subset only, delete full-domain files
  python3 taiwan_wrf_download.py --full-domain         # full-domain files only, no subset
  python3 taiwan_wrf_download.py --hours 0 6 12        # only 0/6/12h forecasts
  python3 taiwan_wrf_download.py --model M-A0061       # 15km model
  python3 taiwan_wrf_download.py --radius 75           # 75nm radius around Keelung
  python3 taiwan_wrf_download.py --info                # show current run and exit
  python3 taiwan_wrf_download.py --check-deps          # check subsetting libraries

Models available:
  M-A0064  3km high-res (Taiwan domain, ~170 MB/file × 15 files)  [default]
  M-A0061  15km regional (wider Asia, ~55 MB/file × 15 files)
""",
    )
    p.add_argument(
        "--model",
        choices=list(MODELS.keys()),
        default=DEFAULT_MODEL,
        metavar="MODEL",
        help=f"WRF model to use (default: {DEFAULT_MODEL}). "
             f"Choices: {', '.join(MODELS.keys())}",
    )
    p.add_argument(
        "--hours",
        nargs="+",
        type=int,
        default=None,
        metavar="H",
        help="Forecast hours to download, e.g. --hours 0 6 12 18 24 "
             "(default: all 15 files, 0–84h)",
    )
    p.add_argument(
        "--full-domain",
        action="store_true",
        help="Skip Keelung subsetting and keep only the full-domain GRIB2 files.",
    )
    p.add_argument(
        "--keelung-only",
        action="store_true",
        help="Delete full-domain files after subsetting (keep only the Keelung subset). "
             "Subsetting is on by default; this just adds the cleanup step.",
    )
    p.add_argument(
        "--radius",
        type=float,
        default=DEFAULT_RADIUS_NM,
        metavar="NM",
        help=f"Nautical-mile radius for the Keelung subset (default: {DEFAULT_RADIUS_NM})",
    )
    p.add_argument(
        "--outdir",
        default="./wrf_downloads",
        metavar="DIR",
        help="Output directory (default: ./wrf_downloads)",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Re-download/re-subset files even if they already exist",
    )
    p.add_argument(
        "--info",
        action="store_true",
        help="Print current model run metadata and exit (no download)",
    )
    p.add_argument(
        "--workers",
        type=int,
        default=3,
        metavar="N",
        help="Number of parallel download workers (default: 3)",
    )
    p.add_argument(
        "--check-deps",
        action="store_true",
        help="Check which subsetting libraries are available and exit",
    )
    return p


def check_deps() -> None:
    print("\n  Dependency check for GRIB2 subsetting:\n")
    for pkg, label in [
        ("eccodes",  "eccodes        → GRIB2 output  (recommended)"),
        ("cfgrib",   "cfgrib         → GRIB2 reading  (NetCDF fallback)"),
        ("xarray",   "xarray         → needed by cfgrib fallback"),
    ]:
        try:
            mod = __import__(pkg)
            ver = getattr(mod, "__version__", "?")
            print(f"    ✓  {label}  (v{ver})")
        except ImportError:
            print(f"    ✗  {label}")
    print()
    print("  To install all at once:")
    print("    pip install eccodes cfgrib xarray\n")


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.check_deps:
        check_deps()
        return

    if args.info:
        print("\n  Fetching model run info …")
        info = get_run_info(args.model)
        info["init_time"] = info["init_time"].isoformat()
        print(json.dumps(info, indent=4, ensure_ascii=False))
        return

    # Subsetting is on by default; --full-domain disables it.
    keelung = not args.full_domain

    # Resolve forecast hours
    all_hours = list(range(0, MODELS[args.model]["max_hours"] + 1, FORECAST_INTERVAL))
    hours = sorted(set(args.hours)) if args.hours else all_hours

    bad = [h for h in hours if h not in all_hours]
    if bad:
        print(f"  ✗  Invalid forecast hours: {bad}")
        print(f"     Valid values: {all_hours}")
        sys.exit(1)

    run(
        model_id=args.model,
        hours=hours,
        outdir=Path(args.outdir),
        force=args.force,
        keelung=keelung,
        keelung_only=args.keelung_only,
        radius_nm=args.radius,
        workers=args.workers,
    )


if __name__ == "__main__":
    main()
