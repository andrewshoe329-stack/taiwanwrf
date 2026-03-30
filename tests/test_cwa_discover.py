"""Tests for cwa_discover.py — station discovery and nearest-match logic."""
from cwa_discover import (
    _extract_coords,
    _try_float,
    find_nearest,
    build_station_mapping,
    KNOWN_BUOY_COORDS,
    KNOWN_STATION_COORDS,
)
from cwa_fetch import _haversine_km


class TestTryFloat:
    """_try_float converts various inputs to float safely."""

    def test_normal_float(self):
        assert _try_float(25.1) == 25.1

    def test_string_float(self):
        assert _try_float("25.1") == 25.1

    def test_integer(self):
        assert _try_float(25) == 25.0

    def test_none(self):
        assert _try_float(None) is None

    def test_empty_string(self):
        assert _try_float("") is None

    def test_sentinel_minus_99(self):
        assert _try_float("-99") is None

    def test_invalid_string(self):
        assert _try_float("abc") is None

    def test_zero(self):
        assert _try_float(0) == 0.0

    def test_negative(self):
        assert _try_float(-12.5) == -12.5


class TestExtractCoords:
    """_extract_coords handles various CWA station dict structures."""

    def test_geoinfo_direct(self):
        stn = {"GeoInfo": {"Latitude": 25.1, "Longitude": 121.7}}
        lat, lon = _extract_coords(stn)
        assert lat == 25.1
        assert lon == 121.7

    def test_geoinfo_coordinates_array(self):
        stn = {"GeoInfo": {"Coordinates": [
            {"StationLatitude": 25.2, "StationLongitude": 121.8}
        ]}}
        lat, lon = _extract_coords(stn)
        assert lat == 25.2
        assert lon == 121.8

    def test_geoinfo_station_lat_lon(self):
        stn = {"GeoInfo": {"StationLatitude": 25.3, "StationLongitude": 121.9}}
        lat, lon = _extract_coords(stn)
        assert lat == 25.3
        assert lon == 121.9

    def test_top_level_keys(self):
        stn = {"lat": 25.4, "lon": 122.0}
        lat, lon = _extract_coords(stn)
        assert lat == 25.4
        assert lon == 122.0

    def test_empty_dict(self):
        lat, lon = _extract_coords({})
        assert lat is None
        assert lon is None

    def test_lowercase_geoinfo(self):
        stn = {"geoInfo": {"latitude": 25.5, "longitude": 122.1}}
        lat, lon = _extract_coords(stn)
        assert lat == 25.5
        assert lon == 122.1

    def test_string_coords_converted(self):
        stn = {"GeoInfo": {"Latitude": "25.6", "Longitude": "121.3"}}
        lat, lon = _extract_coords(stn)
        assert lat == 25.6
        assert lon == 121.3


class TestHaversineKm:
    """_haversine_km computes reasonable distances."""

    def test_same_point_is_zero(self):
        assert _haversine_km(25.0, 121.0, 25.0, 121.0) == 0.0

    def test_keelung_to_fulong(self):
        """Keelung (25.156, 121.788) to Fulong (25.019, 121.940) ≈ 20km."""
        d = _haversine_km(25.156, 121.788, 25.019, 121.940)
        assert 15 < d < 25

    def test_symmetry(self):
        d1 = _haversine_km(25.0, 121.0, 24.0, 122.0)
        d2 = _haversine_km(24.0, 122.0, 25.0, 121.0)
        assert abs(d1 - d2) < 0.001


class TestFindNearest:
    """find_nearest returns closest item within max distance."""

    def test_finds_closest(self):
        items = [
            {"lat": 25.0, "lon": 121.0, "station_id": "A"},
            {"lat": 25.1, "lon": 121.1, "station_id": "B"},
        ]
        best, dist = find_nearest(items, 25.09, 121.09)
        assert best["station_id"] == "B"
        assert dist is not None
        assert dist < 5

    def test_respects_max_distance(self):
        items = [{"lat": 0.0, "lon": 0.0, "station_id": "far"}]
        best, dist = find_nearest(items, 25.0, 121.0, max_dist_km=50)
        assert best is None
        assert dist is None

    def test_empty_list(self):
        best, dist = find_nearest([], 25.0, 121.0)
        assert best is None
        assert dist is None

    def test_items_missing_coords_skipped(self):
        items = [
            {"station_id": "no_coords"},
            {"lat": 25.0, "lon": 121.0, "station_id": "with_coords"},
        ]
        best, dist = find_nearest(items, 25.0, 121.0)
        assert best["station_id"] == "with_coords"


class TestKnownCoordinates:
    """Known coordinate dictionaries have valid entries."""

    def test_buoy_coords_have_valid_lat_lon(self):
        for bid, (lat, lon, name) in KNOWN_BUOY_COORDS.items():
            assert 20 < lat < 30, f"Buoy {bid} lat out of range: {lat}"
            assert 119 < lon < 123, f"Buoy {bid} lon out of range: {lon}"
            assert isinstance(name, str) and len(name) > 0

    def test_station_coords_have_valid_lat_lon(self):
        for sid, (lat, lon, name) in KNOWN_STATION_COORDS.items():
            assert 20 < lat < 30, f"Station {sid} lat out of range: {lat}"
            assert 119 < lon < 123, f"Station {sid} lon out of range: {lon}"
            assert isinstance(name, str) and len(name) > 0
