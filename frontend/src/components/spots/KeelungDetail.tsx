import { useTranslation } from 'react-i18next'
import { HARBOURS } from '@/lib/constants'
import { ShareButton } from '@/components/layout/ShareButton'
import { LiveObsCard } from '@/components/spots/LiveObsCard'
import { EnsembleAccuracyPills } from '@/components/spots/EnsembleAccuracyPills'
import { seaComfortStars, seaComfortLabel } from '@/lib/forecast-utils'
import type { EnsembleData, AccuracyEntry, CwaObs, WaveRecord } from '@/lib/types'

interface KeelungDetailProps {
  ensemble: EnsembleData | null
  accuracy: AccuracyEntry[] | null
  cwaObs?: CwaObs | null
  waveRec?: WaveRecord | null
  onDeselect: () => void
}

export function KeelungDetail({ ensemble, accuracy, cwaObs, waveRec, onDeselect }: KeelungDetailProps) {
  const { t } = useTranslation()

  return (
    <section className="md:px-3 py-3 space-y-3">
      {/* 1. Header */}
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

      {/* 2. LIVE observations — prominent */}
      <LiveObsCard spotId="keelung" />

      {/* 3. CWA warnings + sea comfort + webcams */}
      <div className="flex flex-wrap gap-1.5">
        {cwaObs?.specialized_warnings
          ?.filter(w => !w.area || w.area.includes('基隆'))
          .map((w, i) => (
          <span key={i} className={`fs-compact px-1.5 py-0.5 rounded ${
            w.type === 'rain' ? 'bg-blue-500/20 text-blue-400' :
            w.type === 'heat' ? 'bg-red-500/20 text-red-400' :
            'bg-cyan-500/20 text-cyan-400'
          }`} title={w.headline || w.description || undefined}>
            {w.severity_level || w.event || w.type}
          </span>
        ))}
        {waveRec?.sea_comfort != null && (
          <span className="inline-flex items-center gap-1 fs-compact border border-[var(--color-border)] rounded-full px-2.5 py-0.5 text-[var(--color-text-muted)]">
            <span>{t('common.sea_state')}</span>
            <span className="text-[var(--color-text-secondary)]">
              {seaComfortStars(waveRec.sea_comfort)} {seaComfortLabel(waveRec.sea_comfort) ?? ''}
            </span>
          </span>
        )}
        {HARBOURS[0]?.webcams?.map((cam, i) => (
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

      {/* 4. Ensemble + accuracy */}
      <EnsembleAccuracyPills ensemble={ensemble} accuracy={accuracy} />
    </section>
  )
}
