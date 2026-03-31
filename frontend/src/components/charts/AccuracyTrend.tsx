import { useState, useMemo, lazy, Suspense } from 'react'
import { useTranslation } from 'react-i18next'
import type { AccuracyEntry } from '@/lib/types'

const LineChart = lazy(() => import('recharts').then(m => ({ default: m.LineChart })))
const Line = lazy(() => import('recharts').then(m => ({ default: m.Line })))
const XAxis = lazy(() => import('recharts').then(m => ({ default: m.XAxis })))
const YAxis = lazy(() => import('recharts').then(m => ({ default: m.YAxis })))
const Tooltip = lazy(() => import('recharts').then(m => ({ default: m.Tooltip })))
const ResponsiveContainer = lazy(() => import('recharts').then(m => ({ default: m.ResponsiveContainer })))

interface AccuracyTrendProps {
  entries: AccuracyEntry[] | null
  compact?: boolean // inline sparkline mode
}

export function AccuracyTrend({ entries, compact = false }: AccuracyTrendProps) {
  const { i18n } = useTranslation()
  const lang = i18n.language?.startsWith('zh') ? 'zh' : 'en'
  const [expanded, setExpanded] = useState(false)

  const chartData = useMemo(() => {
    if (!entries || entries.length === 0) return []
    // Sort chronologically, take last 30
    const sorted = [...entries]
      .sort((a, b) => a.init_utc.localeCompare(b.init_utc))
      .slice(-30)
    return sorted.map(e => ({
      date: new Date(e.init_utc).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }),
      wind: e.wind_mae_kt != null ? Math.round(e.wind_mae_kt * 10) / 10 : null,
      temp: e.temp_mae_c != null ? Math.round(e.temp_mae_c * 10) / 10 : null,
      wave: e.wave?.hs_mae_m != null ? Math.round(e.wave.hs_mae_m * 100) / 100 : null,
    }))
  }, [entries])

  if (!entries || entries.length < 2) return null

  // Compute summary stats
  const latest = entries[0]
  const windBias = latest?.wind_bias_kt
  const tempBias = latest?.temp_bias_c

  if (compact) {
    // Inline expandable sparkline mode
    return (
      <div className="mt-1">
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex items-center gap-1 text-[8px] text-[var(--color-text-dim)] hover:text-[var(--color-text-muted)] transition-colors"
        >
          <span>{expanded ? '▼' : '▶'}</span>
          <span>{lang === 'zh' ? '準確度趨勢' : 'Accuracy trend'}</span>
          {windBias != null && (
            <span className="text-[var(--color-text-muted)]">
              ({lang === 'zh' ? '風偏差' : 'wind bias'} {windBias > 0 ? '+' : ''}{windBias.toFixed(1)}kt)
            </span>
          )}
        </button>
        {expanded && chartData.length > 0 && (
          <div className="mt-1" style={{ height: 80 }}>
            <Suspense fallback={<div className="h-full bg-[var(--color-bg)]/30 rounded animate-pulse" />}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData} margin={{ top: 4, right: 4, bottom: 0, left: -20 }}>
                  <XAxis dataKey="date" tick={false} axisLine={false} />
                  <YAxis tick={{ fontSize: 8, fill: '#6b7280' }} axisLine={false} tickLine={false} />
                  <Tooltip
                    contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #334155', borderRadius: 6, fontSize: 10 }}
                    labelStyle={{ color: '#94a3b8', fontSize: 9 }}
                  />
                  <Line type="monotone" dataKey="wind" stroke="#2dd4bf" strokeWidth={1.5} dot={false} name="Wind MAE (kt)" />
                  <Line type="monotone" dataKey="temp" stroke="#fb923c" strokeWidth={1.5} dot={false} name="Temp MAE (°C)" />
                  {chartData.some(d => d.wave != null) && (
                    <Line type="monotone" dataKey="wave" stroke="#60a5fa" strokeWidth={1.5} dot={false} name="Wave MAE (m)" />
                  )}
                </LineChart>
              </ResponsiveContainer>
            </Suspense>
          </div>
        )}
      </div>
    )
  }

  // Full chart mode (for charts panel)
  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <p className="text-[9px] uppercase tracking-wider text-[var(--color-text-dim)]">
          {lang === 'zh' ? '模型準確度 (30天)' : 'Model Accuracy (30 days)'}
        </p>
        <div className="flex gap-2 text-[8px]">
          {tempBias != null && (
            <span className="text-orange-400">
              {lang === 'zh' ? '溫度偏差' : 'Temp bias'} {tempBias > 0 ? '+' : ''}{tempBias.toFixed(1)}°C
            </span>
          )}
          {windBias != null && (
            <span className="text-teal-400">
              {lang === 'zh' ? '風偏差' : 'Wind bias'} {windBias > 0 ? '+' : ''}{windBias.toFixed(1)}kt
            </span>
          )}
        </div>
      </div>
      {chartData.length > 0 && (
        <div style={{ height: 140 }}>
          <Suspense fallback={<div className="h-full bg-[var(--color-bg)]/30 rounded animate-pulse" />}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData} margin={{ top: 4, right: 8, bottom: 16, left: -10 }}>
                <XAxis
                  dataKey="date"
                  tick={{ fontSize: 8, fill: '#6b7280' }}
                  axisLine={false}
                  tickLine={false}
                  interval={Math.max(0, Math.floor(chartData.length / 6) - 1)}
                />
                <YAxis tick={{ fontSize: 8, fill: '#6b7280' }} axisLine={false} tickLine={false} />
                <Tooltip
                  contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #334155', borderRadius: 6, fontSize: 10 }}
                  labelStyle={{ color: '#94a3b8', fontSize: 9 }}
                />
                <Line type="monotone" dataKey="wind" stroke="#2dd4bf" strokeWidth={1.5} dot={{ r: 1.5 }} name="Wind MAE (kt)" />
                <Line type="monotone" dataKey="temp" stroke="#fb923c" strokeWidth={1.5} dot={{ r: 1.5 }} name="Temp MAE (°C)" />
                {chartData.some(d => d.wave != null) && (
                  <Line type="monotone" dataKey="wave" stroke="#60a5fa" strokeWidth={1.5} dot={{ r: 1.5 }} name="Wave MAE (m)" />
                )}
              </LineChart>
            </ResponsiveContainer>
          </Suspense>
        </div>
      )}
    </div>
  )
}
