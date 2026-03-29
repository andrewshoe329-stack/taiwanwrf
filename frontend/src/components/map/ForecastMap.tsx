import { useRef, useEffect, useState } from 'react'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { TAIWAN_CENTER, TAIWAN_ZOOM, SPOTS, HARBOURS } from '@/lib/constants'
import { WindParticleSystem } from '@/lib/wind-particles'
import { interpolateWindGrid } from '@/lib/interpolate'
import { useTimeline } from '@/hooks/useTimeline'
import { useWindGrid, type WindModel } from '@/hooks/useWindGrid'
import { SpotMarkers } from './SpotMarkers'

// Inline dark style — no external tile service needed
const DARK_STYLE: maplibregl.StyleSpecification = {
  version: 8,
  sources: {
    land: {
      type: 'geojson',
      data: '/data/taiwan.geojson?v=3',
    },
  },
  layers: [
    {
      id: 'background',
      type: 'background',
      paint: { 'background-color': '#0a0a1a' },
    },
    {
      id: 'land-fill',
      type: 'fill',
      source: 'land',
      paint: { 'fill-color': '#1a1a2e', 'fill-opacity': 0.6 },
    },
    {
      id: 'land-outline',
      type: 'line',
      source: 'land',
      paint: { 'line-color': '#334155', 'line-width': 1 },
    },
  ],
}

const MODEL_LABELS: Record<WindModel, string> = {
  wrf: 'WRF 3km',
  ecmwf: 'ECMWF',
  gfs: 'GFS',
}

export function ForecastMap() {
  const mapContainerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)
  const particlesRef = useRef<WindParticleSystem | null>(null)
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const [mapReady, setMapReady] = useState(false)

  const { index } = useTimeline()
  const { grid, model, setModel } = useWindGrid()

  useEffect(() => {
    if (!mapContainerRef.current) return

    const container = mapContainerRef.current

    // Create map
    const map = new maplibregl.Map({
      container,
      style: DARK_STYLE,
      center: TAIWAN_CENTER,
      zoom: TAIWAN_ZOOM,
      minZoom: 5,
      maxZoom: 12,
      attributionControl: false,
    })

    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-left')
    map.addControl(new maplibregl.AttributionControl({ compact: true }), 'bottom-right')

    // Log map errors so we can debug
    map.on('error', (e) => {
      console.warn('[ForecastMap] Map error:', e.error?.message ?? e)
    })

    // Create particle canvas INSIDE the map container
    const canvas = document.createElement('canvas')
    canvas.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;pointer-events:none;z-index:1;'
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

    const syncSize = () => {
      const { clientWidth: w, clientHeight: h } = container
      if (w === 0 || h === 0) return
      canvas.width = w
      canvas.height = h
      ps.resize(w, h)
    }

    const syncBounds = () => {
      const b = map.getBounds()
      ps.setBounds(b.getWest(), b.getSouth(), b.getEast(), b.getNorth())
    }

    // Load coastline + labels immediately (don't wait for map style)
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

      // Labels (always set, independent of geojson)
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

    // Initialize everything without waiting for map style to load
    syncSize()
    syncBounds()
    loadCoastline()
    ps.start()

    // Mark map ready immediately so markers render
    mapRef.current = map
    setMapReady(true)

    // Keep canvas in sync with map
    map.on('move', syncBounds)
    map.on('moveend', syncSize)
    window.addEventListener('resize', syncSize)

    return () => {
      window.removeEventListener('resize', syncSize)
      ps.stop()
      ps.clear()
      particlesRef.current = null
      canvasRef.current = null
      mapRef.current = null
      setMapReady(false)
      map.remove()
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
    <div className="relative w-full h-full" style={{ background: '#0a0a1a' }}>
      {/* MapLibre container */}
      <div ref={mapContainerRef} className="absolute inset-0" />

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
