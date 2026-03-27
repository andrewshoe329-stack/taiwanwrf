import { useParams, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { SPOTS } from '@/lib/constants'
import { useForecastData } from '@/hooks/useForecastData'

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

      {/* 5-Day Forecast placeholder */}
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

      {/* Swell Compass placeholder */}
      <section className="border border-[var(--color-border)] rounded-xl p-4 mb-4">
        <h2 className="text-xs uppercase tracking-wider text-[var(--color-text-muted)] mb-3">
          {t('spots.swell_compass')}
        </h2>
        <div className="flex items-center justify-center py-10">
          <div className="w-32 h-32 rounded-full border border-[var(--color-border)] flex items-center justify-center">
            <span className="text-xs text-[var(--color-text-dim)]">{t('spots.coming_soon')}</span>
          </div>
        </div>
      </section>

      {/* Score Breakdown placeholder */}
      <section className="border border-[var(--color-border)] rounded-xl p-4 mb-4">
        <h2 className="text-xs uppercase tracking-wider text-[var(--color-text-muted)] mb-3">
          {t('spots.score_breakdown')}
        </h2>
        {spotForecast && spotForecast.ratings.length > 0 ? (
          <div className="space-y-2">
            <ScoreFactor label={t('spots.score_swell_dir')} />
            <ScoreFactor label={t('spots.score_wind_dir')} />
            <ScoreFactor label={t('spots.score_wind_speed')} />
            <ScoreFactor label={t('spots.score_swell_height')} />
            <ScoreFactor label={t('spots.score_wave_period')} />
          </div>
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
  // Format date to short weekday
  const d = new Date(date + 'T00:00:00Z')
  const weekday = d.toLocaleDateString('en-US', { weekday: 'short', timeZone: 'UTC' })
  const dayNum = d.getUTCDate()

  const ratingColor: Record<string, string> = {
    firing:    'text-[var(--color-firing)]',
    good:      'text-[var(--color-rating-good)]',
    marginal:  'text-[var(--color-rating-marginal)]',
    poor:      'text-[var(--color-rating-poor)]',
    flat:      'text-[var(--color-text-dim)]',
    dangerous: 'text-[var(--color-rating-dangerous)]',
  }

  return (
    <div className="flex flex-col items-center gap-1 py-2">
      <span className="text-[10px] text-[var(--color-text-muted)]">{weekday}</span>
      <span className="text-xs text-[var(--color-text-secondary)]">{dayNum}</span>
      <span className={`text-[10px] font-medium mt-1 ${ratingColor[rating] ?? 'text-[var(--color-text-dim)]'}`}>
        {t(`rating.${rating}`)}
      </span>
      <span className="text-[10px] text-[var(--color-text-dim)]">{score}/14</span>
    </div>
  )
}

function ScoreFactor({ label }: { label: string }) {
  return (
    <div className="flex items-center justify-between py-1.5 border-b border-[var(--color-border-subtle)]">
      <span className="text-xs text-[var(--color-text-secondary)]">{label}</span>
      <span className="text-xs text-[var(--color-text-dim)]">--</span>
    </div>
  )
}
