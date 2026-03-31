import { useTranslation } from 'react-i18next'
import { AccuracyTrend } from '@/components/charts/AccuracyTrend'
import type { EnsembleData, AccuracyEntry } from '@/lib/types'

interface EnsembleAccuracyPillsProps {
  ensemble: EnsembleData | null
  accuracy: AccuracyEntry[] | null
}

export function EnsembleAccuracyPills({ ensemble, accuracy }: EnsembleAccuracyPillsProps) {
  const { t } = useTranslation()
  return (
    <>
      {ensemble?.spread && (
        <div className="flex flex-wrap gap-1.5">
          {(() => {
            const ws = ensemble.spread.wind_spread_kt ?? 99
            const level = ws < 5 ? 'high' : ws < 10 ? 'moderate' : 'low'
            const stars = level === 'high' ? '★★★' : level === 'moderate' ? '★★☆' : '★☆☆'
            const color = level === 'high' ? 'text-green-400' : level === 'moderate' ? 'text-yellow-400' : 'text-red-400'
            return (
              <span className={`text-[10px] px-1.5 py-0.5 rounded bg-[var(--color-bg-elevated)] ${color}`}>
                {t('models_page.ensemble_confidence') ?? 'Confidence'} {stars}
              </span>
            )
          })()}
          {accuracy?.[0] && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--color-bg-elevated)] text-[var(--color-text-muted)]">
              ±{accuracy[0].wind_mae_kt?.toFixed(1) ?? '?'}kt wind · ±{accuracy[0].temp_mae_c?.toFixed(1) ?? '?'}°C temp
              {accuracy[0].wave?.hs_mae_m != null && ` · ±${accuracy[0].wave.hs_mae_m.toFixed(1)}m wave`}
            </span>
          )}
          {accuracy?.[0]?.by_horizon && (() => {
            const horizons = ['0-24h', '24-48h', '48-72h'] as const
            const labels = ['24h', '48h', '72h']
            return horizons.map((h, i) => {
              const wind = accuracy![0].by_horizon?.[h]?.wind_mae_kt
              if (wind == null) return null
              const temp = accuracy![0].by_horizon?.[h]?.temp_mae_c
              return (
                <span key={h} className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--color-bg-elevated)] text-[var(--color-text-muted)]">
                  {labels[i]}: ±{wind.toFixed(1)}kt{temp != null && ` ±${temp.toFixed(1)}°C`}
                </span>
              )
            })
          })()}
          {ensemble?.spread?.precip_spread_mm != null && ensemble.spread.precip_spread_mm > 1 && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--color-bg-elevated)] text-[var(--color-text-muted)]">
              Rain spread ±{ensemble.spread.precip_spread_mm.toFixed(1)}mm
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
