"""Tests for forecast_summary.py — pure functions only (no API calls)."""

import pytest
from forecast_summary import (
    _trim_records, build_user_prompt, render_html, SYSTEM_PROMPT,
    _summarise_accuracy, _parse_sections,
)


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
        assert "AI Forecast Summary" in html or "AI 預報摘要" in html
        assert "Light winds and small swells expected." in html
        assert "Not a substitute for official marine forecasts" in html or "不可取代官方海洋預報" in html

    def test_html_escaping(self):
        html = render_html('Wind <15kt & seas "calm"')
        assert "&lt;15kt" in html
        assert "&amp;" in html
        assert "&quot;calm&quot;" in html

    def test_empty_summary(self):
        html = render_html("")
        assert "AI Forecast Summary" in html or "AI 預報摘要" in html

    def test_section_id(self):
        html = render_html("test")
        assert 'id="summary"' in html

    def test_has_section_class(self):
        html = render_html("test")
        assert 'class="section"' in html

    def test_disclaimer_present(self):
        html = render_html("test")
        assert "ai-disclaimer" in html

    def test_multiline_summary(self):
        text = "Line one.\nLine two.\nLine three."
        html = render_html(text)
        assert "Line one." in html
        assert "Line three." in html

    def test_bilingual_split(self):
        """When response contains ---, it splits into en/zh sections."""
        text = "English forecast here.\n---\n中文預報在這裡。"
        html = render_html(text)
        assert 'lang="en"' in html
        assert 'lang="zh"' in html
        assert "English forecast here." in html
        assert "中文預報在這裡。" in html

    def test_no_separator_fallback(self):
        """Without --- separator, entire text is treated as single content."""
        text = "English only forecast."
        html = render_html(text)
        assert "English only forecast." in html
        # Should not have separate lang="zh" content div
        assert html.count('lang="zh"') <= 2  # only from T() title/disclaimer, not content

    def test_structured_sections_render_as_cards(self):
        """When [WIND]/[WAVES]/[OUTLOOK] markers present, renders as ai-card divs."""
        text = (
            "[WIND] NE winds 12-15kt through midweek.\n"
            "[WAVES] Small NE swell building to 1.2m.\n"
            "[OUTLOOK] Thursday looks best for sailing.\n"
            "---\n"
            "[WIND] 東北風12-15節。\n"
            "[WAVES] 東北湧浪逐漸增至1.2公尺。\n"
            "[OUTLOOK] 週四最適合出航。"
        )
        html = render_html(text)
        assert 'ai-card' in html
        assert 'ai-card-header' in html
        assert 'NE winds 12-15kt' in html
        assert '東北風12-15節' in html
        assert 'lang="en"' in html
        assert 'lang="zh"' in html

    def test_structured_fallback_to_plain(self):
        """Without section markers, falls back to ai-content (legacy)."""
        text = "Just plain text.\n---\n只是純文字。"
        html = render_html(text)
        assert 'ai-content' in html
        assert 'ai-card' not in html


# ── _parse_sections ──────────────────────────────────────────────────────────

class TestParseSections:
    def test_parses_all_three_sections(self):
        text = "[WIND] Wind info. [WAVES] Wave info. [OUTLOOK] Outlook info."
        sections = _parse_sections(text)
        assert len(sections) == 3
        assert sections[0] == ('WIND', 'Wind info.')
        assert sections[1] == ('WAVES', 'Wave info.')
        assert sections[2] == ('OUTLOOK', 'Outlook info.')

    def test_no_markers_returns_full_text(self):
        text = "No markers here, just text."
        sections = _parse_sections(text)
        assert len(sections) == 1
        assert sections[0] == ('', text)

    def test_partial_markers(self):
        text = "[WIND] Wind only."
        sections = _parse_sections(text)
        assert len(sections) == 1
        assert sections[0][0] == 'WIND'

    def test_empty_string(self):
        sections = _parse_sections("")
        assert len(sections) == 1


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

    def test_mentions_accuracy_instructions(self):
        assert "accuracy" in SYSTEM_PROMPT.lower()
        assert "bias" in SYSTEM_PROMPT.lower()


# ── _summarise_accuracy ─────────────────────────────────────────────────────

class TestSummariseAccuracy:
    SAMPLE_LOG = [
        {
            "init_utc": "2026-03-20T00:00:00+00:00",
            "temp_mae_c": 1.2,
            "temp_bias_c": 0.8,
            "wind_mae_kt": 3.5,
            "wind_bias_kt": -1.1,
            "wdir_mae_deg": 28.0,
            "mslp_mae_hpa": 0.9,
            "wave": {"hs_mae_m": 0.3, "hs_bias_m": 0.1},
        },
        {
            "init_utc": "2026-03-20T06:00:00+00:00",
            "temp_mae_c": 1.4,
            "temp_bias_c": 1.0,
            "wind_mae_kt": 4.0,
            "wind_bias_kt": -0.5,
            "wdir_mae_deg": 32.0,
            "mslp_mae_hpa": 1.1,
            "wave": {"hs_mae_m": 0.4, "hs_bias_m": 0.2},
        },
    ]

    def test_returns_none_for_empty(self):
        assert _summarise_accuracy([]) is None
        assert _summarise_accuracy(None) is None

    def test_returns_none_for_no_metrics(self):
        assert _summarise_accuracy([{"init_utc": "2026-03-20T00:00:00+00:00"}]) is None

    def test_contains_temp_info(self):
        result = _summarise_accuracy(self.SAMPLE_LOG)
        assert result is not None
        assert "Temp" in result
        assert "MAE" in result
        assert "warm" in result  # positive bias → "runs warm"

    def test_contains_wind_info(self):
        result = _summarise_accuracy(self.SAMPLE_LOG)
        assert "Wind" in result
        assert "underforecasts" in result  # negative bias

    def test_contains_wave_info(self):
        result = _summarise_accuracy(self.SAMPLE_LOG)
        assert "Wave Hs" in result

    def test_contains_run_count(self):
        result = _summarise_accuracy(self.SAMPLE_LOG)
        assert "2 verified runs" in result or "last 2" in result

    def test_averages_correctly(self):
        result = _summarise_accuracy(self.SAMPLE_LOG)
        # Temp MAE = (1.2 + 1.4) / 2 = 1.3
        assert "1.3" in result

    def test_uses_last_10_only(self):
        # Create 15 entries
        big_log = [
            {
                "init_utc": f"2026-03-{i:02d}T00:00:00+00:00",
                "temp_mae_c": float(i),
                "temp_bias_c": 0.0,
                "wind_mae_kt": 3.0,
                "wind_bias_kt": 0.0,
            }
            for i in range(1, 16)
        ]
        result = _summarise_accuracy(big_log)
        assert "last 10" in result


class TestBuildUserPromptWithAccuracy:
    def _make_wrf(self):
        return {
            "meta": {"init_utc": "2026-03-20T00:00:00+00:00"},
            "records": [
                {
                    "valid_utc": "2026-03-20T00:00:00+00:00",
                    "temp_c": 22.0,
                    "wind_kt": 12.0,
                    "wind_dir": 45,
                }
            ],
        }

    def test_accuracy_included_in_prompt(self):
        log = [{"temp_mae_c": 1.5, "temp_bias_c": 0.5,
                "wind_mae_kt": 3.0, "wind_bias_kt": -1.0}]
        prompt = build_user_prompt(self._make_wrf(), None, None, accuracy_log=log)
        assert "model accuracy" in prompt.lower() or "Recent model" in prompt

    def test_no_accuracy_without_log(self):
        prompt = build_user_prompt(self._make_wrf(), None, None, accuracy_log=None)
        assert "accuracy" not in prompt.lower()

    def test_no_accuracy_with_empty_log(self):
        prompt = build_user_prompt(self._make_wrf(), None, None, accuracy_log=[])
        assert "accuracy" not in prompt.lower()


class TestBuildUserPromptWithCWAObs:
    def _make_wrf(self):
        return {
            "meta": {"init_utc": "2026-03-20T00:00:00+00:00"},
            "records": [
                {
                    "valid_utc": "2026-03-20T00:00:00+00:00",
                    "temp_c": 22.0,
                    "wind_kt": 12.0,
                    "wind_dir": 45,
                }
            ],
        }

    def test_cwa_station_included(self):
        cwa_obs = {
            "station": {
                "obs_time": "2026-03-20T00:00:00+00:00",
                "temp_c": 20.5,
                "wind_kt": 8.0,
                "wind_dir": 225,
                "gust_kt": 12.0,
                "pressure_hpa": 1013.2,
                "humidity_pct": 78,
            },
        }
        prompt = build_user_prompt(self._make_wrf(), None, None, cwa_obs=cwa_obs)
        assert "CWA Keelung station" in prompt
        assert "20.5" in prompt
        assert "humidity=78" in prompt

    def test_cwa_buoy_included(self):
        cwa_obs = {
            "buoy": {
                "buoy_name": "龍洞",
                "obs_time": "2026-03-20T00:00:00+00:00",
                "wave_height_m": 1.2,
                "peak_period_s": 12.3,
                "wave_dir": 45,
                "water_temp_c": 21.5,
            },
        }
        prompt = build_user_prompt(self._make_wrf(), None, None, cwa_obs=cwa_obs)
        assert "CWA wave buoy" in prompt
        assert "1.2m" in prompt
        assert "龍洞" in prompt

    def test_cwa_warnings_included(self):
        cwa_obs = {
            "warnings": [
                {
                    "type": "Gale Warning",
                    "description": "Strong winds in northern Taiwan waters",
                }
            ],
        }
        prompt = build_user_prompt(self._make_wrf(), None, None, cwa_obs=cwa_obs)
        assert "CWA WARNING" in prompt
        assert "Gale Warning" in prompt

    def test_no_cwa_obs(self):
        prompt = build_user_prompt(self._make_wrf(), None, None, cwa_obs=None)
        assert "CWA" not in prompt

    def test_empty_cwa_obs(self):
        prompt = build_user_prompt(self._make_wrf(), None, None, cwa_obs={})
        assert "Real-time observations" not in prompt


class TestBuildUserPromptWithEnsemble:
    def _make_wrf(self):
        return {
            "meta": {"init_utc": "2026-03-20T00:00:00+00:00"},
            "records": [
                {
                    "valid_utc": "2026-03-20T00:00:00+00:00",
                    "temp_c": 22.0,
                    "wind_kt": 12.0,
                }
            ],
        }

    def test_ensemble_spread_included(self):
        ensemble = {
            "spread": {
                "wind_spread_kt": 4.5,
                "temp_spread_c": 2.0,
                "precip_spread_mm": 3.0,
            },
        }
        prompt = build_user_prompt(self._make_wrf(), None, None, ensemble=ensemble)
        assert "ensemble spread" in prompt.lower()
        assert "4.5" in prompt
        assert "confidence" in prompt.lower()

    def test_high_confidence_wind(self):
        ensemble = {"spread": {"wind_spread_kt": 1.5}}
        prompt = build_user_prompt(self._make_wrf(), None, None, ensemble=ensemble)
        assert "high" in prompt.lower()

    def test_low_confidence_wind(self):
        ensemble = {"spread": {"wind_spread_kt": 8.0}}
        prompt = build_user_prompt(self._make_wrf(), None, None, ensemble=ensemble)
        assert "low" in prompt.lower()

    def test_no_ensemble(self):
        prompt = build_user_prompt(self._make_wrf(), None, None, ensemble=None)
        assert "ensemble" not in prompt.lower()


class TestBuildUserPromptWithSpotObs:
    def _make_wrf(self):
        return {
            "meta": {"init_utc": "2026-03-20T00:00:00+00:00"},
            "records": [{"valid_utc": "2026-03-20T00:00:00+00:00",
                         "temp_c": 22.0, "wind_kt": 12.0}],
        }

    def test_spot_obs_included(self):
        cwa_obs = {
            "spot_obs": {
                "fulong": {
                    "station": {
                        "station_id": "466950", "temp_c": 21.5,
                        "wind_kt": 6.0, "distance_km": 5.0,
                        "obs_time": "2026-03-20T00:00:00+00:00",
                    },
                    "buoy": {
                        "buoy_id": "46694A", "wave_height_m": 0.8,
                        "distance_km": 15.0,
                        "obs_time": "2026-03-20T00:00:00+00:00",
                    },
                }
            },
            "station": {"obs_time": "2026-03-20T00:00:00+00:00",
                        "temp_c": 20.0, "wind_kt": 5.0, "wind_dir": 180,
                        "gust_kt": 8.0, "pressure_hpa": 1013.0,
                        "humidity_pct": 75},
        }
        prompt = build_user_prompt(self._make_wrf(), None, None,
                                   cwa_obs=cwa_obs)
        assert "Per-spot CWA obs" in prompt
        assert "fulong" in prompt
        assert "466950" in prompt
        assert "46694A" in prompt

    def test_no_spot_obs(self):
        cwa_obs = {"station": {"obs_time": "2026-03-20T00:00:00+00:00",
                               "temp_c": 20.0, "wind_kt": 5.0,
                               "wind_dir": 180, "gust_kt": 8.0,
                               "pressure_hpa": 1013.0, "humidity_pct": 75}}
        prompt = build_user_prompt(self._make_wrf(), None, None,
                                   cwa_obs=cwa_obs)
        assert "Per-spot CWA obs" not in prompt

    def test_township_forecasts_included(self):
        cwa_obs = {
            "township_forecasts": {
                "宜蘭縣": {
                    "location": "頭城鎮",
                    "elements": {
                        "Wx": [{"value": "晴"}, {"value": "多雲"}],
                        "MaxT": [{"value": "25"}],
                    }
                }
            },
            "station": {"obs_time": "2026-03-20T00:00:00+00:00",
                        "temp_c": 20.0, "wind_kt": 5.0, "wind_dir": 180,
                        "gust_kt": 8.0, "pressure_hpa": 1013.0,
                        "humidity_pct": 75},
        }
        prompt = build_user_prompt(self._make_wrf(), None, None,
                                   cwa_obs=cwa_obs)
        assert "宜蘭縣" in prompt
