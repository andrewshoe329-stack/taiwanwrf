import {
  ResponsiveContainer, AreaChart, Area, Line, XAxis, YAxis,
  CartesianGrid, Tooltip,
} from 'recharts'
import type { WaveRecord } from '@/lib/types'

interface WaveChartProps {
  records: WaveRecord[]
}

function toCST(utc: string): string {
  const d = new Date(utc)
  d.setUTCHours(d.getUTCHours() + 8)
  return `${String(d.getUTCHours()).padStart(2, '0')}:00`
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
      <p style={{ color: '#666666', marginBottom: 4 }}>{props.label}</p>
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

export function WaveChart({ records }: WaveChartProps) {
  if (!records?.length) return null

  const chartData: ChartRow[] = records.map(r => ({
    time: toCST(r.valid_utc),
    timeLabel: toCSTLabel(r.valid_utc),
    swell: r.swell_wave_height,
    wind_sea: r.wind_wave_height,
    total: r.wave_height,
    period: r.wave_period,
  }))

  return (
    <ResponsiveContainer width="100%" height={240}>
      <AreaChart data={chartData} margin={{ top: 8, right: 8, bottom: 0, left: -12 }}>
        <CartesianGrid stroke="var(--color-border)" strokeDasharray="3 3" />
        <XAxis
          dataKey="time"
          tick={{ fill: 'var(--color-text-muted)', fontSize: 10 }}
          stroke="var(--color-border)"
          interval="preserveStartEnd"
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
          width={40}
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
          stackId="waves"
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
          stackId="waves"
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
      </AreaChart>
    </ResponsiveContainer>
  )
}
