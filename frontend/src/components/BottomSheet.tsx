import { useRef, useCallback, useState, useEffect, type ReactNode } from 'react'

const PEEK = 120
const HALF_RATIO = 0.5
const FULL_RATIO = 0.92

type SnapPoint = 'peek' | 'half' | 'full'

interface BottomSheetProps {
  children: ReactNode
  /** Force snap to a specific point (e.g. when selecting a spot) */
  snapTo?: SnapPoint
}

function getSnapHeight(snap: SnapPoint, vh: number): number {
  switch (snap) {
    case 'peek': return PEEK
    case 'half': return vh * HALF_RATIO
    case 'full': return vh * FULL_RATIO
  }
}

export function BottomSheet({ children, snapTo }: BottomSheetProps) {
  const sheetRef = useRef<HTMLDivElement>(null)
  const dragRef = useRef({ startY: 0, startHeight: 0, dragging: false })
  const [height, setHeight] = useState(PEEK)
  const [snap, setSnap] = useState<SnapPoint>('peek')
  const [transitioning, setTransitioning] = useState(false)
  const vh = typeof window !== 'undefined' ? window.innerHeight : 800

  // External snap control
  useEffect(() => {
    if (snapTo && snapTo !== snap) {
      setSnap(snapTo)
      setHeight(getSnapHeight(snapTo, vh))
      setTransitioning(true)
    }
  }, [snapTo, snap, vh])

  const snapToNearest = useCallback((h: number) => {
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
    setHeight(getSnapHeight(target.snap, vh))
    setTransitioning(true)
  }, [vh])

  const onPointerDown = useCallback((e: React.PointerEvent) => {
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
  }, [height, vh, snapToNearest])

  // Snap on up using the latest height via ref
  const heightRef = useRef(height)
  heightRef.current = height

  return (
    <div
      ref={sheetRef}
      className={`absolute bottom-0 left-0 right-0 z-40 bg-[var(--color-bg)] border-t border-[var(--color-border)] rounded-t-2xl overflow-hidden ${
        transitioning ? 'transition-[height] duration-300 ease-out' : ''
      }`}
      style={{ height }}
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
        style={{ height: height - 28, paddingBottom: 'env(safe-area-inset-bottom, 16px)' }}
      >
        {children}
      </div>
    </div>
  )
}
