import { useMemo } from 'react'
import { AreaChart, Area, ReferenceLine, ReferenceDot, ResponsiveContainer } from 'recharts'

interface TidePoint {
  time_utc: string
  height_m: number
}

interface TideExtremum {
  time_utc: string
  height_m: number
  type: 'high' | 'low'
}

interface TideSparklineProps {
  predictions: TidePoint[]
  extrema?: TideExtremum[]
  nowMs?: number
}

export function TideSparkline({ predictions, extrema, nowMs }: TideSparklineProps) {
  // Stabilize `now` so memos don't recompute every render when nowMs is undefined
  const now = useMemo(() => nowMs ?? Date.now(), [nowMs])
  const windowEnd = now + 24 * 3600_000

  const chartData = useMemo(() => {
    return predictions
      .filter(p => {
        const t = new Date(p.time_utc).getTime()
        return t >= now && t <= windowEnd
      })
      .map(p => ({
        t: new Date(p.time_utc).getTime(),
        h: p.height_m,
      }))
  }, [predictions, now, windowEnd])

  const extremaDots = useMemo(() => {
    if (!extrema) return []
    return extrema
      .filter(e => {
        const t = new Date(e.time_utc).getTime()
        return t >= now && t <= windowEnd
      })
      .map(e => ({
        t: new Date(e.time_utc).getTime(),
        h: e.height_m,
        type: e.type,
      }))
  }, [extrema, now, windowEnd])

  if (chartData.length < 2) return null

  return (
    <div className="w-full rounded-md border border-white/10 overflow-hidden" style={{ height: 48 }}>
      <ResponsiveContainer width="100%" height={48}>
        <AreaChart data={chartData} margin={{ top: 2, right: 0, bottom: 0, left: 0 }}>
          <defs>
            <linearGradient id="tideFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#60a5fa" stopOpacity={0.3} />
              <stop offset="100%" stopColor="#60a5fa" stopOpacity={0.05} />
            </linearGradient>
          </defs>
          <Area
            type="monotone"
            dataKey="h"
            stroke="#60a5fa"
            strokeWidth={1.5}
            fill="url(#tideFill)"
            isAnimationActive={false}
            dot={false}
          />
          {nowMs != null && chartData.length >= 2 && now >= chartData[0].t && now <= chartData[chartData.length - 1].t && (
            <ReferenceLine
              x={now}
              stroke="#f8fafc"
              strokeWidth={1}
              strokeOpacity={0.5}
              strokeDasharray="2 2"
            />
          )}
          {extremaDots.map((e, i) => (
            <ReferenceDot
              key={i}
              x={e.t}
              y={e.h}
              r={3}
              fill={e.type === 'high' ? '#60a5fa' : '#94a3b8'}
              stroke="none"
              ifOverflow="extendDomain"
            />
          ))}
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}
