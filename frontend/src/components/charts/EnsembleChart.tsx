import { memo } from 'react'
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis,
  CartesianGrid, Tooltip, ReferenceLine,
} from 'recharts'
import type { TooltipContentProps } from 'recharts'
import type { EnsembleData } from '@/lib/types'
import { useIsMobile } from '@/hooks/useIsMobile'
import {
  toCSTLabel, MultiLineTick, timeTicks, timeDomain,
  filterByTimeRange,
  chartMargin, xAxisHeight, yAxisWidth, NOW_LABEL, TOOLTIP_STYLE, TOOLTIP_LABEL_STYLE,
  type TimeRange,
} from './chart-utils'

const MODEL_COLORS: Record<string, string> = {
  ECMWF: '#60a5fa',  // blue
  GFS: '#22c55e',    // green
  ICON: '#f59e0b',   // amber
  JMA: '#8b5cf6',    // purple
}

// Preferred display order — models only shown if they have data
const MODEL_ORDER = ['ECMWF', 'GFS', 'ICON', 'JMA'] as const

interface ChartRow {
  timeMs: number
  timeLabel: string
  [model: string]: number | string | undefined
}

function CustomTooltip({ active, payload }: TooltipContentProps) {
  if (!active || !payload?.length) return null
  return (
    <div style={TOOLTIP_STYLE}>
      <p style={TOOLTIP_LABEL_STYLE}>{(payload[0]?.payload as ChartRow)?.timeLabel}</p>
      {payload.map((p, i) => (
        <p key={i} style={{ color: p.color, margin: 0 }}>
          {p.name}: {typeof p.value === 'number' ? p.value.toFixed(1) : '--'} kt
        </p>
      ))}
    </div>
  )
}

interface EnsembleChartProps {
  ensemble: EnsembleData | null
  timeRange?: TimeRange
  selectedMs?: number
}

export const EnsembleChart = memo(function EnsembleChart({ ensemble, timeRange, selectedMs }: EnsembleChartProps) {
  const mobile = useIsMobile()

  if (!ensemble?.models) return null

  // Discover which models have records
  const availableModels = MODEL_ORDER.filter(k =>
    ensemble.models[k]?.records?.length,
  )
  if (!availableModels.length) return null

  // Build a merged timeline from all models
  const timeMap = new Map<number, ChartRow>()

  for (const key of availableModels) {
    const model = ensemble.models[key]
    if (!model?.records?.length) continue

    const records = filterByTimeRange(model.records, timeRange)

    for (const r of records) {
      const ms = new Date(r.valid_utc).getTime()
      if (!timeMap.has(ms)) {
        timeMap.set(ms, {
          timeMs: ms,
          timeLabel: toCSTLabel(r.valid_utc),
        })
      }
      const row = timeMap.get(ms)!
      if (r.wind_kt != null) {
        row[key] = r.wind_kt
      }
    }
  }

  const chartData = Array.from(timeMap.values()).sort((a, b) => a.timeMs - b.timeMs)
  if (!chartData.length) return null

  const activeModels = availableModels.filter(k =>
    chartData.some(row => row[k] != null),
  )
  if (!activeModels.length) return null

  const nowMs = selectedMs
  const domain = timeDomain(timeRange) ?? (['dataMin', 'dataMax'] as const)
  const ticks = timeTicks(timeRange, chartData, mobile)

  return (
    <div>
      <p style={{
        fontSize: 'var(--fs-compact)',
        textTransform: 'uppercase',
        letterSpacing: '0.05em',
        color: 'var(--color-text-muted)',
        margin: '0 0 4px 0',
      }}>
        Model Comparison — Wind
      </p>
      <ResponsiveContainer width="100%" height={140}>
        <LineChart data={chartData} margin={chartMargin(mobile, false)}>
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
            tick={{ fill: 'var(--color-text-muted)', fontSize: 'var(--fs-compact)' }}
            stroke="var(--color-border)"
            unit=" kt"
            width={yAxisWidth(mobile)}
          />
          <Tooltip content={CustomTooltip} allowEscapeViewBox={{ x: false, y: false }} />
          {activeModels.map(key => (
            <Line
              key={key}
              dataKey={key}
              name={key}
              stroke={MODEL_COLORS[key] ?? '#888'}
              strokeWidth={1.5}
              dot={false}
              type="monotone"
              isAnimationActive={false}
              connectNulls
            />
          ))}
          {nowMs != null && (
            <ReferenceLine
              x={nowMs}
              stroke="var(--color-text-muted)"
              strokeWidth={1}
              strokeDasharray="4 3"
              label={NOW_LABEL}
            />
          )}
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
})
