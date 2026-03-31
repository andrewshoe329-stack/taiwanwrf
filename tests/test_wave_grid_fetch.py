"""Tests for wave_grid_fetch.py — grid generation and data assembly."""

from wave_grid_fetch import make_grid, fetch_wave_grid
from unittest.mock import patch, MagicMock


class TestMakeGrid:
    """make_grid produces correct lat/lon arrays."""

    def test_basic_grid(self):
        lats, lons = make_grid(24.0, 25.0, 121.0, 122.0, 0.5)
        assert lats == [24.0, 24.5, 25.0]
        assert lons == [121.0, 121.5, 122.0]

    def test_single_point(self):
        lats, lons = make_grid(25.0, 25.0, 121.0, 121.0, 0.25)
        assert lats == [25.0]
        assert lons == [121.0]

    def test_grid_ordering(self):
        """Latitudes and longitudes should be in ascending order."""
        lats, lons = make_grid(24.0, 26.0, 120.0, 123.0, 0.25)
        assert lats == sorted(lats)
        assert lons == sorted(lons)
        assert lats[0] == 24.0
        assert lats[-1] == 26.0
        assert lons[0] == 120.0
        assert lons[-1] == 123.0

    def test_default_resolution(self):
        """Without explicit resolution, uses module default (0.1)."""
        lats, lons = make_grid(25.0, 25.2, 121.0, 121.2)
        assert len(lats) == 3  # 25.0, 25.1, 25.2
        assert len(lons) == 3

    def test_fractional_resolution(self):
        lats, lons = make_grid(24.0, 24.3, 121.0, 121.3, 0.1)
        assert len(lats) == 4  # 24.0, 24.1, 24.2, 24.3
        assert len(lons) == 4

    def test_rounding(self):
        """Grid values should be rounded to avoid float drift."""
        lats, lons = make_grid(24.0, 24.3, 121.0, 121.3, 0.1)
        for lat in lats:
            assert lat == round(lat, 6)
        for lon in lons:
            assert lon == round(lon, 6)


class TestFetchWaveGrid:
    """fetch_wave_grid assembles grid data from API responses."""

    def _mock_hourly(self, n_times=3):
        """Build a fake Open-Meteo hourly response."""
        return {
            "time": [f"2025-01-01T{h:02d}:00" for h in range(n_times)],
            "wave_height": [1.0 + i * 0.1 for i in range(n_times)],
            "swell_wave_height": [0.8 + i * 0.1 for i in range(n_times)],
            "swell_wave_direction": [90.0] * n_times,
            "swell_wave_period": [10.0] * n_times,
        }

    @patch("wave_grid_fetch._fetch_point")
    def test_all_points_success(self, mock_fetch):
        """All grid points succeed — produces correct structure."""
        lats = [24.0, 24.5]
        lons = [121.0, 121.5]
        hourly = self._mock_hourly(2)

        def side_effect(lat, lon):
            return lat, lon, {"hourly": hourly}

        mock_fetch.side_effect = side_effect
        result = fetch_wave_grid(lats, lons)

        assert result is not None
        assert result["model"] == "ECMWF-WAM"
        assert result["grid"]["nx"] == 2
        assert result["grid"]["ny"] == 2
        assert result["bounds"]["lat_min"] == 24.0
        assert result["bounds"]["lat_max"] == 24.5
        assert result["bounds"]["lon_min"] == 121.0
        assert result["bounds"]["lon_max"] == 121.5
        assert len(result["timesteps"]) == 2

    @patch("wave_grid_fetch._fetch_point")
    def test_timestep_structure(self, mock_fetch):
        """Each timestep has wave_height, swell_height, swell_direction, swell_period grids."""
        lats = [24.0]
        lons = [121.0]
        hourly = self._mock_hourly(1)

        mock_fetch.side_effect = lambda lat, lon: (lat, lon, {"hourly": hourly})
        result = fetch_wave_grid(lats, lons)

        ts = result["timesteps"][0]
        assert "valid_utc" in ts
        assert "wave_height" in ts
        assert "swell_height" in ts
        assert "swell_direction" in ts
        assert "swell_period" in ts
        # Grid is [ny][nx] = [1][1]
        assert len(ts["wave_height"]) == 1
        assert len(ts["wave_height"][0]) == 1

    @patch("wave_grid_fetch._fetch_point")
    def test_utc_suffix_added(self, mock_fetch):
        """Timestamps without timezone get +00:00 appended."""
        lats = [24.0]
        lons = [121.0]
        hourly = self._mock_hourly(1)

        mock_fetch.side_effect = lambda lat, lon: (lat, lon, {"hourly": hourly})
        result = fetch_wave_grid(lats, lons)

        assert result["timesteps"][0]["valid_utc"].endswith("+00:00")

    @patch("wave_grid_fetch._fetch_point")
    def test_no_results_returns_none(self, mock_fetch):
        """If all points fail, returns None."""
        lats = [24.0]
        lons = [121.0]

        mock_fetch.side_effect = lambda lat, lon: (lat, lon, None)
        result = fetch_wave_grid(lats, lons)
        assert result is None

    @patch("wave_grid_fetch._fetch_point")
    def test_partial_failure_fills_none(self, mock_fetch):
        """When some points fail, their grid cells are None."""
        lats = [24.0, 24.5]
        lons = [121.0]
        hourly = self._mock_hourly(1)

        def side_effect(lat, lon):
            if lat == 24.0:
                return lat, lon, {"hourly": hourly}
            return lat, lon, None

        mock_fetch.side_effect = side_effect
        result = fetch_wave_grid(lats, lons)

        assert result is not None
        ts = result["timesteps"][0]
        # First lat row has data
        assert ts["wave_height"][0][0] is not None
        # Second lat row has None (failed point)
        assert ts["wave_height"][1][0] is None

    @patch("wave_grid_fetch._fetch_point")
    def test_missing_swell_fields_graceful(self, mock_fetch):
        """If swell fields are absent, fills None."""
        lats = [24.0]
        lons = [121.0]
        hourly = {
            "time": ["2025-01-01T00:00"],
            "wave_height": [1.5],
            # No swell_wave_height, etc.
        }

        mock_fetch.side_effect = lambda lat, lon: (lat, lon, {"hourly": hourly})
        result = fetch_wave_grid(lats, lons)

        ts = result["timesteps"][0]
        assert ts["wave_height"][0][0] == 1.5
        assert ts["swell_height"][0][0] is None
        assert ts["swell_direction"][0][0] is None
        assert ts["swell_period"][0][0] is None
