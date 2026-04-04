"""Tests validating data contracts between pipeline modules.

These tests verify that JSON output schemas match what downstream consumers
expect, preventing silent integration failures.
"""

import json
import os
import re

from config import SPOT_COORDS, SPOT_STATIONS


class TestLiveObsSync:
    """Verify that api/live-obs.js SPOT_STATIONS stays in sync with config.py."""

    def _parse_js_spot_stations(self):
        """Extract spot IDs from the JS SPOT_STATIONS object."""
        path = os.path.join(os.path.dirname(__file__), '..', 'api', 'live-obs.js')
        with open(path) as f:
            content = f.read()
        # Find SPOT_STATIONS block
        match = re.search(r'const SPOT_STATIONS\s*=\s*\{', content)
        assert match, "Could not find SPOT_STATIONS in live-obs.js"
        # Extract top-level keys: lines starting with "  word:" (2-space indent, not deeper)
        start = match.end()
        keys = set()
        for line in content[start:].split('\n'):
            # Stop at closing brace
            if line.strip() == '}':
                break
            # Match top-level keys (indented with spaces, followed by colon and {)
            m = re.match(r'^\s{2}(\w+)\s*:', line)
            if m:
                keys.add(m.group(1))
        return keys

    def test_js_has_all_python_spots(self):
        """Every spot in config.py SPOT_STATIONS should be in live-obs.js."""
        py_ids = set(SPOT_STATIONS.keys())
        js_ids = self._parse_js_spot_stations()
        missing = py_ids - js_ids
        assert not missing, f"Spots in config.py but missing from live-obs.js: {missing}"

    def test_js_has_no_extra_spots(self):
        """live-obs.js should not have spots that config.py doesn't know about."""
        py_ids = set(SPOT_STATIONS.keys())
        js_ids = self._parse_js_spot_stations()
        extra = js_ids - py_ids
        assert not extra, f"Spots in live-obs.js but missing from config.py: {extra}"

    def test_weather_stations_match(self):
        """Primary weather station IDs should match between Python and JS."""
        path = os.path.join(os.path.dirname(__file__), '..', 'api', 'live-obs.js')
        with open(path) as f:
            content = f.read()
        for sid, info in SPOT_STATIONS.items():
            py_station = info['weather']
            # Check that the JS file contains this station ID for this spot
            pattern = rf"{sid}\s*:\s*\{{[^}}]*weather:\s*'{py_station}'"
            assert re.search(pattern, content), \
                f"{sid}: config.py has weather={py_station} but live-obs.js differs"


class TestFrontendConstantsSync:
    """Verify that frontend constants.ts stays in sync with config.py."""

    def _parse_ts_spot_county(self):
        """Extract spot IDs from frontend SPOT_COUNTY."""
        path = os.path.join(os.path.dirname(__file__), '..',
                            'frontend', 'src', 'lib', 'constants.ts')
        with open(path) as f:
            content = f.read()
        match = re.search(r'SPOT_COUNTY[^{]*\{([^}]+)\}', content)
        assert match, "Could not find SPOT_COUNTY in constants.ts"
        block = match.group(1)
        keys = re.findall(r"(\w+)\s*:", block)
        return set(keys)

    def test_frontend_has_all_python_spots(self):
        """Every spot in SPOT_COORDS should be in frontend SPOT_COUNTY."""
        py_ids = {s['id'] for s in SPOT_COORDS}
        ts_ids = self._parse_ts_spot_county()
        missing = py_ids - ts_ids
        assert not missing, f"Spots in config.py but missing from constants.ts SPOT_COUNTY: {missing}"
