import { lazy, Suspense, useMemo } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { SPOTS } from '@/lib/constants'
import { useForecastData } from '@/hooks/useForecastData'
import { SwellCompass } from '@/components/spots/SwellCompass'
import { ScoreBreakdown } from '@/components/spots/ScoreBreakdown'
import { SpotForecastTable } from '@/components/shared/ForecastTable'
import { WeatherWarnings } from '@/components/layout/WeatherWarnings'
import { DataFreshness } from '@/components/layout/DataFreshness'
import {
  degToCompass, isCurrentTimestep,
  ratingColorClass, windColorClass, waveColorClass,
  windType, windTypeColorClass,
  type WindType,
} from '@/lib/forecast-utils'
import type { TimeRange } from '@/components/charts/chart-utils'

const WaveChart = lazy(() => import('@/components/charts/WaveChart').then(m => ({ default: m.WaveChart })))
const WindChart = lazy(() => import('@/components/charts/WindChart').then(m => ({ default: m.WindChart })))

export function SpotDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { t, i18n } = useTranslation()
  const lang = i18n.language as 'en' | 'zh'
  const data = useForecastData()
  const spotIndex = SPOTS.findIndex(s => s.id === id)
  const spot = spotIndex >= 0 ? SPOTS[spotIndex] : undefined

  if (!spot) {
    return (
      <div className="px-4 py-6 pb-24 max-w-screen-xl mx-auto">
        <button onClick={() => navigate(-1)} className="flex items-center gap-1 text-sm text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] transition-colors mb-6">
          <span className="text-base">&larr;</span>
          <span>{t('spots.back')}</span>
        </button>
        <p className="text-[var(--color-text-muted)]">Spot not found</p>
      </div>
    )
  }

  const spotForecast = data.surf?.spots?.find(sf => sf.spot.id === id)
  const allUtcs = spotForecast?.ratings?.map(r => r.valid_utc) ?? []
  const currentRating = spotForecast?.ratings?.find(r => isCurrentTimestep(r.valid_utc, allUtcs)) ?? spotForecast?.ratings?.[0]
  const wt: WindType | undefined = currentRating?.wind_dir != null ? windType(currentRating.wind_dir, spot.facing) : undefined

  // CWA per-spot live obs
  const spotObs = data.cwa_obs?.spot_obs?.[id as keyof typeof data.cwa_obs.spot_obs] as
    | { station?: { temp_c?: number; wind_kt?: number; wind_dir?: number; distance_km?: number }; buoy?: { wave_height_m?: number; wave_period_s?: number; distance_km?: number } }
    | undefined

  // Prev/next spot navigation
  const prevSpot = spotIndex > 0 ? SPOTS[spotIndex - 1] : undefined
  const nextSpot = spotIndex < SPOTS.length - 1 ? SPOTS[spotIndex + 1] : undefined

  // Nearby spots with their current rating
  const nearbySpots = useMemo(() => {
    if (!data.surf?.spots) return []
    return SPOTS
      .filter(s => s.id !== id)
      .map(s => {
        const sf = data.surf!.spots.find(f => f.spot.id === s.id)
        const best = sf?.daily_best?.[0]
        return { spot: s, rating: best?.rating, score: best?.score }
      })
      .sort((a, b) => (b.score ?? 0) - (a.score ?? 0))
      .slice(0, 4)
  }, [data.surf, id])

  // Build wave records for the chart (from surf forecast ratings)
  const timeRange: TimeRange | undefined = useMemo(() => {
    const ratings = spotForecast?.ratings
    if (!ratings?.length) return undefined
    return { startUtc: ratings[0].valid_utc, endUtc: ratings[ratings.length - 1].valid_utc }
  }, [spotForecast?.ratings])

  // Build chart-compatible wave records from spot ratings
  const waveChartRecords = useMemo(() => {
    if (!spotForecast?.ratings) return []
    return spotForecast.ratings
      .filter(r => r.swell_height != null)
      .map(r => ({
        valid_utc: r.valid_utc,
        wave_height: r.swell_height,
        swell_wave_height: r.swell_height,
        swell_wave_period: r.swell_period,
        swell_wave_direction: r.swell_dir,
      }))
  }, [spotForecast?.ratings])

  // Build chart-compatible wind records from spot ratings
  const windChartRecords = useMemo(() => {
    if (!spotForecast?.ratings) return []
    return spotForecast.ratings
      .filter(r => r.wind_kt != null)
      .map(r => ({
        valid_utc: r.valid_utc,
        wind_kt: r.wind_kt,
      }))
  }, [spotForecast?.ratings])

  return (
    <div className="px-4 pt-4 pb-24 max-w-screen-xl mx-auto">
      {/* Prev/Next spot nav + back */}
      <div className="flex items-center justify-between mb-4">
        <button onClick={() => navigate(-1)} className="flex items-center gap-1 text-sm text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] transition-colors">
          <span className="text-base">&larr;</span>
          <span>{t('spots.back')}</span>
        </button>
        <div className="flex items-center gap-3">
          {prevSpot && (
            <Link to={`/spots/${prevSpot.id}`} className="text-xs text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] transition-colors no-underline">
              &larr; {prevSpot.name[lang]}
            </Link>
          )}
          {nextSpot && (
            <Link to={`/spots/${nextSpot.id}`} className="text-xs text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] transition-colors no-underline">
              {nextSpot.name[lang]} &rarr;
            </Link>
          )}
        </div>
      </div>

      {/* Spot header — name + inline info pills */}
      <div className="mb-4">
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-xl font-semibold text-[var(--color-text-primary)] leading-tight">
              {spot.name[lang]}
            </h1>
            <p className="text-sm text-[var(--color-text-muted)] mt-0.5">
              {spot.name[lang === 'en' ? 'zh' : 'en']}
            </p>
          </div>
          <DataFreshness />
        </div>
        {/* Compact info pills */}
        <div className="flex flex-wrap items-center gap-2 mt-2">
          <InfoPill label={t('spots.facing')} value={spot.facing} />
          <InfoPill label={t(`region.${spot.region}`)} />
          <InfoPill label={t('spots.optimal_wind')} value={spot.opt_wind.join(', ')} />
          <InfoPill label={t('spots.optimal_swell')} value={spot.opt_swell.join(', ')} />
        </div>
      </div>

      {/* Weather Warnings */}
      <WeatherWarnings />

      {/* Hero: Current conditions card */}
      {currentRating && (
        <section className="border border-[var(--color-border)] rounded-xl p-4 mb-4">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-xs uppercase tracking-wider text-[var(--color-text-muted)]">
              {t('spots.current_conditions')}
            </h2>
            <span className={`text-sm font-semibold ${ratingColorClass(currentRating.rating)}`}>
              {t(`rating.${currentRating.rating}`)}
              <span className="text-[var(--color-text-dim)] font-normal ml-1 text-xs">{currentRating.score}/14</span>
            </span>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <HeroStat
              label={t('common.wind')}
              value={currentRating.wind_kt?.toFixed(0) ?? '--'}
              unit="kt"
              colorClass={currentRating.wind_kt != null ? windColorClass(currentRating.wind_kt) : undefined}
              sub={wt ? (
                <span className={windTypeColorClass(wt)}>{t(`spots.${wt}`)}</span>
              ) : undefined}
              observed={spotObs?.station?.wind_kt != null ? `${spotObs.station.wind_kt.toFixed(0)} obs` : undefined}
            />
            <HeroStat
              label={t('spots.swell')}
              value={currentRating.swell_height?.toFixed(1) ?? '--'}
              unit="m"
              colorClass={currentRating.swell_height != null ? waveColorClass(currentRating.swell_height) : undefined}
              sub={currentRating.swell_period != null ? (
                <span className="text-[var(--color-text-dim)]">@ {currentRating.swell_period.toFixed(0)}s {currentRating.swell_dir != null ? degToCompass(currentRating.swell_dir) : ''}</span>
              ) : undefined}
              observed={spotObs?.buoy?.wave_height_m != null ? `${spotObs.buoy.wave_height_m.toFixed(1)} obs` : undefined}
            />
            <HeroStat
              label={t('spots.tide')}
              value={currentRating.tide_height?.toFixed(2) ?? '--'}
              unit="m"
            />
            <HeroStat
              label={t('harbours_page.direction')}
              value={currentRating.wind_dir != null ? degToCompass(currentRating.wind_dir) : '--'}
              unit={currentRating.wind_dir != null ? `${currentRating.wind_dir}°` : ''}
            />
          </div>
        </section>
      )}

      {/* 5-Day Forecast + Best Time merged */}
      <section className="border border-[var(--color-border)] rounded-xl p-4 mb-4">
        <h2 className="text-xs uppercase tracking-wider text-[var(--color-text-muted)] mb-3">
          {t('spots.five_day_forecast')}
        </h2>
        {spotForecast && spotForecast.daily_best.length > 0 ? (
          <div className="grid grid-cols-5 gap-2">
            {spotForecast.daily_best.map(day => {
              const bt = spotForecast.best_times.find(b => b.date === day.date)
              return <DayCard key={day.date} date={day.date} rating={day.rating} score={day.score} bestTime={bt} t={t} />
            })}
          </div>
        ) : (
          <p className="text-sm text-[var(--color-text-dim)] py-4 text-center">{t('spots.no_data')}</p>
        )}
      </section>

      {/* Swell + Wind sparkline charts */}
      {(waveChartRecords.length > 0 || windChartRecords.length > 0) && (
        <section className="border border-[var(--color-border)] rounded-xl p-4 mb-4">
          <h2 className="text-xs uppercase tracking-wider text-[var(--color-text-muted)] mb-3">
            {t('spots.forecast_charts')}
          </h2>
          <Suspense fallback={null}>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {windChartRecords.length > 0 && (
                <div>
                  <p className="text-[10px] uppercase tracking-widest text-[var(--color-text-dim)] mb-1">{t('common.wind')}</p>
                  <WindChart records={windChartRecords} timeRange={timeRange} />
                </div>
              )}
              {waveChartRecords.length > 0 && (
                <div>
                  <p className="text-[10px] uppercase tracking-widest text-[var(--color-text-dim)] mb-1">{t('spots.swell')}</p>
                  <WaveChart records={waveChartRecords} timeRange={timeRange} />
                </div>
              )}
            </div>
          </Suspense>
        </section>
      )}

      {/* Hourly Forecast Table (shared component) */}
      <section className="border border-[var(--color-border)] rounded-xl p-4 mb-4">
        <h2 className="text-xs uppercase tracking-wider text-[var(--color-text-muted)] mb-3">
          {t('spots.hourly_forecast')}
        </h2>
        {spotForecast?.ratings && spotForecast.ratings.length > 0 ? (
          <SpotForecastTable ratings={spotForecast.ratings} facing={spot.facing} lang={lang} />
        ) : (
          <p className="text-sm text-[var(--color-text-dim)] py-4 text-center">{t('spots.no_data')}</p>
        )}
      </section>

      {/* Swell Compass + Score Breakdown side by side */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
        <section className="border border-[var(--color-border)] rounded-xl p-4">
          <h2 className="text-xs uppercase tracking-wider text-[var(--color-text-muted)] mb-3">
            {t('spots.swell_compass')}
          </h2>
          <div className="flex items-center justify-center py-2">
            <SwellCompass
              facing={spot.facing}
              optSwell={spot.opt_swell}
              swellDir={currentRating?.swell_dir}
              swellHeight={currentRating?.swell_height}
            />
          </div>
          {currentRating?.swell_height != null && (
            <p className="text-center text-[10px] text-[var(--color-text-muted)] mt-1">
              {currentRating.swell_height.toFixed(1)} m @ {currentRating.swell_period?.toFixed(0) ?? '--'} s
            </p>
          )}
        </section>

        <section className="border border-[var(--color-border)] rounded-xl p-4">
          <h2 className="text-xs uppercase tracking-wider text-[var(--color-text-muted)] mb-3">
            {t('spots.score_breakdown')}
          </h2>
          {currentRating ? (
            <ScoreBreakdown rating={currentRating} spot={spot} />
          ) : (
            <p className="text-sm text-[var(--color-text-dim)] py-4 text-center">{t('spots.no_data')}</p>
          )}
        </section>
      </div>

      {/* Nearby Spots quick-nav */}
      {nearbySpots.length > 0 && (
        <section className="border border-[var(--color-border)] rounded-xl p-4 mb-4">
          <h2 className="text-xs uppercase tracking-wider text-[var(--color-text-muted)] mb-3">
            {t('spots.nearby')}
          </h2>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            {nearbySpots.map(ns => (
              <Link
                key={ns.spot.id}
                to={`/spots/${ns.spot.id}`}
                className="border border-[var(--color-border)] rounded-lg px-3 py-2 no-underline hover:border-[var(--color-border-active)] transition-colors"
              >
                <p className="text-xs text-[var(--color-text-primary)] font-medium truncate">{ns.spot.name[lang]}</p>
                <p className="text-[10px] text-[var(--color-text-muted)]">{ns.spot.name[lang === 'en' ? 'zh' : 'en']}</p>
                {ns.rating && (
                  <p className={`text-[10px] font-medium mt-1 ${ratingColorClass(ns.rating)}`}>
                    {t(`rating.${ns.rating}`)}
                    {ns.score != null && <span className="text-[var(--color-text-dim)] ml-1">{ns.score}/14</span>}
                  </p>
                )}
              </Link>
            ))}
          </div>
        </section>
      )}
    </div>
  )
}

/* ── Sub-components ─────────────────────────────────────────────────────────── */

function InfoPill({ label, value }: { label: string; value?: string }) {
  return (
    <span className="inline-flex items-center gap-1 text-[10px] border border-[var(--color-border)] rounded-full px-2.5 py-0.5 text-[var(--color-text-muted)]">
      <span>{label}</span>
      {value && <span className="text-[var(--color-text-secondary)]">{value}</span>}
    </span>
  )
}

function HeroStat({ label, value, unit, colorClass, sub, observed }: {
  label: string; value: string; unit: string; colorClass?: string; sub?: React.ReactNode; observed?: string
}) {
  return (
    <div className="bg-[var(--color-bg-elevated)] rounded-lg px-3 py-2">
      <p className="text-[10px] text-[var(--color-text-muted)] uppercase tracking-wider mb-0.5">{label}</p>
      <p className={`text-base font-semibold tabular-nums ${colorClass ?? 'text-[var(--color-text-primary)]'}`}>
        {value}
        <span className="text-xs text-[var(--color-text-muted)] ml-0.5">{unit}</span>
      </p>
      {sub && <p className="text-[10px] leading-tight mt-0.5">{sub}</p>}
      {observed && <p className="text-[9px] text-emerald-500/80 leading-tight mt-0.5">{observed}</p>}
    </div>
  )
}

function DayCard({ date, rating, score, bestTime, t }: {
  date: string; rating: string; score: number
  bestTime?: { start_cst: string; end_cst: string; rating: string }
  t: (key: string) => string
}) {
  const d = new Date(date + 'T00:00:00Z')
  const weekday = d.toLocaleDateString('en-US', { weekday: 'short', timeZone: 'UTC' })
  const dayNum = d.getUTCDate()

  const bgMap: Record<string, string> = {
    firing:    'bg-[var(--color-firing-bg)] border-[var(--color-firing)]/30',
    good:      'bg-[rgba(94,234,212,0.08)] border-[var(--color-rating-good)]/20',
    marginal:  'bg-[rgba(251,191,36,0.06)] border-[var(--color-rating-marginal)]/15',
    poor:      'border-[var(--color-border)]',
    flat:      'border-[var(--color-border)]',
    dangerous: 'bg-[rgba(248,113,113,0.08)] border-[var(--color-rating-dangerous)]/20',
  }

  return (
    <div className={`flex flex-col items-center gap-1 py-2 rounded-lg border ${bgMap[rating] ?? 'border-[var(--color-border)]'}`}>
      <span className="text-[10px] text-[var(--color-text-muted)]">{weekday}</span>
      <span className="text-xs text-[var(--color-text-secondary)]">{dayNum}</span>
      <span className={`text-[10px] font-medium mt-0.5 ${ratingColorClass(rating)}`}>
        {t(`rating.${rating}`)}
      </span>
      <span className="text-[10px] text-[var(--color-text-dim)]">{score}/14</span>
      {bestTime && (
        <span className="text-[9px] text-[var(--color-text-muted)] mt-0.5 tabular-nums">
          {bestTime.start_cst}–{bestTime.end_cst}
        </span>
      )}
    </div>
  )
}
