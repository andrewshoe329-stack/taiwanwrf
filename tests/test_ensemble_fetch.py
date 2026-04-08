"""Tests for ensemble_fetch.py — pure functions only (no API calls)."""

from ensemble_fetch import compute_ensemble_stats, _fetch_location, ENSEMBLE_VARS
from unittest.mock import patch


class TestComputeEnsembleStats:
    def _make_records(self, model_data: dict[str, list[tuple[str, dict]]]) -> dict[str, list[dict]]:
        """Create model records from {model: [(valid_utc, {var: val}), ...]}."""
        result = {}
        for model, entries in model_data.items():
            result[model] = [
                {"valid_utc": vt, **vals}
                for vt, vals in entries
            ]
        return result

    def test_basic_stats(self):
        recs = self._make_records({
            "gfs": [("2026-03-22T00:00:00+00:00", {"wind_kt": 10, "temp_c": 22})],
            "jma": [("2026-03-22T00:00:00+00:00", {"wind_kt": 14, "temp_c": 24})],
            "ecmwf": [("2026-03-22T00:00:00+00:00", {"wind_kt": 12, "temp_c": 23})],
        })
        stats = compute_ensemble_stats(recs)
        assert len(stats) == 1
        s = stats[0]
        assert s["wind_kt"]["min"] == 10
        assert s["wind_kt"]["max"] == 14
        assert s["wind_kt"]["spread"] == 4
        assert s["wind_kt"]["n"] == 3
        assert abs(s["wind_kt"]["mean"] - 12.0) < 0.01

    def test_missing_values_excluded(self):
        recs = self._make_records({
            "gfs": [("2026-03-22T00:00:00+00:00", {"wind_kt": 10, "temp_c": None})],
            "jma": [("2026-03-22T00:00:00+00:00", {"wind_kt": 14, "temp_c": 24})],
        })
        stats = compute_ensemble_stats(recs)
        s = stats[0]
        assert s["wind_kt"]["n"] == 2
        assert s["temp_c"]["n"] == 1  # Only JMA has temp
        assert s["temp_c"]["spread"] == 0  # Single value → no spread

    def test_single_model(self):
        recs = self._make_records({
            "gfs": [("2026-03-22T00:00:00+00:00", {"wind_kt": 10})],
        })
        stats = compute_ensemble_stats(recs)
        s = stats[0]
        assert s["wind_kt"]["n"] == 1
        assert s["wind_kt"]["spread"] == 0

    def test_empty_input(self):
        stats = compute_ensemble_stats({})
        assert stats == []

    def test_multiple_timesteps(self):
        recs = self._make_records({
            "gfs": [
                ("2026-03-22T00:00:00+00:00", {"wind_kt": 10}),
                ("2026-03-22T06:00:00+00:00", {"wind_kt": 15}),
            ],
            "jma": [
                ("2026-03-22T00:00:00+00:00", {"wind_kt": 12}),
                ("2026-03-22T06:00:00+00:00", {"wind_kt": 18}),
            ],
        })
        stats = compute_ensemble_stats(recs)
        assert len(stats) == 2
        assert stats[0]["valid_utc"] < stats[1]["valid_utc"]

    def test_disjoint_timesteps(self):
        recs = self._make_records({
            "gfs": [("2026-03-22T00:00:00+00:00", {"wind_kt": 10})],
            "jma": [("2026-03-22T06:00:00+00:00", {"wind_kt": 12})],
        })
        stats = compute_ensemble_stats(recs)
        assert len(stats) == 2
        # Each timestep has only 1 model
        assert stats[0]["wind_kt"]["n"] == 1
        assert stats[1]["wind_kt"]["n"] == 1

    def test_all_vars_present(self):
        recs = self._make_records({
            "gfs": [("2026-03-22T00:00:00+00:00", {
                "temp_c": 22, "wind_kt": 10, "gust_kt": 15,
                "mslp_hpa": 1013, "precip_mm_6h": 1.5, "cape": 200,
            })],
        })
        stats = compute_ensemble_stats(recs)
        s = stats[0]
        for var in ENSEMBLE_VARS:
            assert var in s
            assert s[var] is not None
            assert s[var]["n"] == 1

    def test_no_values_for_var(self):
        recs = self._make_records({
            "gfs": [("2026-03-22T00:00:00+00:00", {"wind_kt": 10})],
        })
        stats = compute_ensemble_stats(recs)
        s = stats[0]
        assert s["cape"] is None  # Not provided → None


class TestFetchLocation:
    """Test _fetch_location compact output (mocked API)."""

    def test_returns_compact_output(self):
        fake_result = {
            "models": {
                "GFS": {
                    "meta": {"model_id": "GFS-Global"},
                    "records": [{"valid_utc": "t1"}, {"valid_utc": "t2"}],
                },
                "ICON": {
                    "meta": {"model_id": "ICON-Global"},
                    "records": [{"valid_utc": "t1"}],
                },
            },
            "spread": {"wind_spread_kt": 3.5, "temp_spread_c": 1.2},
        }
        with patch("ensemble_fetch._fetch_ensemble_for_point", return_value=fake_result):
            loc_id, result = _fetch_location({"id": "jinshan", "lat": 25.0, "lon": 121.0})

        assert loc_id == "jinshan"
        assert result is not None
        # Compact output should have record_count, not full records
        assert "records" not in result["models"]["GFS"]
        assert result["models"]["GFS"]["record_count"] == 2
        assert result["models"]["ICON"]["record_count"] == 1
        assert result["spread"] == fake_result["spread"]

    def test_returns_none_when_no_data(self):
        with patch("ensemble_fetch._fetch_ensemble_for_point", return_value=None):
            loc_id, result = _fetch_location({"id": "taipei", "lat": 25.0, "lon": 121.5})

        assert loc_id == "taipei"
        assert result is None
