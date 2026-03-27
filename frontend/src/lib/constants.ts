import type { SpotInfo, HarbourInfo, Region } from './types'

// ── Taiwan bounding box ──────────────────────────────────────────────────────

export const TAIWAN_BBOX = {
  lat_min: 21.5,
  lat_max: 25.5,
  lon_min: 119.0,
  lon_max: 122.5,
}

export const TAIWAN_CENTER: [number, number] = [121.0, 23.5] // [lng, lat] for MapLibre
export const TAIWAN_ZOOM = 7.2

// ── Harbours ─────────────────────────────────────────────────────────────────

export const HARBOURS: HarbourInfo[] = [
  { id: 'keelung',   name: { en: 'Keelung',   zh: '基隆' }, lat: 25.156, lon: 121.788 },
  { id: 'kaohsiung', name: { en: 'Kaohsiung', zh: '高雄' }, lat: 22.615, lon: 120.265 },
  { id: 'taichung',  name: { en: 'Taichung',  zh: '台中' }, lat: 24.280, lon: 120.510 },
  { id: 'anping',    name: { en: 'Anping',    zh: '安平' }, lat: 22.995, lon: 120.160 },
  { id: 'magong',    name: { en: 'Magong',    zh: '馬公' }, lat: 23.565, lon: 119.580 },
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
  // East coast
  { id: 'donghe',      name: { en: 'Donghe',       zh: '東河' },   lat: 22.970, lon: 121.300, facing: 'E/SE',  region: 'east',      opt_wind: ['W','NW'],        opt_swell: ['E','SE','S'] },
  { id: 'jinzun',      name: { en: 'Jinzun',       zh: '金樽' },   lat: 22.970, lon: 121.280, facing: 'E',     region: 'east',      opt_wind: ['W','NW'],        opt_swell: ['E','NE','SE'] },
  { id: 'chenggong',   name: { en: 'Chenggong',    zh: '成功' },   lat: 23.100, lon: 121.380, facing: 'E',     region: 'east',      opt_wind: ['W','NW'],        opt_swell: ['E','SE'] },
  { id: 'dulan',       name: { en: 'Dulan',        zh: '都蘭' },   lat: 22.880, lon: 121.230, facing: 'E',     region: 'east',      opt_wind: ['W','SW'],        opt_swell: ['E','SE'] },
  // South
  { id: 'nanwan',      name: { en: 'Nanwan',       zh: '南灣' },   lat: 21.955, lon: 120.765, facing: 'S/SW',  region: 'south',     opt_wind: ['N','NE'],        opt_swell: ['S','SW','SE'] },
  { id: 'jialeshuei',  name: { en: 'Jialeshuei',   zh: '佳樂水' }, lat: 21.990, lon: 120.850, facing: 'SE/E',  region: 'south',     opt_wind: ['W','NW'],        opt_swell: ['SE','E','S'] },
  { id: 'baishawan',   name: { en: 'Baishawan',    zh: '白沙灣' }, lat: 21.945, lon: 120.710, facing: 'W',     region: 'south',     opt_wind: ['E','NE'],        opt_swell: ['W','SW'] },
]

export const REGIONS: Region[] = ['north', 'northeast', 'east', 'south']

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
