import { useState, useEffect } from 'react'

const MOBILE_BREAKPOINT = 768
const MOBILE_QUERY = `(max-width: ${MOBILE_BREAKPOINT - 1}px), (orientation: landscape) and (max-height: 500px)`

export function useIsMobile(): boolean {
  const [isMobile, setIsMobile] = useState(
    () => typeof window !== 'undefined' && window.matchMedia(MOBILE_QUERY).matches,
  )

  useEffect(() => {
    const mql = window.matchMedia(MOBILE_QUERY)
    const handler = (e: MediaQueryListEvent) => setIsMobile(e.matches)
    mql.addEventListener('change', handler)
    setIsMobile(mql.matches)
    return () => mql.removeEventListener('change', handler)
  }, [])

  return isMobile
}

/** True when the device is in landscape with limited height (phone landscape). */
export function useMobileLandscape(): boolean {
  const [isLandscape, setIsLandscape] = useState(
    () => typeof window !== 'undefined' && window.matchMedia('(orientation: landscape) and (max-height: 500px)').matches,
  )

  useEffect(() => {
    const mql = window.matchMedia('(orientation: landscape) and (max-height: 500px)')
    const handler = (e: MediaQueryListEvent) => setIsLandscape(e.matches)
    mql.addEventListener('change', handler)
    setIsLandscape(mql.matches)
    return () => mql.removeEventListener('change', handler)
  }, [])

  return isLandscape
}
