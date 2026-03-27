import { useParams } from 'react-router-dom'
import { SPOTS } from '@/lib/constants'
import { useTranslation } from 'react-i18next'

export function SpotDetailPage() {
  const { id } = useParams<{ id: string }>()
  const { i18n } = useTranslation()
  const lang = i18n.language as 'en' | 'zh'
  const spot = SPOTS.find(s => s.id === id)

  if (!spot) {
    return (
      <div className="px-4 py-6">
        <p className="text-[var(--color-text-muted)]">Spot not found</p>
      </div>
    )
  }

  return (
    <div className="px-4 py-6 max-w-screen-xl mx-auto">
      <h1 className="text-lg font-semibold mb-1">{spot.name[lang]}</h1>
      <p className="text-[var(--color-text-muted)] text-sm mb-6">
        {spot.facing} · {spot.region}
      </p>
      <div className="border border-[var(--color-border)] rounded-xl p-5">
        <p className="text-[var(--color-text-muted)] text-sm">
          Swell compass, score breakdown, timeline, and hourly data will render here
        </p>
      </div>
    </div>
  )
}
