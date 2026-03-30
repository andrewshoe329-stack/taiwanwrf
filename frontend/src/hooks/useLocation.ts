import { createContext, useContext, useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'

export interface LocationState {
  locationId: string | null
  setLocationId: (id: string | null) => void
}

const defaultState: LocationState = {
  locationId: null,
  setLocationId: () => {},
}

export const LocationContext = createContext<LocationState>(defaultState)

export function useLocationProvider(): LocationState {
  const [searchParams, setSearchParams] = useSearchParams()
  const locationId = searchParams.get('loc') || null

  const setLocationId = useCallback((id: string | null) => {
    setSearchParams(prev => {
      const next = new URLSearchParams(prev)
      if (id) {
        next.set('loc', id)
      } else {
        next.delete('loc')
      }
      return next
    }, { replace: true })
  }, [setSearchParams])

  return { locationId, setLocationId }
}

export function useLocation() {
  return useContext(LocationContext)
}
