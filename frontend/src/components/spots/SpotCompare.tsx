import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { degToCompass } from '@/lib/forecast-utils'
import type { SpotForecast, SpotRating } from '@/lib/types'

interface SpotCompareProps {
  spots: SpotForecast[]
  targetUtc?: string
  onSelectSpot?: (id: string) => void
}

const RATING_COLORS: Record<string, string> = {
  firing: '#f5f5f5',
  great: '#6ee7b7',
  good: '#5eead4',
  marginal: '#fbbf24',
  poor: '#78716c',
  flat: '#3f3f46',
  dangerous: '#f87171',
}

/**
 * Compact comparison table showing current conditions across all spots.
 * Displayed in the left panel when no specific spot is selected.
 */
export function SpotCompare({ spots, targetUtc, onSelectSpot }: SpotCompareProps) {
  const { i18n } = useTranslation()
  const lang = (i18n.language.startsWith('zh') ? 'zh' : 'en') as 'en' | 'zh'

  const rows = useMemo(() => {
    if (!spots.length) return []
    const targetMs = targetUtc ? new Date(targetUtc).getTime() : Date.now()

    return spots
      .filter(sf => sf.spot.type !== 'harbour')
      .map(sf => {
        // Find closest rating to target time
        let best: SpotRating | null = null
        let bestDiff = Infinity
        for (const r of sf.ratings) {
          const diff = Math.abs(new Date(r.valid_utc).getTime() - targetMs)
          if (diff < bestDiff) { bestDiff = diff; best = r }
        }
        return { spot: sf.spot, rating: best }
      })
      .filter(r => r.rating)
  }, [spots, targetUtc])

  if (rows.length === 0) return null

  return (
    <div className="space-y-0.5">
      <p className="text-[9px] uppercase tracking-widest text-[var(--color-text-dim)] mb-1">
        Spot Comparison
      </p>
      <table className="w-full text-[10px]">
        <thead>
          <tr className="text-[var(--color-text-dim)]">
            <th className="text-left font-normal pb-1 pr-1">Spot</th>
            <th className="text-center font-normal pb-1 px-0.5">Rating</th>
            <th className="text-center font-normal pb-1 px-0.5">Wind</th>
            <th className="text-center font-normal pb-1 px-0.5">Swell</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(({ spot, rating }) => {
            const r = rating!
            const ratingLabel = r.rating ?? 'flat'
            const ratingColor = RATING_COLORS[ratingLabel] ?? '#3f3f46'

            return (
              <tr
                key={spot.id}
                className="hover:bg-[var(--color-bg-elevated)]/50 cursor-pointer transition-colors"
                onClick={() => onSelectSpot?.(spot.id)}
              >
                <td className="py-1 pr-1 text-[var(--color-text-secondary)] whitespace-nowrap">
                  {spot.name[lang]}
                </td>
                <td className="py-1 px-0.5 text-center">
                  <span
                    className="inline-block w-2 h-2 rounded-full"
                    style={{ backgroundColor: ratingColor }}
                    title={ratingLabel}
                  />
                </td>
                <td className="py-1 px-0.5 text-center text-[var(--color-text-muted)]">
                  {r.wind_kt != null ? `${r.wind_kt.toFixed(0)}` : '--'}
                  {r.wind_dir != null && (
                    <span className="text-[var(--color-text-dim)]"> {degToCompass(r.wind_dir)}</span>
                  )}
                </td>
                <td className="py-1 px-0.5 text-center text-[var(--color-text-muted)]">
                  {r.swell_height != null ? `${r.swell_height.toFixed(1)}m` : '--'}
                  {r.swell_dir != null && (
                    <span className="text-[var(--color-text-dim)]"> {degToCompass(r.swell_dir)}</span>
                  )}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
