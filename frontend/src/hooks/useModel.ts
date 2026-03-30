import { createContext, useContext, useState, useCallback, useEffect, useRef } from 'react'
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
  const abortRef = useRef<AbortController | null>(null)

  const loadGrid = useCallback(async (m: WindModel) => {
    // Cancel any in-flight request
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller

    setGridLoading(true)
    try {
      const res = await fetch(MODEL_FILES[m], { signal: controller.signal })
      if (controller.signal.aborted) return
      if (res.ok) {
        setGrid(await res.json())
      } else {
        setGrid(null)
      }
    } catch (err) {
      if (controller.signal.aborted) return
      setGrid(null)
    } finally {
      if (!controller.signal.aborted) setGridLoading(false)
    }
  }, [])

  const setModel = useCallback((m: WindModel) => {
    setModelState(m)
    loadGrid(m)
  }, [loadGrid])

  // Load initial grid on mount; clean up on unmount
  useEffect(() => {
    loadGrid('ecmwf')
    return () => { abortRef.current?.abort() }
  }, [loadGrid])

  return { model, setModel, grid, gridLoading }
}

export function useModel() {
  return useContext(ModelContext)
}
