import { lazy, Suspense, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { SPOTS } from '@/lib/constants'
import { useForecastData } from '@/hooks/useForecastData'
import { useTimeline } from '@/hooks/useTimeline'
import { useModel } from '@/hooks/useModel'
import { useLocation } from '@/hooks/useLocation'
import { TimelineScrubber } from '@/components/timeline/TimelineScrubber'
import { WeatherWarnings } from '@/components/layout/WeatherWarnings'
import { LoadingSpinner } from '@/components/layout/LoadingSpinner'
import { BottomSheet } from '@/components/BottomSheet'
import { ConditionsStrip } from '@/components/ConditionsStrip'
import { SurfHeatmap } from '@/components/spots/SurfHeatmap'
import { SwellCompass } from '@/components/spots/SwellCompass'
import {
  degToCompass, getModelRecords, windType,
} from '@/lib/forecast-utils'
import type { TimeRange } from '@/components/charts/chart-utils'
import type { SpotForecast } from '@/lib/types'

const ForecastMap = lazy(() => import('@/components/map/ForecastMap').then(m => ({ default: m.ForecastMap })))
const WindChart = lazy(() => import('@/components/charts/WindChart').then(m => ({ default: m.WindChart })))
const OceanChart = lazy(() => import('@/components/charts/OceanChart').then(m => ({ default: m.OceanChart })))
const TideChart = lazy(() => import('@/components/charts/TideChart').then(m => ({ default: m.TideChart })))
const TempChart = lazy(() => import('@/components/charts/TempPressureChart').then(m => ({ default: m.TempChart })))
const PrecipChart = lazy(() => import('@/components/charts/PrecipChart').then(m => ({ default: m.PrecipChart })))

export function NowPage() {
  const { t, i18n } = useTranslation()
  const lang = (i18n.language.startsWith('zh') ? 'zh' : 'en') as 'en' | 'zh'
  const data = useForecastData()
  const { index } = useTimeline()
  const { model } = useModel()
  const { locationId, setLocationId } = useLocation()

  const [aiExpanded, setAiExpanded] = useState(false)

  // Location-specific forecast data
  const locationForecast: SpotForecast | null = useMemo(() => {
    if (!locationId || !data.surf?.spots) return null
    const sf = data.surf.spots.find(s => s.spot.id === locationId)
    if (!sf) return null
    return sf
  }, [data.surf, locationId])

  // Chart records based on selected model
  const chartRecords = useMemo(() => {
    if (!locationId) return data.keelung?.records ?? []
    return getModelRecords(locationId, model, data)
  }, [locationId, model, data])

  // Time range for charts
  const timeRange: TimeRange | undefined = useMemo(() => {
    if (!chartRecords?.length) return undefined
    return { startUtc: chartRecords[0].valid_utc, endUtc: chartRecords[chartRecords.length - 1].valid_utc }
  }, [chartRecords])

  // Spot metadata
  const spotInfo = useMemo(() => {
    if (!locationId) return undefined
    return SPOTS.find(s => s.id === locationId)
  }, [locationId])

  // Current rating for spot detail
  const currentRating = useMemo(() => {
    if (!locationForecast) return null
    const targetUtc = data.keelung?.records?.[index]?.valid_utc
    if (!targetUtc) return locationForecast.ratings[0] ?? null
    const targetMs = new Date(targetUtc).getTime()
    let best = locationForecast.ratings[0] ?? null
    let bestDiff = Infinity
    for (const r of locationForecast.ratings) {
      const diff = Math.abs(new Date(r.valid_utc).getTime() - targetMs)
      if (diff < bestDiff) { bestDiff = diff; best = r }
    }
    return best
  }, [locationForecast, data.keelung, index])

  if (data.loading) {
    return <LoadingSpinner />
  }

  const isSpotSelected = locationId != null && locationId !== 'keelung'

  return (
    <div className="h-[100dvh] flex flex-col">
      {/* Map fills available space */}
      <div className="flex-1 relative min-h-0">
        <Suspense fallback={<div className="w-full h-full bg-black" />}>
          <ForecastMap selectedId={locationId} onSelectLocation={setLocationId} />
        </Suspense>

        {/* Timeline scrubber overlay at bottom of map */}
        <div className="absolute bottom-0 left-0 right-0 z-20 bg-[var(--color-bg)]/70 backdrop-blur-md border-t border-[var(--color-border)]/40">
          <TimelineScrubber />
        </div>

        {/* Bottom Sheet */}
        <BottomSheet snapTo={locationId ? 'half' : 'peek'}>
          {/* Conditions strip (peek content) */}
          <ConditionsStrip />

          {/* Weather warnings */}
          <WeatherWarnings />

          {/* Selected spot detail */}
          {isSpotSelected && spotInfo && (
            <section className="mt-3 space-y-3">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-semibold text-[var(--color-text-primary)]">
                  {spotInfo.name[lang]}
                  <span className="text-[var(--color-text-muted)] ml-1.5 text-xs font-normal">
                    {spotInfo.name[lang === 'en' ? 'zh' : 'en']}
                  </span>
                </h2>
                <button
                  onClick={() => setLocationId(null)}
                  className="w-6 h-6 flex items-center justify-center rounded-full hover:bg-[var(--color-bg-elevated)] text-[var(--color-text-muted)]"
                >
                  <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M1 1 L9 9 M9 1 L1 9" />
                  </svg>
                </button>
              </div>

              {/* Spot info pills */}
              <div className="flex flex-wrap gap-1.5">
                <InfoPill label={t('spots.facing')} value={spotInfo.facing} />
                <InfoPill label={t('spots.optimal_wind')} value={spotInfo.opt_wind.join(', ')} />
                <InfoPill label={t('spots.optimal_swell')} value={spotInfo.opt_swell.join(', ')} />
              </div>

              {/* Current data for this spot */}
              {currentRating && (
                <div className="grid grid-cols-4 gap-2">
                  <DataCell
                    label={t('common.wind')}
                    value={`${currentRating.wind_kt?.toFixed(0) ?? '--'}`}
                    unit="kt"
                    sub={currentRating.wind_dir != null ? degToCompass(currentRating.wind_dir) : undefined}
                  />
                  <DataCell
                    label={t('common.swell')}
                    value={`${currentRating.swell_height?.toFixed(1) ?? '--'}`}
                    unit="m"
                    sub={currentRating.swell_dir != null ? degToCompass(currentRating.swell_dir) : undefined}
                  />
                  <DataCell
                    label={t('spots.period')}
                    value={`${currentRating.swell_period?.toFixed(0) ?? '--'}`}
                    unit="s"
                  />
                  <DataCell
                    label={t('common.tide')}
                    value={`${currentRating.tide_height?.toFixed(2) ?? '--'}`}
                    unit="m"
                  />
                </div>
              )}

              {/* Wind type indicator */}
              {currentRating?.wind_dir != null && spotInfo.facing && (
                <p className="text-[10px] text-[var(--color-text-muted)]">
                  {t('common.wind')}: <span className="text-[var(--color-text-secondary)] capitalize">{windType(currentRating.wind_dir, spotInfo.facing)}</span>
                </p>
              )}
            </section>
          )}

          {/* Harbour selected */}
          {locationId === 'keelung' && (
            <section className="mt-3">
              <div className="flex items-center justify-between mb-2">
                <h2 className="text-sm font-semibold text-[var(--color-text-primary)]">
                  {t('harbour.keelung')}
                </h2>
                <button
                  onClick={() => setLocationId(null)}
                  className="w-6 h-6 flex items-center justify-center rounded-full hover:bg-[var(--color-bg-elevated)] text-[var(--color-text-muted)]"
                >
                  <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M1 1 L9 9 M9 1 L1 9" />
                  </svg>
                </button>
              </div>
            </section>
          )}

          {/* Surf Heatmap (always visible in half/full) */}
          {data.surf && (
            <div className="mt-4">
              <p className="text-[10px] uppercase tracking-widest text-[var(--color-text-muted)] mb-2">
                {t('spots.heatmap_title')}
              </p>
              <SurfHeatmap spots={data.surf.spots} filter="all" onSelectSpot={setLocationId} />
            </div>
          )}

          {/* Location cards */}
          {data.surf && (
            <div className="mt-4">
              <p className="text-[10px] uppercase tracking-widest text-[var(--color-text-muted)] mb-2">
                {t('spots.all_locations')}
              </p>
              <div className="grid grid-cols-2 gap-2">
                {data.surf.spots.map(sf => (
                  <LocationCard
                    key={sf.spot.id}
                    forecast={sf}
                    lang={lang}
                    index={index}
                    keelungRecords={data.keelung?.records}
                    onSelect={() => setLocationId(sf.spot.id)}
                    selected={sf.spot.id === locationId}
                    t={t}
                  />
                ))}
              </div>
            </div>
          )}

          {/* Charts */}
          <Suspense fallback={null}>
            <div className="mt-4 space-y-1">
              <p className="text-[10px] uppercase tracking-widest text-[var(--color-text-muted)] mb-2">
                {t('spots.forecast_charts')}
              </p>

              {chartRecords.length > 0 && (
                <ChartCard title={t('common.wind')}>
                  <WindChart records={chartRecords} timeRange={timeRange} />
                </ChartCard>
              )}

              {data.wave?.ecmwf_wave?.records && (
                <ChartCard title={`${t('common.wave_height')} + ${t('common.swell_period')}`}>
                  <OceanChart records={data.wave.ecmwf_wave.records} timeRange={timeRange} />
                </ChartCard>
              )}

              {data.tide?.predictions && (
                <ChartCard title={t('common.tide')}>
                  <TideChart
                    predictions={data.tide.predictions}
                    extrema={data.tide.extrema}
                    timeRange={timeRange}
                  />
                </ChartCard>
              )}

              {chartRecords.length > 0 && (
                <ChartCard title={t('common.precip')}>
                  <PrecipChart records={chartRecords} timeRange={timeRange} />
                </ChartCard>
              )}

              {chartRecords.length > 0 && (
                <ChartCard title={t('common.temp')}>
                  <TempChart records={chartRecords} timeRange={timeRange} />
                </ChartCard>
              )}
            </div>
          </Suspense>

          {/* Swell Compass for selected spot */}
          {isSpotSelected && spotInfo && currentRating && (
            <div className="mt-4">
              <p className="text-[10px] uppercase tracking-widest text-[var(--color-text-muted)] mb-2">
                {t('spots.swell_compass')}
              </p>
              <div className="flex justify-center">
                <SwellCompass
                  facing={spotInfo.facing}
                  optSwell={spotInfo.opt_swell}
                  swellDir={currentRating.swell_dir}
                  swellHeight={currentRating.swell_height}
                />
              </div>
              {currentRating.swell_height != null && (
                <p className="text-center text-[10px] text-[var(--color-text-muted)] mt-1">
                  {currentRating.swell_height.toFixed(1)} m @ {currentRating.swell_period?.toFixed(0) ?? '--'} s
                </p>
              )}
            </div>
          )}

          {/* AI Summary */}
          {data.summary && (
            <div className="mt-4 border border-[var(--color-border)] rounded-xl overflow-hidden">
              <button
                onClick={() => setAiExpanded(!aiExpanded)}
                className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-[var(--color-bg-elevated)]/50 transition-colors"
              >
                <span className="text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
                  {t('ai.title')}
                </span>
                <svg
                  width="12" height="12" viewBox="0 0 12 12"
                  className={`text-[var(--color-text-muted)] transition-transform ${aiExpanded ? 'rotate-180' : ''}`}
                  fill="none" stroke="currentColor" strokeWidth="2"
                >
                  <path d="M2 4 L6 8 L10 4" />
                </svg>
              </button>
              {aiExpanded && (
                <div className="px-4 pb-4 space-y-2 text-sm text-[var(--color-text-secondary)] leading-relaxed">
                  <p>{data.summary.wind[lang]}</p>
                  <p>{data.summary.waves[lang]}</p>
                  <p>{data.summary.outlook[lang]}</p>
                </div>
              )}
            </div>
          )}

          {/* Bottom padding for safe area */}
          <div className="h-8" />
        </BottomSheet>
      </div>
    </div>
  )
}

/* ── Sub-components ─────────────────────────────────────────────────────── */

function InfoPill({ label, value }: { label: string; value?: string }) {
  return (
    <span className="inline-flex items-center gap-1 text-[10px] border border-[var(--color-border)] rounded-full px-2.5 py-0.5 text-[var(--color-text-muted)]">
      <span>{label}</span>
      {value && <span className="text-[var(--color-text-secondary)]">{value}</span>}
    </span>
  )
}

function DataCell({ label, value, unit, sub }: {
  label: string; value: string; unit: string; sub?: string
}) {
  return (
    <div className="bg-[var(--color-bg-elevated)] rounded-lg px-2 py-1.5 text-center">
      <p className="text-[9px] text-[var(--color-text-muted)] uppercase tracking-wider">{label}</p>
      <p className="text-sm font-semibold text-[var(--color-text-primary)] tabular-nums">
        {value}<span className="text-[10px] text-[var(--color-text-muted)] ml-0.5">{unit}</span>
      </p>
      {sub && <p className="text-[10px] text-[var(--color-text-dim)]">{sub}</p>}
    </div>
  )
}

function ChartCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="border-b border-[var(--color-border)] py-2">
      <p className="text-[10px] uppercase tracking-widest text-[var(--color-text-muted)] mb-1 ml-1">
        {title}
      </p>
      {children}
    </div>
  )
}

function LocationCard({ forecast: sf, lang, index, keelungRecords, onSelect, selected, t }: {
  forecast: SpotForecast
  lang: 'en' | 'zh'
  index: number
  keelungRecords?: { valid_utc: string }[]
  onSelect: () => void
  selected: boolean
  t: (key: string) => string
}) {
  const currentRating = useMemo(() => {
    if (!sf.ratings.length) return null
    const targetUtc = keelungRecords?.[index]?.valid_utc
    if (!targetUtc) return sf.ratings[0]
    const targetMs = new Date(targetUtc).getTime()
    let best = sf.ratings[0]
    let bestDiff = Infinity
    for (const r of sf.ratings) {
      const diff = Math.abs(new Date(r.valid_utc).getTime() - targetMs)
      if (diff < bestDiff) { bestDiff = diff; best = r }
    }
    return best
  }, [sf.ratings, keelungRecords, index])

  return (
    <button
      onClick={onSelect}
      className={`text-left border rounded-lg px-3 py-2 transition-colors ${
        selected
          ? 'border-[var(--color-text-muted)] bg-[var(--color-bg-elevated)]'
          : 'border-[var(--color-border)] hover:bg-[var(--color-bg-elevated)]/50'
      }`}
    >
      <p className="text-xs font-medium text-[var(--color-text-primary)] truncate">
        {sf.spot.name[lang]}
      </p>
      <div className="text-[10px] text-[var(--color-text-muted)] mt-0.5 space-y-0.5">
        <p>
          {t('common.wind')} {currentRating?.wind_kt?.toFixed(0) ?? '--'}kt
          {currentRating?.wind_dir != null && ` ${degToCompass(currentRating.wind_dir)}`}
        </p>
        {currentRating?.swell_height != null && (
          <p>{t('common.swell')} {currentRating.swell_height.toFixed(1)}m
            {currentRating.swell_period != null && ` @ ${currentRating.swell_period.toFixed(0)}s`}
          </p>
        )}
      </div>
    </button>
  )
}
