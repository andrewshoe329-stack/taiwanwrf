import { lazy, Suspense } from 'react'
import { createBrowserRouter } from 'react-router-dom'
import { App } from './App'

const NowPage = lazy(() => import('./pages/NowPage').then(m => ({ default: m.NowPage })))
const SpotsPage = lazy(() => import('./pages/SpotsPage').then(m => ({ default: m.SpotsPage })))
const SpotDetailPage = lazy(() => import('./pages/SpotDetailPage').then(m => ({ default: m.SpotDetailPage })))
const ModelsPage = lazy(() => import('./pages/ModelsPage').then(m => ({ default: m.ModelsPage })))

function LazyFallback() {
  return (
    <div className="flex items-center justify-center h-[50vh]">
      <div className="w-4 h-4 border-2 border-[var(--color-text-muted)] border-t-transparent rounded-full animate-spin" />
    </div>
  )
}

function withSuspense(Component: React.LazyExoticComponent<React.ComponentType>) {
  return (
    <Suspense fallback={<LazyFallback />}>
      <Component />
    </Suspense>
  )
}

export const router = createBrowserRouter([
  {
    path: '/',
    element: <App />,
    children: [
      { index: true, element: withSuspense(NowPage) },
      { path: 'spots', element: withSuspense(SpotsPage) },
      { path: 'spots/:id', element: withSuspense(SpotDetailPage) },
      { path: 'models', element: withSuspense(ModelsPage) },
    ],
  },
])
