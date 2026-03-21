"""Shared constants for the taiwanwrf pipeline."""

import logging


def setup_logging(level: int = logging.INFO) -> None:
    """Configure root logger for CLI scripts."""
    logging.basicConfig(
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        level=level,
    )


# Keelung harbour target point (WRF grid extraction, ECMWF/wave API queries)
KEELUNG_LAT = 25.15589534977208
KEELUNG_LON = 121.78782946186699
