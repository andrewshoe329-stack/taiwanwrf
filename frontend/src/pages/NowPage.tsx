import { lazy, Suspense, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useForecastData } from '@/hooks/useForecastData'
import { useTimeline } from '@/hooks/useTimeline'
import { useModel } from '@/hooks/useModel'
import { useLocation } from '@/hooks/useLocation'
import { TimelineScrubber } from '@/components/timeline/TimelineScrubber'
import { WeatherWarnings } from '@/components/layout/WeatherWarnings'
import { LoadingSpinner } from '@/components/layout/LoadingSpinner'
import { SurfHeatmap } from '@/components/spots/SurfHeatmap'
import {
  sailDecision, surfDecision, degToCompass,
  getLocationForecast, getBestSpot, getModelRecords,
  windType, windTypeColorClass,
} from '@/lib/forecast-utils'
import type { TimeRange } from '@/components/charts/chart-utils'
import type { SpotForecast } from '@/lib/types'

const ForecastMap = lazy(() => import('@/components/map/ForecastMap').then(m => ({ default: m.ForecastMap })))
const WindChart = lazy(() => import('@/components/charts/WindChart').then(m => ({ default: m.WindChart })))
const WaveChart = lazy(() => import('@/components/charts/WaveChart').then(m => ({ default: m.WaveChart })))
const WavePeriodChart = lazy(() => import('@/components/charts/WaveChart').then(m => ({ default: m.WavePeriodChart })))
const TideChart = lazy(() => import('@/components/charts/TideChart').then(m => ({ default: m.TideChart })))
const TempChart = lazy(() => import('@/components/charts/TempPressureChart').then(m => ({ default: m.TempChart })))
const PressureChart = lazy(() => import('@/components/charts/TempPressureChart').then(m => ({ default: m.PressureChart })))
const PrecipChart = lazy(() => import('@/components/charts/PrecipChart').then(m => ({ default: m.PrecipChart })))

const RATING_COLORS: Record<string, string> = {
  firing: '#22c55e', great: '#4ade80', good: '#3b82f6', marginal: '#eab308',
  poor: '#9ca3af', flat: '#6b7280', dangerous: '#ef4444',
}

export function NowPage() {
  const { t, i18n } = useTranslation()
  const lang = (i18n.language.startsWith('zh') ? 'zh' : 'en') as 'en' | 'zh'
  const data = useForecastData()
  const { index } = useTimeline()
  const { model } = useModel()
  const { locationId, setLocationId } = useLocation()

  const [aiExpanded, setAiExpanded] = useState(false)

  // Determine if we're in focus mode
  const isFocusMode = locationId != null
  const isHarbour = locationId === 'keelung'

  // Get location-specific data
  const locationForecast: SpotForecast | null = useMemo(() => {
    if (!locationId) return null
    return getLocationForecast(data, locationId)
  }, [data, locationId])

  // Get chart records based on selected model
  const chartRecords = useMemo(() => {
    if (!locationId) return data.keelung?.records ?? []
    return getModelRecords(locationId, model, data)
  }, [locationId, model, data])

  // Time range for charts
  const timeRange: TimeRange | undefined = useMemo(() => {
    if (!chartRecords?.length) return undefined
    return { startUtc: chartRecords[0].valid_utc, endUtc: chartRecords[chartRecords.length - 1].valid_utc }
  }, [chartRecords])

  // Best spot for browse mode banner
  const bestSpot = useMemo(() => getBestSpot(data), [data])
  const bestSpotName = useMemo(() => {
    if (!bestSpot || !data.surf) return null
    const sf = data.surf.spots.find(s => s.spot.id === bestSpot.spotId)
    return sf?.spot.name[lang] ?? bestSpot.spotId
  }, [bestSpot, data.surf, lang])

  // Current record for conditions bar
  const currentRecord = useMemo(() => {
    if (!chartRecords?.length) return null
    return chartRecords[Math.min(index, chartRecords.length - 1)]
  }, [chartRecords, index])

  // Current spot rating (for focus mode on a surf spot)
  const currentRating = useMemo(() => {
    if (!locationForecast || isHarbour) return null
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
  }, [locationForecast, isHarbour, data.keelung, index])

  // Wave/swell data — use SpotRating for surf spots (has swell_height), WaveRecord for harbour
  const waveRecord = useMemo(() => {
    // For focused surf spots, use SpotRating which has swell data
    if (isFocusMode && !isHarbour && currentRating) return currentRating
    // Otherwise use the global wave data
    const recs = data.wave?.ecmwf_wave?.records
    if (!recs?.length) return null
    return recs[Math.min(index, recs.length - 1)]
  }, [isFocusMode, isHarbour, currentRating, data.wave, index])

  // Decisions
  const windKt = currentRecord?.wind_kt ?? 0
  const waveHt = (waveRecord && 'swell_height' in waveRecord ? waveRecord.swell_height : undefined)
    ?? (waveRecord && 'swell_wave_height' in waveRecord ? waveRecord.swell_wave_height : undefined)
    ?? 0
  const sailDec = sailDecision(windKt)
  const surfDec = surfDecision(waveHt, windKt)

  // CWA observed badges (browse mode / Keelung)
  const cwa = data.cwa_obs?.station
  const buoy = data.cwa_obs?.buoy

  if (data.loading) {
    return <LoadingSpinner />
  }

  return (
    <div className="min-h-screen">
      {/* Map + sticky timeline overlay */}
      <div className="relative h-[40vh] md:h-[55vh]">
        <Suspense fallback={<div className="w-full h-full bg-[var(--color-bg-card)]" />}>
          <ForecastMap selectedId={locationId} onSelectLocation={setLocationId} />
        </Suspense>
        <div className="absolute bottom-0 left-0 right-0 bg-[var(--color-bg)]/80 backdrop-blur-md border-t border-[var(--color-border)]/50">
          <TimelineScrubber />
        </div>
      </div>

      {/* ─── Focus Mode Header ─── */}
      {isFocusMode && (
        <div className="border-b border-[var(--color-border)] bg-[var(--color-bg)]">
          <div className="max-w-screen-lg mx-auto px-4 py-3 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <h2 className="text-base font-semibold text-[var(--color-text-primary)]">
                {locationForecast?.spot.name[lang] ?? locationId}
              </h2>
              {currentRating && currentRating.rating && (
                <span
                  className="text-[10px] uppercase tracking-wider font-medium px-2 py-0.5 rounded-full border"
                  style={{
                    color: RATING_COLORS[currentRating.rating] ?? '#9ca3af',
                    borderColor: RATING_COLORS[currentRating.rating] ?? '#9ca3af',
                  }}
                >
                  {t(`rating.${currentRating.rating}`)}
                  {currentRating.score != null && ` ${currentRating.score}/14`}
                </span>
              )}
            </div>
            <div className="flex items-center gap-2">
              {!isHarbour && (
                <Link
                  to={`/spots/${locationId}`}
                  className="text-[10px] text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)] no-underline"
                >
                  {t('spots.more_details')}
                </Link>
              )}
              <button
                onClick={() => setLocationId(null)}
                aria-label="Close location detail"
                className="w-6 h-6 flex items-center justify-center rounded-full hover:bg-[var(--color-bg-elevated)] text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] transition-colors"
              >
                <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M2 2 L10 10 M10 2 L2 10" />
                </svg>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ─── Conditions Bar ─── */}
      <div className="border-b border-[var(--color-border)] bg-[var(--color-bg)]">
        <div className="max-w-screen-lg mx-auto px-4 py-3 space-y-2">
          <div className="flex items-center gap-2">
            <DecisionPill label={t('activity.sail')} decision={sailDec} t={t} />
            {!isHarbour && <DecisionPill label={t('activity.surf')} decision={surfDec} t={t} />}
          </div>
          <div className="flex items-center gap-4 overflow-x-auto">
            {currentRecord && (
              <>
                <Stat label={t('common.wind')} value={`${currentRecord.wind_kt?.toFixed(0) ?? '--'}`} unit="kt"
                  detail={currentRecord.gust_kt ? `G${currentRecord.gust_kt.toFixed(0)}` : undefined}
                  observed={(!isFocusMode || isHarbour) && cwa?.wind_kt != null ? `${cwa.wind_kt.toFixed(0)} obs` : undefined} />
                <Stat label={t('common.temp')} value={`${currentRecord.temp_c?.toFixed(0) ?? '--'}`} unit="°C"
                  observed={(!isFocusMode || isHarbour) && cwa?.temp_c != null ? `${cwa.temp_c.toFixed(1)} obs` : undefined} />
                <Stat label={t('common.pressure')} value={`${currentRecord.mslp_hpa?.toFixed(0) ?? '--'}`} unit="hPa" />
              </>
            )}
            {waveRecord && (() => {
              const sh = 'swell_height' in waveRecord ? waveRecord.swell_height : ('swell_wave_height' in waveRecord ? waveRecord.swell_wave_height : undefined)
              const sp = 'swell_period' in waveRecord ? waveRecord.swell_period : ('swell_wave_period' in waveRecord ? waveRecord.swell_wave_period : undefined)
              return (
                <Stat label="Swell"
                  value={`${sh?.toFixed(1) ?? '--'}`}
                  unit="m"
                  detail={`@ ${sp?.toFixed(0) ?? '--'}s`}
                  observed={(!isFocusMode || isHarbour) && buoy?.wave_height_m != null ? `${buoy.wave_height_m.toFixed(1)} obs` : undefined} />
              )
            })()}
            {/* Wind type for focused surf spot */}
            {isFocusMode && !isHarbour && currentRating?.wind_dir != null && locationForecast?.spot.facing && (
              <div className="shrink-0 text-center min-w-[52px]">
                <p className="text-[9px] text-[var(--color-text-muted)] uppercase tracking-wider">Wind</p>
                <p className={`text-xs font-medium capitalize ${windTypeColorClass(windType(currentRating.wind_dir, locationForecast.spot.facing))}`}>
                  {windType(currentRating.wind_dir, locationForecast.spot.facing)}
                </p>
                <p className="text-[10px] text-[var(--color-text-muted)]">{degToCompass(currentRating.wind_dir)}</p>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ─── Content ─── */}
      <div className="md:px-4 py-4 max-w-screen-lg mx-auto space-y-4">

        {/* Browse mode content */}
        {!isFocusMode && (
          <>
            <WeatherWarnings />

            {/* Best spot banner */}
            {bestSpot && bestSpotName && (
              <button
                onClick={() => setLocationId(bestSpot.spotId)}
                className="mx-4 md:mx-0 w-[calc(100%-2rem)] md:w-full text-left border border-[var(--color-border)] rounded-xl px-4 py-3 hover:bg-[var(--color-bg-elevated)]/50 transition-colors"
              >
                <p className="text-[10px] uppercase tracking-widest text-[var(--color-text-muted)] mb-1">
                  {t('spots.best_now')}
                </p>
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold text-[var(--color-text-primary)]">{bestSpotName}</span>
                  <span
                    className="text-[10px] uppercase tracking-wider font-medium px-2 py-0.5 rounded-full border"
                    style={{
                      color: RATING_COLORS[bestSpot.rating] ?? '#9ca3af',
                      borderColor: RATING_COLORS[bestSpot.rating] ?? '#9ca3af',
                    }}
                  >
                    {t(`rating.${bestSpot.rating}`)} {bestSpot.score}/14
                  </span>
                </div>
              </button>
            )}

            {/* Surf Heatmap */}
            {data.surf && (
              <div className="mx-4 md:mx-0">
                <p className="text-[10px] uppercase tracking-widest text-[var(--color-text-muted)] mb-2">
                  {t('spots.heatmap_title')}
                </p>
                <SurfHeatmap spots={data.surf.spots} filter="all" onSelectSpot={setLocationId} />
              </div>
            )}

            {/* Location cards grid */}
            {data.surf && (
              <div className="mx-4 md:mx-0">
                <p className="text-[10px] uppercase tracking-widest text-[var(--color-text-muted)] mb-2">
                  {t('spots.all_locations')}
                </p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  {data.surf.spots.map(sf => (
                    <LocationCard
                      key={sf.spot.id}
                      forecast={sf}
                      lang={lang}
                      index={index}
                      keelungRecords={data.keelung?.records}
                      onSelect={() => setLocationId(sf.spot.id)}
                      t={t}
                    />
                  ))}
                </div>
              </div>
            )}

            {/* AI Summary — collapsed in browse */}
            {data.summary && (
              <AiSummary
                summary={data.summary}
                lang={lang}
                expanded={aiExpanded}
                onToggle={() => setAiExpanded(!aiExpanded)}
                t={t}
              />
            )}
          </>
        )}

        {/* Focus mode content */}
        {isFocusMode && (
          <>
            {/* Charts */}
            <Suspense fallback={null}>
              <div className="grid grid-cols-1 md:grid-cols-2 md:gap-4 gap-0">
                {chartRecords.length > 0 && (
                  <ChartCard title={t('common.wind')}>
                    <WindChart records={chartRecords} timeRange={timeRange} />
                  </ChartCard>
                )}

                {/* Wave chart — from ratings (model-independent) */}
                {data.wave?.ecmwf_wave?.records && (
                  <ChartCard title="Wave Height">
                    <WaveChart records={data.wave.ecmwf_wave.records} timeRange={timeRange} />
                  </ChartCard>
                )}

                {data.tide?.predictions && (
                  <ChartCard title="Tide">
                    <TideChart
                      predictions={data.tide.predictions}
                      extrema={data.tide.extrema}
                      timeRange={timeRange}
                    />
                  </ChartCard>
                )}

                {data.wave?.ecmwf_wave?.records && (
                  <ChartCard title="Swell Period">
                    <WavePeriodChart records={data.wave.ecmwf_wave.records} timeRange={timeRange} />
                  </ChartCard>
                )}

                {chartRecords.length > 0 && (
                  <ChartCard title={t('common.temp')}>
                    <TempChart records={chartRecords} timeRange={timeRange} />
                  </ChartCard>
                )}

                {chartRecords.length > 0 && (
                  <ChartCard title={t('common.pressure')}>
                    <PressureChart records={chartRecords} timeRange={timeRange} />
                  </ChartCard>
                )}

                {chartRecords.length > 0 && (
                  <ChartCard title={t('common.precip')}>
                    <PrecipChart records={chartRecords} timeRange={timeRange} />
                  </ChartCard>
                )}
              </div>
            </Suspense>

            {/* All Locations — collapsed */}
            {data.surf && (
              <CollapsibleSection title={t('spots.all_locations')} defaultOpen={false}>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  {data.surf.spots.map(sf => (
                    <LocationCard
                      key={sf.spot.id}
                      forecast={sf}
                      lang={lang}
                      index={index}
                      keelungRecords={data.keelung?.records}
                      onSelect={() => setLocationId(sf.spot.id)}
                      t={t}
                    />
                  ))}
                </div>
              </CollapsibleSection>
            )}

            {/* AI Summary — collapsed in focus */}
            {data.summary && (
              <AiSummary
                summary={data.summary}
                lang={lang}
                expanded={aiExpanded}
                onToggle={() => setAiExpanded(!aiExpanded)}
                t={t}
              />
            )}
          </>
        )}
      </div>
    </div>
  )
}

/* ── Sub-components ─────────────────────────────────────────────────────── */

function DecisionPill({ label, decision, t }: {
  label: string
  decision: 'go' | 'caution' | 'nogo'
  t: (key: string) => string
}) {
  const colors = {
    go: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
    caution: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
    nogo: 'bg-red-500/15 text-red-400 border-red-500/30',
  }
  return (
    <div className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-full border text-xs font-medium w-[120px] ${colors[decision]}`}>
      <span className="text-[var(--color-text-muted)] text-[10px] uppercase">{label}</span>
      <span className="truncate">{t(`decision.${decision}`)}</span>
    </div>
  )
}

function Stat({ label, value, unit, detail, observed }: {
  label: string; value: string; unit: string; detail?: string; observed?: string
}) {
  return (
    <div className="shrink-0 text-center min-w-[52px]">
      <p className="text-[9px] text-[var(--color-text-muted)] uppercase tracking-wider">{label}</p>
      <p className="text-sm font-semibold text-[var(--color-text-primary)] tabular-nums leading-tight">
        {value}<span className="text-[10px] text-[var(--color-text-muted)] ml-0.5">{unit}</span>
      </p>
      {detail && <p className="text-[10px] text-[var(--color-text-muted)] leading-tight">{detail}</p>}
      {observed && <p className="text-[9px] text-emerald-500/80 leading-tight">{observed}</p>}
    </div>
  )
}

function ChartCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="
      border-b border-[var(--color-border)] px-2 py-3
      md:border md:rounded-xl md:p-4
    ">
      <p className="text-[10px] uppercase tracking-widest text-[var(--color-text-muted)] mb-2 md:mb-3 ml-1 md:ml-0">
        {title}
      </p>
      {children}
    </div>
  )
}

function LocationCard({ forecast: sf, lang, index, keelungRecords, onSelect, t }: {
  forecast: SpotForecast
  lang: 'en' | 'zh'
  index: number
  keelungRecords?: { valid_utc: string }[]
  onSelect: () => void
  t: (key: string) => string
}) {
  const isHarbour = sf.spot.type === 'harbour'

  // Find closest rating to current timeline
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

  const windKt = currentRating?.wind_kt ?? 0
  const rating = currentRating?.rating
  const ratingColor = rating ? RATING_COLORS[rating] : undefined

  return (
    <button
      onClick={onSelect}
      className="text-left border border-[var(--color-border)] rounded-lg px-3 py-2.5 hover:bg-[var(--color-bg-elevated)]/50 transition-colors"
    >
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs font-medium text-[var(--color-text-primary)] truncate">
          {sf.spot.name[lang]}
        </span>
        {!isHarbour && rating && (
          <span className="text-[9px] uppercase font-medium ml-1 shrink-0" style={{ color: ratingColor }}>
            {t(`rating.${rating}`)}
          </span>
        )}
        {isHarbour && (
          <span className={`text-[9px] uppercase font-medium ml-1 shrink-0 ${
            sailDecision(windKt) === 'go' ? 'text-emerald-400' :
            sailDecision(windKt) === 'caution' ? 'text-amber-400' : 'text-red-400'
          }`}>
            {t(`decision.${sailDecision(windKt)}`)}
          </span>
        )}
      </div>
      <div className="text-[10px] text-[var(--color-text-muted)] space-y-0.5">
        <p>
          {t('common.wind')} {currentRating?.wind_kt?.toFixed(0) ?? '--'}kt
          {currentRating?.wind_dir != null && ` ${degToCompass(currentRating.wind_dir)}`}
        </p>
        {!isHarbour && currentRating?.swell_height != null && (
          <p>Swell {currentRating.swell_height.toFixed(1)}m
            {currentRating.swell_period != null && ` @ ${currentRating.swell_period.toFixed(0)}s`}
          </p>
        )}
      </div>
    </button>
  )
}

function CollapsibleSection({ title, defaultOpen, children }: {
  title: string; defaultOpen: boolean; children: React.ReactNode
}) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="mx-4 md:mx-0 border border-[var(--color-border)] rounded-xl overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-[var(--color-bg-elevated)]/50 transition-colors"
      >
        <span className="text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">{title}</span>
        <svg
          width="12" height="12" viewBox="0 0 12 12"
          className={`text-[var(--color-text-muted)] transition-transform ${open ? 'rotate-180' : ''}`}
          fill="none" stroke="currentColor" strokeWidth="2"
        >
          <path d="M2 4 L6 8 L10 4" />
        </svg>
      </button>
      {open && <div className="px-4 pb-4">{children}</div>}
    </div>
  )
}

function AiSummary({ summary, lang, expanded, onToggle, t }: {
  summary: { wind: Record<string, string>; waves: Record<string, string>; outlook: Record<string, string> }
  lang: 'en' | 'zh'
  expanded: boolean
  onToggle: () => void
  t: (key: string) => string
}) {
  return (
    <div className="mx-4 md:mx-0 border border-[var(--color-border)] rounded-xl overflow-hidden">
      <button
        onClick={onToggle}
        className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-[var(--color-bg-elevated)]/50 transition-colors"
      >
        <span className="text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
          {t('ai.title')}
        </span>
        <svg
          width="12" height="12" viewBox="0 0 12 12"
          className={`text-[var(--color-text-muted)] transition-transform ${expanded ? 'rotate-180' : ''}`}
          fill="none" stroke="currentColor" strokeWidth="2"
        >
          <path d="M2 4 L6 8 L10 4" />
        </svg>
      </button>
      {expanded && (
        <div className="px-4 pb-4 space-y-2 text-sm text-[var(--color-text-secondary)] leading-relaxed">
          <p>{summary.wind[lang]}</p>
          <p>{summary.waves[lang]}</p>
          <p>{summary.outlook[lang]}</p>
        </div>
      )}
    </div>
  )
}
