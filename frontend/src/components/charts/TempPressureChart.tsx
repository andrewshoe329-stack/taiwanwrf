import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis,
  CartesianGrid, Tooltip, ReferenceLine,
} from 'recharts'
import type { ForecastRecord } from '@/lib/types'
import { useIsMobile } from '@/hooks/useIsMobile'
import {
  toCSTLabel, MultiLineTick, timeTicks,
  filterByTimeRange, findNowMs,
  chartMargin, chartHeight, xAxisHeight, YAXIS_WIDTH, NOW_LABEL,
  type TimeRange,
} from './chart-utils'

interface TempPressureChartProps {
  records: ForecastRecord[]
  timeRange?: TimeRange
}

interface ChartRow {
  timeMs: number
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
      <p style={{ color: '#666666', marginBottom: 4 }}>{props.payload[0]?.payload?.timeLabel}</p>
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

export function TempPressureChart({ records, timeRange }: TempPressureChartProps) {
  if (!records?.length) return null
  const mobile = useIsMobile()

  const filtered = filterByTimeRange(records, timeRange)
  const chartData: ChartRow[] = filtered.map(r => ({
    timeMs: new Date(r.valid_utc).getTime(),
    timeLabel: toCSTLabel(r.valid_utc),
    temp: r.temp_c,
    pressure: r.mslp_hpa,
  }))

  const nowMs = findNowMs(chartData)
  const ticks = timeTicks(chartData)

  return (
    <div>
      <ResponsiveContainer width="100%" height={chartHeight(mobile)}>
        <LineChart data={chartData} margin={chartMargin(mobile, !mobile)}>
          <CartesianGrid stroke="var(--color-border)" strokeDasharray="3 3" />
          <XAxis
            dataKey="timeMs"
            type="number"
            scale="time"
            domain={['dataMin', 'dataMax']}
            ticks={ticks}
            tick={<MultiLineTick />}
            stroke="var(--color-border)"
            height={xAxisHeight(mobile)}
          />
          <YAxis
            yAxisId="temp"
            tick={{ fill: 'var(--color-text-muted)', fontSize: 10 }}
            stroke="var(--color-border)"
            unit="°C"
            width={YAXIS_WIDTH}
            domain={['auto', 'auto']}
          />
          {!mobile && (
            <YAxis
              yAxisId="pressure"
              orientation="right"
              tick={{ fill: 'var(--color-text-muted)', fontSize: 10 }}
              stroke="var(--color-border)"
              unit=" hPa"
              width={YAXIS_WIDTH}
              domain={['auto', 'auto']}
            />
          )}
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
          {/* Pressure: separate axis on desktop, hidden on mobile (shown in tooltip only) */}
          {!mobile && (
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
          )}
          {nowMs != null && (
            <ReferenceLine
              yAxisId="temp"
              x={nowMs}
              stroke="var(--color-text-muted)"
              strokeWidth={1}
              strokeDasharray="4 3"
              label={NOW_LABEL}
            />
          )}
        </LineChart>
      </ResponsiveContainer>
      {mobile && (
        <p className="text-[9px] text-[var(--color-text-muted)] mt-1 ml-9">
          Pressure available in tooltip
        </p>
      )}
    </div>
  )
}
