import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { SPOTS, REGIONS } from '@/lib/constants'
import { useForecastData } from '@/hooks/useForecastData'
import { SurfHeatmap } from '@/components/spots/SurfHeatmap'
import type { Region } from '@/lib/types'

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

  // Build a lookup of spot id -> best current rating + conditions from surf data
  const spotRatings: Record<string, { rating: string; score: number; wind_kt?: number; wind_dir?: number; swell_height?: number; swell_period?: number }> = {}
  if (data.surf?.spots) {
    for (const sf of data.surf.spots) {
      const best = sf.daily_best?.[0]
      const currentRating = sf.ratings?.[0]
      if (best) {
        spotRatings[sf.spot.id] = {
          rating: best.rating,
          score: best.score,
          wind_kt: currentRating?.wind_kt,
          wind_dir: currentRating?.wind_dir,
          swell_height: currentRating?.swell_height,
          swell_period: currentRating?.swell_period,
        }
      }
    }
  }

  return (
    <div className="px-4 pt-4 pb-24 max-w-screen-xl mx-auto">
      <h1 className="text-lg font-semibold mb-4 text-[var(--color-text-primary)]">
        {t('spots.title')}
      </h1>

      {/* Region filter pills — horizontal scrollable */}
      <div className="flex gap-2 overflow-x-auto pb-3 mb-5 scrollbar-none" style={{ scrollbarWidth: 'none' }}>
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
          const ratingInfo = spotRatings[spot.id]
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
                {ratingInfo && (
                  <RatingBadge rating={ratingInfo.rating} t={t} />
                )}
              </div>
              {/* Current conditions from forecast data */}
              {ratingInfo && (ratingInfo.wind_kt != null || ratingInfo.swell_height != null) && (
                <div className="flex items-center gap-3 mt-2 text-xs text-[var(--color-text-secondary)]">
                  {ratingInfo.wind_kt != null && (
                    <span className="tabular-nums">
                      {ratingInfo.wind_kt.toFixed(0)} kt
                    </span>
                  )}
                  {ratingInfo.swell_height != null && (
                    <span className="tabular-nums">
                      {ratingInfo.swell_height.toFixed(1)} m
                      {ratingInfo.swell_period != null && (
                        <span className="text-[var(--color-text-muted)]"> @ {ratingInfo.swell_period.toFixed(0)}s</span>
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
                <span className="text-[10px] text-[var(--color-text-muted)]">
                  {spot.facing}
                </span>
              </div>
            </Link>
          )
        })}
      </div>

      {filtered.length === 0 && (
        <div className="text-center py-12">
          <p className="text-sm text-[var(--color-text-muted)]">
            {t('spots.no_data')}
          </p>
        </div>
      )}
    </div>
  )
}

function RatingBadge({ rating, t }: { rating: string; t: (key: string) => string }) {
  const colorMap: Record<string, string> = {
    firing:    'bg-[var(--color-firing-bg)] text-[var(--color-firing)]',
    good:      'bg-[var(--color-bg-elevated)] text-[var(--color-rating-good)]',
    marginal:  'bg-[var(--color-bg-elevated)] text-[var(--color-rating-marginal)]',
    poor:      'bg-[var(--color-bg-elevated)] text-[var(--color-rating-poor)]',
    flat:      'bg-[var(--color-bg-elevated)] text-[var(--color-rating-flat)]',
    dangerous: 'bg-[var(--color-danger-bg)] text-[var(--color-rating-dangerous)]',
  }

  return (
    <span className={`text-[10px] font-medium px-2 py-0.5 rounded-full ${colorMap[rating] ?? ''}`}>
      {t(`rating.${rating}`)}
    </span>
  )
}
