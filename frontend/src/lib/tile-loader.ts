/**
 * XYZ tile math + image cache for rendering map tile overlays on canvas.
 *
 * Standard Web Mercator (EPSG:3857) tile scheme — same as OpenStreetMap.
 */

/** Convert lon/lat to tile x/y at a given zoom level */
export function lonLatToTile(lon: number, lat: number, zoom: number): { x: number; y: number } {
  const n = 2 ** zoom
  const x = Math.floor(((lon + 180) / 360) * n)
  const latRad = (lat * Math.PI) / 180
  const y = Math.floor((1 - Math.log(Math.tan(latRad) + 1 / Math.cos(latRad)) / Math.PI) / 2 * n)
  return { x, y }
}

/** Get the lat/lon bounds of a tile */
export function tileBounds(x: number, y: number, zoom: number): {
  west: number; east: number; north: number; south: number
} {
  const n = 2 ** zoom
  const west = (x / n) * 360 - 180
  const east = ((x + 1) / n) * 360 - 180
  const north = tileLatFromY(y, n)
  const south = tileLatFromY(y + 1, n)
  return { west, east, north, south }
}

function tileLatFromY(y: number, n: number): number {
  const mercN = Math.PI - (2 * Math.PI * y) / n
  return (180 / Math.PI) * Math.atan(0.5 * (Math.exp(mercN) - Math.exp(-mercN)))
}

/** Choose an appropriate zoom level for a given viewport longitude span */
export function zoomForSpan(lonSpan: number): number {
  // At zoom z, the world is 2^z tiles of 360/2^z degrees each
  const z = Math.round(Math.log2(360 / lonSpan))
  return Math.max(3, Math.min(z, 12))
}

/** Get all tile coordinates that intersect a viewport */
export function tilesInView(
  west: number, south: number, east: number, north: number, zoom: number
): Array<{ x: number; y: number }> {
  const tl = lonLatToTile(west, north, zoom)
  const br = lonLatToTile(east, south, zoom)
  const tiles: Array<{ x: number; y: number }> = []
  for (let y = tl.y; y <= br.y; y++) {
    for (let x = tl.x; x <= br.x; x++) {
      tiles.push({ x, y })
    }
  }
  return tiles
}

/**
 * Simple image cache for tile PNGs.
 * Keyed by full URL. Evicts oldest entries when capacity exceeded.
 */
export class TileCache {
  private cache = new Map<string, HTMLImageElement>()
  private capacity: number

  constructor(capacity = 128) {
    this.capacity = capacity
  }

  get(url: string): HTMLImageElement | undefined {
    return this.cache.get(url)
  }

  /** Load a tile image, returning from cache if available */
  load(url: string): Promise<HTMLImageElement> {
    const cached = this.cache.get(url)
    if (cached) return Promise.resolve(cached)

    return new Promise((resolve, reject) => {
      const img = new Image()
      img.crossOrigin = 'anonymous'
      img.onload = () => {
        // Evict oldest if at capacity
        if (this.cache.size >= this.capacity) {
          const first = this.cache.keys().next().value
          if (first) this.cache.delete(first)
        }
        this.cache.set(url, img)
        resolve(img)
      }
      img.onerror = () => reject(new Error(`Failed to load tile: ${url}`))
      img.src = url
    })
  }

  clear() {
    this.cache.clear()
  }
}
