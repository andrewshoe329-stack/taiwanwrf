import { useTranslation } from 'react-i18next'
import { useForecastData } from '@/hooks/useForecastData'

/** Show how long ago the forecast data was initialized. */
export function DataFreshness() {
  const { t } = useTranslation()
  const data = useForecastData()

  const initUtc = data.keelung?.meta?.init_utc ?? data.ecmwf?.meta?.init_utc
  if (!initUtc) return null

  const ageMs = Date.now() - new Date(initUtc).getTime()
  const ageHours = Math.floor(ageMs / 3_600_000)
  const ageMinutes = Math.floor(ageMs / 60_000)

  let timeStr: string
  if (ageMinutes < 5) timeStr = t('common.just_now')
  else if (ageHours < 1) timeStr = t('common.updated_ago', { time: `${ageMinutes}m` })
  else if (ageHours < 24) timeStr = t('common.updated_ago', { time: `${ageHours}h` })
  else timeStr = t('common.updated_ago', { time: `${Math.floor(ageHours / 24)}d` })

  const isStale = ageHours >= 12
  const isVeryStale = ageHours >= 24

  return (
    <span className={`fs-compact tabular-nums ${isStale ? 'text-[var(--color-danger)]' : 'text-[var(--color-text-dim)]'} ${isVeryStale ? 'animate-pulse' : ''}`}>
      {isStale && <span className="mr-0.5" aria-hidden="true">{'\u26A0'}</span>}
      {timeStr}
      {data.keelung?.meta?.model_id && (
        <span className="ml-1.5">{data.keelung.meta.model_id}</span>
      )}
    </span>
  )
}
