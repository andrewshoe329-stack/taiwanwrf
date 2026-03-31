import { lazy, Suspense, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { SPOTS, HARBOURS } from '@/lib/constants'
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
import { SpotCompare } from '@/components/spots/SpotCompare'
import { TideSparkline } from '@/components/charts/TideSparkline'
import {
  degToCompass, getModelRecords, windType,
  ratingsToWaveRecords, ratingsToTidePredictions, getSpotTideExtrema,
} from '@/lib/forecast-utils'
import { useLiveObsContext } from '@/App'
import type { TimeRange } from '@/components/charts/chart-utils'
import type { SpotForecast } from '@/lib/types'

const TIDE_LEVEL_MAP: Record<string, { en: string; zh: string }> = {
  '漲潮': { en: 'Rising', zh: '漲潮' },
  '退潮': { en: 'Falling', zh: '退潮' },
  '滿潮': { en: 'High', zh: '滿潮' },
  '乾潮': { en: 'Low', zh: '乾潮' },
}

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

          {/* Swell compass + data cells (desktop only — on mobile, shown below timeline) */}
          {!mobile && currentRating && (
            <div className="space-y-2">
              <div className="flex justify-center">
                <SwellCompass
                  facing={spotInfo.facing}
                  optSwell={spotInfo.opt_swell}
                  swellDir={currentRating.swell_dir}
                  swellHeight={currentRating.swell_height}
                  size={100}
                />
              </div>
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
              {tidePredictions.length > 0 && (
                <TideSparkline
                  predictions={tidePredictions}
                  extrema={tideExtrema}
                  nowMs={data.keelung?.records?.[index]?.valid_utc
                    ? new Date(data.keelung.records[index].valid_utc).getTime()
                    : undefined}
                />
              )}
            </div>
          )}

          {/* Info pills + wind type + warnings */}
          <div className="flex flex-wrap gap-1.5">
            <InfoPill label={t('spots.facing')} value={spotInfo.facing} />
            <InfoPill label={t('spots.optimal_wind')} value={spotInfo.opt_wind.join(', ')} />
            {currentRating?.wind_dir != null && spotInfo.facing && (
              <InfoPill label={t('common.wind')} value={windType(currentRating.wind_dir, spotInfo.facing)} />
            )}
            {data.cwa_obs?.specialized_warnings?.map((w, i) => (
              <span key={i} className={`text-[10px] px-1.5 py-0.5 rounded ${
                w.type === 'rain' ? 'bg-blue-500/20 text-blue-400' :
                w.type === 'heat' ? 'bg-red-500/20 text-red-400' :
                'bg-cyan-500/20 text-cyan-400'
              }`}>
                {w.severity_level || w.event || w.type}
              </span>
            ))}
            {spotInfo.webcams?.map((cam, i) => (
              <a
                key={i}
                href={cam.url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded bg-[var(--color-bg-elevated)] text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] transition-colors"
              >
                <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M23 7l-7 5 7 5V7z" /><rect x="1" y="5" width="15" height="14" rx="2" ry="2" />
                </svg>
                {cam.label}
              </a>
            ))}
          </div>

          {/* CWA real-time observations (live from serverless, or fallback to deploy-time) */}
          {(() => {
            const live = liveObs.data?.spots?.[spotInfo.id]
            const stale = data.cwa_obs?.spot_obs?.[spotInfo.id]
            const stn = live?.station ?? stale?.station
            const buoy = live?.buoy ?? stale?.buoy
            const tide = live?.tide
            if (!stn && !buoy && !tide) return null
            const waterTemp = tide?.sea_temp_c ?? live?.buoy?.sea_temp_c ?? stale?.buoy?.water_temp_c
            const items: { label: string; value: string; accent?: boolean }[] = []
            if (stn?.temp_c != null) items.push({ label: t('live.temp'), value: `${stn.temp_c.toFixed(1)}°C` })
            if (stn?.wind_kt != null) items.push({ label: t('live.wind'), value: `${stn.wind_kt.toFixed(0)}${stn.gust_kt ? `G${stn.gust_kt.toFixed(0)}` : ''}kt ${stn.wind_dir != null ? degToCompass(stn.wind_dir) : ''}` })
            if (stn?.pressure_hpa != null) items.push({ label: t('live.pressure'), value: `${stn.pressure_hpa.toFixed(0)} hPa` })
            if (tide?.tide_height_m != null) { const tl = tide.tide_level ? (TIDE_LEVEL_MAP[tide.tide_level]?.[lang] ?? tide.tide_level) : ''; items.push({ label: t('live.tide'), value: `${tide.tide_height_m.toFixed(2)}m${tl ? ` ${tl}` : ''}` }) }
            if (buoy?.wave_height_m != null) items.push({ label: t('live.waves'), value: `${buoy.wave_height_m.toFixed(1)}m${buoy.wave_period_s ? ` ${buoy.wave_period_s.toFixed(0)}s` : ''}` })
            if (waterTemp != null) items.push({ label: t('live.water_temp'), value: `${waterTemp.toFixed(1)}°C` })
            if (live?.station?.visibility_km != null && live.station.visibility_km < 10) items.push({ label: t('live.visibility'), value: `${live.station.visibility_km.toFixed(1)}km` })
            if (live?.station?.uv_index != null && live.station.uv_index > 0) items.push({ label: 'UV', value: `${live.station.uv_index.toFixed(0)}`, accent: live.station.uv_index >= 6 })
            if (live?.buoy?.current_speed_ms != null && live.buoy.current_speed_ms > 0.1) items.push({ label: t('common.current') || 'Current', value: `${(live.buoy.current_speed_ms * 1.94384).toFixed(1)}kt ${live.buoy.current_dir != null ? degToCompass(live.buoy.current_dir) : ''}` })
            if (!items.length) return null
            return (
              <div className="mt-2 rounded-lg bg-[var(--color-bg-elevated)]/50 border border-[var(--color-border)] p-2">
                <div className="grid grid-cols-3 gap-x-2 gap-y-1.5">
                  {items.map((item, i) => (
                    <div key={i} className="text-center">
                      <p className="text-[8px] uppercase tracking-wider text-[var(--color-text-dim)]">{item.label}</p>
                      <p className={`text-[11px] font-medium tabular-nums leading-tight ${item.accent ? 'text-orange-400' : 'text-[var(--color-text-secondary)]'}`}>{item.value}</p>
                    </div>
                  ))}
                </div>
                {liveObs.data && (
                  <p className="text-[8px] text-[var(--color-text-dim)] mt-1.5 text-center">{t('live.title')}</p>
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
                  {data.accuracy[0].wave?.hs_mae_m != null && ` · ±${data.accuracy[0].wave.hs_mae_m.toFixed(1)}m wave`}
                </span>
              )}
              {data.accuracy?.[0]?.by_horizon?.['0-24h']?.wind_mae_kt != null && (
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--color-bg-elevated)] text-[var(--color-text-muted)]">
                  24h: ±{data.accuracy[0].by_horizon['0-24h'].wind_mae_kt.toFixed(1)}kt
                </span>
              )}
              {data.ensemble?.spread?.precip_spread_mm != null && data.ensemble.spread.precip_spread_mm > 1 && (
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--color-bg-elevated)] text-[var(--color-text-muted)]">
                  Rain spread ±{data.ensemble.spread.precip_spread_mm.toFixed(1)}mm
                </span>
              )}
            </div>
          )}
        </section>
      )}

      {/* Harbour selected */}
      {locationId === 'keelung' && (
        <section className="md:px-3 py-3 space-y-3">
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

          {/* Webcam links for Keelung */}
          {HARBOURS[0]?.webcams && (
            <div className="flex flex-wrap gap-1.5">
              {HARBOURS[0].webcams.map((cam, i) => (
                <a
                  key={i}
                  href={cam.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded bg-[var(--color-bg-elevated)] text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] transition-colors"
                >
                  <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M23 7l-7 5 7 5V7z" /><rect x="1" y="5" width="15" height="14" rx="2" ry="2" />
                  </svg>
                  {cam.label}
                </a>
              ))}
            </div>
          )}

          {/* Live observations for Keelung */}
          {(() => {
            const live = liveObs.data?.spots?.keelung
            const stale = data.cwa_obs?.spot_obs?.keelung ?? data.cwa_obs
            const stn = live?.station ?? stale?.station
            const tide = live?.tide
            const buoy = live?.buoy ?? stale?.buoy
            if (!stn && !buoy && !tide) return null
            const waterTemp = tide?.sea_temp_c ?? live?.buoy?.sea_temp_c ?? stale?.buoy?.water_temp_c
            const items: { label: string; value: string; accent?: boolean }[] = []
            if (stn?.temp_c != null) items.push({ label: t('live.temp'), value: `${stn.temp_c.toFixed(1)}°C` })
            if (stn?.wind_kt != null) items.push({ label: t('live.wind'), value: `${stn.wind_kt.toFixed(0)}${stn.gust_kt ? `G${stn.gust_kt.toFixed(0)}` : ''}kt ${stn.wind_dir != null ? degToCompass(stn.wind_dir) : ''}` })
            if (stn?.pressure_hpa != null) items.push({ label: t('live.pressure'), value: `${stn.pressure_hpa.toFixed(0)} hPa` })
            if (tide?.tide_height_m != null) { const tl = tide.tide_level ? (TIDE_LEVEL_MAP[tide.tide_level]?.[lang] ?? tide.tide_level) : ''; items.push({ label: t('live.tide'), value: `${tide.tide_height_m.toFixed(2)}m${tl ? ` ${tl}` : ''}` }) }
            if (buoy?.wave_height_m != null) items.push({ label: t('live.waves'), value: `${buoy.wave_height_m.toFixed(1)}m${buoy.wave_period_s ? ` ${buoy.wave_period_s.toFixed(0)}s` : ''}` })
            if (waterTemp != null) items.push({ label: t('live.water_temp'), value: `${waterTemp.toFixed(1)}°C` })
            if (live?.station?.visibility_km != null && live.station.visibility_km < 10) items.push({ label: t('live.visibility'), value: `${live.station.visibility_km.toFixed(1)}km` })
            if (live?.station?.uv_index != null && live.station.uv_index > 0) items.push({ label: 'UV', value: `${live.station.uv_index.toFixed(0)}`, accent: live.station.uv_index >= 6 })
            if (live?.buoy?.current_speed_ms != null && live.buoy.current_speed_ms > 0.1) items.push({ label: t('common.current'), value: `${(live.buoy.current_speed_ms * 1.94384).toFixed(1)}kt ${live.buoy.current_dir != null ? degToCompass(live.buoy.current_dir) : ''}` })
            if (!items.length) return null
            return (
              <div className="mt-2 rounded-lg bg-[var(--color-bg-elevated)]/50 border border-[var(--color-border)] p-2">
                <div className="grid grid-cols-3 gap-x-2 gap-y-1.5">
                  {items.map((item, i) => (
                    <div key={i} className="text-center">
                      <p className="text-[8px] uppercase tracking-wider text-[var(--color-text-dim)]">{item.label}</p>
                      <p className={`text-[11px] font-medium tabular-nums leading-tight ${item.accent ? 'text-orange-400' : 'text-[var(--color-text-secondary)]'}`}>{item.value}</p>
                    </div>
                  ))}
                </div>
                {liveObs.data && (
                  <p className="text-[8px] text-[var(--color-text-dim)] mt-1.5 text-center">{t('live.title')}</p>
                )}
              </div>
            )
          })()}

          {/* Ensemble confidence + accuracy */}
          {data.ensemble?.spread && (
            <div className="flex flex-wrap gap-1.5">
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
                  {data.accuracy[0].wave?.hs_mae_m != null && ` · ±${data.accuracy[0].wave.hs_mae_m.toFixed(1)}m wave`}
                </span>
              )}
              {data.accuracy?.[0]?.by_horizon?.['0-24h']?.wind_mae_kt != null && (
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--color-bg-elevated)] text-[var(--color-text-muted)]">
                  24h: ±{data.accuracy[0].by_horizon['0-24h'].wind_mae_kt.toFixed(1)}kt
                </span>
              )}
              {data.ensemble?.spread?.precip_spread_mm != null && data.ensemble.spread.precip_spread_mm > 1 && (
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--color-bg-elevated)] text-[var(--color-text-muted)]">
                  Rain spread ±{data.ensemble.spread.precip_spread_mm.toFixed(1)}mm
                </span>
              )}
            </div>
          )}
        </section>
      )}

      {/* Spot comparison (browse mode — no spot selected) */}
      {!isSpotSelected && locationId !== 'keelung' && data.surf?.spots && (
        <section className="md:px-3 py-2">
          <SpotCompare
            spots={data.surf.spots}
            targetUtc={data.keelung?.records?.[index]?.valid_utc}
            onSelectSpot={setLocationId}
          />
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
  const chartsPanel = (compact?: boolean) => (
    <div className={compact ? "space-y-1.5" : "space-y-3"}>
      {/* Sticky header: timeline + conditions (only in non-compact / mobile) */}
      {!compact && (
        <div className="sticky top-0 z-10 bg-[var(--color-bg)] border-b border-[var(--color-border)] -mx-4 px-4 md:-mx-6 md:px-6">
          <TimelineScrubber records={chartRecords} />
          <ConditionsStrip />
        </div>
      )}

      {/* Swell compass + data cells (mobile only — placed below timeline for clear connection) */}
      {!compact && mobile && isSpotSelected && spotInfo && currentRating && (
        <div className="flex items-start gap-3 px-1">
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
            {tidePredictions.length > 0 && (
              <TideSparkline
                predictions={tidePredictions}
                extrema={tideExtrema}
                nowMs={data.keelung?.records?.[index]?.valid_utc
                  ? new Date(data.keelung.records[index].valid_utc).getTime()
                  : undefined}
              />
            )}
          </div>
        </div>
      )}

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

        {/* Precip + Temp: side by side on desktop (non-compact), stacked otherwise */}
        <div className={!compact && !mobile ? 'grid grid-cols-2 gap-3' : 'space-y-1.5'}>
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
    </div>
  )

  /* ── Desktop: 3-column layout ──────────────────────────────────────── */
  if (!mobile) {
    return (
      <div className="flex h-full">
        {/* Left column: location detail + AI summary */}
        <div className="w-[260px] min-w-[240px] shrink-0 border-r border-[var(--color-border)] flex flex-col overflow-y-auto">
          <div className="px-1 py-2">
            {locationDetail}
          </div>
        </div>

        {/* Center column: map + timeline + conditions */}
        <div className="flex-1 flex flex-col min-w-0">
          {/* Map takes most of the space */}
          <div className="relative flex-1 min-h-[300px]">
            <Suspense fallback={<div className="w-full h-full bg-black" />}>
              <ForecastMap selectedId={locationId} onSelectLocation={setLocationId} />
            </Suspense>
          </div>
          {/* Timeline + conditions below map */}
          <div className="shrink-0 border-t border-[var(--color-border)] px-3">
            <TimelineScrubber records={chartRecords} />
            <ConditionsStrip />
          </div>
        </div>

        {/* Right column: compact charts */}
        <div className="w-[300px] min-w-[260px] shrink-0 border-l border-[var(--color-border)] overflow-y-auto px-2 py-1.5">
          {chartsPanel(true)}
        </div>
      </div>
    )
  }

  /* ── Mobile: map top (40vh), detail + charts below (scrolls) ───────── */
  return (
    <div className="h-full overflow-y-auto overflow-x-hidden">
      {/* Map section — shorter in landscape to leave room for data */}
      <div className="h-[40vh] min-h-[200px] max-h-[360px] landscape:h-[30vh] landscape:min-h-[140px] landscape:max-h-[240px] relative shrink-0">
        <Suspense fallback={<div className="w-full h-full bg-black" />}>
          <ForecastMap selectedId={locationId} onSelectLocation={setLocationId} />
        </Suspense>
      </div>

      {/* Data section */}
      <div className="px-4 py-2">
        {locationDetail}
        {chartsPanel()}
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
