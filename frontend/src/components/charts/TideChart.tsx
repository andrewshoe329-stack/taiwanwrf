import { useMemo } from 'react'
import {
  ResponsiveContainer, AreaChart, Area, XAxis, YAxis,
  CartesianGrid, Tooltip, ReferenceLine,
} from 'recharts'
import type { TooltipContentProps } from 'recharts'
import type { TidePrediction, TideExtremum } from '@/lib/types'
import { useIsMobile } from '@/hooks/useIsMobile'
import {
  toCSTLabel, MultiLineTick, timeTicks, timeDomain,
  filterByTimeRange, downsampleTide,
  chartMargin, chartHeight, xAxisHeight, YAXIS_WIDTH, NOW_LABEL,
  type TimeRange,
} from './chart-utils'

interface TideChartProps {
  predictions: TidePrediction[]
  extrema: TideExtremum[]
  timeRange?: TimeRange
  selectedMs?: number
}

interface ChartRow {
  timeMs: number
  timeLabel: string
  height: number
}

function CustomTooltip({ active, payload }: TooltipContentProps) {
  if (!active || !payload?.length) return null
  return (
    <div style={{
      background: '#0a0a0a', border: '1px solid #1a1a1a',
      borderRadius: 8, padding: '8px 12px', fontSize: 12,
    }}>
      <p style={{ color: '#666666', marginBottom: 4 }}>{(payload[0]?.payload as ChartRow)?.timeLabel}</p>
      {payload.map((p, i) => (
        <p key={i} style={{ color: p.color, margin: 0 }}>
          Height: {typeof p.value === 'number' ? p.value.toFixed(2) : '--'} m
        </p>
      ))}
    </div>
  )
}

export function TideChart({ predictions, extrema, timeRange, selectedMs }: TideChartProps) {
  if (!predictions?.length) return null
  const mobile = useIsMobile()

  const filtered = filterByTimeRange(predictions, timeRange, 'time_utc')
  const sampled = downsampleTide(filtered, 100)

  const chartData: ChartRow[] = sampled.map(p => ({
    timeMs: new Date(p.time_utc).getTime(),
    timeLabel: toCSTLabel(p.time_utc),
    height: p.height_m,
  }))

  const nowMs = selectedMs
  const domain = timeDomain(timeRange) ?? ['dataMin', 'dataMax'] as any
  const ticks = timeTicks(timeRange, chartData)

  const visibleExtrema = useMemo(() => {
    const visible = extrema.filter(e => {
      const ms = new Date(e.time_utc).getTime()
      return chartData.length >= 2 &&
        ms >= chartData[0].timeMs &&
        ms <= chartData[chartData.length - 1].timeMs
    })
    // Thin out labels: skip if too close to previous
    // Mobile needs wider gaps to avoid overlap (8h vs 4h)
    const minGapMs = mobile ? 8 * 3600 * 1000 : 4 * 3600 * 1000
    const thinned: typeof visible = []
    for (const e of visible) {
      const ms = new Date(e.time_utc).getTime()
      const prev = thinned.length > 0 ? new Date(thinned[thinned.length - 1].time_utc).getTime() : -Infinity
      if (ms - prev >= minGapMs) thinned.push(e)
    }
    return thinned
  }, [extrema, chartData])

  return (
    <ResponsiveContainer width="100%" height={chartHeight(mobile)}>
      <AreaChart data={chartData} margin={chartMargin(mobile, false)}>
        <CartesianGrid stroke="var(--color-border)" strokeDasharray="3 3" />
        <XAxis
          dataKey="timeMs"
          type="number"
          scale="time"
          domain={domain}
          ticks={ticks}
          tick={<MultiLineTick />}
          stroke="var(--color-border)"
          height={xAxisHeight(mobile)}
        />
        <YAxis
          tick={{ fill: 'var(--color-text-muted)', fontSize: 10 }}
          stroke="var(--color-border)"
          unit=" m"
          width={YAXIS_WIDTH}
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
        {nowMs != null && (
          <ReferenceLine
            x={nowMs}
            stroke="var(--color-text-muted)"
            strokeWidth={1}
            strokeDasharray="4 3"
            label={NOW_LABEL}
          />
        )}
        {visibleExtrema.map((e, i) => (
          <ReferenceLine
            key={i}
            x={new Date(e.time_utc).getTime()}
            stroke="none"
            label={{
              value: `${e.type === 'high' ? 'H' : 'L'} ${e.height_m.toFixed(1)}`,
              fill: 'var(--color-text-secondary)',
              fontSize: mobile ? 7 : 9,
              position: e.type === 'high' ? 'insideTop' : 'insideBottom',
              offset: mobile ? 2 : 4,
            }}
          />
        ))}
      </AreaChart>
    </ResponsiveContainer>
  )
}
