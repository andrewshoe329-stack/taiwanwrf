"""Tests for config.py shared constants."""

from config import KEELUNG_LAT, KEELUNG_LON, setup_logging


def test_keelung_coordinates_in_range():
    """Keelung is in northern Taiwan — lat ~25°N, lon ~121°E."""
    assert 24.0 < KEELUNG_LAT < 26.0
    assert 120.0 < KEELUNG_LON < 123.0


def test_setup_logging_does_not_raise():
    setup_logging()
