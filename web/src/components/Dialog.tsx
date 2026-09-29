import { type ReactNode, useEffect, useId, useRef } from 'react'
import { X } from 'lucide-react'
import clsx from 'clsx'
import { Card, SectionHead } from './ui'

// The one modal dialog: Escape closes it, a click on the backdrop closes it, it is announced as a modal dialog named
// by its title, the close button is labelled, focus moves into it on open and returns to where it was on close.
// Pages use this rather than their own fixed overlay, so every dialog behaves — and is accessible — the same way.
export function Dialog({ title, onClose, children, className }: {
  title: ReactNode; onClose: () => void; children: ReactNode; className?: string
}) {
  const titleId = useId()
  const box = useRef<HTMLDivElement>(null)
  // the latest onClose, without re-running the open/close effect (callers pass a new function every render, and
  // re-running would pull focus back to the dialog in the middle of the user's work)
  const close = useRef(onClose)
  useEffect(() => { close.current = onClose }, [onClose])
  useEffect(() => {
    const before = document.activeElement as HTMLElement | null
    box.current?.focus()
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') { e.stopPropagation(); close.current() } }
    document.addEventListener('keydown', onKey)
    return () => { document.removeEventListener('keydown', onKey); before?.focus?.() }
  }, [])
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="absolute inset-0 bg-black/50" aria-hidden="true" />
      <div ref={box} role="dialog" aria-modal="true" aria-labelledby={titleId} tabIndex={-1}
        className={clsx('relative w-full max-w-lg outline-none', className)} onClick={e => e.stopPropagation()}>
        <Card className="p-0 overflow-hidden">
          <div className="flex items-center justify-between px-5 py-3 border-b border-[var(--color-line)]">
            <span id={titleId}><SectionHead>{title}</SectionHead></span>
            <button type="button" onClick={onClose} aria-label="Close" className="text-[var(--color-faint)] hover:text-[var(--color-ink)]"><X size={17} /></button>
          </div>
          <div className="p-5 max-h-[78vh] overflow-y-auto">{children}</div>
        </Card>
      </div>
    </div>
  )
}
