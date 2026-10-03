import type { CSSProperties, ReactNode } from 'react'
import clsx from 'clsx'
import { useOverlay } from './overlay'

// The one side drawer — Dialog's sibling for panels that slide in from the right edge. Same behaviour: Escape
// closes it, a click on the scrim closes it, it is announced as a modal dialog named by `label`, focus moves into it
// on open and returns on close. The page keeps its own header and places a (labelled) CloseButton in it.
//
// `className` / `style` style the panel (width, padding, scrolling); `resize` adds the drag handle on the left edge
// (from useResizableWidth). `placement="left"` slides in from the left edge (the app menu on small screens).
// `placement="full"` is the full-screen takeover variant (the filing view): it covers the page, so there is no scrim
// to click — Escape or the close button dismiss it.
export function Drawer({ label, onClose, children, className, style, resize, placement = 'right', overlayClassName, backdropClassName }: {
  label: string; onClose: () => void; children: ReactNode; className?: string; style?: CSSProperties
  resize?: { start: (e: React.MouseEvent | React.TouchEvent) => void; reset: () => void }
  placement?: 'right' | 'left' | 'full'; overlayClassName?: string; backdropClassName?: string
}) {
  const box = useOverlay<HTMLDivElement>(onClose)
  const panel = (
    <div ref={box} role="dialog" aria-modal="true" aria-label={label} tabIndex={-1} style={style}
      className={clsx('relative outline-none', className)} onClick={e => e.stopPropagation()}>
      {resize && <div onMouseDown={resize.start} onTouchStart={resize.start} onDoubleClick={resize.reset} title="Drag to resize · double-click to reset" aria-hidden="true"
        className="absolute top-0 left-0 h-full w-1.5 cursor-col-resize hover:bg-[color-mix(in_oklab,var(--color-sky)_45%,transparent)] active:bg-[var(--color-sky)] transition z-30" />}
      {children}
    </div>
  )
  if (placement === 'full') return <div className={clsx('fixed inset-0 overflow-y-auto bg-[var(--color-bg)]', overlayClassName ?? 'z-50')}>{panel}</div>
  return (
    <div className={clsx('fixed inset-0 flex', placement === 'left' ? 'justify-start' : 'justify-end', overlayClassName ?? 'z-50')} onClick={onClose}>
      <div className={clsx('absolute inset-0', backdropClassName ?? 'bg-black/40')} aria-hidden="true" />
      {panel}
    </div>
  )
}
