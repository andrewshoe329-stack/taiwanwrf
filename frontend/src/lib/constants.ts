import type { SpotInfo, HarbourInfo, Region } from './types'

// ── Taiwan bounding box ──────────────────────────────────────────────────────

export const TAIWAN_BBOX = {
  lat_min: 24.5,
  lat_max: 25.5,
  lon_min: 121.0,
  lon_max: 122.5,
}

export const TAIWAN_CENTER: [number, number] = [121.75, 25.0] // [lng, lat] for MapLibre
export const TAIWAN_ZOOM = 9.5

// ── Harbours ─────────────────────────────────────────────────────────────────

export const HARBOURS: HarbourInfo[] = [
  { id: 'keelung',   name: { en: 'Keelung',   zh: '基隆' }, lat: 25.156, lon: 121.788 },
]

// ── Surf spots ───────────────────────────────────────────────────────────────

export const SPOTS: SpotInfo[] = [
  // North
  { id: 'fulong',      name: { en: 'Fulong',      zh: '福隆' },   lat: 25.019, lon: 121.940, facing: 'NE/E',  region: 'north',     opt_wind: ['S','SW'],        opt_swell: ['N','NE','E'] },
  { id: 'greenbay',    name: { en: 'Green Bay',    zh: '翡翠灣' }, lat: 25.189, lon: 121.686, facing: 'NE',    region: 'north',     opt_wind: ['W','SW'],        opt_swell: ['E','NE'] },
  { id: 'jinshan',     name: { en: 'Jinshan',      zh: '金山' },   lat: 25.238, lon: 121.638, facing: 'NE',    region: 'north',     opt_wind: ['S','SW'],        opt_swell: ['N','NNE','NE','E','ESE'] },
  // Northeast
  { id: 'daxi',        name: { en: 'Daxi',         zh: '大溪' },   lat: 24.870, lon: 121.930, facing: 'SE',    region: 'northeast', opt_wind: ['NW','W'],        opt_swell: ['SE','SSE','S','E'] },
  { id: 'wushih',      name: { en: 'Wushih',       zh: '烏石' },   lat: 24.862, lon: 121.921, facing: 'E',     region: 'northeast', opt_wind: ['NW','W'],        opt_swell: ['E','SE','SSE'] },
  { id: 'doublelions', name: { en: 'Double Lions',  zh: '雙獅' },   lat: 24.847, lon: 121.917, facing: 'E',     region: 'northeast', opt_wind: ['W','SW'],        opt_swell: ['ENE','E','SE','SSE'] },
  { id: 'chousui',     name: { en: 'Chousui',      zh: '臭水' },   lat: 24.820, lon: 121.899, facing: 'E',     region: 'northeast', opt_wind: ['WSW','W'],       opt_swell: ['ENE','E','ESE'] },
]

export const REGIONS: Region[] = ['north', 'northeast']

// ── Beaufort scale ───────────────────────────────────────────────────────────

export const BEAUFORT_SCALE = [
  { force: 0, min: 0,  max: 1,   label: 'Calm' },
  { force: 1, min: 1,  max: 3,   label: 'Light air' },
  { force: 2, min: 4,  max: 6,   label: 'Light breeze' },
  { force: 3, min: 7,  max: 10,  label: 'Gentle breeze' },
  { force: 4, min: 11, max: 16,  label: 'Moderate breeze' },
  { force: 5, min: 17, max: 21,  label: 'Fresh breeze' },
  { force: 6, min: 22, max: 27,  label: 'Strong breeze' },
  { force: 7, min: 28, max: 33,  label: 'Near gale' },
  { force: 8, min: 34, max: 40,  label: 'Gale' },
  { force: 9, min: 41, max: 47,  label: 'Strong gale' },
  { force: 10, min: 48, max: 55, label: 'Storm' },
  { force: 11, min: 56, max: 63, label: 'Violent storm' },
  { force: 12, min: 64, max: 999, label: 'Hurricane' },
]

// ── Data file paths ──────────────────────────────────────────────────────────

export const DATA_BASE = '/data'
export const DATA_FILES = {
  keelung:  `${DATA_BASE}/keelung.json`,
  ecmwf:    `${DATA_BASE}/ecmwf.json`,
  wave:     `${DATA_BASE}/wave.json`,
  tide:     `${DATA_BASE}/tide.json`,
  ensemble: `${DATA_BASE}/ensemble.json`,
  surf:     `${DATA_BASE}/surf.json`,
  cwa_obs:  `${DATA_BASE}/cwa_obs.json`,
  accuracy: `${DATA_BASE}/accuracy.json`,
  summary:  `${DATA_BASE}/summary.json`,
  // Multi-harbour data (per-harbour ECMWF, wave, ensemble)
  ecmwf_harbours:    `${DATA_BASE}/ecmwf_harbours.json`,
  wave_harbours:     `${DATA_BASE}/wave_harbours.json`,
  ensemble_harbours: `${DATA_BASE}/ensemble_harbours.json`,
  // Wind grids
  wind_grid_wrf:   `${DATA_BASE}/wind_grid_wrf.json`,
  wind_grid_ecmwf: `${DATA_BASE}/wind_grid_ecmwf.json`,
  wind_grid_gfs:   `${DATA_BASE}/wind_grid_gfs.json`,
}
