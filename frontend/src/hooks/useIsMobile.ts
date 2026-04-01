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

/** True on tablet-sized screens (768-1199px wide, not landscape-phone).
 *  Covers iPad portrait (834-1024px) and iPad 11" landscape (1194px). */
export function useIsTabletPortrait(): boolean {
  const [is, setIs] = useState(
    () => typeof window !== 'undefined' && window.matchMedia(
      '(min-width: 768px) and (max-width: 1199px) and (min-height: 500px)',
    ).matches,
  )

  useEffect(() => {
    const mql = window.matchMedia('(min-width: 768px) and (max-width: 1199px) and (min-height: 500px)')
    const handler = (e: MediaQueryListEvent) => setIs(e.matches)
    mql.addEventListener('change', handler)
    setIs(mql.matches)
    return () => mql.removeEventListener('change', handler)
  }, [])

  return is
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
