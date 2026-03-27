import { useTranslation } from 'react-i18next'
import { ActivityToggle } from './ActivityToggle'
import { LanguageToggle } from './LanguageToggle'

export function Header() {
  const { t } = useTranslation()

  return (
    <header className="fixed top-0 left-0 right-0 z-50 glass border-b border-[var(--color-border)]">
      <div className="flex items-center justify-between h-12 px-4 max-w-screen-xl mx-auto">
        <a href="/" className="text-[15px] font-semibold tracking-tight text-[var(--color-text-primary)] no-underline">
          {t('app.title')}
        </a>
        <div className="flex items-center gap-3">
          <ActivityToggle />
          <LanguageToggle />
        </div>
      </div>
    </header>
  )
}
