"""Tests for config.py shared constants and utilities."""

import json
import os
import tempfile
import urllib.error
from unittest.mock import patch, MagicMock

from datetime import datetime, timezone

from config import (
    KEELUNG_LAT, KEELUNG_LON, COMPASS_NAMES, deg_to_compass,
    norm_utc, setup_logging, sail_rating,
    fetch_json, load_json_file,
    SPOT_COORDS, SPOT_COUNTY,
    sunrise_sunset, is_daylight,
)


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


# ── sail_rating ──────────────────────────────────────────────────────────

class TestSailRating:
    def test_good_conditions(self):
        r = sail_rating(10, 15, 0.5, 2)
        assert '🟢' in r['label']
        assert r['emoji'] == '🟢'
        assert r['max_w'] == 10

    def test_marginal_wind(self):
        r = sail_rating(25, 30, 1.0, 5)
        assert 'Marginal' in r['label']
        assert r['emoji'] == '🟡'

    def test_marginal_rain(self):
        r = sail_rating(10, 15, 0.5, 20)
        assert 'Marginal' in r['label']

    def test_marginal_waves(self):
        r = sail_rating(10, 15, 1.8, 2)
        assert 'Marginal' in r['label']

    def test_nogo_gust(self):
        r = sail_rating(20, 40, 0.5, 0)
        assert r['label'] == '🔴 No-go'
        assert r['emoji'] == '🔴'

    def test_nogo_wind(self):
        r = sail_rating(30, 20, 0.5, 0)
        assert 'No-go' in r['label']

    def test_nogo_waves(self):
        r = sail_rating(10, 15, 3.0, 0)
        assert 'No-go' in r['label']

    def test_none_values(self):
        r = sail_rating(None, None, None, 0)
        assert '🟢' in r['label']

    def test_returns_dict_keys(self):
        r = sail_rating(10, 15, 0.5, 2)
        for key in ('label', 'emoji', 'bg', 'col', 'max_w', 'max_g', 'max_hs'):
            assert key in r


# ── fetch_json ─────────────────────────────────────────────────────────

class TestFetchJson:
    @patch('config.urllib.request.urlopen')
    def test_returns_parsed_json(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = b'{"key": "value"}'
        mock_urlopen.return_value = mock_resp
        result = fetch_json("https://example.com/api", label="test")
        assert result == {"key": "value"}

    @patch('config.urllib.request.urlopen')
    def test_returns_none_on_failure(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.URLError("timeout")
        result = fetch_json("https://example.com/api", label="test",
                            retries=1, retry_delay=0)
        assert result is None

    @patch('config.urllib.request.urlopen')
    def test_retries_on_error(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = b'{"ok": true}'
        mock_urlopen.side_effect = [
            urllib.error.URLError("first fail"),
            mock_resp,
        ]
        result = fetch_json("https://example.com/api", label="test",
                            retries=2, retry_delay=0)
        assert result == {"ok": True}
        assert mock_urlopen.call_count == 2


# ── load_json_file ────────────────────────────────────────────────────

class TestLoadJsonFile:
    def test_loads_valid_file(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({"a": 1}, f)
            f.flush()
            path = f.name
        try:
            result = load_json_file(path, "test")
            assert result == {"a": 1}
        finally:
            os.unlink(path)

    def test_returns_none_for_missing_file(self):
        result = load_json_file("/nonexistent/path.json", "test")
        assert result is None

    def test_returns_none_for_invalid_json(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("not json{{{")
            f.flush()
            path = f.name
        try:
            result = load_json_file(path, "test")
            assert result is None
        finally:
            os.unlink(path)


class TestSpotCoords:
    def test_has_at_least_8_entries(self):
        assert len(SPOT_COORDS) >= 8

    def test_keelung_is_first(self):
        assert SPOT_COORDS[0]["id"] == "keelung"

    def test_all_have_required_keys(self):
        for s in SPOT_COORDS:
            assert "id" in s
            assert "lat" in s
            assert "lon" in s

    def test_unique_ids(self):
        ids = [s["id"] for s in SPOT_COORDS]
        assert len(ids) == len(set(ids))

    def test_coordinates_in_taiwan(self):
        for s in SPOT_COORDS:
            assert 21 < s["lat"] < 26, f"{s['id']} lat out of range"
            assert 119 < s["lon"] < 123, f"{s['id']} lon out of range"

    def test_spot_county_covers_original_spots(self):
        """SPOT_COUNTY covers at least the original 8 northern spots."""
        original_ids = {"keelung", "fulong", "greenbay", "jinshan",
                        "daxi", "wushih", "doublelions", "chousui"}
        assert original_ids.issubset(set(SPOT_COUNTY.keys()))

    def test_county_values_valid(self):
        valid = {"基隆市", "新北市", "宜蘭縣"}
        for county in SPOT_COUNTY.values():
            assert county in valid


class TestSunriseSunset:
    def test_summer_keelung(self):
        """Summer solstice — sunrise ~05:05, sunset ~18:45 CST."""
        d = datetime(2026, 6, 21)
        sr_utc, ss_utc = sunrise_sunset(d, KEELUNG_LAT, KEELUNG_LON)
        sr_cst = sr_utc + 8
        ss_cst = ss_utc + 8
        assert 4.8 < sr_cst < 5.5, f"Summer sunrise {sr_cst:.2f} CST"
        assert 18.5 < ss_cst < 19.2, f"Summer sunset {ss_cst:.2f} CST"

    def test_winter_keelung(self):
        """Winter solstice — sunrise ~06:30, sunset ~17:15 CST."""
        d = datetime(2026, 12, 21)
        sr_utc, ss_utc = sunrise_sunset(d, KEELUNG_LAT, KEELUNG_LON)
        sr_cst = sr_utc + 8
        ss_cst = ss_utc + 8
        assert 6.2 < sr_cst < 6.8, f"Winter sunrise {sr_cst:.2f} CST"
        assert 16.8 < ss_cst < 17.5, f"Winter sunset {ss_cst:.2f} CST"

    def test_equinox_roughly_12h_daylight(self):
        """Near equinox, daylight should be ~12 hours."""
        d = datetime(2026, 3, 20)
        sr_utc, ss_utc = sunrise_sunset(d, KEELUNG_LAT, KEELUNG_LON)
        daylight_hours = ss_utc - sr_utc
        assert 11.5 < daylight_hours < 12.5

    def test_returns_floats(self):
        d = datetime(2026, 3, 24)
        sr, ss = sunrise_sunset(d)
        assert isinstance(sr, float)
        assert isinstance(ss, float)
        assert sr < ss  # sunrise before sunset

    def test_sunrise_before_sunset(self):
        """Sunrise should always be before sunset at 25°N."""
        for month in range(1, 13):
            d = datetime(2026, month, 15)
            sr, ss = sunrise_sunset(d, KEELUNG_LAT, KEELUNG_LON)
            assert sr < ss, f"Month {month}: sunrise {sr:.2f} >= sunset {ss:.2f}"


class TestIsDaylight:
    def test_midday_is_daylight(self):
        """Noon UTC (20:00 CST) — should still be daylight in summer."""
        dt = datetime(2026, 6, 21, 10, 0, tzinfo=timezone.utc)  # 18:00 CST
        assert is_daylight(dt) is True

    def test_midnight_utc_is_dark(self):
        """00:00 UTC = 08:00 CST — daylight in summer, but check winter."""
        # 18:00 UTC = 02:00 CST next day — definitely dark
        dt = datetime(2026, 12, 21, 18, 0, tzinfo=timezone.utc)
        assert is_daylight(dt) is False

    def test_margin_extends_window(self):
        """With 30-minute margin, times near sunrise/sunset should count."""
        # Summer sunrise at Keelung ~21:05 UTC (05:05 CST).
        # Use 20:50 UTC (04:50 CST) — dark without margin, light with 30 min
        just_before = datetime(2026, 6, 21, 20, 50, tzinfo=timezone.utc)
        assert is_daylight(just_before, margin_minutes=30) is True
        assert is_daylight(just_before, margin_minutes=0) is False
