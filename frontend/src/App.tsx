import { Outlet } from 'react-router-dom'
import { Header } from '@/components/layout/Header'
import { BottomNav } from '@/components/layout/BottomNav'
import { ForecastDataContext, useForecastDataLoader } from '@/hooks/useForecastData'
import { TimelineContext, useTimelineProvider } from '@/hooks/useTimeline'
import { ActivityContext, useActivityProvider } from '@/hooks/useActivity'

export function App() {
  const forecastData = useForecastDataLoader()
  const timeline = useTimelineProvider()
  const activity = useActivityProvider()

  return (
    <ForecastDataContext.Provider value={forecastData}>
      <TimelineContext.Provider value={timeline}>
        <ActivityContext.Provider value={activity}>
          <div className="min-h-screen bg-[var(--color-bg)]">
            <Header />
            <main className="pt-12 pb-16">
              <Outlet />
            </main>
            <BottomNav />
          </div>
        </ActivityContext.Provider>
      </TimelineContext.Provider>
    </ForecastDataContext.Provider>
  )
}
