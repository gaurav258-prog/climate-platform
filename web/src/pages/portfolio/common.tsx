import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { AlertTriangle } from 'lucide-react'
import { HEADING, InfoButton, messageDetails, type DetailSection, type Details, type Message } from '../../components/Details'
import { SectionHead } from '../../components/ui'

// The Portfolio page's shared pieces (UI standard, 2026-10-16): each card's explanation sits behind one "How it's
// calculated" pop-up — what the card shows in the page's words, then the method in the words of the server that
// computed the figure (its catalogue message, core/messages.py), so the two can never drift apart.

export const CALC = 'How it’s calculated'
export const METHOD_TAB = '/admin?tab=Methodology'

// what → how it is calculated, why → its limits, next → what the reader can do
export function calcDetails(title: string, shows: ReactNode, m?: Message | null, read?: ReactNode): Details {
  const d = m?.detail ?? {}
  const sections: DetailSection[] = [{ heading: HEADING.shows, body: shows }]
  if (read) sections.push({ heading: HEADING.read, body: read })
  if (d.what) sections.push({ heading: CALC, body: d.what })
  if (d.why) sections.push({ heading: HEADING.limits, body: d.why })
  if (d.next) sections.push({ heading: 'What you can do', body: d.next })
  return { title, sections }
}

// A card's heading row: its title on the left, "How it's calculated" on the right.
export function CardHead({ title, hint, details, className }: { title: ReactNode; hint?: ReactNode; details: Details; className?: string }) {
  return (
    <div className={`flex flex-wrap items-center justify-between gap-x-4 gap-y-1 ${className ?? 'mb-3'}`}>
      <SectionHead hint={hint}>{title}</SectionHead>
      <InfoButton details={details} label={CALC} />
    </div>
  )
}

// A figure that is missing for a reason other than a method choice (a calculation setting, a missing input): the
// reason's label on the screen, its explanation in the pop-up, and where to fix it.
export function GapLine({ what, m, to }: { what: string; m: Message; to?: string }) {
  return (
    <div className="rounded-xl border border-[var(--color-warn)]/40 bg-[var(--color-panel)] px-4 py-2.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[12.5px]">
      <AlertTriangle size={14} className="text-[var(--color-warn)] shrink-0" />
      <span className="text-[var(--color-ink)] flex-1 min-w-0"><b>{what}: </b>{m.label}</span>
      <InfoButton compact details={messageDetails(m)} />
      {to && <Link to={to} className="text-[var(--color-sky)] hover:underline whitespace-nowrap">Set it →</Link>}
    </div>
  )
}

// Small chips — a sector, a hazard, a collateral — in the product's type, never the code font.
export function Chip({ children, title }: { children: ReactNode; title?: string }) {
  return <span title={title} className="text-[11.5px] px-2 py-1 rounded-lg border border-[var(--color-line-2)] text-[var(--color-mute)] tabular-nums">{children}</span>
}

export const pct = (v: number | null | undefined) => (v == null ? '—' : `${v}%`)
