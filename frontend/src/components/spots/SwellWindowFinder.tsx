import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import type { SpotForecast } from '@/lib/types'

interface SwellWindowFinderProps {
  spots: SpotForecast[]
  onSelectSpot: (id: string) => void
}

const RATING_COLORS: Record<string, string> = {
  firing: '#f97316', great: '#22c55e', good: '#4ade80',
  marginal: '#facc15', poor: '#ef4444',
}
const RATING_ORDER: Record<string, number> = {
  firing: 5, great: 4, good: 3, marginal: 2, poor: 1,
}

const DAY_NAMES = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
const DAY_NAMES_ZH = ['日', '一', '二', '三', '四', '五', '六']

interface RankedWindow {
  spotId: string
  spotName: string
  spotNameZh: string
  date: string
  dayName: string
  dayNameZh: string
  startCst: string
  endCst: string
  rating: string
  ratingOrder: number
  score: number
}

export function SwellWindowFinder({ spots, onSelectSpot }: SwellWindowFinderProps) {
  const { i18n } = useTranslation()
  const lang = i18n.language?.startsWith('zh') ? 'zh' : 'en'

  const topWindows = useMemo(() => {
    const windows: RankedWindow[] = []

    for (const sf of spots) {
      if (!sf.best_times || sf.spot.type === 'harbour') continue
      for (const w of sf.best_times) {
        const order = RATING_ORDER[w.rating] ?? 0
        if (order < 2) continue // skip poor
        const d = new Date(w.date + 'T00:00:00')
        // Find matching daily_best score for this date
        const db = sf.daily_best?.find(b => b.date === w.date)
        windows.push({
          spotId: sf.spot.id,
          spotName: sf.spot.name,
          spotNameZh: sf.spot.name_zh ?? sf.spot.name,
          date: w.date,
          dayName: DAY_NAMES[d.getDay()],
          dayNameZh: DAY_NAMES_ZH[d.getDay()],
          startCst: w.start_cst,
          endCst: w.end_cst,
          rating: w.rating,
          ratingOrder: order,
          score: db?.score ?? order * 3,
        })
      }
    }

    // Sort by rating then score, take top 5
    windows.sort((a, b) => b.ratingOrder - a.ratingOrder || b.score - a.score)
    return windows.slice(0, 5)
  }, [spots])

  if (topWindows.length === 0) return null

  return (
    <section className="md:px-3 py-2">
      <p className="text-[9px] uppercase tracking-widest text-[var(--color-text-dim)] mb-1.5 px-1">
        {lang === 'zh' ? '本週最佳浪況' : 'Best Sessions This Week'}
      </p>
      <div className="space-y-0.5">
        {topWindows.map((w, i) => (
          <button
            key={`${w.spotId}-${w.date}`}
            onClick={() => onSelectSpot(w.spotId)}
            className="w-full flex items-center gap-1.5 px-1.5 py-1 rounded-md text-left hover:bg-[var(--color-bg-elevated)]/60 transition-colors"
          >
            <span className="text-[9px] text-[var(--color-text-dim)] w-3 font-mono">{i + 1}</span>
            <span className="text-[10px] text-[var(--color-text-muted)] w-6 font-medium">
              {lang === 'zh' ? w.dayNameZh : w.dayName}
            </span>
            <span className="text-[10px] text-[var(--color-text-secondary)] flex-1 truncate">
              {lang === 'zh' ? w.spotNameZh : w.spotName}
            </span>
            <span className="text-[9px] text-[var(--color-text-dim)] font-mono tabular-nums">
              {w.startCst}–{w.endCst}
            </span>
            <span
              className="text-[8px] font-medium capitalize px-1 rounded min-w-[40px] text-center"
              style={{
                color: RATING_COLORS[w.rating] ?? '#6b7280',
                backgroundColor: (RATING_COLORS[w.rating] ?? '#6b7280') + '20',
              }}
            >
              {w.rating}
            </span>
          </button>
        ))}
      </div>
    </section>
  )
}
