"""Tests for ecmwf_fetch.py helper functions."""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from ecmwf_fetch import _norm_utc, process


# ── _norm_utc ────────────────────────────────────────────────────────────────

class TestNormUtc:
    def test_bare_datetime(self):
        assert _norm_utc('2026-03-09T06:00') == '2026-03-09T06:00:00+00:00'

    def test_with_seconds(self):
        assert _norm_utc('2026-03-09T06:00:00') == '2026-03-09T06:00:00+00:00'

    def test_already_normalized(self):
        result = _norm_utc('2026-03-09T06:00:00+00:00')
        assert result == '2026-03-09T06:00:00+00:00'

    def test_strips_whitespace(self):
        assert _norm_utc('  2026-03-09T06:00  ') == '2026-03-09T06:00:00+00:00'


# ── process ──────────────────────────────────────────────────────────────────

class TestProcess:
    def test_empty_input(self):
        meta, records = process({})
        assert records == []

    def test_empty_hourly(self):
        meta, records = process({'hourly': {}})
        assert records == []

    def test_basic_processing(self):
        """Process a minimal hourly response (12 hours → 2 six-hourly records)."""
        times = [f'2026-03-09T{h:02d}:00' for h in range(13)]
        raw = {
            'hourly': {
                'time': times,
                'temperature_2m': [20.0] * 13,
                'windspeed_10m': [10.0] * 13,
                'winddirection_10m': [180.0] * 13,
                'windgusts_10m': [15.0] * 13,
                'precipitation': [0.0] * 13,
                'cloudcover': [50.0] * 13,
                'pressure_msl': [1013.0] * 13,
                'visibility': [10000.0] * 13,
                'cape': [100.0] * 13,
            }
        }
        meta, records = process(raw)
        assert len(records) >= 2
        assert records[0]['temp_c'] == 20.0
        assert records[0]['wind_kt'] == 10.0
        assert records[0]['wind_dir'] == 180.0
        assert meta['model_id'] == 'ECMWF-IFS-0.25'

    def test_gfs_backfill(self):
        """Null gusts in ECMWF should be filled from GFS."""
        times = [f'2026-03-09T{h:02d}:00' for h in range(7)]
        raw = {
            'hourly': {
                'time': times,
                'temperature_2m': [20.0] * 7,
                'windspeed_10m': [10.0] * 7,
                'winddirection_10m': [180.0] * 7,
                'windgusts_10m': [None] * 7,
                'precipitation': [0.0] * 7,
                'cloudcover': [50.0] * 7,
                'pressure_msl': [1013.0] * 7,
                'visibility': [None] * 7,
                'cape': [100.0] * 7,
            }
        }
        gfs = {
            'hourly': {
                'time': times,
                'windgusts_10m': [25.0] * 7,
                'visibility': [5000.0] * 7,
            }
        }
        meta, records = process(raw, gfs)
        assert len(records) >= 1
        assert records[0]['gust_kt'] == 25.0
        assert records[0]['vis_km'] == 5.0
