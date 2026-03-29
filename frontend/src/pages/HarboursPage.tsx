import React, { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { HARBOURS } from '@/lib/constants'
import { useForecastData } from '@/hooks/useForecastData'
import { LoadingSpinner } from '@/components/layout/LoadingSpinner'
import {
  degToCompass, formatTimeCst,
  isCurrentTimestep, windColorClass, waveColorClass, sailDecision,
  groupByDay,
} from '@/lib/forecast-utils'
import type { ForecastRecord, WaveRecord } from '@/lib/types'

export function HarboursPage() {
  const { t, i18n } = useTranslation()
  const lang = (i18n.language.startsWith('zh') ? 'zh' : 'en') as 'en' | 'zh'
  const data = useForecastData()
  const [collapsedHarbour, setCollapsedHarbour] = useState<Record<string, boolean>>({})

  if (data.loading) {
    return <LoadingSpinner />
  }

  return (
    <div className="px-4 pt-4 pb-24 max-w-screen-xl mx-auto">
      <h1 className="text-lg font-semibold mb-1 text-[var(--color-text-primary)]">
        {t('harbours_page.title')}
      </h1>
      <p className="text-xs text-[var(--color-text-muted)] mb-5">
        {t('harbours_page.subtitle')}
      </p>

      <div className="space-y-6">
        {HARBOURS.map(harbour => {
          const records = data.ecmwf?.records ?? []
          const waveRecords = data.wave?.ecmwf_wave?.records ?? []
          const ensemble = data.ensemble

          // Current conditions (first record)
          const windRec: ForecastRecord | undefined = records[0]
          const waveRec: WaveRecord | undefined = waveRecords[0]

          // Sail decision for this harbour
          const windKt = windRec?.wind_kt ?? 0
          const sailDec = sailDecision(windKt)

          const decisionBorder = {
            go: 'border-[var(--color-rating-good)]',
            caution: 'border-[var(--color-text-muted)]',
            nogo: 'border-[var(--color-danger)]',
          }

          // Ensemble spread for confidence
          const spread = ensemble?.spread
          const hasSpread = spread && (spread.wind_spread_kt != null || spread.temp_spread_c != null)

          const isCollapsed = collapsedHarbour[harbour.id] === true
          const hasForecast = records.length > 1
          const allUtcs = records.map(r => r.valid_utc)
          const dayGroups = groupByDay(records, lang)

          return (
            <div
              key={harbour.id}
              className={`border rounded-xl p-4 ${decisionBorder[sailDec]}`}
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
                  {t(`decision.${sailDec}`)}
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
                  value={windRec?.wind_dir != null ? degToCompass(windRec.wind_dir) : '--'}
                  unit={windRec?.wind_dir != null ? `${windRec.wind_dir}°` : ''}
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
                    <span>{t('common.wind')} +/-{spread.wind_spread_kt.toFixed(1)} kt</span>
                  )}
                  {spread.temp_spread_c != null && (
                    <span>{t('common.temp')} +/-{spread.temp_spread_c.toFixed(1)}{'\u00B0'}</span>
                  )}
                </div>
              )}

              {/* Forecast timeline — visible by default */}
              {hasForecast && (
                <>
                  <div className="mt-4 flex items-center justify-between">
                    <h3 className="text-xs font-medium text-[var(--color-text-secondary)] uppercase tracking-wider">
                      {t('harbours_page.forecast_timeline')}
                    </h3>
                    <button
                      onClick={() => setCollapsedHarbour(prev => ({ ...prev, [harbour.id]: !prev[harbour.id] }))}
                      className="text-xs text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] transition-colors flex items-center gap-1"
                    >
                      <svg className={`w-3 h-3 transition-transform ${isCollapsed ? '' : 'rotate-180'}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                        <path d="M6 9l6 6 6-6" />
                      </svg>
                      {isCollapsed ? t('harbours_page.show_forecast') : t('harbours_page.hide_forecast')}
                    </button>
                  </div>

                  {!isCollapsed && (
                    <div className="mt-2 overflow-x-auto" style={{ scrollbarWidth: 'thin' }}>
                      <table className="w-full border-collapse text-xs" style={{ minWidth: 480 }}>
                        <thead>
                          <tr className="border-b border-[var(--color-border)]">
                            <th className="text-left py-2 pr-2 text-[var(--color-text-muted)] font-normal">{t('harbours_page.time')}</th>
                            <th className="text-right py-2 px-2 text-[var(--color-text-muted)] font-normal">{t('common.wind')}</th>
                            <th className="text-right py-2 px-2 text-[var(--color-text-muted)] font-normal">{t('harbours_page.direction')}</th>
                            <th className="text-right py-2 px-2 text-[var(--color-text-muted)] font-normal">{t('harbours_page.waves')}</th>
                            <th className="text-right py-2 px-2 text-[var(--color-text-muted)] font-normal">{t('common.temp')}</th>
                            <th className="text-right py-2 pl-2 text-[var(--color-text-muted)] font-normal">{t('common.pressure')}</th>
                          </tr>
                        </thead>
                        <tbody>
                          {dayGroups.map(group => (
                            <React.Fragment key={group.dayKey}>
                              {/* Day header row */}
                              <tr>
                                <td colSpan={6} className="pt-3 pb-1">
                                  <span className="text-[11px] font-semibold text-[var(--color-text-secondary)] tracking-wide">
                                    {group.dayLabel}
                                  </span>
                                </td>
                              </tr>
                              {group.items.map(rec => {
                                const wr = waveRecords.find(w => w.valid_utc === rec.valid_utc)
                                const isCurrent = isCurrentTimestep(rec.valid_utc, allUtcs)
                                return (
                                  <tr
                                    key={rec.valid_utc}
                                    className={`border-b border-[var(--color-border)]/30 ${isCurrent ? 'bg-[var(--color-bg-elevated)]' : ''}`}
                                  >
                                    <td className="py-1.5 pr-2">
                                      <span className="text-[var(--color-text-secondary)] tabular-nums">
                                        {formatTimeCst(rec.valid_utc)}
                                      </span>
                                      {isCurrent && (
                                        <span className="ml-1 text-[9px] font-medium text-[var(--color-rating-good)] uppercase">now</span>
                                      )}
                                    </td>
                                    <td className={`text-right py-1.5 px-2 tabular-nums font-medium ${rec.wind_kt != null ? windColorClass(rec.wind_kt) : 'text-[var(--color-text-muted)]'}`}>
                                      {rec.wind_kt?.toFixed(0) ?? '--'}
                                      {rec.gust_kt != null && (
                                        <span className="text-[var(--color-text-dim)] font-normal"> G{rec.gust_kt.toFixed(0)}</span>
                                      )}
                                      <span className="text-[var(--color-text-dim)] font-normal ml-0.5">kt</span>
                                    </td>
                                    <td className="text-right py-1.5 px-2 text-[var(--color-text-secondary)] tabular-nums">
                                      {rec.wind_dir != null ? (
                                        <>
                                          <span className="inline-block w-3 text-center" style={{ transform: `rotate(${rec.wind_dir + 180}deg)` }}>
                                            {'\u2191'}
                                          </span>
                                          {' '}{degToCompass(rec.wind_dir)}
                                        </>
                                      ) : '--'}
                                    </td>
                                    <td className={`text-right py-1.5 px-2 tabular-nums ${wr?.wave_height != null ? waveColorClass(wr.wave_height) : 'text-[var(--color-text-muted)]'}`}>
                                      {wr?.wave_height != null ? wr.wave_height.toFixed(1) : '--'}
                                      <span className="text-[var(--color-text-dim)] ml-0.5">m</span>
                                      {wr?.wave_period != null && (
                                        <span className="text-[var(--color-text-dim)]"> {wr.wave_period.toFixed(0)}s</span>
                                      )}
                                    </td>
                                    <td className="text-right py-1.5 px-2 text-[var(--color-text-primary)] tabular-nums">
                                      {rec.temp_c?.toFixed(0) ?? '--'}{'\u00B0'}
                                    </td>
                                    <td className="text-right py-1.5 pl-2 text-[var(--color-text-secondary)] tabular-nums">
                                      {rec.mslp_hpa?.toFixed(0) ?? '--'}
                                    </td>
                                  </tr>
                                )
                              })}
                            </React.Fragment>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </>
              )}
            </div>
          )
        })}
      </div>

      {/* No harbour data fallback */}
      {!data.ecmwf && !data.wave && (
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
