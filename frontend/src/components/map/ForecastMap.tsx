import { useRef, useEffect, useCallback, useState } from 'react'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { TAIWAN_CENTER, TAIWAN_ZOOM } from '@/lib/constants'
import { WindParticleSystem } from '@/lib/wind-particles'
import { interpolateWindGrid } from '@/lib/interpolate'
import { useTimeline } from '@/hooks/useTimeline'
import { useWindGrid, type WindModel } from '@/hooks/useWindGrid'
import { SpotMarkers } from './SpotMarkers'

// Taiwan coastline as [lon, lat][] rings — drawn directly on the particle canvas
const TAIWAN_COAST: [number, number][] = [
  [120.225,22.57],[120.265,22.54],[120.31,22.53],[120.36,22.51],[120.395,22.485],
  [120.43,22.46],[120.47,22.45],[120.51,22.46],[120.56,22.48],[120.62,22.51],
  [120.68,22.54],[120.72,22.555],[120.76,22.56],[120.81,22.54],[120.85,22.515],
  [120.88,21.98],[120.87,21.94],[120.845,21.92],[120.81,21.91],[120.77,21.91],
  [120.73,21.92],[120.7,21.935],[120.69,21.95],[120.69,21.98],[120.7,22.01],
  [120.74,22.06],[120.78,22.1],[120.82,22.14],[120.855,22.2],[120.87,22.27],
  [120.89,22.35],[120.92,22.43],[120.96,22.5],[121.0,22.57],[121.03,22.64],
  [121.06,22.72],[121.08,22.8],[121.1,22.88],[121.13,22.96],[121.17,23.05],
  [121.21,23.13],[121.25,23.22],[121.29,23.31],[121.32,23.4],[121.36,23.49],
  [121.4,23.57],[121.44,23.64],[121.48,23.72],[121.51,23.8],[121.53,23.87],
  [121.56,23.95],[121.59,24.04],[121.61,24.12],[121.63,24.2],[121.65,24.28],
  [121.68,24.36],[121.72,24.44],[121.76,24.52],[121.8,24.59],[121.83,24.66],
  [121.86,24.74],[121.88,24.81],[121.9,24.87],[121.92,24.94],[121.94,25.01],
  [121.94,25.07],[121.93,25.12],[121.9,25.15],[121.86,25.17],[121.81,25.19],
  [121.77,25.2],[121.73,25.21],[121.68,25.22],[121.64,25.23],[121.59,25.24],
  [121.54,25.26],[121.51,25.27],[121.47,25.28],[121.43,25.28],[121.39,25.27],
  [121.35,25.26],[121.31,25.24],[121.27,25.21],[121.23,25.17],[121.2,25.14],
  [121.18,25.11],[121.15,25.08],[121.12,25.06],[121.06,25.04],[121.01,25.03],
  [120.96,25.02],[120.91,25.01],[120.86,24.99],[120.82,24.96],[120.78,24.93],
  [120.74,24.89],[120.7,24.85],[120.67,24.8],[120.64,24.74],[120.62,24.68],
  [120.6,24.61],[120.58,24.54],[120.56,24.47],[120.54,24.4],[120.53,24.33],
  [120.51,24.26],[120.49,24.19],[120.47,24.12],[120.45,24.05],[120.43,23.98],
  [120.4,23.91],[120.38,23.84],[120.36,23.77],[120.34,23.7],[120.32,23.63],
  [120.3,23.56],[120.28,23.49],[120.26,23.41],[120.25,23.34],[120.24,23.27],
  [120.23,23.2],[120.22,23.13],[120.21,23.06],[120.2,22.99],[120.2,22.92],
  [120.2,22.85],[120.2,22.78],[120.205,22.71],[120.215,22.64],[120.225,22.57],
]
const PENGHU_COAST: [number, number][] = [
  [119.52,23.52],[119.56,23.5],[119.62,23.51],[119.66,23.53],[119.68,23.56],
  [119.67,23.6],[119.64,23.63],[119.6,23.64],[119.56,23.63],[119.53,23.6],
  [119.51,23.56],[119.52,23.52],
]

// Minimal dark style — background only, Taiwan added programmatically on load
const DARK_STYLE: maplibregl.StyleSpecification = {
  version: 8,
  sources: {},
  layers: [
    {
      id: 'background',
      type: 'background',
      paint: { 'background-color': '#0a0a1a' },
    },
  ],
}

const MODEL_LABELS: Record<WindModel, string> = {
  wrf: 'WRF 3km',
  ecmwf: 'ECMWF',
  gfs: 'GFS',
}

export function ForecastMap() {
  const wrapperRef = useRef<HTMLDivElement>(null)
  const mapContainerRef = useRef<HTMLDivElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)
  const particlesRef = useRef<WindParticleSystem | null>(null)
  const [mapReady, setMapReady] = useState(false)

  const { index } = useTimeline()
  const { grid, model, setModel } = useWindGrid()

  // Initialize map
  useEffect(() => {
    if (!mapContainerRef.current) return

    const map = new maplibregl.Map({
      container: mapContainerRef.current,
      style: DARK_STYLE,
      center: TAIWAN_CENTER,
      zoom: TAIWAN_ZOOM,
      minZoom: 5,
      maxZoom: 12,
      attributionControl: false,
    })

    map.addControl(new maplibregl.AttributionControl({ compact: true }), 'bottom-right')

    map.on('load', () => {
      mapRef.current = map
      setMapReady(true)
    })

    return () => {
      mapRef.current = null
      setMapReady(false)
      map.remove()
    }
  }, [])

  // Initialize particle system
  useEffect(() => {
    if (!canvasRef.current) return

    const ps = new WindParticleSystem({
      canvas: canvasRef.current,
      count: window.innerWidth < 768 ? 2000 : 4000,
      maxAge: 80,
      speedFactor: 0.3,
      lineWidth: 1.2,
      fadeFactor: 0.97,
    })

    particlesRef.current = ps
    ps.setCoastlines([TAIWAN_COAST, PENGHU_COAST])
    ps.start()

    return () => {
      ps.stop()
      ps.clear()
      particlesRef.current = null
    }
  }, [])

  // Sync canvas size with wrapper
  const syncSize = useCallback(() => {
    if (!wrapperRef.current || !canvasRef.current) return
    const { clientWidth: w, clientHeight: h } = wrapperRef.current
    canvasRef.current.width = w
    canvasRef.current.height = h
    particlesRef.current?.resize(w, h)
  }, [])

  useEffect(() => {
    syncSize()
    window.addEventListener('resize', syncSize)
    return () => window.removeEventListener('resize', syncSize)
  }, [syncSize])

  // Sync map bounds to particle system
  useEffect(() => {
    const map = mapRef.current
    if (!map || !mapReady) return

    const update = () => {
      const b = map.getBounds()
      particlesRef.current?.setBounds(
        b.getWest(), b.getSouth(), b.getEast(), b.getNorth()
      )
    }

    update()
    map.on('move', update)
    map.on('moveend', syncSize)
    return () => {
      map.off('move', update)
      map.off('moveend', syncSize)
    }
  }, [mapReady, syncSize])

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
    <div ref={wrapperRef} className="relative w-full h-full">
      {/* MapLibre GL container */}
      <div ref={mapContainerRef} className="absolute inset-0 z-0" />

      {/* Wind particle canvas overlay — pointer-events-none lets map receive drag/touch */}
      <canvas
        ref={canvasRef}
        className="absolute inset-0 pointer-events-none"
        style={{ zIndex: 1 }}
      />

      {/* Zoom controls — rendered outside the map so the canvas doesn't cover them */}
      <div className="absolute top-3 left-3 z-20 flex flex-col gap-1">
        <button
          onClick={() => mapRef.current?.zoomIn()}
          className="w-8 h-8 flex items-center justify-center rounded-md text-sm font-bold bg-[var(--color-bg-elevated)]/90 text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] backdrop-blur-sm border border-[var(--color-border)]"
          aria-label="Zoom in"
        >+</button>
        <button
          onClick={() => mapRef.current?.zoomOut()}
          className="w-8 h-8 flex items-center justify-center rounded-md text-sm font-bold bg-[var(--color-bg-elevated)]/90 text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] backdrop-blur-sm border border-[var(--color-border)]"
          aria-label="Zoom out"
        >−</button>
      </div>

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

      {/* Spot markers */}
      <SpotMarkers map={mapReady ? mapRef.current : null} />
    </div>
  )
}
