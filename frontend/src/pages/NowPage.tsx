import { lazy, Suspense, useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { SPOTS } from '@/lib/constants'
import { useForecastData } from '@/hooks/useForecastData'
import { useTimeline } from '@/hooks/useTimeline'
import { useModel } from '@/hooks/useModel'
import { useLocation } from '@/hooks/useLocation'
import { useIsMobile, useIsTabletPortrait, useMobileLandscape } from '@/hooks/useIsMobile'
import { TimelineScrubber } from '@/components/timeline/TimelineScrubber'
import { WeatherWarnings } from '@/components/layout/WeatherWarnings'
import { LoadingSpinner } from '@/components/layout/LoadingSpinner'
import { ConditionsStrip } from '@/components/ConditionsStrip'
import { SpotCompare } from '@/components/spots/SpotCompare'
import { SwellWindowFinder } from '@/components/spots/SwellWindowFinder'
import { SpotDetail } from '@/components/spots/SpotDetail'
import type { DetailSection } from '@/components/spots/SpotDetail'
import { KeelungDetail } from '@/components/spots/KeelungDetail'
import { TaipeiDetail } from '@/components/spots/TaipeiDetail'
import { TownshipForecastCard } from '@/components/layout/TownshipForecastCard'
import { AlertSettingsPanel, checkAlerts } from '@/components/layout/AlertSettingsPanel'
import { AccuracyTrend } from '@/components/charts/AccuracyTrend'
import {
  getModelRecords,
  ratingsToWaveRecords, ratingsToTidePredictions, getSpotTideExtrema,
} from '@/lib/forecast-utils'
import type { TimeRange } from '@/components/charts/chart-utils'
import type { SpotForecast } from '@/lib/types'

const ForecastMap = lazy(() => import('@/components/map/ForecastMap').then(m => ({ default: m.ForecastMap })))
const WindChart = lazy(() => import('@/components/charts/WindChart').then(m => ({ default: m.WindChart })))
const OceanChart = lazy(() => import('@/components/charts/OceanChart').then(m => ({ default: m.OceanChart })))
const TideChart = lazy(() => import('@/components/charts/TideChart').then(m => ({ default: m.TideChart })))
const TempChart = lazy(() => import('@/components/charts/TempPressureChart').then(m => ({ default: m.TempChart })))
const PrecipChart = lazy(() => import('@/components/charts/PrecipChart').then(m => ({ default: m.PrecipChart })))
const EnsembleChart = lazy(() => import('@/components/charts/EnsembleChart').then(m => ({ default: m.EnsembleChart })))

export function NowPage() {
  const { t, i18n } = useTranslation()
  const lang = (i18n.language.startsWith('zh') ? 'zh' : 'en') as 'en' | 'zh'
  const data = useForecastData()
  const { index } = useTimeline()
  const { model } = useModel()
  const { locationId, setLocationId } = useLocation()
  const mobile = useIsMobile()
  const tabletPortrait = useIsTabletPortrait()
  const mobileLandscape = useMobileLandscape()

  const [aiExpanded, setAiExpanded] = useState(false)
  const [alertsOpen, setAlertsOpen] = useState(false)
  const alertsFired = useRef(false)

  // Fire browser notifications when forecast data loads (once per session)
  useEffect(() => {
    if (alertsFired.current || data.loading) return
    const records = data.keelung?.records
    const waveRecs = data.wave?.ecmwf_wave?.records
    const surfRatings = (data.surf?.spots?.flatMap(s => s.ratings) ?? []).map(r => ({
      valid_utc: r.valid_utc, score: r.score ?? undefined, rating: r.rating ?? undefined,
    }))
    if (records?.length) {
      alertsFired.current = true
      checkAlerts(records, waveRecs ?? [], surfRatings)
    }
  }, [data.loading, data.keelung, data.wave, data.surf])

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

  // Forecast time label for selected timestep (CST)
  // NOTE: must be above the loading guard to satisfy Rules of Hooks
  const forecastTimeLabel = useMemo(() => {
    const rec = chartRecords?.[index]
    if (!rec?.valid_utc) return ''
    const d = new Date(rec.valid_utc)
    return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'Asia/Taipei' })
  }, [chartRecords, index])

  // nowMs for tide sparkline in spot detail
  // NOTE: must be above the loading guard to satisfy Rules of Hooks
  const nowMs = useMemo(() => {
    const vu = data.keelung?.records?.[index]?.valid_utc
    return vu ? new Date(vu).getTime() : undefined
  }, [data.keelung, index])

  if (data.loading) {
    return <LoadingSpinner />
  }

  if (data.error) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <div className="text-center space-y-3">
          <p className="text-[var(--color-text-muted)] fs-label">{data.error}</p>
          <button
            onClick={data.reload}
            className="px-4 py-2 rounded-lg bg-[var(--color-accent)]/20 text-[var(--color-accent)] fs-body hover:bg-[var(--color-accent)]/30 transition-colors"
          >
            {t('common.retry', 'Retry')}
          </button>
        </div>
      </div>
    )
  }

  const isSpotSelected = locationId != null && locationId !== 'keelung' && locationId !== 'taipei'

  /* ── Spot / harbour detail panel ──────────────────────────────────── */
  const keelungWaveRec = useMemo(() => {
    const recs = data.wave?.ecmwf_wave?.records
    if (!recs?.length) return null
    return recs[Math.min(index, recs.length - 1)] ?? null
  }, [data.wave, index])

  const locationDetail = (section?: DetailSection, opts?: { collapsibleLiveObs?: boolean }) => (
    <>
      {/* Selected spot detail */}
      {isSpotSelected && spotInfo && (
        <SpotDetail
          spotInfo={spotInfo}
          currentRating={currentRating}
          locationForecast={locationForecast}
          tidePredictions={tidePredictions}
          tideExtrema={tideExtrema}
          forecastTimeLabel={forecastTimeLabel}
          nowMs={nowMs}
          ensemble={data.ensemble}
          accuracy={data.accuracy}
          cwaObs={data.cwa_obs}
          section={section}
          collapsibleLiveObs={opts?.collapsibleLiveObs}
          onDeselect={() => setLocationId(null)}
        />
      )}

      {/* Harbour selected */}
      {locationId === 'keelung' && (
        <KeelungDetail
          ensemble={data.ensemble}
          accuracy={data.accuracy}
          cwaObs={data.cwa_obs}
          waveRec={keelungWaveRec}
          forecastTimeLabel={forecastTimeLabel}
          section={section}
          collapsibleLiveObs={opts?.collapsibleLiveObs}
          onDeselect={() => setLocationId(null)}
        />
      )}

      {/* City selected (Taipei) */}
      {locationId === 'taipei' && (
        <TaipeiDetail
          cwaObs={data.cwa_obs}
          forecastRec={chartRecords?.[index] ?? null}
          forecastTimeLabel={forecastTimeLabel}
          section={section}
          onDeselect={() => setLocationId(null)}
        />
      )}

      {/* Spot comparison (browse mode — no spot selected) */}
      {!isSpotSelected && locationId !== 'keelung' && locationId !== 'taipei' && data.surf?.spots && (!section || section === 'all' || section === 'above-timeline' || section === 'no-live') && (
        <>
          <section className="md:px-3 py-2">
            <SpotCompare
              spots={data.surf.spots}
              targetUtc={data.keelung?.records?.[index]?.valid_utc}
              onSelectSpot={setLocationId}
            />
          </section>
          <SwellWindowFinder spots={data.surf.spots} onSelectSpot={setLocationId} />
        </>
      )}

      {/* AI Summary */}
      {data.summary && (!section || section === 'all' || section === 'below-timeline' || section === 'no-live') && (
        <div className="md:mx-3 border border-[var(--color-border)] rounded-xl overflow-hidden">
          <button
            onClick={() => setAiExpanded(!aiExpanded)}
            className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-[var(--color-bg-elevated)]/50 transition-colors"
          >
            <span className="fs-compact uppercase tracking-widest text-[var(--color-text-muted)]">
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
          <div className={`grid transition-[grid-template-rows] duration-300 ${aiExpanded ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]'}`}>
            <div className="overflow-hidden">
              <div className="px-4 pb-4 space-y-2 fs-body text-[var(--color-text-secondary)] leading-relaxed">
                <p>{data.summary.wind[lang]}</p>
                <p>{data.summary.waves[lang]}</p>
                <p>{data.summary.outlook[lang]}</p>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  )

  /* ── Charts panel ──────────────────────────────────────────────────── */
  const chartsPanel = () => (
    <div className="space-y-1.5">
      {/* CWA Township Forecast */}
      <TownshipForecastCard cwaObs={data.cwa_obs} locationId={locationId} />

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

        <div className="space-y-1.5">
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

        {/* Ensemble model comparison */}
        {data.ensemble?.models && (
          <ChartCard title="Model Comparison">
            <EnsembleChart ensemble={data.ensemble} timeRange={timeRange} selectedMs={selectedMs} />
          </ChartCard>
        )}

        {/* Accuracy trend — only in browse mode (detail panels have their own) */}
        {!isSpotSelected && locationId !== 'keelung' && locationId !== 'taipei' && data.accuracy && data.accuracy.length >= 2 && (
          <AccuracyTrend entries={data.accuracy} />
        )}
      </Suspense>
    </div>
  )

  /* ── Desktop: 3-column layout (≥1080px) ────────────────────────────── */
  if (!mobile && !tabletPortrait) {
    return (
      <div className="flex flex-col h-full max-w-[1600px] mx-auto">
        {/* Full-width weather warnings banner */}
        <div className="shrink-0">
          <WeatherWarnings />
        </div>
        <div className="flex flex-1 min-h-0">
        {/* Left column: location detail + AI summary */}
        <div className="w-[20%] min-w-[240px] max-w-[320px] shrink-0 border-r border-[var(--color-border)] flex flex-col overflow-y-auto">
          <div className="px-1 py-2">
            {locationDetail()}
          </div>
        </div>

        {/* Center column: map + timeline + conditions */}
        <div className="flex-1 flex flex-col min-w-0">
          {/* Map takes most of the space */}
          <div className="relative flex-1 min-h-[300px] max-h-[800px]">
            <Suspense fallback={<div className="w-full h-full bg-black" />}>
              <ForecastMap selectedId={locationId} onSelectLocation={setLocationId} />
            </Suspense>
          </div>
          {/* Timeline + conditions below map */}
          <div className="shrink-0 border-t border-[var(--color-border)] px-3">
            <div className="flex items-center gap-1">
              <div className="flex-1 min-w-0"><TimelineScrubber records={chartRecords} /></div>
              <button
                onClick={() => setAlertsOpen(true)}
                className="shrink-0 w-7 h-7 min-w-[44px] min-h-[44px] flex items-center justify-center rounded-full hover:bg-[var(--color-bg-elevated)] text-[var(--color-text-muted)] transition-colors"
                aria-label="Alert settings"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
                  <path d="M13.73 21a2 2 0 0 1-3.46 0" />
                </svg>
              </button>
            </div>
            <ConditionsStrip />
          </div>
        </div>

        {/* Right column: compact charts */}
        <div className="w-[24%] min-w-[260px] max-w-[380px] shrink-0 border-l border-[var(--color-border)] overflow-y-auto px-2 py-1.5">
          {chartsPanel()}
        </div>
        </div>
        <AlertSettingsPanel open={alertsOpen} onClose={() => setAlertsOpen(false)} />
      </div>
    )
  }

  /* ── Tablet portrait: map top, 2-col data below (768-1079px) ───────── */
  if (tabletPortrait) {
    return (
      <div className="flex flex-col h-full">
        {/* Full-width weather warnings banner */}
        <div className="shrink-0">
          <WeatherWarnings />
        </div>
        {/* Map section */}
        <div className="h-[50vh] min-h-[280px] max-h-[500px] relative shrink-0">
          <Suspense fallback={<div className="w-full h-full bg-black" />}>
            <ForecastMap selectedId={locationId} onSelectLocation={setLocationId} />
          </Suspense>
        </div>
        {/* Timeline + conditions */}
        <div className="shrink-0 border-t border-[var(--color-border)] px-3">
          <div className="flex items-center gap-1">
            <div className="flex-1 min-w-0"><TimelineScrubber records={chartRecords} /></div>
            <button
              onClick={() => setAlertsOpen(true)}
              className="shrink-0 w-7 h-7 min-w-[44px] min-h-[44px] flex items-center justify-center rounded-full hover:bg-[var(--color-bg-elevated)] text-[var(--color-text-muted)] transition-colors"
              aria-label="Alert settings"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
                <path d="M13.73 21a2 2 0 0 1-3.46 0" />
              </svg>
            </button>
          </div>
          <ConditionsStrip />
        </div>
        {/* Two-column data: detail left, charts right */}
        <div className="flex flex-1 min-h-0 border-t border-[var(--color-border)] gap-1">
          <div className="w-1/2 overflow-y-auto border-r border-[var(--color-border)] px-2 py-2">
            {locationDetail()}
          </div>
          <div className="w-1/2 overflow-y-auto px-2 py-1.5">
            {chartsPanel()}
          </div>
        </div>
        <AlertSettingsPanel open={alertsOpen} onClose={() => setAlertsOpen(false)} />
      </div>
    )
  }

  /* ── Shared timeline + alert bell bar (mobile portrait & landscape) ── */
  const timelineBar = (compact?: boolean) => (
    <div className="flex items-center gap-1">
      <div className="flex-1 min-w-0"><TimelineScrubber records={chartRecords} /></div>
      <button
        onClick={() => setAlertsOpen(true)}
        className={`shrink-0 flex items-center justify-center rounded-full hover:bg-[var(--color-bg-elevated)] text-[var(--color-text-muted)] transition-colors ${compact ? 'w-6 h-6 min-w-[36px] min-h-[36px]' : 'w-7 h-7 min-w-[36px] min-h-[36px]'}`}
        aria-label="Alert settings"
      >
        <svg width={compact ? 12 : 14} height={compact ? 12 : 14} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
          <path d="M13.73 21a2 2 0 0 1-3.46 0" />
        </svg>
      </button>
    </div>
  )

  /* ── Mobile landscape: map+live left, header+timeline+forecast right ── */
  if (mobileLandscape) {
    return (
      <div className="flex h-full overflow-hidden">
        {/* Left: map (top ~60%) + live obs (bottom, collapsible) */}
        <div className="w-[45%] flex flex-col min-w-0 shrink-0">
          <div className="flex-1 relative min-h-0">
            <Suspense fallback={<div className="w-full h-full bg-black" />}>
              <ForecastMap selectedId={locationId} onSelectLocation={setLocationId} />
            </Suspense>
          </div>
          <div className="shrink-0 border-t border-[var(--color-border)] px-2 py-1">
            {locationDetail('live', { collapsibleLiveObs: true })}
          </div>
        </div>

        {/* Right: single scroll container — header scrolls away, timeline sticks */}
        <div className="w-[55%] flex flex-col min-w-0 border-l border-[var(--color-border)]">
          <div className="flex-1 overflow-y-auto">
            {/* Scrollable header: warnings + spot header */}
            <div className="px-2 py-1">
              <WeatherWarnings />
              {locationDetail('no-live')}
            </div>

            {/* Sticky timeline + conditions — pins when header scrolls away */}
            <div className="sticky top-0 z-10 bg-[var(--color-bg)] border-b border-[var(--color-border)] px-2">
              {timelineBar(true)}
              <ConditionsStrip />
            </div>

            {/* Charts */}
            <div className="px-2 py-1">
              {chartsPanel()}
            </div>
          </div>
        </div>
        <AlertSettingsPanel open={alertsOpen} onClose={() => setAlertsOpen(false)} />
      </div>
    )
  }

  /* ── Mobile portrait: map top (30vh), single scroll below with sticky timeline ── */
  return (
    <div className="flex flex-col h-full">
      {/* Full-width weather warnings banner */}
      <div className="shrink-0">
        <WeatherWarnings />
      </div>
      {/* Map section — shrunk to leave more room for data */}
      <div className="h-[30vh] min-h-[180px] max-h-[300px] relative shrink-0">
        <Suspense fallback={<div className="w-full h-full bg-black" />}>
          <ForecastMap selectedId={locationId} onSelectLocation={setLocationId} />
        </Suspense>
      </div>

      {/* Single scroll container: header scrolls away, timeline sticks, charts below */}
      <div className="flex-1 overflow-y-auto overflow-x-hidden">
        {/* Header + live obs — visible on load, scrolls away */}
        <div className="px-4 pt-1">
          {locationDetail('above-timeline', { collapsibleLiveObs: true })}
        </div>

        {/* Sticky timeline + conditions — pins when header scrolls past */}
        <div className="sticky top-0 z-10 bg-[var(--color-bg)] border-t border-[var(--color-border)] px-4">
          {timelineBar()}
          <ConditionsStrip />
        </div>

        {/* Forecast + spot info + accuracy + charts (time-dependent) */}
        <div className="px-4 py-2">
          {locationDetail('below-timeline')}
          {chartsPanel()}
        </div>
      </div>
      <AlertSettingsPanel open={alertsOpen} onClose={() => setAlertsOpen(false)} />
    </div>
  )
}

function ChartCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="border-b border-[var(--color-border)] py-2">
      <p className="fs-compact uppercase tracking-widest text-[var(--color-text-muted)] mb-1 ml-1">
        {title}
      </p>
      {children}
    </div>
  )
}
