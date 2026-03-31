import { useState } from 'react'
import { useTranslation } from 'react-i18next'

export function ShareButton({ locationId }: { locationId?: string | null }) {
  const { i18n } = useTranslation()
  const lang = i18n.language?.startsWith('zh') ? 'zh' : 'en'
  const [copied, setCopied] = useState(false)

  const handleShare = async () => {
    const url = new URL(window.location.href)
    // Ensure loc param reflects current selection
    if (locationId) {
      url.searchParams.set('loc', locationId)
    } else {
      url.searchParams.delete('loc')
    }
    const shareUrl = url.toString()

    // Try native share first (mobile), fall back to clipboard
    if (navigator.share) {
      try {
        await navigator.share({
          title: lang === 'zh' ? '台灣天氣預報' : 'Taiwan Weather Forecast',
          url: shareUrl,
        })
        return
      } catch {
        // User cancelled or share failed — fall through to clipboard
      }
    }

    try {
      await navigator.clipboard.writeText(shareUrl)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // Fallback: select from a temp input
      const input = document.createElement('input')
      input.value = shareUrl
      document.body.appendChild(input)
      input.select()
      document.execCommand('copy')
      document.body.removeChild(input)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  return (
    <button
      onClick={handleShare}
      className="w-6 h-6 flex items-center justify-center rounded-full hover:bg-[var(--color-bg-elevated)] text-[var(--color-text-muted)] transition-colors"
      aria-label={lang === 'zh' ? '分享' : 'Share'}
      title={lang === 'zh' ? '分享連結' : 'Share link'}
    >
      {copied ? (
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#22c55e" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <path d="M20 6 L9 17 L4 12" />
        </svg>
      ) : (
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="18" cy="5" r="3" /><circle cx="6" cy="12" r="3" /><circle cx="18" cy="19" r="3" />
          <line x1="8.59" y1="13.51" x2="15.42" y2="17.49" />
          <line x1="15.41" y1="6.51" x2="8.59" y2="10.49" />
        </svg>
      )}
    </button>
  )
}
