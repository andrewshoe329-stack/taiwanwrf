import { useRef, useEffect, useCallback, useMemo, useState } from 'react'
import { TAIWAN_BBOX, SPOTS, HARBOURS, DATA_FILES } from '@/lib/constants'
import { WindParticleSystem } from '@/lib/wind-particles'
import { interpolateWindGrid } from '@/lib/interpolate'
import { useTimeline } from '@/hooks/useTimeline'
import { useModel, type WindModel } from '@/hooks/useModel'
import { useForecastData } from '@/hooks/useForecastData'
import type { SpotRating, WaveGrid } from '@/lib/types'

type MapLayer = 'wind' | 'waves'

const MODEL_LABELS: Record<WindModel, string> = {
  wrf: 'WRF 3km',
  ecmwf: 'ECMWF',
  gfs: 'GFS',
}

// Zoom limits (degrees of longitude span)
const MIN_LON_SPAN = 0.5   // max zoom in (was 0.3 — too close causes distortion)
const MAX_LON_SPAN = TAIWAN_BBOX.lon_max - TAIWAN_BBOX.lon_min  // max zoom out = initial view

// Pin label colors: muted by default, brighter when selected
const PIN_COLOR_DEFAULT = '#9ca3af'
const PIN_COLOR_SELECTED = '#f5f5f5'

interface MapLabel {
  lon: number
  lat: number
  text: string
  textZh?: string
  type: 'spot' | 'harbour' | 'city'
  id?: string
}

// Build label list once
const ALL_LABELS: MapLabel[] = [
  ...SPOTS.map(s => ({
    lon: s.lon, lat: s.lat, text: s.name.en, textZh: s.name.zh,
    type: 'spot' as const, id: s.id,
  })),
  ...HARBOURS.map(h => ({
    lon: h.lon, lat: h.lat, text: h.name.en, textZh: h.name.zh,
    type: 'harbour' as const, id: h.id,
  })),
  { lon: 121.565, lat: 25.033, text: 'Taipei', type: 'city' },
  { lon: 121.817, lat: 24.760, text: 'Yilan', type: 'city' },
]

interface ForecastMapProps {
  selectedId?: string | null
  onSelectLocation?: (id: string) => void
}

/**
 * Canvas-only forecast map with zoom/pan, hover tooltips, and tap-to-select.
 * Renders: ocean background, land fill + coastline, wind particles, spot labels.
 */
export function ForecastMap({ selectedId, onSelectLocation }: ForecastMapProps) {
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
  // Tap detection: track mousedown/touchstart position
  const tapStartRef = useRef<{ x: number; y: number } | null>(null)

  const { index } = useTimeline()
  const { grid, model, setModel } = useModel()
  const data = useForecastData()
  const [layer, setLayer] = useState<MapLayer>('wind')
  const waveGridRef = useRef<WaveGrid | null>(null)

  // Load wave grid data once
  useEffect(() => {
    fetch(DATA_FILES.wave_grid)
      .then(r => r.ok ? r.json() : null)
      .then(d => { waveGridRef.current = d })
      .catch(() => {})
  }, [])

  // Current valid_utc from the keelung timeline
  const currentUtc = data.keelung?.records?.[index]?.valid_utc

  // Build a map of spot_id → closest SpotRating for the current timestep
  const spotWeather = useMemo(() => {
    const map = new Map<string, SpotRating>()
    if (!currentUtc || !data.surf?.spots) return map
    const targetMs = new Date(currentUtc).getTime()
    for (const sf of data.surf.spots) {
      let best: SpotRating | null = null
      let bestDiff = Infinity
      for (const r of sf.ratings) {
        const diff = Math.abs(new Date(r.valid_utc).getTime() - targetMs)
        if (diff < bestDiff) { bestDiff = diff; best = r }
      }
      if (best) map.set(sf.spot.id, best)
    }
    return map
  }, [currentUtc, data.surf])

  // Pass pin colors to the particle system — highlight selected
  const spotRatingColors = useMemo(() => {
    const colors: Record<string, string> = {}
    for (const [id] of spotWeather) {
      colors[id] = id === selectedId ? PIN_COLOR_SELECTED : PIN_COLOR_DEFAULT
    }
    return colors
  }, [spotWeather, selectedId])

  useEffect(() => {
    particlesRef.current?.setLabelColors(spotRatingColors)
  }, [spotRatingColors])

  useEffect(() => {
    particlesRef.current?.setSelectedId(selectedId ?? null)
  }, [selectedId])

  /** Hit-test labels at canvas position, return label if within radius */
  const hitTestLabel = useCallback((canvasX: number, canvasY: number): MapLabel | null => {
    if (!particlesRef.current) return null
    const hitRadius = 24
    let closest: MapLabel | null = null
    let closestDist = hitRadius

    for (const label of ALL_LABELS) {
      if (label.type === 'city') continue // cities not selectable
      const [lx, ly] = particlesRef.current.projectPoint(label.lon, label.lat)
      const dist = Math.sqrt((canvasX - lx) ** 2 + (canvasY - ly) ** 2)
      if (dist < closestDist) {
        closestDist = dist
        closest = label
      }
    }
    return closest
  }, [])

  const updateBounds = useCallback((west: number, south: number, east: number, north: number) => {
    // Clamp zoom span
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
      // At max zoom out, snap to initial TAIWAN_BBOX
      west = TAIWAN_BBOX.lon_min
      east = TAIWAN_BBOX.lon_max
      south = TAIWAN_BBOX.lat_min
      north = TAIWAN_BBOX.lat_max
    }

    // Clamp pan to stay within TAIWAN_BBOX
    const bboxLon = TAIWAN_BBOX.lon_max - TAIWAN_BBOX.lon_min
    const bboxLat = TAIWAN_BBOX.lat_max - TAIWAN_BBOX.lat_min
    lonSpan = east - west
    latSpan = north - south
    if (lonSpan <= bboxLon) {
      if (west < TAIWAN_BBOX.lon_min) { west = TAIWAN_BBOX.lon_min; east = west + lonSpan }
      if (east > TAIWAN_BBOX.lon_max) { east = TAIWAN_BBOX.lon_max; west = east - lonSpan }
    }
    if (latSpan <= bboxLat) {
      if (south < TAIWAN_BBOX.lat_min) { south = TAIWAN_BBOX.lat_min; north = south + latSpan }
      if (north > TAIWAN_BBOX.lat_max) { north = TAIWAN_BBOX.lat_max; south = north - latSpan }
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
      count: window.innerWidth < 768 ? 1200 : 2500,
      maxAge: 80,
      speedFactor: 0.18,
      lineWidth: 0.8,
      fadeFactor: 0.95,
    })
    particlesRef.current = ps

    const b = boundsRef.current
    ps.setBounds(b.west, b.south, b.east, b.north)

    const syncSize = () => {
      const { clientWidth: w, clientHeight: h } = container
      if (w === 0 || h === 0) return
      ps.resize(w, h)
    }

    const loadCoastline = async () => {
      try {
        const resp = await fetch('/data/taiwan.geojson?v=5')
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

    // ── Mouse drag pan + tap detection ──
    const handleMouseDown = (e: MouseEvent) => {
      if (e.button !== 0) return
      dragRef.current = {
        startX: e.clientX,
        startY: e.clientY,
        startBounds: { ...boundsRef.current },
      }
      tapStartRef.current = { x: e.clientX, y: e.clientY }
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
        return
      }

      canvas.style.cursor = 'grab'
    }

    const handleMouseUp = (e: MouseEvent) => {
      // Tap detection: if movement < 6px, treat as click
      if (tapStartRef.current && onSelectLocation) {
        const dx = e.clientX - tapStartRef.current.x
        const dy = e.clientY - tapStartRef.current.y
        if (Math.sqrt(dx * dx + dy * dy) < 6) {
          const rect = canvas.getBoundingClientRect()
          const cx = e.clientX - rect.left
          const cy = e.clientY - rect.top
          const hit = hitTestLabel(cx, cy)
          if (hit?.id) {
            onSelectLocation(hit.id)
          }
        }
      }
      dragRef.current = null
      tapStartRef.current = null
      canvas.style.cursor = 'grab'
    }

    // ── Touch zoom/pan + tap detection ──
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
        tapStartRef.current = { x: e.touches[0].clientX, y: e.touches[0].clientY }
      } else if (e.touches.length === 2) {
        e.preventDefault()
        dragRef.current = null
        tapStartRef.current = null
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

    const handleTouchEnd = (e: TouchEvent) => {
      // Tap detection for touch
      if (tapStartRef.current && onSelectLocation && e.changedTouches.length > 0) {
        const touch = e.changedTouches[0]
        const dx = touch.clientX - tapStartRef.current.x
        const dy = touch.clientY - tapStartRef.current.y
        if (Math.sqrt(dx * dx + dy * dy) < 6) {
          const rect = canvas.getBoundingClientRect()
          const cx = touch.clientX - rect.left
          const cy = touch.clientY - rect.top
          const hit = hitTestLabel(cx, cy)
          if (hit?.id) {
            onSelectLocation(hit.id)
          }
        }
      }
      dragRef.current = null
      tapStartRef.current = null
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
  }, [updateBounds, hitTestLabel])

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

  // Update wave mode + wave grid on layer/timestep change
  useEffect(() => {
    const ps = particlesRef.current
    if (!ps) return
    ps.setWaveMode(layer === 'waves')
    if (layer === 'waves' && waveGridRef.current) {
      ps.setWaveGrid(waveGridRef.current)
      // Map timeline index to wave grid timestep (wave grid may have different count)
      const waveSteps = waveGridRef.current.timesteps.length
      const windSteps = data.keelung?.records?.length ?? waveSteps
      const waveIdx = Math.min(Math.round(index * waveSteps / Math.max(windSteps, 1)), waveSteps - 1)
      ps.setWaveTimestep(waveIdx)
    }
  }, [layer, index, data.keelung])

  return (
    <div className="relative w-full h-full" style={{ background: '#000000' }}>
      <div ref={containerRef} className="absolute inset-0" />

      {/* Layer toggle (Wind / Waves) */}
      <div className="absolute top-3 left-3 z-20 flex gap-0.5 rounded-md overflow-hidden border border-[var(--color-border)] backdrop-blur-sm">
        {(['wind', 'waves'] as MapLayer[]).map(l => (
          <button
            key={l}
            onClick={() => setLayer(l)}
            className={`
              px-2 py-1 text-[10px] font-medium transition-all
              ${layer === l
                ? 'bg-[var(--color-text-primary)] text-[var(--color-bg)]'
                : 'bg-[var(--color-bg-elevated)]/80 text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)]'
              }
            `}
          >
            {l === 'wind' ? 'Wind' : 'Waves'}
          </button>
        ))}
      </div>

      {/* Model switcher (only visible in wind mode) */}
      <div className={`absolute top-3 right-3 z-20 flex gap-1 ${layer !== 'wind' ? 'opacity-30 pointer-events-none' : ''}`}>
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
      <div className="absolute top-14 right-3 z-20 flex flex-col gap-1">
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
      {/* Wave height legend (only in wave mode) */}
      {layer === 'waves' && (
        <div className="absolute bottom-3 left-3 z-20 backdrop-blur-sm bg-[var(--color-bg-elevated)]/80 border border-[var(--color-border)] rounded-md px-2 py-1.5">
          <p className="text-[8px] text-[var(--color-text-muted)] uppercase tracking-wider mb-1">Wave Height</p>
          <div className="flex items-center gap-0.5">
            {[
              { color: '#1e3a5f', label: '0' },
              { color: '#1a6b8a', label: '' },
              { color: '#2d9a4e', label: '1' },
              { color: '#7ab648', label: '' },
              { color: '#c9a832', label: '2' },
              { color: '#d4682a', label: '' },
              { color: '#c93030', label: '3m+' },
            ].map((s, i) => (
              <div key={i} className="flex flex-col items-center">
                <div className="w-4 h-2 rounded-sm" style={{ backgroundColor: s.color }} />
                {s.label && <span className="text-[7px] text-[var(--color-text-dim)] mt-0.5">{s.label}</span>}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
