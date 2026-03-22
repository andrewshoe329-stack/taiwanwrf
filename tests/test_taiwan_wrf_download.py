"""Tests for taiwan_wrf_download.py helper functions."""


from taiwan_wrf_download import (
    nm_to_km, bbox_from_point, bbox_contains_point,
    MODELS, DEFAULT_MODEL, FORECAST_INTERVAL,
)


# ── nm_to_km ─────────────────────────────────────────────────────────────────

class TestNmToKm:
    def test_zero(self):
        assert nm_to_km(0) == 0

    def test_one_nm(self):
        assert abs(nm_to_km(1) - 1.852) < 1e-9

    def test_fifty_nm(self):
        assert abs(nm_to_km(50) - 92.6) < 0.1


# ── bbox_from_point ──────────────────────────────────────────────────────────

class TestBboxFromPoint:
    def test_returns_valid_bbox(self):
        bbox = bbox_from_point(25.0, 121.0, 50)
        assert bbox['lat_min'] < 25.0
        assert bbox['lat_max'] > 25.0
        assert bbox['lon_min'] < 121.0
        assert bbox['lon_max'] > 121.0

    def test_symmetric_latitude(self):
        bbox = bbox_from_point(25.0, 121.0, 50)
        assert abs((bbox['lat_max'] - 25.0) - (25.0 - bbox['lat_min'])) < 1e-9

    def test_center_in_bbox(self):
        bbox = bbox_from_point(25.0, 121.0, 50)
        assert bbox_contains_point(bbox, 25.0, 121.0)


# ── bbox_contains_point ─────────────────────────────────────────────────────

class TestBboxContainsPoint:
    def test_inside(self):
        bbox = {'lat_min': 24.0, 'lat_max': 26.0, 'lon_min': 120.0, 'lon_max': 122.0}
        assert bbox_contains_point(bbox, 25.0, 121.0)

    def test_outside(self):
        bbox = {'lat_min': 24.0, 'lat_max': 26.0, 'lon_min': 120.0, 'lon_max': 122.0}
        assert not bbox_contains_point(bbox, 30.0, 121.0)

    def test_on_boundary(self):
        bbox = {'lat_min': 24.0, 'lat_max': 26.0, 'lon_min': 120.0, 'lon_max': 122.0}
        assert bbox_contains_point(bbox, 24.0, 120.0)


# ── Constants sanity ─────────────────────────────────────────────────────────

class TestConstants:
    def test_default_model_exists(self):
        assert DEFAULT_MODEL in MODELS

    def test_forecast_interval_positive(self):
        assert FORECAST_INTERVAL > 0

    def test_model_has_required_keys(self):
        for model_id, model in MODELS.items():
            assert 'name' in model
            assert 'resolution' in model
            assert 'max_hours' in model
            assert 'approx_mb' in model
