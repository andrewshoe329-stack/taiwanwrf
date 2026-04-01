import { useTranslation } from 'react-i18next'

export function LoadingSpinner({ message }: { message?: string }) {
  const { t } = useTranslation()
  return (
    <div className="flex items-center justify-center h-[60vh]" role="status" aria-label={message ?? t('common.loading')}>
      <div className="text-center">
        <div className="w-5 h-5 border-2 border-[var(--color-text-muted)] border-t-transparent rounded-full animate-spin mx-auto mb-3" />
        <p className="text-[var(--color-text-muted)] fs-body">{message ?? t('common.loading')}</p>
      </div>
    </div>
  )
}
