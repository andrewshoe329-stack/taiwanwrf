"""Tests for surf_forecast.py helper functions and rating logic."""


from datetime import datetime, timezone, timedelta

from surf_forecast import (
    deg_diff, compass, dir_quality, _safe_get, _score_timestep,
    day_rating, sail_day_rating, _recommend, generate_planner_json,
    best_time_for_day, classify_tide, tide_score,
    SPOTS, MIN_SWELL_HEIGHT_M, MAX_SWELL_HEIGHT_M, MAX_WIND_KT,
    LIGHT_WIND_KT, ONSHORE_WIND_KT,
)


# ── _safe_get ────────────────────────────────────────────────────────────────

class TestSafeGet:
    def test_valid_index(self):
        assert _safe_get([10, 20, 30], 1) == 20

    def test_out_of_bounds(self):
        assert _safe_get([10, 20], 5) is None

    def test_none_list(self):
        assert _safe_get(None, 0) is None

    def test_empty_list(self):
        assert _safe_get([], 0) is None

    def test_first_element(self):
        assert _safe_get([42], 0) == 42


# ── deg_diff ─────────────────────────────────────────────────────────────────

class TestDegDiff:
    def test_same_direction(self):
        assert deg_diff(0, 0) == 0

    def test_opposite(self):
        assert deg_diff(0, 180) == 180

    def test_wrap_around(self):
        assert deg_diff(350, 10) == 20

    def test_symmetric(self):
        assert deg_diff(90, 270) == deg_diff(270, 90)

    def test_small_difference(self):
        assert abs(deg_diff(45, 50) - 5) < 1e-9


# ── compass ──────────────────────────────────────────────────────────────────

class TestCompass:
    def test_north(self):
        assert compass(0) == 'N'

    def test_east(self):
        assert compass(90) == 'E'

    def test_south(self):
        assert compass(180) == 'S'

    def test_west(self):
        assert compass(270) == 'W'

    def test_none(self):
        assert compass(None) == '—'

    def test_northeast(self):
        assert compass(45) == 'NE'

    def test_wrap_360(self):
        assert compass(360) == 'N'


# ── dir_quality ──────────────────────────────────────────────────────────────

class TestDirQuality:
    def test_good_match(self):
        assert dir_quality(180, ['S']) == 'good'

    def test_ok_match(self):
        assert dir_quality(210, ['S']) == 'ok'  # 30° off — between 22.5 and 45

    def test_poor_match(self):
        assert dir_quality(0, ['S']) == 'poor'  # 180° off

    def test_none_direction(self):
        assert dir_quality(None, ['S']) == 'unknown'

    def test_multiple_optimal(self):
        assert dir_quality(45, ['N', 'NE', 'E']) == 'good'


# ── day_rating ───────────────────────────────────────────────────────────────

class TestDayRating:
    SPOT = SPOTS[0]  # Fulong

    def test_no_data(self):
        r = day_rating([], self.SPOT)
        assert r['label'] == 'No data'

    def test_flat(self):
        recs = [{'sw_hs': 0.1, 'wind': 5}]
        r = day_rating(recs, self.SPOT)
        assert r['label'] == 'Flat'

    def test_dangerous_swell(self):
        recs = [{'sw_hs': 5.0, 'wind': 10, 'sw_dir': 45, 'w_dir': 180, 'sw_tp': 10}]
        r = day_rating(recs, self.SPOT)
        assert r['label'] == 'Dangerous'

    def test_dangerous_wind(self):
        recs = [{'sw_hs': 1.0, 'wind': 35, 'sw_dir': 45, 'w_dir': 180, 'sw_tp': 10}]
        r = day_rating(recs, self.SPOT)
        assert r['label'] == 'Dangerous'

    def test_good_conditions(self):
        # Good swell from NE, light offshore wind from SW, long period
        recs = [{'sw_hs': 1.5, 'wind': 5, 'sw_dir': 45, 'w_dir': 225, 'sw_tp': 14}]
        r = day_rating(recs, self.SPOT)
        assert r['label'] in ('Firing!', 'Good')

    def test_all_none_fields(self):
        recs = [{'sw_hs': None, 'wind': None, 'sw_dir': None, 'w_dir': None, 'sw_tp': None}]
        r = day_rating(recs, self.SPOT)
        assert r['label'] in ('Flat', 'No data', 'Poor')

    def test_marginal_boundary(self):
        # Moderate swell, onshore wind, short period → should be Marginal or Poor
        recs = [{'sw_hs': 0.8, 'wind': 12, 'sw_dir': 90, 'w_dir': 90, 'sw_tp': 8}]
        r = day_rating(recs, self.SPOT)
        assert r['label'] in ('Marginal', 'Poor', 'Good')


# ── sail_day_rating ──────────────────────────────────────────────────────────

class TestSailDayRating:
    def test_no_data(self):
        r = sail_day_rating([])
        assert r['label'] == '—'

    def test_good_conditions(self):
        recs = [{'wind': 10, 'gust': 15, 'hs': 0.5, 'rain6h': 0}]
        r = sail_day_rating(recs)
        assert 'Good' in r['label']

    def test_nogo_gust(self):
        recs = [{'wind': 20, 'gust': 40, 'hs': 1.0, 'rain6h': 0}]
        r = sail_day_rating(recs)
        assert 'No-go' in r['label']

    def test_nogo_wave(self):
        recs = [{'wind': 10, 'gust': 15, 'hs': 3.0, 'rain6h': 0}]
        r = sail_day_rating(recs)
        assert 'No-go' in r['label']


# ── Constants sanity ─────────────────────────────────────────────────────────

class TestConstants:
    def test_thresholds_ordered(self):
        assert MIN_SWELL_HEIGHT_M < MAX_SWELL_HEIGHT_M
        assert LIGHT_WIND_KT < ONSHORE_WIND_KT < MAX_WIND_KT

    def test_spots_have_required_keys(self):
        for spot in SPOTS:
            assert 'name' in spot
            assert 'lat' in spot
            assert 'lon' in spot
            assert 'opt_wind' in spot
            assert 'opt_swell' in spot


# ── _recommend ──────────────────────────────────────────────────────────────

class TestRecommend:
    """Tests for the _recommend() recommendation logic."""

    def _sail(self, emoji, label):
        return {'emoji': emoji, 'label': label, 'bg': '#000', 'col': '#fff'}

    def _surf(self, emoji, label):
        return {'emoji': emoji, 'label': label, 'bg': '#000', 'col': '#fff'}

    def test_sail_and_fire_surf(self):
        text, bg = _recommend(self._sail('🟢', 'Good'), self._surf('🔥', 'Firing!'), 'Fulong')
        assert '⛵' in text and '🏄' in text and 'Fulong' in text
        assert bg == '#0d2d1a'

    def test_sail_and_good_surf(self):
        text, bg = _recommend(self._sail('🟢', 'Good'), self._surf('🟢', 'Good'), 'Jinshan')
        assert '⛵' in text and 'Jinshan' in text

    def test_sail_only(self):
        text, bg = _recommend(self._sail('🟢', 'Good'), self._surf('😴', 'Flat'), 'Fulong')
        assert text == '⛵ Go sailing'
        assert bg == '#0d2d1a'

    def test_fire_surf_no_sail(self):
        text, bg = _recommend(self._sail('🔴', 'No-go'), self._surf('🔥', 'Firing!'), 'Daxi')
        assert '🏄' in text and 'Daxi' in text

    def test_marginal_both(self):
        text, bg = _recommend(self._sail('🟡', 'Marginal'), self._surf('🟡', 'Marginal'), 'Wushih')
        assert '🟡' in text and 'Wushih' in text
        assert bg == '#3d2e00'

    def test_marginal_sail_only(self):
        text, bg = _recommend(self._sail('🟡', 'Marginal'), self._surf('😴', 'Flat'), 'Fulong')
        assert 'Marginal sailing' in text

    def test_stay_home(self):
        text, bg = _recommend(self._sail('🔴', 'No-go'), self._surf('🔴', 'Poor'), 'Fulong')
        assert text == '🔴 Stay home'
        assert bg == '#3d1515'


# ── generate_planner_json ──────────────────────────────────────────────────

class TestGeneratePlannerJson:
    """Tests for generate_planner_json() sidecar data output."""

    SPOT = SPOTS[0]  # Fulong

    def _make_spot_data(self, days=None):
        """Create minimal all_spot_data for one spot over given date keys."""
        if days is None:
            days = ['2026-03-22']
        records = []
        for dk in days:
            records.append({
                'dk': dk, 'sw_hs': 1.2, 'wind': 8, 'sw_dir': 45,
                'w_dir': 225, 'sw_tp': 12, 'hs': 0.8,
            })
        return [{'spot': self.SPOT, 'records': records}]

    def _make_keelung(self, days=None):
        """Create minimal keelung_records."""
        if days is None:
            days = ['2026-03-22']
        return [
            {'dk': dk, 'wind': 10, 'gust': 15, 'hs': 0.5, 'rain6h': 0}
            for dk in days
        ]

    def test_basic_structure(self):
        result = generate_planner_json(self._make_spot_data(), self._make_keelung())
        assert 'days' in result
        assert '2026-03-22' in result['days']

    def test_day_has_required_keys(self):
        result = generate_planner_json(self._make_spot_data(), self._make_keelung())
        day = result['days']['2026-03-22']
        assert 'sail' in day
        assert 'best_surf' in day
        assert 'recommendation' in day

    def test_sail_rating_populated(self):
        result = generate_planner_json(self._make_spot_data(), self._make_keelung())
        sail = result['days']['2026-03-22']['sail']
        assert 'label' in sail
        assert 'emoji' in sail

    def test_best_surf_populated(self):
        result = generate_planner_json(self._make_spot_data(), self._make_keelung())
        bs = result['days']['2026-03-22']['best_surf']
        assert 'spot' in bs
        assert 'label' in bs
        assert 'emoji' in bs

    def test_recommendation_populated(self):
        result = generate_planner_json(self._make_spot_data(), self._make_keelung())
        rec = result['days']['2026-03-22']['recommendation']
        assert 'text' in rec
        assert 'bg' in rec

    def test_multiple_days(self):
        days = ['2026-03-22', '2026-03-23', '2026-03-24']
        result = generate_planner_json(self._make_spot_data(days), self._make_keelung(days))
        assert len(result['days']) == 3
        for dk in days:
            assert dk in result['days']

    def test_no_keelung_records(self):
        result = generate_planner_json(self._make_spot_data(), None)
        assert 'days' in result
        day = result['days']['2026-03-22']
        assert day['sail']['label'] == '—'  # no data → dash

    def test_empty_spot_data(self):
        result = generate_planner_json([{'spot': self.SPOT, 'records': []}])
        assert result == {'days': {}}

    def test_spot_times_in_output(self):
        """Planner JSON should include spot_times with best window per spot."""
        dt1 = datetime(2026, 3, 22, 6, 0, tzinfo=timezone.utc)
        records = [{
            'dk': '2026-03-22',
            'dt_utc': dt1,
            'dt_cst': dt1 + timedelta(hours=8),
            'sw_hs': 1.2, 'wind': 8, 'sw_dir': 45,
            'w_dir': 225, 'sw_tp': 12, 'hs': 0.8, 'gust': 12, 'rain6h': 0,
        }]
        spot_data = [{'spot': self.SPOT, 'records': records}]
        result = generate_planner_json(spot_data, None)
        day = result['days']['2026-03-22']
        assert 'spot_times' in day
        assert len(day['spot_times']) >= 1
        assert 'window' in day['spot_times'][0]
        assert 'tide_class' in day['spot_times'][0]


# ── _score_timestep ─────────────────────────────────────────────────────────

class TestScoreTimestep:
    SPOT = SPOTS[0]  # Fulong

    def test_good_conditions_high_score(self):
        r = {'sw_hs': 1.5, 'wind': 5, 'sw_dir': 45, 'w_dir': 225, 'sw_tp': 14}
        score = _score_timestep(r, self.SPOT)
        assert score >= 9  # Should be Firing!-range

    def test_flat_conditions_low_score(self):
        r = {'sw_hs': 0.1, 'wind': 5, 'sw_dir': 45, 'w_dir': 225, 'sw_tp': 5}
        score = _score_timestep(r, self.SPOT)
        assert score < 7

    def test_tide_bonus_for_jinshan(self):
        """Jinshan prefers mid tide — mid tide should score higher than low tide."""
        jinshan = SPOTS[2]  # Jinshan, opt_tide='mid'
        r = {'sw_hs': 1.0, 'wind': 8, 'sw_dir': 45, 'w_dir': 225, 'sw_tp': 10}
        score_mid  = _score_timestep(r, jinshan, tide_height_m=0.45)  # mid
        score_low  = _score_timestep(r, jinshan, tide_height_m=0.10)  # low
        assert score_mid > score_low

    def test_no_tide_penalty_for_any(self):
        """Fulong accepts any tide — score should not change with tide."""
        r = {'sw_hs': 1.0, 'wind': 8, 'sw_dir': 45, 'w_dir': 225, 'sw_tp': 10}
        score_low  = _score_timestep(r, self.SPOT, tide_height_m=0.10)
        score_high = _score_timestep(r, self.SPOT, tide_height_m=0.80)
        assert score_low == score_high


# ── best_time_for_day ────────────────────────────────────────────────────────

class TestBestTimeForDay:
    SPOT = SPOTS[0]  # Fulong

    def _make_recs(self, hours=(0, 6, 12, 18)):
        """Create records at given UTC hours on 2026-03-22."""
        recs = []
        for h in hours:
            dt_utc = datetime(2026, 3, 22, h, 0, tzinfo=timezone.utc)
            recs.append({
                'dk': '2026-03-22',
                'dt_utc': dt_utc,
                'dt_cst': dt_utc + timedelta(hours=8),
                'sw_hs': 1.0, 'sw_tp': 10, 'sw_dir': 45,
                'wind': 8, 'w_dir': 225, 'gust': 12,
                'hs': 0.8, 'rain6h': 0,
            })
        return recs

    def test_returns_dict(self):
        recs = self._make_recs()
        bt = best_time_for_day(recs, self.SPOT)
        assert bt is not None
        assert 'window' in bt
        assert 'score' in bt
        assert 'tide_height_m' in bt
        assert 'tide_class' in bt

    def test_returns_none_for_flat(self):
        recs = [{'dk': '2026-03-22', 'sw_hs': 0.05, 'wind': 5}]
        bt = best_time_for_day(recs, self.SPOT)
        assert bt is None

    def test_returns_none_for_empty(self):
        assert best_time_for_day([], self.SPOT) is None

    def test_returns_none_for_dangerous(self):
        recs = [{'dk': '2026-03-22', 'sw_hs': 5.0, 'wind': 10}]
        bt = best_time_for_day(recs, self.SPOT)
        assert bt is None

    def test_window_format(self):
        recs = self._make_recs()
        bt = best_time_for_day(recs, self.SPOT)
        assert bt is not None
        assert 'CST' in bt['window']

    def test_picks_best_timestep(self):
        """Should pick the timestep with best conditions."""
        dt_bad = datetime(2026, 3, 22, 0, 0, tzinfo=timezone.utc)
        dt_good = datetime(2026, 3, 22, 6, 0, tzinfo=timezone.utc)
        recs = [
            {
                'dk': '2026-03-22', 'dt_utc': dt_bad,
                'dt_cst': dt_bad + timedelta(hours=8),
                'sw_hs': 0.3, 'sw_tp': 5, 'sw_dir': 180,  # poor swell direction for Fulong
                'wind': 20, 'w_dir': 90, 'gust': 25,  # onshore wind
                'hs': 0.5, 'rain6h': 5,
            },
            {
                'dk': '2026-03-22', 'dt_utc': dt_good,
                'dt_cst': dt_good + timedelta(hours=8),
                'sw_hs': 1.5, 'sw_tp': 14, 'sw_dir': 45,  # ideal NE swell
                'wind': 5, 'w_dir': 225, 'gust': 8,  # light offshore SW
                'hs': 1.2, 'rain6h': 0,
            },
        ]
        bt = best_time_for_day(recs, self.SPOT)
        assert bt is not None
        assert bt['dt_utc'] == dt_good

    def test_tide_info_populated(self):
        recs = self._make_recs()
        bt = best_time_for_day(recs, self.SPOT)
        assert bt is not None
        assert bt['tide_height_m'] is not None
        assert bt['tide_class'] in ('low', 'mid', 'high')
        assert 'm' in bt['tide_str']


# ── classify_tide ────────────────────────────────────────────────────────────

class TestClassifyTide:
    def test_low(self):
        assert classify_tide(0.15) == 'low'

    def test_mid(self):
        assert classify_tide(0.45) == 'mid'

    def test_high(self):
        assert classify_tide(0.75) == 'high'

    def test_none(self):
        assert classify_tide(None) == 'unknown'

    def test_boundary_low_mid(self):
        assert classify_tide(0.30) == 'mid'  # 0.30 is >= _TIDE_LOW_MAX

    def test_boundary_mid_high(self):
        assert classify_tide(0.60) == 'mid'  # 0.60 is not > _TIDE_HIGH_MIN


# ── tide_score ───────────────────────────────────────────────────────────────

class TestTideScore:
    def test_any_always_zero(self):
        assert tide_score('low', 'any') == 0
        assert tide_score('high', 'any') == 0

    def test_match(self):
        assert tide_score('mid', 'mid') == 1

    def test_opposite(self):
        assert tide_score('low', 'high') == -1
        assert tide_score('high', 'low') == -1

    def test_partial_match(self):
        assert tide_score('low', 'low-mid') == 1
        assert tide_score('mid', 'low-mid') == 1

    def test_unknown_tide(self):
        assert tide_score('unknown', 'mid') == 0
