import { useRef, useCallback, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useTimeline } from '@/hooks/useTimeline'
import { DataFreshness } from '@/components/layout/DataFreshness'
import type { ForecastRecord } from '@/lib/types'

function formatTime(utc: string): string {
  const d = new Date(utc)
  const h = d.getUTCHours() + 8 // CST = UTC+8
  return `${((h + 24) % 24).toString().padStart(2, '0')}:00`
}

const DAY_NAMES = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']

function formatDate(utc: string): string {
  const d = new Date(utc)
  d.setUTCHours(d.getUTCHours() + 8)
  return `${DAY_NAMES[d.getUTCDay()]} ${d.getUTCMonth() + 1}/${d.getUTCDate()}`
}

interface TimelineScrubberProps {
  /** The records driving the timeline. Determines total length and time labels. */
  records?: ForecastRecord[]
}

export function TimelineScrubber({ records: externalRecords }: TimelineScrubberProps) {
  const { t } = useTranslation()
  const { index, total, setIndex, playing, toggle, setTotal } = useTimeline()
  const trackRef = useRef<HTMLDivElement>(null)

  const records = externalRecords ?? []

  // Sync total timesteps when records change
  useEffect(() => {
    if (records.length > 0 && total !== records.length) {
      setTotal(records.length)
    }
  }, [records.length, total, setTotal])

  const handlePointerDown = useCallback((e: React.PointerEvent) => {
    e.preventDefault()
    const track = trackRef.current
    if (!track || total === 0) return

    const update = (clientX: number) => {
      const rect = track.getBoundingClientRect()
      const frac = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width))
      setIndex(Math.round(frac * (total - 1)))
    }

    update(e.clientX)

    const onMove = (ev: PointerEvent) => update(ev.clientX)
    const onUp = () => {
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('pointerup', onUp)
    }

    window.addEventListener('pointermove', onMove)
    window.addEventListener('pointerup', onUp)
  }, [total, setIndex])

  const currentRecord = records[index]
  const progress = total > 1 ? index / (total - 1) : 0

  // Day boundary ticks (show only day-change positions, not every record)
  const dayTicks: number[] = []
  let lastDate = ''
  for (let i = 0; i < records.length; i++) {
    const r = records[i]
    if (!r.valid_utc) continue
    const d = formatDate(r.valid_utc)
    if (d !== lastDate) {
      lastDate = d
      if (i > 0) dayTicks.push((i / Math.max(records.length - 1, 1)) * 100)
    }
  }

  return (
    <div className="w-full py-1.5 select-none">
      {/* Time display + play button + freshness */}
      <div className="flex items-center gap-2 mb-1">
        <button
          onClick={toggle}
          className="w-7 h-7 flex items-center justify-center rounded-full border border-[var(--color-border)] bg-[var(--color-bg-elevated)] text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] transition-colors shrink-0"
          aria-label={playing ? 'Pause' : 'Play'}
        >
          {playing ? (
            <svg width="10" height="12" viewBox="0 0 10 12" fill="currentColor">
              <rect x="0" y="0" width="3" height="12" rx="1" />
              <rect x="7" y="0" width="3" height="12" rx="1" />
            </svg>
          ) : (
            <svg width="10" height="12" viewBox="0 0 10 12" fill="currentColor">
              <path d="M0 0 L10 6 L0 12Z" />
            </svg>
          )}
        </button>

        <div className="flex-1 min-w-0 text-center">
          {currentRecord?.valid_utc ? (
            <span className="fs-body font-medium text-[var(--color-text-primary)]">
              {formatDate(currentRecord.valid_utc)}{' '}
              <span className="text-[var(--color-text-secondary)]">
                {formatTime(currentRecord.valid_utc)} {t('timeline.cst')}
              </span>
            </span>
          ) : (
            <span className="fs-body text-[var(--color-text-muted)]">{t('common.no_data')}</span>
          )}
        </div>

        <span className="shrink-0">
          <DataFreshness />
        </span>
      </div>

      {/* Slider track */}
      <div
        ref={trackRef}
        role="slider"
        aria-label={t('timeline.scrubber', 'Forecast time scrubber')}
        aria-valuemin={0}
        aria-valuemax={total > 0 ? total - 1 : 0}
        aria-valuenow={index}
        aria-valuetext={currentRecord?.valid_utc ? `${formatDate(currentRecord.valid_utc)} ${formatTime(currentRecord.valid_utc)} CST` : undefined}
        tabIndex={0}
        className="relative h-6 flex items-center cursor-pointer touch-none"
        onPointerDown={handlePointerDown}
      >
        {/* Background rail */}
        <div className="absolute left-0 right-0 h-[3px] rounded-full bg-[var(--color-border)]" />

        {/* Filled portion */}
        <div
          className="absolute left-0 h-[3px] rounded-full bg-[var(--color-text-muted)] transition-[width] duration-75"
          style={{ width: `${progress * 100}%` }}
        />

        {/* Day boundary ticks only */}
        {dayTicks.map((pos, i) => (
          <div
            key={i}
            className="absolute w-[1px] h-3 bg-[var(--color-text-dim)]"
            style={{ left: `${pos}%`, top: '50%', transform: 'translateY(-50%)' }}
          />
        ))}

        {/* Thumb */}
        <div
          className="absolute w-4 h-4 rounded-full bg-[var(--color-text-primary)] border-2 border-[var(--color-bg)] shadow-sm transition-[left] duration-75"
          style={{ left: `${progress * 100}%`, transform: 'translateX(-50%)' }}
        />
      </div>
    </div>
  )
}
