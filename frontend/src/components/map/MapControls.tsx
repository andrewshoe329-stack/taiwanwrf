import { useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import type { WindModel } from '@/hooks/useModel'
import type { HimawariBandMode } from '@/lib/himawari'

export type MapLayer = 'wind' | 'waves' | 'currents' | 'radar' | 'satellite'

const MODEL_LABELS: Record<WindModel, string> = {
  wrf: 'WRF 3km',
  ecmwf: 'ECMWF',
  gfs: 'GFS',
}

interface MapControlsProps {
  layer: MapLayer
  setLayer: (layer: MapLayer) => void
  model: WindModel
  setModel: (model: WindModel) => void
  onZoomIn: () => void
  onZoomOut: () => void
  // Wave legend
  // Radar state
  tileTimestamp: string
  tileStale: boolean
  tileError: boolean
  // Satellite state
  himawariActiveBand: string
  himawariBandMode: HimawariBandMode
  onHimawariBandChange: (mode: HimawariBandMode) => void
}

const WAVE_LEGEND = [
  { color: '#1e3a5f', label: '0' },
  { color: '#1a6b8a', label: '' },
  { color: '#2d9a4e', label: '1' },
  { color: '#7ab648', label: '' },
  { color: '#c9a832', label: '2' },
  { color: '#d4682a', label: '' },
  { color: '#c93030', label: '3m+' },
]

export function MapControls({
  layer,
  setLayer,
  model,
  setModel,
  onZoomIn,
  onZoomOut,
  tileTimestamp,
  tileStale,
  tileError,
  himawariActiveBand,
  himawariBandMode,
  onHimawariBandChange,
}: MapControlsProps) {
  const { t } = useTranslation()

  const handleBandChange = useCallback((mode: HimawariBandMode) => {
    onHimawariBandChange(mode)
  }, [onHimawariBandChange])

  return (
    <>
      {/* Layer toggle */}
      <div className="absolute top-3 left-3 z-20 flex gap-0.5 rounded-md overflow-hidden border border-[var(--color-border)] backdrop-blur-sm">
        {(['wind', 'waves', 'currents', 'radar', 'satellite'] as MapLayer[]).map(l => (
          <button
            key={l}
            onClick={() => setLayer(l)}
            aria-label={`Show ${l} layer`}
            aria-pressed={layer === l}
            className={`
              px-2 py-1 text-[10px] font-medium transition-all
              ${layer === l
                ? 'bg-[var(--color-text-primary)] text-[var(--color-bg)]'
                : 'bg-[var(--color-bg-elevated)]/80 text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)]'
              }
            `}
          >
            {t(`map.${l}`)}
          </button>
        ))}
      </div>

      {/* Model switcher (only visible in wind mode) — below layers on small screens, top-right on md+ */}
      <div className={`absolute z-20 flex gap-1 top-11 left-3 md:top-3 md:left-auto md:right-3 ${layer !== 'wind' ? 'hidden' : ''}`}>
        {(['wrf', 'ecmwf', 'gfs'] as WindModel[]).map(m => (
          <button
            key={m}
            onClick={() => setModel(m)}
            aria-label={`Select ${MODEL_LABELS[m]} model`}
            aria-pressed={model === m}
            className={`
              px-2 py-1 text-[10px] font-medium rounded-md transition-all
              ${model === m
                ? 'bg-[var(--color-text-primary)] text-[var(--color-bg)]'
                : 'bg-[var(--color-bg-elevated)]/80 text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)]'
              }
              backdrop-blur-sm border border-[var(--color-border)]
            `}
          >
            {MODEL_LABELS[m]}
          </button>
        ))}
      </div>

      {/* Zoom controls */}
      <div className="absolute top-14 right-3 z-20 flex flex-col gap-1">
        <button
          onClick={onZoomIn}
          aria-label="Zoom in"
          className="w-7 h-7 flex items-center justify-center rounded-md bg-[var(--color-bg-elevated)]/80 text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] backdrop-blur-sm border border-[var(--color-border)] text-sm font-bold"
        >
          +
        </button>
        <button
          onClick={onZoomOut}
          aria-label="Zoom out"
          className="w-7 h-7 flex items-center justify-center rounded-md bg-[var(--color-bg-elevated)]/80 text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] backdrop-blur-sm border border-[var(--color-border)] text-sm font-bold"
        >
          −
        </button>
      </div>

      {/* Wave height legend (only in wave mode) */}
      {layer === 'waves' && (
        <div className="absolute bottom-3 left-3 z-20 backdrop-blur-sm bg-[var(--color-bg-elevated)]/80 border border-[var(--color-border)] rounded-md px-2 py-1.5">
          <p className="text-[8px] text-[var(--color-text-muted)] uppercase tracking-wider mb-1">Wave Height</p>
          <div className="flex items-center gap-0.5">
            {WAVE_LEGEND.map((s, i) => (
              <div key={i} className="flex flex-col items-center">
                <div className="w-4 h-2 rounded-sm" style={{ backgroundColor: s.color }} />
                {s.label && <span className="text-[7px] text-[var(--color-text-dim)] mt-0.5">{s.label}</span>}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Radar status badge + legend */}
      {layer === 'radar' && (
        <div className={`absolute bottom-3 left-3 z-20 backdrop-blur-sm bg-[var(--color-bg-elevated)]/80 border rounded-md px-2 py-1.5 ${tileStale ? 'border-amber-500/50' : tileError ? 'border-red-500/50' : 'border-[var(--color-border)]'}`}>
          <p className="text-[8px] text-[var(--color-text-muted)] uppercase tracking-wider mb-1">{t('map.radar')}</p>
          {tileError ? (
            <p className="text-[10px] text-red-400">{t('common.unavailable')}</p>
          ) : (
            <>
              <div className="flex items-center gap-0.5 mb-1">
                {[
                  { color: '#0a0f1e', label: '' },
                  { color: '#00c85a', label: t('map.radar_light') },
                  { color: '#ffff00', label: '' },
                  { color: '#ff8c00', label: t('map.radar_mod') },
                  { color: '#ff0000', label: '' },
                  { color: '#c800c8', label: t('map.radar_heavy') },
                ].map((s, i) => (
                  <div key={i} className="flex flex-col items-center">
                    <div className="w-3 h-1.5 rounded-sm" style={{ backgroundColor: s.color }} />
                    {s.label && <span className="text-[6px] text-[var(--color-text-dim)] mt-0.5">{s.label}</span>}
                  </div>
                ))}
              </div>
              {tileTimestamp && (
                <p className={`text-[9px] ${tileStale ? 'text-amber-400' : 'text-[var(--color-text-dim)]'}`}>
                  {tileTimestamp}{tileStale ? ` (${t('common.stale')})` : ''}
                </p>
              )}
            </>
          )}
        </div>
      )}

      {/* Satellite status badge + band toggle */}
      {layer === 'satellite' && (
        <div className={`absolute bottom-3 left-3 z-20 backdrop-blur-sm bg-[var(--color-bg-elevated)]/80 border rounded-md px-2 py-1.5 ${tileStale ? 'border-amber-500/50' : tileError ? 'border-red-500/50' : 'border-[var(--color-border)]'}`}>
          <p className="text-[8px] text-[var(--color-text-muted)] uppercase tracking-wider mb-1">Himawari {himawariActiveBand}</p>
          <div className="flex gap-0.5 mb-1">
            {([['auto', 'Auto'], ['ir', 'IR'], ['vis', 'VIS']] as const).map(([mode, label]) => (
              <button
                key={mode}
                onClick={() => handleBandChange(mode)}
                aria-label={`Satellite band: ${label}`}
                aria-pressed={himawariBandMode === mode}
                className={`px-1.5 py-0.5 text-[8px] font-medium rounded transition-all ${
                  himawariBandMode === mode
                    ? 'bg-[var(--color-text-primary)] text-[var(--color-bg)]'
                    : 'bg-[var(--color-bg)]/50 text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)]'
                }`}
              >
                {label}
              </button>
            ))}
          </div>
          {tileError ? (
            <p className="text-[10px] text-red-400">{t('common.unavailable')}</p>
          ) : tileTimestamp ? (
            <p className={`text-[9px] ${tileStale ? 'text-amber-400' : 'text-[var(--color-text-dim)]'}`}>
              {tileTimestamp}{tileStale ? ` (${t('common.stale')})` : ''}
            </p>
          ) : (
            <p className="text-[10px] text-[var(--color-text-dim)]">{t('common.loading_short')}</p>
          )}
        </div>
      )}
    </>
  )
}
