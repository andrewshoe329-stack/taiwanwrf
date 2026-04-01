import { describe, it, expect } from 'vitest'
import {
  degToCompass,
  facingAngle,
  windType,
  windTypeColorClass,
  toCST,
  formatTimeCst,
  formatDayHeader,
  getDayKey,
  groupByDay,
  sailDecision,
  surfDecision,
  windColorClass,
  waveColorClass,
  ratingColorClass,
  ratingsToForecastRecords,
  ratingsToTidePredictions,
  gfsToForecastRecords,
  getLocationAccuracy,
  gustFactorLabel,
  gustFactorColor,
  seaComfortStars,
  seaComfortLabel,
} from '../forecast-utils'
import type { SpotRating, GfsRecord, AccuracyEntry } from '../types'

// ── degToCompass ────────────────────────────────────────────────────────────

describe('degToCompass', () => {
  it('converts 0° to N', () => {
    expect(degToCompass(0)).toBe('N')
  })

  it('converts 90° to E', () => {
    expect(degToCompass(90)).toBe('E')
  })

  it('converts 180° to S', () => {
    expect(degToCompass(180)).toBe('S')
  })

  it('converts 270° to W', () => {
    expect(degToCompass(270)).toBe('W')
  })

  it('converts 45° to NE', () => {
    expect(degToCompass(45)).toBe('NE')
  })

  it('wraps 360° to N', () => {
    expect(degToCompass(360)).toBe('N')
  })
})

// ── facingAngle ─────────────────────────────────────────────────────────────

describe('facingAngle', () => {
  it('returns 45 for NE', () => {
    expect(facingAngle('NE')).toBeCloseTo(45, 0)
  })

  it('averages NE/E to ~67.5', () => {
    const angle = facingAngle('NE/E')
    expect(angle).toBeCloseTo(67.5, 0)
  })

  it('returns 0 for N', () => {
    expect(facingAngle('N')).toBeCloseTo(0, 0)
  })
})

// ── windType ────────────────────────────────────────────────────────────────

describe('windType', () => {
  it('returns offshore when wind is opposite to beach facing', () => {
    // Beach faces NE (45°), wind from SW (225°) → diff = 180° → offshore
    expect(windType(225, 'NE')).toBe('offshore')
  })

  it('returns onshore when wind matches beach facing', () => {
    // Beach faces NE, wind from NE → diff = 0° → onshore
    expect(windType(45, 'NE')).toBe('onshore')
  })

  it('returns cross for perpendicular wind', () => {
    // Beach faces E (90°), wind from N (0°) → diff = 90° → cross
    expect(windType(0, 'E')).toBe('cross')
  })
})

// ── windTypeColorClass ──────────────────────────────────────────────────────

describe('windTypeColorClass', () => {
  it('returns offshore class', () => {
    expect(windTypeColorClass('offshore')).toContain('offshore')
  })

  it('returns onshore class', () => {
    expect(windTypeColorClass('onshore')).toContain('onshore')
  })

  it('returns cross class', () => {
    expect(windTypeColorClass('cross')).toContain('cross')
  })
})

// ── toCST / formatTimeCst ───────────────────────────────────────────────────

describe('toCST', () => {
  it('adds 8 hours to UTC', () => {
    const d = toCST('2025-01-01T00:00:00+00:00')
    expect(d.getUTCHours()).toBe(8)
  })

  it('handles day rollover', () => {
    const d = toCST('2025-01-01T20:00:00+00:00')
    expect(d.getUTCHours()).toBe(4)
    expect(d.getUTCDate()).toBe(2)
  })
})

describe('formatTimeCst', () => {
  it('formats midnight UTC as 08:00 CST', () => {
    expect(formatTimeCst('2025-01-01T00:00:00+00:00')).toBe('08:00')
  })

  it('formats 16:00 UTC as 00:00 CST next day', () => {
    expect(formatTimeCst('2025-01-01T16:00:00+00:00')).toBe('00:00')
  })
})

// ── formatDayHeader ─────────────────────────────────────────────────────────

describe('formatDayHeader', () => {
  it('formats English day header', () => {
    // 2025-01-01 UTC midnight → Jan 1 CST = Wednesday
    const header = formatDayHeader('2025-01-01T00:00:00+00:00', 'en')
    expect(header).toBe('Wed 01/01')
  })

  it('formats Chinese day header', () => {
    const header = formatDayHeader('2025-01-01T00:00:00+00:00', 'zh')
    expect(header).toBe('01/01 (三)')
  })
})

// ── getDayKey ───────────────────────────────────────────────────────────────

describe('getDayKey', () => {
  it('groups by CST date', () => {
    const key = getDayKey('2025-01-01T00:00:00+00:00')
    expect(key).toBe('2025-0-1') // CST Jan 1 → month 0, date 1
  })

  it('handles day boundary correctly', () => {
    // 15:59 UTC = 23:59 CST (same day)
    const key1 = getDayKey('2025-01-01T15:59:00+00:00')
    // 16:00 UTC = 00:00 CST (next day)
    const key2 = getDayKey('2025-01-01T16:00:00+00:00')
    expect(key1).not.toBe(key2)
  })
})

// ── groupByDay ──────────────────────────────────────────────────────────────

describe('groupByDay', () => {
  it('groups records by CST day', () => {
    const records = [
      { valid_utc: '2025-01-01T00:00:00+00:00', value: 1 },
      { valid_utc: '2025-01-01T06:00:00+00:00', value: 2 },
      { valid_utc: '2025-01-01T18:00:00+00:00', value: 3 }, // next CST day
    ]
    const groups = groupByDay(records)
    expect(groups.length).toBe(2)
    expect(groups[0].items.length).toBe(2)
    expect(groups[1].items.length).toBe(1)
  })

  it('returns empty array for empty input', () => {
    expect(groupByDay([])).toEqual([])
  })
})

// ── sailDecision ────────────────────────────────────────────────────────────

describe('sailDecision', () => {
  it('returns go for moderate wind', () => {
    expect(sailDecision(15)).toBe('go')
  })

  it('returns nogo for very strong wind', () => {
    expect(sailDecision(40)).toBe('nogo')
  })

  it('returns nogo for very light wind', () => {
    expect(sailDecision(2)).toBe('nogo')
  })

  it('returns caution for moderate-high wind', () => {
    expect(sailDecision(30)).toBe('caution')
  })

  it('returns caution for light wind', () => {
    expect(sailDecision(5)).toBe('caution')
  })
})

// ── surfDecision ────────────────────────────────────────────────────────────

describe('surfDecision', () => {
  it('returns go for good conditions', () => {
    expect(surfDecision(1.0, 10)).toBe('go')
  })

  it('returns nogo for dangerous waves', () => {
    expect(surfDecision(5.0, 10)).toBe('nogo')
  })

  it('returns nogo for extreme wind', () => {
    expect(surfDecision(1.0, 35)).toBe('nogo')
  })

  it('returns caution for marginal conditions', () => {
    expect(surfDecision(3.0, 15)).toBe('caution')
  })
})

// ── windColorClass ──────────────────────────────────────────────────────────

describe('windColorClass', () => {
  it('returns muted for calm', () => {
    expect(windColorClass(3)).toContain('muted')
  })

  it('returns sky for light breeze', () => {
    expect(windColorClass(8)).toContain('sky')
  })

  it('returns emerald for moderate', () => {
    expect(windColorClass(12)).toContain('emerald')
  })

  it('returns red for storm', () => {
    expect(windColorClass(40)).toContain('red')
  })
})

// ── waveColorClass ──────────────────────────────────────────────────────────

describe('waveColorClass', () => {
  it('returns muted for small waves', () => {
    expect(waveColorClass(0.5)).toContain('muted')
  })

  it('returns red for large waves', () => {
    expect(waveColorClass(3.5)).toContain('red')
  })
})

// ── ratingColorClass ────────────────────────────────────────────────────────

describe('ratingColorClass', () => {
  it('returns firing color for firing', () => {
    expect(ratingColorClass('firing')).toContain('firing')
  })

  it('returns dim for unknown rating', () => {
    expect(ratingColorClass('unknown')).toContain('dim')
  })

  it('returns dangerous color', () => {
    expect(ratingColorClass('dangerous')).toContain('dangerous')
  })
})

// ── Conversion helpers ──────────────────────────────────────────────────────

describe('ratingsToForecastRecords', () => {
  it('maps SpotRating fields to ForecastRecord', () => {
    const ratings: SpotRating[] = [{
      valid_utc: '2025-01-01T00:00:00+00:00',
      wind_kt: 15, wind_dir: 90, gust_kt: 20,
      temp_c: 22, mslp_hpa: 1013,
      precip_mm_6h: 0, cloud_pct: 50, cape: 100,
      score: 7, rating: 'good', spot_id: 'test',
      wave_height: 1.2, swell_height: 0.8,
      swell_dir: 45, swell_period: 10,
      tide_height: 0.5,
    }]
    const result = ratingsToForecastRecords(ratings)
    expect(result).toHaveLength(1)
    expect(result[0].wind_kt).toBe(15)
    expect(result[0].temp_c).toBe(22)
  })
})

describe('ratingsToTidePredictions', () => {
  it('filters out null tide heights', () => {
    const ratings = [
      { valid_utc: 'a', tide_height: 0.5 },
      { valid_utc: 'b', tide_height: undefined },
      { valid_utc: 'c', tide_height: 1.0 },
    ] as unknown as SpotRating[]
    const result = ratingsToTidePredictions(ratings)
    expect(result).toHaveLength(2)
    expect(result[0].height_m).toBe(0.5)
  })
})

describe('gfsToForecastRecords', () => {
  it('maps GFS fields correctly', () => {
    const gfs: GfsRecord[] = [{
      valid_utc: '2025-01-01T00:00:00+00:00',
      wind_kt: 10, wind_dir: 180, gust_kt: 15,
      temp_c: 20, mslp_hpa: 1015, vis_km: 10,
    }]
    const result = gfsToForecastRecords(gfs)
    expect(result).toHaveLength(1)
    expect(result[0].vis_km).toBe(10)
  })
})

// ── getLocationAccuracy ─────────────────────────────────────────────────────

describe('getLocationAccuracy', () => {
  it('returns null for empty log', () => {
    expect(getLocationAccuracy(null, 'keelung')).toBeNull()
    expect(getLocationAccuracy([], 'keelung')).toBeNull()
  })

  it('returns last entry for matching location', () => {
    const log = [
      { location_id: 'keelung', model_id: 'WRF', temp_mae_c: 1.0 },
      { location_id: 'keelung', model_id: 'WRF', temp_mae_c: 0.8 },
    ] as unknown as AccuracyEntry[]
    const result = getLocationAccuracy(log, 'keelung')
    expect(result?.temp_mae_c).toBe(0.8)
  })

  it('filters by model_id when provided', () => {
    const log = [
      { location_id: 'keelung', model_id: 'WRF', temp_mae_c: 1.0 },
      { location_id: 'keelung', model_id: 'ECMWF', temp_mae_c: 0.5 },
    ] as unknown as AccuracyEntry[]
    const result = getLocationAccuracy(log, 'keelung', 'ECMWF')
    expect(result?.temp_mae_c).toBe(0.5)
  })

  it('defaults location_id to keelung when missing', () => {
    const log = [
      { model_id: 'WRF', temp_mae_c: 1.2 },
    ] as unknown as AccuracyEntry[]
    const result = getLocationAccuracy(log, 'keelung')
    expect(result?.temp_mae_c).toBe(1.2)
  })
})

// ── B7: gustFactorLabel / gustFactorColor ──────────────────────────────────

describe('gustFactorLabel', () => {
  it('returns null for undefined', () => {
    expect(gustFactorLabel(undefined)).toBeNull()
  })

  it('returns null for normal gust factor', () => {
    expect(gustFactorLabel(1.2)).toBeNull()
  })

  it('returns Gusty for moderate gust factor', () => {
    expect(gustFactorLabel(1.6)).toBe('Gusty')
  })

  it('returns Extreme gusts for high gust factor', () => {
    expect(gustFactorLabel(2.5)).toBe('Extreme gusts')
  })
})

describe('gustFactorColor', () => {
  it('returns empty for undefined', () => {
    expect(gustFactorColor(undefined)).toBe('')
  })

  it('returns muted for normal', () => {
    expect(gustFactorColor(1.2)).toContain('muted')
  })

  it('returns orange for moderate', () => {
    expect(gustFactorColor(1.6)).toContain('orange')
  })

  it('returns red for extreme', () => {
    expect(gustFactorColor(2.1)).toContain('red')
  })
})

// ── B8: seaComfortStars / seaComfortLabel ──────────────────────────────────

describe('seaComfortStars', () => {
  it('returns -- for undefined', () => {
    expect(seaComfortStars(undefined)).toBe('--')
  })

  it('returns 5 filled stars for comfort 5', () => {
    const result = seaComfortStars(5)
    expect(result).toBe('\u2605\u2605\u2605\u2605\u2605')
  })

  it('returns 1 filled + 4 empty for comfort 1', () => {
    const result = seaComfortStars(1)
    expect(result).toBe('\u2605\u2606\u2606\u2606\u2606')
  })

  it('returns 3 filled + 2 empty for comfort 3', () => {
    const result = seaComfortStars(3)
    expect(result).toBe('\u2605\u2605\u2605\u2606\u2606')
  })
})

describe('seaComfortLabel', () => {
  it('returns null for undefined', () => {
    expect(seaComfortLabel(undefined)).toBeNull()
  })

  it('returns Smooth for comfort 5', () => {
    expect(seaComfortLabel(5)).toBe('Smooth')
  })

  it('returns Rough for comfort 2', () => {
    expect(seaComfortLabel(2)).toBe('Rough')
  })

  it('returns Very rough for comfort 1', () => {
    expect(seaComfortLabel(1)).toBe('Very rough')
  })

  it('returns null for unknown comfort level', () => {
    expect(seaComfortLabel(0)).toBeNull()
  })
})

// ── ratingsToForecastRecords: gust_factor/squall_risk passthrough ─────────

describe('ratingsToForecastRecords passthrough', () => {
  it('includes gust_factor and squall_risk', () => {
    const ratings: SpotRating[] = [{
      valid_utc: '2025-01-01T00:00:00+00:00',
      score: 5, rating: 'marginal', spot_id: 'test',
      gust_factor: 1.8, squall_risk: true,
    }]
    const result = ratingsToForecastRecords(ratings)
    expect(result[0].gust_factor).toBe(1.8)
    expect(result[0].squall_risk).toBe(true)
  })
})
