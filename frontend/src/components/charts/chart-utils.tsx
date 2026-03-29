/**
 * Shared chart utilities: time conversion, tick formatting, responsive layout.
 *
 * All charts use a NUMERIC x-axis (timeMs) so that the "Now" reference line
 * aligns to the exact same pixel across charts with different data density
 * (e.g. tide has ~100 points, wind has ~20).
 */

const DAY_NAMES = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']

/** Convert UTC ISO string → CST Date (UTC+8) */
export function cstDate(utc: string): Date {
  const d = new Date(utc)
  d.setUTCHours(d.getUTCHours() + 8)
  return d
}

/** Full CST label for tooltips: "Mon 3/29 08:00 CST" */
export function toCSTLabel(utc: string): string {
  const d = cstDate(utc)
  const day = DAY_NAMES[d.getUTCDay()]
  const mm = d.getUTCMonth() + 1
  const dd = d.getUTCDate()
  const hh = String(d.getUTCHours()).padStart(2, '0')
  return `${day} ${mm}/${dd} ${hh}:00 CST`
}

/* ── Numeric X-axis tick formatting ──────────────────────────────────── */

/**
 * Generate evenly-spaced tick values (ms timestamps) for the numeric axis.
 * Targets ~6-8 ticks, snapped to 6-hour CST boundaries.
 * Accepts either a TimeRange (preferred, for cross-chart consistency) or data array.
 */
export function timeTicks(range: TimeRange | undefined, data?: { timeMs: number }[]): number[] {
  let min: number, max: number
  if (range) {
    min = new Date(range.startUtc).getTime()
    max = new Date(range.endUtc).getTime()
  } else if (data && data.length >= 2) {
    min = data[0].timeMs
    max = data[data.length - 1].timeMs
  } else {
    return data?.map(d => d.timeMs) ?? []
  }
  const span = max - min
  // Pick interval: 6h, 12h, or 24h to get ~6-8 ticks
  const SIX_H = 6 * 3600_000
  const TWELVE_H = 12 * 3600_000
  const TWENTY_FOUR_H = 24 * 3600_000
  let interval = SIX_H
  if (span / SIX_H > 12) interval = TWELVE_H
  if (span / TWELVE_H > 12) interval = TWENTY_FOUR_H

  // Snap first tick to next CST boundary
  // CST = UTC+8, so midnight CST = 16:00 UTC prev day
  const cstOffset = 8 * 3600_000
  const firstAligned = Math.ceil((min + cstOffset) / interval) * interval - cstOffset
  const ticks: number[] = []
  for (let t = firstAligned; t <= max; t += interval) {
    if (t >= min) ticks.push(t)
  }
  return ticks
}

/** Format a ms timestamp for the x-axis tick label */
let prevTickDay = ''

export function MultiLineTick(props: any) {
  const { x, y, payload, index } = props
  if (payload?.value == null) return null

  // Numeric axis: value is ms timestamp
  const ms = typeof payload.value === 'number' ? payload.value : Number(payload.value)
  if (isNaN(ms)) return null

  const d = new Date(ms)
  d.setUTCHours(d.getUTCHours() + 8) // CST

  const dayName = DAY_NAMES[d.getUTCDay()]
  const mm = d.getUTCMonth() + 1
  const dd = d.getUTCDate()
  const hh = String(d.getUTCHours()).padStart(2, '0')

  const dayKey = `${dayName} ${mm}/${dd}`
  const showDate = index === 0 || dayKey !== prevTickDay
  prevTickDay = dayKey

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
          {dayKey}
        </text>
      )}
      <text
        dy={showDate ? 21 : 10}
        textAnchor="middle"
        fill="var(--color-text-muted)"
        fontSize={9}
      >
        {hh}h
      </text>
    </g>
  )
}

/* ── Shared time range filter ────────────────────────────────────────── */

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
 * Downsample tide predictions (keep every Nth point).
 * Preserves first and last for correct range.
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
 * Return current time in ms if it falls within the given time range, else undefined.
 */
export function findNowMs(range: TimeRange | undefined): number | undefined {
  if (!range) return undefined
  const now = Date.now()
  const start = new Date(range.startUtc).getTime()
  const end = new Date(range.endUtc).getTime()
  if (now < start || now > end) return undefined
  return now
}

/**
 * Convert TimeRange to a numeric [startMs, endMs] domain for the x-axis.
 * All charts using the same timeRange will have identical pixel mapping.
 */
export function timeDomain(range: TimeRange | undefined): [number, number] | undefined {
  if (!range) return undefined
  return [new Date(range.startUtc).getTime(), new Date(range.endUtc).getTime()]
}

/* ── Responsive chart layout ─────────────────────────────────────────── */

export const YAXIS_WIDTH = 44

export function chartMargin(mobile: boolean, dualAxis: boolean) {
  if (mobile) {
    return { top: 8, right: 8, bottom: 4, left: -8 }
  }
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

export const NOW_LABEL = {
  value: 'Now',
  fill: 'var(--color-text-muted)',
  fontSize: 10,
  position: 'insideTopRight' as const,
  offset: 4,
}
