/**
 * Shared chart utilities: time conversion, tick formatting, tooltip.
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
 * Any record with a UTC time field outside the range is dropped.
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
 * Custom tick component for Recharts XAxis.
 * Shows hour on every tick, "Mon 3/29" above on first tick and day changes.
 */
let prevTickDay = ''

export function MultiLineTick(props: any) {
  const { x, y, payload, index } = props
  if (!payload?.value) return null

  const value: string = payload.value
  // Format: "Mon 03/29 08:00"
  const parts = value.split(' ')
  if (parts.length < 3) return null
  const dayName = parts[0]  // "Mon"
  const date = parts[1]     // "03/29"
  const hour = parts[2]     // "08:00"

  // Show day label on first tick or when day changes
  const dayKey = `${dayName} ${date}`
  const showDate = index === 0 || dayKey !== prevTickDay
  prevTickDay = dayKey

  // Compact: "Mon 3/29"
  const shortDate = date.replace(/^0/, '').replace('/0', '/')
  const dayLabel = `${dayName} ${shortDate}`

  // Compact hour: "08h"
  const shortHour = hour.replace(':00', 'h')

  return (
    <g transform={`translate(${x},${y})`}>
      {showDate && (
        <text
          dy={12}
          textAnchor="middle"
          fill="var(--color-text-secondary)"
          fontSize={9}
          fontWeight={500}
        >
          {dayLabel}
        </text>
      )}
      <text
        dy={showDate ? 23 : 12}
        textAnchor="middle"
        fill="var(--color-text-muted)"
        fontSize={9}
      >
        {shortHour}
      </text>
    </g>
  )
}
