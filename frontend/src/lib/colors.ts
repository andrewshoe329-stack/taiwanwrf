/** Wind speed to monochrome color ramp (matching Threads aesthetic) */
export function windSpeedColor(kt: number): string {
  if (kt < 5)  return '#333333'  // calm — barely visible
  if (kt < 10) return '#555555'  // light
  if (kt < 15) return '#888888'  // moderate
  if (kt < 20) return '#aaaaaa'  // fresh
  if (kt < 25) return '#cccccc'  // strong
  if (kt < 30) return '#eeeeee'  // near gale
  if (kt < 40) return '#ffffff'  // gale — white
  return '#f87171'               // storm — red accent
}

/** Wind speed to RGBA for WebGL particles */
export function windSpeedRGBA(kt: number): [number, number, number, number] {
  if (kt < 5)  return [0.2, 0.2, 0.2, 0.4]
  if (kt < 10) return [0.33, 0.33, 0.33, 0.6]
  if (kt < 15) return [0.53, 0.53, 0.53, 0.7]
  if (kt < 20) return [0.67, 0.67, 0.67, 0.8]
  if (kt < 25) return [0.8, 0.8, 0.8, 0.85]
  if (kt < 30) return [0.93, 0.93, 0.93, 0.9]
  if (kt < 40) return [1.0, 1.0, 1.0, 0.95]
  return [0.97, 0.51, 0.44, 1.0] // storm red
}

/** Rating to monochrome shade */
export function ratingColor(rating: string): string {
  switch (rating) {
    case 'firing':    return '#f5f5f5'
    case 'good':      return '#a0a0a0'
    case 'marginal':  return '#666666'
    case 'poor':      return '#333333'
    case 'flat':      return '#1a1a1a'
    case 'dangerous': return '#f87171'
    default:          return '#333333'
  }
}

/** Rating background */
export function ratingBg(rating: string): string {
  switch (rating) {
    case 'firing':    return '#222222'
    case 'good':      return '#1a1a1a'
    case 'marginal':  return '#111111'
    case 'poor':      return '#0a0a0a'
    case 'flat':      return '#050505'
    case 'dangerous': return '#1a0000'
    default:          return '#0a0a0a'
  }
}
