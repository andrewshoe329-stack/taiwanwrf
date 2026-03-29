import { lazy, Suspense, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useForecastData } from '@/hooks/useForecastData'
import { useTimeline } from '@/hooks/useTimeline'
import { TimelineScrubber } from '@/components/timeline/TimelineScrubber'
import type { TimeRange } from '@/components/charts/chart-utils'

const ForecastMap = lazy(() => import('@/components/map/ForecastMap').then(m => ({ default: m.ForecastMap })))
const WindChart = lazy(() => import('@/components/charts/WindChart').then(m => ({ default: m.WindChart })))
const WaveChart = lazy(() => import('@/components/charts/WaveChart').then(m => ({ default: m.WaveChart })))
const WavePeriodChart = lazy(() => import('@/components/charts/WaveChart').then(m => ({ default: m.WavePeriodChart })))
const TideChart = lazy(() => import('@/components/charts/TideChart').then(m => ({ default: m.TideChart })))
const TempChart = lazy(() => import('@/components/charts/TempPressureChart').then(m => ({ default: m.TempChart })))
const PressureChart = lazy(() => import('@/components/charts/TempPressureChart').then(m => ({ default: m.PressureChart })))

export function NowPage() {
  const { t, i18n } = useTranslation()
  const data = useForecastData()
  const { index } = useTimeline()
  const [aiExpanded, setAiExpanded] = useState(true)

  const timeRange: TimeRange | undefined = useMemo(() => {
    const recs = data.keelung?.records
    if (!recs?.length) return undefined
    return { startUtc: recs[0].valid_utc, endUtc: recs[recs.length - 1].valid_utc }
  }, [data.keelung?.records])

  const record = data.keelung?.records?.[index]
  const waveRecords = data.wave?.ecmwf_wave?.records
  const waveRecord = record?.valid_utc
    ? waveRecords?.find(w => w.valid_utc === record.valid_utc) ?? waveRecords?.[index]
    : waveRecords?.[index]

  // Decision logic
  const windKt = record?.wind_kt ?? 0
  const waveHt = waveRecord?.wave_height ?? 0

  let sailDecision: 'go' | 'caution' | 'nogo' = 'caution'
  if (windKt >= 8 && windKt <= 25) sailDecision = 'go'
  else if (windKt > 35 || windKt < 4) sailDecision = 'nogo'

  let surfDecision: 'go' | 'caution' | 'nogo' = 'caution'
  if (waveHt >= 0.6 && waveHt <= 2.5 && windKt < 20) surfDecision = 'go'
  else if (waveHt > 4 || windKt > 30) surfDecision = 'nogo'

  // CWA observed badge
  const cwa = data.cwa_obs?.station

  if (data.loading) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <div className="text-center">
          <div className="w-5 h-5 border-2 border-[var(--color-text-muted)] border-t-transparent rounded-full animate-spin mx-auto mb-3" />
          <p className="text-[var(--color-text-muted)] text-xs">{t('common.loading')}</p>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen">
      {/* Map + sticky timeline overlay */}
      <div className="relative h-[50vh] md:h-[55vh]">
        <Suspense fallback={<div className="w-full h-full bg-[var(--color-bg-card)]" />}>
          <ForecastMap />
        </Suspense>
        {/* Timeline overlaying bottom of map */}
        <div className="absolute bottom-0 left-0 right-0 bg-[var(--color-bg)]/80 backdrop-blur-md border-t border-[var(--color-border)]/50">
          <TimelineScrubber />
        </div>
      </div>

      {/* Conditions bar */}
      <div className="border-b border-[var(--color-border)] bg-[var(--color-bg)]">
        <div className="max-w-screen-lg mx-auto px-4 py-3 space-y-2">
          {/* Decisions — fixed-width pills so stats don't jump */}
          <div className="flex items-center gap-2">
            <DecisionPill label={t('activity.sail')} decision={sailDecision} t={t} />
            <DecisionPill label={t('activity.surf')} decision={surfDecision} t={t} />
          </div>
          {/* Stats — scrollable row */}
          <div className="flex items-center gap-4 overflow-x-auto">
            {record && (
              <>
                <Stat label={t('common.wind')} value={`${record.wind_kt?.toFixed(0) ?? '--'}`} unit="kt"
                  detail={record.gust_kt ? `G${record.gust_kt.toFixed(0)}` : undefined}
                  observed={cwa?.wind_kt != null ? `${cwa.wind_kt.toFixed(0)} obs` : undefined} />
                <Stat label={t('common.temp')} value={`${record.temp_c?.toFixed(0) ?? '--'}`} unit="°C"
                  observed={cwa?.temp_c != null ? `${cwa.temp_c.toFixed(1)} obs` : undefined} />
                <Stat label={t('common.pressure')} value={`${record.mslp_hpa?.toFixed(0) ?? '--'}`} unit="hPa" />
              </>
            )}
            {waveRecord && (
              <>
                <Stat label="Swell" value={`${waveRecord.swell_wave_height?.toFixed(1) ?? '--'}`} unit="m"
                  detail={`@ ${waveRecord.swell_wave_period?.toFixed(0) ?? '--'}s`} />
                <Stat label="Wind Sea" value={`${waveRecord.wind_wave_height?.toFixed(1) ?? '--'}`} unit="m" />
              </>
            )}
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="md:px-4 py-4 max-w-screen-lg mx-auto space-y-4">
        {/* AI Summary — collapsible */}
        {data.summary && (() => {
          const lang = i18n.language.startsWith('zh') ? 'zh' : 'en'
          return (
            <div className="mx-4 md:mx-0 border border-[var(--color-border)] rounded-xl overflow-hidden">
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
          )
        })()}

        {/* Charts — 2-col on desktop, full-bleed stacked on mobile */}
        <Suspense fallback={null}>
          <div className="grid grid-cols-1 md:grid-cols-2 md:gap-4 gap-0">
            {data.keelung?.records && (
              <ChartCard title={t('common.wind')}>
                <WindChart
                  records={data.keelung.records}
                  ecmwfRecords={data.ecmwf?.records}
                  timeRange={timeRange}
                />
              </ChartCard>
            )}

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

            {data.keelung?.records && (
              <ChartCard title={t('common.temp')}>
                <TempChart records={data.keelung.records} timeRange={timeRange} />
              </ChartCard>
            )}

            {data.keelung?.records && (
              <ChartCard title={t('common.pressure')}>
                <PressureChart records={data.keelung.records} timeRange={timeRange} />
              </ChartCard>
            )}
          </div>
        </Suspense>
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
