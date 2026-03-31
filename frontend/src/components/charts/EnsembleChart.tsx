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
  chartMargin, xAxisHeight, YAXIS_WIDTH, NOW_LABEL,
  type TimeRange,
} from './chart-utils'

const MODEL_COLORS: Record<string, string> = {
  GFS: '#22c55e',
  ICON: '#f59e0b',
  JMA: '#8b5cf6',
}

const MODEL_KEYS = ['GFS', 'ICON', 'JMA'] as const

interface EnsembleChartProps {
  ensemble: EnsembleData | null
  timeRange?: TimeRange
  selectedMs?: number
}

interface ChartRow {
  timeMs: number
  timeLabel: string
  GFS?: number
  ICON?: number
  JMA?: number
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
          {p.name}: {typeof p.value === 'number' ? p.value.toFixed(1) : '--'} kt
        </p>
      ))}
    </div>
  )
}

export function EnsembleChart({ ensemble, timeRange, selectedMs }: EnsembleChartProps) {
  const mobile = useIsMobile()

  if (!ensemble?.models) return null

  // Build a merged timeline from all models
  const timeMap = new Map<number, ChartRow>()

  for (const key of MODEL_KEYS) {
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

  const activeModels = MODEL_KEYS.filter(k =>
    chartData.some(row => row[k] != null),
  )
  if (!activeModels.length) return null

  const nowMs = selectedMs
  const domain = timeDomain(timeRange) ?? (['dataMin', 'dataMax'] as const)
  const ticks = timeTicks(timeRange, chartData, mobile)

  return (
    <div>
      <p style={{
        fontSize: 10,
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
            tick={{ fill: 'var(--color-text-muted)', fontSize: 10 }}
            stroke="var(--color-border)"
            unit=" kt"
            width={YAXIS_WIDTH}
          />
          <Tooltip content={CustomTooltip} />
          {activeModels.map(key => (
            <Line
              key={key}
              dataKey={key}
              name={key}
              stroke={MODEL_COLORS[key]}
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
}
