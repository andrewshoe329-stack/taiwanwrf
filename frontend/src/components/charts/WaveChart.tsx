import {
  ResponsiveContainer, AreaChart, Area, Line, XAxis, YAxis,
  CartesianGrid, Tooltip, ReferenceLine,
} from 'recharts'
import type { WaveRecord } from '@/lib/types'
import { toCST, toCSTLabel, tickInterval, MultiLineTick, filterByTimeRange, findNowTime, type TimeRange } from './chart-utils'

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

export function WaveChart({ records, timeRange }: WaveChartProps) {
  if (!records?.length) return null

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
    <ResponsiveContainer width="100%" height={240}>
      <AreaChart data={chartData} margin={{ top: 8, right: 8, bottom: 16, left: -12 }}>
        <CartesianGrid stroke="var(--color-border)" strokeDasharray="3 3" />
        <XAxis
          dataKey="time"
          tick={<MultiLineTick />}
          stroke="var(--color-border)"
          interval={tickInterval(chartData.length)}
          height={40}
        />
        <YAxis
          yAxisId="height"
          tick={{ fill: 'var(--color-text-muted)', fontSize: 10 }}
          stroke="var(--color-border)"
          unit=" m"
          width={44}
        />
        <YAxis
          yAxisId="period"
          orientation="right"
          tick={{ fill: 'var(--color-text-muted)', fontSize: 10 }}
          stroke="var(--color-border)"
          unit=" s"
          width={44}
        />
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
          yAxisId="period"
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
            x={nowTime}
            stroke="var(--color-text-muted)"
            strokeWidth={1}
            strokeDasharray="4 3"
            label={{ value: 'Now', fill: 'var(--color-text-muted)', fontSize: 10, position: 'insideTopRight', offset: 4 }}
          />
        )}
      </AreaChart>
    </ResponsiveContainer>
  )
}
