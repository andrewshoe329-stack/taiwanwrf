import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis,
  CartesianGrid, Tooltip, ReferenceLine,
} from 'recharts'
import type { ForecastRecord } from '@/lib/types'
import { useIsMobile } from '@/hooks/useIsMobile'
import {
  toCSTLabel, MultiLineTick, timeTicks, timeDomain,
  filterByTimeRange, findNowMs,
  chartMargin, chartHeight, chartHeightCompact, xAxisHeight, YAXIS_WIDTH, NOW_LABEL,
  type TimeRange,
} from './chart-utils'

interface ChartProps {
  records: ForecastRecord[]
  timeRange?: TimeRange
}

interface TempRow {
  timeMs: number
  timeLabel: string
  temp?: number
}

interface PressureRow {
  timeMs: number
  timeLabel: string
  pressure?: number
}

function TempTooltip(props: any) {
  if (!props.active || !props.payload?.length) return null
  return (
    <div style={{
      background: '#0a0a0a', border: '1px solid #1a1a1a',
      borderRadius: 8, padding: '8px 12px', fontSize: 12,
    }}>
      <p style={{ color: '#666666', marginBottom: 4 }}>{props.payload[0]?.payload?.timeLabel}</p>
      {props.payload.map((p: any, i: number) => (
        <p key={i} style={{ color: p.color, margin: 0 }}>
          Temp: {typeof p.value === 'number' ? p.value.toFixed(1) : '--'} °C
        </p>
      ))}
    </div>
  )
}

function PressureTooltip(props: any) {
  if (!props.active || !props.payload?.length) return null
  return (
    <div style={{
      background: '#0a0a0a', border: '1px solid #1a1a1a',
      borderRadius: 8, padding: '8px 12px', fontSize: 12,
    }}>
      <p style={{ color: '#666666', marginBottom: 4 }}>{props.payload[0]?.payload?.timeLabel}</p>
      {props.payload.map((p: any, i: number) => (
        <p key={i} style={{ color: p.color, margin: 0 }}>
          Pressure: {typeof p.value === 'number' ? p.value.toFixed(1) : '--'} hPa
        </p>
      ))}
    </div>
  )
}

/** Temperature chart */
export function TempChart({ records, timeRange }: ChartProps) {
  if (!records?.length) return null
  const mobile = useIsMobile()

  const filtered = filterByTimeRange(records, timeRange)
  const chartData: TempRow[] = filtered.map(r => ({
    timeMs: new Date(r.valid_utc).getTime(),
    timeLabel: toCSTLabel(r.valid_utc),
    temp: r.temp_c,
  }))

  const nowMs = findNowMs(timeRange)
  const domain = timeDomain(timeRange) ?? ['dataMin', 'dataMax'] as any
  const ticks = timeTicks(timeRange, chartData)

  return (
    <ResponsiveContainer width="100%" height={chartHeightCompact(mobile)}>
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
          unit="°C"
          width={YAXIS_WIDTH}
          domain={['auto', 'auto']}
        />
        <Tooltip content={TempTooltip} />
        <Line
          dataKey="temp"
          name="Temp"
          stroke="var(--color-text-primary)"
          strokeWidth={1.5}
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
      </LineChart>
    </ResponsiveContainer>
  )
}

/** Pressure chart */
export function PressureChart({ records, timeRange }: ChartProps) {
  if (!records?.length) return null
  const mobile = useIsMobile()

  const filtered = filterByTimeRange(records, timeRange)
  const chartData: PressureRow[] = filtered.map(r => ({
    timeMs: new Date(r.valid_utc).getTime(),
    timeLabel: toCSTLabel(r.valid_utc),
    pressure: r.mslp_hpa,
  }))

  const nowMs = findNowMs(timeRange)
  const domain = timeDomain(timeRange) ?? ['dataMin', 'dataMax'] as any
  const ticks = timeTicks(timeRange, chartData)

  return (
    <ResponsiveContainer width="100%" height={chartHeight(mobile)}>
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
          unit=" hPa"
          width={YAXIS_WIDTH}
          domain={['auto', 'auto']}
        />
        <Tooltip content={PressureTooltip} />
        <Line
          dataKey="pressure"
          name="Pressure"
          stroke="var(--color-text-primary)"
          strokeWidth={1.5}
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
      </LineChart>
    </ResponsiveContainer>
  )
}

