import { useState, useEffect, useCallback } from 'react'
import { DATA_FILES } from '@/lib/constants'
import type { WindGrid } from '@/lib/types'

export type WindModel = 'wrf' | 'ecmwf' | 'gfs'

const MODEL_FILES: Record<WindModel, string> = {
  wrf: DATA_FILES.wind_grid_wrf,
  ecmwf: DATA_FILES.wind_grid_ecmwf,
  gfs: DATA_FILES.wind_grid_gfs,
}

export interface WindGridState {
  grid: WindGrid | null
  model: WindModel
  setModel: (m: WindModel) => void
  loading: boolean
}

export function useWindGrid(): WindGridState {
  const [model, setModelState] = useState<WindModel>('ecmwf')
  const [grid, setGrid] = useState<WindGrid | null>(null)
  const [loading, setLoading] = useState(false)

  const loadGrid = useCallback(async (m: WindModel) => {
    setLoading(true)
    try {
      const res = await fetch(MODEL_FILES[m])
      if (res.ok) {
        const data: WindGrid = await res.json()
        setGrid(data)
      } else {
        setGrid(null)
      }
    } catch {
      setGrid(null)
    } finally {
      setLoading(false)
    }
  }, [])

  const setModel = useCallback((m: WindModel) => {
    setModelState(m)
    loadGrid(m)
  }, [loadGrid])

  // Load initial model on mount only
  useEffect(() => {
    loadGrid('ecmwf')
  }, [loadGrid])

  return { grid, model, setModel, loading }
}
