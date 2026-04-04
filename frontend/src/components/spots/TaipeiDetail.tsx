import { useTranslation } from 'react-i18next'
import { ShareButton } from '@/components/layout/ShareButton'
import { SectionDivider } from '@/components/spots/SectionDivider'
import type { DetailSection } from '@/components/spots/SpotDetail'
import type { CwaObs, ForecastRecord } from '@/lib/types'

function DataCell({ label, value, unit, sub }: {
  label: string; value: string; unit: string; sub?: string
}) {
  return (
    <div className="bg-[var(--color-bg-elevated)] rounded-lg px-2 py-1.5 text-center">
      <p className="fs-compact text-[var(--color-text-muted)] uppercase tracking-wider">{label}</p>
      <p className="fs-label font-semibold text-[var(--color-text-primary)] tabular-nums">
        {value}<span className="fs-compact text-[var(--color-text-muted)] ml-0.5">{unit}</span>
      </p>
      {sub && <p className="fs-compact text-[var(--color-text-dim)]">{sub}</p>}
    </div>
  )
}

interface TaipeiDetailProps {
  cwaObs?: CwaObs | null
  forecastRec?: ForecastRecord | null
  forecastTimeLabel?: string
  section?: DetailSection
  onDeselect: () => void
}

export function TaipeiDetail({ cwaObs, forecastRec, forecastTimeLabel, section = 'all', onDeselect }: TaipeiDetailProps) {
  const { t, i18n } = useTranslation()
  const lang = (i18n.language.startsWith('zh') ? 'zh' : 'en') as 'en' | 'zh'

  const show = (s: number) =>
    section === 'all' ||
    (section === 'live' && s === 3) ||
    (section === 'no-live' && s !== 3) ||
    (section === 'above-timeline' && s <= 3) ||
    (section === 'below-timeline' && s >= 4)

  const warnings = cwaObs?.specialized_warnings?.filter(w => !w.area || w.area.includes('臺北') || w.area.includes('台北')) ?? []

  return (
    <section className="md:px-3 py-3 space-y-3">
      {/* 1. Header */}
      {show(1) && (
        <div className="flex items-center justify-between">
          <h2 className="fs-label font-semibold text-[var(--color-text-primary)]">
            {lang === 'zh' ? '台北' : 'Taipei'}
          </h2>
          <div className="flex items-center gap-1.5">
            <ShareButton locationId="taipei" />
            <button
              onClick={onDeselect}
              className="w-6 h-6 flex items-center justify-center rounded-full hover:bg-[var(--color-bg-elevated)] text-[var(--color-text-muted)]"
              aria-label="Deselect"
            >
              <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M1 1 L9 9 M9 1 L1 9" />
              </svg>
            </button>
          </div>
        </div>
      )}

      {/* 2. Warnings */}
      {show(2) && warnings.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {warnings.map((w, i) => (
            <span key={i} className={`fs-compact px-1.5 py-0.5 rounded ${
              w.type === 'rain' ? 'bg-blue-500/20 text-blue-400' :
              w.type === 'heat' ? 'bg-red-500/20 text-red-400' :
              'bg-cyan-500/20 text-cyan-400'
            }`} title={w.headline || w.description || undefined}>
              {w.severity_level || w.event || w.type}
            </span>
          ))}
        </div>
      )}

      {/* 3. Current conditions from forecast */}
      {show(3) && forecastRec && (
        <>
          <SectionDivider label={
            `${lang === 'zh' ? '天氣' : 'Weather'}${forecastTimeLabel ? ` · ${forecastTimeLabel} CST` : ''}`
          } />
          <div className="grid grid-cols-2 gap-1.5">
            {forecastRec.temp_c != null && (
              <DataCell label={t('common.temp')} value={forecastRec.temp_c.toFixed(0)} unit="°C" />
            )}
            {forecastRec.wind_kt != null && (
              <DataCell
                label={t('common.wind')}
                value={forecastRec.wind_kt.toFixed(0)}
                unit="kt"
                sub={forecastRec.wind_dir != null ? `${forecastRec.wind_dir.toFixed(0)}°` : undefined}
              />
            )}
            {forecastRec.gust_kt != null && (
              <DataCell label={lang === 'zh' ? '陣風' : 'Gust'} value={forecastRec.gust_kt.toFixed(0)} unit="kt" />
            )}
            {forecastRec.precip_mm_6h != null && forecastRec.precip_mm_6h > 0 && (
              <DataCell label={t('common.precip')} value={forecastRec.precip_mm_6h.toFixed(1)} unit="mm" />
            )}
            {forecastRec.mslp_hpa != null && (
              <DataCell label={lang === 'zh' ? '氣壓' : 'Pressure'} value={forecastRec.mslp_hpa.toFixed(0)} unit="hPa" />
            )}
            {forecastRec.humidity_pct != null && (
              <DataCell label={lang === 'zh' ? '濕度' : 'Humidity'} value={forecastRec.humidity_pct.toFixed(0)} unit="%" />
            )}
          </div>
        </>
      )}

      {/* 4. Info */}
      {show(4) && (
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="fs-compact px-1.5 py-0.5 rounded bg-[var(--color-bg-elevated)] text-[var(--color-text-dim)]">
            {lang === 'zh' ? '城市天氣' : 'City weather'}
          </span>
          <span className="fs-compact px-1.5 py-0.5 rounded bg-[var(--color-bg-elevated)] text-[var(--color-text-dim)]">
            25.03°N 121.57°E
          </span>
        </div>
      )}
    </section>
  )
}
