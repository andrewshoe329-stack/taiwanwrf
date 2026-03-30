import {
  ResponsiveContainer, AreaChart, Area, Line, XAxis, YAxis,
  CartesianGrid, Tooltip, ReferenceLine,
} from 'recharts'
import type { TooltipContentProps } from 'recharts'
import type { WaveRecord } from '@/lib/types'
import { useIsMobile } from '@/hooks/useIsMobile'
import {
  toCSTLabel, MultiLineTick, timeTicks, timeDomain,
  filterByTimeRange, findNowMs,
  chartMargin, chartHeight, xAxisHeight, YAXIS_WIDTH, NOW_LABEL,
  type TimeRange,
} from './chart-utils'

interface WaveChartProps {
  records: WaveRecord[]
  timeRange?: TimeRange
}

interface ChartRow {
  timeMs: number
  timeLabel: string
  swell?: number
  wind_sea?: number
  total?: number
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
          {p.name}: {typeof p.value === 'number' ? p.value.toFixed(1) : '--'} m
        </p>
      ))}
    </div>
  )
}

/** Wave height chart — swell, wind sea, total. Period is a separate chart. */
export function WaveChart({ records, timeRange }: WaveChartProps) {
  if (!records?.length) return null
  const mobile = useIsMobile()

  const filtered = filterByTimeRange(records, timeRange)
  const chartData: ChartRow[] = filtered.map(r => ({
    timeMs: new Date(r.valid_utc).getTime(),
    timeLabel: toCSTLabel(r.valid_utc),
    swell: r.swell_wave_height,
    wind_sea: r.wind_wave_height,
    total: r.wave_height,
  }))

  const nowMs = findNowMs(timeRange)
  const domain = timeDomain(timeRange) ?? ['dataMin', 'dataMax'] as any
  const ticks = timeTicks(timeRange, chartData)

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
        />
        <Tooltip content={CustomTooltip} />
        <Area
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
          dataKey="total"
          name="Total"
          stroke="var(--color-text-primary)"
          strokeWidth={2.5}
          dot={false}
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
      </AreaChart>
    </ResponsiveContainer>
  )
}

/* ── Swell Period chart (separate) ───────────────────────────────────── */

interface PeriodRow {
  timeMs: number
  timeLabel: string
  period?: number
}

function PeriodTooltip({ active, payload }: TooltipContentProps) {
  if (!active || !payload?.length) return null
  return (
    <div style={{
      background: '#0a0a0a', border: '1px solid #1a1a1a',
      borderRadius: 8, padding: '8px 12px', fontSize: 12,
    }}>
      <p style={{ color: '#666666', marginBottom: 4 }}>{(payload[0]?.payload as PeriodRow)?.timeLabel}</p>
      {payload.map((p, i) => (
        <p key={i} style={{ color: p.color, margin: 0 }}>
          Period: {typeof p.value === 'number' ? p.value.toFixed(1) : '--'} s
        </p>
      ))}
    </div>
  )
}

export function WavePeriodChart({ records, timeRange }: WaveChartProps) {
  if (!records?.length) return null
  const mobile = useIsMobile()

  const filtered = filterByTimeRange(records, timeRange)
  const chartData: PeriodRow[] = filtered.map(r => ({
    timeMs: new Date(r.valid_utc).getTime(),
    timeLabel: toCSTLabel(r.valid_utc),
    period: r.swell_wave_period ?? r.wave_period,
  }))

  const nowMs = findNowMs(timeRange)
  const domain = timeDomain(timeRange) ?? ['dataMin', 'dataMax'] as any
  const ticks = timeTicks(timeRange, chartData)

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
          unit=" s"
          width={YAXIS_WIDTH}
        />
        <Tooltip content={PeriodTooltip} />
        <Area
          dataKey="period"
          name="Swell Period"
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
      </AreaChart>
    </ResponsiveContainer>
  )
}
