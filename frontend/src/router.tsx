import React, { lazy, Suspense } from 'react'
import { createBrowserRouter, Navigate, useParams } from 'react-router-dom'
import { App } from './App'

const NowPage = lazy(() =>
  import('./pages/NowPage').then(m => ({ default: m.NowPage }))
    .catch(() => {
      // Retry once after a brief delay (handles CDN propagation / stale SW cache)
      return new Promise<{ default: typeof import('./pages/NowPage')['NowPage'] }>(resolve =>
        setTimeout(() => resolve(
          import('./pages/NowPage').then(m => ({ default: m.NowPage }))
        ), 1500)
      )
    })
)
const HistoryPage = lazy(() =>
  import('./pages/HistoryPage').then(m => ({ default: m.HistoryPage }))
)

/** Redirect /spots/:id → /?loc=:id */
function SpotRedirect() {
  const { id } = useParams<{ id: string }>()
  return <Navigate to={`/?loc=${id}`} replace />
}

function LazyFallback() {
  return (
    <div className="flex items-center justify-center h-[50vh]">
      <div className="w-4 h-4 border-2 border-[var(--color-text-muted)] border-t-transparent rounded-full animate-spin" />
    </div>
  )
}

class LazyErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { hasError: boolean; retried: boolean }
> {
  constructor(props: { children: React.ReactNode }) {
    super(props)
    this.state = { hasError: false, retried: false }
  }

  static getDerivedStateFromError(): Partial<{ hasError: boolean }> {
    return { hasError: true }
  }

  componentDidUpdate(_: unknown, prevState: { hasError: boolean; retried: boolean }) {
    // Auto-retry once after 2s on first failure (CDN propagation delay)
    if (this.state.hasError && !prevState.hasError && !this.state.retried) {
      setTimeout(() => {
        this.setState({ hasError: false, retried: true })
      }, 2000)
    }
  }

  handleRetry = () => {
    window.location.reload()
  }

  render() {
    if (this.state.hasError) {
      // During auto-retry, show spinner instead of error
      if (!this.state.retried) {
        return (
          <div className="flex items-center justify-center h-[50vh]">
            <div className="w-4 h-4 border-2 border-[var(--color-text-muted)] border-t-transparent rounded-full animate-spin" />
          </div>
        )
      }
      return (
        <div className="flex flex-col items-center justify-center h-[50vh] gap-4">
          <p className="text-[var(--color-text-muted)] fs-label">Failed to load page.</p>
          <button
            onClick={this.handleRetry}
            className="px-4 py-2 fs-label rounded-md bg-[var(--color-bg-elevated)] text-[var(--color-text-primary)] border border-[var(--color-border)] hover:bg-[var(--color-border)] transition-colors"
          >
            Retry
          </button>
        </div>
      )
    }
    return this.props.children
  }
}

export const router = createBrowserRouter([
  {
    path: '/',
    element: <App />,
    children: [
      {
        index: true,
        element: (
          <LazyErrorBoundary>
            <Suspense fallback={<LazyFallback />}>
              <NowPage />
            </Suspense>
          </LazyErrorBoundary>
        ),
      },
      { path: 'spots', element: <Navigate to="/" replace /> },
      { path: 'spots/:id', element: <SpotRedirect /> },
      { path: 'harbours', element: <Navigate to="/?loc=keelung" replace /> },
      { path: 'models', element: <Navigate to="/" replace /> },
      {
        path: 'history',
        element: (
          <LazyErrorBoundary>
            <Suspense fallback={<LazyFallback />}>
              <HistoryPage />
            </Suspense>
          </LazyErrorBoundary>
        ),
      },
    ],
  },
])
