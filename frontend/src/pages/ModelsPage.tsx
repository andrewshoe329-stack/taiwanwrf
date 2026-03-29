import { useTranslation } from 'react-i18next'
import { useForecastData } from '@/hooks/useForecastData'
import { LoadingSpinner } from '@/components/layout/LoadingSpinner'
import type { AccuracyEntry } from '@/lib/types'

/* ── Helpers ─────────────────────────────────────────────────────────────────── */

const MODEL_META: Record<string, { label: string; cssVar: string; bgVar: string }> = {
  WRF:   { label: 'CWA WRF',   cssVar: '--color-wrf',        bgVar: '--color-wrf-bg' },
  ECMWF: { label: 'ECMWF IFS', cssVar: '--color-ecmwf',      bgVar: '--color-ecmwf-bg' },
  GFS:   { label: 'NCEP GFS',  cssVar: '--color-gfs',        bgVar: '--color-gfs-bg' },
  JMA:   { label: 'JMA GSM',   cssVar: '--color-gfs',        bgVar: '--color-gfs-bg' },
}

function fmt(v: number | undefined | null, unit: string, decimals = 1): string {
  if (v == null) return '--'
  return `${v.toFixed(decimals)}${unit}`
}

/** Map spread magnitude to a confidence descriptor and opacity class. */
function spreadConfidence(
  windSpread?: number,
  tempSpread?: number,
): { label: string; opacity: string; level: 'high' | 'moderate' | 'low' } {
  const w = windSpread ?? 0
  const t = tempSpread ?? 0
  if (w <= 3 && t <= 1.5) return { label: 'High', opacity: 'opacity-100', level: 'high' }
  if (w <= 6 && t <= 3)   return { label: 'Moderate', opacity: 'opacity-60', level: 'moderate' }
  return { label: 'Low', opacity: 'opacity-35', level: 'low' }
}

/* ── Sub-components ──────────────────────────────────────────────────────────── */

function ModelCard({
  modelKey,
  recordCount,
  initUtc,
}: {
  modelKey: string
  recordCount: number
  initUtc?: string
}) {
  const meta = MODEL_META[modelKey] ?? { label: modelKey, cssVar: '--color-text-secondary', bgVar: '--color-bg-elevated' }

  return (
    <div className="border border-[var(--color-border)] rounded-xl p-4 space-y-3">
      <div className="flex items-center gap-2">
        <span
          className="inline-block w-2 h-2 rounded-full"
          style={{ background: `var(${meta.cssVar})` }}
        />
        <h3 className="text-sm font-medium text-[var(--color-text-primary)]">
          {meta.label}
        </h3>
      </div>

      <div className="space-y-1 text-xs text-[var(--color-text-secondary)]">
        {initUtc && (
          <p>
            <span className="text-[var(--color-text-muted)]">Init: </span>
            {initUtc.replace('T', ' ').slice(0, 16)} UTC
          </p>
        )}
        <p>
          <span className="text-[var(--color-text-muted)]">Records: </span>
          {recordCount}
        </p>
      </div>
    </div>
  )
}

function SpreadIndicator({
  windSpread,
  tempSpread,
}: {
  windSpread?: number
  tempSpread?: number
}) {
  const { t } = useTranslation()
  const conf = spreadConfidence(windSpread, tempSpread)

  const barColor =
    conf.level === 'high'
      ? 'bg-[var(--color-text-primary)]'
      : conf.level === 'moderate'
        ? 'bg-[var(--color-text-secondary)]'
        : 'bg-[var(--color-text-dim)]'

  return (
    <div className="border border-[var(--color-border)] rounded-xl p-4 space-y-3">
      <h3 className="text-xs font-medium tracking-wide uppercase text-[var(--color-text-muted)]">
        {t('models_page.ensemble_confidence', 'Ensemble Confidence')}
      </h3>

      {/* Confidence label */}
      <p className={`text-2xl font-semibold ${conf.opacity}`}>
        {conf.label}
      </p>

      {/* Visual bar */}
      <div className="flex gap-1">
        {[0, 1, 2, 3, 4].map((i) => (
          <div
            key={i}
            className={`h-1 flex-1 rounded-full ${
              i < (conf.level === 'high' ? 5 : conf.level === 'moderate' ? 3 : 1)
                ? barColor
                : 'bg-[var(--color-border)]'
            }`}
          />
        ))}
      </div>

      {/* Spread values */}
      <div className="flex gap-6 text-xs text-[var(--color-text-secondary)]">
        <div>
          <span className="text-[var(--color-text-muted)]">Wind spread: </span>
          {fmt(windSpread, ' kt')}
        </div>
        <div>
          <span className="text-[var(--color-text-muted)]">Temp spread: </span>
          {fmt(tempSpread, ' C', 1)}{tempSpread != null ? '\u00b0' : ''}
        </div>
      </div>
    </div>
  )
}

function AccuracyCard({ entry }: { entry: AccuracyEntry }) {
  const { t } = useTranslation()

  return (
    <div className="border border-[var(--color-border)] rounded-xl p-4 space-y-4">
      <div className="flex items-baseline justify-between">
        <h3 className="text-xs font-medium tracking-wide uppercase text-[var(--color-text-muted)]">
          {t('models_page.accuracy', 'Accuracy Metrics')}
        </h3>
        <span className="text-xs text-[var(--color-text-dim)]">
          {entry.verified_utc?.replace('T', ' ').slice(0, 16)} UTC
        </span>
      </div>

      {/* Primary MAE grid */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <MetricCell label="Temp MAE" value={fmt(entry.temp_mae_c, '\u00b0C')} />
        <MetricCell label="Wind MAE" value={fmt(entry.wind_mae_kt, ' kt')} />
        <MetricCell label="MSLP MAE" value={fmt(entry.mslp_mae_hpa, ' hPa')} />
        <MetricCell label="Wind Dir MAE" value={fmt(entry.wdir_mae_deg, '\u00b0')} />
      </div>

      {/* Bias row */}
      {(entry.temp_bias_c != null || entry.wind_bias_kt != null) && (
        <div className="flex gap-6 text-xs text-[var(--color-text-secondary)]">
          {entry.temp_bias_c != null && (
            <div>
              <span className="text-[var(--color-text-muted)]">Temp bias: </span>
              {entry.temp_bias_c > 0 ? '+' : ''}{entry.temp_bias_c.toFixed(1)}{'\u00b0C'}
            </div>
          )}
          {entry.wind_bias_kt != null && (
            <div>
              <span className="text-[var(--color-text-muted)]">Wind bias: </span>
              {entry.wind_bias_kt > 0 ? '+' : ''}{entry.wind_bias_kt.toFixed(1)} kt
            </div>
          )}
        </div>
      )}

      {/* Wave metrics */}
      {entry.wave && (
        <div>
          <p className="text-xs text-[var(--color-text-muted)] mb-2">Wave verification</p>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            <MetricCell label="Hs MAE" value={fmt(entry.wave.hs_mae_m, ' m')} />
            <MetricCell label="Hs bias" value={fmt(entry.wave.hs_bias_m, ' m')} />
            <MetricCell label="Tp MAE" value={fmt(entry.wave.tp_mae_s, ' s')} />
          </div>
        </div>
      )}

      {/* Horizon breakdown */}
      {entry.by_horizon && Object.keys(entry.by_horizon).length > 0 && (
        <HorizonBreakdown horizons={entry.by_horizon} />
      )}
    </div>
  )
}

function MetricCell({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-[var(--color-bg-elevated)] rounded-lg px-3 py-2">
      <p className="text-xs text-[var(--color-text-muted)] mb-0.5">{label}</p>
      <p className="text-sm font-medium text-[var(--color-text-primary)]">{value}</p>
    </div>
  )
}

function HorizonBreakdown({ horizons }: { horizons: Record<string, Record<string, number>> }) {
  const { t } = useTranslation()
  const keys = Object.keys(horizons).sort()

  if (keys.length === 0) return null

  return (
    <div>
      <p className="text-xs text-[var(--color-text-muted)] mb-2">
        {t('models_page.by_horizon', 'By forecast horizon')}
      </p>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-[var(--color-border)]">
              <th className="text-left py-1.5 pr-3 text-[var(--color-text-muted)] font-normal">
                Horizon
              </th>
              <th className="text-right py-1.5 px-2 text-[var(--color-text-muted)] font-normal">
                Temp
              </th>
              <th className="text-right py-1.5 px-2 text-[var(--color-text-muted)] font-normal">
                Wind
              </th>
              <th className="text-right py-1.5 px-2 text-[var(--color-text-muted)] font-normal">
                MSLP
              </th>
            </tr>
          </thead>
          <tbody>
            {keys.map((horizon) => {
              const h = horizons[horizon]
              return (
                <tr key={horizon} className="border-b border-[var(--color-border-subtle)]">
                  <td className="py-1.5 pr-3 text-[var(--color-text-secondary)]">{horizon}</td>
                  <td className="text-right py-1.5 px-2 text-[var(--color-text-primary)]">
                    {fmt(h.temp_mae_c, '\u00b0')}
                  </td>
                  <td className="text-right py-1.5 px-2 text-[var(--color-text-primary)]">
                    {fmt(h.wind_mae_kt, ' kt')}
                  </td>
                  <td className="text-right py-1.5 px-2 text-[var(--color-text-primary)]">
                    {fmt(h.mslp_mae_hpa, '')}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="border border-[var(--color-border)] rounded-xl p-8 text-center">
      <p className="text-[var(--color-text-muted)] text-sm">{message}</p>
    </div>
  )
}

/* ── Main page ───────────────────────────────────────────────────────────────── */

export function ModelsPage() {
  const { t } = useTranslation()
  const data = useForecastData()

  if (data.loading) {
    return <LoadingSpinner />
  }

  const ensemble = data.ensemble
  const accuracy = data.accuracy
  const latestAccuracy = accuracy && accuracy.length > 0 ? accuracy[accuracy.length - 1] : null

  // Gather all available models from ensemble + primary sources
  const modelEntries: Array<{
    key: string
    recordCount: number
    initUtc?: string
  }> = []

  // WRF (from keelung data)
  if (data.keelung) {
    modelEntries.push({
      key: 'WRF',
      recordCount: data.keelung.records?.length ?? 0,
      initUtc: data.keelung.meta?.init_utc,
    })
  }

  // ECMWF (from ecmwf data)
  if (data.ecmwf) {
    modelEntries.push({
      key: 'ECMWF',
      recordCount: data.ecmwf.records?.length ?? 0,
      initUtc: data.ecmwf.meta?.init_utc,
    })
  }

  // Ensemble models
  if (ensemble?.models) {
    for (const key of Object.keys(ensemble.models)) {
      // Skip if already added from primary sources
      if (key === 'WRF' || key === 'ECMWF') continue
      const model = ensemble.models[key]
      modelEntries.push({
        key,
        recordCount: model.record_count ?? model.records?.length ?? 0,
        initUtc: model.meta?.init_utc,
      })
    }
  }

  return (
    <div className="px-4 py-6 max-w-screen-xl mx-auto space-y-8">
      {/* Page header */}
      <div>
        <h1 className="text-lg font-semibold text-[var(--color-text-primary)]">
          {t('models_page.title', 'Models')}
        </h1>
        <p className="text-xs text-[var(--color-text-muted)] mt-1">
          {t('models_page.subtitle', 'Multi-model comparison and verification')}
        </p>
      </div>

      {/* Ensemble spread indicator */}
      {ensemble?.spread && (
        <SpreadIndicator
          windSpread={ensemble.spread.wind_spread_kt}
          tempSpread={ensemble.spread.temp_spread_c}
        />
      )}

      {/* Model cards */}
      <section className="space-y-3">
        <h2 className="text-xs font-medium tracking-wide uppercase text-[var(--color-text-muted)]">
          {t('models_page.available_models', 'Available Models')}
        </h2>

        {modelEntries.length > 0 ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {modelEntries.map((m) => (
              <ModelCard
                key={m.key}
                modelKey={m.key}
                recordCount={m.recordCount}
                initUtc={m.initUtc}
              />
            ))}
          </div>
        ) : (
          <EmptyState message={t('models_page.no_models', 'No model data available')} />
        )}
      </section>

      {/* Accuracy section */}
      <section className="space-y-3">
        <h2 className="text-xs font-medium tracking-wide uppercase text-[var(--color-text-muted)]">
          {t('models_page.verification', 'Verification')}
        </h2>

        {latestAccuracy ? (
          <AccuracyCard entry={latestAccuracy} />
        ) : (
          <EmptyState message={t('models_page.no_accuracy', 'No accuracy data available')} />
        )}
      </section>
    </div>
  )
}
