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

