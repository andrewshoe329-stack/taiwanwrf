/**
 * Shared chart utilities: time conversion, tick formatting, responsive layout.
 *
 * All charts use a NUMERIC x-axis (timeMs) so that the "Now" reference line
 * aligns to the exact same pixel across charts with different data density
 * (e.g. tide has ~100 points, wind has ~20).
 */

const DAY_NAMES = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']

/** Find the data array index closest to a given ms timestamp. Returns -1 if no match. */
export function findClosestIndex(data: { timeMs: number }[], targetMs: number | undefined): number {
  if (!targetMs || !data.length) return -1
  let best = 0
  let bestDiff = Infinity
  for (let i = 0; i < data.length; i++) {
    const diff = Math.abs(data[i].timeMs - targetMs)
    if (diff < bestDiff) { bestDiff = diff; best = i }
  }
  return best
}

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
export function timeTicks(range: TimeRange | undefined, data?: { timeMs: number }[], mobile?: boolean): number[] {
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
  // Pick interval: 6h, 12h, or 24h
  // Mobile targets ~4-5 ticks; desktop targets ~6-8
  const SIX_H = 6 * 3600_000
  const TWELVE_H = 12 * 3600_000
  const TWENTY_FOUR_H = 24 * 3600_000
  const maxTicks = mobile ? 5 : 8
  let interval = SIX_H
  if (span / SIX_H > maxTicks) interval = TWELVE_H
  if (span / TWELVE_H > maxTicks) interval = TWENTY_FOUR_H

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

/** Format a ms timestamp for the x-axis tick label.
 *  Uses the ticks array from props to determine day boundaries
 *  (avoids module-global mutable state that breaks with multiple charts). */
interface TickProps {
  x?: number
  y?: number
  payload?: { value: number | string }
  index?: number
  ticks?: (number | { value: number })[]
}

export function MultiLineTick(props: TickProps) {
  const { x = 0, y = 0, payload, index = 0, ticks } = props
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

  // Determine whether to show day header by comparing to previous tick
  let showDate = index === 0
  if (!showDate && Array.isArray(ticks) && index > 0) {
    const prev = ticks[index - 1]
    const prevMs = typeof prev === 'number' ? prev : prev?.value ?? 0
    const pd = new Date(prevMs)
    pd.setUTCHours(pd.getUTCHours() + 8)
    const prevKey = `${DAY_NAMES[pd.getUTCDay()]} ${pd.getUTCMonth() + 1}/${pd.getUTCDate()}`
    showDate = dayKey !== prevKey
  }

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
    return { top: 4, right: 8, bottom: 2, left: -8 }
  }
  return {
    top: 4,
    right: dualAxis ? 8 : 12,
    bottom: 4,
    left: -8,
  }
}

export function chartHeight(mobile: boolean) {
  return mobile ? 160 : 180
}

/** Compact chart height for secondary charts (precip, temp) in 2-col desktop layout */
export function chartHeightCompact(mobile: boolean) {
  return mobile ? 140 : 120
}

export function xAxisHeight(mobile: boolean) {
  return mobile ? 32 : 40
}

export const NOW_LABEL = {
  value: '',
  fill: 'var(--color-text-muted)',
  fontSize: 10,
  position: 'insideTopRight' as const,
  offset: 4,
}
