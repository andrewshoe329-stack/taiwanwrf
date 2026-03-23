"""Tests for accuracy_track.py."""


from accuracy_track import (
    compute_accuracy,
    _circular_diff,
    _circular_mae,
    _fh_bin,
)


class TestCircularDiff:
    def test_same_direction(self):
        assert _circular_diff(90, 90) == 0

    def test_small_positive(self):
        assert _circular_diff(100, 90) == 10

    def test_small_negative(self):
        assert _circular_diff(80, 90) == -10

    def test_wrap_around(self):
        # 10° vs 350° should be +20, not -340
        assert _circular_diff(10, 350) == 20

    def test_wrap_around_negative(self):
        # 350° vs 10° should be -20
        assert _circular_diff(350, 10) == -20

    def test_opposite(self):
        assert abs(_circular_diff(0, 180)) == 180


class TestCircularMAE:
    def test_empty(self):
        assert _circular_mae([]) is None

    def test_zero(self):
        assert _circular_mae([0, 0, 0]) == 0.0

    def test_symmetric(self):
        # errors of +10 and -10 should give MAE of 10
        assert _circular_mae([10, -10]) == 10.0

    def test_small_values(self):
        assert _circular_mae([20, -20]) == 20.0


class TestFHBin:
    def test_zero(self):
        assert _fh_bin(0) == "0-24h"

    def test_12(self):
        assert _fh_bin(12) == "0-24h"

    def test_24(self):
        assert _fh_bin(24) == "24-48h"

    def test_48(self):
        assert _fh_bin(48) == "48-72h"

    def test_72(self):
        assert _fh_bin(72) == "72h+"

    def test_168(self):
        assert _fh_bin(168) == "72h+"


class TestComputeAccuracy:
    def test_empty_inputs(self):
        assert compute_accuracy([], {}) is None

    def test_no_overlap(self):
        forecast = [{'valid_utc': '2026-03-22T00:00:00+00:00', 'temp_c': 20,
                      'wind_kt': 10, 'fh': 0}]
        obs = {'hourly': {'time': ['2026-03-23T00:00'], 'temperature_2m': [21],
                          'wind_speed_10m': [12], 'wind_direction_10m': [180],
                          'precipitation': [0], 'pressure_msl': [1013]}}
        assert compute_accuracy(forecast, obs) is None

    def test_perfect_forecast(self):
        vt = '2026-03-22T06:00:00+00:00'
        forecast = [{'valid_utc': vt, 'temp_c': 20.0, 'wind_kt': 10.0,
                      'wind_dir': 180.0, 'mslp_hpa': 1013.0, 'fh': 6}]
        obs = {'hourly': {'time': ['2026-03-22T06:00'], 'temperature_2m': [20.0],
                          'wind_speed_10m': [10.0], 'wind_direction_10m': [180.0],
                          'precipitation': [0], 'pressure_msl': [1013.0]}}
        m = compute_accuracy(forecast, obs)
        assert m is not None
        assert m['overall']['temp_mae_c'] == 0.0
        assert m['overall']['wind_mae_kt'] == 0.0
        assert m['overall']['wdir_mae_deg'] == 0.0
        assert m['overall']['mslp_mae_hpa'] == 0.0

    def test_nonzero_error(self):
        vt = '2026-03-22T06:00:00+00:00'
        forecast = [{'valid_utc': vt, 'temp_c': 22.0, 'wind_kt': 15.0,
                      'wind_dir': 200.0, 'mslp_hpa': 1015.0, 'fh': 6}]
        obs = {'hourly': {'time': ['2026-03-22T06:00'], 'temperature_2m': [20.0],
                          'wind_speed_10m': [10.0], 'wind_direction_10m': [180.0],
                          'precipitation': [0], 'pressure_msl': [1013.0]}}
        m = compute_accuracy(forecast, obs)
        assert m is not None
        assert m['overall']['temp_mae_c'] == 2.0
        assert m['overall']['temp_bias_c'] == 2.0
        assert m['overall']['wind_mae_kt'] == 5.0
        assert m['overall']['wdir_mae_deg'] == 20.0
        assert m['overall']['mslp_mae_hpa'] == 2.0
        assert m['overall']['mslp_bias_hpa'] == 2.0

    def test_multiple_records(self):
        records = [
            {'valid_utc': '2026-03-22T00:00:00+00:00', 'temp_c': 20,
             'wind_kt': 10, 'fh': 0},
            {'valid_utc': '2026-03-22T06:00:00+00:00', 'temp_c': 22,
             'wind_kt': 12, 'fh': 6},
        ]
        obs = {'hourly': {
            'time': ['2026-03-22T00:00', '2026-03-22T06:00'],
            'temperature_2m': [19, 23],
            'wind_speed_10m': [11, 11],
            'wind_direction_10m': [180, 180],
            'precipitation': [0, 0],
            'pressure_msl': [1013, 1013],
        }}
        m = compute_accuracy(records, obs)
        assert m is not None
        assert m['overall']['n_compared'] == 2
        # temp errors: +1, -1 → MAE=1.0, bias=0.0
        assert m['overall']['temp_mae_c'] == 1.0
        assert m['overall']['temp_bias_c'] == 0.0

    def test_forecast_hour_binning(self):
        records = [
            {'valid_utc': '2026-03-22T00:00:00+00:00', 'temp_c': 20,
             'wind_kt': 10, 'fh': 6},
            {'valid_utc': '2026-03-22T06:00:00+00:00', 'temp_c': 22,
             'wind_kt': 12, 'fh': 30},
        ]
        obs = {'hourly': {
            'time': ['2026-03-22T00:00', '2026-03-22T06:00'],
            'temperature_2m': [19, 23],
            'wind_speed_10m': [11, 11],
            'wind_direction_10m': [180, 180],
            'precipitation': [0, 0],
            'pressure_msl': [1013, 1013],
        }}
        m = compute_accuracy(records, obs)
        assert m is not None
        assert '0-24h' in m['by_horizon']
        assert '24-48h' in m['by_horizon']
        assert m['by_horizon']['0-24h']['n'] == 1
        assert m['by_horizon']['24-48h']['n'] == 1
        assert m['by_horizon']['0-24h']['temp_mae'] == 1.0
        assert m['by_horizon']['24-48h']['temp_mae'] == 1.0

    def test_wind_direction_wrap_around(self):
        vt = '2026-03-22T06:00:00+00:00'
        forecast = [{'valid_utc': vt, 'temp_c': 20.0, 'wind_kt': 10.0,
                      'wind_dir': 5.0, 'fh': 6}]
        obs = {'hourly': {'time': ['2026-03-22T06:00'], 'temperature_2m': [20.0],
                          'wind_speed_10m': [10.0], 'wind_direction_10m': [355.0],
                          'precipitation': [0], 'pressure_msl': [1013]}}
        m = compute_accuracy(forecast, obs)
        assert m is not None
        assert m['overall']['wdir_mae_deg'] == 10.0

    def test_wave_accuracy(self):
        vt = '2026-03-22T06:00:00+00:00'
        wave_forecast = [{'valid_utc': vt, 'hs': 1.5, 'sw_tp': 10.0, 'sw_dir': 90.0}]
        wave_obs = {'hourly': {
            'time': ['2026-03-22T06:00'],
            'wave_height': [1.2],
            'wave_period': [9.0],
            'wave_direction': [85.0],
        }}
        # Need at least temp/wind for overall to not be None
        forecast = [{'valid_utc': vt, 'temp_c': 20.0, 'wind_kt': 10.0, 'fh': 6}]
        obs = {'hourly': {'time': ['2026-03-22T06:00'], 'temperature_2m': [20.0],
                          'wind_speed_10m': [10.0], 'wind_direction_10m': [180],
                          'precipitation': [0], 'pressure_msl': [1013]}}
        m = compute_accuracy(forecast, obs, wave_forecast, wave_obs)
        assert m is not None
        assert 'wave' in m
        assert m['wave']['hs_mae_m'] == 0.3
        assert m['wave']['tp_mae_s'] == 1.0
        assert m['wave']['wdir_mae_deg'] == 5.0
