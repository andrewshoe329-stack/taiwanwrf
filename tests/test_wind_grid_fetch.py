"""Tests for wind_grid_fetch.py — UV conversion and grid generation."""
import math

from wind_grid_fetch import wind_to_uv, make_grid


class TestWindToUV:
    """wind_to_uv converts speed + meteorological direction to u/v."""

    def test_north_wind(self):
        """North wind (from 0°/360°): blows southward → u≈0, v<0."""
        u, v = wind_to_uv(10.0, 0.0)
        assert abs(u) < 0.01
        assert v == -10.0

    def test_south_wind(self):
        """South wind (from 180°): blows northward → u≈0, v>0."""
        u, v = wind_to_uv(10.0, 180.0)
        assert abs(u) < 0.01
        assert abs(v - 10.0) < 0.01

    def test_east_wind(self):
        """East wind (from 90°): blows westward → u<0, v≈0."""
        u, v = wind_to_uv(10.0, 90.0)
        assert abs(u - (-10.0)) < 0.01
        assert abs(v) < 0.01

    def test_west_wind(self):
        """West wind (from 270°): blows eastward → u>0, v≈0."""
        u, v = wind_to_uv(10.0, 270.0)
        assert abs(u - 10.0) < 0.01
        assert abs(v) < 0.01

    def test_calm_wind(self):
        """Zero speed gives zero components regardless of direction."""
        u, v = wind_to_uv(0.0, 45.0)
        assert u == 0.0
        assert v == 0.0

    def test_full_circle(self):
        """360° should be same as 0°."""
        u0, v0 = wind_to_uv(5.0, 0.0)
        u360, v360 = wind_to_uv(5.0, 360.0)
        assert abs(u0 - u360) < 0.01
        assert abs(v0 - v360) < 0.01

    def test_magnitude_preserved(self):
        """sqrt(u² + v²) should equal the input speed (within rounding)."""
        for direction in (0, 45, 90, 135, 180, 225, 270, 315):
            u, v = wind_to_uv(8.5, direction)
            mag = math.sqrt(u ** 2 + v ** 2)
            assert abs(mag - 8.5) < 0.05, f"dir={direction}: mag={mag}"

    def test_rounding(self):
        """Output is rounded to 2 decimal places."""
        u, v = wind_to_uv(1.0, 33.3)
        assert u == round(u, 2)
        assert v == round(v, 2)


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
