import { useTranslation } from 'react-i18next'
import { HARBOURS } from '@/lib/constants'
import { useForecastData } from '@/hooks/useForecastData'
import type { ForecastRecord, WaveRecord } from '@/lib/types'

export function HarboursPage() {
  const { t, i18n } = useTranslation()
  const lang = (i18n.language.startsWith('zh') ? 'zh' : 'en') as 'en' | 'zh'
  const data = useForecastData()

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

          // Get current (first) record from each source
          const windRec: ForecastRecord | undefined = ecmwf?.records?.[0]
          const waveRec: WaveRecord | undefined = wave?.ecmwf_wave?.records?.[0]

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

              {/* Conditions grid */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                {/* Wind */}
                <MiniStat
                  label={t('common.wind')}
                  value={windRec?.wind_kt != null ? `${windRec.wind_kt.toFixed(0)}` : '--'}
                  unit="kt"
                  sub={windRec?.gust_kt != null ? `G${windRec.gust_kt.toFixed(0)}` : undefined}
                />
                {/* Direction */}
                <MiniStat
                  label={t('harbours_page.direction')}
                  value={windRec?.wind_dir != null ? `${windRec.wind_dir}` : '--'}
                  unit="°"
                />
                {/* Waves */}
                <MiniStat
                  label={t('harbours_page.waves')}
                  value={waveRec?.wave_height != null ? waveRec.wave_height.toFixed(1) : '--'}
                  unit="m"
                  sub={waveRec?.wave_period != null ? `${waveRec.wave_period.toFixed(0)}s` : undefined}
                />
                {/* Temp */}
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
