"""Tests for accuracy_track.py."""


from accuracy_track import (
    compute_accuracy,
    _circular_diff,
    _circular_mae,
    _fh_bin,
    _compute_buoy_verification,
    _compute_tide_accuracy,
    _write_to_firestore,
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

    def test_buoy_verification(self):
        """CWA buoy observation should produce buoy_verification in metrics."""
        vt = '2026-03-22T06:00:00+00:00'
        forecast = [{'valid_utc': vt, 'temp_c': 20.0, 'wind_kt': 10.0, 'fh': 6}]
        obs = {'hourly': {'time': ['2026-03-22T06:00'], 'temperature_2m': [20.0],
                          'wind_speed_10m': [10.0], 'wind_direction_10m': [180],
                          'precipitation': [0], 'pressure_msl': [1013]}}
        wave_forecast = [{'valid_utc': vt, 'wave_height': 1.5, 'wave_period': 10.0,
                          'wave_direction': 90.0}]
        cwa_buoy = {
            'buoy_id': '46694A',
            'obs_time': '2026-03-22T06:30:00+00:00',
            'wave_height_m': 1.2,
            'wave_period_s': 8.5,
            'wave_dir': 85.0,
        }
        m = compute_accuracy(forecast, obs, wave_forecast, None, cwa_buoy=cwa_buoy)
        assert m is not None
        assert 'buoy_verification' in m
        bv = m['buoy_verification']
        assert bv['buoy_id'] == '46694A'
        assert bv['hs_obs_m'] == 1.2
        assert bv['hs_fc_m'] == 1.5
        assert bv['hs_error_m'] == 0.3


class TestBuoyVerification:
    def test_basic_comparison(self):
        wave_fc = [{'valid_utc': '2026-03-22T06:00:00+00:00',
                     'wave_height': 1.5, 'wave_period': 10.0, 'wave_direction': 90.0}]
        buoy = {
            'obs_time': '2026-03-22T06:00:00+00:00',
            'wave_height_m': 1.2,
            'wave_period_s': 9.0,
            'wave_dir': 85.0,
        }
        result = _compute_buoy_verification(wave_fc, buoy)
        assert result is not None
        assert result['hs_error_m'] == 0.3
        assert result['tp_error_s'] == 1.0
        assert result['dir_error'] == 5.0

    def test_no_buoy_time(self):
        result = _compute_buoy_verification(
            [{'valid_utc': '2026-03-22T06:00:00+00:00', 'wave_height': 1.5}],
            {'wave_height_m': 1.2}  # no obs_time
        )
        assert result is None

    def test_no_buoy_hs(self):
        result = _compute_buoy_verification(
            [{'valid_utc': '2026-03-22T06:00:00+00:00', 'wave_height': 1.5}],
            {'obs_time': '2026-03-22T06:00:00+00:00'}  # no wave_height_m
        )
        assert result is None

    def test_too_far_in_time(self):
        """Buoy obs >3h from nearest forecast should return None."""
        wave_fc = [{'valid_utc': '2026-03-22T06:00:00+00:00', 'wave_height': 1.5}]
        buoy = {
            'obs_time': '2026-03-22T12:00:00+00:00',  # 6h away
            'wave_height_m': 1.2,
        }
        result = _compute_buoy_verification(wave_fc, buoy)
        assert result is None

    def test_finds_closest_timestep(self):
        wave_fc = [
            {'valid_utc': '2026-03-22T00:00:00+00:00', 'wave_height': 2.0},
            {'valid_utc': '2026-03-22T06:00:00+00:00', 'wave_height': 1.5},
            {'valid_utc': '2026-03-22T12:00:00+00:00', 'wave_height': 1.0},
        ]
        buoy = {
            'obs_time': '2026-03-22T05:30:00+00:00',
            'wave_height_m': 1.3,
        }
        result = _compute_buoy_verification(wave_fc, buoy)
        assert result is not None
        assert result['hs_fc_m'] == 1.5  # should match the 06:00 timestep


class TestComputeTideAccuracy:
    def test_basic_comparison(self):
        obs = {
            'station_id': 'C4B01',
            'obs_time': '2026-03-22T06:00:00+00:00',
            'tide_height_m': 0.55,
        }
        result = _compute_tide_accuracy(obs, None)
        assert result is not None
        assert result['obs_height_m'] == 0.55
        assert 'harmonic_height_m' in result
        assert 'harmonic_error_m' in result
        assert result['station_id'] == 'C4B01'

    def test_with_cwa_forecast(self):
        obs = {
            'station_id': 'C4B01',
            'obs_time': '2026-03-22T09:00:00+00:00',
            'tide_height_m': 0.45,
        }
        cwa_fc = [
            {"time_utc": "2026-03-22T06:00:00+00:00", "height_m": 0.85, "type": "high"},
            {"time_utc": "2026-03-22T12:15:00+00:00", "height_m": 0.10, "type": "low"},
        ]
        result = _compute_tide_accuracy(obs, cwa_fc)
        assert result is not None
        assert 'anchored_height_m' in result
        assert 'anchored_error_m' in result

    def test_returns_none_without_obs(self):
        assert _compute_tide_accuracy(None, None) is None
        assert _compute_tide_accuracy({}, None) is None
        assert _compute_tide_accuracy({'tide_height_m': None}, None) is None

    def test_returns_none_without_obs_time(self):
        obs = {'tide_height_m': 0.5}
        assert _compute_tide_accuracy(obs, None) is None


# ── Firestore stub ────────────────────────────────────────────────────────────

class TestWriteToFirestore:
    def test_skips_silently_without_env_var(self, monkeypatch):
        """Should do nothing when FIREBASE_PROJECT is not set."""
        monkeypatch.delenv('FIREBASE_PROJECT', raising=False)
        # Should not raise
        _write_to_firestore({'init_utc': '2026-01-01T00:00:00+00:00', 'model_id': 'WRF'})

    def test_warns_without_firebase_admin(self, monkeypatch):
        """Should log warning when firebase-admin not installed."""
        monkeypatch.setenv('FIREBASE_PROJECT', 'test-project')
        # firebase_admin may or may not be installed; function should not crash
        _write_to_firestore({'init_utc': '2026-01-01T00:00:00+00:00', 'model_id': 'WRF'})
