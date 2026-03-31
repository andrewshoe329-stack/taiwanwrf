import { useState, useEffect, useCallback, useRef } from 'react'

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

const BASE_INTERVAL = 5 * 60 * 1000 // 5 minutes
const MAX_INTERVAL = 20 * 60 * 1000 // 20 minutes (cap for backoff)

export function useLiveObs() {
  const [data, setData] = useState<LiveObsData | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const failCountRef = useRef(0)

  const fetchLive = useCallback(async () => {
    setLoading(true)
    try {
      const controller = new AbortController()
      const timeout = setTimeout(() => controller.abort(), 20000)
      const res = await fetch('/api/live-obs', { signal: controller.signal })
      clearTimeout(timeout)

      if (!res.ok) {
        // Serverless function not available (dev mode, no CWA key, etc.)
        failCountRef.current++
        setError(null)
        setData(null)
        return
      }

      const json = await res.json()
      setData(json)
      setError(null)
      failCountRef.current = 0 // Reset on success
    } catch {
      // Silent fail — live data is optional enhancement
      failCountRef.current++
      setData(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    let timeoutId: ReturnType<typeof setTimeout> | null = null

    const schedule = () => {
      if (cancelled) return
      // Exponential backoff: 5m → 10m → 20m (capped) on consecutive failures
      const backoff = Math.min(
        BASE_INTERVAL * Math.pow(2, failCountRef.current),
        MAX_INTERVAL,
      )
      const interval = failCountRef.current === 0 ? BASE_INTERVAL : backoff
      timeoutId = setTimeout(async () => {
        if (cancelled) return
        await fetchLive()
        schedule()
      }, interval)
    }

    // Initial fetch
    fetchLive().then(() => { if (!cancelled) schedule() })

    return () => {
      cancelled = true
      if (timeoutId) clearTimeout(timeoutId)
    }
  }, [fetchLive])

  return { data, loading, error, refresh: fetchLive }
}
