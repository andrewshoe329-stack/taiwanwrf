import { createContext, useContext, useState, useCallback, useRef, useEffect } from 'react'

export interface TimelineState {
  /** Index into the forecast records array */
  index: number
  /** Is the play animation running? */
  playing: boolean
  /** Total number of timesteps */
  total: number
  setIndex: (i: number) => void
  play: () => void
  pause: () => void
  toggle: () => void
  next: () => void
  prev: () => void
  setTotal: (n: number) => void
}

const noop = () => {}
const defaultState: TimelineState = {
  index: 0, playing: false, total: 0,
  setIndex: noop, play: noop, pause: noop,
  toggle: noop, next: noop, prev: noop, setTotal: noop,
}

export const TimelineContext = createContext<TimelineState>(defaultState)

export function useTimelineProvider(initialTotal = 0): TimelineState {
  const [index, setIndex] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [total, setTotal] = useState(initialTotal)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const pause = useCallback(() => {
    setPlaying(false)
    if (intervalRef.current) {
      clearInterval(intervalRef.current)
      intervalRef.current = null
    }
  }, [])

  const play = useCallback(() => {
    setPlaying(true)
  }, [])

  const toggle = useCallback(() => {
    setPlaying(p => !p)
  }, [])

  const next = useCallback(() => {
    setIndex(i => (i + 1) % Math.max(total, 1))
  }, [total])

  const prev = useCallback(() => {
    setIndex(i => (i - 1 + Math.max(total, 1)) % Math.max(total, 1))
  }, [total])

  // Auto-advance when playing
  useEffect(() => {
    if (playing && total > 0) {
      intervalRef.current = setInterval(() => {
        setIndex(i => (i + 1) % total)
      }, 1500)
    } else if (intervalRef.current) {
      clearInterval(intervalRef.current)
      intervalRef.current = null
    }
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [playing, total])

  return { index, playing, total, setIndex, play, pause, toggle, next, prev, setTotal }
}

export function useTimeline() {
  return useContext(TimelineContext)
}
