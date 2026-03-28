"""Tests for notify.py — alert checking and formatting (no network calls)."""

from notify import check_alerts, format_notification, THRESHOLDS


class TestCheckAlerts:
    def _wrf(self, records):
        return {"meta": {"init_utc": "2026-03-22T00:00:00+00:00"}, "records": records}

    def test_no_alerts(self):
        wrf = self._wrf([{"valid_utc": "2026-03-22T00:00:00+00:00",
                          "wind_kt": 10, "gust_kt": 15, "precip_mm_6h": 1}])
        assert check_alerts(wrf) == []

    def test_gale_warning(self):
        wrf = self._wrf([{"valid_utc": "2026-03-22T00:00:00+00:00",
                          "wind_kt": 30, "gust_kt": 40, "precip_mm_6h": 0}])
        alerts = check_alerts(wrf)
        assert any(a['type'] == 'gale_warning' for a in alerts)
        assert any(a['severity'] == 'danger' for a in alerts)

    def test_strong_wind(self):
        wrf = self._wrf([{"valid_utc": "2026-03-22T00:00:00+00:00",
                          "wind_kt": 25, "gust_kt": 28, "precip_mm_6h": 0}])
        alerts = check_alerts(wrf)
        assert any(a['type'] == 'strong_wind' for a in alerts)

    def test_heavy_rain(self):
        wrf = self._wrf([{"valid_utc": "2026-03-22T00:00:00+00:00",
                          "wind_kt": 5, "gust_kt": 8, "precip_mm_6h": 20}])
        alerts = check_alerts(wrf)
        assert any(a['type'] == 'heavy_rain' for a in alerts)

    def test_dangerous_seas(self):
        wave = {"ecmwf_wave": {"records": [
            {"valid_utc": "2026-03-22T00:00:00+00:00", "wave_height": 4.0}
        ]}}
        alerts = check_alerts(self._wrf([]), wave)
        assert any(a['type'] == 'dangerous_seas' for a in alerts)

    def test_high_seas(self):
        wave = {"ecmwf_wave": {"records": [
            {"valid_utc": "2026-03-22T00:00:00+00:00", "wave_height": 3.0}
        ]}}
        alerts = check_alerts(self._wrf([]), wave)
        assert any(a['type'] == 'high_seas' for a in alerts)

    def test_dedup_per_day(self):
        """Multiple alerts of same type on same day → keep only one per type."""
        wrf = self._wrf([
            {"valid_utc": "2026-03-22T00:00:00+00:00", "wind_kt": 25, "gust_kt": 28, "precip_mm_6h": 0},
            {"valid_utc": "2026-03-22T06:00:00+00:00", "wind_kt": 30, "gust_kt": 40, "precip_mm_6h": 0},
        ])
        alerts = check_alerts(wrf)
        # strong_wind and gale_warning are different types, both kept
        wind_alerts = [a for a in alerts if a['type'] in ('gale_warning', 'strong_wind')]
        assert len(wind_alerts) == 2
        types = {a['type'] for a in wind_alerts}
        assert 'gale_warning' in types
        assert 'strong_wind' in types

    def test_same_type_dedup(self):
        """Two gale_warning alerts on the same day should be deduped to one."""
        wrf = self._wrf([
            {"valid_utc": "2026-03-22T00:00:00+00:00", "wind_kt": 30, "gust_kt": 40, "precip_mm_6h": 0},
            {"valid_utc": "2026-03-22T12:00:00+00:00", "wind_kt": 32, "gust_kt": 45, "precip_mm_6h": 0},
        ])
        alerts = check_alerts(wrf)
        gale_alerts = [a for a in alerts if a['type'] == 'gale_warning']
        assert len(gale_alerts) == 1
        # Dedup keeps first occurrence when severity is equal
        assert gale_alerts[0]['value'] == 40

    def test_empty_records(self):
        assert check_alerts(self._wrf([])) == []

    def test_none_values(self):
        wrf = self._wrf([{"valid_utc": "2026-03-22T00:00:00+00:00",
                          "wind_kt": None, "gust_kt": None, "precip_mm_6h": None}])
        assert check_alerts(wrf) == []


class TestFormatNotification:
    def test_empty_alerts(self):
        assert format_notification([]) == ''

    def test_basic_format(self):
        alerts = [{"type": "gale_warning", "severity": "danger",
                   "message": "Gale: 40kt gusts", "valid_utc": "2026-03-22T00:00:00+00:00",
                   "value": 40}]
        msg = format_notification(alerts, "2026-03-22T00:00:00+00:00")
        assert 'Alert' in msg
        assert 'DANGER' in msg
        assert '40kt' in msg

    def test_includes_init_time(self):
        alerts = [{"type": "test", "severity": "warning",
                   "message": "test msg", "valid_utc": "", "value": 0}]
        msg = format_notification(alerts, "2026-03-22T12:00:00+00:00")
        assert '2026-03-22' in msg

    def test_mixed_severities(self):
        alerts = [
            {"type": "gale", "severity": "danger", "message": "Gale",
             "valid_utc": "", "value": 0},
            {"type": "rain", "severity": "warning", "message": "Rain",
             "valid_utc": "", "value": 0},
        ]
        msg = format_notification(alerts)
        assert 'DANGER' in msg
        assert 'WARNING' in msg


class TestThresholds:
    def test_thresholds_are_positive(self):
        for key, val in THRESHOLDS.items():
            assert val > 0, f"{key} should be positive"

    def test_gale_above_strong(self):
        assert THRESHOLDS['gale_wind_kt'] > THRESHOLDS['strong_wind_kt']

    def test_dangerous_above_high(self):
        assert THRESHOLDS['dangerous_seas_m'] > THRESHOLDS['high_seas_m']
