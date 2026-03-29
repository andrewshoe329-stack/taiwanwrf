import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useForecastData } from '@/hooks/useForecastData'

/** Prominent banner showing active CWA weather warnings. */
export function WeatherWarnings() {
  const { i18n } = useTranslation()
  const lang = i18n.language.startsWith('zh') ? 'zh' : 'en'
  const data = useForecastData()
  const [dismissed, setDismissed] = useState<Set<string>>(new Set())

  const warnings = data.cwa_obs?.warnings
  if (!warnings?.length) return null

  // Filter to non-expired, non-dismissed warnings
  const now = new Date()
  const active = warnings.filter(w => {
    if (dismissed.has(w.issued_utc)) return false
    if (w.expires_utc && new Date(w.expires_utc) < now) return false
    return true
  })

  if (!active.length) return null

  return (
    <div className="space-y-2 mx-4 md:mx-0 mb-4">
      {active.map(w => {
        const isSevere = w.severity === 'warning' || w.severity === 'severe'
        return (
          <div
            key={w.issued_utc}
            className={`flex items-start gap-3 px-4 py-3 rounded-xl border ${
              isSevere
                ? 'bg-red-500/10 border-red-500/30 text-red-400'
                : 'bg-amber-500/10 border-amber-500/30 text-amber-400'
            }`}
          >
            <span className="text-base shrink-0 mt-0.5">{isSevere ? '\u26A0' : '\u26A0'}</span>
            <div className="flex-1 min-w-0">
              <p className="text-xs font-medium">
                {w.type}{w.area ? ` \u2014 ${w.area}` : ''}
              </p>
              <p className={`text-xs mt-1 leading-relaxed ${
                isSevere ? 'text-red-400/80' : 'text-amber-400/80'
              }`}>
                {w.description}
              </p>
            </div>
            <button
              onClick={() => setDismissed(prev => new Set(prev).add(w.issued_utc))}
              className="shrink-0 text-xs opacity-50 hover:opacity-100 transition-opacity"
              aria-label={lang === 'zh' ? '關閉' : 'Dismiss'}
            >
              {'\u2715'}
            </button>
          </div>
        )
      })}
    </div>
  )
}
