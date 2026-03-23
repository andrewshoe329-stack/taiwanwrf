"""Tests for cwa_fetch.py — CWA Open Data API integration."""

import json
from unittest.mock import patch, MagicMock

from cwa_fetch import (
    fetch_station_obs, fetch_buoy_obs, fetch_all,
    fetch_tide_obs, fetch_warnings,
    KEELUNG_STATION_ID, KEELUNG_BUOY_IDS,
    CWA_BASE, STATION_ENDPOINT, WAVE_BUOY_ENDPOINT,
    TIDE_OBS_ENDPOINT, WARNING_ENDPOINT,
)


# ── Mock CWA API responses ──────────────────────────────────────────────────

MOCK_STATION_RESPONSE = {
    "success": "true",
    "records": {
        "Station": [{
            "StationId": "466940",
            "StationName": "基隆",
            "ObsTime": {"DateTime": "2026-03-23T14:00:00+08:00"},
            "WeatherElement": {
                "AirTemperature": {"value": "22.5"},
                "WindSpeed": {"value": "3.2"},
                "WindDirection": {"value": "225"},
                "WindGust": {"value": "5.1"},
                "AirPressure": {"value": "1013.2"},
                "RelativeHumidity": {"value": "78"},
                "Now": {"value": "0.0"},
                "Weather": "Cloudy",
            },
        }],
    },
}

MOCK_BUOY_RESPONSE = {
    "success": "true",
    "records": {
        "Station": [
            {
                "StationId": "46694A",
                "StationName": "龍洞",
                "ObsTime": {"DateTime": "2026-03-23T14:00:00+08:00"},
                "WeatherElement": {
                    "SignificantWaveHeight": {"value": "1.2"},
                    "MeanWavePeriod": {"value": "8.5"},
                    "MeanWaveDirection": {"value": "45"},
                    "MaximumWaveHeight": {"value": "2.1"},
                    "PeakWavePeriod": {"value": "12.3"},
                    "SeaTemperature": {"value": "21.5"},
                },
            },
            {
                "StationId": "OTHER",
                "StationName": "Other Buoy",
                "ObsTime": {"DateTime": "2026-03-23T14:00:00+08:00"},
                "WeatherElement": {},
            },
        ],
    },
}


def _mock_urlopen(response_data):
    """Create a mock for urllib.request.urlopen that returns JSON data."""
    mock_resp = MagicMock()
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)
    mock_resp.read.return_value = json.dumps(response_data).encode()

    # json.load reads from the response object directly
    import io
    raw = json.dumps(response_data).encode()
    mock_resp = MagicMock()
    mock_resp.__enter__ = MagicMock(
        return_value=io.BytesIO(raw)
    )
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


class TestFetchStationObs:
    @patch('cwa_fetch.urllib.request.urlopen')
    def test_returns_parsed_data(self, mock_open):
        mock_open.return_value = _mock_urlopen(MOCK_STATION_RESPONSE)
        result = fetch_station_obs("test-key")
        assert result is not None
        assert result["station_id"] == "466940"
        assert result["temp_c"] == 22.5
        # Wind: 3.2 m/s * 1.94384 ≈ 6.2 kt
        assert result["wind_kt"] is not None
        assert result["wind_kt"] > 6
        assert result["wind_dir"] == 225
        assert result["pressure_hpa"] == 1013.2
        assert result["obs_time"] is not None

    @patch('cwa_fetch.urllib.request.urlopen')
    def test_handles_api_failure(self, mock_open):
        mock_open.side_effect = Exception("API timeout")
        result = fetch_station_obs("test-key")
        assert result is None

    @patch('cwa_fetch.urllib.request.urlopen')
    def test_handles_empty_response(self, mock_open):
        mock_open.return_value = _mock_urlopen({"success": "true", "records": {"Station": []}})
        result = fetch_station_obs("test-key")
        assert result is None


class TestFetchBuoyObs:
    @patch('cwa_fetch.urllib.request.urlopen')
    def test_returns_parsed_data(self, mock_open):
        mock_open.return_value = _mock_urlopen(MOCK_BUOY_RESPONSE)
        result = fetch_buoy_obs("test-key")
        assert result is not None
        assert result["buoy_id"] == "46694A"
        assert result["wave_height_m"] == 1.2
        assert result["wave_period_s"] == 8.5
        assert result["wave_dir"] == 45
        assert result["water_temp_c"] == 21.5
        assert result["peak_period_s"] == 12.3

    @patch('cwa_fetch.urllib.request.urlopen')
    def test_finds_correct_buoy(self, mock_open):
        """Should find the buoy matching KEELUNG_BUOY_IDS, not the other one."""
        mock_open.return_value = _mock_urlopen(MOCK_BUOY_RESPONSE)
        result = fetch_buoy_obs("test-key")
        assert result is not None
        assert result["buoy_id"] == "46694A"  # not "OTHER"

    @patch('cwa_fetch.urllib.request.urlopen')
    def test_handles_api_failure(self, mock_open):
        mock_open.side_effect = Exception("Network error")
        result = fetch_buoy_obs("test-key")
        assert result is None

    @patch('cwa_fetch.urllib.request.urlopen')
    def test_handles_no_matching_buoy(self, mock_open):
        resp = {
            "success": "true",
            "records": {
                "Station": [{
                    "StationId": "UNKNOWN",
                    "StationName": "Remote Buoy",
                    "ObsTime": {"DateTime": "2026-03-23T14:00:00+08:00"},
                    "WeatherElement": {},
                }],
            },
        }
        mock_open.return_value = _mock_urlopen(resp)
        result = fetch_buoy_obs("test-key")
        assert result is None


class TestFetchAll:
    @patch('cwa_fetch.fetch_buoy_obs')
    @patch('cwa_fetch.fetch_station_obs')
    def test_returns_combined(self, mock_station, mock_buoy):
        mock_station.return_value = {"temp_c": 22.5, "obs_time": "2026-03-23T06:00:00+00:00"}
        mock_buoy.return_value = {"wave_height_m": 1.2, "obs_time": "2026-03-23T06:00:00+00:00"}
        result = fetch_all("test-key")
        assert result["source"] == "CWA Open Data"
        assert result["station"]["temp_c"] == 22.5
        assert result["buoy"]["wave_height_m"] == 1.2

    @patch('cwa_fetch.fetch_buoy_obs')
    @patch('cwa_fetch.fetch_station_obs')
    def test_handles_partial_failure(self, mock_station, mock_buoy):
        mock_station.return_value = {"temp_c": 22.5, "obs_time": "2026-03-23T06:00:00+00:00"}
        mock_buoy.return_value = None
        result = fetch_all("test-key")
        assert result["station"] is not None
        assert result["buoy"] is None


MOCK_TIDE_RESPONSE = {
    "success": "true",
    "records": {
        "Station": [{
            "StationId": "KL01",
            "StationName": "基隆",
            "ObsTime": {"DateTime": "2026-03-23T14:00:00+08:00"},
            "WeatherElement": {
                "TideHeight": {"value": "0.85"},
            },
        }],
    },
}

MOCK_WARNING_RESPONSE = {
    "success": "true",
    "records": {
        "record": [{
            "datasetDescription": "豪雨特報",
            "phenomena": "Heavy Rain",
            "significance": "warning",
            "affectedAreas": "基隆市,新北市",
            "startTime": "2026-03-23T06:00:00+08:00",
            "endTime": "2026-03-24T06:00:00+08:00",
            "contents": {"content": {"contentText": "北部地區有豪雨 Heavy rain in northern Taiwan"}},
        }],
    },
}


class TestFetchTideObs:
    @patch('cwa_fetch.urllib.request.urlopen')
    def test_returns_parsed_data(self, mock_open):
        mock_open.return_value = _mock_urlopen(MOCK_TIDE_RESPONSE)
        result = fetch_tide_obs("test-key")
        assert result is not None
        assert result["station_id"] == "KL01"
        assert result["tide_height_m"] == 0.85
        assert result["obs_time"] is not None

    @patch('cwa_fetch.urllib.request.urlopen')
    def test_handles_api_failure(self, mock_open):
        mock_open.side_effect = Exception("API timeout")
        result = fetch_tide_obs("test-key")
        assert result is None

    @patch('cwa_fetch.urllib.request.urlopen')
    def test_handles_empty_response(self, mock_open):
        mock_open.return_value = _mock_urlopen({"success": "true", "records": {"Station": []}})
        result = fetch_tide_obs("test-key")
        assert result is None


class TestFetchWarnings:
    @patch('cwa_fetch.urllib.request.urlopen')
    def test_returns_relevant_warnings(self, mock_open):
        mock_open.return_value = _mock_urlopen(MOCK_WARNING_RESPONSE)
        result = fetch_warnings("test-key")
        assert len(result) == 1
        assert result[0]["type"] == "Heavy Rain"
        assert result[0]["severity"] == "warning"
        assert "基隆" in result[0]["area"]

    @patch('cwa_fetch.urllib.request.urlopen')
    def test_handles_api_failure(self, mock_open):
        mock_open.side_effect = Exception("Network error")
        result = fetch_warnings("test-key")
        assert result == []

    @patch('cwa_fetch.urllib.request.urlopen')
    def test_filters_irrelevant_areas(self, mock_open):
        resp = {
            "success": "true",
            "records": {
                "record": [{
                    "datasetDescription": "Warning",
                    "affectedAreas": "高雄市,屏東縣",
                    "contents": "Southern Taiwan warning",
                }],
            },
        }
        mock_open.return_value = _mock_urlopen(resp)
        result = fetch_warnings("test-key")
        assert len(result) == 0

    @patch('cwa_fetch.urllib.request.urlopen')
    def test_empty_warnings(self, mock_open):
        mock_open.return_value = _mock_urlopen({"success": "true", "records": {"record": []}})
        result = fetch_warnings("test-key")
        assert result == []


class TestFetchAllExpanded:
    @patch('cwa_fetch.fetch_warnings')
    @patch('cwa_fetch.fetch_tide_obs')
    @patch('cwa_fetch.fetch_buoy_obs')
    @patch('cwa_fetch.fetch_station_obs')
    def test_returns_all_sources(self, mock_station, mock_buoy, mock_tide, mock_warnings):
        mock_station.return_value = {"temp_c": 22.5, "obs_time": "2026-03-23T06:00:00+00:00"}
        mock_buoy.return_value = {"wave_height_m": 1.2, "obs_time": "2026-03-23T06:00:00+00:00"}
        mock_tide.return_value = {"tide_height_m": 0.85, "obs_time": "2026-03-23T06:00:00+00:00"}
        mock_warnings.return_value = [{"type": "Gale", "severity": "warning"}]
        result = fetch_all("test-key")
        assert result["station"] is not None
        assert result["buoy"] is not None
        assert result["tide"] is not None
        assert len(result["warnings"]) == 1


class TestConstants:
    def test_station_id(self):
        assert KEELUNG_STATION_ID == "466940"

    def test_buoy_ids_not_empty(self):
        assert len(KEELUNG_BUOY_IDS) > 0

    def test_endpoints_defined(self):
        assert STATION_ENDPOINT
        assert WAVE_BUOY_ENDPOINT
        assert TIDE_OBS_ENDPOINT
        assert WARNING_ENDPOINT
