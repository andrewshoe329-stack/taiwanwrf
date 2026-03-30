/**
 * Shared forecast utilities — extracted from duplicated logic
 * across HarboursPage, SpotDetailPage, NowPage, and SpotsPage.
 */

import type {
  ForecastRecord, SpotForecast, SpotRating,
  AccuracyEntry, GfsRecord,
} from './types'
import type { AllForecastData } from '@/hooks/useForecastData'
import type { WindModel } from '@/hooks/useModel'

// ── Compass & direction ─────────────────────────────────────────────────────

const COMPASS_DIRS = ['N','NNE','NE','ENE','E','ESE','SE','SSE','S','SSW','SW','WSW','W','WNW','NW','NNW']

/** Convert degrees (0-360) to 16-point compass abbreviation. */
export function degToCompass(deg: number): string {
  return COMPASS_DIRS[Math.round(deg / 22.5) % 16]
}

// ── Direction analysis ─────────────────────────────────────────────────────

export const DIR_ANGLES: Record<string, number> = {
  N: 0, NNE: 22.5, NE: 45, ENE: 67.5,
  E: 90, ESE: 112.5, SE: 135, SSE: 157.5,
  S: 180, SSW: 202.5, SW: 225, WSW: 247.5,
  W: 270, WNW: 292.5, NW: 315, NNW: 337.5,
}

/** Circular distance between two angles in degrees. */
function circularDist(a: number, b: number): number {
  const d = Math.abs(a - b) % 360
  return d > 180 ? 360 - d : d
}

/** Compute facing angle from a spot's facing string (e.g. "NE/E"). */
export function facingAngle(facing: string): number {
  const parts = facing.split('/')
  const angles = parts.map(p => DIR_ANGLES[p.trim()] ?? 0)
  const sinSum = angles.reduce((s, a) => s + Math.sin((a * Math.PI) / 180), 0)
  const cosSum = angles.reduce((s, a) => s + Math.cos((a * Math.PI) / 180), 0)
  const avg = (Math.atan2(sinSum, cosSum) * 180) / Math.PI
  return (avg + 360) % 360
}

export type WindType = 'offshore' | 'cross' | 'onshore'

/** Check if wind direction is offshore/cross/onshore for a given beach facing. */
export function windType(windDir: number, facing: string): WindType {
  const fAngle = facingAngle(facing)
  const diff = circularDist(windDir, fAngle)
  if (diff >= 135) return 'offshore'
  if (diff >= 60) return 'cross'
  return 'onshore'
}

/** CSS color class for wind type. */
export function windTypeColorClass(wt: WindType): string {
  if (wt === 'offshore') return 'text-[var(--color-offshore)]'
  if (wt === 'cross') return 'text-[var(--color-cross)]'
  return 'text-[var(--color-onshore)]'
}

// ── Time formatting (UTC → CST / UTC+8) ─────────────────────────────────────

/** Convert UTC ISO string to a CST Date (UTC+8, using UTC methods). */
export function toCST(utc: string): Date {
  const d = new Date(utc)
  d.setUTCHours(d.getUTCHours() + 8)
  return d
}

/** Format UTC ISO string as "HH:00" in CST. */
export function formatTimeCst(utc: string): string {
  const d = toCST(utc)
  return `${String(d.getUTCHours()).padStart(2, '0')}:00`
}

const WEEKDAYS_EN = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
const WEEKDAYS_ZH = ['日', '一', '二', '三', '四', '五', '六']

/** Format UTC ISO string as a day header like "Mon 03/29" or "03/29 (一)". */
export function formatDayHeader(utc: string, lang: 'en' | 'zh' = 'en'): string {
  const d = toCST(utc)
  const mm = String(d.getUTCMonth() + 1).padStart(2, '0')
  const dd = String(d.getUTCDate()).padStart(2, '0')
  const dayName = lang === 'zh' ? WEEKDAYS_ZH[d.getUTCDay()] : WEEKDAYS_EN[d.getUTCDay()]
  return lang === 'zh' ? `${mm}/${dd} (${dayName})` : `${dayName} ${mm}/${dd}`
}

/** Get a day key for grouping records by CST date. */
export function getDayKey(utc: string): string {
  const d = toCST(utc)
  return `${d.getUTCFullYear()}-${d.getUTCMonth()}-${d.getUTCDate()}`
}

// ── Current timestep detection ──────────────────────────────────────────────

/** Check if a timestamp is the closest past record (i.e. "current"). */
export function isCurrentTimestep(utc: string, allUtcs: string[]): boolean {
  if (!allUtcs.length) return false
  const now = Date.now()
  let closest = 0
  let closestDiff = Infinity
  for (let i = 0; i < allUtcs.length; i++) {
    const t = new Date(allUtcs[i]).getTime()
    if (isNaN(t)) continue
    const diff = now - t
    if (diff >= 0 && diff < closestDiff) {
      closestDiff = diff
      closest = i
    }
  }
  return allUtcs[closest] === utc
}

// ── Day grouping ────────────────────────────────────────────────────────────

export interface DayGroup<T> {
  dayKey: string
  dayLabel: string
  items: T[]
}

/** Group records by CST day. Each record must have a `valid_utc` string. */
export function groupByDay<T extends { valid_utc: string }>(
  records: T[],
  lang: 'en' | 'zh' = 'en',
): DayGroup<T>[] {
  const groups: DayGroup<T>[] = []
  let currentKey = ''
  for (const r of records) {
    const key = getDayKey(r.valid_utc)
    if (key !== currentKey) {
      currentKey = key
      groups.push({ dayKey: key, dayLabel: formatDayHeader(r.valid_utc, lang), items: [] })
    }
    groups[groups.length - 1].items.push(r)
  }
  return groups
}

// ── Decision logic ──────────────────────────────────────────────────────────

export type Decision = 'go' | 'caution' | 'nogo'

/** Compute sail go/caution/nogo decision from wind speed in knots. */
export function sailDecision(windKt: number): Decision {
  if (windKt >= 8 && windKt <= 25) return 'go'
  if (windKt > 35 || windKt < 4) return 'nogo'
  return 'caution'
}

/** Compute surf go/caution/nogo decision from wave height (m) and wind (kt). */
export function surfDecision(waveHt: number, windKt: number): Decision {
  if (waveHt >= 0.6 && waveHt <= 2.5 && windKt < 20) return 'go'
  if (waveHt > 4 || windKt > 30) return 'nogo'
  return 'caution'
}

// ── Color helpers ───────────────────────────────────────────────────────────

/** Tailwind text color class based on wind speed (Beaufort-ish). */
export function windColorClass(kt: number): string {
  if (kt >= 34) return 'text-red-400'
  if (kt >= 22) return 'text-orange-400'
  if (kt >= 17) return 'text-yellow-400'
  if (kt >= 11) return 'text-emerald-400'
  if (kt >= 7)  return 'text-sky-400'
  return 'text-[var(--color-text-muted)]'
}

/** Tailwind text color class based on wave height. */
export function waveColorClass(m: number): string {
  if (m >= 3.0) return 'text-red-400'
  if (m >= 2.0) return 'text-orange-400'
  if (m >= 1.0) return 'text-sky-400'
  return 'text-[var(--color-text-muted)]'
}

/** Rating → Tailwind text color class. */
export function ratingColorClass(rating: string): string {
  const map: Record<string, string> = {
    firing:    'text-[var(--color-firing)]',
    great:     'text-[var(--color-rating-good)]',
    good:      'text-[var(--color-rating-good)]',
    marginal:  'text-[var(--color-rating-marginal)]',
    poor:      'text-[var(--color-rating-poor)]',
    flat:      'text-[var(--color-text-dim)]',
    dangerous: 'text-[var(--color-rating-dangerous)]',
  }
  return map[rating] ?? 'text-[var(--color-text-dim)]'
}

// ── Location-aware data access ─────────────────────────────────────────────

/**
 * Find a spot's forecast data from the surf JSON.
 */
export function getLocationForecast(
  data: AllForecastData,
  locationId: string,
): SpotForecast | null {
  if (!data.surf?.spots) return null
  return data.surf.spots.find(s => s.spot.id === locationId) ?? null
}

/**
 * Get the best-rated surf spot right now (highest score at first timestep).
 */
export function getBestSpot(
  data: AllForecastData,
): { spotId: string; score: number; rating: string } | null {
  if (!data.surf) return null

  let best: { spotId: string; score: number; rating: string } | null = null
  for (const sf of data.surf.spots) {
    if (sf.spot.type === 'harbour') continue
    const first = sf.ratings[0]
    if (!first || first.score == null) continue
    if (!best || first.score > best.score) {
      best = { spotId: sf.spot.id, score: first.score, rating: first.rating ?? 'poor' }
    }
  }
  return best
}

/**
 * Get forecast records for a location + model combination.
 * Returns ForecastRecord[] suitable for weather charts.
 */
export function getModelRecords(
  locationId: string,
  model: WindModel,
  data: AllForecastData,
): ForecastRecord[] {
  if (model === 'wrf') {
    if (locationId === 'keelung' && data.keelung) {
      return data.keelung.records
    }
    if (data.wrf_spots?.locations?.[locationId]) {
      return data.wrf_spots.locations[locationId].records
    }
    return []
  }

  const sf = getLocationForecast(data, locationId)
  if (!sf) {
    if (locationId === 'keelung' && model === 'ecmwf' && data.ecmwf) {
      return data.ecmwf.records
    }
    return []
  }

  if (model === 'gfs') {
    return gfsToForecastRecords(sf.gfs ?? [])
  }

  return ratingsToForecastRecords(sf.ratings)
}

/** Map SpotRating[] to ForecastRecord[] for chart consumption. */
export function ratingsToForecastRecords(ratings: SpotRating[]): ForecastRecord[] {
  return ratings.map(r => ({
    valid_utc: r.valid_utc,
    wind_kt: r.wind_kt,
    wind_dir: r.wind_dir,
    gust_kt: r.gust_kt,
    temp_c: r.temp_c,
    mslp_hpa: r.mslp_hpa,
    precip_mm_6h: r.precip_mm_6h,
    cloud_pct: r.cloud_pct,
    cape: r.cape,
  }))
}

/** Map GfsRecord[] to ForecastRecord[] for chart consumption. */
export function gfsToForecastRecords(gfs: GfsRecord[]): ForecastRecord[] {
  return gfs.map(r => ({
    valid_utc: r.valid_utc,
    wind_kt: r.wind_kt,
    wind_dir: r.wind_dir,
    gust_kt: r.gust_kt,
    temp_c: r.temp_c,
    mslp_hpa: r.mslp_hpa,
    vis_km: r.vis_km,
  }))
}

/** Get most recent accuracy entry for a location and optional model. */
export function getLocationAccuracy(
  accuracyLog: AccuracyEntry[] | null,
  locationId: string,
  modelId?: string,
): AccuracyEntry | null {
  if (!accuracyLog?.length) return null
  const forLocation = accuracyLog.filter(e =>
    (e.location_id ?? 'keelung') === locationId
  )
  if (modelId) {
    const forModel = forLocation.filter(e => e.model_id === modelId)
    return forModel[forModel.length - 1] ?? null
  }
  return forLocation[forLocation.length - 1] ?? null
}
