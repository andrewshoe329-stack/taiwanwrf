import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useForecastData } from '@/hooks/useForecastData'
import { LanguageToggle } from './LanguageToggle'
import { TextSizeToggle } from './TextSizeToggle'

function useViewportDebug() {
  const [size, setSize] = useState('')
  useEffect(() => {
    const update = () => setSize(`${window.innerWidth}×${window.innerHeight}`)
    update()
    window.addEventListener('resize', update)
    return () => window.removeEventListener('resize', update)
  }, [])
  return size
}

export function Header() {
  const { t } = useTranslation()
  const { reload, loading } = useForecastData()
  const vpSize = useViewportDebug()

  return (
    <header className="shrink-0 z-50 border-b border-[var(--color-border)] bg-[var(--color-bg)] pwa-header">
      <div className="flex items-center justify-between h-9 px-3 max-w-screen-xl mx-auto">
        <span className="fs-body font-semibold tracking-tight text-[var(--color-text-primary)]">
          {t('app.title')}
        </span>
        <div className="flex items-center gap-2">
          <span className="fs-micro text-[var(--color-text-dim)] tabular-nums">{vpSize}</span>
          <button
            onClick={reload}
            disabled={loading}
            className="w-6 h-6 flex items-center justify-center rounded-full text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-bg-elevated)] transition-colors disabled:opacity-30"
            aria-label="Refresh data"
          >
            <svg
              width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"
              className={loading ? 'animate-spin' : ''}
            >
              <path d="M1.5 7a5.5 5.5 0 0 1 9.4-3.9M12.5 7a5.5 5.5 0 0 1-9.4 3.9" />
              <path d="M11 1v3h-3M3 13v-3h3" />
            </svg>
          </button>
          <TextSizeToggle />
          <LanguageToggle />
        </div>
      </div>
    </header>
  )
}
