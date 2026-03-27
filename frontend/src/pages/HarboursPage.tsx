import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { HARBOURS } from '@/lib/constants'
import { useForecastData } from '@/hooks/useForecastData'
import type { ForecastRecord, WaveRecord } from '@/lib/types'

function toCST(utc: string): string {
  const d = new Date(utc)
  d.setUTCHours(d.getUTCHours() + 8)
  const mm = String(d.getUTCMonth() + 1).padStart(2, '0')
  const dd = String(d.getUTCDate()).padStart(2, '0')
  const hh = String(d.getUTCHours()).padStart(2, '0')
  return `${mm}/${dd} ${hh}:00`
}

export function HarboursPage() {
  const { t, i18n } = useTranslation()
  const lang = (i18n.language.startsWith('zh') ? 'zh' : 'en') as 'en' | 'zh'
  const data = useForecastData()
  const [expandedHarbour, setExpandedHarbour] = useState<string | null>(null)

  if (data.loading) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <div className="text-center">
          <div className="w-5 h-5 border-2 border-[var(--color-text-muted)] border-t-transparent rounded-full animate-spin mx-auto mb-3" />
          <p className="text-[var(--color-text-muted)] text-xs">{t('common.loading')}</p>
        </div>
      </div>
    )
  }

  return (
    <div className="px-4 pt-4 pb-24 max-w-screen-xl mx-auto">
      <h1 className="text-lg font-semibold mb-1 text-[var(--color-text-primary)]">
        {t('harbours_page.title')}
      </h1>
      <p className="text-xs text-[var(--color-text-muted)] mb-5">
        {t('harbours_page.subtitle')}
      </p>

      <div className="space-y-4">
        {HARBOURS.map(harbour => {
          const ecmwf = data.ecmwf_harbours?.[harbour.id]
          const wave = data.wave_harbours?.[harbour.id]
          const ensemble = data.ensemble_harbours?.[harbour.id]

          const records = ecmwf?.records ?? []
          const waveRecords = wave?.ecmwf_wave?.records ?? []

          // Current conditions (first record)
          const windRec: ForecastRecord | undefined = records[0]
          const waveRec: WaveRecord | undefined = waveRecords[0]

          // Sail decision for this harbour
          const windKt = windRec?.wind_kt ?? 0
          let sailDecision: 'go' | 'caution' | 'nogo' = 'caution'
          if (windKt >= 8 && windKt <= 25) sailDecision = 'go'
          else if (windKt > 35 || windKt < 4) sailDecision = 'nogo'

          const decisionBorder = {
            go: 'border-[var(--color-rating-good)]',
            caution: 'border-[var(--color-text-muted)]',
            nogo: 'border-[var(--color-danger)]',
          }

          // Ensemble spread for confidence
          const spread = ensemble?.spread
          const hasSpread = spread && (spread.wind_spread_kt != null || spread.temp_spread_c != null)

          const isExpanded = expandedHarbour === harbour.id
          const hasForecast = records.length > 1

          return (
            <div
              key={harbour.id}
              className={`border rounded-xl p-4 ${decisionBorder[sailDecision]}`}
            >
              {/* Header */}
              <div className="flex items-start justify-between mb-3">
                <div>
                  <h2 className="text-base font-semibold text-[var(--color-text-primary)]">
                    {harbour.name[lang]}
                  </h2>
                  <p className="text-xs text-[var(--color-text-muted)]">
                    {harbour.name[lang === 'en' ? 'zh' : 'en']}
                  </p>
                </div>
                <span className="text-sm font-medium text-[var(--color-text-primary)]">
                  {t(`decision.${sailDecision}`)}
                </span>
              </div>

              {/* Current conditions grid */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <MiniStat
                  label={t('common.wind')}
                  value={windRec?.wind_kt != null ? `${windRec.wind_kt.toFixed(0)}` : '--'}
                  unit="kt"
                  sub={windRec?.gust_kt != null ? `G${windRec.gust_kt.toFixed(0)}` : undefined}
                />
                <MiniStat
                  label={t('harbours_page.direction')}
                  value={windRec?.wind_dir != null ? `${windRec.wind_dir}` : '--'}
                  unit="°"
                />
                <MiniStat
                  label={t('harbours_page.waves')}
                  value={waveRec?.wave_height != null ? waveRec.wave_height.toFixed(1) : '--'}
                  unit="m"
                  sub={waveRec?.wave_period != null ? `${waveRec.wave_period.toFixed(0)}s` : undefined}
                />
                <MiniStat
                  label={t('common.temp')}
                  value={windRec?.temp_c != null ? windRec.temp_c.toFixed(0) : '--'}
                  unit="°C"
                />
              </div>

              {/* Ensemble confidence */}
              {hasSpread && (
                <div className="mt-3 flex items-center gap-3 text-xs text-[var(--color-text-muted)]">
                  <span>{t('harbours_page.model_spread')}:</span>
                  {spread.wind_spread_kt != null && (
                    <span>{t('common.wind')} ±{spread.wind_spread_kt.toFixed(1)} kt</span>
                  )}
                  {spread.temp_spread_c != null && (
                    <span>{t('common.temp')} ±{spread.temp_spread_c.toFixed(1)}°</span>
                  )}
                </div>
              )}

              {/* Expand/collapse forecast toggle */}
              {hasForecast && (
                <button
                  onClick={() => setExpandedHarbour(isExpanded ? null : harbour.id)}
                  className="mt-3 text-xs text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] transition-colors flex items-center gap-1"
                >
                  <svg className={`w-3 h-3 transition-transform ${isExpanded ? 'rotate-180' : ''}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                    <path d="M6 9l6 6 6-6" />
                  </svg>
                  {isExpanded ? t('harbours_page.hide_forecast') : t('harbours_page.show_forecast')}
                </button>
              )}

              {/* Expanded forecast table */}
              {isExpanded && (
                <div className="mt-3 overflow-x-auto" style={{ scrollbarWidth: 'none' }}>
                  <table className="w-full border-collapse text-xs" style={{ minWidth: 400 }}>
                    <thead>
                      <tr className="border-b border-[var(--color-border)]">
                        <th className="text-left py-2 pr-2 text-[var(--color-text-muted)] font-normal">{t('harbours_page.time')}</th>
                        <th className="text-right py-2 px-2 text-[var(--color-text-muted)] font-normal">{t('common.wind')}</th>
                        <th className="text-right py-2 px-2 text-[var(--color-text-muted)] font-normal">Dir</th>
                        <th className="text-right py-2 px-2 text-[var(--color-text-muted)] font-normal">{t('harbours_page.waves')}</th>
                        <th className="text-right py-2 px-2 text-[var(--color-text-muted)] font-normal">{t('common.temp')}</th>
                        <th className="text-right py-2 pl-2 text-[var(--color-text-muted)] font-normal">{t('common.pressure')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {records.map((rec, i) => {
                        const wr = waveRecords[i]
                        return (
                          <tr key={rec.valid_utc} className="border-b border-[var(--color-border)]/50">
                            <td className="py-1.5 pr-2">
                              <span className="text-[var(--color-text-secondary)] tabular-nums">{toCST(rec.valid_utc)}</span>
                              {i === 0 && (
                                <span className="ml-1 text-[10px] text-[var(--color-text-dim)]">CST</span>
                              )}
                            </td>
                            <td className="text-right py-1.5 px-2 text-[var(--color-text-primary)] tabular-nums">
                              {rec.wind_kt?.toFixed(0) ?? '--'}
                              {rec.gust_kt != null && (
                                <span className="text-[var(--color-text-dim)]"> G{rec.gust_kt.toFixed(0)}</span>
                              )}
                              <span className="text-[var(--color-text-dim)] ml-0.5">kt</span>
                            </td>
                            <td className="text-right py-1.5 px-2 text-[var(--color-text-secondary)] tabular-nums">
                              {rec.wind_dir != null ? `${rec.wind_dir}°` : '--'}
                            </td>
                            <td className="text-right py-1.5 px-2 text-[var(--color-text-primary)] tabular-nums">
                              {wr?.wave_height != null ? wr.wave_height.toFixed(1) : '--'}
                              <span className="text-[var(--color-text-dim)] ml-0.5">m</span>
                              {wr?.wave_period != null && (
                                <span className="text-[var(--color-text-dim)]"> {wr.wave_period.toFixed(0)}s</span>
                              )}
                            </td>
                            <td className="text-right py-1.5 px-2 text-[var(--color-text-primary)] tabular-nums">
                              {rec.temp_c?.toFixed(0) ?? '--'}°
                            </td>
                            <td className="text-right py-1.5 pl-2 text-[var(--color-text-secondary)] tabular-nums">
                              {rec.mslp_hpa?.toFixed(0) ?? '--'}
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* No harbour data fallback */}
      {!data.ecmwf_harbours && !data.wave_harbours && (
        <div className="border border-[var(--color-border)] rounded-xl p-8 text-center mt-4">
          <p className="text-sm text-[var(--color-text-muted)]">
            {t('harbours_page.no_data')}
          </p>
        </div>
      )}
    </div>
  )
}

function MiniStat({ label, value, unit, sub }: { label: string; value: string; unit: string; sub?: string }) {
  return (
    <div className="bg-[var(--color-bg-elevated)] rounded-lg px-3 py-2">
      <p className="text-[10px] text-[var(--color-text-muted)] uppercase tracking-wider mb-0.5">{label}</p>
      <p className="text-base font-semibold text-[var(--color-text-primary)] tabular-nums">
        {value}
        <span className="text-xs text-[var(--color-text-muted)] ml-0.5">{unit}</span>
      </p>
      {sub && <p className="text-[10px] text-[var(--color-text-dim)]">{sub}</p>}
    </div>
  )
}
