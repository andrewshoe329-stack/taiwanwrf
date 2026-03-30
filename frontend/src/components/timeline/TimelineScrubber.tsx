import { useRef, useCallback, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useTimeline } from '@/hooks/useTimeline'
import { useForecastData } from '@/hooks/useForecastData'

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

export function TimelineScrubber() {
  const { t } = useTranslation()
  const { index, total, setIndex, playing, toggle, setTotal } = useTimeline()
  const { keelung } = useForecastData()
  const trackRef = useRef<HTMLDivElement>(null)

  const records = keelung?.records ?? []

  // Sync total timesteps
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

  // Compute day labels for the timeline
  const dayLabels: { label: string; position: number }[] = []
  let lastDate = ''
  for (let i = 0; i < records.length; i++) {
    const r = records[i]
    if (!r.valid_utc) continue
    const d = formatDate(r.valid_utc)
    if (d !== lastDate) {
      lastDate = d
      dayLabels.push({ label: d, position: (i / Math.max(records.length - 1, 1)) * 100 })
    }
  }

  return (
    <div className="w-full px-4 py-2 select-none">
      {/* Time display + play button */}
      <div className="flex items-center gap-3 mb-2">
        <button
          onClick={toggle}
          className="w-7 h-7 flex items-center justify-center rounded-full border border-[var(--color-border)] bg-[var(--color-bg-elevated)] text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] transition-colors"
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

        <div className="flex-1 text-center">
          {currentRecord?.valid_utc ? (
            <span className="text-xs font-medium text-[var(--color-text-primary)]">
              {formatDate(currentRecord.valid_utc)}{' '}
              <span className="text-[var(--color-text-secondary)]">
                {formatTime(currentRecord.valid_utc)} {t('timeline.cst')}
              </span>
            </span>
          ) : (
            <span className="text-xs text-[var(--color-text-muted)]">{t('common.no_data')}</span>
          )}
        </div>

        <span className="text-[10px] text-[var(--color-text-muted)] tabular-nums w-12 text-right">
          {index + 1}/{total}
        </span>
      </div>

      {/* Track */}
      <div className="relative">
        {/* Day labels */}
        <div className="relative h-3 mb-1">
          {dayLabels.map((dl, i) => (
            <span
              key={i}
              className="absolute text-[9px] text-[var(--color-text-muted)] -translate-x-1/2"
              style={{ left: `${dl.position}%` }}
            >
              {dl.label}
            </span>
          ))}
        </div>

        {/* Slider track */}
        <div
          ref={trackRef}
          className="relative h-8 flex items-center cursor-pointer touch-none"
          onPointerDown={handlePointerDown}
        >
          {/* Background rail */}
          <div className="absolute left-0 right-0 h-[3px] rounded-full bg-[var(--color-border)]" />

          {/* Filled portion */}
          <div
            className="absolute left-0 h-[3px] rounded-full bg-[var(--color-text-muted)] transition-[width] duration-75"
            style={{ width: `${progress * 100}%` }}
          />

          {/* Tick marks */}
          {records.map((_, i) => (
            <div
              key={i}
              className="absolute w-[1px] h-2 bg-[var(--color-border)]"
              style={{ left: `${(i / Math.max(records.length - 1, 1)) * 100}%`, top: '50%', transform: 'translateY(-50%)' }}
            />
          ))}

          {/* Thumb */}
          <div
            className="absolute w-5 h-5 rounded-full bg-[var(--color-text-primary)] border-2 border-[var(--color-bg)] shadow-sm transition-[left] duration-75"
            style={{ left: `${progress * 100}%`, transform: 'translateX(-50%)' }}
          />
        </div>
      </div>
    </div>
  )
}
