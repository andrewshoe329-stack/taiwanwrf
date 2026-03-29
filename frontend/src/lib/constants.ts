import type { SpotInfo, HarbourInfo, Region } from './types'

// ── Taiwan bounding box ──────────────────────────────────────────────────────

export const TAIWAN_BBOX = {
  lat_min: 24.5,
  lat_max: 25.5,
  lon_min: 121.0,
  lon_max: 122.5,
}

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
  // Wind grids
  wind_grid_wrf:   `${DATA_BASE}/wind_grid_wrf.json`,
  wind_grid_ecmwf: `${DATA_BASE}/wind_grid_ecmwf.json`,
  wind_grid_gfs:   `${DATA_BASE}/wind_grid_gfs.json`,
}
