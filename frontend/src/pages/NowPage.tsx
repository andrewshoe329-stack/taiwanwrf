import { lazy, Suspense } from 'react'
import { useTranslation } from 'react-i18next'
import { useForecastData } from '@/hooks/useForecastData'
import { useTimeline } from '@/hooks/useTimeline'
import { useActivity } from '@/hooks/useActivity'
import { TimelineScrubber } from '@/components/timeline/TimelineScrubber'

const ForecastMap = lazy(() => import('@/components/map/ForecastMap').then(m => ({ default: m.ForecastMap })))
const WindChart = lazy(() => import('@/components/charts/WindChart').then(m => ({ default: m.WindChart })))
const WaveChart = lazy(() => import('@/components/charts/WaveChart').then(m => ({ default: m.WaveChart })))
const TideChart = lazy(() => import('@/components/charts/TideChart').then(m => ({ default: m.TideChart })))
const TempPressureChart = lazy(() => import('@/components/charts/TempPressureChart').then(m => ({ default: m.TempPressureChart })))

export function NowPage() {
  const { t, i18n } = useTranslation()
  const data = useForecastData()
  const { index } = useTimeline()
  const { activity } = useActivity()

  const record = data.keelung?.records?.[index]
  const waveRecord = data.wave?.ecmwf_wave?.records?.[index]

  // Decision logic
  const windKt = record?.wind_kt ?? 0
  const waveHt = waveRecord?.wave_height ?? 0

  let sailDecision: 'go' | 'caution' | 'nogo' = 'caution'
  if (windKt >= 8 && windKt <= 25) sailDecision = 'go'
  else if (windKt > 35 || windKt < 4) sailDecision = 'nogo'

  let surfDecision: 'go' | 'caution' | 'nogo' = 'caution'
  if (waveHt >= 0.6 && waveHt <= 2.5 && windKt < 20) surfDecision = 'go'
  else if (waveHt > 4 || windKt > 30) surfDecision = 'nogo'

  const decision = activity === 'sail' ? sailDecision : surfDecision
  const decisionColors = {
    go: 'border-[var(--color-rating-good)]',
    caution: 'border-[var(--color-text-muted)]',
    nogo: 'border-[var(--color-danger)]',
  }

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
      {/* Map with wind particles */}
      <div className="h-[55vh] md:h-[60vh]">
        <Suspense fallback={<div className="w-full h-full bg-[var(--color-bg-card)]" />}>
          <ForecastMap />
        </Suspense>
      </div>

      {/* Timeline scrubber */}
      <div className="bg-[var(--color-bg)] border-b border-[var(--color-border)]">
        <TimelineScrubber />
      </div>

      {/* Content below the fold */}
      <div className="px-4 py-5 max-w-screen-lg mx-auto space-y-4">
        {/* Decision Banner */}
        <div className={`border rounded-xl p-4 ${decisionColors[decision]}`}>
          <div className="flex items-center justify-between">
            <div>
              <p className="text-[10px] uppercase tracking-widest text-[var(--color-text-muted)] mb-1">
                {activity === 'sail' ? t('activity.sail') : t('activity.surf')}
              </p>
              <p className="text-lg font-semibold text-[var(--color-text-primary)]">
                {t(`decision.${decision}`)}
              </p>
            </div>
            <div className="text-right text-xs text-[var(--color-text-secondary)] space-y-1">
              {record && (
                <>
                  <p>{record.wind_kt?.toFixed(0) ?? '--'} kt {record.wind_dir ? `${record.wind_dir}°` : ''}</p>
                  {record.gust_kt && <p className="text-[var(--color-text-muted)]">G{record.gust_kt.toFixed(0)}</p>}
                </>
              )}
              {waveRecord && (
                <p>{waveRecord.wave_height?.toFixed(1) ?? '--'} m @ {waveRecord.wave_period?.toFixed(0) ?? '--'}s</p>
              )}
            </div>
          </div>
        </div>

        {/* Quick stats grid */}
        {record && (
          <div className="grid grid-cols-3 gap-3">
            <StatCard label={t('common.wind')} value={`${record.wind_kt?.toFixed(0) ?? '--'}`} unit="kt" />
            <StatCard label={t('common.temp')} value={`${record.temp_c?.toFixed(0) ?? '--'}`} unit="°C" />
            <StatCard label={t('common.pressure')} value={`${record.mslp_hpa?.toFixed(0) ?? '--'}`} unit="hPa" />
          </div>
        )}

        {/* Wave conditions */}
        {waveRecord && (
          <div className="grid grid-cols-3 gap-3">
            <StatCard label="Swell" value={`${waveRecord.swell_wave_height?.toFixed(1) ?? '--'}`} unit="m" />
            <StatCard label="Period" value={`${waveRecord.swell_wave_period?.toFixed(0) ?? '--'}`} unit="s" />
            <StatCard label="Wind Sea" value={`${waveRecord.wind_wave_height?.toFixed(1) ?? '--'}`} unit="m" />
          </div>
        )}

        {/* AI Summary */}
        {data.summary && (() => {
          const lang = i18n.language.startsWith('zh') ? 'zh' : 'en'
          return (
            <div className="border border-[var(--color-border)] rounded-xl p-4">
              <p className="text-[10px] uppercase tracking-widest text-[var(--color-text-muted)] mb-3">
                {t('ai.title')}
              </p>
              <div className="space-y-3 text-sm text-[var(--color-text-secondary)] leading-relaxed">
                <p>{data.summary.wind[lang]}</p>
                <p>{data.summary.waves[lang]}</p>
                <p>{data.summary.outlook[lang]}</p>
              </div>
            </div>
          )
        })()}

        {/* CWA Live Observations */}
        {data.cwa_obs?.station && (
          <div className="border border-[var(--color-border)] rounded-xl p-4">
            <p className="text-[10px] uppercase tracking-widest text-[var(--color-text-muted)] mb-3">
              {t('live.title')}
            </p>
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div>
                <span className="text-[var(--color-text-muted)]">{t('common.wind')}</span>
                <span className="ml-2 text-[var(--color-text-primary)]">
                  {data.cwa_obs.station.wind_kt?.toFixed(0) ?? '--'} kt
                </span>
              </div>
              <div>
                <span className="text-[var(--color-text-muted)]">{t('common.temp')}</span>
                <span className="ml-2 text-[var(--color-text-primary)]">
                  {data.cwa_obs.station.temp_c?.toFixed(1) ?? '--'}°C
                </span>
              </div>
            </div>
          </div>
        )}

        {/* Charts */}
        <Suspense fallback={null}>
        {data.keelung?.records && (
          <div className="border border-[var(--color-border)] rounded-xl p-4">
            <p className="text-[10px] uppercase tracking-widest text-[var(--color-text-muted)] mb-3">
              {t('common.wind')}
            </p>
            <WindChart
              records={data.keelung.records}
              ecmwfRecords={data.ecmwf?.records}
            />
          </div>
        )}

        {data.wave?.ecmwf_wave?.records && (
          <div className="border border-[var(--color-border)] rounded-xl p-4">
            <p className="text-[10px] uppercase tracking-widest text-[var(--color-text-muted)] mb-3">
              Waves
            </p>
            <WaveChart records={data.wave.ecmwf_wave.records} />
          </div>
        )}

        {data.tide && (
          <div className="border border-[var(--color-border)] rounded-xl p-4">
            <p className="text-[10px] uppercase tracking-widest text-[var(--color-text-muted)] mb-3">
              Tide
            </p>
            <TideChart
              predictions={data.tide.predictions}
              extrema={data.tide.extrema}
            />
          </div>
        )}

        {data.keelung?.records && (
          <div className="border border-[var(--color-border)] rounded-xl p-4">
            <p className="text-[10px] uppercase tracking-widest text-[var(--color-text-muted)] mb-3">
              {t('common.temp')} & {t('common.pressure')}
            </p>
            <TempPressureChart records={data.keelung.records} />
          </div>
        )}
        </Suspense>
      </div>
    </div>
  )
}

function StatCard({ label, value, unit }: { label: string; value: string; unit: string }) {
  return (
    <div className="border border-[var(--color-border)] rounded-lg p-3 text-center">
      <p className="text-[10px] text-[var(--color-text-muted)] uppercase tracking-wider mb-1">{label}</p>
      <p className="text-xl font-semibold text-[var(--color-text-primary)] tabular-nums">
        {value}
        <span className="text-xs text-[var(--color-text-muted)] ml-1">{unit}</span>
      </p>
    </div>
  )
}
