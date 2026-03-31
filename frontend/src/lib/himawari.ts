/**
 * NICT Himawari-9 satellite tile integration.
 *
 * Himawari-9 is a geostationary satellite at 140.7°E, providing full-disk
 * imagery of the Asia-Pacific region every 10 minutes.
 *
 * Tile URL pattern (via our proxy to avoid CORS):
 *   /api/himawari?q=tile&band=INFRARED_FULL&z=8&x=2&y=2&time=20260331120000
 *
 * The full-disk image uses orthographic (geostationary) projection, not Web
 * Mercator. This module handles the projection math to map tile pixels onto
 * our Mercator canvas.
 *
 * Source: https://himawari8.nict.go.jp/
 * Non-commercial use only.
 */

const SUBLON_DEG = 140.7 // Himawari-9 subsatellite longitude
const SUBLON = (SUBLON_DEG * Math.PI) / 180
const TILE_PX = 550

export type HimawariBand = 'INFRARED_FULL' | 'D531106'
export type HimawariBandMode = 'auto' | 'ir' | 'vis'

const REFRESH_MS = 5 * 60 * 1000 // poll latest every 5 min
const bandCache = new Map<string, { date: Date; fetchedAt: number }>()

// --- Geostationary projection math ---

/** Convert lat/lon (degrees) to normalized disk coordinates [-1, 1] */
function geoToDisk(
  latDeg: number,
  lonDeg: number
): { x: number; y: number } | null {
  const lat = (latDeg * Math.PI) / 180
  const lon = (lonDeg * Math.PI) / 180
  const x = Math.cos(lat) * Math.sin(lon - SUBLON)
  const y = Math.sin(lat)
  // Check if point is on visible disk
  const z = Math.cos(lat) * Math.cos(lon - SUBLON)
  if (z < 0) return null // behind the Earth from satellite's view
  return { x, y }
}

/** Convert normalized disk coordinates to lat/lon (degrees) */
function diskToGeo(
  xn: number,
  yn: number
): { lat: number; lon: number } | null {
  const r2 = xn * xn + yn * yn
  if (r2 > 1) return null // outside Earth disk
  const z = Math.sqrt(1 - r2)
  const lat = Math.asin(yn)
  const lon = SUBLON + Math.atan2(xn, z)
  return { lat: (lat * 180) / Math.PI, lon: (lon * 180) / Math.PI }
}

/** Convert lat/lon to pixel coords in the full-disk image at given zoom */
function geoToPixel(
  latDeg: number,
  lonDeg: number,
  zoom: number
): { px: number; py: number } | null {
  const d = geoToDisk(latDeg, lonDeg)
  if (!d) return null
  const total = zoom * TILE_PX
  const cx = total / 2
  const cy = total / 2
  const radius = total / 2
  return {
    px: cx + d.x * radius,
    py: cy - d.y * radius, // y is flipped (image y goes down)
  }
}

/** Get geographic bounds of a Himawari tile (4 corners → bounding box) */
export function himawariTileBounds(
  tx: number,
  ty: number,
  zoom: number
): { west: number; east: number; north: number; south: number } | null {
  const total = zoom * TILE_PX
  const radius = total / 2
  const cx = total / 2
  const cy = total / 2

  // Sample multiple points along tile edges for better bounds
  const lats: number[] = []
  const lons: number[] = []
  const steps = 8

  for (let i = 0; i <= steps; i++) {
    const frac = i / steps
    // Top edge
    addPoint(tx * TILE_PX + frac * TILE_PX, ty * TILE_PX)
    // Bottom edge
    addPoint(tx * TILE_PX + frac * TILE_PX, (ty + 1) * TILE_PX)
    // Left edge
    addPoint(tx * TILE_PX, ty * TILE_PX + frac * TILE_PX)
    // Right edge
    addPoint((tx + 1) * TILE_PX, ty * TILE_PX + frac * TILE_PX)
  }

  function addPoint(px: number, py: number) {
    const xn = (px - cx) / radius
    const yn = -(py - cy) / radius
    const geo = diskToGeo(xn, yn)
    if (geo) {
      lats.push(geo.lat)
      lons.push(geo.lon)
    }
  }

  if (lats.length < 4) return null // tile is mostly off-disk

  return {
    west: Math.min(...lons),
    east: Math.max(...lons),
    south: Math.min(...lats),
    north: Math.max(...lats),
  }
}

/** Determine which Himawari tiles overlap a viewport */
export function himawariTilesForBounds(
  west: number,
  south: number,
  east: number,
  north: number,
  zoom: number
): Array<{ x: number; y: number }> {
  // Project viewport corners to pixel coords
  const corners = [
    geoToPixel(north, west, zoom),
    geoToPixel(north, east, zoom),
    geoToPixel(south, west, zoom),
    geoToPixel(south, east, zoom),
    geoToPixel((north + south) / 2, (west + east) / 2, zoom), // center
  ]

  const validPx = corners.filter((c): c is { px: number; py: number } => c != null)
  if (!validPx.length) return []

  const minPx = Math.min(...validPx.map((c) => c.px))
  const maxPx = Math.max(...validPx.map((c) => c.px))
  const minPy = Math.min(...validPx.map((c) => c.py))
  const maxPy = Math.max(...validPx.map((c) => c.py))

  const tx0 = Math.max(0, Math.floor(minPx / TILE_PX))
  const tx1 = Math.min(zoom - 1, Math.floor(maxPx / TILE_PX))
  const ty0 = Math.max(0, Math.floor(minPy / TILE_PX))
  const ty1 = Math.min(zoom - 1, Math.floor(maxPy / TILE_PX))

  const tiles: Array<{ x: number; y: number }> = []
  for (let ty = ty0; ty <= ty1; ty++) {
    for (let tx = tx0; tx <= tx1; tx++) {
      tiles.push({ x: tx, y: ty })
    }
  }
  return tiles
}

// --- API layer ---

export interface HimawariLatest {
  date: Date
  source: 'nict' | 'jma'
  /** JMA-specific fields for regional image fallback */
  jmaBand?: string
  hhmm?: string
}

const latestCache = new Map<string, { data: HimawariLatest; fetchedAt: number }>()
const latestInflight = new Map<string, Promise<HimawariLatest>>()

/** Fetch the latest available Himawari timestamp (cached 5 min, per band) */
export async function fetchHimawariLatest(band: HimawariBand = 'INFRARED_FULL'): Promise<HimawariLatest> {
  const lc = latestCache.get(band)
  if (lc && Date.now() - lc.fetchedAt < REFRESH_MS) {
    return lc.data
  }
  const existing = latestInflight.get(band)
  if (existing) return existing

  const promise = (async () => {
    try {
      const resp = await fetch(`/api/himawari?q=latest&band=${band}`)
      if (!resp.ok) throw new Error(`Himawari API ${resp.status}`)
      const json = await resp.json()
      const data: HimawariLatest = {
        date: new Date(json.date),
        source: json.source || 'nict',
        jmaBand: json.jmaBand,
        hhmm: json.hhmm,
      }
      latestCache.set(band, { data, fetchedAt: Date.now() })
      // Also update legacy bandCache for backward compat
      bandCache.set(band, { date: data.date, fetchedAt: Date.now() })
      return data
    } finally {
      latestInflight.delete(band)
    }
  })()

  latestInflight.set(band, promise)
  return promise
}

/** Build URL for JMA MSC regional image (fallback) */
export function jmaRegionalUrl(jmaBand: string, hhmm: string, band: string): string {
  return `/api/himawari?q=regional&band=${band}&jmaBand=${jmaBand}&hhmm=${hhmm}`
}

/** Geographic bounds of JMA MSC SE2 (Southeast Asia 2) region image */
export const JMA_SE2_BOUNDS = {
  north: 50,
  south: 0,
  west: 90,
  east: 150,
}

/**
 * Determine the appropriate Himawari band based on mode and current time.
 * Auto mode uses visible (D531106) during Taiwan daytime (~06:30-17:30 CST),
 * infrared otherwise.
 */
export function resolveHimawariBand(mode: HimawariBandMode): HimawariBand {
  if (mode === 'ir') return 'INFRARED_FULL'
  if (mode === 'vis') return 'D531106'
  // Auto: check current time in CST (UTC+8)
  const now = new Date()
  const cstHour = (now.getUTCHours() + 8) % 24
  const cstMin = now.getUTCMinutes()
  const cstTime = cstHour + cstMin / 60
  // Visible is usable roughly 06:30 to 17:30 CST
  return (cstTime >= 6.5 && cstTime < 17.5) ? 'D531106' : 'INFRARED_FULL'
}

/** Format a Date as the time string used in NICT tile URLs (YYYYMMDDHHMMSS) */
export function formatHimawariTime(date: Date): string {
  const pad = (n: number) => n.toString().padStart(2, '0')
  return (
    date.getUTCFullYear().toString() +
    pad(date.getUTCMonth() + 1) +
    pad(date.getUTCDate()) +
    pad(date.getUTCHours()) +
    pad(date.getUTCMinutes()) +
    pad(date.getUTCSeconds())
  )
}

/** Build the proxy URL for a Himawari tile */
export function himawariTileUrl(
  band: string,
  zoom: number,
  tx: number,
  ty: number,
  time: string
): string {
  return `/api/himawari?q=tile&band=${band}&z=${zoom}&x=${tx}&y=${ty}&time=${time}`
}

/** Recommended zoom level for a given viewport longitude span */
export function himawariZoomForSpan(lonSpan: number): number {
  // Full disk covers ~160° of visible longitude
  // At zoom N, each tile covers ~160/N degrees
  // We want ~2-4 tiles across our viewport for good resolution
  if (lonSpan > 30) return 4
  if (lonSpan > 10) return 8
  return 16
}
