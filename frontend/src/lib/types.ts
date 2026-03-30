// ── Forecast data types (mirrors Python JSON contracts) ──────────────────────

export interface ForecastMeta {
  model_id: string
  init_utc: string
  source: string
}

export interface ForecastRecord {
  valid_utc: string
  fh?: number
  temp_c?: number
  wind_kt?: number
  wind_dir?: number
  gust_kt?: number
  mslp_hpa?: number
  precip_mm_6h?: number
  cloud_pct?: number
  vis_km?: number
  cape?: number
}

export interface ForecastData {
  meta: ForecastMeta
  records: ForecastRecord[]
}

export interface WaveRecord {
  valid_utc: string
  wave_height?: number
  wave_direction?: number
  wave_period?: number
  swell_wave_height?: number
  swell_wave_direction?: number
  swell_wave_period?: number
  wind_wave_height?: number
  wind_wave_direction?: number
  wind_wave_period?: number
}

export interface WaveData {
  ecmwf_wave: { meta: ForecastMeta; records: WaveRecord[] }
  cwa_wave: { meta: ForecastMeta; records: WaveRecord[] } | null
}

export interface TidePrediction {
  time_utc: string
  height_m: number
}

export interface TideExtremum {
  time_utc: string
  height_m: number
  type: 'high' | 'low'
}

export interface TideData {
  meta: { station: string; lat: number; lon: number }
  predictions: TidePrediction[]
  extrema: TideExtremum[]
}

export interface CwaTideExtremum {
  time_utc: string
  height_m: number | null
  type: 'high' | 'low'
  station_name?: string
}

export interface CwaObs {
  source: string
  fetched_utc: string
  tide_forecast_stations?: Record<string, CwaTideExtremum[]>
  station?: {
    station_id: string
    obs_time: string
    temp_c?: number
    wind_kt?: number
    wind_dir?: number
    gust_kt?: number
    pressure_hpa?: number
    humidity_pct?: number
    precip_mm?: number
  }
  buoy?: {
    buoy_id: string
    obs_time: string
    wave_height_m?: number
    wave_period_s?: number
    wave_dir?: number
    water_temp_c?: number
  }
  spot_obs?: Record<string, {
    station?: { station_id?: string; obs_time?: string; temp_c?: number; wind_kt?: number; wind_dir?: number; gust_kt?: number; pressure_hpa?: number; humidity_pct?: number; distance_km?: number }
    buoy?: { buoy_id?: string; obs_time?: string; wave_height_m?: number; wave_period_s?: number; wave_dir?: number; water_temp_c?: number; distance_km?: number }
  }>
  warnings?: Array<{
    type: string
    type_en?: string
    severity: string
    area: string
    area_en?: string
    description: string
    description_en?: string
    issued_utc: string
    expires_utc: string
  }>
}

export interface EnsembleData {
  models: Record<string, { meta: ForecastMeta; records?: ForecastRecord[]; record_count?: number }>
  spread: {
    wind_spread_kt?: number
    temp_spread_c?: number
  }
}

export interface AISummary {
  wind: { en: string; zh: string }
  waves: { en: string; zh: string }
  outlook: { en: string; zh: string }
}

export interface AccuracyEntry {
  init_utc: string
  verified_utc: string
  model_id: string
  n_compared: number
  location_id?: string
  temp_mae_c?: number
  temp_bias_c?: number
  wind_mae_kt?: number
  wind_bias_kt?: number
  wdir_mae_deg?: number
  mslp_mae_hpa?: number
  wave?: { hs_mae_m?: number; hs_bias_m?: number; tp_mae_s?: number }
  by_horizon?: Record<string, Record<string, number>>
}

// ── Wind grid for particle animation ─────────────────────────────────────────

export interface WindGrid {
  model: string
  bounds: { lat_min: number; lat_max: number; lon_min: number; lon_max: number }
  grid: { nx: number; ny: number }
  timesteps: Array<{
    valid_utc: string
    u: number[][]
    v: number[][]
  }>
}

export interface WaveGrid {
  model: string
  bounds: { lat_min: number; lat_max: number; lon_min: number; lon_max: number }
  grid: { nx: number; ny: number }
  timesteps: Array<{
    valid_utc: string
    wave_height: (number | null)[][]
    swell_height: (number | null)[][]
    swell_direction: (number | null)[][]
    swell_period: (number | null)[][]
  }>
}

// ── Surf spot types ──────────────────────────────────────────────────────────

export type Region = 'north' | 'northeast'

export type LocationType = 'spot' | 'harbour'

export interface SpotInfo {
  id: string
  type?: LocationType
  name: { en: string; zh: string }
  lat: number
  lon: number
  facing: string
  region: Region
  opt_wind: string[]
  opt_swell: string[]
}

export interface SpotRating {
  spot_id: string
  valid_utc: string
  score: number | null
  rating: 'firing' | 'great' | 'good' | 'marginal' | 'poor' | 'flat' | 'dangerous' | null
  swell_height?: number
  swell_dir?: number
  swell_period?: number
  wave_height?: number
  wind_kt?: number
  wind_dir?: number
  gust_kt?: number
  temp_c?: number
  mslp_hpa?: number
  precip_mm_6h?: number
  cloud_pct?: number
  cape?: number
  tide_height?: number
}

export interface GfsRecord {
  valid_utc: string
  wind_kt?: number
  wind_dir?: number
  gust_kt?: number
  temp_c?: number
  mslp_hpa?: number
  vis_km?: number
}

export interface SpotForecast {
  spot: SpotInfo
  ratings: SpotRating[]
  gfs?: GfsRecord[] | null
  best_times: Array<{ date: string; start_cst: string; end_cst: string; rating: string }> | null
  daily_best: Array<{ date: string; rating: string; score: number }> | null
}

export interface SurfData {
  spots: SpotForecast[]
}

// ── WRF per-spot data ───────────────────────────────────────────────────────

export interface WrfSpotsData {
  meta: ForecastMeta
  locations: Record<string, { records: ForecastRecord[] }>
}

// ── Harbour types ────────────────────────────────────────────────────────────

export interface HarbourInfo {
  id: string
  name: { en: string; zh: string }
  lat: number
  lon: number
}
