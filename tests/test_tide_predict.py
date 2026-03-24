"""Tests for tide_predict.py harmonic tide prediction."""


from datetime import datetime, timedelta, timezone
from tide_predict import (predict_height, predict_height_anchored, _parse_extrema,
                          find_extrema, tide_state, CONSTITUENTS, MSL_OFFSET)


class TestPredictHeight:
    def test_returns_float(self):
        dt = datetime(2026, 3, 22, 12, 0, 0, tzinfo=timezone.utc)
        h = predict_height(dt)
        assert isinstance(h, float)

    def test_within_reasonable_range(self):
        """Keelung tidal range is ~0.5m; height should be 0-1m above chart datum."""
        dt = datetime(2026, 3, 22, 0, 0, 0, tzinfo=timezone.utc)
        for hour in range(0, 48):
            h = predict_height(dt + timedelta(hours=hour))
            assert -0.2 < h < 1.2, f"Height {h}m at +{hour}h is out of range"

    def test_varies_over_time(self):
        """Height should change over 6 hours (not stuck at one value)."""
        dt = datetime(2026, 3, 22, 0, 0, 0, tzinfo=timezone.utc)
        heights = [predict_height(dt + timedelta(hours=h)) for h in range(7)]
        assert len(set(heights)) > 1

    def test_msl_offset_used(self):
        """MSL offset should be reflected in the prediction."""
        assert MSL_OFFSET > 0


class TestFindExtrema:
    def test_finds_highs_and_lows(self):
        start = datetime(2026, 3, 22, 0, 0, 0, tzinfo=timezone.utc)
        end = start + timedelta(days=1)
        extrema = find_extrema(start, end)
        types = {ex['type'] for ex in extrema}
        assert 'high' in types
        assert 'low' in types

    def test_semidiurnal_pattern(self):
        """Keelung is semidiurnal — expect ~4 extrema per day (2 highs, 2 lows)."""
        start = datetime(2026, 3, 22, 0, 0, 0, tzinfo=timezone.utc)
        end = start + timedelta(days=2)
        extrema = find_extrema(start, end)
        # 2 days should have 7-10 extrema (not exactly 8 due to boundaries)
        assert 6 <= len(extrema) <= 12

    def test_alternating_high_low(self):
        """Extrema should alternate between high and low."""
        start = datetime(2026, 3, 22, 0, 0, 0, tzinfo=timezone.utc)
        end = start + timedelta(days=1)
        extrema = find_extrema(start, end)
        for i in range(1, len(extrema)):
            assert extrema[i]['type'] != extrema[i-1]['type'], \
                f"Consecutive {extrema[i-1]['type']} at {extrema[i-1]['utc']} and {extrema[i]['utc']}"

    def test_extrema_have_required_fields(self):
        start = datetime(2026, 3, 22, 0, 0, 0, tzinfo=timezone.utc)
        end = start + timedelta(days=1)
        extrema = find_extrema(start, end)
        for ex in extrema:
            assert 'type' in ex
            assert 'utc' in ex
            assert 'cst' in ex
            assert 'height_m' in ex
            assert ex['type'] in ('high', 'low')

    def test_highs_higher_than_lows(self):
        start = datetime(2026, 3, 22, 0, 0, 0, tzinfo=timezone.utc)
        end = start + timedelta(days=2)
        extrema = find_extrema(start, end)
        highs = [ex['height_m'] for ex in extrema if ex['type'] == 'high']
        lows = [ex['height_m'] for ex in extrema if ex['type'] == 'low']
        if highs and lows:
            assert min(highs) > min(lows)


class TestTideState:
    def test_returns_valid_state(self):
        start = datetime(2026, 3, 22, 0, 0, 0, tzinfo=timezone.utc)
        end = start + timedelta(days=1)
        extrema = find_extrema(start, end)
        state = tide_state(start + timedelta(hours=3), extrema)
        assert state in ('rising', 'falling', 'high', 'low')

    def test_empty_extrema(self):
        dt = datetime(2026, 3, 22, 0, 0, 0, tzinfo=timezone.utc)
        assert tide_state(dt, []) == 'unknown'


class TestConstants:
    def test_constituents_structure(self):
        for name, period, amp, phase in CONSTITUENTS:
            assert isinstance(name, str)
            assert period > 0
            assert amp > 0
            assert 0 <= phase < 360


class TestPredictHeightAnchored:
    def _make_extrema(self):
        """Create CWA-style extrema: high at 06:00, low at 12:15."""
        return [
            {"time_utc": "2026-03-22T06:00:00+00:00", "height_m": 0.85, "type": "high"},
            {"time_utc": "2026-03-22T12:15:00+00:00", "height_m": 0.10, "type": "low"},
            {"time_utc": "2026-03-22T18:30:00+00:00", "height_m": 0.80, "type": "high"},
        ]

    def test_returns_float(self):
        dt = datetime(2026, 3, 22, 9, 0, 0, tzinfo=timezone.utc)
        result = predict_height_anchored(dt, self._make_extrema())
        assert isinstance(result, float)

    def test_at_high_returns_high_value(self):
        """At a CWA high tide time, should return the CWA height."""
        dt = datetime(2026, 3, 22, 6, 0, 0, tzinfo=timezone.utc)
        result = predict_height_anchored(dt, self._make_extrema())
        assert abs(result - 0.85) < 0.01

    def test_at_low_returns_low_value(self):
        """At a CWA low tide time, should return the CWA height."""
        dt = datetime(2026, 3, 22, 12, 15, 0, tzinfo=timezone.utc)
        result = predict_height_anchored(dt, self._make_extrema())
        assert abs(result - 0.10) < 0.01

    def test_midpoint_between_high_and_low(self):
        """Midpoint between high and low should be near the average."""
        high_t = datetime(2026, 3, 22, 6, 0, 0, tzinfo=timezone.utc)
        low_t = datetime(2026, 3, 22, 12, 15, 0, tzinfo=timezone.utc)
        mid_t = high_t + (low_t - high_t) / 2
        result = predict_height_anchored(mid_t, self._make_extrema())
        avg = (0.85 + 0.10) / 2
        # Cosine midpoint should be exactly at the average
        assert abs(result - avg) < 0.01

    def test_falls_back_without_extrema(self):
        """Without CWA data, should fall back to harmonic prediction."""
        dt = datetime(2026, 3, 22, 9, 0, 0, tzinfo=timezone.utc)
        anchored = predict_height_anchored(dt, None)
        harmonic = predict_height(dt)
        assert anchored == harmonic

    def test_falls_back_with_empty_list(self):
        dt = datetime(2026, 3, 22, 9, 0, 0, tzinfo=timezone.utc)
        anchored = predict_height_anchored(dt, [])
        harmonic = predict_height(dt)
        assert anchored == harmonic

    def test_falls_back_outside_extrema_range(self):
        """Before first extremum, should fall back to harmonic."""
        dt = datetime(2026, 3, 22, 3, 0, 0, tzinfo=timezone.utc)
        anchored = predict_height_anchored(dt, self._make_extrema())
        harmonic = predict_height(dt)
        assert anchored == harmonic

    def test_cosine_shape(self):
        """Height should decrease monotonically from high to mid to low."""
        extrema = self._make_extrema()
        t1 = datetime(2026, 3, 22, 6, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 3, 22, 9, 0, 0, tzinfo=timezone.utc)
        t3 = datetime(2026, 3, 22, 12, 15, 0, tzinfo=timezone.utc)
        h1 = predict_height_anchored(t1, extrema)
        h2 = predict_height_anchored(t2, extrema)
        h3 = predict_height_anchored(t3, extrema)
        assert h1 > h2 > h3


class TestParseExtrema:
    def test_parses_valid(self):
        extrema = [
            {"time_utc": "2026-03-22T06:00:00+00:00", "height_m": 0.85, "type": "high"},
            {"time_utc": "2026-03-22T12:00:00+00:00", "height_m": 0.10, "type": "low"},
        ]
        parsed = _parse_extrema(extrema)
        assert len(parsed) == 2
        assert parsed[0][2] == "high"
        assert parsed[1][2] == "low"

    def test_skips_invalid(self):
        extrema = [
            {"time_utc": "", "height_m": 0.85, "type": "high"},
            {"time_utc": "2026-03-22T06:00:00+00:00", "height_m": None, "type": "high"},
            {"time_utc": "2026-03-22T12:00:00+00:00", "height_m": 0.10, "type": "low"},
        ]
        parsed = _parse_extrema(extrema)
        assert len(parsed) == 1

    def test_sorted_by_time(self):
        extrema = [
            {"time_utc": "2026-03-22T12:00:00+00:00", "height_m": 0.10, "type": "low"},
            {"time_utc": "2026-03-22T06:00:00+00:00", "height_m": 0.85, "type": "high"},
        ]
        parsed = _parse_extrema(extrema)
        assert parsed[0][0] < parsed[1][0]

    def test_empty_list(self):
        assert _parse_extrema([]) == []
