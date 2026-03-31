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

export function LiveObsCard({ spotId }: { spotId: string }) {
  const { t, i18n } = useTranslation()
  const lang = (i18n.language.startsWith('zh') ? 'zh' : 'en') as 'en' | 'zh'
  const liveObs = useLiveObsContext()
  const data = useForecastData()

  const live = liveObs.data?.spots?.[spotId]
  const stale = spotId === 'keelung'
    ? (data.cwa_obs?.spot_obs?.keelung ?? data.cwa_obs)
    : data.cwa_obs?.spot_obs?.[spotId]
  const stn = live?.station ?? stale?.station
  const buoy = live?.buoy ?? stale?.buoy
  const tide = live?.tide ?? stale?.tide
  if (!stn && !buoy && !tide) return null
  const waterTemp = tide?.sea_temp_c ?? live?.buoy?.sea_temp_c ?? stale?.buoy?.water_temp_c
  const items: { label: string; value: string; accent?: boolean }[] = []
  if (stn?.temp_c != null) items.push({ label: t('live.temp'), value: `${stn.temp_c.toFixed(1)}°C` })
  { const wKt = stn?.wind_kt ?? buoy?.wind_kt; const wDir = stn?.wind_dir ?? buoy?.wind_dir; if (wKt != null) items.push({ label: t('live.wind'), value: `${wKt.toFixed(0)}${stn?.gust_kt ? `G${stn.gust_kt.toFixed(0)}` : ''}kt ${wDir != null ? degToCompass(wDir) : ''}` }) }
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
  return (
    <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/5 p-2">
      <div className="flex items-center gap-1.5 mb-1.5">
        <span className="relative flex h-2 w-2">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
          <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
        </span>
        <span className="text-[8px] uppercase tracking-wider font-semibold text-emerald-400">
          {t('live.title')}{timeStr && ` · ${timeStr}`}
        </span>
      </div>
      <div className="grid grid-cols-3 gap-x-2 gap-y-1.5">
        {items.map((item, i) => (
          <div key={i} className="text-center">
            <p className="text-[8px] uppercase tracking-wider text-[var(--color-text-dim)]">{item.label}</p>
            <p className={`text-[11px] font-medium tabular-nums leading-tight ${item.accent ? 'text-orange-400' : 'text-[var(--color-text-secondary)]'}`}>{item.value}</p>
          </div>
        ))}
      </div>
    </div>
  )
}
