import { type ReactNode, useState } from 'react'
import { Info } from 'lucide-react'
import clsx from 'clsx'
import { Dialog } from './Dialog'

// The UI standard (product owner, 2026-10-16): the main screen carries as little text as possible; anything more lives
// one click away, in a pop-up written as structured, professional text. This is that pop-up and the button that opens
// it. Sections use the standard headings, in this order, so every explanation in the product reads the same way.
export const HEADING = {
  shows: 'What this shows', read: 'How to read it', sources: 'Data sources', limits: 'Limits',
} as const

export type DetailSection = { heading: string; body: ReactNode }
export type Details = { title: ReactNode; sections: DetailSection[] }

export function DetailsBody({ sections }: { sections: DetailSection[] }) {
  return (
    <div className="space-y-4">
      {sections.map((s, i) => (
        <section key={i}>
          <h4 className="text-[12px] font-semibold uppercase tracking-[0.08em] text-[var(--color-mute)] m-0 mb-1.5">{s.heading}</h4>
          <div className="text-[13.5px] leading-relaxed text-[var(--color-ink)]">{s.body}</div>
        </section>
      ))}
    </div>
  )
}

// ⓘ (compact) or "About this page" — opens the details pop-up.
export function InfoButton({ details, label, compact, className }: {
  details: Details; label?: string; compact?: boolean; className?: string
}) {
  const [open, setOpen] = useState(false)
  if (!details.sections.length) return null
  const name = typeof details.title === 'string' ? `More about ${details.title}` : 'More details'
  return (
    <>
      <button type="button" onClick={() => setOpen(true)} aria-label={compact ? name : undefined}
        className={clsx('inline-flex items-center gap-1 text-[var(--color-faint)] hover:text-[var(--color-sky)] transition align-middle', className)}>
        <Info size={compact ? 14 : 13} />
        {!compact && <span className="text-[12.5px]">{label ?? 'About this page'}</span>}
      </button>
      {open && <Dialog title={details.title} onClose={() => setOpen(false)} className="max-w-xl"><DetailsBody sections={details.sections} /></Dialog>}
    </>
  )
}

export { isShort, textOf } from '../lib/brevity'
