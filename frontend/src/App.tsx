import { Outlet } from 'react-router-dom'
import { Header } from '@/components/layout/Header'
import { BottomNav } from '@/components/layout/BottomNav'
import { ForecastDataContext, useForecastDataLoader } from '@/hooks/useForecastData'
import { TimelineContext, useTimelineProvider } from '@/hooks/useTimeline'
import { ModelContext, useModelProvider } from '@/hooks/useModel'
import { LocationContext, useLocationProvider } from '@/hooks/useLocation'

export function App() {
  const forecastData = useForecastDataLoader()
  const timeline = useTimelineProvider()
  const modelState = useModelProvider()
  const locationState = useLocationProvider()

  return (
    <ForecastDataContext.Provider value={forecastData}>
      <TimelineContext.Provider value={timeline}>
        <ModelContext.Provider value={modelState}>
          <LocationContext.Provider value={locationState}>
            <div className="min-h-screen bg-[var(--color-bg)]">
              <Header />
              <main className="pb-16 pwa-main">
                <Outlet />
              </main>
              <BottomNav />
            </div>
          </LocationContext.Provider>
        </ModelContext.Provider>
      </TimelineContext.Provider>
    </ForecastDataContext.Provider>
  )
}
