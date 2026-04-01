import { useTranslation } from 'react-i18next'
import { HARBOURS } from '@/lib/constants'
import { ShareButton } from '@/components/layout/ShareButton'
import { LiveObsCard } from '@/components/spots/LiveObsCard'
import { EnsembleAccuracyPills } from '@/components/spots/EnsembleAccuracyPills'
import type { EnsembleData, AccuracyEntry } from '@/lib/types'

interface KeelungDetailProps {
  ensemble: EnsembleData | null
  accuracy: AccuracyEntry[] | null
  onDeselect: () => void
}

export function KeelungDetail({ ensemble, accuracy, onDeselect }: KeelungDetailProps) {
  const { t } = useTranslation()

  return (
    <section className="md:px-3 py-3 space-y-3">
      {/* 1. Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-[var(--fs-label)] font-semibold text-[var(--color-text-primary)]">
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

      {/* 3. Webcam links */}
      {HARBOURS[0]?.webcams && (
        <div className="flex flex-wrap gap-1.5">
          {HARBOURS[0].webcams.map((cam, i) => (
            <a
              key={i}
              href={cam.url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-[var(--fs-compact)] px-1.5 py-0.5 rounded bg-[var(--color-bg-elevated)] text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] transition-colors"
            >
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M23 7l-7 5 7 5V7z" /><rect x="1" y="5" width="15" height="14" rx="2" ry="2" />
              </svg>
              {cam.label}
            </a>
          ))}
        </div>
      )}

      {/* 4. Ensemble + accuracy */}
      <EnsembleAccuracyPills ensemble={ensemble} accuracy={accuracy} />
    </section>
  )
}
