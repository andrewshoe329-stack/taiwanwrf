import { useTranslation } from 'react-i18next'
import type { SpotForecast } from '@/lib/types'

interface BestTimeWindowsProps {
  spotForecast: SpotForecast
}

const RATING_COLORS: Record<string, string> = {
  firing: '#f97316', great: '#22c55e', good: '#4ade80',
  marginal: '#facc15', poor: '#ef4444',
}

const DAY_NAMES = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
const DAY_NAMES_ZH = ['日', '一', '二', '三', '四', '五', '六']

export function BestTimeWindows({ spotForecast }: BestTimeWindowsProps) {
  const { i18n } = useTranslation()
  const lang = i18n.language?.startsWith('zh') ? 'zh' : 'en'
  const bt = spotForecast.best_times
  if (!bt || bt.length === 0) return null

  // Show up to 3 upcoming windows
  const windows = bt.slice(0, 3)

  return (
    <div className="mt-1.5 mb-1">
      <p className="text-[var(--fs-micro)] uppercase tracking-widest text-[var(--color-text-dim)] mb-1">
        {lang === 'zh' ? '最佳時段' : 'Best Windows'}
      </p>
      <div className="space-y-0.5">
        {windows.map((w, i) => {
          const d = new Date(w.date + 'T00:00:00')
          const dayName = lang === 'zh' ? DAY_NAMES_ZH[d.getDay()] : DAY_NAMES[d.getDay()]
          return (
            <div key={i} className="flex items-center gap-1.5 text-[var(--fs-compact)]">
              <span className="text-[var(--color-text-muted)] w-6 font-medium">{dayName}</span>
              <span className="text-[var(--color-text-secondary)] font-mono tabular-nums">
                {w.start_cst}–{w.end_cst}
              </span>
              <span
                className="text-[var(--fs-compact)] font-medium capitalize px-1 rounded"
                style={{
                  color: RATING_COLORS[w.rating] ?? '#6b7280',
                  backgroundColor: (RATING_COLORS[w.rating] ?? '#6b7280') + '20',
                }}
              >
                {w.rating}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
