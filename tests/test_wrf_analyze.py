"""Tests for wrf_analyze.py helper functions."""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from wrf_analyze import (
    deg_to_compass, _wind_arrow, _fmt,
    _temp_bg, _beaufort, _wind_bg, _precip_bg, _cape_bg,
    _wave_height_bg, _wave_period_bg,
    _delta_span, _delta_cell, _wave_dir_str,
    _sail_rating, _condition_emoji,
    _parse_init_time,
)


# ── deg_to_compass ───────────────────────────────────────────────────────────

class TestDegToCompass:
    def test_north(self):
        assert deg_to_compass(0) == 'N'

    def test_east(self):
        assert deg_to_compass(90) == 'E'

    def test_south(self):
        assert deg_to_compass(180) == 'S'

    def test_west(self):
        assert deg_to_compass(270) == 'W'

    def test_northeast(self):
        assert deg_to_compass(45) == 'NE'

    def test_wrap_360(self):
        assert deg_to_compass(360) == 'N'


# ── _wind_arrow ──────────────────────────────────────────────────────────────

class TestWindArrow:
    def test_north_blows_south(self):
        assert _wind_arrow(0) == '↓'

    def test_east_blows_west(self):
        assert _wind_arrow(90) == '←'

    def test_south_blows_north(self):
        assert _wind_arrow(180) == '↑'

    def test_west_blows_east(self):
        assert _wind_arrow(270) == '→'


# ── _fmt ─────────────────────────────────────────────────────────────────────

class TestFmt:
    def test_format_float(self):
        assert _fmt(12.345) == '12.3'

    def test_format_with_unit(self):
        assert _fmt(12.3, unit='kt') == '12.3kt'

    def test_none(self):
        assert _fmt(None) == '—'

    def test_integer_format(self):
        assert _fmt(12.6, fmt='.0f') == '13'


# ── Background color functions ───────────────────────────────────────────────

class TestBackgroundColors:
    def test_temp_bg_none(self):
        assert _temp_bg(None) == '#1e293b'

    def test_temp_bg_cold(self):
        assert _temp_bg(5) == '#1a3654'

    def test_temp_bg_hot(self):
        assert _temp_bg(35) == '#3d1515'

    def test_wind_bg_none(self):
        assert _wind_bg(None) == '#1e293b'

    def test_wind_bg_light(self):
        assert _wind_bg(5) == '#0d2d1a'

    def test_wind_bg_gale(self):
        assert _wind_bg(40) == '#3d1515'

    def test_precip_bg_none(self):
        assert _precip_bg(None) == '#1e293b'

    def test_precip_bg_dry(self):
        assert _precip_bg(0) == '#1e293b'

    def test_cape_bg_none(self):
        assert _cape_bg(None) == '#1e293b'

    def test_cape_bg_stable(self):
        assert _cape_bg(50) == '#0d2d1a'

    def test_wave_height_bg_none(self):
        assert _wave_height_bg(None) == '#1e293b'

    def test_wave_height_bg_calm(self):
        assert _wave_height_bg(0.1) == '#0d2d1a'

    def test_wave_period_bg_none(self):
        assert _wave_period_bg(None) == '#1e293b'

    def test_wave_period_bg_long(self):
        assert _wave_period_bg(15) == '#1a3654'


# ── _beaufort ────────────────────────────────────────────────────────────────

class TestBeaufort:
    def test_calm(self):
        assert _beaufort(0) == 0

    def test_none(self):
        assert _beaufort(None) == 0

    def test_moderate_breeze(self):
        assert _beaufort(15) == 4

    def test_gale(self):
        assert _beaufort(35) == 8

    def test_hurricane(self):
        assert _beaufort(70) == 12


# ── _delta_span ──────────────────────────────────────────────────────────────

class TestDeltaSpan:
    def test_both_none(self):
        assert _delta_span(None, None) == ''

    def test_no_change(self):
        assert _delta_span(10.0, 10.0) == ''

    def test_positive_change(self):
        result = _delta_span(15.0, 10.0)
        assert '+5.0' in result

    def test_negative_change(self):
        result = _delta_span(10.0, 15.0)
        assert '-5.0' in result


# ── _delta_cell ──────────────────────────────────────────────────────────────

class TestDeltaCell:
    def test_none(self):
        result = _delta_cell(None, 2.0)
        assert '—' in result

    def test_small_difference(self):
        result = _delta_cell(0.5, 2.0)
        assert '#0d2d1a' in result  # green (dark theme)

    def test_large_difference(self):
        result = _delta_cell(5.0, 2.0)
        assert '#3d1515' in result  # red (dark theme)


# ── _wave_dir_str ────────────────────────────────────────────────────────────

class TestWaveDirStr:
    def test_none(self):
        assert _wave_dir_str(None) == '—'

    def test_north(self):
        assert _wave_dir_str(0) == 'N'

    def test_south(self):
        assert _wave_dir_str(180) == 'S'


# ── _parse_init_time ────────────────────────────────────────────────────────

class TestParseInitTime:
    def test_valid_dirname(self):
        dt = _parse_init_time('M-A0064_20260309_00UTC')
        assert dt is not None
        assert dt.year == 2026
        assert dt.month == 3
        assert dt.day == 9
        assert dt.hour == 0

    def test_invalid_dirname(self):
        assert _parse_init_time('random_dir') is None


# ── _sail_rating ─────────────────────────────────────────────────────────────

class TestSailRating:
    def test_good_conditions(self):
        label, bg = _sail_rating(10, 15, 0.5, 2)
        assert 'Good' in label

    def test_marginal_wind(self):
        label, bg = _sail_rating(25, 30, 1.0, 5)
        assert 'Marginal' in label

    def test_nogo_gust(self):
        label, bg = _sail_rating(20, 40, 0.5, 0)
        assert 'No-go' in label or 'No go' in label


# ── _condition_emoji ─────────────────────────────────────────────────────────

class TestConditionEmoji:
    def test_returns_string(self):
        result = _condition_emoji(10, 0, 50, 0.5)
        assert isinstance(result, str)
        assert len(result) >= 1
