import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import type { SpotForecast, Region } from '@/lib/types'

interface SurfHeatmapProps {
  spots: SpotForecast[]
  filter: Region | 'all'
  onSelectSpot?: (id: string) => void
}

const RATING_STYLES: Record<string, { bg: string; color: string }> = {
  firing:    { bg: '#f5f5f5',             color: '#000000' },
  great:     { bg: 'rgba(94,234,212,0.25)', color: '#6ee7b7' },
  good:      { bg: 'rgba(94,234,212,0.2)', color: '#5eead4' },
  marginal:  { bg: 'rgba(251,191,36,0.15)', color: '#fbbf24' },
  poor:      { bg: '#1a1a1a',             color: '#78716c' },
  flat:      { bg: '#111111',             color: '#3f3f46' },
  dangerous: { bg: 'rgba(248,113,113,0.2)', color: '#f87171' },
}

function formatDayHeader(dateStr: string): string {
  const d = new Date(dateStr + 'T00:00:00Z')
  return d.toLocaleDateString('en-US', { weekday: 'short' })
}

function formatDateSub(dateStr: string): string {
  const d = new Date(dateStr + 'T00:00:00Z')
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

export function SurfHeatmap({ spots, filter, onSelectSpot }: SurfHeatmapProps) {
  const { t, i18n } = useTranslation()
  const lang = i18n.language as 'en' | 'zh'

  const filtered = useMemo(() =>
    (filter === 'all'
      ? spots
      : spots.filter(sf => sf.spot.region === filter)
    ).filter(sf => sf.spot.type !== 'harbour' && sf.daily_best != null),
    [spots, filter],
  )

  const { dates, lookup } = useMemo(() => {
    const allDates = new Set<string>()
    for (const sf of filtered) {
      for (const db of sf.daily_best!) {
        allDates.add(db.date)
      }
    }
    const dates = Array.from(allDates).sort().slice(0, 7)

    const lookup: Record<string, Record<string, { rating: string; score: number }>> = {}
    for (const sf of filtered) {
      lookup[sf.spot.id] = {}
      for (const db of sf.daily_best!) {
        lookup[sf.spot.id][db.date] = { rating: db.rating, score: db.score }
      }
    }
    return { dates, lookup }
  }, [filtered])

  if (filtered.length === 0 || dates.length === 0) return null

  return (
    <div className="mb-5 overflow-x-auto relative" style={{ scrollbarWidth: 'none' }}>
      <p className="fs-compact text-[var(--color-text-dim)] text-right mb-1 md:hidden">{t('common.scroll_for_more')}</p>
      <table className="w-full border-collapse fs-body" style={{ minWidth: dates.length * 64 + 100 }}>
        <thead>
          <tr>
            <th className="text-left py-2 pr-3 text-[var(--color-text-muted)] font-normal sticky left-0 bg-[var(--color-bg)] z-10">
              {t('spots.title')}
            </th>
            {dates.map(date => (
              <th key={date} className="text-center py-2 px-1 font-normal" style={{ minWidth: 56 }}>
                <div className="text-[var(--color-text-secondary)] font-medium">{formatDayHeader(date)}</div>
                <div className="text-[var(--color-text-dim)] fs-compact">{formatDateSub(date)}</div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {filtered.map(sf => (
            <tr key={sf.spot.id}>
              <td className="py-1 pr-3 sticky left-0 bg-[var(--color-bg)] z-10">
                {onSelectSpot ? (
                  <button
                    onClick={() => onSelectSpot(sf.spot.id)}
                    className="text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] transition-colors whitespace-nowrap bg-transparent border-none cursor-pointer p-0 text-left fs-body"
                  >
                    {sf.spot.name[lang]}
                  </button>
                ) : (
                  <Link
                    to={`/spots/${sf.spot.id}`}
                    className="text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] transition-colors no-underline whitespace-nowrap"
                  >
                    {sf.spot.name[lang]}
                  </Link>
                )}
              </td>
              {dates.map(date => {
                const entry = lookup[sf.spot.id]?.[date]
                const rating = entry?.rating ?? 'flat'
                const style = RATING_STYLES[rating] ?? RATING_STYLES.flat
                return (
                  <td key={date} className="py-1 px-1 text-center">
                    <Link
                      to={`/spots/${sf.spot.id}`}
                      className="block rounded-md py-1.5 px-1 no-underline transition-opacity hover:opacity-80"
                      style={{ backgroundColor: style.bg, color: style.color }}
                    >
                      {t(`rating.${rating}`)}
                    </Link>
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
