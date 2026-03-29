/**
 * Shared chart utilities: time conversion, tick formatting, responsive layout.
 */

/** Convert UTC string to CST Date object */
export function cstDate(utc: string): Date {
  const d = new Date(utc)
  d.setUTCHours(d.getUTCHours() + 8)
  return d
}

const DAY_NAMES = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']

/** Unique key for each data point: DDD MM/DD HH:00 */
export function toCST(utc: string): string {
  const d = cstDate(utc)
  const day = DAY_NAMES[d.getUTCDay()]
  const mm = String(d.getUTCMonth() + 1).padStart(2, '0')
  const dd = String(d.getUTCDate()).padStart(2, '0')
  const hh = String(d.getUTCHours()).padStart(2, '0')
  return `${day} ${mm}/${dd} ${hh}:00`
}

/** Full label for tooltips */
export function toCSTLabel(utc: string): string {
  return `${toCST(utc)} CST`
}

/**
 * Compute tick interval: show a tick every N data points.
 * Aims for ~6-10 visible ticks regardless of data length.
 */
export function tickInterval(dataLen: number): number {
  if (dataLen <= 12) return 1
  if (dataLen <= 24) return 3
  if (dataLen <= 48) return 6
  if (dataLen <= 96) return 12
  return 24
}

/**
 * Shared time range: clips records to a start/end UTC window.
 */
export interface TimeRange {
  startUtc: string
  endUtc: string
}

export function filterByTimeRange<T extends Record<string, any>>(
  records: T[],
  range: TimeRange | undefined,
  timeKey: string = 'valid_utc',
): T[] {
  if (!range) return records
  const start = new Date(range.startUtc).getTime()
  const end = new Date(range.endUtc).getTime()
  return records.filter(r => {
    const t = new Date(r[timeKey]).getTime()
    return t >= start && t <= end
  })
}

/**
 * Downsample tide predictions to ~hourly (keep every Nth point).
 * Preserves first and last point for correct range.
 */
export function downsampleTide<T>(records: T[], targetCount: number = 120): T[] {
  if (records.length <= targetCount) return records
  const step = records.length / targetCount
  const result: T[] = []
  for (let i = 0; i < records.length; i++) {
    if (i === 0 || i === records.length - 1 || Math.floor(i / step) !== Math.floor((i - 1) / step)) {
      result.push(records[i])
    }
  }
  return result
}

/**
 * Find the chart `time` key closest to "now", if now falls within the data range.
 */
export function findNowTime(chartData: { time: string; timeMs: number }[]): string | undefined {
  if (chartData.length < 2) return undefined
  const nowMs = Date.now()
  if (nowMs < chartData[0].timeMs || nowMs > chartData[chartData.length - 1].timeMs) return undefined
  let closest = chartData[0]
  let minDiff = Math.abs(nowMs - closest.timeMs)
  for (const row of chartData) {
    const diff = Math.abs(nowMs - row.timeMs)
    if (diff < minDiff) { minDiff = diff; closest = row }
  }
  return closest.time
}

/* ── Responsive chart layout ─────────────────────────────────────────────
 *
 * All charts use identical margins so the plot areas (and "Now" lines)
 * align vertically when stacked on mobile.
 *
 * Mobile:  no right Y-axis → all charts same width
 * Desktop: dual-axis charts get a right Y-axis; single-axis charts
 *          use matching right margin so widths stay consistent.
 */

export const YAXIS_WIDTH = 44

/** Shared chart margins. On mobile all charts are identical. */
export function chartMargin(mobile: boolean, dualAxis: boolean) {
  if (mobile) {
    // Identical for every chart → "Now" lines align
    return { top: 8, right: 8, bottom: 4, left: -8 }
  }
  // Desktop: single-axis charts pad right to match dual-axis Y-axis width
  return {
    top: 8,
    right: dualAxis ? 8 : YAXIS_WIDTH + 8,
    bottom: 8,
    left: -8,
  }
}

export function chartHeight(mobile: boolean) {
  return mobile ? 280 : 240
}

export function xAxisHeight(mobile: boolean) {
  return mobile ? 32 : 40
}

/** Shared "Now" ReferenceLine label props */
export const NOW_LABEL = {
  value: 'Now',
  fill: 'var(--color-text-muted)',
  fontSize: 10,
  position: 'insideTopRight' as const,
  offset: 4,
}

/**
 * Custom tick component for Recharts XAxis.
 * Shows hour on every tick, "Mon 3/29" above on first tick and day changes.
 */
let prevTickDay = ''

export function MultiLineTick(props: any) {
  const { x, y, payload, index } = props
  if (!payload?.value) return null

  const value: string = payload.value
  const parts = value.split(' ')
  if (parts.length < 3) return null
  const dayName = parts[0]
  const date = parts[1]
  const hour = parts[2]

  const dayKey = `${dayName} ${date}`
  const showDate = index === 0 || dayKey !== prevTickDay
  prevTickDay = dayKey

  const shortDate = date.replace(/^0/, '').replace('/0', '/')
  const dayLabel = `${dayName} ${shortDate}`
  const shortHour = hour.replace(':00', 'h')

  return (
    <g transform={`translate(${x},${y})`}>
      {showDate && (
        <text
          dy={10}
          textAnchor="middle"
          fill="var(--color-text-secondary)"
          fontSize={9}
          fontWeight={500}
        >
          {dayLabel}
        </text>
      )}
      <text
        dy={showDate ? 21 : 10}
        textAnchor="middle"
        fill="var(--color-text-muted)"
        fontSize={9}
      >
        {shortHour}
      </text>
    </g>
  )
}
