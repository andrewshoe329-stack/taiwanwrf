"""Tests for wave_fetch.py helper functions."""


from wave_fetch import process_ecmwf_wave


# ── process_ecmwf_wave ──────────────────────────────────────────────────────

class TestProcessEcmwfWave:
    def test_empty_input(self):
        meta, records = process_ecmwf_wave({})
        assert records == []

    def test_basic_processing(self):
        """Process a minimal hourly marine response."""
        times = [f'2026-03-09T{h:02d}:00' for h in range(7)]
        raw = {
            'hourly': {
                'time': times,
                'wave_height': [1.5] * 7,
                'wave_period': [8.0] * 7,
                'wave_direction': [45.0] * 7,
                'wind_wave_height': [0.5] * 7,
                'wind_wave_period': [4.0] * 7,
                'wind_wave_direction': [90.0] * 7,
                'swell_wave_height': [1.2] * 7,
                'swell_wave_period': [10.0] * 7,
                'swell_wave_direction': [180.0] * 7,
            }
        }
        meta, records = process_ecmwf_wave(raw)
        assert len(records) >= 1
        assert records[0]['wave_height'] == 1.5
        assert records[0]['wave_period'] == 8.0
        assert records[0]['swell_wave_height'] == 1.2
        assert meta['model_id'] == 'ECMWF-WAM'
