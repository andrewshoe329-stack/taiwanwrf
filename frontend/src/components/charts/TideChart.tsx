import {
  ResponsiveContainer, AreaChart, Area, XAxis, YAxis,
  CartesianGrid, Tooltip, ReferenceLine, ReferenceDot,
} from 'recharts'
import type { TidePrediction, TideExtremum } from '@/lib/types'

interface TideChartProps {
  predictions: TidePrediction[]
  extrema: TideExtremum[]
}

function toCST(utc: string): string {
  const d = new Date(utc)
  d.setUTCHours(d.getUTCHours() + 8)
  const mm = String(d.getUTCMonth() + 1).padStart(2, '0')
  const dd = String(d.getUTCDate()).padStart(2, '0')
  const hh = String(d.getUTCHours()).padStart(2, '0')
  return `${mm}/${dd} ${hh}:00`
}

function toCSTLabel(utc: string): string {
  const d = new Date(utc)
  d.setUTCHours(d.getUTCHours() + 8)
  const mm = String(d.getUTCMonth() + 1).padStart(2, '0')
  const dd = String(d.getUTCDate()).padStart(2, '0')
  const hh = String(d.getUTCHours()).padStart(2, '0')
  return `${mm}/${dd} ${hh}:00 CST`
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
      <p style={{ color: '#666666', marginBottom: 4 }}>{props.label}</p>
      {props.payload.map((p: any, i: number) => (
        <p key={i} style={{ color: p.color, margin: 0 }}>
          Height: {typeof p.value === 'number' ? p.value.toFixed(2) : '--'} m
        </p>
      ))}
    </div>
  )
}

export function TideChart({ predictions, extrema }: TideChartProps) {
  if (!predictions?.length) return null

  const chartData: ChartRow[] = predictions.map(p => ({
    time: toCST(p.time_utc),
    timeLabel: toCSTLabel(p.time_utc),
    timeMs: new Date(p.time_utc).getTime(),
    height: p.height_m,
  }))

  // Determine if "now" falls within the data range
  const nowMs = Date.now()
  const hasNow = chartData.length >= 2 &&
    nowMs >= chartData[0].timeMs &&
    nowMs <= chartData[chartData.length - 1].timeMs

  // Find the chart row closest to "now" for the reference line
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

  // Map extrema to chart coordinates
  const extremaDots = extrema.map(e => {
    const ms = new Date(e.time_utc).getTime()
    let closest = chartData[0]
    let minDiff = Infinity
    for (const row of chartData) {
      const diff = Math.abs(ms - row.timeMs)
      if (diff < minDiff) {
        minDiff = diff
        closest = row
      }
    }
    return { ...e, time: closest.time, height: closest.height }
  }).filter(e => {
    // Only show extrema that are within the data range
    const ms = new Date(e.time_utc).getTime()
    return chartData.length >= 2 &&
      ms >= chartData[0].timeMs &&
      ms <= chartData[chartData.length - 1].timeMs
  })

  return (
    <ResponsiveContainer width="100%" height={200}>
      <AreaChart data={chartData} margin={{ top: 16, right: 8, bottom: 0, left: -12 }}>
        <CartesianGrid stroke="var(--color-border)" strokeDasharray="3 3" />
        <XAxis
          dataKey="time"
          tick={{ fill: 'var(--color-text-muted)', fontSize: 10 }}
          stroke="var(--color-border)"
          interval="preserveStartEnd"
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
            label={{ value: 'Now', fill: 'var(--color-text-muted)', fontSize: 10, position: 'top' }}
          />
        )}
        {extremaDots.map((e, i) => (
          <ReferenceDot
            key={i}
            x={e.time}
            y={e.height}
            r={3}
            fill={e.type === 'high' ? 'var(--color-text-primary)' : 'var(--color-text-muted)'}
            stroke="none"
            label={{
              value: `${e.type === 'high' ? 'H' : 'L'} ${e.height.toFixed(1)}m`,
              fill: 'var(--color-text-secondary)',
              fontSize: 9,
              position: e.type === 'high' ? 'top' : 'bottom',
            }}
          />
        ))}
      </AreaChart>
    </ResponsiveContainer>
  )
}
