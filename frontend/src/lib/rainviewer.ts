/**
 * RainViewer API integration.
 *
 * Fetches available radar + satellite tile paths from the public API.
 * Free, no API key required. Updates every ~5-10 minutes.
 *
 * Tile URL pattern:
 *   https://tilecache.rainviewer.com{path}/256/{z}/{x}/{y}/2/1_1.png
 *
 * See: https://www.rainviewer.com/api/weather-maps-api.html
 */

const MAPS_URL = 'https://api.rainviewer.com/public/weather-maps.json'
const REFRESH_MS = 5 * 60 * 1000 // 5 minutes

export interface RainViewerFrame {
  time: number  // unix timestamp
  path: string  // tile path prefix
}

export interface RainViewerMaps {
  radar: { past: RainViewerFrame[]; nowcast: RainViewerFrame[] }
  satellite: { infrared: RainViewerFrame[] }
}

let cached: { maps: RainViewerMaps; fetchedAt: number } | null = null
let inflight: Promise<RainViewerMaps> | null = null

/** Fetch the latest RainViewer map metadata (cached for 5 min) */
export async function fetchRainViewerMaps(): Promise<RainViewerMaps> {
  if (cached && Date.now() - cached.fetchedAt < REFRESH_MS) {
    return cached.maps
  }
  if (inflight) return inflight

  inflight = (async () => {
    try {
      const resp = await fetch(MAPS_URL)
      if (!resp.ok) throw new Error(`RainViewer API ${resp.status}`)
      const maps: RainViewerMaps = await resp.json()
      cached = { maps, fetchedAt: Date.now() }
      return maps
    } finally {
      inflight = null
    }
  })()

  return inflight
}

/** Get the latest radar tile path (most recent past frame) */
export function latestRadarPath(maps: RainViewerMaps): RainViewerFrame | null {
  const past = maps.radar?.past
  return past?.length ? past[past.length - 1] : null
}

/** Get the latest satellite tile path */
export function latestSatellitePath(maps: RainViewerMaps): RainViewerFrame | null {
  const ir = maps.satellite?.infrared
  return ir?.length ? ir[ir.length - 1] : null
}

/**
 * Build a tile URL for a given frame and tile coordinates.
 * colorScheme: 1 = original, 2 = universal blue, 4 = dark sky, 8 = TITAN
 * smooth: 0 = raw, 1 = light smooth, 2 = heavy smooth
 */
export function tileUrl(
  frame: RainViewerFrame,
  z: number, x: number, y: number,
  opts: { size?: 256 | 512; colorScheme?: number; smooth?: number } = {}
): string {
  const size = opts.size ?? 256
  const color = opts.colorScheme ?? 2  // universal blue (good on dark bg)
  const smooth = opts.smooth ?? 1
  return `https://tilecache.rainviewer.com${frame.path}/${size}/${z}/${x}/${y}/${color}/${smooth}_1.png`
}

/** Build a satellite tile URL */
export function satelliteTileUrl(
  frame: RainViewerFrame,
  z: number, x: number, y: number,
  size: 256 | 512 = 256
): string {
  return `https://tilecache.rainviewer.com${frame.path}/${size}/${z}/${x}/${y}/0/0_1.png`
}
