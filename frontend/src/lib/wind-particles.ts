/**
 * Wind particle animation system.
 *
 * Renders flowing particles on a Canvas overlay, driven by a u/v wind grid.
 * Particles move in the direction of the wind, speed proportional to magnitude.
 * Monochrome color ramp: dim for calm, bright white for strong, red for storm.
 */

import type { WindGrid } from './types'

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
  private animId: number | null = null
  private running = false
  private coastlines: [number, number][][] = []
  private projector: ((lon: number, lat: number) => { x: number; y: number }) | null = null

  // Viewport mapping (set by the map component)
  private bounds = { west: 119.0, east: 122.5, south: 21.5, north: 25.5 }

  constructor(opts: WindParticleOptions) {
    this.canvas = opts.canvas
    this.ctx = opts.canvas.getContext('2d')
    this.count = opts.count ?? 4000
    this.maxAge = opts.maxAge ?? 80
    this.speedFactor = opts.speedFactor ?? 0.3
    this.lineWidth = opts.lineWidth ?? 1.2
    this.fadeFactor = opts.fadeFactor ?? 0.97
  }

  /** Set the wind grid data (call when timeline changes) */
  setGrid(grid: WindGrid) {
    this.grid = grid
    if (this.particles.length === 0) this.initParticles()
  }

  /** Set coastline polygons to draw (array of [lon, lat][] rings) */
  setCoastlines(rings: [number, number][][]) {
    this.coastlines = rings
  }

  /** Set Mercator projector function from MapLibre map.project() */
  setProjector(fn: (lon: number, lat: number) => { x: number; y: number }) {
    this.projector = fn
  }

  /** Update the map viewport bounds (call on map move/zoom) */
  setBounds(west: number, south: number, east: number, north: number) {
    this.bounds = { west, south, east, north }
  }

  /** Resize canvas to match container */
  resize(width: number, height: number) {
    this.canvas.width = width
    this.canvas.height = height
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

  /** Bilinear interpolation of wind (u, v) at a given canvas pixel */
  private sampleWind(px: number, py: number): [number, number] {
    if (!this.grid) return [0, 0]

    const { west, east, south, north } = this.bounds
    const w = this.canvas.width
    const h = this.canvas.height

    // Canvas pixel → geographic coords
    const lon = west + (px / w) * (east - west)
    const lat = north - (py / h) * (north - south)

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

  private loop = () => {
    if (!this.running || !this.ctx) return

    const ctx = this.ctx
    const w = this.canvas.width
    const h = this.canvas.height

    // Fade previous frame (trail effect) — preserve canvas transparency
    // Save current content with reduced alpha for trails
    ctx.globalCompositeOperation = 'destination-in'
    ctx.fillStyle = `rgba(0, 0, 0, ${this.fadeFactor})`
    ctx.fillRect(0, 0, w, h)
    ctx.globalCompositeOperation = 'source-over'

    ctx.lineWidth = this.lineWidth
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

      const dx = u * this.speedFactor
      const dy = -v * this.speedFactor  // v is northward, canvas y is downward

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

    // Draw coastline outline on top of particles
    this.drawCoastlines(ctx)

    this.animId = requestAnimationFrame(this.loop)
  }

  /** Draw all coastline polygons using Mercator projection */
  private drawCoastlines(ctx: CanvasRenderingContext2D) {
    if (this.coastlines.length === 0 || !this.projector) return

    ctx.globalCompositeOperation = 'source-over'

    for (const ring of this.coastlines) {
      if (ring.length < 3) continue

      ctx.beginPath()
      const first = this.projector(ring[0][0], ring[0][1])
      ctx.moveTo(first.x, first.y)
      for (let i = 1; i < ring.length; i++) {
        const pt = this.projector(ring[i][0], ring[i][1])
        ctx.lineTo(pt.x, pt.y)
      }
      ctx.closePath()
      ctx.fillStyle = 'rgba(20, 20, 40, 0.4)'
      ctx.fill()

      ctx.strokeStyle = 'rgba(120, 120, 170, 0.7)'
      ctx.lineWidth = 1.5
      ctx.stroke()
    }
  }
}
