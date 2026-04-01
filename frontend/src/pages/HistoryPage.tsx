import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { DailyArchive } from '@/lib/types'

function StatCard({ label, value, unit }: { label: string; value?: string; unit?: string }) {
  return (
    <div className="bg-[var(--color-bg-elevated)] rounded-lg px-3 py-2 text-center">
      <p className="fs-micro text-[var(--color-text-muted)] uppercase tracking-wider">{label}</p>
      <p className="fs-label font-semibold text-[var(--color-text-primary)] tabular-nums">
        {value ?? '--'}
        {unit && <span className="fs-compact text-[var(--color-text-muted)] ml-0.5">{unit}</span>}
      </p>
    </div>
  )
}

export function HistoryPage() {
  const { t } = useTranslation()
  const [entries, setEntries] = useState<DailyArchive[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [days, setDays] = useState(30)

  useEffect(() => {
    setLoading(true)
    setError(null)
    fetch(`/api/history?days=${days}`)
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      })
      .then(data => {
        setEntries(data.entries ?? [])
        setLoading(false)
      })
      .catch(err => {
        setError(err.message)
        setLoading(false)
      })
  }, [days])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <div className="w-4 h-4 border-2 border-[var(--color-text-muted)] border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <p className="text-[var(--color-text-muted)] fs-body">{t('common.error')}: {error}</p>
      </div>
    )
  }

  // Compute averages across all entries
  const avg = (fn: (e: DailyArchive) => number | undefined) => {
    const vals = entries.map(fn).filter((v): v is number => v != null)
    return vals.length ? (vals.reduce((a, b) => a + b, 0) / vals.length) : undefined
  }
  const max = (fn: (e: DailyArchive) => number | undefined) => {
    const vals = entries.map(fn).filter((v): v is number => v != null)
    return vals.length ? Math.max(...vals) : undefined
  }

  const avgTemp = avg(e => e.temp_avg_c)
  const maxWind = max(e => e.wind_max_kt)
  const avgWind = avg(e => e.wind_avg_kt)
  const maxWave = max(e => e.wave_max_m)
  const avgWave = avg(e => e.wave_avg_m)
  const totalPrecip = entries.reduce((sum, e) => sum + (e.precip_total_mm ?? 0), 0)

  return (
    <div className="max-w-4xl mx-auto px-4 py-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="fs-label font-semibold text-[var(--color-text-primary)]">
          {t('history.title')}
        </h1>
        <div className="flex gap-1">
          {[7, 30, 60].map(d => (
            <button
              key={d}
              onClick={() => setDays(d)}
              className={`px-2.5 py-1 fs-compact rounded ${
                days === d
                  ? 'bg-[var(--color-accent)]/20 text-[var(--color-accent)]'
                  : 'text-[var(--color-text-muted)] hover:bg-[var(--color-bg-elevated)]'
              }`}
            >
              {d}d
            </button>
          ))}
        </div>
      </div>

      {entries.length === 0 ? (
        <p className="text-[var(--color-text-muted)] text-center py-8">{t('common.no_data')}</p>
      ) : (
        <>
          {/* Summary cards */}
          <div className="grid grid-cols-3 md:grid-cols-6 gap-2">
            <StatCard label={t('history.avg_temp')} value={avgTemp?.toFixed(1)} unit="°C" />
            <StatCard label={t('history.max_wind')} value={maxWind?.toFixed(0)} unit="kt" />
            <StatCard label={t('history.avg_wind')} value={avgWind?.toFixed(0)} unit="kt" />
            <StatCard label={t('history.max_wave')} value={maxWave?.toFixed(1)} unit="m" />
            <StatCard label={t('history.avg_wave')} value={avgWave?.toFixed(1)} unit="m" />
            <StatCard label={t('history.total_precip')} value={totalPrecip.toFixed(0)} unit="mm" />
          </div>

          {/* Daily table */}
          <div className="overflow-x-auto">
            <table className="w-full fs-compact text-[var(--color-text-secondary)]">
              <thead>
                <tr className="text-[var(--color-text-muted)] uppercase tracking-wider border-b border-[var(--color-border)]">
                  <th className="text-left py-2 pr-2">{t('history.date')}</th>
                  <th className="text-right px-1">{t('history.temp_range')}</th>
                  <th className="text-right px-1">{t('common.wind')}</th>
                  <th className="text-right px-1">{t('common.gust')}</th>
                  <th className="text-right px-1">{t('common.wave_height')}</th>
                  <th className="text-right px-1">{t('common.precip')}</th>
                  <th className="text-right pl-1">{t('common.pressure')}</th>
                </tr>
              </thead>
              <tbody>
                {entries.slice().reverse().map(e => (
                  <tr key={e.date} className="border-b border-[var(--color-border)]/30 hover:bg-[var(--color-bg-elevated)]/50">
                    <td className="py-1.5 pr-2 tabular-nums">{e.date}</td>
                    <td className="text-right px-1 tabular-nums">
                      {e.temp_min_c?.toFixed(0) ?? '--'}–{e.temp_max_c?.toFixed(0) ?? '--'}°C
                    </td>
                    <td className="text-right px-1 tabular-nums">
                      {e.wind_avg_kt?.toFixed(0) ?? '--'}
                      <span className="text-[var(--color-text-dim)]"> / {e.wind_max_kt?.toFixed(0) ?? '--'} kt</span>
                    </td>
                    <td className="text-right px-1 tabular-nums">
                      {e.gust_max_kt?.toFixed(0) ?? '--'} kt
                    </td>
                    <td className="text-right px-1 tabular-nums">
                      {e.wave_avg_m?.toFixed(1) ?? '--'}
                      <span className="text-[var(--color-text-dim)]"> / {e.wave_max_m?.toFixed(1) ?? '--'} m</span>
                    </td>
                    <td className="text-right px-1 tabular-nums">
                      {e.precip_total_mm != null && e.precip_total_mm > 0
                        ? `${e.precip_total_mm.toFixed(1)} mm`
                        : '--'}
                    </td>
                    <td className="text-right pl-1 tabular-nums">
                      {e.pressure_min_hpa?.toFixed(0) ?? '--'}–{e.pressure_max_hpa?.toFixed(0) ?? '--'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}
