import { createContext, useContext } from 'react'
import { Outlet } from 'react-router-dom'
import { Header } from '@/components/layout/Header'
import { ForecastDataContext, useForecastDataLoader } from '@/hooks/useForecastData'
import { TimelineContext, useTimelineProvider } from '@/hooks/useTimeline'
import { ModelContext, useModelProvider } from '@/hooks/useModel'
import { LocationContext, useLocationProvider } from '@/hooks/useLocation'
import { useLiveObs, type LiveObsData } from '@/hooks/useLiveObs'
import { TextSizeContext, useTextSizeProvider } from '@/hooks/useTextSize'

interface LiveObsContextValue {
  data: LiveObsData | null
  loading: boolean
  refresh: () => void
}

export const LiveObsContext = createContext<LiveObsContextValue>({
  data: null, loading: false, refresh: () => {},
})

export function useLiveObsContext() {
  return useContext(LiveObsContext)
}

export function App() {
  const forecastData = useForecastDataLoader()
  const timeline = useTimelineProvider()
  const modelState = useModelProvider()
  const locationState = useLocationProvider()
  const liveObs = useLiveObs()
  const textSize = useTextSizeProvider()

  return (
    <TextSizeContext.Provider value={textSize}>
    <ForecastDataContext.Provider value={forecastData}>
      <LiveObsContext.Provider value={liveObs}>
        <TimelineContext.Provider value={timeline}>
          <ModelContext.Provider value={modelState}>
            <LocationContext.Provider value={locationState}>
              <div className="h-[100dvh] flex flex-col bg-[var(--color-bg)] pwa-safe-lr">
                <a href="#main-content" className="sr-only focus:not-sr-only focus:absolute focus:z-[100] focus:top-2 focus:left-2 focus:px-3 focus:py-1.5 focus:rounded-lg focus:bg-[var(--color-accent)] focus:text-black focus:fs-body focus:font-medium">
                  Skip to content
                </a>
                <Header />
                <main id="main-content" className="flex-1 min-h-0">
                  <Outlet />
                </main>
              </div>
            </LocationContext.Provider>
          </ModelContext.Provider>
        </TimelineContext.Provider>
      </LiveObsContext.Provider>
    </ForecastDataContext.Provider>
    </TextSizeContext.Provider>
  )
}
