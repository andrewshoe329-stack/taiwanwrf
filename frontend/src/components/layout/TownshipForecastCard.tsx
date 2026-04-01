import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { CwaObs } from '@/lib/types'

interface TownshipForecastCardProps {
  cwaObs: CwaObs | null
  locationId: string | null
}

// Map spot IDs to their CWA county
const SPOT_COUNTY: Record<string, string> = {
  keelung: '基隆市',
  jinshan: '新北市',
  greenbay: '新北市',
  fulong: '新北市',
  daxi: '宜蘭縣',
  doublelions: '宜蘭縣',
  wushih: '宜蘭縣',
  chousui: '宜蘭縣',
}

const COUNTY_EN: Record<string, string> = {
  '基隆市': 'Keelung',
  '新北市': 'New Taipei',
  '宜蘭縣': 'Yilan',
}

function extractElement(elements: Record<string, unknown[]>, name: string): string | null {
  const arr = elements[name] as Array<{ time?: string; value?: string }> | undefined
  if (!arr || arr.length === 0) return null
  return arr[0]?.value ?? null
}

export function TownshipForecastCard({ cwaObs, locationId }: TownshipForecastCardProps) {
  const { i18n } = useTranslation()
  const lang = i18n.language?.startsWith('zh') ? 'zh' : 'en'
  const [expanded, setExpanded] = useState(false)

  const county = SPOT_COUNTY[locationId ?? 'keelung'] ?? '基隆市'

  // Try township_forecasts (3-day) first, then township_forecasts_week
  const forecasts = (cwaObs as unknown as Record<string, unknown>)?.township_forecasts as
    Record<string, { location?: string; elements?: Record<string, unknown[]> }> | undefined
  const weekForecasts = cwaObs?.township_forecasts_week

  const fc = forecasts?.[county] ?? weekForecasts?.[county]
  if (!fc?.elements) return null

  const elements = fc.elements as Record<string, unknown[]>
  const wx = extractElement(elements, 'Wx') ?? extractElement(elements, 'WeatherDescription')
  const minT = extractElement(elements, 'MinT') ?? extractElement(elements, 'MinTemperature')
  const maxT = extractElement(elements, 'MaxT') ?? extractElement(elements, 'MaxTemperature')
  const pop = extractElement(elements, 'PoP12h') ?? extractElement(elements, 'PoP6h')
  const wind = extractElement(elements, 'WS') ?? extractElement(elements, 'WindSpeed')
  const ci = extractElement(elements, 'CI') ?? extractElement(elements, 'Comfort')

  if (!wx && !minT && !maxT) return null

  const countyLabel = lang === 'zh' ? county : COUNTY_EN[county] ?? county

  return (
    <div className="border-b border-[var(--color-border)] py-2 px-1">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between text-left"
      >
        <div className="flex items-center gap-1.5">
          <span className="fs-micro uppercase tracking-wider text-[var(--color-text-dim)]">
            {lang === 'zh' ? 'CWA 預報' : 'CWA Forecast'}
          </span>
          <span className="fs-compact text-[var(--color-text-muted)]">{countyLabel}</span>
        </div>
        <div className="flex items-center gap-2">
          {minT && maxT && (
            <span className="fs-compact text-[var(--color-text-secondary)] font-mono tabular-nums">
              {minT}–{maxT}°C
            </span>
          )}
          {pop && (
            <span className="fs-compact text-blue-400 font-mono tabular-nums">
              {pop}%
            </span>
          )}
          <span className="fs-micro text-[var(--color-text-dim)]">{expanded ? '▲' : '▼'}</span>
        </div>
      </button>

      {expanded && (
        <div className="mt-1.5 space-y-1">
          {wx && (
            <p className="fs-compact text-[var(--color-text-secondary)] leading-relaxed">{wx}</p>
          )}
          <div className="flex flex-wrap gap-x-3 gap-y-0.5 fs-compact text-[var(--color-text-dim)]">
            {minT && maxT && <span>{lang === 'zh' ? '溫度' : 'Temp'}: {minT}–{maxT}°C</span>}
            {pop && <span>{lang === 'zh' ? '降雨' : 'Rain'}: {pop}%</span>}
            {wind && <span>{lang === 'zh' ? '風速' : 'Wind'}: {wind}</span>}
            {ci && <span>{lang === 'zh' ? '舒適度' : 'Comfort'}: {ci}</span>}
          </div>
        </div>
      )}
    </div>
  )
}
