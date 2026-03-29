import {
  ResponsiveContainer, LineChart, Line, Area, XAxis, YAxis,
  CartesianGrid, Tooltip,
} from 'recharts'
import type { ForecastRecord } from '@/lib/types'
import { toCST, toCSTLabel, tickInterval, MultiLineTick, filterByTimeRange, type TimeRange } from './chart-utils'

interface WindChartProps {
  records: ForecastRecord[]
  ecmwfRecords?: ForecastRecord[]
  timeRange?: TimeRange
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
      <p style={{ color: '#666666', marginBottom: 4 }}>{props.payload[0]?.payload?.timeLabel}</p>
      {props.payload.map((p: any, i: number) => (
        <p key={i} style={{ color: p.color, margin: 0 }}>
          {p.name}: {typeof p.value === 'number' ? p.value.toFixed(1) : '--'} kt
        </p>
      ))}
    </div>
  )
}

export function WindChart({ records, ecmwfRecords, timeRange }: WindChartProps) {
  if (!records?.length) return null

  const filtered = filterByTimeRange(records, timeRange)
  const ecmwfMap = new Map<string, ForecastRecord>()
  ecmwfRecords?.forEach(r => ecmwfMap.set(r.valid_utc, r))

  const chartData: ChartRow[] = filtered.map(r => ({
    time: toCST(r.valid_utc),
    timeLabel: toCSTLabel(r.valid_utc),
    wrf_wind: r.wind_kt,
    wrf_gust: r.gust_kt,
    ecmwf_wind: ecmwfMap.get(r.valid_utc)?.wind_kt,
  }))

  return (
    <ResponsiveContainer width="100%" height={240}>
      <LineChart data={chartData} margin={{ top: 8, right: 8, bottom: 16, left: -12 }}>
        <CartesianGrid stroke="var(--color-border)" strokeDasharray="3 3" />
        <XAxis
          dataKey="time"
          tick={<MultiLineTick />}
          stroke="var(--color-border)"
          interval={tickInterval(chartData.length)}
          height={40}
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
