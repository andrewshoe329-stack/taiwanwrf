/**
 * Wind particle animation system.
 *
 * Renders flowing particles on a Canvas overlay, driven by a u/v wind grid.
 * Particles move in the direction of the wind, speed proportional to magnitude.
 * Monochrome color ramp: dim for calm, bright white for strong, red for storm.
 */

import type { WindGrid, WaveGrid } from './types'
import { tileBounds, tilesInView } from './tile-loader'

interface Particle {
  x: number
  y: number
  age: number
  maxAge: number
}

export interface WindParticleOptions {
  /** Canvas element to render on */
  canvas: HTMLCanvasElement
  /** Number of particles (default 4000) */
  count?: number
  /** Max particle lifespan in frames (default 80) */
  maxAge?: number
  /** Speed multiplier (default 0.3) */
  speedFactor?: number
  /** Line width (default 1.2) */
  lineWidth?: number
  /** Trail fade factor 0-1 (default 0.97) */
  fadeFactor?: number
}

export class WindParticleSystem {
  private canvas: HTMLCanvasElement
  private ctx: CanvasRenderingContext2D | null
  private particles: Particle[] = []
  private count: number
  private maxAge: number
  private speedFactor: number
  private lineWidth: number
  private fadeFactor: number
  private grid: WindGrid | null = null
  private waveGrid: WaveGrid | null = null
  private waveMode = false
  private waveTimestepIndex = 0
  private tileOverlayMode: 'radar' | 'satellite' | null = null
  private tileImages = new Map<string, HTMLImageElement>()
  private tileOverlayZoom = 0
  private tileOverlayAlpha = 0.7
  private animId: number | null = null
  private running = false
  private offscreen: HTMLCanvasElement | null = null
  private coastline: [number, number][][] = []  // array of rings, each ring is [lon, lat][]
  private labels: { lon: number; lat: number; text: string; textZh?: string; type: 'spot' | 'harbour' | 'city'; id?: string }[] = []
  private labelColors: Record<string, string> = {}  // label id → rating color
  private selectedId: string | null = null
  private lang: 'en' | 'zh' = 'en'

  // Viewport mapping (set by the map component)
  private bounds = { west: 119.0, east: 122.5, south: 21.5, north: 25.5 }
  private boundsChanged = false

  // HiDPI scaling
  private dpr = 1
  private logicalW = 0
  private logicalH = 0

  constructor(opts: WindParticleOptions) {
    this.canvas = opts.canvas
    this.ctx = opts.canvas.getContext('2d')
    this.count = opts.count ?? 4000
    this.maxAge = opts.maxAge ?? 80
    this.speedFactor = opts.speedFactor ?? 0.3
    this.lineWidth = opts.lineWidth ?? 1.2
    this.fadeFactor = opts.fadeFactor ?? 0.97
  }

  /** Set coastline polygons to draw on the canvas (array of [lon,lat][] rings) */
  setCoastline(rings: [number, number][][]) {
    this.coastline = rings
  }

  /** Set location labels to draw on the canvas */
  setLabels(labels: { lon: number; lat: number; text: string; textZh?: string; type: 'spot' | 'harbour' | 'city'; id?: string }[]) {
    this.labels = labels
  }

  /** Set display language for labels */
  setLang(lang: 'en' | 'zh') {
    this.lang = lang
  }

  /** Set per-label rating colors (keyed by label id) */
  setLabelColors(colors: Record<string, string>) {
    this.labelColors = colors
  }

  /** Set selected location id for highlight ring */
  setSelectedId(id: string | null) {
    this.selectedId = id
  }

  /** Set the wind grid data (call when timeline changes) */
  setGrid(grid: WindGrid) {
    this.grid = grid
    if (this.particles.length === 0) this.initParticles()
  }

  /** Set wave grid data for heatmap mode */
  setWaveGrid(waveGrid: WaveGrid | null) {
    this.waveGrid = waveGrid
  }

  /** Enable/disable wave heatmap mode (disables wind particles) */
  setWaveMode(enabled: boolean) {
    this.waveMode = enabled
  }

  /** Set the timestep index for wave heatmap */
  setWaveTimestep(index: number) {
    this.waveTimestepIndex = index
  }

  /** Set tile overlay mode (radar/satellite) and tile images */
  setTileOverlay(mode: 'radar' | 'satellite' | null, images: Map<string, HTMLImageElement>, zoom = 0) {
    this.tileOverlayMode = mode
    this.tileImages = images
    this.tileOverlayZoom = zoom
  }

  /** Update the map viewport bounds (call on map move/zoom) */
  setBounds(west: number, south: number, east: number, north: number) {
    this.bounds = { west, south, east, north }
    this.boundsChanged = true
  }

  /** Get current viewport bounds */
  getBounds() {
    return { ...this.bounds }
  }

  /** Get labels for hit-testing */
  getLabels() {
    return this.labels
  }

  /** Project lon/lat to logical pixel (public for hit-testing) */
  projectPoint(lon: number, lat: number): [number, number] {
    return this.project(lon, lat, this.logicalW, this.logicalH)
  }

  /** Resize canvas to match container (accounts for devicePixelRatio) */
  resize(width: number, height: number) {
    this.dpr = window.devicePixelRatio || 1
    this.logicalW = width
    this.logicalH = height
    this.canvas.width = Math.round(width * this.dpr)
    this.canvas.height = Math.round(height * this.dpr)
  }

  /** Start animation loop */
  start() {
    if (this.running) return
    this.running = true
    this.initParticles()
    this.loop()
  }

  /** Stop animation loop */
  stop() {
    this.running = false
    if (this.animId !== null) {
      cancelAnimationFrame(this.animId)
      this.animId = null
    }
  }

  /** Clear the canvas */
  clear() {
    this.ctx?.clearRect(0, 0, this.canvas.width, this.canvas.height)
  }

  private initParticles() {
    this.particles = Array.from({ length: this.count }, () => this.randomParticle())
  }

  private randomParticle(): Particle {
    return {
      x: Math.random() * this.canvas.width,
      y: Math.random() * this.canvas.height,
      age: Math.floor(Math.random() * this.maxAge),
      maxAge: this.maxAge + Math.floor(Math.random() * 20 - 10),
    }
  }

  /** Bilinear interpolation of wind (u, v) at a given physical canvas pixel */
  private sampleWind(px: number, py: number): [number, number] {
    if (!this.grid) return [0, 0]

    const { west, east, south, north } = this.bounds
    const w = this.canvas.width  // physical pixels
    const h = this.canvas.height

    // Canvas pixel → geographic coords (inverse Mercator)
    const lon = west + (px / w) * (east - west)
    const mercY = (l: number) => Math.log(Math.tan(Math.PI / 4 + (l * Math.PI / 180) / 2))
    const yMin = mercY(south)
    const yMax = mercY(north)
    const mercLat = yMax - (py / h) * (yMax - yMin)
    const lat = (2 * Math.atan(Math.exp(mercLat)) - Math.PI / 2) * 180 / Math.PI

    // Geographic → grid indices
    const { bounds: gb, grid: { nx, ny } } = this.grid
    const gx = ((lon - gb.lon_min) / (gb.lon_max - gb.lon_min)) * (nx - 1)
    const gy = ((gb.lat_max - lat) / (gb.lat_max - gb.lat_min)) * (ny - 1)

    if (gx < 0 || gx >= nx - 1 || gy < 0 || gy >= ny - 1) return [0, 0]

    // Bilinear interpolation
    const i = Math.floor(gx)
    const j = Math.floor(gy)
    const fx = gx - i
    const fy = gy - j

    const ts = this.grid.timesteps[0] // current timestep
    if (!ts) return [0, 0]

    const u00 = ts.u[j]?.[i] ?? 0
    const u10 = ts.u[j]?.[i + 1] ?? 0
    const u01 = ts.u[j + 1]?.[i] ?? 0
    const u11 = ts.u[j + 1]?.[i + 1] ?? 0
    const v00 = ts.v[j]?.[i] ?? 0
    const v10 = ts.v[j]?.[i + 1] ?? 0
    const v01 = ts.v[j + 1]?.[i] ?? 0
    const v11 = ts.v[j + 1]?.[i + 1] ?? 0

    const u = (1 - fx) * (1 - fy) * u00 + fx * (1 - fy) * u10 +
              (1 - fx) * fy * u01 + fx * fy * u11
    const v = (1 - fx) * (1 - fy) * v00 + fx * (1 - fy) * v10 +
              (1 - fx) * fy * v01 + fx * fy * v11

    return [u, v]
  }

  /** Draw wave height heatmap on the canvas */
  private drawWaveHeatmap(ctx: CanvasRenderingContext2D, w: number, h: number) {
    const wg = this.waveGrid
    if (!wg || !wg.timesteps.length) return

    const ti = Math.min(this.waveTimestepIndex, wg.timesteps.length - 1)
    const step = wg.timesteps[ti]
    if (!step?.wave_height) return

    const { lat_min, lat_max, lon_min, lon_max } = wg.bounds
    const ny = wg.grid.ny
    const nx = wg.grid.nx
    const dLat = (lat_max - lat_min) / Math.max(ny - 1, 1)
    const dLon = (lon_max - lon_min) / Math.max(nx - 1, 1)

    for (let yi = 0; yi < ny; yi++) {
      for (let xi = 0; xi < nx; xi++) {
        const hs = step.wave_height[yi]?.[xi]
        if (hs == null) continue

        // Grid cell corners in geo coords
        const cellLonW = lon_min + (xi - 0.5) * dLon
        const cellLonE = lon_min + (xi + 0.5) * dLon
        const cellLatS = lat_min + (yi - 0.5) * dLat
        const cellLatN = lat_min + (yi + 0.5) * dLat

        // Project to canvas
        const [x1, y1] = this.project(cellLonW, cellLatN, w, h)
        const [x2, y2] = this.project(cellLonE, cellLatS, w, h)

        // Skip cells outside viewport
        if (x2 < 0 || x1 > w || y2 < 0 || y1 > h) continue

        // Color ramp: blue (calm) → cyan → green → yellow → red (big)
        const color = this.waveColor(hs)
        ctx.fillStyle = color
        ctx.globalAlpha = 0.45
        ctx.fillRect(x1, y1, x2 - x1, y2 - y1)
      }
    }
    ctx.globalAlpha = 1.0

    // Draw swell direction arrows
    const swellDir = step.swell_direction
    const swellH = step.swell_height
    if (swellDir && swellH) {
      ctx.strokeStyle = 'rgba(255,255,255,0.5)'
      ctx.lineWidth = 1 * this.dpr
      for (let yi = 0; yi < ny; yi++) {
        for (let xi = 0; xi < nx; xi++) {
          const dir = swellDir[yi]?.[xi]
          const sh = swellH[yi]?.[xi]
          if (dir == null || sh == null || sh < 0.2) continue

          const lon = lon_min + xi * dLon
          const lat = lat_min + yi * dLat
          const [cx, cy] = this.project(lon, lat, w, h)
          if (cx < 0 || cx > w || cy < 0 || cy > h) continue

          // Arrow length proportional to swell height (capped)
          const len = Math.min(sh * 8, 20) * this.dpr
          const rad = (dir * Math.PI) / 180
          const dx = Math.sin(rad) * len
          const dy = -Math.cos(rad) * len

          ctx.beginPath()
          ctx.moveTo(cx - dx * 0.5, cy - dy * 0.5)
          ctx.lineTo(cx + dx * 0.5, cy + dy * 0.5)
          ctx.stroke()

          // Arrowhead
          const ax = cx + dx * 0.5
          const ay = cy + dy * 0.5
          const headLen = 4 * this.dpr
          ctx.beginPath()
          ctx.moveTo(ax, ay)
          ctx.lineTo(ax - headLen * Math.sin(rad - 0.5), ay + headLen * Math.cos(rad - 0.5))
          ctx.moveTo(ax, ay)
          ctx.lineTo(ax - headLen * Math.sin(rad + 0.5), ay + headLen * Math.cos(rad + 0.5))
          ctx.stroke()
        }
      }
    }
  }

  /** Draw tile overlay (radar or satellite) on the canvas */
  private drawTileOverlay(ctx: CanvasRenderingContext2D, w: number, h: number) {
    if (!this.tileImages.size || !this.tileOverlayZoom) return

    const { west, east, south, north } = this.bounds
    const zoom = this.tileOverlayZoom
    const tiles = tilesInView(west, south, east, north, zoom)

    ctx.save()
    ctx.globalAlpha = this.tileOverlayAlpha

    for (const tile of tiles) {
      const key = `${zoom}/${tile.x}/${tile.y}`
      const img = this.tileImages.get(key)
      if (!img) continue

      const tb = tileBounds(tile.x, tile.y, zoom)
      const [x1, y1] = this.project(tb.west, tb.north, w, h)
      const [x2, y2] = this.project(tb.east, tb.south, w, h)

      ctx.drawImage(img, x1, y1, x2 - x1, y2 - y1)
    }

    ctx.restore()
  }

  /** Wave height → color (blue calm → red big) */
  private waveColor(hs: number): string {
    if (hs < 0.3) return '#1e3a5f'  // very calm — dark blue
    if (hs < 0.5) return '#1a6b8a'  // calm — teal
    if (hs < 1.0) return '#2d9a4e'  // moderate — green
    if (hs < 1.5) return '#7ab648'  // moderate-high — lime
    if (hs < 2.0) return '#c9a832'  // high — yellow
    if (hs < 3.0) return '#d4682a'  // very high — orange
    return '#c93030'                // extreme — red
  }

  private loop = () => {
    if (!this.running || !this.ctx) return

    const ctx = this.ctx
    const w = this.canvas.width
    const h = this.canvas.height

    // Tile overlay mode (radar/satellite): static render (no land mask — radar covers land)
    if (this.tileOverlayMode) {
      ctx.clearRect(0, 0, w, h)
      this.drawTileOverlay(ctx, w, h)
      this.drawCoastline(ctx, w, h)
      this.animId = requestAnimationFrame(this.loop)
      return
    }

    // Wave heatmap mode: static render (no particle animation)
    if (this.waveMode) {
      ctx.clearRect(0, 0, w, h)
      this.drawWaveHeatmap(ctx, w, h)
      // Mask out land: fill coastline polygons with background color
      this.fillLandMask(ctx, w, h)
      this.drawCoastline(ctx, w, h)
      this.animId = requestAnimationFrame(this.loop)
      return
    }

    // On bounds change (drag/zoom), skip trail fade to prevent ghosting
    if (this.boundsChanged) {
      this.boundsChanged = false
      ctx.clearRect(0, 0, w, h)
      // Reset offscreen too
      if (this.offscreen) {
        const oc = this.offscreen.getContext('2d')
        oc?.clearRect(0, 0, this.offscreen.width, this.offscreen.height)
      }
    } else {
      // Fade trails using offscreen canvas to avoid destination-out compositing
      // bugs that can make the canvas appear opaque/black in some browsers.
      if (!this.offscreen) {
        this.offscreen = document.createElement('canvas')
      }
      const off = this.offscreen
      if (off.width !== w || off.height !== h) {
        off.width = w
        off.height = h
      }
      const offCtx = off.getContext('2d')
      if (offCtx) {
        offCtx.clearRect(0, 0, w, h)
        offCtx.drawImage(this.canvas, 0, 0)
      }
      ctx.clearRect(0, 0, w, h)
      ctx.globalAlpha = this.fadeFactor
      ctx.drawImage(off, 0, 0)
      ctx.globalAlpha = 1.0
    }

    ctx.lineWidth = this.lineWidth * this.dpr
    ctx.lineCap = 'round'

    for (const p of this.particles) {
      const [u, v] = this.sampleWind(p.x, p.y)

      // Wind speed in m/s → pixel displacement
      const speed = Math.sqrt(u * u + v * v)
      const kt = speed * 1.94384

      // Color based on speed (monochrome ramp)
      const brightness = Math.min(1, speed / 15)
      const alpha = 0.3 + brightness * 0.6
      if (kt > 35) {
        ctx.strokeStyle = `rgba(248, 113, 113, ${alpha})`  // storm red
      } else {
        const g = Math.floor(50 + brightness * 205)
        ctx.strokeStyle = `rgba(${g}, ${g}, ${g}, ${alpha})`
      }

      const dx = u * this.speedFactor * this.dpr
      const dy = -v * this.speedFactor * this.dpr  // v is northward, canvas y is downward

      const nx = p.x + dx
      const ny = p.y + dy

      ctx.beginPath()
      ctx.moveTo(p.x, p.y)
      ctx.lineTo(nx, ny)
      ctx.stroke()

      p.x = nx
      p.y = ny
      p.age++

      // Respawn if out of bounds or too old
      if (p.age > p.maxAge || p.x < 0 || p.x > w || p.y < 0 || p.y > h) {
        const fresh = this.randomParticle()
        p.x = fresh.x
        p.y = fresh.y
        p.age = 0
      }
    }

    // Draw coastline + labels (using physical pixel coords for crispness)
    this.drawCoastline(ctx, w, h)

    this.animId = requestAnimationFrame(this.loop)
  }

  /** Convert lon/lat to canvas pixel coordinates using Mercator projection */
  private project(lon: number, lat: number, w: number, h: number): [number, number] {
    const { west, east, south, north } = this.bounds
    // X is linear in longitude
    const x = ((lon - west) / (east - west)) * w
    // Y uses Mercator-like scaling (lat → sinh) for correct aspect ratio
    const mercY = (l: number) => Math.log(Math.tan(Math.PI / 4 + (l * Math.PI / 180) / 2))
    const yMin = mercY(south)
    const yMax = mercY(north)
    const y = ((yMax - mercY(lat)) / (yMax - yMin)) * h
    return [x, y]
  }

  /** Fill land polygons with background color to mask wave heatmap over land */
  private fillLandMask(ctx: CanvasRenderingContext2D, w: number, h: number) {
    if (!this.coastline.length) return
    ctx.fillStyle = '#000000'  // match ocean/map background
    for (const ring of this.coastline) {
      if (ring.length < 3) continue
      ctx.beginPath()
      const [sx, sy] = this.project(ring[0][0], ring[0][1], w, h)
      ctx.moveTo(sx, sy)
      for (let i = 1; i < ring.length; i++) {
        const [px, py] = this.project(ring[i][0], ring[i][1], w, h)
        ctx.lineTo(px, py)
      }
      ctx.closePath()
      ctx.fill()
    }
  }

  private drawCoastline(ctx: CanvasRenderingContext2D, w: number, h: number) {
    const dpr = this.dpr
    ctx.save()
    ctx.globalCompositeOperation = 'source-over'

    if (this.coastline.length > 0) {
      // Fill land polygons first (subtle dark fill, visible even if MapLibre fails)
      ctx.fillStyle = 'rgba(20, 20, 20, 0.5)'
      for (const ring of this.coastline) {
        ctx.beginPath()
        for (let i = 0; i < ring.length; i++) {
          const [x, y] = this.project(ring[i][0], ring[i][1], w, h)
          if (i === 0) ctx.moveTo(x, y)
          else ctx.lineTo(x, y)
        }
        ctx.closePath()
        ctx.fill()
      }

      // Stroke coastline outline on top
      ctx.strokeStyle = 'rgba(200, 200, 200, 0.4)'
      ctx.lineWidth = 1.5 * dpr
      ctx.lineJoin = 'round'

      for (const ring of this.coastline) {
        ctx.beginPath()
        for (let i = 0; i < ring.length; i++) {
          const [x, y] = this.project(ring[i][0], ring[i][1], w, h)
          if (i === 0) ctx.moveTo(x, y)
          else ctx.lineTo(x, y)
        }
        ctx.closePath()
        ctx.stroke()
      }
    }

    // Draw location labels
    if (this.labels.length > 0) {
      ctx.textBaseline = 'middle'

      for (const label of this.labels) {
        const [x, y] = this.project(label.lon, label.lat, w, h)

        // Skip if off-screen
        const margin = 50 * dpr
        if (x < -margin || x > w + margin || y < -margin || y > h + margin) continue

        const isSelected = label.id != null && label.id === this.selectedId
        const ratingColor = label.id ? this.labelColors[label.id] : undefined

        // Selected highlight ring
        if (isSelected) {
          ctx.beginPath()
          ctx.arc(x, y, 10 * dpr, 0, Math.PI * 2)
          ctx.strokeStyle = ratingColor ?? '#ffffff'
          ctx.lineWidth = 2 * dpr
          ctx.stroke()
          // Glow effect
          ctx.beginPath()
          ctx.arc(x, y, 12 * dpr, 0, Math.PI * 2)
          ctx.strokeStyle = `${ratingColor ?? '#ffffff'}40`
          ctx.lineWidth = 3 * dpr
          ctx.stroke()
        }

        // Dot — rating-colored for spots, diamond shape for harbour
        if (label.type === 'harbour') {
          // Diamond pin for harbour
          const s = (isSelected ? 6 : 4.5) * dpr
          ctx.beginPath()
          ctx.moveTo(x, y - s)
          ctx.lineTo(x + s, y)
          ctx.lineTo(x, y + s)
          ctx.lineTo(x - s, y)
          ctx.closePath()
          ctx.fillStyle = ratingColor ?? '#cccccc'
          ctx.fill()
          ctx.strokeStyle = 'rgba(255,255,255,0.8)'
          ctx.lineWidth = 1 * dpr
          ctx.stroke()
        } else {
          // Circular dot for spots + cities
          const dotRadius = (label.type === 'city' ? 3 : isSelected ? 5 : 4) * dpr
          ctx.beginPath()
          ctx.arc(x, y, dotRadius, 0, Math.PI * 2)
          ctx.fillStyle = label.type === 'city' ? '#888'
            : ratingColor ?? '#e0e0e0'
          ctx.fill()
          ctx.strokeStyle = 'rgba(255,255,255,0.8)'
          ctx.lineWidth = 1 * dpr
          ctx.stroke()
        }

        // Label text
        const offsetX = (label.type === 'harbour' ? 10 : label.type === 'city' ? 8 : (isSelected ? 10 : 9)) * dpr
        const fontSize = label.type === 'city' ? 10 * dpr
          : isSelected ? 12 * dpr
          : 11 * dpr
        ctx.font = `${isSelected && label.type !== 'city' ? 'bold ' : ''}${fontSize}px Inter, system-ui, sans-serif`
        ctx.fillStyle = label.type === 'harbour' ? '#d0d0d0'
          : label.type === 'city' ? '#999'
          : isSelected ? '#ffffff'
          : '#f0f0f0'
        ctx.textAlign = 'left'

        // Text shadow for readability
        const displayText = (this.lang === 'zh' && label.textZh) ? label.textZh : label.text
        ctx.strokeStyle = 'rgba(0, 0, 0, 0.8)'
        ctx.lineWidth = 3 * dpr
        ctx.strokeText(displayText, x + offsetX, y)
        ctx.fillText(displayText, x + offsetX, y)
      }
    }

    ctx.restore()
  }
}
