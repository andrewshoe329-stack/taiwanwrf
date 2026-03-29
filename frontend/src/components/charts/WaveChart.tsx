import {
  ResponsiveContainer, AreaChart, Area, Line, XAxis, YAxis,
  CartesianGrid, Tooltip, ReferenceLine,
} from 'recharts'
import type { WaveRecord } from '@/lib/types'
import { useIsMobile } from '@/hooks/useIsMobile'
import {
  toCST, toCSTLabel, tickInterval, MultiLineTick,
  filterByTimeRange, findNowTime,
  chartMargin, chartHeight, xAxisHeight, YAXIS_WIDTH, NOW_LABEL,
  type TimeRange,
} from './chart-utils'

interface WaveChartProps {
  records: WaveRecord[]
  timeRange?: TimeRange
}

interface ChartRow {
  time: string
  timeLabel: string
  timeMs: number
  swell?: number
  wind_sea?: number
  total?: number
  period?: number
}

function CustomTooltip(props: any) {
  if (!props.active || !props.payload?.length) return null
  return (
    <div style={{
      background: '#0a0a0a', border: '1px solid #1a1a1a',
      borderRadius: 8, padding: '8px 12px', fontSize: 12,
    }}>
      <p style={{ color: '#666666', marginBottom: 4 }}>{props.payload[0]?.payload?.timeLabel}</p>
      {props.payload.map((p: any, i: number) => {
        const unit = String(p.dataKey) === 'period' ? 's' : 'm'
        return (
          <p key={i} style={{ color: p.color, margin: 0 }}>
            {p.name}: {typeof p.value === 'number' ? p.value.toFixed(1) : '--'} {unit}
          </p>
        )
      })}
    </div>
  )
}

/** Inline legend for mobile (replaces hidden right Y-axis) */
function DualLegend({ items }: { items: { color: string; label: string }[] }) {
  return (
    <div className="flex gap-3 mt-1 ml-9">
      {items.map(({ color, label }) => (
        <span key={label} className="flex items-center gap-1 text-[9px] text-[var(--color-text-muted)]">
          <span className="inline-block w-2 h-2 rounded-full" style={{ background: color }} />
          {label}
        </span>
      ))}
    </div>
  )
}

export function WaveChart({ records, timeRange }: WaveChartProps) {
  if (!records?.length) return null
  const mobile = useIsMobile()

  const filtered = filterByTimeRange(records, timeRange)
  const chartData: ChartRow[] = filtered.map(r => ({
    time: toCST(r.valid_utc),
    timeLabel: toCSTLabel(r.valid_utc),
    timeMs: new Date(r.valid_utc).getTime(),
    swell: r.swell_wave_height,
    wind_sea: r.wind_wave_height,
    total: r.wave_height,
    period: r.wave_period,
  }))

  const nowTime = findNowTime(chartData)

  return (
    <div>
      <ResponsiveContainer width="100%" height={chartHeight(mobile)}>
        <AreaChart data={chartData} margin={chartMargin(mobile, !mobile)}>
          <CartesianGrid stroke="var(--color-border)" strokeDasharray="3 3" />
          <XAxis
            dataKey="time"
            tick={<MultiLineTick />}
            stroke="var(--color-border)"
            interval={tickInterval(chartData.length)}
            height={xAxisHeight(mobile)}
          />
          <YAxis
            yAxisId="height"
            tick={{ fill: 'var(--color-text-muted)', fontSize: 10 }}
            stroke="var(--color-border)"
            unit=" m"
            width={YAXIS_WIDTH}
          />
          {!mobile && (
            <YAxis
              yAxisId="period"
              orientation="right"
              tick={{ fill: 'var(--color-text-muted)', fontSize: 10 }}
              stroke="var(--color-border)"
              unit=" s"
              width={YAXIS_WIDTH}
            />
          )}
          <Tooltip content={CustomTooltip} />
          <Area
            yAxisId="height"
            dataKey="swell"
            name="Swell"
            fill="var(--color-text-primary)"
            fillOpacity={0.1}
            stroke="var(--color-text-primary)"
            strokeWidth={1}
            type="monotone"
            isAnimationActive={false}
          />
          <Area
            yAxisId="height"
            dataKey="wind_sea"
            name="Wind Sea"
            fill="#888888"
            fillOpacity={0.15}
            stroke="#888888"
            strokeWidth={1}
            type="monotone"
            isAnimationActive={false}
          />
          <Line
            yAxisId="height"
            dataKey="total"
            name="Total"
            stroke="var(--color-text-primary)"
            strokeWidth={1.5}
            dot={false}
            type="monotone"
            isAnimationActive={false}
          />
          <Line
            yAxisId={mobile ? 'height' : 'period'}
            dataKey="period"
            name="Period"
            stroke="var(--color-text-muted)"
            strokeWidth={1}
            strokeDasharray="4 3"
            dot={false}
            type="monotone"
            isAnimationActive={false}
          />
          {nowTime && (
            <ReferenceLine
              yAxisId="height"
              x={nowTime}
              stroke="var(--color-text-muted)"
              strokeWidth={1}
              strokeDasharray="4 3"
              label={NOW_LABEL}
            />
          )}
        </AreaChart>
      </ResponsiveContainer>
      {mobile && (
        <DualLegend items={[
          { color: 'var(--color-text-primary)', label: 'Height (m)' },
          { color: 'var(--color-text-muted)', label: 'Period (s)' },
        ]} />
      )}
    </div>
  )
}
