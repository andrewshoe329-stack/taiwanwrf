import { useTranslation } from 'react-i18next'
import { AccuracyTrend } from '@/components/charts/AccuracyTrend'
import type { EnsembleData, AccuracyEntry } from '@/lib/types'

interface EnsembleAccuracyPillsProps {
  ensemble: EnsembleData | null
  accuracy: AccuracyEntry[] | null
}

/** Get the most recent accuracy entry (by init_utc). */
function latestAccuracy(entries: AccuracyEntry[] | null): AccuracyEntry | null {
  if (!entries?.length) return null
  return entries.reduce((a, b) => (a.init_utc > b.init_utc ? a : b))
}

export function EnsembleAccuracyPills({ ensemble, accuracy }: EnsembleAccuracyPillsProps) {
  const { i18n } = useTranslation()
  const lang = i18n.language?.startsWith('zh') ? 'zh' : 'en'
  const latest = latestAccuracy(accuracy)

  return (
    <>
      {ensemble?.spread && (
        <div className="flex flex-wrap gap-1.5">
          {(() => {
            const ws = ensemble.spread.wind_spread_kt ?? 99
            const level = ws < 5 ? 'high' : ws < 10 ? 'moderate' : 'low'
            const stars = level === 'high' ? '★★★' : level === 'moderate' ? '★★☆' : '★☆☆'
            const color = level === 'high' ? 'text-green-400' : level === 'moderate' ? 'text-yellow-400' : 'text-red-400'
            const label = lang === 'zh' ? '模型共識' : 'Model consensus'
            return (
              <span
                className={`fs-compact px-1.5 py-0.5 rounded bg-[var(--color-bg-elevated)] ${color}`}
                aria-label={`${label}: ${level}`}
              >
                {label} {stars}
              </span>
            )
          })()}
          {latest && (
            <span className="fs-compact px-1.5 py-0.5 rounded bg-[var(--color-bg-elevated)] text-[var(--color-text-muted)]">
              ±{latest.wind_mae_kt?.toFixed(1) ?? '?'}kt wind · ±{latest.temp_mae_c?.toFixed(1) ?? '?'}°C temp
              {latest.wave?.hs_mae_m != null && ` · ±${latest.wave.hs_mae_m.toFixed(1)}m wave`}
            </span>
          )}
          {latest?.by_horizon && (() => {
            const horizons = ['0-24h', '24-48h', '48-72h'] as const
            return horizons.map(h => {
              const wind = latest.by_horizon?.[h]?.wind_mae_kt
              if (wind == null) return null
              const temp = latest.by_horizon?.[h]?.temp_mae_c
              return (
                <span key={h} className="fs-compact px-1.5 py-0.5 rounded bg-[var(--color-bg-elevated)] text-[var(--color-text-muted)]">
                  {h}: ±{wind.toFixed(1)}kt{temp != null && ` ±${temp.toFixed(1)}°C`}
                </span>
              )
            })
          })()}
          {ensemble?.spread?.precip_spread_mm != null && ensemble.spread.precip_spread_mm > 1 && (
            <span className="fs-compact px-1.5 py-0.5 rounded bg-[var(--color-bg-elevated)] text-[var(--color-text-muted)]">
              {lang === 'zh' ? '降雨差異' : 'Rain spread'} ±{ensemble.spread.precip_spread_mm.toFixed(1)}mm
            </span>
          )}
        </div>
      )}
      {accuracy && accuracy.length >= 2 && (
        <AccuracyTrend entries={accuracy} compact />
      )}
    </>
  )
}
