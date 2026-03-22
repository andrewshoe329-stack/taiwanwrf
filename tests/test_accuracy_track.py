"""Tests for accuracy_track.py."""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from accuracy_track import compute_accuracy


class TestComputeAccuracy:
    def test_empty_inputs(self):
        assert compute_accuracy([], {}) is None

    def test_no_overlap(self):
        forecast = [{'valid_utc': '2026-03-22T00:00:00+00:00', 'temp_c': 20, 'wind_kt': 10}]
        obs = {'hourly': {'time': ['2026-03-23T00:00'], 'temperature_2m': [21], 'windspeed_10m': [12],
                          'winddirection_10m': [180], 'precipitation': [0]}}
        assert compute_accuracy(forecast, obs) is None

    def test_perfect_forecast(self):
        vt = '2026-03-22T06:00:00+00:00'
        forecast = [{'valid_utc': vt, 'temp_c': 20.0, 'wind_kt': 10.0}]
        obs = {'hourly': {'time': ['2026-03-22T06:00'], 'temperature_2m': [20.0],
                          'windspeed_10m': [10.0], 'winddirection_10m': [180], 'precipitation': [0]}}
        m = compute_accuracy(forecast, obs)
        assert m is not None
        assert m['temp_mae_c'] == 0.0
        assert m['wind_mae_kt'] == 0.0

    def test_nonzero_error(self):
        vt = '2026-03-22T06:00:00+00:00'
        forecast = [{'valid_utc': vt, 'temp_c': 22.0, 'wind_kt': 15.0}]
        obs = {'hourly': {'time': ['2026-03-22T06:00'], 'temperature_2m': [20.0],
                          'windspeed_10m': [10.0], 'winddirection_10m': [180], 'precipitation': [0]}}
        m = compute_accuracy(forecast, obs)
        assert m is not None
        assert m['temp_mae_c'] == 2.0
        assert m['temp_bias_c'] == 2.0
        assert m['wind_mae_kt'] == 5.0

    def test_multiple_records(self):
        records = [
            {'valid_utc': '2026-03-22T00:00:00+00:00', 'temp_c': 20, 'wind_kt': 10},
            {'valid_utc': '2026-03-22T06:00:00+00:00', 'temp_c': 22, 'wind_kt': 12},
        ]
        obs = {'hourly': {
            'time': ['2026-03-22T00:00', '2026-03-22T06:00'],
            'temperature_2m': [19, 23],
            'windspeed_10m': [11, 11],
            'winddirection_10m': [180, 180],
            'precipitation': [0, 0],
        }}
        m = compute_accuracy(records, obs)
        assert m is not None
        assert m['n_compared'] == 2
        # temp errors: +1, -1 → MAE=1.0, bias=0.0
        assert m['temp_mae_c'] == 1.0
        assert m['temp_bias_c'] == 0.0
