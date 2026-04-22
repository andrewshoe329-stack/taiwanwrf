#!/usr/bin/env python3
"""
firebase_storage.py — Firebase Firestore + Cloud Storage helpers for the pipeline.

Replaces Google Drive (rclone) for persistent storage of:
  - keelung_summary.json  → Firestore document (pipeline_state/keelung_summary)
  - accuracy_log.json     → Firestore document (pipeline_state/accuracy_log)
  - GRIB2 .tar.gz archives → Cloud Storage bucket with 3-day retention

Usage (CLI):
    python firebase_storage.py download-summary --output keelung_summary.json
    python firebase_storage.py upload-summary --input keelung_summary_new.json
    python firebase_storage.py download-accuracy-log --output accuracy_log.json
    python firebase_storage.py upload-accuracy-log --input accuracy_log.json
    python firebase_storage.py upload-archive --input path/to/archive.tar.gz
    python firebase_storage.py get-archive-url --name archive_name.tar.gz
    python firebase_storage.py cleanup-archives --keep current_archive.tar.gz

Requires:
    FIREBASE_PROJECT           — Firebase project ID
    GOOGLE_APPLICATION_CREDENTIALS — path to service account JSON key
    FIREBASE_STORAGE_BUCKET    — Cloud Storage bucket (for archives only)
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from config import setup_logging

log = logging.getLogger(__name__)

# Firestore collection/document paths
_COLLECTION = 'pipeline_state'
_SUMMARY_DOC = 'keelung_summary'
_ACCURACY_DOC = 'accuracy_log'
_WRF_SPOTS_DOC = 'wrf_spots'
_ACCURACY_ENTRIES = 'accuracy_log'  # per-entry collection for queryability
_ARCHIVE_PREFIX = 'archives/'

# Module-level flag to track initialisation
_initialized = False


def _check_configured() -> bool:
    """Return True if Firebase environment variables are set.

    Requires FIREBASE_PROJECT plus either GOOGLE_APPLICATION_CREDENTIALS
    (service account path) or ambient ADC. Without credentials the SDK
    crashes inside credentials.Certificate(None), so fail fast here.
    """
    project = os.environ.get('FIREBASE_PROJECT')
    if not project:
        log.info("FIREBASE_PROJECT not set — Firebase storage disabled")
        return False
    sa_path = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
    if sa_path and not Path(sa_path).is_file():
        log.error("GOOGLE_APPLICATION_CREDENTIALS=%s does not exist", sa_path)
        return False
    return True


def init_firebase() -> None:
    """Initialise Firebase Admin SDK (idempotent)."""
    global _initialized
    if _initialized:
        return

    import firebase_admin  # type: ignore[import-untyped]
    from firebase_admin import credentials  # type: ignore[import-untyped]

    try:
        firebase_admin.get_app()
        _initialized = True
        return
    except ValueError:
        pass  # no app initialized yet

    project = os.environ.get('FIREBASE_PROJECT')
    sa_path = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
    if sa_path:
        cred = credentials.Certificate(sa_path)
    else:
        cred = credentials.ApplicationDefault()

    firebase_admin.initialize_app(cred, {
        'projectId': project,
        'storageBucket': os.environ.get('FIREBASE_STORAGE_BUCKET', ''),
    })
    _initialized = True
    log.info("Firebase initialised (project=%s)", project)


# ── Firestore document operations ────────────────────────────────────────────

def read_document(collection: str, doc_id: str) -> dict | None:
    """Read a Firestore document. Returns dict or None if not found."""
    from firebase_admin import firestore  # type: ignore[import-untyped]

    init_firebase()
    db = firestore.client()
    doc = db.collection(collection).document(doc_id).get()
    if doc.exists:
        return doc.to_dict()
    return None


def write_document(collection: str, doc_id: str, data: dict) -> None:
    """Write/overwrite a Firestore document."""
    from firebase_admin import firestore  # type: ignore[import-untyped]

    init_firebase()
    db = firestore.client()
    db.collection(collection).document(doc_id).set(data)
    log.info("Firestore write → %s/%s", collection, doc_id)


# ── High-level helpers for pipeline JSON files ───────────────────────────────

def download_summary() -> dict | None:
    """Download the previous keelung_summary from Firestore."""
    return read_document(_COLLECTION, _SUMMARY_DOC)


def upload_summary(data: dict) -> None:
    """Upload keelung_summary to Firestore."""
    write_document(_COLLECTION, _SUMMARY_DOC, data)


def download_wrf_spots() -> dict | None:
    """Download the WRF per-spot data from Firestore."""
    return read_document(_COLLECTION, _WRF_SPOTS_DOC)


def upload_wrf_spots(data: dict) -> None:
    """Upload WRF per-spot data to Firestore."""
    write_document(_COLLECTION, _WRF_SPOTS_DOC, data)


def download_accuracy_log() -> list | None:
    """Download the full accuracy_log array from Firestore."""
    doc = read_document(_COLLECTION, _ACCURACY_DOC)
    if doc and 'entries' in doc:
        return doc['entries']
    return None


def upload_accuracy_log(entries: list) -> None:
    """Upload accuracy_log array to Firestore.

    Stores the full array as a single document (pipeline_state/accuracy_log)
    and also writes the latest entry to the per-entry collection.
    """
    # Full array in a single document for easy download
    # Trim to last 90 entries to stay within Firestore 1MB doc limit
    trimmed = entries[-90:] if len(entries) > 90 else entries
    doc_data = {'entries': trimmed}
    doc_size = len(json.dumps(doc_data).encode('utf-8'))
    if doc_size > 900_000:  # 100KB safety margin below Firestore 1MB doc limit
        # Further trim until under limit
        while doc_size > 900_000 and len(trimmed) > 10:
            trimmed = trimmed[-len(trimmed)//2:]
            doc_data = {'entries': trimmed}
            doc_size = len(json.dumps(doc_data).encode('utf-8'))
        log.warning("Accuracy log trimmed to %d entries (%d bytes) "
                     "to stay within Firestore 1MB limit.", len(trimmed), doc_size)
    write_document(_COLLECTION, _ACCURACY_DOC, doc_data)

    # Also write the latest entry individually (for querying)
    if entries:
        entry = entries[-1]
        init_utc = entry.get('init_utc', 'unknown')
        model_id = entry.get('model_id', 'unknown')
        doc_id = f"{init_utc}_{model_id}".replace(':', '-').replace('+', 'p')
        write_document(_ACCURACY_ENTRIES, doc_id, entry)


# ── Pipeline health metrics ──────────────────────────────────────────────────

def record_pipeline_health(run_id: str, metrics: dict) -> None:
    """Store pipeline run health metrics in Firestore.

    Args:
        run_id: GitHub Actions run ID or 'local' for local runs.
        metrics: Dict of step outcomes (e.g. {'ecmwf': True, 'wave': False}).
    """
    from datetime import datetime, timezone
    doc = {
        'run_utc': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S+00:00'),
        **metrics,
    }
    write_document('pipeline_health', run_id, doc)


def archive_daily_summary(summary: dict, wave: dict | None = None) -> None:
    """Archive daily max/min/avg for key weather variables to Firestore.

    Designed to be called once per forecast cycle; uses the first valid_utc
    date as the document ID so only the latest cycle's data is kept per day.
    """
    records = summary.get('records', [])
    if not records:
        return

    date_str = records[0].get('valid_utc', '')[:10]  # YYYY-MM-DD
    if not date_str:
        return

    def _stats(values):
        if not values:
            return None, None, None
        return round(min(values), 1), round(max(values), 1), round(sum(values) / len(values), 1)

    temps = [r['temp_c'] for r in records if r.get('temp_c') is not None]
    winds = [r['wind_kt'] for r in records if r.get('wind_kt') is not None]
    gusts = [r['gust_kt'] for r in records if r.get('gust_kt') is not None]
    precips = [r.get('precip_mm_6h', 0) or 0 for r in records]
    pressures = [r['mslp_hpa'] for r in records if r.get('mslp_hpa') is not None]

    t_min, t_max, t_avg = _stats(temps)
    _, w_max, w_avg = _stats(winds)
    _, g_max, _ = _stats(gusts)
    p_min, p_max, _ = _stats(pressures)

    doc: dict = {
        'date': date_str,
        'temp_min_c': t_min,
        'temp_max_c': t_max,
        'temp_avg_c': t_avg,
        'wind_max_kt': w_max,
        'wind_avg_kt': w_avg,
        'gust_max_kt': g_max,
        'precip_total_mm': round(sum(precips), 1),
        'pressure_min_hpa': p_min,
        'pressure_max_hpa': p_max,
    }

    # Wave data from wave_keelung.json
    if wave:
        wave_recs = wave.get('ecmwf_wave', {}).get('records', [])
        wave_hs = [r['wave_height'] for r in wave_recs if r.get('wave_height') is not None]
        if wave_hs:
            doc['wave_max_m'] = round(max(wave_hs), 1)
            doc['wave_avg_m'] = round(sum(wave_hs) / len(wave_hs), 1)

    write_document('daily_archive', date_str, doc)


# ── Cloud Storage for GRIB2 archives ─────────────────────────────────────────

def _get_bucket():
    """Get the Cloud Storage bucket."""
    from firebase_admin import storage  # type: ignore[import-untyped]

    init_firebase()
    return storage.bucket()


def upload_archive(local_path: str) -> str | None:
    """Upload a .tar.gz archive to Cloud Storage. Returns the public URL."""
    if not Path(local_path).is_file():
        log.error("Archive file not found: %s", local_path)
        return None
    bucket = _get_bucket()
    name = _ARCHIVE_PREFIX + Path(local_path).name
    blob = bucket.blob(name)
    blob.upload_from_filename(local_path)
    # Make publicly readable so the download link works without auth
    try:
        blob.make_public()
    except Exception as e:
        log.warning("Failed to make blob public (%s): %s — URL may not be accessible", name, e)
    log.info("Archive uploaded → gs://%s/%s", bucket.name, name)
    return blob.public_url


def get_archive_url(archive_name: str) -> str | None:
    """Get the public URL for an archive already in Cloud Storage."""
    bucket = _get_bucket()
    name = _ARCHIVE_PREFIX + archive_name
    blob = bucket.blob(name)
    if blob.exists():
        return blob.public_url
    log.warning("Archive not found: %s", name)
    return None


def cleanup_old_archives(keep_name: str | None = None) -> int:
    """Delete all archives except *keep_name*. Returns count deleted.

    Only the latest run's archive is retained for the download link.
    """
    bucket = _get_bucket()
    keep_blob = (_ARCHIVE_PREFIX + keep_name) if keep_name else None
    deleted = 0
    for blob in bucket.list_blobs(prefix=_ARCHIVE_PREFIX):
        if blob.name != keep_blob:
            blob.delete()
            log.info("Deleted old archive: %s", blob.name)
            deleted += 1
    log.info("Archive cleanup: deleted %d old blobs (kept %s)", deleted, keep_name or "none")
    return deleted


# ── CLI interface ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Firebase storage operations')
    sub = parser.add_subparsers(dest='command', required=True)

    # download-summary
    p = sub.add_parser('download-summary')
    p.add_argument('--output', required=True, help='Output JSON file path')

    # upload-summary
    p = sub.add_parser('upload-summary')
    p.add_argument('--input', required=True, help='Input JSON file path')

    # download-accuracy-log
    p = sub.add_parser('download-accuracy-log')
    p.add_argument('--output', required=True, help='Output JSON file path')

    # upload-accuracy-log
    p = sub.add_parser('upload-accuracy-log')
    p.add_argument('--input', required=True, help='Input JSON file path')

    # download-wrf-spots
    p = sub.add_parser('download-wrf-spots')
    p.add_argument('--output', required=True, help='Output JSON file path')

    # upload-wrf-spots
    p = sub.add_parser('upload-wrf-spots')
    p.add_argument('--input', required=True, help='Input JSON file path')

    # upload-archive
    p = sub.add_parser('upload-archive')
    p.add_argument('--input', required=True, help='Path to .tar.gz archive')

    # get-archive-url
    p = sub.add_parser('get-archive-url')
    p.add_argument('--name', required=True, help='Archive filename')

    # cleanup-archives
    p = sub.add_parser('cleanup-archives')
    p.add_argument('--keep', default=None, help='Archive filename to keep (delete all others)')

    args = parser.parse_args()

    if not _check_configured():
        log.warning("Firebase not configured — exiting")
        sys.exit(0)

    if args.command == 'download-summary':
        data = download_summary()
        if data:
            Path(args.output).write_text(json.dumps(data, indent=2))
            log.info("Summary written to %s", args.output)
        else:
            log.info("No previous summary found in Firestore")

    elif args.command == 'upload-summary':
        try:
            data = json.loads(Path(args.input).read_text())
        except (json.JSONDecodeError, OSError) as e:
            log.error("Failed to read summary file %s: %s", args.input, e)
            sys.exit(1)
        upload_summary(data)

    elif args.command == 'download-accuracy-log':
        entries = download_accuracy_log()
        if entries:
            Path(args.output).write_text(json.dumps(entries, indent=2))
            log.info("Accuracy log written to %s (%d entries)", args.output, len(entries))
        else:
            log.info("No accuracy log found in Firestore")

    elif args.command == 'upload-accuracy-log':
        try:
            entries = json.loads(Path(args.input).read_text())
        except (json.JSONDecodeError, OSError) as e:
            log.error("Failed to read accuracy log file %s: %s", args.input, e)
            sys.exit(1)
        upload_accuracy_log(entries)

    elif args.command == 'download-wrf-spots':
        data = download_wrf_spots()
        if data:
            Path(args.output).write_text(json.dumps(data, indent=2))
            log.info("WRF spots written to %s", args.output)
        else:
            log.info("No WRF spots data found in Firestore")

    elif args.command == 'upload-wrf-spots':
        try:
            data = json.loads(Path(args.input).read_text())
        except (json.JSONDecodeError, OSError) as e:
            log.error("Failed to read WRF spots file %s: %s", args.input, e)
            sys.exit(1)
        upload_wrf_spots(data)

    elif args.command == 'upload-archive':
        url = upload_archive(args.input)
        if url:
            print(url)

    elif args.command == 'get-archive-url':
        url = get_archive_url(args.name)
        if url:
            print(url)

    elif args.command == 'cleanup-archives':
        cleanup_old_archives(args.keep)


if __name__ == '__main__':
    setup_logging()
    main()
