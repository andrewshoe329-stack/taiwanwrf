"""Tests for config.py shared constants and utilities."""

from config import KEELUNG_LAT, KEELUNG_LON, COMPASS_NAMES, deg_to_compass, norm_utc, setup_logging


def test_keelung_coordinates_in_range():
    """Keelung is in northern Taiwan — lat ~25°N, lon ~121°E."""
    assert 24.0 < KEELUNG_LAT < 26.0
    assert 120.0 < KEELUNG_LON < 123.0


def test_setup_logging_does_not_raise():
    setup_logging()


# ── deg_to_compass ────────────────────────────────────────────────────────

class TestDegToCompass:
    def test_cardinal_directions(self):
        assert deg_to_compass(0) == 'N'
        assert deg_to_compass(90) == 'E'
        assert deg_to_compass(180) == 'S'
        assert deg_to_compass(270) == 'W'

    def test_intercardinal(self):
        assert deg_to_compass(45) == 'NE'
        assert deg_to_compass(135) == 'SE'
        assert deg_to_compass(225) == 'SW'
        assert deg_to_compass(315) == 'NW'

    def test_wrap_360(self):
        assert deg_to_compass(360) == 'N'

    def test_none_returns_dash(self):
        assert deg_to_compass(None) == '—'

    def test_all_16_points(self):
        """Each 22.5° increment should map to a unique compass name."""
        results = [deg_to_compass(i * 22.5) for i in range(16)]
        assert results == list(COMPASS_NAMES)


# ── norm_utc ──────────────────────────────────────────────────────────────

class TestNormUtc:
    def test_bare_datetime_16_chars(self):
        assert norm_utc('2026-03-09T06:00') == '2026-03-09T06:00:00+00:00'

    def test_with_seconds_19_chars(self):
        assert norm_utc('2026-03-09T06:00:00') == '2026-03-09T06:00:00+00:00'

    def test_already_normalized(self):
        result = norm_utc('2026-03-09T06:00:00+00:00')
        assert result == '2026-03-09T06:00:00+00:00'

    def test_strips_whitespace(self):
        assert norm_utc('  2026-03-09T06:00  ') == '2026-03-09T06:00:00+00:00'

    def test_midnight(self):
        assert norm_utc('2026-01-01T00:00') == '2026-01-01T00:00:00+00:00'

    def test_z_suffix(self):
        assert norm_utc('2026-03-22T06:00:00Z') == '2026-03-22T06:00:00+00:00'

    def test_z_suffix_no_seconds(self):
        assert norm_utc('2026-03-22T06:00Z') == '2026-03-22T06:00:00+00:00'
