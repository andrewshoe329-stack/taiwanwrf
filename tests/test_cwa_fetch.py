"""Tests for cwa_fetch.py — CWA Open Data API integration."""

import json
import urllib.error
from unittest.mock import patch, MagicMock

from cwa_fetch import (
    fetch_station_obs, fetch_buoy_obs, fetch_all, fetch_all_buoys,
    fetch_tide_obs, fetch_tide_forecast, fetch_township_forecast,
    fetch_warnings, find_nearest_buoy,
    _parse_buoy_station, _haversine_km,
    KEELUNG_STATION_ID, KEELUNG_BUOY_IDS,
    CWA_BASE, STATION_ENDPOINT, WAVE_BUOY_ENDPOINT,
    TIDE_OBS_ENDPOINT, TIDE_FORECAST_ENDPOINT,
    TOWNSHIP_FORECAST_ENDPOINT, WARNING_ENDPOINT,
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
        mock_open.side_effect = urllib.error.URLError("API timeout")
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
        mock_open.side_effect = urllib.error.URLError("Network error")
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
    @patch('cwa_fetch.fetch_warnings')
    @patch('cwa_fetch.fetch_township_forecast')
    @patch('cwa_fetch.fetch_tide_forecast')
    @patch('cwa_fetch.fetch_tide_obs')
    @patch('cwa_fetch.fetch_all_buoys')
    @patch('cwa_fetch.fetch_station_obs')
    def test_returns_combined(self, mock_station, mock_all_buoys, mock_tide,
                               mock_tide_fc, mock_township, mock_warn):
        mock_station.return_value = {"temp_c": 22.5, "obs_time": "2026-03-23T06:00:00+00:00"}
        mock_all_buoys.return_value = [
            {"buoy_id": "46694A", "buoy_name": "龍洞", "wave_height_m": 1.2,
             "obs_time": "2026-03-23T06:00:00+00:00", "lat": 25.1, "lon": 121.9},
        ]
        mock_tide.return_value = None
        mock_tide_fc.return_value = []
        mock_township.return_value = None
        mock_warn.return_value = []
        result = fetch_all("test-key")
        assert result["source"] == "CWA Open Data"
        assert result["station"]["temp_c"] == 22.5
        assert result["buoy"]["wave_height_m"] == 1.2
        assert len(result["all_buoys"]) == 1

    @patch('cwa_fetch.fetch_warnings')
    @patch('cwa_fetch.fetch_township_forecast')
    @patch('cwa_fetch.fetch_tide_forecast')
    @patch('cwa_fetch.fetch_tide_obs')
    @patch('cwa_fetch.fetch_all_buoys')
    @patch('cwa_fetch.fetch_station_obs')
    def test_handles_partial_failure(self, mock_station, mock_all_buoys, mock_tide,
                                      mock_tide_fc, mock_township, mock_warn):
        mock_station.return_value = {"temp_c": 22.5, "obs_time": "2026-03-23T06:00:00+00:00"}
        mock_all_buoys.return_value = []
        mock_tide.return_value = None
        mock_tide_fc.return_value = []
        mock_township.return_value = None
        mock_warn.return_value = []
        result = fetch_all("test-key")
        assert result["station"] is not None
        assert result["buoy"] is None
        assert result["all_buoys"] == []


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
        mock_open.side_effect = urllib.error.URLError("API timeout")
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
        mock_open.side_effect = urllib.error.URLError("Network error")
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


class TestFetchTideForecast:
    @patch('cwa_fetch.urllib.request.urlopen')
    def test_returns_extrema(self, mock_open):
        resp = {
            "success": "true",
            "records": {
                "TideForecasts": {
                    "Location": [{
                        "LocationName": "基隆",
                        "TimePeriods": {
                            "Daily": [{
                                "TideInfo": [
                                    {
                                        "DateTime": "2026-03-23T05:30:00+08:00",
                                        "Tide": "滿潮",
                                        "AboveLocalMSL": {"value": "0.95"},
                                    },
                                    {
                                        "DateTime": "2026-03-23T11:45:00+08:00",
                                        "Tide": "乾潮",
                                        "AboveLocalMSL": {"value": "0.15"},
                                    },
                                ],
                            }],
                        },
                    }],
                },
            },
        }
        mock_open.return_value = _mock_urlopen(resp)
        result = fetch_tide_forecast("test-key")
        assert len(result) == 2
        assert result[0]["type"] == "high"
        assert result[0]["height_m"] == 0.95
        assert result[1]["type"] == "low"
        assert result[1]["height_m"] == 0.15

    @patch('cwa_fetch.urllib.request.urlopen')
    def test_handles_api_failure(self, mock_open):
        mock_open.side_effect = urllib.error.URLError("API timeout")
        assert fetch_tide_forecast("test-key") == []

    @patch('cwa_fetch.urllib.request.urlopen')
    def test_handles_list_items_in_tide_data(self, mock_open):
        """Regression: tide_data may contain list items instead of dicts."""
        resp = {
            "success": "true",
            "records": {
                "TideForecasts": {
                    "Location": [{
                        "LocationName": "基隆",
                        "TimePeriods": {
                            "Daily": [
                                ["unexpected", "list", "item"],
                                {
                                    "TideInfo": [{
                                        "DateTime": "2026-03-23T06:00:00+08:00",
                                        "Tide": "滿潮",
                                        "AboveLocalMSL": {"value": "0.80"},
                                    }],
                                },
                            ],
                        },
                    }],
                },
            },
        }
        mock_open.return_value = _mock_urlopen(resp)
        result = fetch_tide_forecast("test-key")
        assert len(result) == 1
        assert result[0]["type"] == "high"


class TestFetchTownshipForecast:
    @patch('cwa_fetch.urllib.request.urlopen')
    def test_returns_elements(self, mock_open):
        resp = {
            "success": "true",
            "records": {
                "location": [{
                    "locationName": "基隆市",
                    "weatherElement": [
                        {
                            "elementName": "Wx",
                            "time": [
                                {"startTime": "2026-03-23T06:00:00+08:00",
                                 "elementValue": [{"value": "多雲"}]},
                            ],
                        },
                        {
                            "elementName": "MaxT",
                            "time": [
                                {"startTime": "2026-03-23T06:00:00+08:00",
                                 "elementValue": [{"value": "24"}]},
                            ],
                        },
                    ],
                }],
            },
        }
        mock_open.return_value = _mock_urlopen(resp)
        result = fetch_township_forecast("test-key")
        assert result is not None
        assert result["location"] == "基隆市"
        assert "Wx" in result["elements"]
        assert "MaxT" in result["elements"]
        assert result["elements"]["Wx"][0]["value"] == "多雲"

    @patch('cwa_fetch.urllib.request.urlopen')
    def test_handles_api_failure(self, mock_open):
        mock_open.side_effect = urllib.error.URLError("Network error")
        assert fetch_township_forecast("test-key") is None


class TestFetchAllExpanded:
    @patch('cwa_fetch.fetch_warnings')
    @patch('cwa_fetch.fetch_township_forecast')
    @patch('cwa_fetch.fetch_tide_forecast')
    @patch('cwa_fetch.fetch_tide_obs')
    @patch('cwa_fetch.fetch_all_buoys')
    @patch('cwa_fetch.fetch_station_obs')
    def test_returns_all_sources(self, mock_station, mock_all_buoys, mock_tide,
                                  mock_tide_fc, mock_township, mock_warnings):
        mock_station.return_value = {"temp_c": 22.5, "obs_time": "2026-03-23T06:00:00+00:00"}
        mock_all_buoys.return_value = [
            {"buoy_id": "46694A", "buoy_name": "龍洞", "wave_height_m": 1.2,
             "obs_time": "2026-03-23T06:00:00+00:00", "lat": 25.1, "lon": 121.9},
            {"buoy_id": "46708A", "buoy_name": "蘇澳", "wave_height_m": 0.8,
             "obs_time": "2026-03-23T06:00:00+00:00", "lat": 24.6, "lon": 121.9},
        ]
        mock_tide.return_value = {"tide_height_m": 0.85, "obs_time": "2026-03-23T06:00:00+00:00"}
        mock_tide_fc.return_value = [{"type": "high", "height_m": 0.95}]
        mock_township.return_value = {"location": "基隆市", "elements": {"Wx": []}}
        mock_warnings.return_value = [{"type": "Gale", "severity": "warning"}]
        result = fetch_all("test-key")
        assert result["station"] is not None
        assert result["buoy"] is not None
        assert result["buoy"]["buoy_id"] == "46694A"  # primary = Keelung-area
        assert len(result["all_buoys"]) == 2
        assert result["tide"] is not None
        assert len(result["tide_forecast"]) == 1
        assert result["township_forecast"] is not None
        assert len(result["warnings"]) == 1


class TestHaversine:
    def test_same_point(self):
        assert _haversine_km(25.0, 121.0, 25.0, 121.0) == 0.0

    def test_keelung_to_yilan(self):
        # Keelung (25.15, 121.79) to Wushih (24.86, 121.92) ≈ 35 km
        dist = _haversine_km(25.15, 121.79, 24.86, 121.92)
        assert 30 < dist < 40

    def test_short_distance(self):
        # ~1 degree latitude ≈ 111 km
        dist = _haversine_km(25.0, 121.0, 26.0, 121.0)
        assert 110 < dist < 112


class TestParseBuoyStation:
    def test_parses_valid_station(self):
        stn = {
            "StationId": "46694A",
            "StationName": "龍洞",
            "ObsTime": {"DateTime": "2026-03-23T14:00:00+08:00"},
            "GeoInfo": {"Latitude": "25.097", "Longitude": "121.925"},
            "WeatherElement": {
                "SignificantWaveHeight": {"value": "1.2"},
                "MeanWavePeriod": {"value": "8.5"},
                "MeanWaveDirection": {"value": "45"},
                "PeakWavePeriod": {"value": "12.3"},
                "SeaTemperature": {"value": "21.5"},
            },
        }
        result = _parse_buoy_station(stn)
        assert result is not None
        assert result["buoy_id"] == "46694A"
        assert result["wave_height_m"] == 1.2
        assert result["lat"] == 25.097
        assert result["lon"] == 121.925

    def test_returns_none_for_no_wave_data(self):
        stn = {
            "StationId": "OTHER",
            "StationName": "No Data",
            "ObsTime": {"DateTime": "2026-03-23T14:00:00+08:00"},
            "WeatherElement": {},
        }
        assert _parse_buoy_station(stn) is None


class TestFindNearestBuoy:
    def test_finds_closest(self):
        buoys = [
            {"buoy_id": "FAR", "buoy_name": "Far", "lat": 22.0, "lon": 120.0,
             "wave_height_m": 1.0},
            {"buoy_id": "NEAR", "buoy_name": "Near", "lat": 25.1, "lon": 121.9,
             "wave_height_m": 1.5},
        ]
        result = find_nearest_buoy(buoys, 25.15, 121.79)  # Keelung
        assert result is not None
        assert result["buoy_id"] == "NEAR"

    def test_respects_max_distance(self):
        buoys = [
            {"buoy_id": "FAR", "buoy_name": "Far", "lat": 22.0, "lon": 120.0,
             "wave_height_m": 1.0},
        ]
        result = find_nearest_buoy(buoys, 25.15, 121.79, max_dist_km=50)
        assert result is None  # >300km away, outside limit

    def test_empty_list(self):
        assert find_nearest_buoy([], 25.0, 121.0) is None

    def test_fallback_no_coordinates(self):
        buoys = [
            {"buoy_id": "X", "buoy_name": "NoCoord", "wave_height_m": 1.0},
        ]
        result = find_nearest_buoy(buoys, 25.0, 121.0)
        assert result is not None
        assert result["buoy_id"] == "X"  # fallback to first

    def test_multiple_buoys_for_surf_spots(self):
        """Simulate finding nearest buoy for different surf spot locations."""
        buoys = [
            {"buoy_id": "46694A", "buoy_name": "龍洞", "lat": 25.097, "lon": 121.925,
             "wave_height_m": 1.2},
            {"buoy_id": "46708A", "buoy_name": "蘇澳", "lat": 24.63, "lon": 121.87,
             "wave_height_m": 0.8},
        ]
        # Fulong (NE coast) should match Longdong
        near_fulong = find_nearest_buoy(buoys, 25.019, 121.940)
        assert near_fulong["buoy_id"] == "46694A"

        # Chousui (southern Yilan) should match Suao
        near_chousui = find_nearest_buoy(buoys, 24.820, 121.899)
        assert near_chousui["buoy_id"] == "46708A"


class TestFetchAllBuoys:
    @patch('cwa_fetch.urllib.request.urlopen')
    def test_parses_multiple_buoys(self, mock_open):
        resp = {
            "success": "true",
            "records": {
                "Station": [
                    {
                        "StationId": "46694A",
                        "StationName": "龍洞",
                        "ObsTime": {"DateTime": "2026-03-23T14:00:00+08:00"},
                        "GeoInfo": {"Latitude": "25.097", "Longitude": "121.925"},
                        "WeatherElement": {
                            "SignificantWaveHeight": {"value": "1.2"},
                            "MeanWavePeriod": {"value": "8.5"},
                        },
                    },
                    {
                        "StationId": "46708A",
                        "StationName": "蘇澳",
                        "ObsTime": {"DateTime": "2026-03-23T14:00:00+08:00"},
                        "GeoInfo": {"Latitude": "24.63", "Longitude": "121.87"},
                        "WeatherElement": {
                            "SignificantWaveHeight": {"value": "0.8"},
                            "MeanWavePeriod": {"value": "7.0"},
                        },
                    },
                    {
                        "StationId": "EMPTY",
                        "StationName": "No Data",
                        "ObsTime": {"DateTime": "2026-03-23T14:00:00+08:00"},
                        "WeatherElement": {},
                    },
                ],
            },
        }
        mock_open.return_value = _mock_urlopen(resp)
        result = fetch_all_buoys("test-key")
        assert len(result) == 2  # EMPTY filtered out (no Hs)
        assert result[0]["buoy_id"] == "46694A"
        assert result[1]["buoy_id"] == "46708A"

    @patch('cwa_fetch.urllib.request.urlopen')
    def test_handles_api_failure(self, mock_open):
        mock_open.side_effect = urllib.error.URLError("Network error")
        assert fetch_all_buoys("test-key") == []


class TestConstants:
    def test_station_id(self):
        assert KEELUNG_STATION_ID == "466940"

    def test_buoy_ids_not_empty(self):
        assert len(KEELUNG_BUOY_IDS) > 0

    def test_endpoints_defined(self):
        assert STATION_ENDPOINT
        assert WAVE_BUOY_ENDPOINT
        assert TIDE_OBS_ENDPOINT
        assert TIDE_FORECAST_ENDPOINT
        assert TOWNSHIP_FORECAST_ENDPOINT
        assert WARNING_ENDPOINT
