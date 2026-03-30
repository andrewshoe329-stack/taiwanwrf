import { useRef, useCallback, useState, useEffect, type ReactNode } from 'react'
import { useIsMobile } from '@/hooks/useIsMobile'

const PEEK = 160   // enough for timeline + conditions strip
const HALF_RATIO = 0.55
const FULL_RATIO = 0.92

type SnapPoint = 'peek' | 'half' | 'full'

interface BottomSheetProps {
  children: ReactNode
  snapTo?: SnapPoint
}

function getSnapHeight(snap: SnapPoint, vh: number, mobile: boolean): number {
  switch (snap) {
    case 'peek': return mobile ? PEEK : vh  // desktop: always full panel
    case 'half': return mobile ? vh * HALF_RATIO : vh
    case 'full': return mobile ? vh * FULL_RATIO : vh
  }
}

export function BottomSheet({ children, snapTo }: BottomSheetProps) {
  const mobile = useIsMobile()
  const sheetRef = useRef<HTMLDivElement>(null)
  const dragRef = useRef({ startY: 0, startHeight: 0, dragging: false })
  const [height, setHeight] = useState(PEEK)
  const [snap, setSnap] = useState<SnapPoint>('peek')
  const [transitioning, setTransitioning] = useState(false)
  const vh = typeof window !== 'undefined' ? window.innerHeight : 800

  // Desktop: always show as full-height side panel (no dragging)
  useEffect(() => {
    if (!mobile) {
      setHeight(vh)
      setSnap('full')
    }
  }, [mobile, vh])

  // External snap control (mobile only)
  useEffect(() => {
    if (!mobile) return
    if (snapTo && snapTo !== snap) {
      setSnap(snapTo)
      setHeight(getSnapHeight(snapTo, vh, mobile))
      setTransitioning(true)
    }
  }, [snapTo, snap, vh, mobile])

  const snapToNearest = useCallback((h: number) => {
    if (!mobile) return
    const peekH = PEEK
    const halfH = vh * HALF_RATIO
    const fullH = vh * FULL_RATIO

    const dists = [
      { snap: 'peek' as SnapPoint, dist: Math.abs(h - peekH) },
      { snap: 'half' as SnapPoint, dist: Math.abs(h - halfH) },
      { snap: 'full' as SnapPoint, dist: Math.abs(h - fullH) },
    ]
    dists.sort((a, b) => a.dist - b.dist)
    const target = dists[0]
    setSnap(target.snap)
    setHeight(getSnapHeight(target.snap, vh, true))
    setTransitioning(true)
  }, [vh, mobile])

  const onPointerDown = useCallback((e: React.PointerEvent) => {
    if (!mobile) return // no dragging on desktop
    e.preventDefault()
    dragRef.current = { startY: e.clientY, startHeight: height, dragging: true }
    setTransitioning(false)

    const onMove = (ev: PointerEvent) => {
      if (!dragRef.current.dragging) return
      const dy = dragRef.current.startY - ev.clientY
      const newH = Math.max(PEEK, Math.min(vh * FULL_RATIO, dragRef.current.startHeight + dy))
      setHeight(newH)
    }

    const onUp = () => {
      dragRef.current.dragging = false
      snapToNearest(height)
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('pointerup', onUp)
    }

    window.addEventListener('pointermove', onMove)
    window.addEventListener('pointerup', onUp)
  }, [height, vh, snapToNearest, mobile])

  const heightRef = useRef(height)
  heightRef.current = height

  // Desktop: side panel (right column)
  if (!mobile) {
    return (
      <div className="h-full overflow-y-auto bg-[var(--color-bg)] border-l border-[var(--color-border)]">
        <div className="px-4 py-3">
          {children}
        </div>
      </div>
    )
  }

  // Mobile: bottom sheet overlay
  return (
    <div
      ref={sheetRef}
      className={`absolute bottom-0 left-0 right-0 z-40 bg-[var(--color-bg)] border-t border-[var(--color-border)] rounded-t-2xl overflow-hidden ${
        transitioning ? 'transition-[height] duration-300 ease-out' : ''
      }`}
      style={{ height, paddingBottom: 'env(safe-area-inset-bottom, 0px)' }}
      onTransitionEnd={() => setTransitioning(false)}
    >
      {/* Drag handle */}
      <div
        className="flex items-center justify-center py-2 cursor-grab active:cursor-grabbing touch-none select-none"
        onPointerDown={onPointerDown}
      >
        <div className="w-10 h-1 rounded-full bg-[var(--color-border)]" />
      </div>

      {/* Scrollable content */}
      <div
        className="overflow-y-auto overscroll-contain px-4"
        style={{ height: height - 28 }}
      >
        {children}
      </div>
    </div>
  )
}
