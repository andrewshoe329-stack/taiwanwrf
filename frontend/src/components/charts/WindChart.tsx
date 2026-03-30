import {
  ResponsiveContainer, LineChart, Line, Area, XAxis, YAxis,
  CartesianGrid, Tooltip, ReferenceLine,
} from 'recharts'
import type { TooltipContentProps } from 'recharts'
import type { ForecastRecord } from '@/lib/types'
import { useIsMobile } from '@/hooks/useIsMobile'
import {
  toCSTLabel, MultiLineTick, timeTicks, timeDomain,
  filterByTimeRange,
  chartMargin, chartHeight, xAxisHeight, YAXIS_WIDTH, NOW_LABEL,
  type TimeRange,
} from './chart-utils'

interface WindChartProps {
  records: ForecastRecord[]
  ecmwfRecords?: ForecastRecord[]
  timeRange?: TimeRange
  selectedMs?: number
}

interface ChartRow {
  timeMs: number
  timeLabel: string
  wrf_wind?: number
  wrf_gust?: number
  ecmwf_wind?: number
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
          {p.name}: {typeof p.value === 'number' ? p.value.toFixed(1) : '--'} kt
        </p>
      ))}
    </div>
  )
}

export function WindChart({ records, ecmwfRecords, timeRange, selectedMs }: WindChartProps) {
  if (!records?.length) return null
  const mobile = useIsMobile()

  const filtered = filterByTimeRange(records, timeRange)
  const ecmwfMap = new Map<string, ForecastRecord>()
  ecmwfRecords?.forEach(r => ecmwfMap.set(r.valid_utc, r))

  const chartData: ChartRow[] = filtered.map(r => ({
    timeMs: new Date(r.valid_utc).getTime(),
    timeLabel: toCSTLabel(r.valid_utc),
    wrf_wind: r.wind_kt,
    wrf_gust: r.gust_kt,
    ecmwf_wind: ecmwfMap.get(r.valid_utc)?.wind_kt,
  }))

  const nowMs = selectedMs
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
          unit=" kt"
          width={YAXIS_WIDTH}
        />
        <Tooltip content={CustomTooltip} />
        {/* Beaufort reference lines */}
        <ReferenceLine y={12} stroke="var(--color-text-dim)" strokeDasharray="2 4" />
        <ReferenceLine y={25} stroke="var(--color-text-dim)" strokeDasharray="2 4" />
        <ReferenceLine y={35} stroke="var(--color-rating-dangerous)" strokeDasharray="2 4" strokeOpacity={0.4} />
        <Area
          dataKey="wrf_gust"
          name="Gust"
          fill="var(--color-text-primary)"
          fillOpacity={0.15}
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
