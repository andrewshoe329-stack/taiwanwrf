/**
 * SVG compass rose showing swell direction and quality for a surf spot.
 * Highlights optimal swell directions and shows current swell arrow.
 */
import { DIR_ANGLES, facingAngle } from '@/lib/forecast-utils'

const DIRECTIONS = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'] as const

/** Build arc segments for optimal swell directions */
function optSwellArcs(optSwell: string[]): Array<{ startAngle: number; endAngle: number }> {
  if (optSwell.length === 0) return []

  // Convert each optimal direction to an angle and create a small arc around it
  const angles = optSwell
    .map(d => DIR_ANGLES[d])
    .filter((a): a is number => a !== undefined)
    .sort((a, b) => a - b)

  if (angles.length === 0) return []

  // Merge adjacent directions into continuous arcs
  const arcs: Array<{ startAngle: number; endAngle: number }> = []
  let start = angles[0]
  let end = angles[0]

  for (let i = 1; i < angles.length; i++) {
    const diff = angles[i] - end
    if (diff <= 22.5 + 1) {
      // Adjacent — extend the arc
      end = angles[i]
    } else {
      arcs.push({ startAngle: start - 11.25, endAngle: end + 11.25 })
      start = angles[i]
      end = angles[i]
    }
  }
  arcs.push({ startAngle: start - 11.25, endAngle: end + 11.25 })

  // Check wrap-around: if last arc's end and first arc's start are adjacent across 360
  if (arcs.length > 1) {
    const first = arcs[0]
    const last = arcs[arcs.length - 1]
    if (360 - last.endAngle + first.startAngle <= 23) {
      arcs[0] = { startAngle: last.startAngle - 360, endAngle: first.endAngle }
      arcs.pop()
    }
  }

  return arcs
}

function describeArc(cx: number, cy: number, r: number, startAngle: number, endAngle: number): string {
  // SVG arcs: 0deg = top (N), clockwise
  const toRad = (deg: number) => ((deg - 90) * Math.PI) / 180
  const x1 = cx + r * Math.cos(toRad(startAngle))
  const y1 = cy + r * Math.sin(toRad(startAngle))
  const x2 = cx + r * Math.cos(toRad(endAngle))
  const y2 = cy + r * Math.sin(toRad(endAngle))
  const span = endAngle - startAngle
  const largeArc = span > 180 ? 1 : 0
  return `M ${cx} ${cy} L ${x1} ${y1} A ${r} ${r} 0 ${largeArc} 1 ${x2} ${y2} Z`
}

interface SwellCompassProps {
  facing: string
  optSwell: string[]
  swellDir?: number
  swellHeight?: number
  size?: number
}

export function SwellCompass({ facing, optSwell, swellDir, swellHeight, size }: SwellCompassProps) {
  const cx = 100
  const cy = 100
  const outerR = 88
  const innerR = 70
  const labelR = 78
  const tickR = 92

  const facingDeg = facingAngle(facing)
  const arcs = optSwellArcs(optSwell)

  // Arrow opacity based on swell height: 0m → 0.3, 3m+ → 1.0
  const arrowOpacity = swellHeight != null
    ? Math.min(1, Math.max(0.3, swellHeight / 3))
    : 0.6

  return (
    <svg viewBox="0 0 200 200" className="block" style={{ width: size ?? 200, height: size ?? 200 }} role="img" aria-labelledby="compass-title compass-desc">
      <title id="compass-title">Swell Compass</title>
      <desc id="compass-desc">Shows current swell direction relative to optimal directions for this spot (facing {facing})</desc>
      {/* Outer ring */}
      <circle cx={cx} cy={cy} r={outerR} fill="none" stroke="var(--color-border)" strokeWidth="1" />
      <circle cx={cx} cy={cy} r={innerR} fill="none" stroke="var(--color-border-subtle)" strokeWidth="0.5" />

      {/* Cross hairs */}
      {[0, 45, 90, 135].map(angle => {
        const rad = ((angle - 90) * Math.PI) / 180
        const x1 = cx + innerR * Math.cos(rad)
        const y1 = cy + innerR * Math.sin(rad)
        const x2 = cx + outerR * Math.cos(rad)
        const y2 = cy + outerR * Math.sin(rad)
        const x3 = cx - innerR * Math.cos(rad)
        const y3 = cy - innerR * Math.sin(rad)
        const x4 = cx - outerR * Math.cos(rad)
        const y4 = cy - outerR * Math.sin(rad)
        return (
          <g key={angle}>
            <line x1={x1} y1={y1} x2={x2} y2={y2} stroke="var(--color-border-subtle)" strokeWidth="0.5" />
            <line x1={x3} y1={y3} x2={x4} y2={y4} stroke="var(--color-border-subtle)" strokeWidth="0.5" />
          </g>
        )
      })}

      {/* Optimal swell arcs */}
      {arcs.map((arc, i) => (
        <path
          key={i}
          d={describeArc(cx, cy, outerR, arc.startAngle, arc.endAngle)}
          fill="white"
          opacity={0.15}
        />
      ))}

      {/* Direction labels — hide intercardinals on small compass to prevent overlap */}
      {DIRECTIONS.filter(dir => (size ?? 200) >= 100 || dir.length === 1).map(dir => {
        const idx = DIRECTIONS.indexOf(dir)
        const angle = idx * 45
        const rad = ((angle - 90) * Math.PI) / 180
        const x = cx + labelR * Math.cos(rad)
        const y = cy + labelR * Math.sin(rad)
        return (
          <text
            key={dir}
            x={x}
            y={y}
            textAnchor="middle"
            dominantBaseline="central"
            fill="var(--color-text-muted)"
            fontSize="var(--fs-micro)"
            fontWeight={dir === 'N' ? '600' : '400'}
          >
            {dir}
          </text>
        )
      })}

      {/* Beach facing tick */}
      {(() => {
        const rad = ((facingDeg - 90) * Math.PI) / 180
        const x1 = cx + (outerR - 4) * Math.cos(rad)
        const y1 = cy + (outerR - 4) * Math.sin(rad)
        const x2 = cx + tickR * Math.cos(rad)
        const y2 = cy + tickR * Math.sin(rad)
        return (
          <line
            x1={x1} y1={y1} x2={x2} y2={y2}
            stroke="var(--color-text-muted)"
            strokeWidth="2.5"
            strokeLinecap="round"
          />
        )
      })()}

      {/* Current swell direction arrow */}
      {swellDir != null && (
        (() => {
          // Swell direction is where swell comes FROM, so arrow points from edge toward center
          const rad = ((swellDir - 90) * Math.PI) / 180
          const tipX = cx + 20 * Math.cos(rad)
          const tipY = cy + 20 * Math.sin(rad)
          const tailX = cx + (innerR - 4) * Math.cos(rad)
          const tailY = cy + (innerR - 4) * Math.sin(rad)
          // Arrowhead
          const headLen = 8
          const headAngle = 25 * Math.PI / 180
          const ax1 = tipX + headLen * Math.cos(rad + Math.PI - headAngle)
          const ay1 = tipY + headLen * Math.sin(rad + Math.PI - headAngle)
          const ax2 = tipX + headLen * Math.cos(rad + Math.PI + headAngle)
          const ay2 = tipY + headLen * Math.sin(rad + Math.PI + headAngle)
          return (
            <g opacity={arrowOpacity}>
              <line
                x1={tailX} y1={tailY} x2={tipX} y2={tipY}
                stroke="var(--color-text-primary)"
                strokeWidth="2"
                strokeLinecap="round"
              />
              <polygon
                points={`${tipX},${tipY} ${ax1},${ay1} ${ax2},${ay2}`}
                fill="var(--color-text-primary)"
              />
            </g>
          )
        })()
      )}

      {/* Center dot */}
      <circle cx={cx} cy={cy} r="2" fill="var(--color-text-dim)" />
    </svg>
  )
}
