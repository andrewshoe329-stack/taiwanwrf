"""Tests for current_grid_fetch.py — grid generation and data assembly."""

from current_grid_fetch import make_grid, fetch_current_grid
from unittest.mock import patch


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
        lats, lons = make_grid(24.0, 26.0, 120.0, 123.0, 0.25)
        assert lats == sorted(lats)
        assert lons == sorted(lons)
        assert lats[0] == 24.0
        assert lats[-1] == 26.0

    def test_default_resolution(self):
        lats, lons = make_grid(25.0, 25.2, 121.0, 121.2)
        assert len(lats) == 3
        assert len(lons) == 3

    def test_rounding(self):
        lats, lons = make_grid(24.0, 24.3, 121.0, 121.3, 0.1)
        for lat in lats:
            assert lat == round(lat, 6)


class TestFetchCurrentGrid:
    """fetch_current_grid assembles grid data from API responses."""

    def _mock_hourly(self, n_hours=6):
        """Build a fake Open-Meteo hourly response with 3-hourly times."""
        return {
            "time": [f"2025-01-01T{h:02d}:00" for h in range(n_hours)],
            "ocean_current_velocity": [0.5 + i * 0.1 for i in range(n_hours)],
            "ocean_current_direction": [180.0 + i * 10 for i in range(n_hours)],
        }

    @patch("current_grid_fetch._fetch_point")
    def test_all_points_success(self, mock_fetch):
        """All grid points succeed — correct structure."""
        lats = [24.0, 24.5]
        lons = [121.0, 121.5]
        hourly = self._mock_hourly(6)

        mock_fetch.side_effect = lambda lat, lon: (lat, lon, {"hourly": hourly})
        result = fetch_current_grid(lats, lons)

        assert result is not None
        assert result["model"] == "CMEMS"
        assert result["grid"]["nx"] == 2
        assert result["grid"]["ny"] == 2
        assert result["bounds"]["lat_min"] == 24.0
        assert result["bounds"]["lon_max"] == 121.5

    @patch("current_grid_fetch._fetch_point")
    def test_3hourly_filtering(self, mock_fetch):
        """Only hours divisible by 3 are included."""
        lats = [24.0]
        lons = [121.0]
        hourly = self._mock_hourly(6)  # hours 0,1,2,3,4,5

        mock_fetch.side_effect = lambda lat, lon: (lat, lon, {"hourly": hourly})
        result = fetch_current_grid(lats, lons)

        # Hours 0 and 3 should be included (divisible by 3)
        assert len(result["timesteps"]) == 2

    @patch("current_grid_fetch._fetch_point")
    def test_timestep_structure(self, mock_fetch):
        """Each timestep has velocity and direction grids."""
        lats = [24.0]
        lons = [121.0]
        hourly = self._mock_hourly(3)  # hours 0,1,2 → only hour 0

        mock_fetch.side_effect = lambda lat, lon: (lat, lon, {"hourly": hourly})
        result = fetch_current_grid(lats, lons)

        ts = result["timesteps"][0]
        assert "valid_utc" in ts
        assert "velocity" in ts
        assert "direction" in ts
        assert len(ts["velocity"]) == 1  # ny=1
        assert len(ts["velocity"][0]) == 1  # nx=1

    @patch("current_grid_fetch._fetch_point")
    def test_utc_suffix_added(self, mock_fetch):
        """Timestamps without timezone get +00:00 appended."""
        lats = [24.0]
        lons = [121.0]
        hourly = self._mock_hourly(3)

        mock_fetch.side_effect = lambda lat, lon: (lat, lon, {"hourly": hourly})
        result = fetch_current_grid(lats, lons)

        assert result["timesteps"][0]["valid_utc"].endswith("+00:00")

    @patch("current_grid_fetch._fetch_point")
    def test_no_results_returns_none(self, mock_fetch):
        """If all points fail, returns None."""
        lats = [24.0]
        lons = [121.0]

        mock_fetch.side_effect = lambda lat, lon: (lat, lon, None)
        result = fetch_current_grid(lats, lons)
        assert result is None

    @patch("current_grid_fetch._fetch_point")
    def test_partial_failure_fills_none(self, mock_fetch):
        """When some points fail, grid cells are None."""
        lats = [24.0, 24.5]
        lons = [121.0]
        hourly = self._mock_hourly(3)

        def side_effect(lat, lon):
            if lat == 24.0:
                return lat, lon, {"hourly": hourly}
            return lat, lon, None

        mock_fetch.side_effect = side_effect
        result = fetch_current_grid(lats, lons)

        assert result is not None
        ts = result["timesteps"][0]
        assert ts["velocity"][0][0] is not None
        assert ts["velocity"][1][0] is None

    @patch("current_grid_fetch._fetch_point")
    def test_velocity_values_correct(self, mock_fetch):
        """Velocity values from API response are placed correctly in grid."""
        lats = [24.0]
        lons = [121.0]
        hourly = {
            "time": ["2025-01-01T00:00"],
            "ocean_current_velocity": [0.42],
            "ocean_current_direction": [270.0],
        }

        mock_fetch.side_effect = lambda lat, lon: (lat, lon, {"hourly": hourly})
        result = fetch_current_grid(lats, lons)

        ts = result["timesteps"][0]
        assert ts["velocity"][0][0] == 0.42
        assert ts["direction"][0][0] == 270.0

    @patch("current_grid_fetch._fetch_point")
    def test_missing_current_fields_graceful(self, mock_fetch):
        """If current fields are missing, fills None."""
        lats = [24.0]
        lons = [121.0]
        hourly = {
            "time": ["2025-01-01T00:00"],
            # No velocity or direction
        }

        mock_fetch.side_effect = lambda lat, lon: (lat, lon, {"hourly": hourly})
        result = fetch_current_grid(lats, lons)

        ts = result["timesteps"][0]
        assert ts["velocity"][0][0] is None
        assert ts["direction"][0][0] is None
