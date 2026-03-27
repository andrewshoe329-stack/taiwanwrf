import { createContext, useContext, useState, useCallback } from 'react'
import type { Activity } from '@/lib/types'

export interface ActivityState {
  activity: Activity
  toggle: () => void
  set: (a: Activity) => void
}

const defaultState: ActivityState = {
  activity: 'sail',
  toggle: () => {},
  set: () => {},
}

export const ActivityContext = createContext<ActivityState>(defaultState)

export function useActivityProvider(): ActivityState {
  const [activity, setActivity] = useState<Activity>(() => {
    return (localStorage.getItem('tw-forecast-activity') as Activity) || 'sail'
  })

  const toggle = useCallback(() => {
    setActivity(prev => {
      const next = prev === 'sail' ? 'surf' : 'sail'
      localStorage.setItem('tw-forecast-activity', next)
      return next
    })
  }, [])

  const set = useCallback((a: Activity) => {
    setActivity(a)
    localStorage.setItem('tw-forecast-activity', a)
  }, [])

  return { activity, toggle, set }
}

export function useActivity() {
  return useContext(ActivityContext)
}
