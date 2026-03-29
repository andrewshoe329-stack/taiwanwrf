/**
 * Shared chart utilities: time conversion, tick formatting, tooltip.
 */

/** Convert UTC string to CST Date object */
export function cstDate(utc: string): Date {
  const d = new Date(utc)
  d.setUTCHours(d.getUTCHours() + 8)
  return d
}

/** Unique key for each data point: MM/DD HH:00 */
export function toCST(utc: string): string {
  const d = cstDate(utc)
  const mm = String(d.getUTCMonth() + 1).padStart(2, '0')
  const dd = String(d.getUTCDate()).padStart(2, '0')
  const hh = String(d.getUTCHours()).padStart(2, '0')
  return `${mm}/${dd} ${hh}:00`
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
  if (dataLen <= 12) return 1      // hourly data, ≤12h: every point
  if (dataLen <= 24) return 3      // ≤24h: every 3h
  if (dataLen <= 48) return 6      // ≤2 days: every 6h
  if (dataLen <= 96) return 12     // ≤4 days: every 12h
  return 24                        // >4 days: every 24h
}

/**
 * X-axis tick formatter: shows hour, adds date on midnight (00:00).
 * prevDate tracks state across ticks to show date on day boundaries.
 */
export function createTickFormatter() {
  let prevDate = ''
  return (value: string): string => {
    // value is "MM/DD HH:00"
    const parts = value.split(' ')
    if (parts.length < 2) return value
    const date = parts[0]  // MM/DD
    const hour = parts[1].replace(':00', 'h')  // "08h"

    if (date !== prevDate) {
      prevDate = date
      // Show date + hour on day change
      return `${date}\n${hour}`
    }
    return hour
  }
}

/**
 * Custom multi-line tick component for Recharts XAxis.
 * Renders hour on first line, date on second line when day changes.
 */
export function MultiLineTick(props: any) {
  const { x, y, payload } = props
  if (!payload?.value) return null

  const value: string = payload.value
  const parts = value.split(' ')
  if (parts.length < 2) return null
  const date = parts[0]
  const hour = parts[1].replace(':00', '')

  // Check if this is a midnight boundary (00h) or first tick
  const isMidnight = hour === '00'

  return (
    <g transform={`translate(${x},${y})`}>
      <text
        dy={12}
        textAnchor="middle"
        fill="var(--color-text-muted)"
        fontSize={10}
      >
        {hour}
      </text>
      {isMidnight && (
        <text
          dy={24}
          textAnchor="middle"
          fill="var(--color-text-secondary)"
          fontSize={9}
          fontWeight={500}
        >
          {date}
        </text>
      )}
    </g>
  )
}
