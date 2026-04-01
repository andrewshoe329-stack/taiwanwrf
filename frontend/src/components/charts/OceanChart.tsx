import {
  ResponsiveContainer, ComposedChart, Area, Line, XAxis, YAxis,
  CartesianGrid, Tooltip, ReferenceLine,
} from 'recharts'
import type { TooltipContentProps } from 'recharts'
import type { WaveRecord } from '@/lib/types'
import { useIsMobile } from '@/hooks/useIsMobile'
import {
  toCSTLabel, MultiLineTick, timeTicks, timeDomain,
  filterByTimeRange,
  chartMargin, xAxisHeight, YAXIS_WIDTH, NOW_LABEL,
  type TimeRange,
} from './chart-utils'

interface OceanChartProps {
  records: WaveRecord[]
  timeRange?: TimeRange
  selectedMs?: number
}

interface ChartRow {
  timeMs: number
  timeLabel: string
  swell?: number
  wind_sea?: number
  total?: number
  period?: number
}

function OceanTooltip({ active, payload }: TooltipContentProps) {
  if (!active || !payload?.length) return null
  return (
    <div style={{
      background: '#0a0a0a', border: '1px solid #1a1a1a',
      borderRadius: 8, padding: '8px 12px', fontSize: 'var(--fs-compact)',
    }}>
      <p style={{ color: '#666666', marginBottom: 4 }}>{(payload[0]?.payload as ChartRow)?.timeLabel}</p>
      {payload.map((p, i) => (
        <p key={i} style={{ color: p.color, margin: 0 }}>
          {p.name}: {typeof p.value === 'number' ? p.value.toFixed(1) : '--'}
          {p.name === 'Period' ? ' s' : ' m'}
        </p>
      ))}
    </div>
  )
}

export function OceanChart({ records, timeRange, selectedMs }: OceanChartProps) {
  if (!records?.length) return null
  const mobile = useIsMobile()

  const filtered = filterByTimeRange(records, timeRange)
  const chartData: ChartRow[] = filtered.map(r => ({
    timeMs: new Date(r.valid_utc).getTime(),
    timeLabel: toCSTLabel(r.valid_utc),
    swell: r.swell_wave_height,
    wind_sea: r.wind_wave_height,
    total: r.wave_height,
    period: r.swell_wave_period ?? r.wave_period,
  }))

  const nowMs = selectedMs
  const domain = timeDomain(timeRange) ?? (['dataMin', 'dataMax'] as const)
  const ticks = timeTicks(timeRange, chartData, mobile)
  const h = mobile ? 160 : 180

  return (
    <ResponsiveContainer width="100%" height={h}>
      <ComposedChart data={chartData} margin={chartMargin(mobile, true)}>
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
        {/* Left axis: wave height */}
        <YAxis
          yAxisId="height"
          tick={{ fill: 'var(--color-text-muted)', fontSize: 'var(--fs-compact)' }}
          stroke="var(--color-border)"
          unit=" m"
          width={YAXIS_WIDTH}
        />
        {/* Right axis: period */}
        <YAxis
          yAxisId="period"
          orientation="right"
          tick={{ fill: 'var(--color-text-dim)', fontSize: 'var(--fs-compact)' }}
          stroke="var(--color-border)"
          unit=" s"
          width={36}
          domain={[0, 'auto']}
        />
        <Tooltip content={OceanTooltip} />
        <Area
          yAxisId="height"
          dataKey="swell"
          name="Swell"
          fill="var(--color-text-primary)"
          fillOpacity={0.06}
          stroke="var(--color-text-primary)"
          strokeWidth={0.75}
          strokeOpacity={0.5}
          type="monotone"
          isAnimationActive={false}
        />
        <Area
          yAxisId="height"
          dataKey="wind_sea"
          name="Wind Sea"
          fill="#888888"
          fillOpacity={0.08}
          stroke="#888888"
          strokeWidth={0.75}
          strokeOpacity={0.5}
          type="monotone"
          isAnimationActive={false}
        />
        <Line
          yAxisId="height"
          dataKey="total"
          name="Total"
          stroke="var(--color-text-primary)"
          strokeWidth={2}
          dot={false}
          type="monotone"
          isAnimationActive={false}
        />
        <Line
          yAxisId="period"
          dataKey="period"
          name="Period"
          stroke="#5eead4"
          strokeWidth={1.5}
          strokeDasharray="4 3"
          dot={false}
          type="monotone"
          isAnimationActive={false}
        />
        {nowMs != null && (
          <ReferenceLine
            x={nowMs}
            yAxisId="height"
            stroke="var(--color-text-muted)"
            strokeWidth={1}
            strokeDasharray="4 3"
            label={NOW_LABEL}
          />
        )}
      </ComposedChart>
    </ResponsiveContainer>
  )
}
