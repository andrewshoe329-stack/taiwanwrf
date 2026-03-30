import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { useForecastData } from '@/hooks/useForecastData'
import { useTimeline } from '@/hooks/useTimeline'
import { useModel } from '@/hooks/useModel'
import { useLocation } from '@/hooks/useLocation'
import { degToCompass, getModelRecords } from '@/lib/forecast-utils'

function Stat({ label, value, unit, detail }: {
  label: string; value: string; unit: string; detail?: string
}) {
  return (
    <div className="text-center">
      <p className="text-[9px] text-[var(--color-text-muted)] uppercase tracking-wider">{label}</p>
      <p className="text-sm font-semibold text-[var(--color-text-primary)] tabular-nums leading-tight">
        {value}<span className="text-[10px] text-[var(--color-text-muted)] ml-0.5">{unit}</span>
      </p>
      {detail && <p className="text-[10px] text-[var(--color-text-muted)] leading-tight">{detail}</p>}
    </div>
  )
}

export function ConditionsStrip() {
  const { t } = useTranslation()
  const data = useForecastData()
  const { index } = useTimeline()
  const { model } = useModel()
  const { locationId } = useLocation()

  const records = useMemo(() => {
    if (locationId) return getModelRecords(locationId, model, data)
    return data.keelung?.records ?? []
  }, [locationId, model, data])

  const rec = useMemo(() => {
    if (!records?.length) return null
    return records[Math.min(index, records.length - 1)]
  }, [records, index])

  const waveRecs = data.wave?.ecmwf_wave?.records
  const waveRec = useMemo(() => {
    if (!waveRecs?.length) return null
    return waveRecs[Math.min(index, waveRecs.length - 1)]
  }, [waveRecs, index])

  if (!rec) return null

  const swellH = waveRec?.swell_wave_height
  const swellP = waveRec?.swell_wave_period ?? waveRec?.wave_period
  const swellDir = waveRec?.swell_wave_direction
  const precip = rec.precip_mm_6h

  return (
    <div className="grid grid-cols-5 gap-1 py-1.5">
      <Stat
        label={t('common.wind')}
        value={rec.wind_kt?.toFixed(0) ?? '--'}
        unit="kt"
        detail={rec.wind_dir != null ? degToCompass(rec.wind_dir) + (rec.gust_kt ? ` G${rec.gust_kt.toFixed(0)}` : '') : undefined}
      />
      <Stat
        label={t('common.swell')}
        value={swellH?.toFixed(1) ?? '--'}
        unit="m"
        detail={swellH != null ? `${swellP?.toFixed(0) ?? '--'}s${swellDir != null ? ' ' + degToCompass(swellDir) : ''}` : undefined}
      />
      <Stat
        label={t('common.wave_height')}
        value={waveRec?.wave_height?.toFixed(1) ?? '--'}
        unit="m"
      />
      <Stat
        label={t('common.temp')}
        value={rec.temp_c?.toFixed(0) ?? '--'}
        unit={'\u00B0C'}
      />
      <Stat
        label={t('common.precip')}
        value={precip != null && precip > 0 ? precip.toFixed(1) : '--'}
        unit="mm"
      />
    </div>
  )
}
