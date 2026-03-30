import { lazy, Suspense, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { SPOTS } from '@/lib/constants'
import { useForecastData } from '@/hooks/useForecastData'
import { useTimeline } from '@/hooks/useTimeline'
import { useModel } from '@/hooks/useModel'
import { useLocation } from '@/hooks/useLocation'
import { useIsMobile } from '@/hooks/useIsMobile'
import { TimelineScrubber } from '@/components/timeline/TimelineScrubber'
import { WeatherWarnings } from '@/components/layout/WeatherWarnings'
import { LoadingSpinner } from '@/components/layout/LoadingSpinner'
import { ConditionsStrip } from '@/components/ConditionsStrip'
import { SwellCompass } from '@/components/spots/SwellCompass'
import {
  degToCompass, getModelRecords, windType,
  ratingsToWaveRecords, ratingsToTidePredictions, getSpotTideExtrema,
} from '@/lib/forecast-utils'
import { useLiveObsContext } from '@/App'
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
  const mobile = useIsMobile()
  const liveObs = useLiveObsContext()

  const [aiExpanded, setAiExpanded] = useState(false)

  // Location-specific forecast data
  const locationForecast: SpotForecast | null = useMemo(() => {
    if (!locationId || !data.surf?.spots) return null
    return data.surf.spots.find(s => s.spot.id === locationId) ?? null
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

  // Selected timestep as ms — drives chart reference line
  const selectedMs = useMemo(() => {
    if (!chartRecords?.length) return undefined
    const rec = chartRecords[Math.min(index, chartRecords.length - 1)]
    if (!rec?.valid_utc) return undefined
    return new Date(rec.valid_utc).getTime()
  }, [chartRecords, index])

  // Spot metadata
  const spotInfo = useMemo(() => {
    if (!locationId) return undefined
    return SPOTS.find(s => s.id === locationId)
  }, [locationId])

  // Current rating for spot detail
  const currentRating = useMemo(() => {
    if (!locationForecast) return null
    const targetUtc = chartRecords?.[index]?.valid_utc
    if (!targetUtc) return locationForecast.ratings[0] ?? null
    const targetMs = new Date(targetUtc).getTime()
    let best = locationForecast.ratings[0] ?? null
    let bestDiff = Infinity
    for (const r of locationForecast.ratings) {
      const diff = Math.abs(new Date(r.valid_utc).getTime() - targetMs)
      if (diff < bestDiff) { bestDiff = diff; best = r }
    }
    return best
  }, [locationForecast, chartRecords, index])

  // Spot-specific wave records for OceanChart (fall back to Keelung)
  const waveRecords = useMemo(() => {
    if (locationForecast && locationId !== 'keelung') {
      return ratingsToWaveRecords(locationForecast.ratings)
    }
    return data.wave?.ecmwf_wave?.records ?? []
  }, [locationForecast, locationId, data.wave])

  // Spot-specific tide predictions for TideChart (fall back to Keelung)
  const tidePredictions = useMemo(() => {
    if (locationForecast && locationId !== 'keelung') {
      return ratingsToTidePredictions(locationForecast.ratings)
    }
    return data.tide?.predictions ?? []
  }, [locationForecast, locationId, data.tide])

  // Tide extrema — per-spot from CWA tide forecast stations, or Keelung default
  const tideExtrema = useMemo(() => {
    if (locationId && locationId !== 'keelung') {
      const spotExtrema = getSpotTideExtrema(locationId, data.cwa_obs?.tide_forecast_stations)
      if (spotExtrema.length > 0) return spotExtrema
    }
    return data.tide?.extrema ?? []
  }, [locationId, data.cwa_obs, data.tide])

  if (data.loading) {
    return <LoadingSpinner />
  }

  const isSpotSelected = locationId != null && locationId !== 'keelung'

  /* ── Spot / harbour detail panel ──────────────────────────────────── */
  const locationDetail = (
    <>
      {/* Selected spot detail */}
      {isSpotSelected && spotInfo && (
        <section className="space-y-3 md:px-3 py-3">
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
              aria-label="Deselect"
            >
              <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M1 1 L9 9 M9 1 L1 9" />
              </svg>
            </button>
          </div>

          {/* Swell compass + data cells side by side */}
          {currentRating && (
            <div className="flex items-start gap-3">
              <div className="shrink-0">
                <SwellCompass
                  facing={spotInfo.facing}
                  optSwell={spotInfo.opt_swell}
                  swellDir={currentRating.swell_dir}
                  swellHeight={currentRating.swell_height}
                  size={120}
                />
              </div>
              <div className="flex-1 min-w-0 space-y-2">
                <div className="grid grid-cols-2 gap-1.5">
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
              </div>
            </div>
          )}

          {/* Info pills + wind type */}
          <div className="flex flex-wrap gap-1.5">
            <InfoPill label={t('spots.facing')} value={spotInfo.facing} />
            <InfoPill label={t('spots.optimal_wind')} value={spotInfo.opt_wind.join(', ')} />
            {currentRating?.wind_dir != null && spotInfo.facing && (
              <InfoPill label={t('common.wind')} value={windType(currentRating.wind_dir, spotInfo.facing)} />
            )}
          </div>

          {/* CWA real-time observations (live from serverless, or fallback to deploy-time) */}
          {(() => {
            const live = liveObs.data?.spots?.[spotInfo.id]
            const stale = data.cwa_obs?.spot_obs?.[spotInfo.id]
            const stn = live?.station ?? stale?.station
            const buoy = live?.buoy ?? stale?.buoy
            const tide = live?.tide
            if (!stn && !buoy && !tide) return null
            return (
              <div className="mt-2 px-2 py-1.5 rounded-lg bg-[var(--color-bg-elevated)]/50 border border-[var(--color-border)]">
                <p className="text-[9px] uppercase tracking-widest text-[var(--color-text-muted)] mb-1">
                  {t('common.live_obs') ?? 'Live Observations'}
                </p>
                <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] text-[var(--color-text-secondary)]">
                  {stn?.temp_c != null && <span>{stn.temp_c.toFixed(1)}°C</span>}
                  {stn?.wind_kt != null && (
                    <span>{stn.wind_kt.toFixed(0)}kt{stn.gust_kt ? ` G${stn.gust_kt.toFixed(0)}` : ''} {stn.wind_dir != null ? degToCompass(stn.wind_dir) : ''}</span>
                  )}
                  {stn?.pressure_hpa != null && <span>{stn.pressure_hpa.toFixed(0)}hPa</span>}
                  {tide?.tide_height_m != null && (
                    <span>{t('common.tide')} {tide.tide_height_m.toFixed(2)}m{tide.tide_level ? ` (${tide.tide_level})` : ''}</span>
                  )}
                  {buoy?.wave_height_m != null && (
                    <span>Hs {buoy.wave_height_m.toFixed(1)}m</span>
                  )}
                  {buoy?.wave_period_s != null && (
                    <span>{buoy.wave_period_s.toFixed(0)}s</span>
                  )}
                  {(() => {
                    const wt = tide?.sea_temp_c ?? live?.buoy?.sea_temp_c ?? stale?.buoy?.water_temp_c
                    return wt != null ? <span>{t('live.water_temp')} {wt.toFixed(1)}°C</span> : null
                  })()}
                  {live?.buoy?.current_speed_ms != null && live.buoy.current_speed_ms > 0.1 && (
                    <span>{t('common.current') ?? 'Current'} {(live.buoy.current_speed_ms * 1.94384).toFixed(1)}kt {live.buoy.current_dir != null ? degToCompass(live.buoy.current_dir) : ''}</span>
                  )}
                  {live?.station?.visibility_km != null && live.station.visibility_km < 10 && (
                    <span>{t('live.visibility')} {live.station.visibility_km.toFixed(1)}km</span>
                  )}
                  {live?.station?.uv_index != null && live.station.uv_index > 0 && (
                    <span className={live.station.uv_index >= 8 ? 'text-red-400' : live.station.uv_index >= 6 ? 'text-orange-400' : ''}>
                      UV {live.station.uv_index.toFixed(0)}
                    </span>
                  )}
                </div>
                {liveObs.data && (
                  <p className="text-[9px] text-[var(--color-text-dim)] mt-0.5">
                    {t('live.title')}
                  </p>
                )}
              </div>
            )
          })()}

          {/* Ensemble confidence + accuracy */}
          {data.ensemble?.spread && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {(() => {
                const ws = data.ensemble.spread.wind_spread_kt ?? 99
                const level = ws < 5 ? 'high' : ws < 10 ? 'moderate' : 'low'
                const stars = level === 'high' ? '★★★' : level === 'moderate' ? '★★☆' : '★☆☆'
                const color = level === 'high' ? 'text-green-400' : level === 'moderate' ? 'text-yellow-400' : 'text-red-400'
                return (
                  <span className={`text-[10px] px-1.5 py-0.5 rounded bg-[var(--color-bg-elevated)] ${color}`}>
                    {t('models_page.ensemble_confidence') ?? 'Confidence'} {stars}
                  </span>
                )
              })()}
              {data.accuracy?.[0] && (
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--color-bg-elevated)] text-[var(--color-text-muted)]">
                  ±{data.accuracy[0].wind_mae_kt?.toFixed(1) ?? '?'}kt wind · ±{data.accuracy[0].temp_mae_c?.toFixed(1) ?? '?'}°C temp
                </span>
              )}
            </div>
          )}
        </section>
      )}

      {/* Harbour selected */}
      {locationId === 'keelung' && (
        <section className="md:px-3 py-3">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-[var(--color-text-primary)]">
              {t('harbour.keelung')}
            </h2>
            <button
              onClick={() => setLocationId(null)}
              className="w-6 h-6 flex items-center justify-center rounded-full hover:bg-[var(--color-bg-elevated)] text-[var(--color-text-muted)]"
              aria-label="Deselect"
            >
              <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M1 1 L9 9 M9 1 L1 9" />
              </svg>
            </button>
          </div>
        </section>
      )}

      {/* AI Summary */}
      {data.summary && (
        <div className="md:mx-3 border border-[var(--color-border)] rounded-xl overflow-hidden">
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
    </>
  )

  /* ── Charts panel ──────────────────────────────────────────────────── */
  const chartsPanel = (
    <div className="space-y-3">
      {/* Sticky header: timeline + conditions */}
      <div className="sticky top-0 z-10 bg-[var(--color-bg)] border-b border-[var(--color-border)] -mx-4 px-4 md:-mx-6 md:px-6">
        <TimelineScrubber records={chartRecords} />
        <ConditionsStrip />
      </div>

      {/* Weather warnings */}
      <WeatherWarnings />

      {/* Charts */}
      <Suspense fallback={null}>
        {chartRecords.length > 0 && (
          <ChartCard title={t('common.wind')}>
            <WindChart records={chartRecords} timeRange={timeRange} selectedMs={selectedMs} />
          </ChartCard>
        )}

        {waveRecords.length > 0 && (
          <ChartCard title={`${t('common.wave_height')} + ${t('common.swell_period')}`}>
            <OceanChart records={waveRecords} timeRange={timeRange} selectedMs={selectedMs} />
          </ChartCard>
        )}

        {tidePredictions.length > 0 && (
          <ChartCard title={t('common.tide')}>
            <TideChart
              predictions={tidePredictions}
              extrema={tideExtrema}
              timeRange={timeRange}
              selectedMs={selectedMs}
            />
          </ChartCard>
        )}

        {/* Precip + Temp: side by side on desktop, stacked on mobile */}
        <div className={mobile ? 'space-y-0' : 'grid grid-cols-2 gap-3'}>
          {chartRecords.length > 0 && (
            <ChartCard title={t('common.precip')}>
              <PrecipChart records={chartRecords} timeRange={timeRange} selectedMs={selectedMs} />
            </ChartCard>
          )}
          {chartRecords.length > 0 && (
            <ChartCard title={t('common.temp')}>
              <TempChart records={chartRecords} timeRange={timeRange} selectedMs={selectedMs} />
            </ChartCard>
          )}
        </div>
      </Suspense>

      {/* Bottom safe-area spacer */}
      <div className="h-4" style={{ paddingBottom: 'env(safe-area-inset-bottom, 0px)' }} />
    </div>
  )

  /* ── Desktop: left sidebar (map + detail) | right (charts) ─────────── */
  if (!mobile) {
    return (
      <div className="flex h-full">
        {/* Left column: map + location detail + AI */}
        <div className="w-[300px] min-w-[260px] shrink-0 border-r border-[var(--color-border)] flex flex-col">
          <div className="relative h-[45%] min-h-[200px] shrink-0">
            <Suspense fallback={<div className="w-full h-full bg-black" />}>
              <ForecastMap selectedId={locationId} onSelectLocation={setLocationId} />
            </Suspense>
          </div>
          <div className="flex-1 overflow-y-auto border-t border-[var(--color-border)]">
            {locationDetail}
          </div>
        </div>

        {/* Right column: timeline + charts */}
        <div className="flex-1 overflow-y-auto px-6 py-2">
          {chartsPanel}
        </div>
      </div>
    )
  }

  /* ── Mobile: map top (40vh), detail + charts below (scrolls) ───────── */
  return (
    <div className="h-full overflow-y-auto">
      {/* Map section */}
      <div className="h-[40vh] min-h-[200px] max-h-[360px] relative shrink-0">
        <Suspense fallback={<div className="w-full h-full bg-black" />}>
          <ForecastMap selectedId={locationId} onSelectLocation={setLocationId} />
        </Suspense>
      </div>

      {/* Data section */}
      <div className="px-4 py-2">
        {locationDetail}
        {chartsPanel}
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
