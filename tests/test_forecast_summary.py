"""Tests for forecast_summary.py — pure functions only (no API calls)."""

import pytest
from forecast_summary import _trim_records, build_user_prompt, render_html, SYSTEM_PROMPT


# ── _trim_records ────────────────────────────────────────────────────────────

class TestTrimRecords:
    def test_empty_input(self):
        assert _trim_records([]) == []

    def test_single_record(self):
        recs = [{"valid_utc": "2026-03-20T00:00:00+00:00"}]
        assert _trim_records(recs) == recs

    def test_trims_beyond_max_days(self):
        recs = [
            {"valid_utc": f"2026-03-{20 + d}T{h:02d}:00:00+00:00"}
            for d in range(10)
            for h in (0, 6, 12, 18)
        ]
        result = _trim_records(recs, max_days=3)
        # Should keep days 20, 21, 22 (3 days * 4 records = 12, plus day 23 00:00)
        assert len(result) <= 13  # 3 full days + first hour of day 4
        assert len(result) >= 12

    def test_keeps_all_within_window(self):
        recs = [
            {"valid_utc": f"2026-03-20T{h:02d}:00:00+00:00"}
            for h in (0, 6, 12, 18)
        ]
        result = _trim_records(recs, max_days=7)
        assert result == recs

    def test_fallback_on_malformed_dates(self):
        recs = [{"valid_utc": "NOT_A_DATE"} for _ in range(20)]
        result = _trim_records(recs, max_days=3)
        assert len(result) == 12  # 3 * 4

    def test_fallback_on_missing_valid_utc(self):
        recs = [{} for _ in range(10)]
        result = _trim_records(recs, max_days=2)
        assert len(result) == 8  # 2 * 4


# ── build_user_prompt ────────────────────────────────────────────────────────

class TestBuildUserPrompt:
    def _make_wrf(self, n_records=4):
        return {
            "meta": {"init_utc": "2026-03-20T00:00:00+00:00"},
            "records": [
                {
                    "valid_utc": f"2026-03-20T{h:02d}:00:00+00:00",
                    "temp_c": 22.0,
                    "wind_kt": 12.0,
                    "wind_dir": 45,
                    "gust_kt": 18.0,
                    "mslp_hpa": 1013.0,
                    "precip_mm_6h": 0.0,
                    "cape": 200,
                }
                for h in (0, 6, 12, 18)
            ][:n_records],
        }

    def test_wrf_only(self):
        prompt = build_user_prompt(self._make_wrf(), None, None)
        assert "Model init:" in prompt
        assert "WRF Keelung forecast" in prompt
        assert "ECMWF" not in prompt
        assert "WAM" not in prompt

    def test_with_ecmwf(self):
        ecmwf = {
            "records": [
                {
                    "valid_utc": "2026-03-20T00:00:00+00:00",
                    "wind_kt": 10.0,
                    "wind_dir": 90,
                }
            ]
        }
        prompt = build_user_prompt(self._make_wrf(), ecmwf, None)
        assert "ECMWF IFS" in prompt

    def test_with_wave(self):
        wave = {
            "ecmwf_wave": {
                "records": [
                    {
                        "valid_utc": "2026-03-20T00:00:00+00:00",
                        "wave_height": 1.5,
                        "wave_period": 8.0,
                        "wave_direction": 45,
                    }
                ]
            }
        }
        prompt = build_user_prompt(self._make_wrf(), None, wave)
        assert "WAM waves" in prompt

    def test_empty_wrf(self):
        prompt = build_user_prompt({"meta": {}, "records": []}, None, None)
        assert "Model init: unknown" in prompt
        # Should not crash, just have no WRF section

    def test_none_values_filtered(self):
        wrf = {
            "meta": {"init_utc": "2026-03-20T00:00:00+00:00"},
            "records": [
                {
                    "valid_utc": "2026-03-20T00:00:00+00:00",
                    "temp_c": None,
                    "wind_kt": 10.0,
                    "cape": None,
                }
            ],
        }
        prompt = build_user_prompt(wrf, None, None)
        assert "temp_c" not in prompt
        assert "wind_kt" in prompt


# ── render_html ──────────────────────────────────────────────────────────────

class TestRenderHtml:
    def test_basic_output(self):
        html = render_html("Light winds and small swells expected.")
        assert "AI Forecast Summary" in html
        assert "Light winds and small swells expected." in html
        assert "Not a substitute for official marine forecasts" in html

    def test_html_escaping(self):
        html = render_html('Wind <15kt & seas "calm"')
        assert "&lt;15kt" in html
        assert "&amp;" in html
        assert "&quot;calm&quot;" in html

    def test_empty_summary(self):
        html = render_html("")
        assert "AI Forecast Summary" in html


# ── SYSTEM_PROMPT ────────────────────────────────────────────────────────────

class TestSystemPrompt:
    def test_mentions_keelung(self):
        assert "Keelung" in SYSTEM_PROMPT

    def test_mentions_spots(self):
        for spot in ("Fulong", "Green Bay", "Jinshan", "Daxi", "Wushih",
                      "Double Lions", "Chousui"):
            assert spot in SYSTEM_PROMPT

    def test_mentions_units(self):
        assert "knots" in SYSTEM_PROMPT
        assert "metres" in SYSTEM_PROMPT
