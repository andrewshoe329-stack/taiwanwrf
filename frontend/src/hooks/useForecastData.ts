import { createContext, useContext, useEffect, useState } from 'react'
import { DATA_FILES } from '@/lib/constants'
import type {
  ForecastData, WaveData, TideData, CwaObs,
  EnsembleData, SurfData, AISummary, AccuracyEntry,
  WrfSpotsData,
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
  wrf_spots: WrfSpotsData | null
  loading: boolean
  error: string | null
  reload: () => void
}

const noop = () => {}

const initial: AllForecastData = {
  keelung: null, ecmwf: null, wave: null, tide: null,
  ensemble: null, surf: null, cwa_obs: null, accuracy: null,
  summary: null, wrf_spots: null, loading: true, error: null,
  reload: noop,
}

export const ForecastDataContext = createContext<AllForecastData>(initial)

async function fetchJson<T>(url: string): Promise<T | null> {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 30_000)
  try {
    const res = await fetch(url, { signal: controller.signal })
    if (!res.ok) {
      console.warn(`[useForecastData] ${url}: HTTP ${res.status}`)
      return null
    }
    return await res.json()
  } catch (err) {
    console.warn(`[useForecastData] ${url}:`, err)
    return null
  } finally {
    clearTimeout(timeout)
  }
}

export function useForecastDataLoader(): AllForecastData {
  const [data, setData] = useState<AllForecastData>(initial)
  const [version, setVersion] = useState(0)

  useEffect(() => {
    let cancelled = false
    let retryCount = 0
    const MAX_RETRIES = 2
    const RETRY_DELAY = 3000

    async function load() {
      setData(prev => ({ ...prev, loading: true, error: null }))

      const [
        keelung, ecmwf, wave, tide, ensemble, surf, cwa_obs, accuracy, summary, wrf_spots,
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
        fetchJson<WrfSpotsData>(DATA_FILES.wrf_spots),
      ])

      if (cancelled) return

      const hasAnyData = keelung || ecmwf || wave || surf

      // Auto-retry on initial load failure (CDN propagation delay)
      if (!hasAnyData && retryCount < MAX_RETRIES) {
        retryCount++
        console.warn(`[useForecastData] No data loaded, retrying (${retryCount}/${MAX_RETRIES})...`)
        setTimeout(() => { if (!cancelled) load() }, RETRY_DELAY)
        return
      }

      setData({
        keelung, ecmwf, wave, tide, ensemble, surf, cwa_obs, accuracy, summary, wrf_spots,
        loading: false,
        error: hasAnyData ? null : 'Failed to load forecast data',
        reload: () => setVersion(v => v + 1),
      })
    }

    load()
    return () => { cancelled = true }
  }, [version])

  // Ensure reload is always available even during loading
  if (data.reload === noop) {
    data.reload = () => setVersion(v => v + 1)
  }

  return data
}

export function useForecastData() {
  return useContext(ForecastDataContext)
}
