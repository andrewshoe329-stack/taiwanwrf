import { useTranslation } from 'react-i18next'
import { useLocation, Link } from 'react-router-dom'

const NAV_ITEMS = [
  { path: '/', key: 'nav.forecast', icon: 'M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5' },
  { path: '/models', key: 'nav.models', icon: 'M18 20V10M12 20V4M6 20v-6' },
] as const

export function BottomNav() {
  const { t } = useTranslation()
  const { pathname } = useLocation()

  return (
    <nav
      className="fixed bottom-0 left-0 right-0 z-50 glass border-t border-[var(--color-border)] pwa-bottom-nav"
    >
      <div className="flex items-center justify-around h-14 max-w-md mx-auto">
        {NAV_ITEMS.map(({ path, key, icon }) => {
          const active = path === '/'
            ? pathname === '/'
            : pathname.startsWith(path)
          return (
            <Link
              key={path}
              to={path}
              className={`flex flex-col items-center gap-0.5 min-w-[56px] py-1 no-underline transition-colors ${
                active ? 'text-[var(--color-text-primary)]' : 'text-[var(--color-text-muted)]'
              }`}
            >
              <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round">
                <path d={icon} />
              </svg>
              <span className="text-[10px] font-medium">{t(key)}</span>
            </Link>
          )
        })}
      </div>
    </nav>
  )
}
