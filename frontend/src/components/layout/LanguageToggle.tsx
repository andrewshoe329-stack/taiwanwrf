import { useTranslation } from 'react-i18next'

export function LanguageToggle() {
  const { i18n } = useTranslation()

  const toggle = () => {
    const next = i18n.language === 'zh' ? 'en' : 'zh'
    i18n.changeLanguage(next)
    localStorage.setItem('tw-forecast-lang', next)
  }

  return (
    <button
      onClick={toggle}
      className="h-7 min-w-[44px] min-h-[44px] px-2 fs-body font-medium text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] transition-colors flex items-center justify-center"
      aria-label="Switch language"
    >
      {i18n.language === 'zh' ? 'EN' : '中'}
    </button>
  )
}
