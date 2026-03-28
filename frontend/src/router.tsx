import React, { lazy, Suspense } from 'react'
import { createBrowserRouter } from 'react-router-dom'
import { App } from './App'

const NowPage = lazy(() => import('./pages/NowPage').then(m => ({ default: m.NowPage })))
const SpotsPage = lazy(() => import('./pages/SpotsPage').then(m => ({ default: m.SpotsPage })))
const SpotDetailPage = lazy(() => import('./pages/SpotDetailPage').then(m => ({ default: m.SpotDetailPage })))
const HarboursPage = lazy(() => import('./pages/HarboursPage').then(m => ({ default: m.HarboursPage })))
const ModelsPage = lazy(() => import('./pages/ModelsPage').then(m => ({ default: m.ModelsPage })))

function LazyFallback() {
  return (
    <div className="flex items-center justify-center h-[50vh]">
      <div className="w-4 h-4 border-2 border-[var(--color-text-muted)] border-t-transparent rounded-full animate-spin" />
    </div>
  )
}

class LazyErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { hasError: boolean }
> {
  constructor(props: { children: React.ReactNode }) {
    super(props)
    this.state = { hasError: false }
  }

  static getDerivedStateFromError(): { hasError: boolean } {
    return { hasError: true }
  }

  handleRetry = () => {
    this.setState({ hasError: false })
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex flex-col items-center justify-center h-[50vh] gap-4">
          <p className="text-[var(--color-text-muted)] text-sm">Failed to load page.</p>
          <button
            onClick={this.handleRetry}
            className="px-4 py-2 text-sm rounded-md bg-[var(--color-bg-elevated)] text-[var(--color-text-primary)] border border-[var(--color-border)] hover:bg-[var(--color-border)] transition-colors"
          >
            Retry
          </button>
        </div>
      )
    }
    return this.props.children
  }
}

function withSuspense(Component: React.LazyExoticComponent<React.ComponentType>) {
  return (
    <LazyErrorBoundary>
      <Suspense fallback={<LazyFallback />}>
        <Component />
      </Suspense>
    </LazyErrorBoundary>
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
      { path: 'harbours', element: withSuspense(HarboursPage) },
      { path: 'models', element: withSuspense(ModelsPage) },
    ],
  },
])
