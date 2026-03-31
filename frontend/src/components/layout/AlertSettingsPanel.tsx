import { useState, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'

/** Browser-side alert thresholds stored in localStorage */
interface AlertPrefs {
  enabled: boolean
  wind_kt: number
  wave_m: number
  rain_mm: number
  surf_score: number
}

const DEFAULTS: AlertPrefs = {
  enabled: false,
  wind_kt: 34,
  wave_m: 2.5,
  rain_mm: 15,
  surf_score: 9,
}

const STORAGE_KEY = 'tw-wrf-alert-prefs'

function loadPrefs(): AlertPrefs {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) return { ...DEFAULTS, ...JSON.parse(raw) }
  } catch { /* ignore */ }
  return { ...DEFAULTS }
}

function savePrefs(prefs: AlertPrefs) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs))
}

/** Request browser notification permission */
async function requestPermission(): Promise<boolean> {
  if (!('Notification' in window)) return false
  if (Notification.permission === 'granted') return true
  if (Notification.permission === 'denied') return false
  const result = await Notification.requestPermission()
  return result === 'granted'
}

/** Check forecast data against thresholds and fire browser notification */
export function checkAlerts(
  records: Array<{ valid_utc: string; wind_kt?: number; gust_kt?: number; precip_mm_6h?: number }>,
  waveRecords: Array<{ valid_utc: string; wave_height?: number }>,
  surfRatings: Array<{ valid_utc: string; score?: number; rating?: string }>,
) {
  const prefs = loadPrefs()
  if (!prefs.enabled || !('Notification' in window) || Notification.permission !== 'granted') return

  const alerts: string[] = []
  const next24h = Date.now() + 24 * 3600_000

  for (const r of records) {
    if (new Date(r.valid_utc).getTime() > next24h) break
    const wind = r.gust_kt ?? r.wind_kt
    if (wind != null && wind >= prefs.wind_kt) {
      alerts.push(`Wind ${wind.toFixed(0)}kt at ${new Date(r.valid_utc).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`)
      break
    }
  }

  for (const w of waveRecords) {
    if (new Date(w.valid_utc).getTime() > next24h) break
    if (w.wave_height != null && w.wave_height >= prefs.wave_m) {
      alerts.push(`Waves ${w.wave_height.toFixed(1)}m`)
      break
    }
  }

  for (const s of surfRatings) {
    if (new Date(s.valid_utc).getTime() > next24h) break
    if (s.score != null && s.score >= prefs.surf_score) {
      alerts.push(`Great surf! Score ${s.score}`)
      break
    }
  }

  if (alerts.length > 0) {
    // Deduplicate: don't notify if we already notified for this forecast cycle
    const key = `tw-wrf-last-alert-${records[0]?.valid_utc ?? ''}`
    if (localStorage.getItem(key)) return
    localStorage.setItem(key, '1')

    new Notification('Taiwan Weather Alert', {
      body: alerts.join('\n'),
      icon: '/icons/icon-192.png',
      tag: 'tw-wrf-alert',
    })
  }
}

interface AlertSettingsPanelProps {
  open: boolean
  onClose: () => void
}

export function AlertSettingsPanel({ open, onClose }: AlertSettingsPanelProps) {
  const { i18n } = useTranslation()
  const lang = i18n.language?.startsWith('zh') ? 'zh' : 'en'
  const [prefs, setPrefs] = useState<AlertPrefs>(loadPrefs)
  const [permState, setPermState] = useState<NotificationPermission | 'unsupported'>('default')

  useEffect(() => {
    if (!('Notification' in window)) setPermState('unsupported')
    else setPermState(Notification.permission)
  }, [open])

  const updatePref = useCallback(<K extends keyof AlertPrefs>(key: K, value: AlertPrefs[K]) => {
    setPrefs(prev => {
      const next = { ...prev, [key]: value }
      savePrefs(next)
      return next
    })
  }, [])

  const handleEnable = async () => {
    const granted = await requestPermission()
    setPermState(granted ? 'granted' : 'denied')
    if (granted) updatePref('enabled', true)
  }

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onClose}>
      <div
        className="bg-[var(--color-bg)] border border-[var(--color-border)] rounded-xl w-[320px] max-w-[90vw] shadow-2xl"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--color-border)]">
          <h3 className="text-sm font-semibold text-[var(--color-text-primary)]">
            {lang === 'zh' ? '警報設定' : 'Alert Settings'}
          </h3>
          <button onClick={onClose} className="text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]">
            <svg width="14" height="14" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M1 1 L9 9 M9 1 L1 9" />
            </svg>
          </button>
        </div>

        <div className="px-4 py-3 space-y-3">
          {/* Enable toggle */}
          <div className="flex items-center justify-between">
            <span className="text-xs text-[var(--color-text-secondary)]">
              {lang === 'zh' ? '瀏覽器通知' : 'Browser notifications'}
            </span>
            {permState === 'unsupported' ? (
              <span className="text-[10px] text-[var(--color-text-dim)]">Not supported</span>
            ) : permState === 'denied' ? (
              <span className="text-[10px] text-red-400">Blocked in browser settings</span>
            ) : prefs.enabled ? (
              <button
                onClick={() => updatePref('enabled', false)}
                className="w-9 h-5 rounded-full bg-green-500 relative transition-colors"
              >
                <span className="absolute right-0.5 top-0.5 w-4 h-4 rounded-full bg-white transition-all" />
              </button>
            ) : (
              <button
                onClick={handleEnable}
                className="w-9 h-5 rounded-full bg-[var(--color-bg-elevated)] border border-[var(--color-border)] relative transition-colors"
              >
                <span className="absolute left-0.5 top-0.5 w-4 h-4 rounded-full bg-[var(--color-text-dim)] transition-all" />
              </button>
            )}
          </div>

          {prefs.enabled && (
            <>
              <p className="text-[9px] text-[var(--color-text-dim)]">
                {lang === 'zh'
                  ? '當未來24小時預報超過以下門檻時通知'
                  : 'Notify when 24h forecast exceeds thresholds:'}
              </p>

              <ThresholdRow
                label={lang === 'zh' ? '強風' : 'Wind gust'}
                value={prefs.wind_kt}
                unit="kt"
                min={15}
                max={50}
                step={1}
                onChange={v => updatePref('wind_kt', v)}
              />
              <ThresholdRow
                label={lang === 'zh' ? '浪高' : 'Wave height'}
                value={prefs.wave_m}
                unit="m"
                min={0.5}
                max={5}
                step={0.5}
                onChange={v => updatePref('wave_m', v)}
              />
              <ThresholdRow
                label={lang === 'zh' ? '降雨' : 'Rain (6h)'}
                value={prefs.rain_mm}
                unit="mm"
                min={5}
                max={50}
                step={5}
                onChange={v => updatePref('rain_mm', v)}
              />
              <ThresholdRow
                label={lang === 'zh' ? '衝浪' : 'Surf score'}
                value={prefs.surf_score}
                unit=""
                min={5}
                max={14}
                step={1}
                onChange={v => updatePref('surf_score', v)}
              />
            </>
          )}

          {/* LINE / Telegram info */}
          <div className="border-t border-[var(--color-border)] pt-2">
            <p className="text-[9px] text-[var(--color-text-dim)] leading-relaxed">
              {lang === 'zh'
                ? 'LINE / Telegram 推播通知由後端排程發送，需在伺服器設定。'
                : 'LINE / Telegram push alerts are sent by the backend pipeline. Configure via server environment variables.'}
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}

function ThresholdRow({ label, value, unit, min, max, step, onChange }: {
  label: string; value: number; unit: string; min: number; max: number; step: number
  onChange: (v: number) => void
}) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-[10px] text-[var(--color-text-muted)] w-16 shrink-0">{label}</span>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={e => onChange(Number(e.target.value))}
        className="flex-1 h-1 accent-blue-500"
      />
      <span className="text-[10px] text-[var(--color-text-secondary)] tabular-nums w-12 text-right">
        {value}{unit}
      </span>
    </div>
  )
}
