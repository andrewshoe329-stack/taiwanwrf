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
    // Full reload to clear stale chunks from SW cache
    window.location.reload()
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
    ],
  },
])
