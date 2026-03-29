import { useState, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { SPOTS, REGIONS } from '@/lib/constants'
import { useForecastData } from '@/hooks/useForecastData'
import { SurfHeatmap } from '@/components/spots/SurfHeatmap'
import { WeatherWarnings } from '@/components/layout/WeatherWarnings'
import { DataFreshness } from '@/components/layout/DataFreshness'
import {
  ratingColorClass, windColorClass, waveColorClass,
  windType, windTypeColorClass,
} from '@/lib/forecast-utils'
import type { Region, SpotRating } from '@/lib/types'

const ALL_REGIONS = ['all', ...REGIONS] as const
type FilterRegion = 'all' | Region

export function SpotsPage() {
  const { t, i18n } = useTranslation()
  const lang = i18n.language as 'en' | 'zh'
  const data = useForecastData()
  const [activeRegion, setActiveRegion] = useState<FilterRegion>('all')

  const filtered = activeRegion === 'all'
    ? SPOTS
    : SPOTS.filter(s => s.region === activeRegion)

  // Build lookup: spot id -> current rating + conditions
  const spotData = useMemo(() => {
    const map: Record<string, { rating: string; score: number; current?: SpotRating }> = {}
    if (!data.surf?.spots) return map
    for (const sf of data.surf.spots) {
      const best = sf.daily_best?.[0]
      const currentRating = sf.ratings?.[0]
      if (best) {
        map[sf.spot.id] = { rating: best.rating, score: best.score, current: currentRating }
      }
    }
    return map
  }, [data.surf])

  // Find the best spot right now
  const bestSpot = useMemo(() => {
    let best: { spotId: string; score: number; rating: string } | null = null
    for (const [id, d] of Object.entries(spotData)) {
      if (!best || d.score > best.score) {
        best = { spotId: id, score: d.score, rating: d.rating }
      }
    }
    return best && best.score >= 4 ? best : null // Only show if at least marginal
  }, [spotData])

  const bestSpotInfo = bestSpot ? SPOTS.find(s => s.id === bestSpot.spotId) : undefined
  const bestSpotCurrent = bestSpot ? spotData[bestSpot.spotId]?.current : undefined

  return (
    <div className="px-4 pt-4 pb-24 max-w-screen-xl mx-auto">
      <div className="flex items-start justify-between mb-4">
        <h1 className="text-lg font-semibold text-[var(--color-text-primary)]">{t('spots.title')}</h1>
        <DataFreshness />
      </div>

      {/* Weather Warnings */}
      <WeatherWarnings />

      {/* Best spot right now banner */}
      {bestSpotInfo && bestSpotCurrent && (
        <Link
          to={`/spots/${bestSpot!.spotId}`}
          className={`block border rounded-xl p-4 mb-5 no-underline transition-colors hover:border-[var(--color-border-active)] ${
            bestSpot!.rating === 'firing'
              ? 'border-[var(--color-firing)]/30 bg-[var(--color-firing-bg)]'
              : bestSpot!.rating === 'good'
                ? 'border-[var(--color-rating-good)]/20 bg-[rgba(94,234,212,0.05)]'
                : 'border-[var(--color-border)]'
          }`}
        >
          <div className="flex items-center justify-between mb-2">
            <span className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">{t('spots.best_now')}</span>
            <span className={`text-sm font-semibold ${ratingColorClass(bestSpot!.rating)}`}>
              {t(`rating.${bestSpot!.rating}`)}
              <span className="text-[var(--color-text-dim)] font-normal ml-1 text-xs">{bestSpot!.score}/14</span>
            </span>
          </div>
          <p className="text-base font-semibold text-[var(--color-text-primary)]">
            {bestSpotInfo.name[lang]}
            <span className="text-sm text-[var(--color-text-muted)] ml-2">{bestSpotInfo.name[lang === 'en' ? 'zh' : 'en']}</span>
          </p>
          <div className="flex items-center gap-4 mt-2 text-xs">
            {bestSpotCurrent.wind_kt != null && (
              <span className={`tabular-nums ${windColorClass(bestSpotCurrent.wind_kt)}`}>
                {bestSpotCurrent.wind_kt.toFixed(0)} kt
                {bestSpotCurrent.wind_dir != null && (
                  <span className={`ml-1 ${windTypeColorClass(windType(bestSpotCurrent.wind_dir, bestSpotInfo.facing))}`}>
                    {windType(bestSpotCurrent.wind_dir, bestSpotInfo.facing)}
                  </span>
                )}
              </span>
            )}
            {bestSpotCurrent.swell_height != null && (
              <span className={`tabular-nums ${waveColorClass(bestSpotCurrent.swell_height)}`}>
                {bestSpotCurrent.swell_height.toFixed(1)} m
                {bestSpotCurrent.swell_period != null && (
                  <span className="text-[var(--color-text-muted)]"> @ {bestSpotCurrent.swell_period.toFixed(0)}s</span>
                )}
              </span>
            )}
          </div>
        </Link>
      )}

      {/* Region filter pills */}
      <div className="flex gap-2 overflow-x-auto pb-3 mb-4 scrollbar-none" style={{ scrollbarWidth: 'none' }}>
        {ALL_REGIONS.map(region => {
          const active = region === activeRegion
          return (
            <button
              key={region}
              onClick={() => setActiveRegion(region)}
              className={`shrink-0 px-4 py-1.5 rounded-full text-xs font-medium transition-colors border ${
                active
                  ? 'bg-[var(--color-text-primary)] text-[var(--color-bg)] border-[var(--color-text-primary)]'
                  : 'bg-transparent text-[var(--color-text-secondary)] border-[var(--color-border)] hover:border-[var(--color-border-active)]'
              }`}
            >
              {t(`region.${region}`)}
            </button>
          )
        })}
      </div>

      {/* Surf heatmap calendar */}
      {data.surf?.spots && data.surf.spots.length > 0 && (
        <SurfHeatmap spots={data.surf.spots} filter={activeRegion} />
      )}

      {/* Spots grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {filtered.map(spot => {
          const info = spotData[spot.id]
          const cr = info?.current
          const wt = cr?.wind_dir != null ? windType(cr.wind_dir, spot.facing) : undefined
          return (
            <Link
              key={spot.id}
              to={`/spots/${spot.id}`}
              className="block border border-[var(--color-border)] rounded-xl p-4 hover:border-[var(--color-border-active)] hover:bg-[var(--color-bg-hover)] transition-colors no-underline"
            >
              <div className="flex items-start justify-between mb-2">
                <div>
                  <h2 className="text-sm font-semibold text-[var(--color-text-primary)] leading-tight">
                    {spot.name[lang]}
                  </h2>
                  <p className="text-xs text-[var(--color-text-muted)] mt-0.5">
                    {spot.name[lang === 'en' ? 'zh' : 'en']}
                  </p>
                </div>
                {info && <RatingBadge rating={info.rating} t={t} />}
              </div>
              {/* Conditions with color */}
              {cr && (cr.wind_kt != null || cr.swell_height != null) && (
                <div className="flex items-center gap-3 mt-2 text-xs">
                  {cr.wind_kt != null && (
                    <span className={`tabular-nums font-medium ${windColorClass(cr.wind_kt)}`}>
                      {cr.wind_kt.toFixed(0)} kt
                    </span>
                  )}
                  {wt && (
                    <span className={`text-[10px] ${windTypeColorClass(wt)}`}>{wt}</span>
                  )}
                  {cr.swell_height != null && (
                    <span className={`tabular-nums ${waveColorClass(cr.swell_height)}`}>
                      {cr.swell_height.toFixed(1)} m
                      {cr.swell_period != null && (
                        <span className="text-[var(--color-text-muted)]"> @ {cr.swell_period.toFixed(0)}s</span>
                      )}
                    </span>
                  )}
                </div>
              )}
              <div className="flex items-center gap-3 mt-2">
                <span className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">
                  {t(`region.${spot.region}`)}
                </span>
                <span className="text-[var(--color-text-dim)]">·</span>
                <span className="text-[10px] text-[var(--color-text-muted)]">{spot.facing}</span>
              </div>
            </Link>
          )
        })}
      </div>

      {filtered.length === 0 && (
        <div className="text-center py-12">
          <p className="text-sm text-[var(--color-text-muted)]">{t('spots.no_data')}</p>
        </div>
      )}
    </div>
  )
}

function RatingBadge({ rating, t }: { rating: string; t: (key: string) => string }) {
  const colorMap: Record<string, string> = {
    firing:    'bg-[var(--color-firing-bg)] text-[var(--color-firing)]',
    good:      'bg-[rgba(94,234,212,0.15)] text-[var(--color-rating-good)]',
    marginal:  'bg-[rgba(251,191,36,0.1)] text-[var(--color-rating-marginal)]',
    poor:      'bg-[var(--color-bg-elevated)] text-[var(--color-rating-poor)]',
    flat:      'bg-[var(--color-bg-elevated)] text-[var(--color-rating-flat)]',
    dangerous: 'bg-[rgba(248,113,113,0.15)] text-[var(--color-rating-dangerous)]',
  }
  return (
    <span className={`text-[10px] font-medium px-2 py-0.5 rounded-full ${colorMap[rating] ?? ''}`}>
      {t(`rating.${rating}`)}
    </span>
  )
}
