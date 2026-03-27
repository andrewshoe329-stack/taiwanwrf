import { useState, useEffect, useCallback } from 'react'
import { DATA_FILES } from '@/lib/constants'
import type { WindGrid } from '@/lib/types'

export type WindModel = 'wrf' | 'ecmwf' | 'gfs' | 'icon'

const MODEL_FILES: Record<WindModel, string> = {
  wrf: DATA_FILES.wind_grid_wrf,
  ecmwf: DATA_FILES.wind_grid_ecmwf,
  gfs: DATA_FILES.wind_grid_gfs,
  icon: DATA_FILES.wind_grid_icon,
}

export interface WindGridState {
  grid: WindGrid | null
  model: WindModel
  setModel: (m: WindModel) => void
  loading: boolean
}

export function useWindGrid(): WindGridState {
  const [model, setModelState] = useState<WindModel>('wrf')
  const [grid, setGrid] = useState<WindGrid | null>(null)
  const [loading, setLoading] = useState(false)
  const [cache] = useState<Map<WindModel, WindGrid>>(new Map())

  const loadGrid = useCallback(async (m: WindModel) => {
    const cached = cache.get(m)
    if (cached) {
      setGrid(cached)
      return
    }

    setLoading(true)
    try {
      const res = await fetch(MODEL_FILES[m])
      if (res.ok) {
        const data: WindGrid = await res.json()
        cache.set(m, data)
        setGrid(data)
      }
    } catch {
      // Grid unavailable for this model
    } finally {
      setLoading(false)
    }
  }, [cache])

  const setModel = useCallback((m: WindModel) => {
    setModelState(m)
    loadGrid(m)
  }, [loadGrid])

  // Load initial model on mount only
  useEffect(() => {
    loadGrid('wrf')
  }, [loadGrid])

  return { grid, model, setModel, loading }
}
