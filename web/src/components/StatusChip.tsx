import clsx from 'clsx'
import { statusLabel } from '../lib/hazards'

// One chip for every status the product shows (UI standard, 2026-10-16): the customer word for the code, in the
// product's own type (not the code font), coloured by what the status means for the reader.
type Tone = 'good' | 'warn' | 'bad' | 'neutral'
const TONE: Record<string, Tone> = {
  active: 'good', paid: 'good', delivered: 'good', approved: 'good', accepted: 'good', attested: 'good', filed: 'good',
  submitted: 'good', released: 'good', done: 'good', published: 'good', resolved: 'good', in_use: 'good', landed: 'good',
  pending: 'warn', open: 'warn', in_review: 'warn', returned: 'warn', draft: 'neutral', in_progress: 'neutral',
  past_due: 'bad', overdue: 'bad', failed: 'bad', rejected: 'bad', breached: 'bad', refused: 'bad', expired: 'bad',
  held: 'warn', candidate: 'neutral', staged: 'neutral', proposed: 'warn', computing: 'neutral',
}
const COLOR: Record<Tone, string> = {
  good: 'var(--color-good)', warn: 'var(--color-warn)', bad: 'var(--color-bad)', neutral: 'var(--color-slate)',
}

export function StatusChip({ value, label, tone, className }: { value?: string | null; label?: string; tone?: Tone; className?: string }) {
  const c = COLOR[tone ?? TONE[value ?? ''] ?? 'neutral']
  return (
    <span className={clsx('inline-flex items-center gap-1.5 text-[11.5px] font-medium px-2 py-0.5 rounded-full whitespace-nowrap', className)}
      style={{ color: c, background: `color-mix(in oklab, ${c} 13%, transparent)` }}>
      <span className="w-1.5 h-1.5 rounded-full" style={{ background: c }} />
      {label ?? statusLabel(value)}
    </span>
  )
}
