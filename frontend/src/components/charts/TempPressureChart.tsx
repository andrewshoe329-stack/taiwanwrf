import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis,
  CartesianGrid, Tooltip,
} from 'recharts'
import type { ForecastRecord } from '@/lib/types'

interface TempPressureChartProps {
  records: ForecastRecord[]
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
  temp?: number
  pressure?: number
}

function CustomTooltip(props: any) {
  if (!props.active || !props.payload?.length) return null
  return (
    <div style={{
      background: '#0a0a0a', border: '1px solid #1a1a1a',
      borderRadius: 8, padding: '8px 12px', fontSize: 12,
    }}>
      <p style={{ color: '#666666', marginBottom: 4 }}>{props.label}</p>
      {props.payload.map((p: any) => {
        const unit = p.dataKey === 'temp' ? '°C' : 'hPa'
        return (
          <p key={String(p.dataKey)} style={{ color: p.color, margin: 0 }}>
            {p.name}: {typeof p.value === 'number' ? p.value.toFixed(1) : '--'} {unit}
          </p>
        )
      })}
    </div>
  )
}

export function TempPressureChart({ records }: TempPressureChartProps) {
  if (!records?.length) return null

  const chartData: ChartRow[] = records.map(r => ({
    time: toCST(r.valid_utc),
    timeLabel: toCSTLabel(r.valid_utc),
    temp: r.temp_c,
    pressure: r.mslp_hpa,
  }))

  return (
    <ResponsiveContainer width="100%" height={240}>
      <LineChart data={chartData} margin={{ top: 8, right: 8, bottom: 0, left: -12 }}>
        <CartesianGrid stroke="var(--color-border)" strokeDasharray="3 3" />
        <XAxis
          dataKey="time"
          tick={{ fill: 'var(--color-text-muted)', fontSize: 10 }}
          stroke="var(--color-border)"
          interval="preserveStartEnd"
        />
        <YAxis
          yAxisId="temp"
          tick={{ fill: 'var(--color-text-muted)', fontSize: 10 }}
          stroke="var(--color-border)"
          unit="°C"
          width={44}
          domain={['auto', 'auto']}
        />
        <YAxis
          yAxisId="pressure"
          orientation="right"
          tick={{ fill: 'var(--color-text-muted)', fontSize: 10 }}
          stroke="var(--color-border)"
          unit=" hPa"
          width={52}
          domain={['auto', 'auto']}
        />
        <Tooltip content={CustomTooltip} />
        <Line
          yAxisId="temp"
          dataKey="temp"
          name="Temp"
          stroke="var(--color-text-primary)"
          strokeWidth={1.5}
          dot={false}
          type="monotone"
          isAnimationActive={false}
        />
        <Line
          yAxisId="pressure"
          dataKey="pressure"
          name="Pressure"
          stroke="#888888"
          strokeWidth={1}
          strokeDasharray="4 3"
          dot={false}
          type="monotone"
          isAnimationActive={false}
        />
      </LineChart>
    </ResponsiveContainer>
  )
}
