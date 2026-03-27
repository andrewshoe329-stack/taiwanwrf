/**
 * Time interpolation utilities for smooth transitions between 6h forecast steps.
 */

import type { WindGrid } from './types'

/**
 * Linearly interpolate between two 2D grids of the same dimensions.
 * t=0 returns grid a, t=1 returns grid b.
 */
export function lerpGrid(a: number[][], b: number[][], t: number): number[][] {
  const rows = a.length
  const result: number[][] = new Array(rows)
  for (let j = 0; j < rows; j++) {
    const cols = a[j].length
    const row = new Array(cols)
    for (let i = 0; i < cols; i++) {
      row[i] = a[j][i] * (1 - t) + b[j][i] * t
    }
    result[j] = row
  }
  return result
}

/**
 * Given a wind grid with multiple timesteps and a fractional time index,
 * return an interpolated single-timestep grid.
 * index=0.0 → first timestep, index=0.5 → halfway between first and second, etc.
 */
export function interpolateWindGrid(
  grid: WindGrid,
  index: number
): { u: number[][]; v: number[][] } | null {
  const steps = grid.timesteps
  if (steps.length === 0) return null

  const clamped = Math.max(0, Math.min(index, steps.length - 1))
  const lo = Math.floor(clamped)
  const hi = Math.min(lo + 1, steps.length - 1)
  const t = clamped - lo

  if (lo === hi || t < 0.001) {
    return { u: steps[lo].u, v: steps[lo].v }
  }

  return {
    u: lerpGrid(steps[lo].u, steps[hi].u, t),
    v: lerpGrid(steps[lo].v, steps[hi].v, t),
  }
}
