import { useTranslation } from 'react-i18next'
import { useForecastData } from '@/hooks/useForecastData'

export function NowPage() {
  const { t } = useTranslation()
  const data = useForecastData()

  if (data.loading) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <p className="text-[var(--color-text-muted)] text-sm">{t('common.loading')}</p>
      </div>
    )
  }

  return (
    <div className="min-h-screen">
      {/* Map + wind particles will go here */}
      <div className="h-[60vh] bg-[var(--color-bg-card)] flex items-center justify-center border-b border-[var(--color-border)]">
        <p className="text-[var(--color-text-dim)] text-sm">Map + Wind Particles</p>
      </div>

      {/* Timeline scrubber will go here */}
      <div className="h-16 bg-[var(--color-bg-elevated)] border-b border-[var(--color-border)] flex items-center justify-center">
        <p className="text-[var(--color-text-dim)] text-sm">Timeline Scrubber</p>
      </div>

      {/* Detail panels below the fold */}
      <div className="px-4 py-6 max-w-screen-xl mx-auto space-y-6">
        {/* Decision Banner */}
        <div className="border border-[var(--color-border)] rounded-xl p-5">
          <p className="text-[var(--color-text-muted)] text-xs uppercase tracking-wider mb-2">
            {t('decision.go')}
          </p>
          <p className="text-[var(--color-text-primary)] text-lg font-medium">
            Forecast data loaded: {data.keelung?.records?.length ?? 0} timesteps
          </p>
        </div>

        {/* AI Summary placeholder */}
        <div className="border border-[var(--color-border)] rounded-xl p-5">
          <p className="text-[var(--color-text-muted)] text-xs uppercase tracking-wider mb-2">
            {t('ai.title')}
          </p>
          <p className="text-[var(--color-text-secondary)] text-sm">
            AI summary will render here
          </p>
        </div>
      </div>
    </div>
  )
}
