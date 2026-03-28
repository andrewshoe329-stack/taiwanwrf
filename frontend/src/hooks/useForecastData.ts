import { createContext, useContext, useEffect, useState } from 'react'
import { DATA_FILES } from '@/lib/constants'
import type {
  ForecastData, WaveData, TideData, CwaObs,
  EnsembleData, SurfData, AISummary, AccuracyEntry,
} from '@/lib/types'

export interface AllForecastData {
  keelung: ForecastData | null
  ecmwf: ForecastData | null
  wave: WaveData | null
  tide: TideData | null
  ensemble: EnsembleData | null
  surf: SurfData | null
  cwa_obs: CwaObs | null
  accuracy: AccuracyEntry[] | null
  summary: AISummary | null
  loading: boolean
  error: string | null
}

const initial: AllForecastData = {
  keelung: null, ecmwf: null, wave: null, tide: null,
  ensemble: null, surf: null, cwa_obs: null, accuracy: null,
  summary: null, loading: true, error: null,
}

export const ForecastDataContext = createContext<AllForecastData>(initial)

async function fetchJson<T>(url: string): Promise<T | null> {
  try {
    const res = await fetch(url)
    if (!res.ok) return null
    return await res.json()
  } catch {
    return null
  }
}

export function useForecastDataLoader(): AllForecastData {
  const [data, setData] = useState<AllForecastData>(initial)

  useEffect(() => {
    let cancelled = false

    async function load() {
      const [
        keelung, ecmwf, wave, tide, ensemble, surf, cwa_obs, accuracy, summary,
      ] = await Promise.all([
        fetchJson<ForecastData>(DATA_FILES.keelung),
        fetchJson<ForecastData>(DATA_FILES.ecmwf),
        fetchJson<WaveData>(DATA_FILES.wave),
        fetchJson<TideData>(DATA_FILES.tide),
        fetchJson<EnsembleData>(DATA_FILES.ensemble),
        fetchJson<SurfData>(DATA_FILES.surf),
        fetchJson<CwaObs>(DATA_FILES.cwa_obs),
        fetchJson<AccuracyEntry[]>(DATA_FILES.accuracy),
        fetchJson<AISummary>(DATA_FILES.summary),
      ])

      if (cancelled) return

      const hasAnyData = keelung || ecmwf || wave || surf
      setData({
        keelung, ecmwf, wave, tide, ensemble, surf, cwa_obs, accuracy, summary,
        loading: false,
        error: hasAnyData ? null : 'Failed to load forecast data',
      })
    }

    load()
    return () => { cancelled = true }
  }, [])

  return data
}

export function useForecastData() {
  return useContext(ForecastDataContext)
}
