import {
  ResponsiveContainer, LineChart, Line, Area, XAxis, YAxis,
  CartesianGrid, Tooltip,
} from 'recharts'
import type { ForecastRecord } from '@/lib/types'

interface WindChartProps {
  records: ForecastRecord[]
  ecmwfRecords?: ForecastRecord[]
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
  wrf_wind?: number
  wrf_gust?: number
  ecmwf_wind?: number
}

function CustomTooltip(props: any) {
  if (!props.active || !props.payload?.length) return null
  return (
    <div style={{
      background: '#0a0a0a', border: '1px solid #1a1a1a',
      borderRadius: 8, padding: '8px 12px', fontSize: 12,
    }}>
      <p style={{ color: '#666666', marginBottom: 4 }}>{props.label}</p>
      {props.payload.map((p: any, i: number) => (
        <p key={i} style={{ color: p.color, margin: 0 }}>
          {p.name}: {typeof p.value === 'number' ? p.value.toFixed(1) : '--'} kt
        </p>
      ))}
    </div>
  )
}

export function WindChart({ records, ecmwfRecords }: WindChartProps) {
  if (!records?.length) return null

  const ecmwfMap = new Map<string, ForecastRecord>()
  ecmwfRecords?.forEach(r => ecmwfMap.set(r.valid_utc, r))

  const chartData: ChartRow[] = records.map(r => ({
    time: toCST(r.valid_utc),
    timeLabel: toCSTLabel(r.valid_utc),
    wrf_wind: r.wind_kt,
    wrf_gust: r.gust_kt,
    ecmwf_wind: ecmwfMap.get(r.valid_utc)?.wind_kt,
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
          tick={{ fill: 'var(--color-text-muted)', fontSize: 10 }}
          stroke="var(--color-border)"
          unit=" kt"
          width={48}
        />
        <Tooltip content={CustomTooltip} />
        <Area
          dataKey="wrf_gust"
          name="Gust"
          fill="var(--color-text-primary)"
          fillOpacity={0.06}
          stroke="none"
          type="monotone"
          isAnimationActive={false}
        />
        <Line
          dataKey="wrf_wind"
          name="WRF"
          stroke="var(--color-text-primary)"
          strokeWidth={1.5}
          dot={false}
          type="monotone"
          isAnimationActive={false}
        />
        <Line
          dataKey="ecmwf_wind"
          name="ECMWF"
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
