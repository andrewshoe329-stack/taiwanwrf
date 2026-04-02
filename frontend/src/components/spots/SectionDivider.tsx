export function SectionDivider({ label }: { label?: string }) {
  return (
    <div className="border-t border-[var(--color-border)] pt-2">
      {label && (
        <span className="fs-micro uppercase tracking-wider font-semibold text-[var(--color-text-dim)]">
          {label}
        </span>
      )}
    </div>
  )
}
