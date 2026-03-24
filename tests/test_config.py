"""Tests for config.py shared constants and utilities."""

import json
import os
import tempfile
import urllib.error
from unittest.mock import patch, MagicMock

from config import (
    KEELUNG_LAT, KEELUNG_LON, COMPASS_NAMES, deg_to_compass,
    norm_utc, setup_logging, sail_rating,
    fetch_json, load_json_file,
    SPOT_COORDS, SPOT_COUNTY,
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
    def test_has_8_entries(self):
        assert len(SPOT_COORDS) == 8

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
            assert 24 < s["lat"] < 26, f"{s['id']} lat out of range"
            assert 121 < s["lon"] < 123, f"{s['id']} lon out of range"

    def test_spot_county_covers_all(self):
        spot_ids = {s["id"] for s in SPOT_COORDS}
        assert set(SPOT_COUNTY.keys()) == spot_ids

    def test_county_values_valid(self):
        valid = {"基隆市", "新北市", "宜蘭縣"}
        for county in SPOT_COUNTY.values():
            assert county in valid
