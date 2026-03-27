import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { HARBOURS } from '@/lib/constants'
import { useForecastData } from '@/hooks/useForecastData'
import type { ForecastRecord, WaveRecord } from '@/lib/types'

function toCST(utc: string): Date {
  const d = new Date(utc)
  d.setUTCHours(d.getUTCHours() + 8)
  return d
}

function formatTime(utc: string): string {
  const d = toCST(utc)
  const hh = String(d.getUTCHours()).padStart(2, '0')
  return `${hh}:00`
}

function formatDayHeader(utc: string, lang: 'en' | 'zh'): string {
  const d = toCST(utc)
  const weekdaysEn = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
  const weekdaysZh = ['日', '一', '二', '三', '四', '五', '六']
  const mm = String(d.getUTCMonth() + 1).padStart(2, '0')
  const dd = String(d.getUTCDate()).padStart(2, '0')
  const dayName = lang === 'zh' ? weekdaysZh[d.getUTCDay()] : weekdaysEn[d.getUTCDay()]
  return lang === 'zh' ? `${mm}/${dd} (${dayName})` : `${dayName} ${mm}/${dd}`
}

function getDayKey(utc: string): string {
  const d = toCST(utc)
  return `${d.getUTCFullYear()}-${d.getUTCMonth()}-${d.getUTCDate()}`
}

function degToCompass(deg: number): string {
  const dirs = ['N','NNE','NE','ENE','E','ESE','SE','SSE','S','SSW','SW','WSW','W','WNW','NW','NNW']
  return dirs[Math.round(deg / 22.5) % 16]
}

/** Return a Tailwind text color class based on wind speed (Beaufort-ish scale). */
function windColor(kt: number): string {
  if (kt >= 34) return 'text-red-400'
  if (kt >= 22) return 'text-orange-400'
  if (kt >= 17) return 'text-yellow-400'
  if (kt >= 11) return 'text-emerald-400'
  if (kt >= 7)  return 'text-sky-400'
  return 'text-[var(--color-text-muted)]'
}

/** Return a Tailwind text color class based on wave height. */
function waveColor(m: number): string {
  if (m >= 3.0) return 'text-red-400'
  if (m >= 2.0) return 'text-orange-400'
  if (m >= 1.0) return 'text-sky-400'
  return 'text-[var(--color-text-muted)]'
}

/** Check if a timestamp is "now" (closest past record). */
function isCurrentTimestep(utc: string, allUtcs: string[]): boolean {
  const now = Date.now()
  let closest = 0
  let closestDiff = Infinity
  for (let i = 0; i < allUtcs.length; i++) {
    const t = new Date(allUtcs[i]).getTime()
    const diff = now - t
    if (diff >= 0 && diff < closestDiff) {
      closestDiff = diff
      closest = i
    }
  }
  return allUtcs[closest] === utc
}

/** Group records by CST day. Returns array of [dayKey, dayLabel, indices]. */
function groupByDay(records: ForecastRecord[], lang: 'en' | 'zh'): Array<{ dayKey: string; dayLabel: string; indices: number[] }> {
  const groups: Array<{ dayKey: string; dayLabel: string; indices: number[] }> = []
  let currentKey = ''
  for (let i = 0; i < records.length; i++) {
    const key = getDayKey(records[i].valid_utc)
    if (key !== currentKey) {
      currentKey = key
      groups.push({ dayKey: key, dayLabel: formatDayHeader(records[i].valid_utc, lang), indices: [] })
    }
    groups[groups.length - 1].indices.push(i)
  }
  return groups
}

export function HarboursPage() {
  const { t, i18n } = useTranslation()
  const lang = (i18n.language.startsWith('zh') ? 'zh' : 'en') as 'en' | 'zh'
  const data = useForecastData()
  const [collapsedHarbour, setCollapsedHarbour] = useState<Record<string, boolean>>({})

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

      <div className="space-y-6">
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

          const isCollapsed = collapsedHarbour[harbour.id] === true
          const hasForecast = records.length > 1
          const allUtcs = records.map(r => r.valid_utc)
          const dayGroups = groupByDay(records, lang)

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
                            <>
                              {/* Day header row */}
                              <tr key={`day-${group.dayKey}`}>
                                <td colSpan={6} className="pt-3 pb-1">
                                  <span className="text-[11px] font-semibold text-[var(--color-text-secondary)] tracking-wide">
                                    {group.dayLabel}
                                  </span>
                                </td>
                              </tr>
                              {group.indices.map(i => {
                                const rec = records[i]
                                const wr = waveRecords.find(w => w.valid_utc === rec.valid_utc) ?? waveRecords[i]
                                const isCurrent = isCurrentTimestep(rec.valid_utc, allUtcs)
                                return (
                                  <tr
                                    key={rec.valid_utc}
                                    className={`border-b border-[var(--color-border)]/30 ${isCurrent ? 'bg-[var(--color-bg-elevated)]' : ''}`}
                                  >
                                    <td className="py-1.5 pr-2">
                                      <span className="text-[var(--color-text-secondary)] tabular-nums">
                                        {formatTime(rec.valid_utc)}
                                      </span>
                                      {isCurrent && (
                                        <span className="ml-1 text-[9px] font-medium text-[var(--color-rating-good)] uppercase">now</span>
                                      )}
                                    </td>
                                    <td className={`text-right py-1.5 px-2 tabular-nums font-medium ${rec.wind_kt != null ? windColor(rec.wind_kt) : 'text-[var(--color-text-muted)]'}`}>
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
                                    <td className={`text-right py-1.5 px-2 tabular-nums ${wr?.wave_height != null ? waveColor(wr.wave_height) : 'text-[var(--color-text-muted)]'}`}>
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
                            </>
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
