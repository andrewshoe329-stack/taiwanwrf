import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useLiveObsContext } from '@/App'
import { useForecastData } from '@/hooks/useForecastData'
import { degToCompass } from '@/lib/forecast-utils'

const TIDE_LEVEL_MAP: Record<string, { en: string; zh: string }> = {
  '漲潮': { en: 'Rising', zh: '漲潮' },
  '退潮': { en: 'Falling', zh: '退潮' },
  '滿潮': { en: 'High', zh: '滿潮' },
  '乾潮': { en: 'Low', zh: '乾潮' },
}

interface LiveObsCardProps {
  spotId: string
  /** When true, renders a single-line summary that expands on tap */
  collapsible?: boolean
}

export function LiveObsCard({ spotId, collapsible = false }: LiveObsCardProps) {
  const { t, i18n } = useTranslation()
  const lang = (i18n.language.startsWith('zh') ? 'zh' : 'en') as 'en' | 'zh'
  const liveObs = useLiveObsContext()
  const data = useForecastData()
  const [expanded, setExpanded] = useState(false)

  const live = liveObs.data?.spots?.[spotId]
  const stale = spotId === 'keelung'
    ? (data.cwa_obs?.spot_obs?.keelung ?? data.cwa_obs)
    : data.cwa_obs?.spot_obs?.[spotId]
  const stn = live?.station ?? stale?.station
  const buoy = live?.buoy ?? stale?.buoy
  const tide = live?.tide
  if (!stn && !buoy && !tide) return null
  const waterTemp = tide?.sea_temp_c ?? live?.buoy?.sea_temp_c ?? stale?.buoy?.water_temp_c
  const items: { label: string; value: string; accent?: boolean }[] = []
  if (stn?.temp_c != null) items.push({ label: t('live.temp'), value: `${stn.temp_c.toFixed(1)}°C` })
  { const wKt = stn?.wind_kt ?? buoy?.wind_kt; const wDir = stn?.wind_dir ?? buoy?.wind_dir; const gKt = stn?.gust_kt; const showGust = gKt != null && gKt > 0 && gKt > (wKt ?? 0); if (wKt != null) items.push({ label: t('live.wind'), value: `${wKt.toFixed(0)}${showGust ? `G${gKt.toFixed(0)}` : ''}kt ${wDir != null ? degToCompass(wDir) : ''}` }) }
  if (stn?.pressure_hpa != null) items.push({ label: t('live.pressure'), value: `${stn.pressure_hpa.toFixed(0)} hPa` })
  if (tide?.tide_height_m != null) { const tl = tide.tide_level ? (TIDE_LEVEL_MAP[tide.tide_level]?.[lang] ?? tide.tide_level) : ''; items.push({ label: t('live.tide'), value: `${tide.tide_height_m.toFixed(2)}m${tl ? ` ${tl}` : ''}` }) }
  if (buoy?.wave_height_m != null) items.push({ label: t('live.waves'), value: `${buoy.wave_height_m.toFixed(1)}m${buoy.wave_period_s ? ` ${buoy.wave_period_s.toFixed(0)}s` : ''}` })
  if (waterTemp != null) items.push({ label: t('live.water_temp'), value: `${waterTemp.toFixed(1)}°C` })
  if (live?.station?.visibility_km != null && live.station.visibility_km < 10) items.push({ label: t('live.visibility'), value: `${live.station.visibility_km.toFixed(1)}km` })
  if (live?.station?.uv_index != null && live.station.uv_index > 0) items.push({ label: 'UV', value: `${live.station.uv_index.toFixed(0)}`, accent: live.station.uv_index >= 6 })
  if (live?.buoy?.current_speed_ms != null && live.buoy.current_speed_ms > 0.1) items.push({ label: t('common.current') || 'Current', value: `${(live.buoy.current_speed_ms * 1.94384).toFixed(1)}kt ${live.buoy.current_dir != null ? degToCompass(live.buoy.current_dir) : ''}` })
  if (!items.length) return null
  const obsTime = live?.station?.obs_time ?? stale?.station?.obs_time
  const timeStr = obsTime ? new Date(obsTime).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'Asia/Taipei' }) : ''

  // Collapsed single-line: green dot + up to 4 key values separated by ·
  if (collapsible && !expanded) {
    const summary = items.slice(0, 4).map(i => i.value).join(' · ')
    return (
      <button
        onClick={() => setExpanded(true)}
        className="w-full rounded-lg border border-emerald-500/30 bg-emerald-500/5 px-2 py-1.5 flex items-center gap-1.5 text-left"
      >
        <span className="relative flex h-2 w-2 shrink-0">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
          <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
        </span>
        <span className="fs-micro uppercase tracking-wider font-semibold text-emerald-400 shrink-0">
          {t('live.title')}{timeStr && ` ${timeStr}`}
        </span>
        <span className="fs-compact tabular-nums text-[var(--color-text-secondary)] truncate">
          {summary}
        </span>
        <svg width="10" height="10" viewBox="0 0 10 10" className="shrink-0 text-emerald-400/60 ml-auto" fill="none" stroke="currentColor" strokeWidth="1.5">
          <path d="M2 4 L5 7 L8 4" />
        </svg>
      </button>
    )
  }

  return (
    <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/5 p-2">
      <div className={`flex items-center gap-1.5 mb-1.5${collapsible ? ' cursor-pointer' : ''}`} onClick={collapsible ? () => setExpanded(false) : undefined}>
        <span className="relative flex h-2 w-2">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
          <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
        </span>
        <span className="fs-micro uppercase tracking-wider font-semibold text-emerald-400">
          {t('live.title')}{timeStr && ` · ${timeStr}`}
        </span>
        {collapsible && (
          <svg width="10" height="10" viewBox="0 0 10 10" className="shrink-0 text-emerald-400/60 ml-auto rotate-180" fill="none" stroke="currentColor" strokeWidth="1.5">
            <path d="M2 4 L5 7 L8 4" />
          </svg>
        )}
      </div>
      <div className="grid grid-cols-3 gap-x-2 gap-y-1.5">
        {items.map((item, i) => (
          <div key={i} className="text-center">
            <p className="fs-micro uppercase tracking-wider text-[var(--color-text-dim)]">{item.label}</p>
            <p className={`fs-compact font-medium tabular-nums leading-tight ${item.accent ? 'text-orange-400' : 'text-[var(--color-text-secondary)]'}`}>{item.value}</p>
          </div>
        ))}
      </div>
    </div>
  )
}
