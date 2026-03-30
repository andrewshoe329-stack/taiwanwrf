/**
 * Visual breakdown of how a surf spot's score is calculated.
 * Shows 5 scoring factors as horizontal bars with a total score.
 */

import { useTranslation } from 'react-i18next'
import type { SpotRating, SpotInfo } from '@/lib/types'
import { degToCompass } from '@/lib/forecast-utils'

const DIR_ANGLES: Record<string, number> = {
  N: 0, NNE: 22.5, NE: 45, ENE: 67.5,
  E: 90, ESE: 112.5, SE: 135, SSE: 157.5,
  S: 180, SSW: 202.5, SW: 225, WSW: 247.5,
  W: 270, WNW: 292.5, NW: 315, NNW: 337.5,
}

/** Circular distance between two angles in degrees */
function circularDist(a: number, b: number): number {
  const d = Math.abs(a - b) % 360
  return d > 180 ? 360 - d : d
}

/** Compute facing angle from the spot's facing string (e.g. "NE/E") */
function facingAngle(facing: string): number {
  const parts = facing.split('/')
  const angles = parts.map(p => DIR_ANGLES[p.trim()] ?? 0)
  const sinSum = angles.reduce((s, a) => s + Math.sin((a * Math.PI) / 180), 0)
  const cosSum = angles.reduce((s, a) => s + Math.cos((a * Math.PI) / 180), 0)
  const avg = (Math.atan2(sinSum, cosSum) * 180) / Math.PI
  return (avg + 360) % 360
}

/** Check if wind direction is offshore for the spot */
function isOffshore(windDir: number, fAngle: number): 'offshore' | 'cross' | 'onshore' {
  // Offshore = wind blowing from land to sea, i.e. wind dir ~opposite to facing
  const diff = circularDist(windDir, fAngle)
  if (diff >= 135) return 'offshore'
  if (diff >= 60) return 'cross'
  return 'onshore'
}

interface ScoreFactors {
  swellDir: { score: number; max: number; label: string }
  windDir: { score: number; max: number; label: string }
  windSpeed: { score: number; max: number; label: string }
  swellHeight: { score: number; max: number; label: string }
  wavePeriod: { score: number; max: number; label: string }
}

function computeFactors(rating: SpotRating, spot: SpotInfo): ScoreFactors {
  const fAngle = facingAngle(spot.facing)

  // Swell direction match: compare against opt_swell
  let swellDirScore = 0
  let swellDirLabel = '--'
  if (rating.swell_dir != null) {
    const swellCompass = degToCompass(rating.swell_dir)
    const isGood = spot.opt_swell.some(d => {
      const optAngle = DIR_ANGLES[d]
      return optAngle !== undefined && circularDist(rating.swell_dir!, optAngle) <= 22.5
    })
    const isOk = !isGood && spot.opt_swell.some(d => {
      const optAngle = DIR_ANGLES[d]
      return optAngle !== undefined && circularDist(rating.swell_dir!, optAngle) <= 45
    })
    swellDirScore = isGood ? 4 : isOk ? 2 : 0
    swellDirLabel = `${swellCompass} (${rating.swell_dir}°)`
  }

  // Wind direction (offshore): check if wind is offshore for spot's facing
  let windDirScore = 0
  let windDirLabel = '--'
  if (rating.wind_dir != null) {
    const windStatus = isOffshore(rating.wind_dir, fAngle)
    windDirScore = windStatus === 'offshore' ? 3 : windStatus === 'cross' ? 1 : 0
    const windCompass = degToCompass(rating.wind_dir)
    windDirLabel = `${windCompass} (${windStatus})`
  }

  // Wind speed
  let windSpeedScore = 0
  let windSpeedLabel = '--'
  if (rating.wind_kt != null) {
    const wk = rating.wind_kt
    if (wk < 10) {
      windSpeedScore = 2
    } else if (wk < 15) {
      windSpeedScore = 1
    } else if (rating.wind_dir != null) {
      const windStatus = isOffshore(rating.wind_dir, fAngle)
      if (windStatus === 'onshore' && wk > 22) {
        windSpeedScore = -2
      }
    }
    windSpeedLabel = `${rating.wind_kt} kt`
  }

  // Swell height
  let swellHeightScore = 0
  let swellHeightLabel = '--'
  if (rating.swell_height != null) {
    const sh = rating.swell_height
    if (sh >= 0.6 && sh <= 2.5) {
      swellHeightScore = 3
    } else if (sh > 0.3) {
      swellHeightScore = 1
    }
    swellHeightLabel = `${rating.swell_height.toFixed(1)} m`
  }

  // Wave period
  let wavePeriodScore = 0
  let wavePeriodLabel = '--'
  if (rating.swell_period != null) {
    if (rating.swell_period >= 12) {
      wavePeriodScore = 2
    } else if (rating.swell_period >= 9) {
      wavePeriodScore = 1
    }
    wavePeriodLabel = `${rating.swell_period.toFixed(1)} s`
  }

  return {
    swellDir: { score: swellDirScore, max: 4, label: swellDirLabel },
    windDir: { score: windDirScore, max: 3, label: windDirLabel },
    windSpeed: { score: windSpeedScore, max: 2, label: windSpeedLabel },
    swellHeight: { score: swellHeightScore, max: 3, label: swellHeightLabel },
    wavePeriod: { score: wavePeriodScore, max: 2, label: wavePeriodLabel },
  }
}

const RATING_COLORS: Record<string, string> = {
  firing: 'var(--color-firing)',
  great: 'var(--color-rating-good)',
  good: 'var(--color-rating-good)',
  marginal: 'var(--color-rating-marginal)',
  poor: 'var(--color-rating-poor)',
  flat: 'var(--color-text-dim)',
  dangerous: 'var(--color-rating-dangerous)',
}

interface ScoreBreakdownProps {
  rating: SpotRating
  spot: SpotInfo
}

export function ScoreBreakdown({ rating, spot }: ScoreBreakdownProps) {
  const { t } = useTranslation()
  const factors = computeFactors(rating, spot)
  const totalScore = rating.score
  const ratingLabel = rating.rating ? t(`rating.${rating.rating}`, rating.rating) : '--'
  const ratingColor = (rating.rating ? RATING_COLORS[rating.rating] : undefined) ?? 'var(--color-text-dim)'

  const rows: Array<{ name: string; factor: { score: number; max: number; label: string } }> = [
    { name: t('spots.score_swell_dir'), factor: factors.swellDir },
    { name: t('spots.score_wind_dir'), factor: factors.windDir },
    { name: t('spots.score_wind_speed'), factor: factors.windSpeed },
    { name: t('spots.score_swell_height'), factor: factors.swellHeight },
    { name: t('spots.score_wave_period'), factor: factors.wavePeriod },
  ]

  return (
    <div className="space-y-3">
      {rows.map(({ name, factor }) => (
        <FactorBar key={name} name={name} score={factor.score} max={factor.max} label={factor.label} />
      ))}

      {/* Total */}
      <div className="flex items-center justify-between pt-3 mt-1 border-t border-[var(--color-border)]">
        <span className="text-xs text-[var(--color-text-secondary)] font-medium">Total</span>
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-[var(--color-text-primary)]">
            {totalScore}/14
          </span>
          <span
            className="text-[10px] uppercase tracking-wider font-medium px-2 py-0.5 rounded-full"
            style={{
              color: ratingColor,
              border: `1px solid ${ratingColor}`,
            }}
          >
            {ratingLabel}
          </span>
        </div>
      </div>
    </div>
  )
}

function FactorBar({ name, score, max, label }: { name: string; score: number; max: number; label: string }) {
  const isNegative = score < 0
  const absScore = Math.abs(score)
  const fillPct = max > 0 ? (absScore / max) * 100 : 0

  let barColor: string
  if (isNegative) {
    barColor = 'var(--color-danger)'
  } else if (score === 0) {
    barColor = 'var(--color-text-muted)'
  } else {
    barColor = 'var(--color-text-primary)'
  }

  const scoreDisplay = isNegative ? `${score}` : `+${score}`
  // Center point for bidirectional bar (negative extends left, positive extends right)
  const centerPct = isNegative ? 50 : 0

  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <span className="text-[11px] text-[var(--color-text-secondary)]">{name}</span>
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-[var(--color-text-muted)]">{label}</span>
          <span
            className="text-[11px] font-medium w-6 text-right"
            style={{ color: barColor }}
          >
            {scoreDisplay}
          </span>
        </div>
      </div>
      <div className="relative h-1 rounded-full bg-[var(--color-bg-elevated)] overflow-hidden">
        {isNegative && (
          <div className="absolute top-0 h-full w-[1px] bg-[var(--color-text-dim)]" style={{ left: '50%' }} />
        )}
        <div
          className="absolute top-0 h-full rounded-full transition-all duration-300"
          style={{
            left: isNegative ? `${centerPct - fillPct / 2}%` : '0%',
            width: `${isNegative ? fillPct / 2 : fillPct}%`,
            backgroundColor: barColor,
          }}
        />
      </div>
    </div>
  )
}
