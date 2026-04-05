import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { SwellCompass } from '@/components/spots/SwellCompass'
import { ScoreBreakdownTooltip } from '@/components/spots/ScoreBreakdownTooltip'
import { BestTimeWindows } from '@/components/spots/BestTimeWindows'
import { ShareButton } from '@/components/layout/ShareButton'
import { LiveObsCard } from '@/components/spots/LiveObsCard'
import { SectionDivider } from '@/components/spots/SectionDivider'
import { TideSparkline } from '@/components/charts/TideSparkline'
import { AccuracyTrend } from '@/components/charts/AccuracyTrend'
import { degToCompass, windType, seaComfortStars, seaComfortLabel } from '@/lib/forecast-utils'
import { SPOT_COUNTY } from '@/lib/constants'
import type { SpotInfo, SpotRating, SpotForecast, TidePrediction, TideExtremum, EnsembleData, AccuracyEntry, CwaObs } from '@/lib/types'

const RATING_COLORS: Record<string, string> = {
  firing: '#f97316', great: '#22c55e', good: '#4ade80',
  marginal: '#facc15', poor: '#ef4444', flat: '#6b7280', dangerous: '#dc2626',
}

function InfoPill({ label, value }: { label: string; value?: string }) {
  return (
    <span className="inline-flex items-center gap-1 fs-compact border border-[var(--color-border)] rounded-full px-2.5 py-0.5 text-[var(--color-text-muted)]">
      <span>{label}</span>
      {value && <span className="text-[var(--color-text-secondary)]">{value}</span>}
    </span>
  )
}

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

/** Get the most recent accuracy entry (by init_utc). */
function latestAccuracy(entries: AccuracyEntry[] | null): AccuracyEntry | null {
  if (!entries?.length) return null
  return entries.reduce((a, b) => (a.init_utc > b.init_utc ? a : b))
}

export type DetailSection = 'all' | 'live' | 'no-live' | 'above-timeline' | 'below-timeline'

interface SpotDetailProps {
  spotInfo: SpotInfo
  currentRating: SpotRating | null
  locationForecast: SpotForecast | null
  tidePredictions: TidePrediction[]
  tideExtrema: TideExtremum[]
  forecastTimeLabel: string
  nowMs: number | undefined
  ensemble: EnsembleData | null
  accuracy: AccuracyEntry[] | null
  cwaObs: CwaObs | null
  section?: DetailSection
  collapsibleLiveObs?: boolean
  onDeselect: () => void
}

export function SpotDetail({
  spotInfo,
  currentRating,
  locationForecast,
  tidePredictions,
  tideExtrema,
  forecastTimeLabel,
  nowMs,
  ensemble,
  accuracy,
  cwaObs,
  section = 'all',
  collapsibleLiveObs = false,
  onDeselect,
}: SpotDetailProps) {
  const { t, i18n } = useTranslation()
  const lang = (i18n.language.startsWith('zh') ? 'zh' : 'en') as 'en' | 'zh'
  const [scoreTooltipOpen, setScoreTooltipOpen] = useState(false)

  // Section visibility: 1=header, 2=warnings, 3=live, 4=forecast, 5=spotinfo, 6=accuracy
  const show = (s: number) =>
    section === 'all' ||
    (section === 'live' && s === 3) ||
    (section === 'no-live' && s !== 3) ||
    (section === 'above-timeline' && s <= 3) ||
    (section === 'below-timeline' && s >= 4)

  const warnings = cwaObs?.specialized_warnings?.filter(w => {
    const county = SPOT_COUNTY[spotInfo.id]
    return !county || !w.area || w.area.includes(county)
  }) ?? []
  const hasWarnings = warnings.length > 0 || !!currentRating?.squall_risk

  const latest = latestAccuracy(accuracy)
  const hasAccuracySection = !!(ensemble?.spread || latest || (accuracy && accuracy.length >= 2))

  return (
    <section className="space-y-3 md:px-3 py-3">
      {/* ── 1. Header ────────────────────────────────────────────────── */}
      {show(1) && (
        <div className="flex items-center justify-between">
          <h2 className="fs-label font-semibold text-[var(--color-text-primary)]">
            {spotInfo.name[lang]}
            <span className="text-[var(--color-text-muted)] ml-1.5 fs-body font-normal">
              {spotInfo.name[lang === 'en' ? 'zh' : 'en']}
            </span>
          </h2>
          <div className="flex items-center gap-1.5">
            <ShareButton locationId={spotInfo.id} />
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

      {/* ── 2. Warnings ──────────────────────────────────────────────── */}
      {show(2) && hasWarnings && (
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
          {currentRating?.squall_risk && (
            <span className="fs-compact px-1.5 py-0.5 rounded bg-red-500/30 text-red-300 font-semibold animate-pulse">
              {t('common.squall_risk', 'Squall Risk')}
            </span>
          )}
        </div>
      )}

      {/* ── 3. Live conditions ───────────────────────────────────────── */}
      {show(3) && (
        <>
          <LiveObsCard spotId={spotInfo.id} collapsible={collapsibleLiveObs} />
          {currentRating?.wind_dir != null && spotInfo.facing && (
            <span className="fs-compact text-[var(--color-text-muted)]">
              {windType(currentRating.wind_dir, spotInfo.facing)}
            </span>
          )}
        </>
      )}

      {/* ── 4. Forecast ──────────────────────────────────────────────── */}
      {show(4) && currentRating && (
        <>
          <SectionDivider label={
            `${t('common.forecast') || 'Forecast'}${forecastTimeLabel ? ` · ${forecastTimeLabel} CST` : ''}`
          } />
          <div className="space-y-2">
            {/* Rating badge — time-dependent, belongs with forecast */}
            {currentRating.rating && (
              <div className="flex items-center gap-1.5">
                <div className="relative">
                  <button
                    onClick={() => setScoreTooltipOpen(!scoreTooltipOpen)}
                    className="fs-compact font-medium capitalize px-1.5 py-0.5 rounded"
                    style={{
                      color: RATING_COLORS[currentRating.rating] ?? '#6b7280',
                      backgroundColor: (RATING_COLORS[currentRating.rating] ?? '#6b7280') + '20',
                    }}
                  >
                    {currentRating.rating} {currentRating.score != null ? `${currentRating.score}` : ''}
                  </button>
                  {scoreTooltipOpen && currentRating.score_breakdown && (
                    <div className="absolute left-0 top-7 z-50">
                      <ScoreBreakdownTooltip rating={currentRating} onClose={() => setScoreTooltipOpen(false)} />
                    </div>
                  )}
                </div>
              </div>
            )}

            <div className="flex justify-center">
              <SwellCompass
                facing={spotInfo.facing}
                optSwell={spotInfo.opt_swell}
                swellDir={currentRating.swell_dir}
                swellHeight={currentRating.swell_height}
                size={100}
              />
            </div>
            <div className="grid grid-cols-2 gap-1.5">
              <DataCell
                label={t('common.wind')}
                value={`${currentRating.wind_kt?.toFixed(0) ?? '--'}`}
                unit="kt"
                sub={currentRating.wind_dir != null ? degToCompass(currentRating.wind_dir) : undefined}
              />
              <DataCell
                label={t('common.swell')}
                value={`${currentRating.swell_height?.toFixed(1) ?? '--'}`}
                unit="m"
                sub={currentRating.swell_dir != null ? degToCompass(currentRating.swell_dir) : undefined}
              />
              <DataCell
                label={t('spots.period')}
                value={`${currentRating.swell_period?.toFixed(0) ?? '--'}`}
                unit="s"
              />
              <DataCell
                label={t('common.tide')}
                value={`${currentRating.tide_height?.toFixed(2) ?? '--'}`}
                unit="m"
              />
              {currentRating.sea_comfort != null && (
                <DataCell
                  label={t('common.sea_state')}
                  value={seaComfortStars(currentRating.sea_comfort)}
                  unit=""
                  sub={seaComfortLabel(currentRating.sea_comfort) ?? undefined}
                />
              )}
            </div>
            {tidePredictions.length > 0 && (
              <TideSparkline
                predictions={tidePredictions}
                extrema={tideExtrema}
                nowMs={nowMs}
              />
            )}
            {locationForecast && <BestTimeWindows spotForecast={locationForecast} />}
          </div>
        </>
      )}

      {/* ── 5. Spot info & webcams ───────────────────────────────────── */}
      {show(5) && (
        <>
          <SectionDivider label={lang === 'zh' ? '浪點資訊' : 'Spot info'} />
          <div className="flex flex-wrap items-center gap-1.5">
            <InfoPill label={t('spots.facing')} value={spotInfo.facing} />
            <InfoPill label={t('spots.optimal_wind')} value={spotInfo.opt_wind.join(', ')} />
            {spotInfo.webcams?.map((cam, i) => (
              <a
                key={i}
                href={cam.url}
                target="_blank"
                rel="noopener noreferrer"
                title={cam.label}
                className="w-7 h-7 flex items-center justify-center rounded-full bg-[var(--color-bg-elevated)] text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] transition-colors"
              >
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M23 7l-7 5 7 5V7z" /><rect x="1" y="5" width="15" height="14" rx="2" ry="2" />
                </svg>
              </a>
            ))}
          </div>
        </>
      )}

      {/* ── 6. Model & accuracy ──────────────────────────────────────── */}
      {show(6) && hasAccuracySection && (
        <>
          <SectionDivider label={lang === 'zh' ? '模型準確度' : 'Model accuracy'} />
          <div className="bg-[var(--color-bg-elevated)]/30 rounded-lg p-2 space-y-2">
            {ensemble?.spread && (
              <div className="flex flex-wrap gap-1.5">
                {(() => {
                  const ws = ensemble.spread.wind_spread_kt ?? 99
                  const level = ws < 5 ? 'high' : ws < 10 ? 'moderate' : 'low'
                  const stars = level === 'high' ? '★★★' : level === 'moderate' ? '★★☆' : '★☆☆'
                  const color = level === 'high' ? 'text-green-400' : level === 'moderate' ? 'text-yellow-400' : 'text-red-400'
                  const lbl = lang === 'zh' ? '模型共識' : 'Model consensus'
                  return (
                    <span className={`fs-compact px-1.5 py-0.5 rounded bg-[var(--color-bg-elevated)] ${color}`} aria-label={`${lbl}: ${level}`}>
                      {lbl} {stars}
                    </span>
                  )
                })()}
                {latest && (
                  <span className="fs-compact px-1.5 py-0.5 rounded bg-[var(--color-bg-elevated)] text-[var(--color-text-muted)]">
                    ±{latest.wind_mae_kt?.toFixed(1) ?? '?'}kt wind · ±{latest.temp_mae_c?.toFixed(1) ?? '?'}°C temp
                    {latest.wave?.hs_mae_m != null && ` · ±${latest.wave.hs_mae_m.toFixed(1)}m wave`}
                  </span>
                )}
              </div>
            )}
            {latest?.by_horizon && (
              <div className="flex flex-wrap gap-1.5">
                {(['0-24h', '24-48h', '48-72h'] as const).map(h => {
                  const wind = latest.by_horizon?.[h]?.wind_mae_kt
                  if (wind == null) return null
                  const temp = latest.by_horizon?.[h]?.temp_mae_c
                  return (
                    <span key={h} className="fs-compact px-1.5 py-0.5 rounded bg-[var(--color-bg-elevated)] text-[var(--color-text-muted)]">
                      {h}: ±{wind.toFixed(1)}kt{temp != null && ` ±${temp.toFixed(1)}°C`}
                    </span>
                  )
                })}
                {ensemble?.spread?.precip_spread_mm != null && ensemble.spread.precip_spread_mm > 1 && (
                  <span className="fs-compact px-1.5 py-0.5 rounded bg-[var(--color-bg-elevated)] text-[var(--color-text-muted)]">
                    {lang === 'zh' ? '降雨差異' : 'Rain spread'} ±{ensemble.spread.precip_spread_mm.toFixed(1)}mm
                  </span>
                )}
              </div>
            )}
            {accuracy && accuracy.length >= 2 && (
              <AccuracyTrend entries={accuracy} />
            )}
          </div>
        </>
      )}
    </section>
  )
}
