import { useRef, useEffect, useCallback, useState } from 'react'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { TAIWAN_CENTER, TAIWAN_ZOOM } from '@/lib/constants'
import { WindParticleSystem } from '@/lib/wind-particles'
import { interpolateWindGrid } from '@/lib/interpolate'
import { useTimeline } from '@/hooks/useTimeline'
import { useWindGrid, type WindModel } from '@/hooks/useWindGrid'
import { SpotMarkers } from './SpotMarkers'

// CartoDB dark-matter — accurate monochrome basemap with real coastlines
const DARK_TILES = 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json'

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
      style: DARK_TILES,
      center: TAIWAN_CENTER,
      zoom: TAIWAN_ZOOM,
      minZoom: 5,
      maxZoom: 12,
      attributionControl: false,
    })

    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-left')
    map.addControl(new maplibregl.AttributionControl({ compact: true }), 'bottom-right')

    map.on('load', async () => {
      // Load Taiwan coastline outline
      try {
        const resp = await fetch('/data/taiwan.geojson')
        if (!resp.ok) throw new Error(`GeoJSON fetch failed: ${resp.status}`)
        const geojson = await resp.json()
        map.addSource('taiwan-outline', { type: 'geojson', data: geojson })

        map.addLayer({
          id: 'taiwan-fill',
          type: 'fill',
          source: 'taiwan-outline',
          paint: {
            'fill-color': '#1e3a5f',
            'fill-opacity': 0.35,
          },
        })

        map.addLayer({
          id: 'taiwan-line',
          type: 'line',
          source: 'taiwan-outline',
          paint: {
            'line-color': '#38bdf8',
            'line-width': 2.5,
            'line-opacity': 1,
          },
        })
        console.log('[ForecastMap] Taiwan outline layers added, source features:',
          (map.getSource('taiwan-outline') as maplibregl.GeoJSONSource)?.serialize?.()?.data ? 'ok' : 'empty'
        )
      } catch (err) {
        console.warn('Taiwan outline not loaded:', err)
      }

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
      {/* MapLibre GL container — handles all touch/drag/zoom natively */}
      <div ref={mapContainerRef} className="absolute inset-0" />

      {/* Wind particle canvas — behind map's interactive layer */}
      <canvas
        ref={canvasRef}
        className="absolute inset-0 pointer-events-none"
        style={{ zIndex: 1, mixBlendMode: 'screen' }}
      />

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
