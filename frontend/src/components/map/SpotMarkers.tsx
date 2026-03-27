import { useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import maplibregl from 'maplibre-gl'
import { SPOTS, HARBOURS } from '@/lib/constants'

interface SpotMarkersProps {
  map: maplibregl.Map | null
}

export function SpotMarkers({ map }: SpotMarkersProps) {
  const { i18n } = useTranslation()
  const navigate = useNavigate()
  const markersRef = useRef<maplibregl.Marker[]>([])

  useEffect(() => {
    if (!map) return

    // Remove existing markers
    markersRef.current.forEach(m => m.remove())
    markersRef.current = []

    const lang = i18n.language.startsWith('zh') ? 'zh' : 'en'

    // Surf spot markers (circles)
    for (const spot of SPOTS) {
      const el = document.createElement('div')
      el.className = 'spot-marker'
      el.style.cssText = `
        width: 10px; height: 10px; border-radius: 50%;
        background: #a0a0a0; border: 1.5px solid #f5f5f5;
        cursor: pointer; transition: transform 0.15s;
      `
      el.addEventListener('mouseenter', () => { el.style.transform = 'scale(1.5)' })
      el.addEventListener('mouseleave', () => { el.style.transform = 'scale(1)' })

      const popup = new maplibregl.Popup({
        offset: 12, closeButton: false, closeOnClick: true,
        className: 'spot-popup',
      }).setHTML(`
        <div style="font-family:Inter,sans-serif; font-size:12px; color:#f5f5f5; background:#111; padding:6px 10px; border-radius:8px; border:1px solid #222;">
          <div style="font-weight:600; margin-bottom:2px;">${spot.name[lang]}</div>
          <div style="color:#888; font-size:10px;">${spot.facing} facing</div>
        </div>
      `)

      const marker = new maplibregl.Marker({ element: el })
        .setLngLat([spot.lon, spot.lat])
        .setPopup(popup)
        .addTo(map)

      el.addEventListener('click', () => {
        navigate(`/spots/${spot.id}`)
      })

      markersRef.current.push(marker)
    }

    // Harbour markers (diamonds)
    for (const harbour of HARBOURS) {
      const el = document.createElement('div')
      el.style.cssText = `
        width: 8px; height: 8px; border-radius: 2px; transform: rotate(45deg);
        background: #5b9bd5; border: 1.5px solid #f5f5f5;
        cursor: pointer; transition: transform 0.15s;
      `
      el.addEventListener('mouseenter', () => { el.style.transform = 'rotate(45deg) scale(1.5)' })
      el.addEventListener('mouseleave', () => { el.style.transform = 'rotate(45deg) scale(1)' })

      const popup = new maplibregl.Popup({
        offset: 12, closeButton: false, closeOnClick: true,
        className: 'spot-popup',
      }).setHTML(`
        <div style="font-family:Inter,sans-serif; font-size:12px; color:#f5f5f5; background:#111; padding:6px 10px; border-radius:8px; border:1px solid #222;">
          <div style="font-weight:600;">${harbour.name[lang]}</div>
          <div style="color:#888; font-size:10px;">Harbour</div>
        </div>
      `)

      const marker = new maplibregl.Marker({ element: el })
        .setLngLat([harbour.lon, harbour.lat])
        .setPopup(popup)
        .addTo(map)

      el.addEventListener('click', () => {
        navigate(`/harbours`)
      })

      markersRef.current.push(marker)
    }

    return () => {
      markersRef.current.forEach(m => m.remove())
      markersRef.current = []
    }
  }, [map, i18n.language, navigate])

  return null
}
