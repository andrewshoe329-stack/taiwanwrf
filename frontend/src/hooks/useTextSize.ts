import { createContext, useContext, useState, useCallback, useEffect } from 'react'

export type TextSizePreset = 'default' | 'large' | 'xlarge'

const STORAGE_KEY = 'tw-forecast-text-size'

const MULTIPLIERS: Record<TextSizePreset, number> = {
  default: 1.0,
  large: 1.3,
  xlarge: 1.6,
}

const BASE_SIZES = {
  micro: 8,
  compact: 10,
  body: 12,
  label: 14,
}

function applyScale(preset: TextSizePreset) {
  const m = MULTIPLIERS[preset]
  const root = document.documentElement.style
  root.setProperty('--fs-micro', `${Math.round(BASE_SIZES.micro * m)}px`)
  root.setProperty('--fs-compact', `${Math.round(BASE_SIZES.compact * m)}px`)
  root.setProperty('--fs-body', `${Math.round(BASE_SIZES.body * m)}px`)
  root.setProperty('--fs-label', `${Math.round(BASE_SIZES.label * m)}px`)
}

function loadPreset(): TextSizePreset {
  const saved = localStorage.getItem(STORAGE_KEY)
  if (saved && saved in MULTIPLIERS) return saved as TextSizePreset
  return 'default'
}

export interface TextSizeState {
  preset: TextSizePreset
  setPreset: (p: TextSizePreset) => void
  /** Return a scaled pixel value for Recharts/canvas inline fontSize props */
  scaled: (basePx: number) => number
}

const defaultState: TextSizeState = {
  preset: 'default',
  setPreset: () => {},
  scaled: (px: number) => px,
}

export const TextSizeContext = createContext<TextSizeState>(defaultState)

export function useTextSizeProvider(): TextSizeState {
  const [preset, setPresetState] = useState<TextSizePreset>(loadPreset)

  const setPreset = useCallback((p: TextSizePreset) => {
    setPresetState(p)
    localStorage.setItem(STORAGE_KEY, p)
    applyScale(p)
  }, [])

  const scaled = useCallback((basePx: number) => {
    return Math.round(basePx * MULTIPLIERS[preset])
  }, [preset])

  // Apply on mount
  useEffect(() => {
    applyScale(preset)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  return { preset, setPreset, scaled }
}

export function useTextSize() {
  return useContext(TextSizeContext)
}
