"""Tests for wrf_analyze.py helper functions."""


from wrf_analyze import (
    deg_to_compass, _wind_arrow, _fmt,
    _temp_bg, _beaufort, _wind_bg, _precip_bg, _cape_bg,
    _wave_height_bg, _wave_period_bg,
    _delta_span, _delta_cell, _wave_dir_str,
    _sail_rating, _condition_emoji,
    _parse_init_time, _daily_summary_html,
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
        assert label == '🔴 No-go'


# ── _condition_emoji ─────────────────────────────────────────────────────────

class TestConditionEmoji:
    def test_returns_string(self):
        result = _condition_emoji(10, 0, 50, 0.5)
        assert isinstance(result, str)
        assert len(result) >= 1

    def test_high_seas(self):
        assert _condition_emoji(10, 0, 50, 4.0) == '🌊'

    def test_thunderstorm_cape(self):
        assert _condition_emoji(10, 0, 600, 0.5) == '⛈️'

    def test_heavy_rain(self):
        assert _condition_emoji(10, 20, 50, 0.5) == '🌧️'

    def test_moderate_rain(self):
        assert _condition_emoji(10, 5, 50, 0.5) == '🌦️'

    def test_gale_gust(self):
        assert _condition_emoji(10, 0, 50, 0.5, 40) == '💨'

    def test_strong_wind(self):
        assert _condition_emoji(30, 0, 50, 0.5) == '💨'

    def test_moderate_wind(self):
        assert _condition_emoji(18, 0, 50, 0.5) == '🌬️'

    def test_fine_weather(self):
        assert _condition_emoji(5, 0, 50, 0.5) == '🌤️'

    def test_all_none(self):
        assert _condition_emoji(None, None, None, None) == '🌤️'

    def test_priority_seas_over_wind(self):
        # High seas should take priority over strong wind
        assert _condition_emoji(30, 0, 50, 4.0) == '🌊'


# ── _daily_summary_html ────────────────────────────────────────────────────

class TestDailySummaryHtml:
    """Tests for the unified day cards HTML generator."""

    def _make_valids(self, date='2026-03-22'):
        """Return 4 valid times (UTC) that map to one CST day."""
        # CST = UTC+8, so UTC 16:00 on 3/21 → CST 00:00 on 3/22
        return [
            f'{date}T{h:02d}:00:00+00:00'
            for h in (0, 6, 12, 18)
        ]

    def _make_wrf(self, valids):
        return {
            vt: {
                'temp_c': 24.0, 'wind_kt': 12.0, 'wind_dir': 45,
                'gust_kt': 18.0, 'precip_mm_6h': 1.0, 'cape': 100,
            }
            for vt in valids
        }

    def _make_ec(self, valids):
        return {
            vt: {
                'temp_c': 23.0, 'wind_kt': 11.0, 'wind_dir': 50,
                'gust_kt': 16.0, 'precip_mm_6h': 0.5, 'cape': 80,
            }
            for vt in valids
        }

    def _make_wave(self, valids):
        return {
            vt: {'wave_height': 1.2, 'wave_period': 10.0, 'wave_direction': 45}
            for vt in valids
        }

    def test_basic_output_has_cards(self):
        valids = self._make_valids()
        html = _daily_summary_html(self._make_wrf(valids), {}, {}, valids)
        assert 'daily-card' in html
        assert 'daily-cards' in html

    def test_empty_valids_returns_empty(self):
        assert _daily_summary_html({}, {}, {}, []) == ''

    def test_wrf_source_tag(self):
        valids = self._make_valids()
        html = _daily_summary_html(self._make_wrf(valids), {}, {}, valids)
        assert 'WRF' in html

    def test_ecmwf_fallback_source_tag(self):
        valids = self._make_valids()
        html = _daily_summary_html({}, self._make_ec(valids), {}, valids)
        assert 'EC' in html

    def test_wave_data_shown(self):
        valids = self._make_valids()
        html = _daily_summary_html(
            self._make_wrf(valids), {}, self._make_wave(valids), valids
        )
        assert 'Hs' in html
        assert '1.2' in html

    def test_wind_display(self):
        valids = self._make_valids()
        html = _daily_summary_html(self._make_wrf(valids), {}, {}, valids)
        assert 'kt' in html
        assert 'NE' in html  # wind_dir=45 → NE

    def test_rain_display(self):
        valids = self._make_valids()
        html = _daily_summary_html(self._make_wrf(valids), {}, {}, valids)
        assert 'mm' in html  # 4 x 1.0mm = 4mm

    def test_dry_day(self):
        valids = self._make_valids()
        wrf = {
            vt: {'temp_c': 24.0, 'wind_kt': 8.0, 'wind_dir': 90,
                 'gust_kt': 12.0, 'precip_mm_6h': 0.0, 'cape': 50}
            for vt in valids
        }
        html = _daily_summary_html(wrf, {}, {}, valids)
        assert 'dry' in html

    def test_surf_planner_integration(self):
        valids = self._make_valids()
        planner = {
            'days': {
                '2026-03-22': {
                    'best_surf': {
                        'spot': 'Fulong', 'label': 'Good',
                        'emoji': '🟢', 'bg': '#0d3320', 'col': '#fff',
                    },
                    'recommendation': {
                        'text': 'Go surf at Fulong', 'bg': '#0d2d1a',
                    },
                }
            }
        }
        html = _daily_summary_html(
            self._make_wrf(valids), {}, {}, valids, surf_planner=planner
        )
        assert 'Fulong' in html
        assert 'surf-pick' in html

    def test_surf_planner_flat(self):
        valids = self._make_valids()
        planner = {
            'days': {
                '2026-03-22': {
                    'best_surf': {
                        'spot': '—', 'label': '—',
                        'emoji': '😴', 'bg': '#1a2236', 'col': '#475569',
                    },
                    'recommendation': {
                        'text': 'Stay home', 'bg': '#3d1515',
                    },
                }
            }
        }
        html = _daily_summary_html(
            self._make_wrf(valids), {}, {}, valids, surf_planner=planner
        )
        assert 'Flat' in html

    def test_tide_data_shown(self):
        valids = self._make_valids()
        tide = {
            'extrema': [
                {'cst': '2026-03-22T06:12:00+08:00', 'type': 'high', 'height_m': 1.2},
                {'cst': '2026-03-22T12:30:00+08:00', 'type': 'low', 'height_m': 0.3},
            ]
        }
        html = _daily_summary_html(
            self._make_wrf(valids), {}, {}, valids, tide_data=tide
        )
        assert '▲' in html
        assert '▼' in html
        assert '1.2m' in html

    def test_multiple_days(self):
        v1 = self._make_valids('2026-03-22')
        v2 = self._make_valids('2026-03-23')
        all_v = v1 + v2
        wrf = self._make_wrf(all_v)
        html = _daily_summary_html(wrf, {}, {}, all_v)
        # Should have two daily cards
        assert html.count('daily-card') >= 2

    def test_cape_badge_shown(self):
        valids = self._make_valids()
        wrf = {
            vt: {'temp_c': 24.0, 'wind_kt': 12.0, 'wind_dir': 45,
                 'gust_kt': 18.0, 'precip_mm_6h': 0.0, 'cape': 600}
            for vt in valids
        }
        html = _daily_summary_html(wrf, {}, {}, valids)
        assert 'CAPE' in html
        assert '⚡' in html
