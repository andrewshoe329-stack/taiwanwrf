import {
  ResponsiveContainer, AreaChart, Area, XAxis, YAxis,
  CartesianGrid, Tooltip, ReferenceLine,
} from 'recharts'
import type { TidePrediction, TideExtremum } from '@/lib/types'
import {
  toCST, toCSTLabel, tickInterval, MultiLineTick,
  filterByTimeRange, downsampleTide, type TimeRange,
} from './chart-utils'

interface TideChartProps {
  predictions: TidePrediction[]
  extrema: TideExtremum[]
  timeRange?: TimeRange
}

interface ChartRow {
  time: string
  timeLabel: string
  timeMs: number
  height: number
}

function CustomTooltip(props: any) {
  if (!props.active || !props.payload?.length) return null
  return (
    <div style={{
      background: '#0a0a0a', border: '1px solid #1a1a1a',
      borderRadius: 8, padding: '8px 12px', fontSize: 12,
    }}>
      <p style={{ color: '#666666', marginBottom: 4 }}>{props.payload[0]?.payload?.timeLabel}</p>
      {props.payload.map((p: any, i: number) => (
        <p key={i} style={{ color: p.color, margin: 0 }}>
          Height: {typeof p.value === 'number' ? p.value.toFixed(2) : '--'} m
        </p>
      ))}
    </div>
  )
}

export function TideChart({ predictions, extrema, timeRange }: TideChartProps) {
  if (!predictions?.length) return null

  // Filter to shared time range, then downsample for cleaner chart
  const filtered = filterByTimeRange(predictions, timeRange, 'time_utc')
  const sampled = downsampleTide(filtered, 100)

  const chartData: ChartRow[] = sampled.map(p => ({
    time: toCST(p.time_utc),
    timeLabel: toCSTLabel(p.time_utc),
    timeMs: new Date(p.time_utc).getTime(),
    height: p.height_m,
  }))

  // "Now" marker
  const nowMs = Date.now()
  const hasNow = chartData.length >= 2 &&
    nowMs >= chartData[0].timeMs &&
    nowMs <= chartData[chartData.length - 1].timeMs

  let nowTime: string | undefined
  if (hasNow) {
    let closest = chartData[0]
    let minDiff = Math.abs(nowMs - closest.timeMs)
    for (const row of chartData) {
      const diff = Math.abs(nowMs - row.timeMs)
      if (diff < minDiff) {
        minDiff = diff
        closest = row
      }
    }
    nowTime = closest.time
  }

  // Filter extrema to visible range and find nearest chart points
  const visibleExtrema = extrema.filter(e => {
    const ms = new Date(e.time_utc).getTime()
    return chartData.length >= 2 &&
      ms >= chartData[0].timeMs &&
      ms <= chartData[chartData.length - 1].timeMs
  })

  return (
    <ResponsiveContainer width="100%" height={200}>
      <AreaChart data={chartData} margin={{ top: 16, right: 52, bottom: 16, left: -12 }}>
        <CartesianGrid stroke="var(--color-border)" strokeDasharray="3 3" />
        <XAxis
          dataKey="time"
          tick={<MultiLineTick />}
          stroke="var(--color-border)"
          interval={tickInterval(chartData.length)}
          height={40}
        />
        <YAxis
          tick={{ fill: 'var(--color-text-muted)', fontSize: 10 }}
          stroke="var(--color-border)"
          unit=" m"
          width={44}
          domain={['auto', 'auto']}
        />
        <Tooltip content={CustomTooltip} />
        <Area
          dataKey="height"
          name="Tide"
          fill="var(--color-text-primary)"
          fillOpacity={0.05}
          stroke="var(--color-text-primary)"
          strokeWidth={1.5}
          type="monotone"
          isAnimationActive={false}
        />
        {nowTime && (
          <ReferenceLine
            x={nowTime}
            stroke="var(--color-text-muted)"
            strokeWidth={1}
            strokeDasharray="4 3"
            label={{ value: 'Now', fill: 'var(--color-text-muted)', fontSize: 10, position: 'insideTopRight', offset: 4 }}
          />
        )}
        {/* H/L labels as reference lines — cleaner than dots */}
        {visibleExtrema.map((e, i) => {
          const ms = new Date(e.time_utc).getTime()
          let closest = chartData[0]
          let minDiff = Infinity
          for (const row of chartData) {
            const diff = Math.abs(ms - row.timeMs)
            if (diff < minDiff) { minDiff = diff; closest = row }
          }
          return (
            <ReferenceLine
              key={i}
              x={closest.time}
              stroke="none"
              label={{
                value: `${e.type === 'high' ? 'H' : 'L'} ${e.height_m.toFixed(1)}m`,
                fill: 'var(--color-text-secondary)',
                fontSize: 9,
                position: e.type === 'high' ? 'insideTop' : 'insideBottom',
                offset: 4,
              }}
            />
          )
        })}
      </AreaChart>
    </ResponsiveContainer>
  )
}
