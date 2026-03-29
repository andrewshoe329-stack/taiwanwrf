import { useParams, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { SPOTS } from '@/lib/constants'
import { useForecastData } from '@/hooks/useForecastData'
import { SwellCompass } from '@/components/spots/SwellCompass'
import { ScoreBreakdown } from '@/components/spots/ScoreBreakdown'
import {
  degToCompass, formatTimeCst, isCurrentTimestep,
  ratingColorClass, groupByDay,
} from '@/lib/forecast-utils'

export function SpotDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { t, i18n } = useTranslation()
  const lang = i18n.language as 'en' | 'zh'
  const data = useForecastData()
  const spot = SPOTS.find(s => s.id === id)

  if (!spot) {
    return (
      <div className="px-4 py-6 pb-24 max-w-screen-xl mx-auto">
        <button
          onClick={() => navigate(-1)}
          className="flex items-center gap-1 text-sm text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] transition-colors mb-6"
        >
          <span className="text-base">&larr;</span>
          <span>{t('spots.back')}</span>
        </button>
        <p className="text-[var(--color-text-muted)]">Spot not found</p>
      </div>
    )
  }

  // Find this spot's forecast data if available
  const spotForecast = data.surf?.spots?.find(sf => sf.spot.id === id)

  // Current rating: first available rating (nearest forecast time)
  const currentRating = spotForecast?.ratings?.[0] ?? undefined

  // Group ratings by day for hourly forecast table
  const dayGroups = spotForecast?.ratings ? groupByDay(spotForecast.ratings) : []
  const allUtcs = spotForecast?.ratings?.map(r => r.valid_utc) ?? []

  return (
    <div className="px-4 pt-4 pb-24 max-w-screen-xl mx-auto">
      {/* Back button */}
      <button
        onClick={() => navigate(-1)}
        className="flex items-center gap-1 text-sm text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] transition-colors mb-5"
      >
        <span className="text-base">&larr;</span>
        <span>{t('spots.back')}</span>
      </button>

      {/* Spot header */}
      <div className="flex items-start justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-[var(--color-text-primary)] leading-tight">
            {spot.name[lang]}
          </h1>
          <p className="text-sm text-[var(--color-text-muted)] mt-0.5">
            {spot.name[lang === 'en' ? 'zh' : 'en']}
          </p>
        </div>
        <span className="shrink-0 text-[10px] uppercase tracking-wider text-[var(--color-text-muted)] border border-[var(--color-border)] rounded-full px-3 py-1 mt-1">
          {t(`region.${spot.region}`)}
        </span>
      </div>

      {/* Spot info section */}
      <section className="border border-[var(--color-border)] rounded-xl p-4 mb-4">
        <h2 className="text-xs uppercase tracking-wider text-[var(--color-text-muted)] mb-3">
          {t('spots.spot_info')}
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <InfoItem label={t('spots.facing')} value={spot.facing} />
          <InfoItem label={t('spots.optimal_wind')} value={spot.opt_wind.join(', ')} />
          <InfoItem label={t('spots.optimal_swell')} value={spot.opt_swell.join(', ')} />
        </div>
      </section>

      {/* 5-Day Forecast */}
      <section className="border border-[var(--color-border)] rounded-xl p-4 mb-4">
        <h2 className="text-xs uppercase tracking-wider text-[var(--color-text-muted)] mb-3">
          {t('spots.five_day_forecast')}
        </h2>
        {spotForecast && spotForecast.daily_best.length > 0 ? (
          <div className="grid grid-cols-5 gap-2">
            {spotForecast.daily_best.map(day => (
              <DayCard key={day.date} date={day.date} rating={day.rating} score={day.score} t={t} />
            ))}
          </div>
        ) : (
          <p className="text-sm text-[var(--color-text-dim)] py-4 text-center">
            {t('spots.no_data')}
          </p>
        )}
      </section>

      {/* Best Time to Surf */}
      {spotForecast && spotForecast.best_times.length > 0 && (
        <section className="border border-[var(--color-border)] rounded-xl p-4 mb-4">
          <h2 className="text-xs uppercase tracking-wider text-[var(--color-text-muted)] mb-3">
            {t('spots.best_time')}
          </h2>
          <div className="space-y-2">
            {spotForecast.best_times.map(bt => {
              const d = new Date(bt.date + 'T00:00:00Z')
              const dayLabel = d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', timeZone: 'UTC' })
              return (
                <div key={bt.date} className="flex items-center justify-between py-1.5">
                  <span className="text-xs text-[var(--color-text-secondary)]">{dayLabel}</span>
                  <div className="flex items-center gap-3">
                    <span className="text-xs text-[var(--color-text-primary)] font-medium tabular-nums">
                      {bt.start_cst} – {bt.end_cst} CST
                    </span>
                    <span className={`text-[10px] font-medium ${ratingColorClass(bt.rating)}`}>
                      {t(`rating.${bt.rating}`)}
                    </span>
                  </div>
                </div>
              )
            })}
          </div>
        </section>
      )}

      {/* Hourly Forecast Table */}
      <section className="border border-[var(--color-border)] rounded-xl p-4 mb-4">
        <h2 className="text-xs uppercase tracking-wider text-[var(--color-text-muted)] mb-3">
          {t('spots.hourly_forecast')}
        </h2>
        {dayGroups.length > 0 ? (
          <div className="overflow-x-auto" style={{ scrollbarWidth: 'thin' }}>
            <table className="w-full border-collapse text-xs" style={{ minWidth: 440 }}>
              <thead>
                <tr className="border-b border-[var(--color-border)]">
                  <th className="text-left py-2 pr-2 text-[var(--color-text-muted)] font-normal">{t('spots.time')}</th>
                  <th className="text-right py-2 px-2 text-[var(--color-text-muted)] font-normal">{t('common.wind')}</th>
                  <th className="text-right py-2 px-2 text-[var(--color-text-muted)] font-normal">{t('spots.swell')}</th>
                  <th className="text-right py-2 px-2 text-[var(--color-text-muted)] font-normal">{t('spots.period')}</th>
                  <th className="text-right py-2 px-2 text-[var(--color-text-muted)] font-normal">{t('spots.tide')}</th>
                  <th className="text-right py-2 pl-2 text-[var(--color-text-muted)] font-normal">{t('spots.rating_label')}</th>
                </tr>
              </thead>
              {dayGroups.map(group => (
                <tbody key={group.dayKey}>
                  {/* Day header row */}
                  <tr>
                    <td colSpan={6} className="pt-3 pb-1">
                      <span className="text-[11px] font-semibold text-[var(--color-text-secondary)] tracking-wide">
                        {group.dayLabel}
                      </span>
                    </td>
                  </tr>
                  {group.items.map(r => {
                    const isCurrent = isCurrentTimestep(r.valid_utc, allUtcs)
                    return (
                      <tr
                        key={r.valid_utc}
                        className={`border-b border-[var(--color-border)]/30 ${isCurrent ? 'bg-[var(--color-bg-elevated)]' : ''}`}
                      >
                        <td className="py-1.5 pr-2">
                          <span className="text-[var(--color-text-secondary)] tabular-nums">
                            {formatTimeCst(r.valid_utc)}
                          </span>
                          {isCurrent && (
                            <span className="ml-1 text-[9px] font-medium text-[var(--color-rating-good)] uppercase">now</span>
                          )}
                        </td>
                        <td className="text-right py-1.5 px-2 tabular-nums text-[var(--color-text-primary)]">
                          {r.wind_kt != null ? (
                            <>
                              {r.wind_dir != null && (
                                <span className="inline-block w-3 text-center text-[var(--color-text-muted)]" style={{ transform: `rotate(${r.wind_dir + 180}deg)` }}>
                                  {'\u2191'}
                                </span>
                              )}
                              {' '}{r.wind_kt.toFixed(0)}
                              <span className="text-[var(--color-text-dim)] ml-0.5">kt</span>
                              {r.wind_dir != null && (
                                <span className="text-[var(--color-text-muted)] ml-1">{degToCompass(r.wind_dir)}</span>
                              )}
                            </>
                          ) : '--'}
                        </td>
                        <td className="text-right py-1.5 px-2 tabular-nums text-[var(--color-text-primary)]">
                          {r.swell_height != null ? (
                            <>
                              {r.swell_height.toFixed(1)}
                              <span className="text-[var(--color-text-dim)] ml-0.5">m</span>
                              {r.swell_dir != null && (
                                <span className="text-[var(--color-text-muted)] ml-1">{degToCompass(r.swell_dir)}</span>
                              )}
                            </>
                          ) : '--'}
                        </td>
                        <td className="text-right py-1.5 px-2 tabular-nums text-[var(--color-text-secondary)]">
                          {r.swell_period != null ? (
                            <>
                              {r.swell_period.toFixed(0)}
                              <span className="text-[var(--color-text-dim)] ml-0.5">s</span>
                            </>
                          ) : '--'}
                        </td>
                        <td className="text-right py-1.5 px-2 tabular-nums text-[var(--color-text-secondary)]">
                          {r.tide_height != null ? (
                            <>
                              {r.tide_height.toFixed(2)}
                              <span className="text-[var(--color-text-dim)] ml-0.5">m</span>
                            </>
                          ) : '--'}
                        </td>
                        <td className="text-right py-1.5 pl-2">
                          <span className={`text-[10px] font-medium ${ratingColorClass(r.rating)}`}>
                            {t(`rating.${r.rating}`)}
                          </span>
                          <span className="text-[var(--color-text-dim)] ml-1 text-[10px]">{r.score}/14</span>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              ))}
            </table>
          </div>
        ) : (
          <p className="text-sm text-[var(--color-text-dim)] py-4 text-center">
            {t('spots.no_data')}
          </p>
        )}
      </section>

      {/* Swell Compass */}
      <section className="border border-[var(--color-border)] rounded-xl p-4 mb-4">
        <h2 className="text-xs uppercase tracking-wider text-[var(--color-text-muted)] mb-3">
          {t('spots.swell_compass')}
        </h2>
        <div className="flex items-center justify-center py-4">
          <SwellCompass
            facing={spot.facing}
            optSwell={spot.opt_swell}
            swellDir={currentRating?.swell_dir}
            swellHeight={currentRating?.swell_height}
          />
        </div>
        {currentRating?.swell_height != null && (
          <p className="text-center text-[10px] text-[var(--color-text-muted)] mt-1">
            {currentRating.swell_height.toFixed(1)} m @ {currentRating.swell_period?.toFixed(0) ?? '--'} s
          </p>
        )}
      </section>

      {/* Score Breakdown */}
      <section className="border border-[var(--color-border)] rounded-xl p-4 mb-4">
        <h2 className="text-xs uppercase tracking-wider text-[var(--color-text-muted)] mb-3">
          {t('spots.score_breakdown')}
        </h2>
        {currentRating ? (
          <ScoreBreakdown rating={currentRating} spot={spot} />
        ) : (
          <p className="text-sm text-[var(--color-text-dim)] py-4 text-center">
            {t('spots.no_data')}
          </p>
        )}
      </section>
    </div>
  )
}

function InfoItem({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-[10px] uppercase tracking-wider text-[var(--color-text-dim)] mb-1">
        {label}
      </dt>
      <dd className="text-sm text-[var(--color-text-primary)] font-medium">
        {value}
      </dd>
    </div>
  )
}

function DayCard({ date, rating, score, t }: { date: string; rating: string; score: number; t: (key: string) => string }) {
  const d = new Date(date + 'T00:00:00Z')
  const weekday = d.toLocaleDateString('en-US', { weekday: 'short', timeZone: 'UTC' })
  const dayNum = d.getUTCDate()

  return (
    <div className="flex flex-col items-center gap-1 py-2">
      <span className="text-[10px] text-[var(--color-text-muted)]">{weekday}</span>
      <span className="text-xs text-[var(--color-text-secondary)]">{dayNum}</span>
      <span className={`text-[10px] font-medium mt-1 ${ratingColorClass(rating)}`}>
        {t(`rating.${rating}`)}
      </span>
      <span className="text-[10px] text-[var(--color-text-dim)]">{score}/14</span>
    </div>
  )
}
