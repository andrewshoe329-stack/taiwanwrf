import { useTextSize, type TextSizePreset } from '@/hooks/useTextSize'

const PRESETS: TextSizePreset[] = ['default', 'large', 'xlarge']
const LABELS: Record<TextSizePreset, string> = {
  default: 'A',
  large: 'A⁺',
  xlarge: 'A⁺⁺',
}

export function TextSizeToggle() {
  const { preset, setPreset } = useTextSize()

  const cycle = () => {
    const idx = PRESETS.indexOf(preset)
    setPreset(PRESETS[(idx + 1) % PRESETS.length])
  }

  return (
    <button
      onClick={cycle}
      className="h-7 px-2 fs-body font-medium text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] transition-colors"
      aria-label={`Text size: ${preset}`}
      title={`Text size: ${preset}`}
    >
      {LABELS[preset]}
    </button>
  )
}
