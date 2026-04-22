import { useTranslation } from 'react-i18next'
import { useForecastData } from '@/hooks/useForecastData'

interface Source {
  label: string
  modelId: string | undefined
  ageMs: number
}

function formatAge(ageMs: number, t: (k: string, o?: Record<string, unknown>) => string): string {
  const ageMinutes = Math.floor(ageMs / 60_000)
  const ageHours = Math.floor(ageMs / 3_600_000)
  if (ageMinutes < 5) return t('common.just_now')
  if (ageHours < 1) return t('common.updated_ago', { time: `${ageMinutes}m` })
  if (ageHours < 24) return t('common.updated_ago', { time: `${ageHours}h` })
  return t('common.updated_ago', { time: `${Math.floor(ageHours / 24)}d` })
}

/** Show how long ago forecast data was initialized, based on the freshest available source. */
export function DataFreshness() {
  const { t } = useTranslation()
  const data = useForecastData()
  const now = Date.now()

  const sources: Source[] = []
  const push = (label: string, init?: string, modelId?: string) => {
    if (!init) return
    const ts = new Date(init).getTime()
    if (Number.isNaN(ts)) return
    sources.push({ label, modelId, ageMs: now - ts })
  }
  push('WRF', data.keelung?.meta?.init_utc, data.keelung?.meta?.model_id)
  push('ECMWF', data.ecmwf?.meta?.init_utc, data.ecmwf?.meta?.model_id)
  push('Waves', data.wave?.ecmwf_wave?.meta?.init_utc, data.wave?.ecmwf_wave?.meta?.model_id)

  if (sources.length === 0) return null

  sources.sort((a, b) => a.ageMs - b.ageMs)
  const freshest = sources[0]
  const freshestHours = freshest.ageMs / 3_600_000

  const STALE_H = 12
  const VERY_STALE_H = 24
  const isStale = freshestHours >= STALE_H
  const isVeryStale = freshestHours >= VERY_STALE_H

  const staleSources = sources.filter(s => s.ageMs / 3_600_000 >= STALE_H)
  const title = staleSources.length > 0
    ? staleSources.map(s => `${s.label}: ${formatAge(s.ageMs, t)}`).join(' · ')
    : undefined

  return (
    <span
      className={`fs-compact tabular-nums ${isStale ? 'text-[var(--color-danger)]' : 'text-[var(--color-text-dim)]'} ${isVeryStale ? 'animate-pulse' : ''}`}
      title={title}
    >
      {isStale && <span className="mr-0.5" aria-hidden="true">{'⚠'}</span>}
      {formatAge(freshest.ageMs, t)}
      {freshest.modelId && (
        <span className="ml-1.5">{freshest.modelId}</span>
      )}
      {staleSources.length > 0 && !isStale && (
        <span className="ml-1 text-[var(--color-warn)]" aria-hidden="true">{'·'}</span>
      )}
    </span>
  )
}
