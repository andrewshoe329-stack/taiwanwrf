import React, { useRef, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import {
  degToCompass, formatTimeCst, isCurrentTimestep,
  windColorClass, waveColorClass,
  windType, windTypeColorClass, sailDecision,
  groupByDay,
} from '@/lib/forecast-utils'
import type { SpotRating, WaveRecord, ForecastRecord } from '@/lib/types'

// ── Spot forecast table ─────────────────────────────────────────────────────

interface SpotTableProps {
  ratings: SpotRating[]
  facing: string
  lang?: 'en' | 'zh'
}

export function SpotForecastTable({ ratings, facing, lang = 'en' }: SpotTableProps) {
  const { t } = useTranslation()
  const dayGroups = groupByDay(ratings, lang)
  const allUtcs = ratings.map(r => r.valid_utc)
  const nowRowRef = useRef<HTMLTableRowElement>(null)

  useEffect(() => {
    nowRowRef.current?.scrollIntoView({ block: 'center', behavior: 'smooth' })
  }, [])

  return (
    <div className="overflow-x-auto" style={{ scrollbarWidth: 'thin' }}>
      <table className="w-full border-collapse text-xs" style={{ minWidth: 480 }}>
        <thead>
          <tr className="border-b border-[var(--color-border)]">
            <th className="text-left py-2 pr-2 text-[var(--color-text-muted)] font-normal">{t('spots.time')}</th>
            <th className="text-right py-2 px-2 text-[var(--color-text-muted)] font-normal">{t('common.wind')}</th>
            <th className="text-right py-2 px-2 text-[var(--color-text-muted)] font-normal">{t('spots.swell')}</th>
            <th className="text-right py-2 px-2 text-[var(--color-text-muted)] font-normal">{t('spots.period')}</th>
            <th className="text-right py-2 px-2 text-[var(--color-text-muted)] font-normal">{t('spots.tide')}</th>
            <th className="text-right py-2 pl-2 text-[var(--color-text-muted)] font-normal">{t('spots.rating_label')}</th>
          </tr>
        </thead>
        {dayGroups.map(group => (
          <tbody key={group.dayKey}>
            <tr>
              <td colSpan={6} className="pt-3 pb-1">
                <span className="text-[11px] font-semibold text-[var(--color-text-secondary)] tracking-wide">
                  {group.dayLabel}
                </span>
              </td>
            </tr>
            {group.items.map((r, i) => {
              const isCurrent = isCurrentTimestep(r.valid_utc, allUtcs)
              const wt = r.wind_dir != null ? windType(r.wind_dir, facing) : undefined
              const prevR = i > 0 ? group.items[i - 1] : undefined
              return (
                <tr
                  key={r.valid_utc}
                  ref={isCurrent ? nowRowRef : undefined}
                  className={`border-b border-[var(--color-border)]/30 ${isCurrent ? 'bg-[var(--color-bg-elevated)]' : ''}`}
                >
                  <td className="py-1.5 pr-2">
                    <span className="text-[var(--color-text-secondary)] tabular-nums">
                      {formatTimeCst(r.valid_utc)}
                    </span>
                    {isCurrent && <span className="ml-1 text-[9px] font-medium text-[var(--color-rating-good)] uppercase">now</span>}
                  </td>
                  <td className="text-right py-1.5 px-2 tabular-nums">
                    {r.wind_kt != null ? (
                      <>
                        {r.wind_dir != null && (
                          <span className="inline-block w-3 text-center text-[var(--color-text-muted)]" style={{ transform: `rotate(${r.wind_dir + 180}deg)` }}>
                            {'\u2191'}
                          </span>
                        )}
                        <span className={`font-medium ${windColorClass(r.wind_kt)}`}>
                          {' '}{r.wind_kt.toFixed(0)}
                        </span>
                        <span className="text-[var(--color-text-dim)] ml-0.5">kt</span>
                        {wt && <span className={`ml-1 text-[9px] ${windTypeColorClass(wt)}`}>{wt.slice(0, 3)}</span>}
                        {prevR?.wind_kt != null && <TrendArrow current={r.wind_kt} previous={prevR.wind_kt} />}
                      </>
                    ) : '--'}
                  </td>
                  <td className="text-right py-1.5 px-2 tabular-nums">
                    {r.swell_height != null ? (
                      <>
                        <span className={`font-medium ${waveColorClass(r.swell_height)}`}>
                          {r.swell_height.toFixed(1)}
                        </span>
                        <span className="text-[var(--color-text-dim)] ml-0.5">m</span>
                        {r.swell_dir != null && (
                          <span className="text-[var(--color-text-muted)] ml-1">{degToCompass(r.swell_dir)}</span>
                        )}
                        {prevR?.swell_height != null && <TrendArrow current={r.swell_height} previous={prevR.swell_height} threshold={0.15} />}
                      </>
                    ) : '--'}
                  </td>
                  <td className="text-right py-1.5 px-2 tabular-nums text-[var(--color-text-secondary)]">
                    {r.swell_period != null ? <>{r.swell_period.toFixed(0)}<span className="text-[var(--color-text-dim)] ml-0.5">s</span></> : '--'}
                  </td>
                  <td className="text-right py-1.5 px-2 tabular-nums text-[var(--color-text-secondary)]">
                    {r.tide_height != null ? <>{r.tide_height.toFixed(2)}<span className="text-[var(--color-text-dim)] ml-0.5">m</span></> : '--'}
                  </td>
                  <td className="text-right py-1.5 pl-2">
                    <span className={`inline-block text-[10px] font-medium px-1.5 py-0.5 rounded-full ${ratingBgClass(r.rating)}`}>
                      {t(`rating.${r.rating}`)}
                    </span>
                    <span className="text-[var(--color-text-dim)] ml-1 text-[10px]">{r.score}/14</span>
                  </td>
                </tr>
              )
            })}
          </tbody>
        ))}
      </table>
    </div>
  )
}

// ── Harbour forecast table ──────────────────────────────────────────────────

interface HarbourTableProps {
  records: ForecastRecord[]
  waveRecords: WaveRecord[]
  lang?: 'en' | 'zh'
}

export function HarbourForecastTable({ records, waveRecords, lang = 'en' }: HarbourTableProps) {
  const { t } = useTranslation()
  const dayGroups = groupByDay(records, lang)
  const allUtcs = records.map(r => r.valid_utc)
  const nowRowRef = useRef<HTMLTableRowElement>(null)

  useEffect(() => {
    nowRowRef.current?.scrollIntoView({ block: 'center', behavior: 'smooth' })
  }, [])

  return (
    <div className="overflow-x-auto" style={{ scrollbarWidth: 'thin' }}>
      <table className="w-full border-collapse text-xs" style={{ minWidth: 520 }}>
        <thead>
          <tr className="border-b border-[var(--color-border)]">
            <th className="text-left py-2 pr-2 text-[var(--color-text-muted)] font-normal">{t('harbours_page.time')}</th>
            <th className="text-right py-2 px-2 text-[var(--color-text-muted)] font-normal">{t('common.wind')}</th>
            <th className="text-right py-2 px-2 text-[var(--color-text-muted)] font-normal">{t('harbours_page.direction')}</th>
            <th className="text-right py-2 px-2 text-[var(--color-text-muted)] font-normal">{t('harbours_page.waves')}</th>
            <th className="text-right py-2 px-2 text-[var(--color-text-muted)] font-normal">{t('common.temp')}</th>
            <th className="text-right py-2 px-2 text-[var(--color-text-muted)] font-normal">{t('common.pressure')}</th>
            <th className="text-right py-2 pl-2 text-[var(--color-text-muted)] font-normal">{t('harbours_page.sail_decision')}</th>
          </tr>
        </thead>
        <tbody>
          {dayGroups.map(group => (
            <React.Fragment key={group.dayKey}>
              <tr>
                <td colSpan={7} className="pt-3 pb-1">
                  <span className="text-[11px] font-semibold text-[var(--color-text-secondary)] tracking-wide">
                    {group.dayLabel}
                  </span>
                </td>
              </tr>
              {group.items.map((rec, i) => {
                const wr = waveRecords.find(w => w.valid_utc === rec.valid_utc)
                const isCurrent = isCurrentTimestep(rec.valid_utc, allUtcs)
                const sailDec = rec.wind_kt != null ? sailDecision(rec.wind_kt) : undefined
                const prevRec = i > 0 ? group.items[i - 1] : undefined
                const sailColors = { go: 'text-emerald-400', caution: 'text-amber-400', nogo: 'text-red-400' }
                return (
                  <tr
                    key={rec.valid_utc}
                    ref={isCurrent ? nowRowRef : undefined}
                    className={`border-b border-[var(--color-border)]/30 ${isCurrent ? 'bg-[var(--color-bg-elevated)]' : ''}`}
                  >
                    <td className="py-1.5 pr-2">
                      <span className="text-[var(--color-text-secondary)] tabular-nums">{formatTimeCst(rec.valid_utc)}</span>
                      {isCurrent && <span className="ml-1 text-[9px] font-medium text-[var(--color-rating-good)] uppercase">now</span>}
                    </td>
                    <td className={`text-right py-1.5 px-2 tabular-nums font-medium ${rec.wind_kt != null ? windColorClass(rec.wind_kt) : 'text-[var(--color-text-muted)]'}`}>
                      {rec.wind_kt?.toFixed(0) ?? '--'}
                      {rec.gust_kt != null && <span className="text-[var(--color-text-dim)] font-normal"> G{rec.gust_kt.toFixed(0)}</span>}
                      <span className="text-[var(--color-text-dim)] font-normal ml-0.5">kt</span>
                      {prevRec?.wind_kt != null && rec.wind_kt != null && <TrendArrow current={rec.wind_kt} previous={prevRec.wind_kt} />}
                    </td>
                    <td className="text-right py-1.5 px-2 text-[var(--color-text-secondary)] tabular-nums">
                      {rec.wind_dir != null ? (
                        <>
                          <span className="inline-block w-3 text-center" style={{ transform: `rotate(${rec.wind_dir + 180}deg)` }}>{'\u2191'}</span>
                          {' '}{degToCompass(rec.wind_dir)}
                        </>
                      ) : '--'}
                    </td>
                    <td className={`text-right py-1.5 px-2 tabular-nums ${wr?.wave_height != null ? waveColorClass(wr.wave_height) : 'text-[var(--color-text-muted)]'}`}>
                      {wr?.wave_height != null ? wr.wave_height.toFixed(1) : '--'}
                      <span className="text-[var(--color-text-dim)] ml-0.5">m</span>
                      {wr?.wave_period != null && <span className="text-[var(--color-text-dim)]"> {wr.wave_period.toFixed(0)}s</span>}
                    </td>
                    <td className="text-right py-1.5 px-2 text-[var(--color-text-primary)] tabular-nums">
                      {rec.temp_c?.toFixed(0) ?? '--'}{'\u00B0'}
                    </td>
                    <td className="text-right py-1.5 px-2 text-[var(--color-text-secondary)] tabular-nums">
                      {rec.mslp_hpa?.toFixed(0) ?? '--'}
                    </td>
                    <td className="text-right py-1.5 pl-2">
                      {sailDec && (
                        <span className={`text-[10px] font-medium ${sailColors[sailDec]}`}>
                          {sailDec === 'go' ? '●' : sailDec === 'caution' ? '◐' : '○'}
                        </span>
                      )}
                    </td>
                  </tr>
                )
              })}
            </React.Fragment>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function TrendArrow({ current, previous, threshold = 2 }: { current: number; previous: number; threshold?: number }) {
  const diff = current - previous
  if (Math.abs(diff) < threshold) return null
  return (
    <span className={`ml-0.5 text-[9px] ${diff > 0 ? 'text-red-400/60' : 'text-emerald-400/60'}`}>
      {diff > 0 ? '↑' : '↓'}
    </span>
  )
}

function ratingBgClass(rating: string): string {
  const map: Record<string, string> = {
    firing:    'bg-[var(--color-firing-bg)] text-[var(--color-firing)]',
    good:      'bg-[rgba(94,234,212,0.15)] text-[var(--color-rating-good)]',
    marginal:  'bg-[rgba(251,191,36,0.1)] text-[var(--color-rating-marginal)]',
    poor:      'bg-[var(--color-bg-elevated)] text-[var(--color-rating-poor)]',
    flat:      'bg-[var(--color-bg-elevated)] text-[var(--color-rating-flat)]',
    dangerous: 'bg-[rgba(248,113,113,0.15)] text-[var(--color-rating-dangerous)]',
  }
  return map[rating] ?? 'bg-[var(--color-bg-elevated)] text-[var(--color-text-dim)]'
}
