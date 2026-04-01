import { useTranslation } from 'react-i18next'
import type { SpotRating } from '@/lib/types'

interface ScoreBreakdownTooltipProps {
  rating: SpotRating
  onClose: () => void
}

const FACTORS = [
  { key: 'swell_dir', label: 'Swell Dir', labelZh: '浪向', max: 4, color: '#3b82f6' },
  { key: 'wind_dir', label: 'Wind Dir', labelZh: '風向', max: 3, color: '#22c55e' },
  { key: 'wind_spd', label: 'Wind Spd', labelZh: '風速', max: 2, color: '#a3e635' },
  { key: 'energy', label: 'Wave Energy', labelZh: '浪能', max: 5, color: '#06b6d4' },
  { key: 'rain', label: 'Rain', labelZh: '降雨', max: 0, color: '#f59e0b' },
  { key: 'tide', label: 'Tide', labelZh: '潮汐', max: 1, color: '#8b5cf6' },
] as const

const RATING_COLORS: Record<string, string> = {
  firing: '#f97316', great: '#22c55e', good: '#4ade80',
  marginal: '#facc15', poor: '#ef4444', flat: '#6b7280', dangerous: '#dc2626',
}

export function ScoreBreakdownTooltip({ rating, onClose }: ScoreBreakdownTooltipProps) {
  const { i18n } = useTranslation()
  const lang = i18n.language?.startsWith('zh') ? 'zh' : 'en'
  const bd = rating.score_breakdown
  if (!bd || rating.score == null) return null

  return (
    <div
      className="absolute z-50 w-48 max-w-[85vw] rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-elevated)] shadow-lg p-2"
      onClick={e => e.stopPropagation()}
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-1.5">
        <div className="flex items-center gap-1.5">
          <span
            className="inline-block w-2 h-2 rounded-full"
            style={{ backgroundColor: RATING_COLORS[rating.rating ?? ''] ?? '#6b7280' }}
          />
          <span className="fs-compact font-semibold text-[var(--color-text-primary)] capitalize">
            {rating.rating}
          </span>
        </div>
        <span className="fs-compact font-mono text-[var(--color-text-muted)]">
          {rating.score}/16
        </span>
      </div>

      {/* Factor bars */}
      <div className="space-y-1">
        {FACTORS.map(f => {
          const pts = bd[f.key as keyof typeof bd]
          const absMax = Math.max(f.max, 1)
          const pct = Math.max(0, Math.min(100, (pts / absMax) * 100))
          return (
            <div key={f.key} className="flex items-center gap-1">
              <span className="fs-micro text-[var(--color-text-dim)] w-14 truncate">
                {lang === 'zh' ? f.labelZh : f.label}
              </span>
              <div className="flex-1 h-1.5 bg-[var(--color-bg)]/50 rounded-full overflow-hidden">
                {pts > 0 && (
                  <div
                    className="h-full rounded-full"
                    style={{ width: `${pct}%`, backgroundColor: f.color }}
                  />
                )}
                {pts < 0 && (
                  <div
                    className="h-full rounded-full bg-red-500"
                    style={{ width: `${Math.abs(pts) / absMax * 100}%` }}
                  />
                )}
              </div>
              <span className={`fs-micro font-mono w-4 text-right ${pts < 0 ? 'text-red-400' : 'text-[var(--color-text-dim)]'}`}>
                {pts > 0 ? `+${pts}` : pts}
              </span>
            </div>
          )
        })}
      </div>

      {/* Close on outside click */}
      <button
        onClick={onClose}
        className="absolute -top-1 -right-1 w-4 h-4 rounded-full bg-[var(--color-bg)] border border-[var(--color-border)] fs-micro text-[var(--color-text-muted)] flex items-center justify-center"
      >
        x
      </button>
    </div>
  )
}
