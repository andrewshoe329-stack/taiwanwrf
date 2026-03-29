import { useRef, useEffect, useState } from 'react'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { TAIWAN_CENTER, TAIWAN_ZOOM, SPOTS, HARBOURS } from '@/lib/constants'
import { WindParticleSystem } from '@/lib/wind-particles'
import { interpolateWindGrid } from '@/lib/interpolate'
import { useTimeline } from '@/hooks/useTimeline'
import { useWindGrid, type WindModel } from '@/hooks/useWindGrid'
import { SpotMarkers } from './SpotMarkers'

const DARK_TILES = 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json'

const MODEL_LABELS: Record<WindModel, string> = {
  wrf: 'WRF 3km',
  ecmwf: 'ECMWF',
  gfs: 'GFS',
}

export function ForecastMap() {
  const wrapperRef = useRef<HTMLDivElement>(null)
  const mapContainerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)
  const particlesRef = useRef<WindParticleSystem | null>(null)
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const [mapReady, setMapReady] = useState(false)

  const { index } = useTimeline()
  const { grid, model, setModel } = useWindGrid()

  // Initialize map + particle canvas inside the map container
  useEffect(() => {
    if (!mapContainerRef.current) return

    const map = new maplibregl.Map({
      container: mapContainerRef.current,
      style: DARK_TILES,
      center: TAIWAN_CENTER,
      zoom: TAIWAN_ZOOM,
      minZoom: 5,
      maxZoom: 12,
      attributionControl: false,
    })

    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-left')
    map.addControl(new maplibregl.AttributionControl({ compact: true }), 'bottom-right')

    // Create particle canvas INSIDE the map container
    // z-index 1 = above basemap canvas, below controls (z-2) and markers (z-5)
    const canvas = document.createElement('canvas')
    canvas.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;pointer-events:none;z-index:1;'
    mapContainerRef.current.appendChild(canvas)
    canvasRef.current = canvas

    // Init particle system
    const ps = new WindParticleSystem({
      canvas,
      count: window.innerWidth < 768 ? 2000 : 4000,
      maxAge: 80,
      speedFactor: 0.3,
      lineWidth: 1.2,
      fadeFactor: 0.97,
    })
    particlesRef.current = ps
    ps.start()

    // Size canvas to container
    const syncSize = () => {
      if (!mapContainerRef.current) return
      const { clientWidth: w, clientHeight: h } = mapContainerRef.current
      canvas.width = w
      canvas.height = h
      ps.resize(w, h)
    }
    syncSize()
    window.addEventListener('resize', syncSize)

    // Sync map bounds to particle system
    const syncBounds = () => {
      const b = map.getBounds()
      ps.setBounds(b.getWest(), b.getSouth(), b.getEast(), b.getNorth())
    }

    map.on('load', async () => {
      // Load Taiwan coastline
      try {
        const resp = await fetch('/data/taiwan.geojson?v=2')
        if (!resp.ok) throw new Error(`GeoJSON fetch failed: ${resp.status}`)
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

        // Location labels
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
        console.log('[ForecastMap] Coastline:', rings.length, 'rings,', labels.length, 'labels')
      } catch (err) {
        console.warn('[ForecastMap] Coastline failed:', err)
      }

      syncBounds()
      mapRef.current = map
      setMapReady(true)
    })

    map.on('move', syncBounds)
    map.on('moveend', syncSize)

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
    <div ref={wrapperRef} className="relative w-full h-full">
      {/* MapLibre container — canvas is appended inside via useEffect */}
      <div ref={mapContainerRef} className="absolute inset-0" />

      {/* Model switcher — z-20 to float above everything */}
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
