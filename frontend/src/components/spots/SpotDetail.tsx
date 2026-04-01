import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { SwellCompass } from '@/components/spots/SwellCompass'
import { ScoreBreakdownTooltip } from '@/components/spots/ScoreBreakdownTooltip'
import { BestTimeWindows } from '@/components/spots/BestTimeWindows'
import { ShareButton } from '@/components/layout/ShareButton'
import { LiveObsCard } from '@/components/spots/LiveObsCard'
import { EnsembleAccuracyPills } from '@/components/spots/EnsembleAccuracyPills'
import { TideSparkline } from '@/components/charts/TideSparkline'
import { degToCompass, windType, seaComfortStars, seaComfortLabel } from '@/lib/forecast-utils'
import { SPOT_COUNTY } from '@/lib/constants'
import type { SpotInfo, SpotRating, SpotForecast, TidePrediction, TideExtremum, EnsembleData, AccuracyEntry, CwaObs } from '@/lib/types'

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

interface SpotDetailProps {
  spotInfo: SpotInfo
  currentRating: SpotRating | null
  locationForecast: SpotForecast | null
  tidePredictions: TidePrediction[]
  tideExtrema: TideExtremum[]
  forecastTimeLabel: string
  mobile: boolean
  nowMs: number | undefined
  ensemble: EnsembleData | null
  accuracy: AccuracyEntry[] | null
  cwaObs: CwaObs | null
  onDeselect: () => void
}

export function SpotDetail({
  spotInfo,
  currentRating,
  locationForecast,
  tidePredictions,
  tideExtrema,
  forecastTimeLabel,
  mobile,
  nowMs,
  ensemble,
  accuracy,
  cwaObs,
  onDeselect,
}: SpotDetailProps) {
  const { t, i18n } = useTranslation()
  const lang = (i18n.language.startsWith('zh') ? 'zh' : 'en') as 'en' | 'zh'
  const [scoreTooltipOpen, setScoreTooltipOpen] = useState(false)

  return (
    <section className="space-y-3 md:px-3 py-3">
      {/* 1. Spot header */}
      <div className="flex items-center justify-between">
        <h2 className="fs-label font-semibold text-[var(--color-text-primary)]">
          {spotInfo.name[lang]}
          <span className="text-[var(--color-text-muted)] ml-1.5 fs-body font-normal">
            {spotInfo.name[lang === 'en' ? 'zh' : 'en']}
          </span>
        </h2>
        <div className="flex items-center gap-1.5">
          {currentRating?.rating && (
            <div className="relative">
              <button
                onClick={() => setScoreTooltipOpen(!scoreTooltipOpen)}
                className="fs-compact font-medium capitalize px-1.5 py-0.5 rounded"
                style={{
                  color: { firing: '#f97316', great: '#22c55e', good: '#4ade80', marginal: '#facc15', poor: '#ef4444', flat: '#6b7280', dangerous: '#dc2626' }[currentRating.rating] ?? '#6b7280',
                  backgroundColor: ({ firing: '#f97316', great: '#22c55e', good: '#4ade80', marginal: '#facc15', poor: '#ef4444', flat: '#6b7280', dangerous: '#dc2626' }[currentRating.rating] ?? '#6b7280') + '20',
                }}
              >
                {currentRating.rating} {currentRating.score != null ? `${currentRating.score}` : ''}
              </button>
              {scoreTooltipOpen && currentRating.score_breakdown && (
                <div className="absolute right-0 top-7 z-50">
                  <ScoreBreakdownTooltip rating={currentRating} onClose={() => setScoreTooltipOpen(false)} />
                </div>
              )}
            </div>
          )}
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

      {/* 2. LIVE observations — prominent, first data section */}
      <LiveObsCard spotId={spotInfo.id} />

      {/* 3. Info pills + webcams — compact reference */}
      <div className="flex flex-wrap gap-1.5">
        <InfoPill label={t('spots.facing')} value={spotInfo.facing} />
        <InfoPill label={t('spots.optimal_wind')} value={spotInfo.opt_wind.join(', ')} />
        {currentRating?.wind_dir != null && spotInfo.facing && (
          <InfoPill label={t('common.wind')} value={windType(currentRating.wind_dir, spotInfo.facing)} />
        )}
        {cwaObs?.specialized_warnings
          ?.filter(w => {
            const county = SPOT_COUNTY[spotInfo.id]
            return !county || !w.area || w.area.includes(county)
          })
          .map((w, i) => (
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
            Squall Risk
          </span>
        )}
        {spotInfo.webcams?.map((cam, i) => (
          <a
            key={i}
            href={cam.url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 fs-compact px-1.5 py-0.5 rounded bg-[var(--color-bg-elevated)] text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] transition-colors"
          >
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M23 7l-7 5 7 5V7z" /><rect x="1" y="5" width="15" height="14" rx="2" ry="2" />
            </svg>
            {cam.label}
          </a>
        ))}
      </div>

      {/* 4. FORECAST section — labeled with selected time (desktop only) */}
      {!mobile && currentRating && (
        <div className="space-y-2">
          <div className="flex items-center gap-1.5">
            <span className="fs-micro uppercase tracking-wider font-semibold text-blue-400">
              {t('common.forecast') || 'Forecast'}{forecastTimeLabel && ` · ${forecastTimeLabel} CST`}
            </span>
          </div>
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
      )}

      {/* 5. Ensemble + accuracy */}
      <EnsembleAccuracyPills ensemble={ensemble} accuracy={accuracy} />
    </section>
  )
}
