import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis,
  CartesianGrid, Tooltip, ReferenceLine,
} from 'recharts'
import type { TooltipContentProps } from 'recharts'
import type { ForecastRecord } from '@/lib/types'
import { useIsMobile } from '@/hooks/useIsMobile'
import {
  toCSTLabel, MultiLineTick, timeTicks, timeDomain,
  filterByTimeRange,
  chartMargin, chartHeightCompact, xAxisHeight, YAXIS_WIDTH, NOW_LABEL,
  type TimeRange,
} from './chart-utils'

interface PrecipChartProps {
  records: ForecastRecord[]
  timeRange?: TimeRange
  selectedMs?: number
}

interface ChartRow {
  timeMs: number
  timeLabel: string
  precip?: number
}

function PrecipTooltip({ active, payload }: TooltipContentProps) {
  if (!active || !payload?.length) return null
  return (
    <div style={{
      background: '#0a0a0a', border: '1px solid #1a1a1a',
      borderRadius: 8, padding: '8px 12px', fontSize: 'var(--fs-body)',
    }}>
      <p style={{ color: '#666666', marginBottom: 4 }}>{(payload[0]?.payload as ChartRow)?.timeLabel}</p>
      {payload.map((p, i) => (
        <p key={i} style={{ color: p.color, margin: 0 }}>
          Precip: {typeof p.value === 'number' ? p.value.toFixed(1) : '0.0'} mm
        </p>
      ))}
    </div>
  )
}

/** 6-hourly precipitation bar chart. */
export function PrecipChart({ records, timeRange, selectedMs }: PrecipChartProps) {
  if (!records?.length) return null
  const mobile = useIsMobile()

  const filtered = filterByTimeRange(records, timeRange)

  const chartData: ChartRow[] = filtered.map(r => ({
    timeMs: new Date(r.valid_utc).getTime(),
    timeLabel: toCSTLabel(r.valid_utc),
    precip: r.precip_mm_6h ?? 0,
  }))

  const nowMs = selectedMs
  const domain = timeDomain(timeRange) ?? (['dataMin', 'dataMax'] as const)
  const ticks = timeTicks(timeRange, chartData, mobile)

  return (
    <ResponsiveContainer width="100%" height={chartHeightCompact(mobile)}>
      <BarChart data={chartData} margin={chartMargin(mobile, false)}>
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
          unit=" mm"
          width={YAXIS_WIDTH}
        />
        <Tooltip content={PrecipTooltip} />
        <Bar
          dataKey="precip"
          name="Precip 6h"
          fill="var(--color-text-primary)"
          fillOpacity={0.3}
          stroke="var(--color-text-primary)"
          strokeWidth={1}
          isAnimationActive={false}
          barSize={Math.max(4, Math.round(300 / Math.max(chartData.length, 1)))}
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
      </BarChart>
    </ResponsiveContainer>
  )
}
