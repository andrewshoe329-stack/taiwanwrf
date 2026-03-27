import { useTranslation } from 'react-i18next'

export function SpotsPage() {
  const { t } = useTranslation()

  return (
    <div className="px-4 py-6 max-w-screen-xl mx-auto">
      <h1 className="text-lg font-semibold mb-6">{t('spots.title')}</h1>
      <div className="border border-[var(--color-border)] rounded-xl p-5">
        <p className="text-[var(--color-text-muted)] text-sm">
          Spot heatmap, rankings, and cards will render here
        </p>
      </div>
    </div>
  )
}
