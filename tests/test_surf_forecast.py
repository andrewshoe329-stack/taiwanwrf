"""Tests for surf_forecast.py helper functions and rating logic."""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from surf_forecast import (
    deg_diff, compass, dir_quality, _safe_get,
    day_rating, sail_day_rating,
    SPOTS, MIN_SWELL_HEIGHT_M, MAX_SWELL_HEIGHT_M, MAX_WIND_KT,
    LIGHT_WIND_KT, ONSHORE_WIND_KT,
)


# ── _safe_get ────────────────────────────────────────────────────────────────

class TestSafeGet:
    def test_valid_index(self):
        assert _safe_get([10, 20, 30], 1) == 20

    def test_out_of_bounds(self):
        assert _safe_get([10, 20], 5) is None

    def test_none_list(self):
        assert _safe_get(None, 0) is None

    def test_empty_list(self):
        assert _safe_get([], 0) is None

    def test_first_element(self):
        assert _safe_get([42], 0) == 42


# ── deg_diff ─────────────────────────────────────────────────────────────────

class TestDegDiff:
    def test_same_direction(self):
        assert deg_diff(0, 0) == 0

    def test_opposite(self):
        assert deg_diff(0, 180) == 180

    def test_wrap_around(self):
        assert deg_diff(350, 10) == 20

    def test_symmetric(self):
        assert deg_diff(90, 270) == deg_diff(270, 90)

    def test_small_difference(self):
        assert abs(deg_diff(45, 50) - 5) < 1e-9


# ── compass ──────────────────────────────────────────────────────────────────

class TestCompass:
    def test_north(self):
        assert compass(0) == 'N'

    def test_east(self):
        assert compass(90) == 'E'

    def test_south(self):
        assert compass(180) == 'S'

    def test_west(self):
        assert compass(270) == 'W'

    def test_none(self):
        assert compass(None) == '—'

    def test_northeast(self):
        assert compass(45) == 'NE'

    def test_wrap_360(self):
        assert compass(360) == 'N'


# ── dir_quality ──────────────────────────────────────────────────────────────

class TestDirQuality:
    def test_good_match(self):
        assert dir_quality(180, ['S']) == 'good'

    def test_ok_match(self):
        assert dir_quality(210, ['S']) == 'ok'  # 30° off — between 22.5 and 45

    def test_poor_match(self):
        assert dir_quality(0, ['S']) == 'poor'  # 180° off

    def test_none_direction(self):
        assert dir_quality(None, ['S']) == 'unknown'

    def test_multiple_optimal(self):
        assert dir_quality(45, ['N', 'NE', 'E']) == 'good'


# ── day_rating ───────────────────────────────────────────────────────────────

class TestDayRating:
    SPOT = SPOTS[0]  # Fulong

    def test_no_data(self):
        r = day_rating([], self.SPOT)
        assert r['label'] == 'No data'

    def test_flat(self):
        recs = [{'sw_hs': 0.1, 'wind': 5}]
        r = day_rating(recs, self.SPOT)
        assert r['label'] == 'Flat'

    def test_dangerous_swell(self):
        recs = [{'sw_hs': 5.0, 'wind': 10, 'sw_dir': 45, 'w_dir': 180, 'sw_tp': 10}]
        r = day_rating(recs, self.SPOT)
        assert r['label'] == 'Dangerous'

    def test_dangerous_wind(self):
        recs = [{'sw_hs': 1.0, 'wind': 35, 'sw_dir': 45, 'w_dir': 180, 'sw_tp': 10}]
        r = day_rating(recs, self.SPOT)
        assert r['label'] == 'Dangerous'

    def test_good_conditions(self):
        # Good swell from NE, light offshore wind from SW, long period
        recs = [{'sw_hs': 1.5, 'wind': 5, 'sw_dir': 45, 'w_dir': 225, 'sw_tp': 14}]
        r = day_rating(recs, self.SPOT)
        assert r['label'] in ('Firing!', 'Good')


# ── sail_day_rating ──────────────────────────────────────────────────────────

class TestSailDayRating:
    def test_no_data(self):
        r = sail_day_rating([])
        assert r['label'] == '—'

    def test_good_conditions(self):
        recs = [{'wind': 10, 'gust': 15, 'hs': 0.5, 'rain6h': 0}]
        r = sail_day_rating(recs)
        assert 'Good' in r['label']

    def test_nogo_gust(self):
        recs = [{'wind': 20, 'gust': 40, 'hs': 1.0, 'rain6h': 0}]
        r = sail_day_rating(recs)
        assert 'No-go' in r['label']

    def test_nogo_wave(self):
        recs = [{'wind': 10, 'gust': 15, 'hs': 3.0, 'rain6h': 0}]
        r = sail_day_rating(recs)
        assert 'No-go' in r['label']


# ── Constants sanity ─────────────────────────────────────────────────────────

class TestConstants:
    def test_thresholds_ordered(self):
        assert MIN_SWELL_HEIGHT_M < MAX_SWELL_HEIGHT_M
        assert LIGHT_WIND_KT < ONSHORE_WIND_KT < MAX_WIND_KT

    def test_spots_have_required_keys(self):
        for spot in SPOTS:
            assert 'name' in spot
            assert 'lat' in spot
            assert 'lon' in spot
            assert 'opt_wind' in spot
            assert 'opt_swell' in spot
