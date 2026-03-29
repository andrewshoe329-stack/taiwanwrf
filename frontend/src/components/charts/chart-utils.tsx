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
  if (dataLen <= 12) return 1
  if (dataLen <= 24) return 3
  if (dataLen <= 48) return 6
  if (dataLen <= 96) return 12
  return 24
}

/**
 * Custom tick component for Recharts XAxis.
 * Shows hour on every tick, compact date above on first tick and day changes.
 */
let prevTickDate = ''

export function MultiLineTick(props: any) {
  const { x, y, payload, index } = props
  if (!payload?.value) return null

  const value: string = payload.value
  const parts = value.split(' ')
  if (parts.length < 2) return null
  const date = parts[0]   // "03/29"
  const hour = parts[1]   // "08:00"

  // Show date on first tick or when day changes
  const showDate = index === 0 || date !== prevTickDate
  prevTickDate = date

  // Compact date: "3/29" instead of "03/29"
  const shortDate = date.replace(/^0/, '').replace('/0', '/')

  // Compact hour: "08" instead of "08:00"
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
          {shortDate}
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
