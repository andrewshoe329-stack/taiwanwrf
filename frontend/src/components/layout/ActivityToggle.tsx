import { useTranslation } from 'react-i18next'
import { useActivity } from '@/hooks/useActivity'

export function ActivityToggle() {
  const { t } = useTranslation()
  const { activity, toggle } = useActivity()

  return (
    <button
      onClick={toggle}
      className="flex items-center h-7 rounded-full border border-[var(--color-border-active)] overflow-hidden text-xs font-medium transition-colors"
      aria-label="Toggle sailing/surfing mode"
    >
      <span
        className={`px-2.5 py-1 transition-colors ${
          activity === 'sail'
            ? 'bg-[var(--color-text-primary)] text-black'
            : 'text-[var(--color-text-muted)]'
        }`}
      >
        {t('activity.sail')}
      </span>
      <span
        className={`px-2.5 py-1 transition-colors ${
          activity === 'surf'
            ? 'bg-[var(--color-text-primary)] text-black'
            : 'text-[var(--color-text-muted)]'
        }`}
      >
        {t('activity.surf')}
      </span>
    </button>
  )
}
