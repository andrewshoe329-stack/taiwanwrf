import { useState, useEffect, useCallback } from 'react'

export interface LiveSpotObs {
  station?: {
    station_id: string
    station_name?: string
    obs_time?: string
    temp_c?: number
    wind_kt?: number
    wind_dir?: number
    gust_kt?: number
    pressure_hpa?: number
    humidity_pct?: number
    visibility_km?: number
    uv_index?: number
  }
  tide?: {
    station_id: string
    station_name?: string
    obs_time?: string
    tide_height_m?: number
    tide_level?: string
    sea_temp_c?: number
  }
  buoy?: {
    station_id: string
    station_name?: string
    obs_time?: string
    wave_height_m?: number
    wave_period_s?: number
    wave_dir?: number
    sea_temp_c?: number
    wind_kt?: number
    wind_dir?: number
    current_speed_ms?: number
    current_dir?: number
  }
}

export interface LiveObsData {
  fetched_utc: string
  spots: Record<string, LiveSpotObs>
}

const REFRESH_INTERVAL = 5 * 60 * 1000 // 5 minutes

export function useLiveObs() {
  const [data, setData] = useState<LiveObsData | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchLive = useCallback(async () => {
    setLoading(true)
    try {
      const controller = new AbortController()
      const timeout = setTimeout(() => controller.abort(), 20000)
      const res = await fetch('/api/live-obs', { signal: controller.signal })
      clearTimeout(timeout)

      if (!res.ok) {
        // Serverless function not available (dev mode, no CWA key, etc.)
        setError(null) // Don't show error — just means live data unavailable
        setData(null)
        return
      }

      const json = await res.json()
      setData(json)
      setError(null)
    } catch {
      // Silent fail — live data is optional enhancement
      setData(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    const safeFetch = async () => {
      if (cancelled) return
      await fetchLive()
    }
    safeFetch()
    const interval = setInterval(safeFetch, REFRESH_INTERVAL)
    return () => { cancelled = true; clearInterval(interval) }
  }, [fetchLive])

  return { data, loading, error, refresh: fetchLive }
}
