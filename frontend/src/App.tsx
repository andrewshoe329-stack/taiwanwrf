import { Outlet } from 'react-router-dom'
import { Header } from '@/components/layout/Header'
import { BottomNav } from '@/components/layout/BottomNav'
import { ForecastDataContext, useForecastDataLoader } from '@/hooks/useForecastData'
import { TimelineContext, useTimelineProvider } from '@/hooks/useTimeline'

export function App() {
  const forecastData = useForecastDataLoader()
  const timeline = useTimelineProvider()

  return (
    <ForecastDataContext.Provider value={forecastData}>
      <TimelineContext.Provider value={timeline}>
        <div className="min-h-screen bg-[var(--color-bg)]">
          <Header />
          <main className="pb-16" style={{ paddingTop: 'calc(3rem + env(safe-area-inset-top, 0px))' }}>
            <Outlet />
          </main>
          <BottomNav />
        </div>
      </TimelineContext.Provider>
    </ForecastDataContext.Provider>
  )
}
