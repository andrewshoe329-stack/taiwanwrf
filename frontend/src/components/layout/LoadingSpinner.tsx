import { useTranslation } from 'react-i18next'

export function LoadingSpinner({ message }: { message?: string }) {
  const { t } = useTranslation()
  return (
    <div className="flex items-center justify-center h-[60vh]">
      <div className="text-center">
        <div className="w-5 h-5 border-2 border-[var(--color-text-muted)] border-t-transparent rounded-full animate-spin mx-auto mb-3" />
        <p className="text-[var(--color-text-muted)] text-xs">{message ?? t('common.loading')}</p>
      </div>
    </div>
  )
}
