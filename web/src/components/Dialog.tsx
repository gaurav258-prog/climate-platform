import { type ReactNode, useId } from 'react'
import { ChevronRight, X } from 'lucide-react'
import clsx from 'clsx'
import { Card, SectionHead } from './ui'
import { useOverlay } from './overlay'

// The one labelled close control for every overlay. `icon="back"` is the ‹ used by resizable side drawers; `look`
// replaces the default faint-glyph styling for a page with its own close design (the round buttons on the globe).
export function CloseButton({ onClick, size = 18, icon = 'x', label = 'Close', className, look }: {
  onClick: () => void; size?: number; icon?: 'x' | 'back'; label?: string; className?: string; look?: string
}) {
  return (
    <button type="button" onClick={onClick} aria-label={label} title={label}
      className={clsx(look ?? 'text-[var(--color-faint)] hover:text-[var(--color-ink)]', 'shrink-0', className)}>
      {icon === 'back' ? <ChevronRight size={size} className="rotate-180" /> : <X size={size} />}
    </button>
  )
}

// The one modal dialog: Escape closes it, a click on the backdrop closes it, it is announced as a modal dialog named
// by its title, the close button is labelled, focus moves into it on open and returns to where it was on close.
// Pages use this rather than their own fixed overlay, so every dialog behaves — and is accessible — the same way.
//
// Default: the standard card with a title bar and close button. `bare`: the page keeps its own panel design —
// `className` styles the panel, `title` (a string) becomes its accessible name, and the page places a CloseButton
// itself. `overlayClassName` / `backdropClassName` override the layer (z-index, padding) and the scrim.
type DialogProps = { onClose: () => void; children: ReactNode; className?: string; overlayClassName?: string; backdropClassName?: string }
  & ({ bare?: false; title: ReactNode } | { bare: true; title: string })

export function Dialog({ title, onClose, children, className, bare, overlayClassName, backdropClassName }: DialogProps) {
  const titleId = useId()
  const box = useOverlay<HTMLDivElement>(onClose)
  const name = bare ? { 'aria-label': title } : { 'aria-labelledby': titleId }
  return (
    <div className={clsx('fixed inset-0 flex items-center justify-center', overlayClassName ?? 'z-50 p-4')} onClick={onClose}>
      <div className={clsx('absolute inset-0', backdropClassName ?? 'bg-black/50')} aria-hidden="true" />
      <div ref={box} role="dialog" aria-modal="true" {...name} tabIndex={-1}
        className={clsx('relative outline-none', !bare && 'w-full max-w-lg', className)} onClick={e => e.stopPropagation()}>
        {bare ? children : (
          <Card className="p-0 overflow-hidden">
            <div className="flex items-center justify-between px-5 py-3 border-b border-[var(--color-line)]">
              <span id={titleId}><SectionHead>{title}</SectionHead></span>
              <CloseButton onClick={onClose} size={17} />
            </div>
            <div className="p-5 max-h-[78vh] overflow-y-auto">{children}</div>
          </Card>
        )}
      </div>
    </div>
  )
}
