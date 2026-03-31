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
  { id: 'keelung',   name: { en: 'Keelung',   zh: '基隆' }, lat: 25.14712477291389, lon: 121.78698610321932, webcams: [{ label: '和平島', url: 'https://tw.live/cam/?id=hpdjsyx' }, { label: '八斗子', url: 'https://tw.live/cam/?id=bdzygjsyx' }] },
]

// ── Surf spots ───────────────────────────────────────────────────────────────

export const SPOTS: SpotInfo[] = [
  // North coast (W→E along coast: Jinshan → Green Bay → Fulong)
  { id: 'jinshan',     name: { en: 'Jinshan',      zh: '金山' },   lat: 25.2402433645372, lon: 121.63355732190196, facing: 'NE',    region: 'north',     opt_wind: ['S','SW'],        opt_swell: ['N','NNE','NE','E','ESE'], webcams: [{ label: '中角灣', url: 'https://tw.live/cam/?id=zhongjiaobay' }] },
  { id: 'greenbay',    name: { en: 'Green Bay',    zh: '翡翠灣' }, lat: 25.18952488598986, lon: 121.68580407087968, facing: 'NE',    region: 'north',     opt_wind: ['W','SW'],        opt_swell: ['E','NE'] },
  { id: 'fulong',      name: { en: 'Fulong',      zh: '福隆' },   lat: 25.02389886806093, lon: 121.94298998527262, facing: 'NE/E',  region: 'north',     opt_wind: ['S','SW'],        opt_swell: ['N','NE','E'], webcams: [{ label: '福隆', url: 'https://www.necoast-nsa.gov.tw/Live-Streaming-Content.aspx?a=3299&l=1' }] },
  // NE coast (N→S along coast: Daxi → Double Lions → Wushih → Chousui)
  { id: 'daxi',        name: { en: 'Daxi',         zh: '大溪' },   lat: 24.93284050868701, lon: 121.88580048320033, facing: 'SE',    region: 'northeast', opt_wind: ['NW','W'],        opt_swell: ['SE','SSE','S','E'] },
  { id: 'doublelions', name: { en: 'Double Lions',  zh: '雙獅' },   lat: 24.888936271482883, lon: 121.85002306336393, facing: 'E',     region: 'northeast', opt_wind: ['W','SW'],        opt_swell: ['ENE','E','SE','SSE'], webcams: [{ label: '外澳沙灘', url: 'https://tw.live/cam/?id=waiaobeach' }, { label: '東北角', url: 'https://www.necoast-nsa.gov.tw/Live-Streaming-Content.aspx?a=3298&l=1' }] },
  { id: 'wushih',      name: { en: 'Wushih',       zh: '烏石' },   lat: 24.8722775159955, lon: 121.84152686026746, facing: 'E',     region: 'northeast', opt_wind: ['NW','W'],        opt_swell: ['E','SE','SSE'], webcams: [{ label: 'CWA 外澳', url: 'https://tw.live/cam/?id=zyqxjylwajsyx1' }, { label: 'CWA 外澳2', url: 'https://tw.live/cam/?id=zyqxjylwajsyx2' }] },
  { id: 'chousui',     name: { en: 'Chousui',      zh: '臭水' },   lat: 24.857077333437765, lon: 121.83333064075161, facing: 'E',     region: 'northeast', opt_wind: ['WSW','W'],       opt_swell: ['ENE','E','ESE'] },
]

// ── All locations (spots + harbours) ────────────────────────────────────────

export const ALL_LOCATIONS: SpotInfo[] = [
  { id: 'keelung', type: 'harbour', name: { en: 'Keelung Harbour', zh: '基隆港' }, lat: 25.14712477291389, lon: 121.78698610321932, facing: '', region: 'north', opt_wind: [], opt_swell: [] },
  ...SPOTS,
]

export const REGIONS: Region[] = ['north', 'northeast']

// Spot → nearest CWA tide forecast station (F-A0021-001 LocationName)
export const SPOT_TIDE_STATION: Record<string, string> = {
  keelung:     '基隆市中正區',
  jinshan:     '新北市金山區',
  greenbay:    '新北市萬里區',
  fulong:      '新北市貢寮區',
  daxi:        '宜蘭縣頭城鎮',
  doublelions: '宜蘭縣頭城鎮',
  wushih:      '宜蘭縣頭城鎮',
  chousui:     '宜蘭縣頭城鎮',
}

// Spot → nearest CWA tide observation station (O-B0075-001 StationID)
export const SPOT_TIDE_OBS_STATION: Record<string, string> = {
  keelung:     'C4B01',
  jinshan:     'C4A03',
  greenbay:    'C4B01',
  fulong:      'C4A05',
  daxi:        'C4U02',
  doublelions: 'C4U02',
  wushih:      'C4U02',
  chousui:     'C4U02',
}

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
  wrf_spots: `${DATA_BASE}/wrf_spots.json`,
  // Wind grids
  wind_grid_wrf:   `${DATA_BASE}/wind_grid_wrf.json`,
  wind_grid_ecmwf: `${DATA_BASE}/wind_grid_ecmwf.json`,
  wind_grid_gfs:   `${DATA_BASE}/wind_grid_gfs.json`,
  // Wave grid (heatmap overlay)
  wave_grid:       `${DATA_BASE}/wave_grid.json`,
  // Current grid (particle overlay)
  current_grid:    `${DATA_BASE}/current_grid.json`,
}
