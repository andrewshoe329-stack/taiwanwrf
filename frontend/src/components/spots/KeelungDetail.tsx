import { useTranslation } from 'react-i18next'
import { HARBOURS } from '@/lib/constants'
import { ShareButton } from '@/components/layout/ShareButton'
import { LiveObsCard } from '@/components/spots/LiveObsCard'
import { SectionDivider } from '@/components/spots/SectionDivider'
import { AccuracyTrend } from '@/components/charts/AccuracyTrend'
import { seaComfortStars, seaComfortLabel } from '@/lib/forecast-utils'
import type { EnsembleData, AccuracyEntry, CwaObs, WaveRecord } from '@/lib/types'

/** Get the most recent accuracy entry (by init_utc). */
function latestAccuracy(entries: AccuracyEntry[] | null): AccuracyEntry | null {
  if (!entries?.length) return null
  return entries.reduce((a, b) => (a.init_utc > b.init_utc ? a : b))
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

interface KeelungDetailProps {
  ensemble: EnsembleData | null
  accuracy: AccuracyEntry[] | null
  cwaObs?: CwaObs | null
  waveRec?: WaveRecord | null
  forecastTimeLabel?: string
  onDeselect: () => void
}

export function KeelungDetail({ ensemble, accuracy, cwaObs, waveRec, forecastTimeLabel, onDeselect }: KeelungDetailProps) {
  const { t, i18n } = useTranslation()
  const lang = (i18n.language.startsWith('zh') ? 'zh' : 'en') as 'en' | 'zh'

  const warnings = cwaObs?.specialized_warnings?.filter(w => !w.area || w.area.includes('基隆')) ?? []
  const latest = latestAccuracy(accuracy)
  const hasAccuracySection = !!(ensemble?.spread || latest || (accuracy && accuracy.length >= 2))

  return (
    <section className="md:px-3 py-3 space-y-3">
      {/* ── 1. Header ────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <h2 className="fs-label font-semibold text-[var(--color-text-primary)]">
          {t('harbour.keelung')}
        </h2>
        <div className="flex items-center gap-1.5">
          <ShareButton locationId="keelung" />
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

      {/* ── 2. Warnings ──────────────────────────────────────────────── */}
      {warnings.length > 0 && (
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

      {/* ── 3. Live conditions ───────────────────────────────────────── */}
      <LiveObsCard spotId="keelung" />

      {/* ── 4. Sea state / forecast ──────────────────────────────────── */}
      {waveRec && (waveRec.wave_height != null || waveRec.sea_comfort != null) && (
        <>
          <SectionDivider label={
            `${t('common.forecast') || 'Forecast'}${forecastTimeLabel ? ` · ${forecastTimeLabel} CST` : ''}`
          } />
          <div className="grid grid-cols-2 gap-1.5">
            {waveRec.wave_height != null && (
              <DataCell
                label={t('common.wave_height')}
                value={waveRec.wave_height.toFixed(1)}
                unit="m"
              />
            )}
            {(waveRec.swell_wave_period ?? waveRec.wave_period) != null && (
              <DataCell
                label={t('common.swell_period')}
                value={`${(waveRec.swell_wave_period ?? waveRec.wave_period)!.toFixed(0)}`}
                unit="s"
              />
            )}
            {waveRec.sea_comfort != null && (
              <DataCell
                label={t('common.sea_state')}
                value={seaComfortStars(waveRec.sea_comfort)}
                unit=""
                sub={seaComfortLabel(waveRec.sea_comfort) ?? undefined}
              />
            )}
          </div>
        </>
      )}

      {/* ── 5. Harbour info & webcams ────────────────────────────────── */}
      {HARBOURS[0]?.webcams?.length ? (
        <>
          <SectionDivider label={lang === 'zh' ? '港口資訊' : 'Harbour info'} />
          <div className="flex flex-wrap items-center gap-1.5">
            {HARBOURS[0].webcams.map((cam, i) => (
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
      ) : null}

      {/* ── 6. Model & accuracy ──────────────────────────────────────── */}
      {hasAccuracySection && (
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
