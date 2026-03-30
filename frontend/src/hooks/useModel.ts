import { createContext, useContext, useState, useCallback, useEffect } from 'react'
import { DATA_FILES } from '@/lib/constants'
import type { WindGrid } from '@/lib/types'

export type WindModel = 'wrf' | 'ecmwf' | 'gfs'

const MODEL_FILES: Record<WindModel, string> = {
  wrf: DATA_FILES.wind_grid_wrf,
  ecmwf: DATA_FILES.wind_grid_ecmwf,
  gfs: DATA_FILES.wind_grid_gfs,
}

export interface ModelState {
  model: WindModel
  setModel: (m: WindModel) => void
  grid: WindGrid | null
  gridLoading: boolean
}

const defaultState: ModelState = {
  model: 'ecmwf',
  setModel: () => {},
  grid: null,
  gridLoading: false,
}

export const ModelContext = createContext<ModelState>(defaultState)

export function useModelProvider(): ModelState {
  const [model, setModelState] = useState<WindModel>('ecmwf')
  const [grid, setGrid] = useState<WindGrid | null>(null)
  const [gridLoading, setGridLoading] = useState(false)

  const loadGrid = useCallback(async (m: WindModel) => {
    setGridLoading(true)
    try {
      const res = await fetch(MODEL_FILES[m])
      if (res.ok) {
        setGrid(await res.json())
      } else {
        setGrid(null)
      }
    } catch {
      setGrid(null)
    } finally {
      setGridLoading(false)
    }
  }, [])

  const setModel = useCallback((m: WindModel) => {
    setModelState(m)
    loadGrid(m)
  }, [loadGrid])

  // Load initial grid on mount
  useEffect(() => { loadGrid('ecmwf') }, [loadGrid])

  return { model, setModel, grid, gridLoading }
}

export function useModel() {
  return useContext(ModelContext)
}
