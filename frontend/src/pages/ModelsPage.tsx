import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router-dom'
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis,
  CartesianGrid, Tooltip, Legend,
} from 'recharts'
import { useForecastData } from '@/hooks/useForecastData'
import { ALL_LOCATIONS } from '@/lib/constants'
import { getModelRecords } from '@/lib/forecast-utils'
import { LoadingSpinner } from '@/components/layout/LoadingSpinner'
import { DataFreshness } from '@/components/layout/DataFreshness'
import { useIsMobile } from '@/hooks/useIsMobile'
import type { AccuracyEntry, ForecastRecord } from '@/lib/types'

/* ── Helpers ─────────────────────────────────────────────────────────────────── */

const MODEL_META: Record<string, { label: string; color: string; bgVar: string }> = {
  WRF:   { label: 'CWA WRF',   color: '#f5f5f5',  bgVar: '--color-wrf-bg' },
  ECMWF: { label: 'ECMWF IFS', color: '#5eead4',   bgVar: '--color-ecmwf-bg' },
  GFS:   { label: 'NCEP GFS',  color: '#fbbf24',   bgVar: '--color-gfs-bg' },
  JMA:   { label: 'JMA GSM',   color: '#f87171',   bgVar: '--color-gfs-bg' },
}

function fmt(v: number | undefined | null, unit: string, decimals = 1): string {
  if (v == null) return '--'
  return `${v.toFixed(decimals)}${unit}`
}

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

function ModelCard({ modelKey, recordCount, initUtc }: {
  modelKey: string; recordCount: number; initUtc?: string
}) {
  const meta = MODEL_META[modelKey] ?? { label: modelKey, color: '#a0a0a0', bgVar: '--color-bg-elevated' }
  return (
    <div className="border border-[var(--color-border)] rounded-xl p-4 space-y-3">
      <div className="flex items-center gap-2">
        <span className="inline-block w-2 h-2 rounded-full" style={{ background: meta.color }} />
        <h3 className="text-sm font-medium text-[var(--color-text-primary)]">{meta.label}</h3>
      </div>
      <div className="space-y-1 text-xs text-[var(--color-text-secondary)]">
        {initUtc && <p><span className="text-[var(--color-text-muted)]">Init: </span>{initUtc.replace('T', ' ').slice(0, 16)} UTC</p>}
        <p><span className="text-[var(--color-text-muted)]">Records: </span>{recordCount}</p>
      </div>
    </div>
  )
}

function SpreadIndicator({ windSpread, tempSpread }: { windSpread?: number; tempSpread?: number }) {
  const { t } = useTranslation()
  const conf = spreadConfidence(windSpread, tempSpread)
  const barColor = conf.level === 'high' ? 'bg-emerald-400' : conf.level === 'moderate' ? 'bg-amber-400' : 'bg-red-400'

  return (
    <div className="border border-[var(--color-border)] rounded-xl p-4 space-y-3">
      <h3 className="text-xs font-medium tracking-wide uppercase text-[var(--color-text-muted)]">
        {t('models_page.ensemble_confidence', 'Ensemble Confidence')}
      </h3>
      <p className={`text-2xl font-semibold ${conf.opacity}`}>{conf.label}</p>
      <div className="flex gap-1">
        {[0, 1, 2, 3, 4].map(i => (
          <div key={i} className={`h-1 flex-1 rounded-full ${
            i < (conf.level === 'high' ? 5 : conf.level === 'moderate' ? 3 : 1) ? barColor : 'bg-[var(--color-border)]'
          }`} />
        ))}
      </div>
      <div className="flex gap-6 text-xs text-[var(--color-text-secondary)]">
        <div><span className="text-[var(--color-text-muted)]">Wind: </span>{fmt(windSpread, ' kt')}</div>
        <div><span className="text-[var(--color-text-muted)]">Temp: </span>{fmt(tempSpread, '°', 1)}</div>
      </div>
    </div>
  )
}

/** Wind comparison chart — WRF vs ECMWF side by side */
function WindComparisonChart({ wrfRecords, ecmwfRecords }: {
  wrfRecords: ForecastRecord[]; ecmwfRecords: ForecastRecord[]
}) {
  const mobile = useIsMobile()

  const chartData = useMemo(() => {
    const ecmwfMap = new Map(ecmwfRecords.map(r => [r.valid_utc, r]))
    return wrfRecords.slice(0, 20).map(r => {
      const ec = ecmwfMap.get(r.valid_utc)
      const d = new Date(r.valid_utc)
      d.setUTCHours(d.getUTCHours() + 8)
      return {
        time: `${String(d.getUTCMonth() + 1)}/${d.getUTCDate()} ${String(d.getUTCHours()).padStart(2, '0')}h`,
        wrf: r.wind_kt,
        ecmwf: ec?.wind_kt,
      }
    })
  }, [wrfRecords, ecmwfRecords])

  if (chartData.length < 2) return null

  return (
    <ResponsiveContainer width="100%" height={mobile ? 180 : 220}>
      <LineChart data={chartData} margin={{ top: 5, right: 10, bottom: 5, left: 0 }}>
        <CartesianGrid stroke="var(--color-border)" strokeDasharray="3 3" />
        <XAxis dataKey="time" tick={{ fill: 'var(--color-text-muted)', fontSize: 9 }} stroke="var(--color-border)" interval={Math.max(1, Math.floor(chartData.length / 6))} />
        <YAxis tick={{ fill: 'var(--color-text-muted)', fontSize: 10 }} stroke="var(--color-border)" unit=" kt" width={45} />
        <Tooltip contentStyle={{ background: '#0a0a0a', border: '1px solid #1a1a1a', borderRadius: 8, fontSize: 12 }} />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        <Line dataKey="wrf" name="WRF" stroke="#f5f5f5" strokeWidth={1.5} dot={false} type="monotone" isAnimationActive={false} />
        <Line dataKey="ecmwf" name="ECMWF" stroke="#5eead4" strokeWidth={1.5} dot={false} type="monotone" isAnimationActive={false} strokeDasharray="4 3" />
      </LineChart>
    </ResponsiveContainer>
  )
}

/** Accuracy trend chart — MAE over last 30 days */
function AccuracyTrendChart({ entries }: { entries: AccuracyEntry[] }) {
  const mobile = useIsMobile()

  const chartData = useMemo(() => {
    return entries.slice(-30).map(e => {
      const d = new Date(e.verified_utc)
      return {
        date: `${d.getUTCMonth() + 1}/${d.getUTCDate()}`,
        temp: e.temp_mae_c,
        wind: e.wind_mae_kt,
        wave: e.wave?.hs_mae_m,
      }
    })
  }, [entries])

  if (chartData.length < 2) return null

  return (
    <ResponsiveContainer width="100%" height={mobile ? 180 : 220}>
      <LineChart data={chartData} margin={{ top: 5, right: 10, bottom: 5, left: 0 }}>
        <CartesianGrid stroke="var(--color-border)" strokeDasharray="3 3" />
        <XAxis dataKey="date" tick={{ fill: 'var(--color-text-muted)', fontSize: 9 }} stroke="var(--color-border)" interval={Math.max(1, Math.floor(chartData.length / 6))} />
        <YAxis tick={{ fill: 'var(--color-text-muted)', fontSize: 10 }} stroke="var(--color-border)" width={35} />
        <Tooltip contentStyle={{ background: '#0a0a0a', border: '1px solid #1a1a1a', borderRadius: 8, fontSize: 12 }} />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        <Line dataKey="temp" name="Temp °C" stroke="#fbbf24" strokeWidth={1.5} dot={false} type="monotone" isAnimationActive={false} />
        <Line dataKey="wind" name="Wind kt" stroke="#5eead4" strokeWidth={1.5} dot={false} type="monotone" isAnimationActive={false} />
        <Line dataKey="wave" name="Wave m" stroke="#f5f5f5" strokeWidth={1.5} dot={false} type="monotone" isAnimationActive={false} />
      </LineChart>
    </ResponsiveContainer>
  )
}

function AccuracyCard({ entry }: { entry: AccuracyEntry }) {
  const { t } = useTranslation()
  return (
    <div className="border border-[var(--color-border)] rounded-xl p-4 space-y-4">
      <div className="flex items-baseline justify-between">
        <h3 className="text-xs font-medium tracking-wide uppercase text-[var(--color-text-muted)]">
          {t('models_page.accuracy', 'Latest Accuracy')}
        </h3>
        <span className="text-xs text-[var(--color-text-dim)]">
          {entry.verified_utc?.replace('T', ' ').slice(0, 16)} UTC
        </span>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <MetricCell label="Temp MAE" value={fmt(entry.temp_mae_c, '°C')} good={entry.temp_mae_c != null && entry.temp_mae_c < 2} />
        <MetricCell label="Wind MAE" value={fmt(entry.wind_mae_kt, ' kt')} good={entry.wind_mae_kt != null && entry.wind_mae_kt < 5} />
        <MetricCell label="MSLP MAE" value={fmt(entry.mslp_mae_hpa, ' hPa')} good={entry.mslp_mae_hpa != null && entry.mslp_mae_hpa < 2} />
        <MetricCell label="Wind Dir" value={fmt(entry.wdir_mae_deg, '°')} good={entry.wdir_mae_deg != null && entry.wdir_mae_deg < 30} />
      </div>
      {(entry.temp_bias_c != null || entry.wind_bias_kt != null) && (
        <div className="flex gap-6 text-xs text-[var(--color-text-secondary)]">
          {entry.temp_bias_c != null && (
            <div>
              <span className="text-[var(--color-text-muted)]">Temp bias: </span>
              <span className={entry.temp_bias_c > 1 ? 'text-red-400' : entry.temp_bias_c < -1 ? 'text-sky-400' : ''}>
                {entry.temp_bias_c > 0 ? '+' : ''}{entry.temp_bias_c.toFixed(1)}°C
              </span>
            </div>
          )}
          {entry.wind_bias_kt != null && (
            <div>
              <span className="text-[var(--color-text-muted)]">Wind bias: </span>
              <span className={Math.abs(entry.wind_bias_kt) > 3 ? 'text-amber-400' : ''}>
                {entry.wind_bias_kt > 0 ? '+' : ''}{entry.wind_bias_kt.toFixed(1)} kt
              </span>
            </div>
          )}
        </div>
      )}
      {entry.wave && (
        <div>
          <p className="text-xs text-[var(--color-text-muted)] mb-2">Wave verification</p>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            <MetricCell label="Hs MAE" value={fmt(entry.wave.hs_mae_m, ' m')} good={entry.wave.hs_mae_m != null && entry.wave.hs_mae_m < 0.5} />
            <MetricCell label="Hs bias" value={fmt(entry.wave.hs_bias_m, ' m')} />
            <MetricCell label="Tp MAE" value={fmt(entry.wave.tp_mae_s, ' s')} />
          </div>
        </div>
      )}
      {entry.by_horizon && Object.keys(entry.by_horizon).length > 0 && (
        <HorizonBreakdown horizons={entry.by_horizon} />
      )}
    </div>
  )
}

function MetricCell({ label, value, good }: { label: string; value: string; good?: boolean }) {
  return (
    <div className="bg-[var(--color-bg-elevated)] rounded-lg px-3 py-2">
      <p className="text-xs text-[var(--color-text-muted)] mb-0.5">{label}</p>
      <p className={`text-sm font-medium ${good ? 'text-emerald-400' : 'text-[var(--color-text-primary)]'}`}>{value}</p>
    </div>
  )
}

function HorizonBreakdown({ horizons }: { horizons: Record<string, Record<string, number>> }) {
  const { t } = useTranslation()
  const keys = Object.keys(horizons).sort()
  if (keys.length === 0) return null

  return (
    <div>
      <p className="text-xs text-[var(--color-text-muted)] mb-2">{t('models_page.by_horizon', 'By forecast horizon')}</p>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-[var(--color-border)]">
              <th className="text-left py-1.5 pr-3 text-[var(--color-text-muted)] font-normal">Horizon</th>
              <th className="text-right py-1.5 px-2 text-[var(--color-text-muted)] font-normal">Temp</th>
              <th className="text-right py-1.5 px-2 text-[var(--color-text-muted)] font-normal">Wind</th>
              <th className="text-right py-1.5 px-2 text-[var(--color-text-muted)] font-normal">MSLP</th>
            </tr>
          </thead>
          <tbody>
            {keys.map(horizon => {
              const h = horizons[horizon]
              return (
                <tr key={horizon} className="border-b border-[var(--color-border-subtle)]">
                  <td className="py-1.5 pr-3 text-[var(--color-text-secondary)]">{horizon}</td>
                  <td className="text-right py-1.5 px-2 text-[var(--color-text-primary)]">{fmt(h.temp_mae_c, '°')}</td>
                  <td className="text-right py-1.5 px-2 text-[var(--color-text-primary)]">{fmt(h.wind_mae_kt, ' kt')}</td>
                  <td className="text-right py-1.5 px-2 text-[var(--color-text-primary)]">{fmt(h.mslp_mae_hpa, '')}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

/* ── Main page ───────────────────────────────────────────────────────────────── */

export function ModelsPage() {
  const { t, i18n } = useTranslation()
  const lang = (i18n.language.startsWith('zh') ? 'zh' : 'en') as 'en' | 'zh'
  const data = useForecastData()
  const [searchParams, setSearchParams] = useSearchParams()
  const selectedLoc = searchParams.get('loc') || null

  if (data.loading) return <LoadingSpinner />

  const ensemble = data.ensemble
  const accuracy = data.accuracy

  // Filter accuracy by selected location
  const filteredAccuracy = useMemo(() => {
    if (!accuracy?.length) return []
    if (!selectedLoc) return accuracy // "All" = aggregate (existing entries without location_id)
    return accuracy.filter(e => (e.location_id ?? 'keelung') === selectedLoc)
  }, [accuracy, selectedLoc])

  const latestAccuracy = filteredAccuracy.length > 0 ? filteredAccuracy[filteredAccuracy.length - 1] : null

  const modelEntries: Array<{ key: string; recordCount: number; initUtc?: string }> = []
  if (data.keelung) modelEntries.push({ key: 'WRF', recordCount: data.keelung.records?.length ?? 0, initUtc: data.keelung.meta?.init_utc })
  if (data.ecmwf) modelEntries.push({ key: 'ECMWF', recordCount: data.ecmwf.records?.length ?? 0, initUtc: data.ecmwf.meta?.init_utc })
  if (ensemble?.models) {
    for (const key of Object.keys(ensemble.models)) {
      if (key === 'WRF' || key === 'ECMWF') continue
      const model = ensemble.models[key]
      modelEntries.push({ key, recordCount: model.record_count ?? model.records?.length ?? 0, initUtc: model.meta?.init_utc })
    }
  }

  // Wind comparison: WRF vs ECMWF for selected location
  const wrfRecords = useMemo(() => {
    if (!selectedLoc) return data.keelung?.records ?? []
    return getModelRecords(selectedLoc, 'wrf', data)
  }, [selectedLoc, data])

  const ecmwfRecords = useMemo(() => {
    if (!selectedLoc) return data.ecmwf?.records ?? []
    return getModelRecords(selectedLoc, 'ecmwf', data)
  }, [selectedLoc, data])

  const setLocation = (loc: string | null) => {
    setSearchParams(prev => {
      const next = new URLSearchParams(prev)
      if (loc) next.set('loc', loc)
      else next.delete('loc')
      return next
    }, { replace: true })
  }

  return (
    <div className="px-4 py-6 pb-24 max-w-screen-xl mx-auto space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-lg font-semibold text-[var(--color-text-primary)]">{t('models_page.title', 'Models')}</h1>
          <p className="text-xs text-[var(--color-text-muted)] mt-1">{t('models_page.subtitle')}</p>
        </div>
        <DataFreshness />
      </div>

      {/* Location picker */}
      <div className="flex items-center gap-1.5 overflow-x-auto pb-1" style={{ scrollbarWidth: 'none' }}>
        <LocationPill
          label={t('region.all')}
          active={selectedLoc === null}
          onClick={() => setLocation(null)}
        />
        {ALL_LOCATIONS.map(loc => (
          <LocationPill
            key={loc.id}
            label={loc.name[lang]}
            active={selectedLoc === loc.id}
            onClick={() => setLocation(loc.id)}
          />
        ))}
      </div>

      {/* Ensemble spread */}
      {ensemble?.spread && <SpreadIndicator windSpread={ensemble.spread.wind_spread_kt} tempSpread={ensemble.spread.temp_spread_c} />}

      {/* Model cards */}
      <section className="space-y-3">
        <h2 className="text-xs font-medium tracking-wide uppercase text-[var(--color-text-muted)]">{t('models_page.available_models')}</h2>
        {modelEntries.length > 0 ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            {modelEntries.map(m => <ModelCard key={m.key} modelKey={m.key} recordCount={m.recordCount} initUtc={m.initUtc} />)}
          </div>
        ) : (
          <EmptyState message={t('models_page.no_models')} />
        )}
      </section>

      {/* Wind comparison chart */}
      {wrfRecords.length > 0 && ecmwfRecords.length > 0 && (
        <section className="space-y-3">
          <h2 className="text-xs font-medium tracking-wide uppercase text-[var(--color-text-muted)]">
            {t('models_page.wind_comparison')}
          </h2>
          <div className="border border-[var(--color-border)] rounded-xl p-4">
            <WindComparisonChart wrfRecords={wrfRecords} ecmwfRecords={ecmwfRecords} />
          </div>
        </section>
      )}

      {/* Accuracy section */}
      <section className="space-y-3">
        <h2 className="text-xs font-medium tracking-wide uppercase text-[var(--color-text-muted)]">{t('models_page.verification')}</h2>
        {latestAccuracy ? <AccuracyCard entry={latestAccuracy} /> : <EmptyState message={t('models_page.no_accuracy')} />}
      </section>

      {/* Accuracy trend chart */}
      {filteredAccuracy.length >= 2 && (
        <section className="space-y-3">
          <h2 className="text-xs font-medium tracking-wide uppercase text-[var(--color-text-muted)]">
            {t('models_page.accuracy_trend')}
          </h2>
          <div className="border border-[var(--color-border)] rounded-xl p-4">
            <AccuracyTrendChart entries={filteredAccuracy} />
          </div>
        </section>
      )}
    </div>
  )
}

function LocationPill({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`shrink-0 px-3 py-1 rounded-full text-[11px] font-medium transition-all border ${
        active
          ? 'bg-[var(--color-text-primary)] text-[var(--color-bg)] border-[var(--color-text-primary)]'
          : 'bg-transparent text-[var(--color-text-muted)] border-[var(--color-border)] hover:text-[var(--color-text-secondary)]'
      }`}
    >
      {label}
    </button>
  )
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="border border-[var(--color-border)] rounded-xl p-8 text-center">
      <p className="text-[var(--color-text-muted)] text-sm">{message}</p>
    </div>
  )
}
