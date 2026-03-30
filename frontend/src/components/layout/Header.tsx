import { useTranslation } from 'react-i18next'
import { LanguageToggle } from './LanguageToggle'

export function Header() {
  const { t } = useTranslation()

  return (
    <header className="shrink-0 z-50 border-b border-[var(--color-border)] bg-[var(--color-bg)] pwa-header">
      <div className="flex items-center justify-between h-9 px-3 max-w-screen-xl mx-auto">
        <span className="text-xs font-semibold tracking-tight text-[var(--color-text-primary)]">
          {t('app.title')}
        </span>
        <LanguageToggle />
      </div>
    </header>
  )
}
