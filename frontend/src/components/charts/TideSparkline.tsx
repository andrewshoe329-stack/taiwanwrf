import { useMemo } from 'react'
import { AreaChart, Area, ReferenceLine, ResponsiveContainer } from 'recharts'

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

  const extremaLabels = useMemo(() => {
    if (!extrema) return []
    return extrema
      .filter(e => {
        const t = new Date(e.time_utc).getTime()
        return t >= now && t <= windowEnd
      })
      .map(e => {
        const t = new Date(e.time_utc).getTime()
        const localH = new Date(t).getHours()
        const ampm = localH >= 12 ? 'p' : 'a'
        const h12 = localH % 12 || 12
        return {
          t,
          h: e.height_m,
          type: e.type,
          label: `${e.type === 'high' ? 'H' : 'L'} ${h12}${ampm}`,
        }
      })
  }, [extrema, now, windowEnd])

  if (chartData.length < 2) return null

  return (
    <div className="w-full rounded-md border border-white/10 overflow-hidden">
      <div className="flex items-center justify-between px-2 pt-1">
        <span className="text-[8px] uppercase tracking-wider text-[var(--color-text-dim)]">Tide 24h</span>
        <div className="flex gap-2">
          {extremaLabels.map((e, i) => (
            <span key={i} className={`text-[8px] font-medium ${e.type === 'high' ? 'text-blue-400' : 'text-slate-400'}`}>
              {e.label} {e.h.toFixed(1)}m
            </span>
          ))}
        </div>
      </div>
      <div style={{ height: 56 }}>
        <ResponsiveContainer width="100%" height={56}>
          <AreaChart data={chartData} margin={{ top: 4, right: 8, bottom: 0, left: 8 }}>
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
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
