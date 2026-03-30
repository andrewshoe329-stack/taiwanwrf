import { lazy, Suspense, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useForecastData } from '@/hooks/useForecastData'
import { LoadingSpinner } from '@/components/layout/LoadingSpinner'
import { WeatherWarnings } from '@/components/layout/WeatherWarnings'
import { DataFreshness } from '@/components/layout/DataFreshness'
import { HarbourForecastTable } from '@/components/shared/ForecastTable'
import {
  degToCompass, windColorClass, waveColorClass, sailDecision,
} from '@/lib/forecast-utils'
import type { ForecastRecord, WaveRecord, TideExtremum } from '@/lib/types'
import type { TimeRange } from '@/components/charts/chart-utils'

const WindChart = lazy(() => import('@/components/charts/WindChart').then(m => ({ default: m.WindChart })))
const TideChart = lazy(() => import('@/components/charts/TideChart').then(m => ({ default: m.TideChart })))

export function HarboursPage() {
  const { t, i18n } = useTranslation()
  const lang = (i18n.language.startsWith('zh') ? 'zh' : 'en') as 'en' | 'zh'
  const data = useForecastData()
  const [showTable, setShowTable] = useState(true)

  if (data.loading) return <LoadingSpinner />

  if (data.error && !data.ecmwf && !data.wave) {
    return (
      <div className="px-4 py-6 pb-24 max-w-screen-xl mx-auto">
        <h1 className="text-lg font-semibold text-[var(--color-text-primary)] mb-4">
          {lang === 'zh' ? '基隆港' : 'Keelung Harbour'}
        </h1>
        <div className="border border-[var(--color-danger)]/30 rounded-xl p-6 text-center">
          <p className="text-sm text-[var(--color-text-muted)]">{t('common.error')}</p>
        </div>
      </div>
    )
  }

  const records = data.ecmwf?.records ?? []
  const waveRecords = data.wave?.ecmwf_wave?.records ?? []
  const ensemble = data.ensemble
  const cwa = data.cwa_obs?.station
  const buoy = data.cwa_obs?.buoy

  // Current conditions (first record)
  const windRec: ForecastRecord | undefined = records[0]
  const waveRec: WaveRecord | undefined = waveRecords[0]

  // Sail decision
  const windKt = windRec?.wind_kt ?? 0
  const sailDec = sailDecision(windKt)

  // Ensemble spread
  const spread = ensemble?.spread
  const hasSpread = spread && (spread.wind_spread_kt != null || spread.temp_spread_c != null)

  // Tide info
  const tideExtrema = data.tide?.extrema ?? []
  const nextTide = tideExtrema.find(e => new Date(e.time_utc).getTime() > Date.now())
  const currentTideHeight = useMemo(() => {
    if (!data.tide?.predictions?.length) return undefined
    const now = Date.now()
    let closest = data.tide.predictions[0]
    let closestDiff = Infinity
    for (const p of data.tide.predictions) {
      const diff = Math.abs(new Date(p.time_utc).getTime() - now)
      if (diff < closestDiff) { closestDiff = diff; closest = p }
    }
    return closest.height_m
  }, [data.tide])

  const timeRange: TimeRange | undefined = useMemo(() => {
    if (!records.length) return undefined
    return { startUtc: records[0].valid_utc, endUtc: records[records.length - 1].valid_utc }
  }, [records])

  const decisionStyle = {
    go: 'border-emerald-500/40 bg-emerald-500/5',
    caution: 'border-amber-500/40 bg-amber-500/5',
    nogo: 'border-red-500/40 bg-red-500/5',
  }
  const decisionTextColor = {
    go: 'text-emerald-400',
    caution: 'text-amber-400',
    nogo: 'text-red-400',
  }

  return (
    <div className="px-4 pt-4 pb-24 max-w-screen-xl mx-auto">
      {/* Header */}
      <div className="flex items-start justify-between mb-1">
        <div>
          <h1 className="text-lg font-semibold text-[var(--color-text-primary)]">
            {lang === 'zh' ? '基隆港' : 'Keelung Harbour'}
          </h1>
          <p className="text-xs text-[var(--color-text-muted)]">
            {lang === 'zh' ? 'Keelung Harbour' : '基隆港'}
          </p>
        </div>
        <div className="flex flex-col items-end gap-1">
          <span className={`text-sm font-semibold ${decisionTextColor[sailDec]}`}>
            {t(`decision.${sailDec}`)}
          </span>
          <DataFreshness />
        </div>
      </div>

      {/* Weather Warnings */}
      <div className="mb-4">
        <WeatherWarnings />
      </div>

      {/* Current conditions hero */}
      <section className={`border rounded-xl p-4 mb-4 ${decisionStyle[sailDec]}`}>
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
          <MiniStat
            label={t('common.wind')}
            value={windRec?.wind_kt != null ? `${windRec.wind_kt.toFixed(0)}` : '--'}
            unit="kt"
            colorClass={windRec?.wind_kt != null ? windColorClass(windRec.wind_kt) : undefined}
            sub={windRec?.gust_kt != null ? `G${windRec.gust_kt.toFixed(0)}` : undefined}
            observed={cwa?.wind_kt != null ? `${cwa.wind_kt.toFixed(0)} obs` : undefined}
          />
          <MiniStat
            label={t('harbours_page.direction')}
            value={windRec?.wind_dir != null ? degToCompass(windRec.wind_dir) : '--'}
            unit={windRec?.wind_dir != null ? `${windRec.wind_dir}°` : ''}
          />
          <MiniStat
            label={t('harbours_page.waves')}
            value={waveRec?.wave_height != null ? waveRec.wave_height.toFixed(1) : '--'}
            unit="m"
            colorClass={waveRec?.wave_height != null ? waveColorClass(waveRec.wave_height) : undefined}
            sub={waveRec?.wave_period != null ? `${waveRec.wave_period.toFixed(0)}s` : undefined}
            observed={buoy?.wave_height_m != null ? `${buoy.wave_height_m.toFixed(1)} obs` : undefined}
          />
          <MiniStat
            label={t('common.temp')}
            value={windRec?.temp_c != null ? windRec.temp_c.toFixed(0) : '--'}
            unit="°C"
            observed={cwa?.temp_c != null ? `${cwa.temp_c.toFixed(1)} obs` : undefined}
          />
          <MiniStat
            label={t('harbours_page.tide')}
            value={currentTideHeight != null ? currentTideHeight.toFixed(2) : '--'}
            unit="m"
            sub={nextTide ? `${t(`harbours_page.${nextTide.type}`)} ${formatTideTime(nextTide)}` : undefined}
          />
        </div>

        {/* Ensemble confidence */}
        {hasSpread && (
          <div className="mt-3 flex items-center gap-3 text-xs text-[var(--color-text-muted)]">
            <span>{t('harbours_page.model_spread')}:</span>
            {spread!.wind_spread_kt != null && <span>{t('common.wind')} ±{spread!.wind_spread_kt.toFixed(1)} kt</span>}
            {spread!.temp_spread_c != null && <span>{t('common.temp')} ±{spread!.temp_spread_c.toFixed(1)}°</span>}
          </div>
        )}
      </section>

      {/* Charts: Wind + Tide side by side */}
      <Suspense fallback={null}>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
          {records.length > 0 && (
            <ChartCard title={t('common.wind')}>
              <WindChart records={records} ecmwfRecords={data.keelung?.records} timeRange={timeRange} />
            </ChartCard>
          )}
          {data.tide?.predictions && (
            <ChartCard title={t('harbours_page.tide')}>
              <TideChart predictions={data.tide.predictions} extrema={data.tide.extrema} timeRange={timeRange} />
            </ChartCard>
          )}
        </div>
      </Suspense>

      {/* Forecast table */}
      {records.length > 1 && (
        <section className="border border-[var(--color-border)] rounded-xl p-4">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-xs font-medium text-[var(--color-text-secondary)] uppercase tracking-wider">
              {t('harbours_page.forecast_timeline')}
            </h2>
            <button
              onClick={() => setShowTable(!showTable)}
              className="text-xs text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] transition-colors flex items-center gap-1"
            >
              <svg className={`w-3 h-3 transition-transform ${showTable ? 'rotate-180' : ''}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                <path d="M6 9l6 6 6-6" />
              </svg>
              {showTable ? t('harbours_page.hide_forecast') : t('harbours_page.show_forecast')}
            </button>
          </div>
          {showTable && (
            <HarbourForecastTable records={records} waveRecords={waveRecords} lang={lang} />
          )}
        </section>
      )}

      {/* No data fallback */}
      {!data.ecmwf && !data.wave && (
        <div className="border border-[var(--color-border)] rounded-xl p-8 text-center mt-4">
          <p className="text-sm text-[var(--color-text-muted)]">{t('harbours_page.no_data')}</p>
        </div>
      )}
    </div>
  )
}

/* ── Sub-components ─────────────────────────────────────────────────────────── */

function MiniStat({ label, value, unit, colorClass, sub, observed }: {
  label: string; value: string; unit: string; colorClass?: string; sub?: string; observed?: string
}) {
  return (
    <div className="bg-[var(--color-bg-elevated)] rounded-lg px-3 py-2">
      <p className="text-[10px] text-[var(--color-text-muted)] uppercase tracking-wider mb-0.5">{label}</p>
      <p className={`text-base font-semibold tabular-nums ${colorClass ?? 'text-[var(--color-text-primary)]'}`}>
        {value}
        <span className="text-xs text-[var(--color-text-muted)] ml-0.5">{unit}</span>
      </p>
      {sub && <p className="text-[10px] text-[var(--color-text-dim)]">{sub}</p>}
      {observed && <p className="text-[9px] text-emerald-500/80 leading-tight">{observed}</p>}
    </div>
  )
}

function ChartCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="border border-[var(--color-border)] rounded-xl p-4">
      <p className="text-[10px] uppercase tracking-widest text-[var(--color-text-muted)] mb-2">{title}</p>
      {children}
    </div>
  )
}

function formatTideTime(e: TideExtremum): string {
  const d = new Date(e.time_utc)
  d.setUTCHours(d.getUTCHours() + 8)
  return `${String(d.getUTCHours()).padStart(2, '0')}:${String(d.getUTCMinutes()).padStart(2, '0')}`
}
