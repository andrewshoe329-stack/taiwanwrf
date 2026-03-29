import { useRef, useEffect, useCallback, useState } from 'react'
import { TAIWAN_BBOX, SPOTS, HARBOURS } from '@/lib/constants'
import { WindParticleSystem } from '@/lib/wind-particles'
import { interpolateWindGrid } from '@/lib/interpolate'
import { useTimeline } from '@/hooks/useTimeline'
import { useWindGrid, type WindModel } from '@/hooks/useWindGrid'

const MODEL_LABELS: Record<WindModel, string> = {
  wrf: 'WRF 3km',
  ecmwf: 'ECMWF',
  gfs: 'GFS',
}

// Zoom limits (degrees of longitude span)
const MIN_LON_SPAN = 0.3   // max zoom in
const MAX_LON_SPAN = 4.0   // max zoom out

interface MapLabel {
  lon: number
  lat: number
  text: string
  textZh?: string
  type: 'spot' | 'harbour' | 'city'
  id?: string
  facing?: string
  region?: string
  opt_wind?: string[]
  opt_swell?: string[]
}

// Build label list once
const ALL_LABELS: MapLabel[] = [
  ...SPOTS.map(s => ({
    lon: s.lon, lat: s.lat, text: s.name.en, textZh: s.name.zh,
    type: 'spot' as const, id: s.id,
    facing: s.facing, region: s.region,
    opt_wind: s.opt_wind, opt_swell: s.opt_swell,
  })),
  ...HARBOURS.map(h => ({
    lon: h.lon, lat: h.lat, text: h.name.en, textZh: h.name.zh,
    type: 'harbour' as const, id: h.id,
  })),
  { lon: 121.565, lat: 25.033, text: 'Taipei', type: 'city' },
  { lon: 121.817, lat: 24.760, text: 'Yilan', type: 'city' },
]

interface TooltipData {
  x: number
  y: number
  label: MapLabel
}

/**
 * Canvas-only forecast map with zoom/pan and hover tooltips.
 * Renders: ocean background, land fill + coastline, wind particles, spot labels.
 */
export function ForecastMap() {
  const containerRef = useRef<HTMLDivElement>(null)
  const particlesRef = useRef<WindParticleSystem | null>(null)
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const boundsRef = useRef({
    west: TAIWAN_BBOX.lon_min,
    south: TAIWAN_BBOX.lat_min,
    east: TAIWAN_BBOX.lon_max,
    north: TAIWAN_BBOX.lat_max,
  })

  // Drag state
  const dragRef = useRef<{ startX: number; startY: number; startBounds: typeof boundsRef.current } | null>(null)
  // Pinch state
  const pinchRef = useRef<{ startDist: number; startBounds: typeof boundsRef.current } | null>(null)

  const [tooltip, setTooltip] = useState<TooltipData | null>(null)

  const { index } = useTimeline()
  const { grid, model, setModel } = useWindGrid()

  const updateBounds = useCallback((west: number, south: number, east: number, north: number) => {
    // Clamp zoom
    let lonSpan = east - west
    let latSpan = north - south
    const aspect = latSpan / lonSpan

    if (lonSpan < MIN_LON_SPAN) {
      const center = (west + east) / 2
      lonSpan = MIN_LON_SPAN
      latSpan = lonSpan * aspect
      west = center - lonSpan / 2
      east = center + lonSpan / 2
      south = (south + north) / 2 - latSpan / 2
      north = (south + north) / 2 + latSpan / 2
    }
    if (lonSpan > MAX_LON_SPAN) {
      const center = (west + east) / 2
      lonSpan = MAX_LON_SPAN
      latSpan = lonSpan * aspect
      west = center - lonSpan / 2
      east = center + lonSpan / 2
      south = (south + north) / 2 - latSpan / 2
      north = (south + north) / 2 + latSpan / 2
    }

    boundsRef.current = { west, south, east, north }
    particlesRef.current?.setBounds(west, south, east, north)
  }, [])

  useEffect(() => {
    if (!containerRef.current) return
    const container = containerRef.current

    const canvas = document.createElement('canvas')
    canvas.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;touch-action:none;'
    container.appendChild(canvas)
    canvasRef.current = canvas

    const ps = new WindParticleSystem({
      canvas,
      count: window.innerWidth < 768 ? 2000 : 4000,
      maxAge: 80,
      speedFactor: 0.3,
      lineWidth: 1.2,
      fadeFactor: 0.97,
    })
    particlesRef.current = ps

    const b = boundsRef.current
    ps.setBounds(b.west, b.south, b.east, b.north)

    const syncSize = () => {
      const { clientWidth: w, clientHeight: h } = container
      if (w === 0 || h === 0) return
      canvas.width = w
      canvas.height = h
      ps.resize(w, h)
    }

    const loadCoastline = async () => {
      try {
        const resp = await fetch('/data/taiwan.geojson?v=4')
        if (!resp.ok) throw new Error(`GeoJSON ${resp.status}`)
        const geojson = await resp.json()

        const rings: [number, number][][] = []
        for (const feature of geojson.features ?? []) {
          const coords = feature.geometry?.coordinates
          if (feature.geometry?.type === 'Polygon' && coords) {
            for (const ring of coords) rings.push(ring)
          } else if (feature.geometry?.type === 'MultiPolygon' && coords) {
            for (const polygon of coords)
              for (const ring of polygon) rings.push(ring)
          }
        }
        ps.setCoastline(rings)
      } catch (err) {
        console.warn('[ForecastMap] Coastline failed:', err)
      }

      ps.setLabels(ALL_LABELS)
    }

    // ── Mouse wheel zoom ──
    const handleWheel = (e: WheelEvent) => {
      e.preventDefault()
      const rect = canvas.getBoundingClientRect()
      const mx = e.clientX - rect.left
      const my = e.clientY - rect.top
      const w = canvas.width
      const h = canvas.height

      const { west, east, south, north } = boundsRef.current
      // Mouse position in geo coords
      const lon = west + (mx / w) * (east - west)
      const lat = north - (my / h) * (north - south)

      // Zoom factor
      const factor = e.deltaY > 0 ? 1.15 : 1 / 1.15

      // Scale bounds around mouse position
      const newWest = lon - (lon - west) * factor
      const newEast = lon + (east - lon) * factor
      const newSouth = lat - (lat - south) * factor
      const newNorth = lat + (north - lat) * factor

      updateBounds(newWest, newSouth, newEast, newNorth)
    }

    // ── Mouse drag pan ──
    const handleMouseDown = (e: MouseEvent) => {
      if (e.button !== 0) return
      dragRef.current = {
        startX: e.clientX,
        startY: e.clientY,
        startBounds: { ...boundsRef.current },
      }
      canvas.style.cursor = 'grabbing'
    }

    const handleMouseMove = (e: MouseEvent) => {
      if (dragRef.current) {
        const dx = e.clientX - dragRef.current.startX
        const dy = e.clientY - dragRef.current.startY
        const { west, east, south, north } = dragRef.current.startBounds
        const lonPerPx = (east - west) / canvas.width
        const latPerPx = (north - south) / canvas.height

        updateBounds(
          west - dx * lonPerPx,
          south + dy * latPerPx,
          east - dx * lonPerPx,
          north + dy * latPerPx,
        )
        setTooltip(null)
        return
      }

      // Hit-test for hover tooltip
      if (!particlesRef.current) return
      const rect = canvas.getBoundingClientRect()
      const mx = e.clientX - rect.left
      const my = e.clientY - rect.top
      const hitRadius = 18 // pixels

      let closest: TooltipData | null = null
      let closestDist = hitRadius

      for (const label of ALL_LABELS) {
        const [lx, ly] = particlesRef.current.projectPoint(label.lon, label.lat)
        const dist = Math.sqrt((mx - lx) ** 2 + (my - ly) ** 2)
        if (dist < closestDist) {
          closestDist = dist
          closest = { x: e.clientX - rect.left, y: e.clientY - rect.top, label }
        }
      }
      setTooltip(closest)
      canvas.style.cursor = closest ? 'pointer' : 'grab'
    }

    const handleMouseUp = () => {
      dragRef.current = null
      canvas.style.cursor = 'grab'
    }

    // ── Touch zoom/pan ──
    const getTouchDist = (touches: TouchList) => {
      const dx = touches[0].clientX - touches[1].clientX
      const dy = touches[0].clientY - touches[1].clientY
      return Math.sqrt(dx * dx + dy * dy)
    }

    const handleTouchStart = (e: TouchEvent) => {
      if (e.touches.length === 1) {
        dragRef.current = {
          startX: e.touches[0].clientX,
          startY: e.touches[0].clientY,
          startBounds: { ...boundsRef.current },
        }
      } else if (e.touches.length === 2) {
        e.preventDefault()
        dragRef.current = null
        pinchRef.current = {
          startDist: getTouchDist(e.touches),
          startBounds: { ...boundsRef.current },
        }
      }
    }

    const handleTouchMove = (e: TouchEvent) => {
      if (e.touches.length === 1 && dragRef.current) {
        e.preventDefault()
        const dx = e.touches[0].clientX - dragRef.current.startX
        const dy = e.touches[0].clientY - dragRef.current.startY
        const { west, east, south, north } = dragRef.current.startBounds
        const lonPerPx = (east - west) / canvas.width
        const latPerPx = (north - south) / canvas.height

        updateBounds(
          west - dx * lonPerPx,
          south + dy * latPerPx,
          east - dx * lonPerPx,
          north + dy * latPerPx,
        )
      } else if (e.touches.length === 2 && pinchRef.current) {
        e.preventDefault()
        const dist = getTouchDist(e.touches)
        const scale = pinchRef.current.startDist / dist
        const { west, east, south, north } = pinchRef.current.startBounds
        const cx = (west + east) / 2
        const cy = (south + north) / 2
        const hw = ((east - west) / 2) * scale
        const hh = ((north - south) / 2) * scale

        updateBounds(cx - hw, cy - hh, cx + hw, cy + hh)
      }
    }

    const handleTouchEnd = () => {
      dragRef.current = null
      pinchRef.current = null
    }

    syncSize()
    loadCoastline()
    ps.start()
    canvas.style.cursor = 'grab'

    canvas.addEventListener('wheel', handleWheel, { passive: false })
    canvas.addEventListener('mousedown', handleMouseDown)
    window.addEventListener('mousemove', handleMouseMove)
    window.addEventListener('mouseup', handleMouseUp)
    canvas.addEventListener('touchstart', handleTouchStart, { passive: false })
    canvas.addEventListener('touchmove', handleTouchMove, { passive: false })
    canvas.addEventListener('touchend', handleTouchEnd)
    window.addEventListener('resize', syncSize)

    return () => {
      canvas.removeEventListener('wheel', handleWheel)
      canvas.removeEventListener('mousedown', handleMouseDown)
      window.removeEventListener('mousemove', handleMouseMove)
      window.removeEventListener('mouseup', handleMouseUp)
      canvas.removeEventListener('touchstart', handleTouchStart)
      canvas.removeEventListener('touchmove', handleTouchMove)
      canvas.removeEventListener('touchend', handleTouchEnd)
      window.removeEventListener('resize', syncSize)
      ps.stop()
      ps.clear()
      particlesRef.current = null
      canvasRef.current = null
    }
  }, [updateBounds])

  // Update wind grid on model/timestep change
  useEffect(() => {
    if (!grid || !particlesRef.current) return
    const interpolated = interpolateWindGrid(grid, index)
    if (!interpolated) return
    particlesRef.current.setGrid({
      ...grid,
      timesteps: [{ valid_utc: '', u: interpolated.u, v: interpolated.v }],
    })
  }, [grid, index])

  return (
    <div className="relative w-full h-full" style={{ background: '#060918' }}>
      <div ref={containerRef} className="absolute inset-0" />

      {/* Hover tooltip */}
      {tooltip && (
        <div
          className="absolute z-30 pointer-events-none px-3 py-2 rounded-lg border text-xs whitespace-nowrap"
          style={{
            left: Math.min(tooltip.x + 12, (containerRef.current?.clientWidth ?? 300) - 200),
            top: tooltip.y - 40,
            background: 'rgba(10, 10, 10, 0.92)',
            borderColor: 'var(--color-border)',
            backdropFilter: 'blur(8px)',
          }}
        >
          <p className="font-medium text-[var(--color-text-primary)]">
            {tooltip.label.text}
            {tooltip.label.textZh && <span className="ml-1.5 text-[var(--color-text-muted)]">{tooltip.label.textZh}</span>}
          </p>
          {tooltip.label.type === 'spot' && (
            <div className="mt-1 space-y-0.5 text-[10px] text-[var(--color-text-muted)]">
              <p>Facing <span className="text-[var(--color-text-secondary)]">{tooltip.label.facing}</span>
                {tooltip.label.region && <> &middot; <span className="capitalize">{tooltip.label.region}</span></>}
              </p>
              {tooltip.label.opt_wind && <p>Best wind: <span className="text-[var(--color-text-secondary)]">{tooltip.label.opt_wind.join(', ')}</span></p>}
              {tooltip.label.opt_swell && <p>Best swell: <span className="text-[var(--color-text-secondary)]">{tooltip.label.opt_swell.join(', ')}</span></p>}
            </div>
          )}
          {tooltip.label.type === 'harbour' && (
            <p className="mt-0.5 text-[10px] text-[var(--color-text-muted)]">
              {tooltip.label.lat.toFixed(3)}°N, {tooltip.label.lon.toFixed(3)}°E
            </p>
          )}
        </div>
      )}

      {/* Model switcher */}
      <div className="absolute top-3 right-3 z-20 flex gap-1">
        {(['wrf', 'ecmwf', 'gfs'] as WindModel[]).map(m => (
          <button
            key={m}
            onClick={() => setModel(m)}
            className={`
              px-2 py-1 text-[10px] font-medium rounded-md transition-all
              ${model === m
                ? 'bg-[var(--color-text-primary)] text-[var(--color-bg)]'
                : 'bg-[var(--color-bg-elevated)]/80 text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)]'
              }
              backdrop-blur-sm border border-[var(--color-border)]
            `}
          >
            {MODEL_LABELS[m]}
          </button>
        ))}
      </div>

      {/* Zoom controls */}
      <div className="absolute bottom-14 right-3 z-20 flex flex-col gap-1">
        <button
          onClick={() => {
            const { west, east, south, north } = boundsRef.current
            const cx = (west + east) / 2, cy = (south + north) / 2
            const f = 1 / 1.3
            updateBounds(cx - (cx - west) * f, cy - (cy - south) * f, cx + (east - cx) * f, cy + (north - cy) * f)
          }}
          className="w-7 h-7 flex items-center justify-center rounded-md bg-[var(--color-bg-elevated)]/80 text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] backdrop-blur-sm border border-[var(--color-border)] text-sm font-bold"
        >
          +
        </button>
        <button
          onClick={() => {
            const { west, east, south, north } = boundsRef.current
            const cx = (west + east) / 2, cy = (south + north) / 2
            const f = 1.3
            updateBounds(cx - (cx - west) * f, cy - (cy - south) * f, cx + (east - cx) * f, cy + (north - cy) * f)
          }}
          className="w-7 h-7 flex items-center justify-center rounded-md bg-[var(--color-bg-elevated)]/80 text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] backdrop-blur-sm border border-[var(--color-border)] text-sm font-bold"
        >
          −
        </button>
      </div>
    </div>
  )
}
