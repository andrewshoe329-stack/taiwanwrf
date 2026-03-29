import { useRef, useEffect } from 'react'
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

/**
 * Canvas-only forecast map. No WebGL / MapLibre dependency.
 * Renders: ocean background, land fill + coastline, wind particles, spot labels.
 */
export function ForecastMap() {
  const containerRef = useRef<HTMLDivElement>(null)
  const particlesRef = useRef<WindParticleSystem | null>(null)
  const canvasRef = useRef<HTMLCanvasElement | null>(null)

  const { index } = useTimeline()
  const { grid, model, setModel } = useWindGrid()

  useEffect(() => {
    if (!containerRef.current) return
    const container = containerRef.current

    // Create canvas filling the container
    const canvas = document.createElement('canvas')
    canvas.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;'
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

    // Set fixed bounds covering northern Taiwan
    ps.setBounds(TAIWAN_BBOX.lon_min, TAIWAN_BBOX.lat_min, TAIWAN_BBOX.lon_max, TAIWAN_BBOX.lat_max)

    const syncSize = () => {
      const { clientWidth: w, clientHeight: h } = container
      if (w === 0 || h === 0) return
      canvas.width = w
      canvas.height = h
      ps.resize(w, h)
    }

    // Load coastline
    const loadCoastline = async () => {
      try {
        const resp = await fetch('/data/taiwan.geojson?v=3')
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

      // Labels for spots, harbours, and cities
      const labels: { lon: number; lat: number; text: string; type: 'spot' | 'harbour' | 'city' }[] = []
      for (const spot of SPOTS) {
        labels.push({ lon: spot.lon, lat: spot.lat, text: spot.name.en, type: 'spot' })
      }
      for (const h of HARBOURS) {
        labels.push({ lon: h.lon, lat: h.lat, text: h.name.en, type: 'harbour' })
      }
      labels.push({ lon: 121.565, lat: 25.033, text: 'Taipei', type: 'city' })
      labels.push({ lon: 121.817, lat: 24.760, text: 'Yilan', type: 'city' })
      ps.setLabels(labels)
    }

    syncSize()
    loadCoastline()
    ps.start()

    window.addEventListener('resize', syncSize)
    return () => {
      window.removeEventListener('resize', syncSize)
      ps.stop()
      ps.clear()
      particlesRef.current = null
      canvasRef.current = null
    }
  }, [])

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
    </div>
  )
}
