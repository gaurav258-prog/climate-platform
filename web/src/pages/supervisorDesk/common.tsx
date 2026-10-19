import clsx from 'clsx'
import { HEADING, messageDetails, type DetailSection, type Message } from '../../components/Details'

// Shared bits of the supervisor's desk — requests and findings, the mandates and who they apply to, the entity file
// (UI standard, 2026-10-16): dates and durations in the reader's words, one progress meter, one segmented switch.
export { day, field } from '../respondent/common'

// A duration in hours, in the unit a reader thinks in: '35 min', '6.5 h', '3.2 d'.
export const hrs = (h: number | null | undefined) => h == null ? '—' : h < 1 ? `${Math.round(h * 60)} min` : h < 48 ? `${h.toFixed(1)} h` : `${(h / 24).toFixed(1)} d`

// A server message's detail as the sections of a page's About pop-up.
export const aboutOf = (m?: Message | null): DetailSection[] => m ? messageDetails(m).sections : []
export const shows = (body: React.ReactNode): DetailSection => ({ heading: HEADING.shows, body })

// How far a count has come: 'filed 3 of 5' as a bar, coloured by whether it is complete.
export function Meter({ value, total, label, late }: { value: number; total: number; label?: string; late?: boolean }) {
  if (!total) return <span className="inline-flex min-w-[7.5rem] text-[11.5px] text-[var(--color-faint)]">None applies yet</span>
  const pct = total ? Math.round((value / total) * 100) : 0
  const color = total && value >= total ? 'var(--color-good)' : late ? 'var(--color-bad)' : 'var(--color-warn)'
  return (
    <span className="inline-flex items-center gap-2 min-w-[7.5rem]" title={label ?? `${value} of ${total}`}>
      <span className="relative h-1.5 flex-1 rounded-full bg-[var(--color-panel-2)] overflow-hidden" role="img" aria-label={label ?? `${value} of ${total}`}>
        <span className="absolute inset-y-0 left-0 rounded-full" style={{ width: `${total ? Math.max(4, pct) : 0}%`, background: color }} />
      </span>
      <span className="text-[11.5px] tabular-nums text-[var(--color-mute)] whitespace-nowrap">{value} of {total}</span>
    </span>
  )
}

// A segmented switch: views of one page, or a filter with a few values.
export function Segmented<K extends string>({ options, value, onChange, label }: { options: [K, string][]; value: K; onChange: (k: K) => void; label: string }) {
  return (
    <div role="group" aria-label={label} className="inline-flex rounded-lg border border-[var(--color-line-2)] overflow-hidden text-[12.5px]">
      {options.map(([k, l]) => (
        <button key={k} type="button" onClick={() => onChange(k)} aria-pressed={value === k}
          className={clsx('px-3 py-1.5 transition', value === k ? 'bg-[var(--color-panel-2)] text-[var(--color-ink)] font-medium' : 'text-[var(--color-mute)] hover:text-[var(--color-ink)]')}>{l}</button>))}
    </div>
  )
}

// A label and its value, in a drawer or pop-up.
export function Facts({ rows }: { rows: [string, React.ReactNode][] }) {
  return (
    <dl className="grid grid-cols-[9rem_1fr] gap-x-3 gap-y-1.5 text-[12.5px] m-0">
      {rows.map(([k, v]) => <div key={k} className="contents"><dt className="text-[var(--color-mute)]">{k}</dt><dd className="m-0 min-w-0 break-words text-[var(--color-ink)]">{v ?? '—'}</dd></div>)}
    </dl>
  )
}

export const Loading = ({ what }: { what: string }) => <div className="py-10 text-center text-[var(--color-faint)] text-sm">Loading {what}…</div>
export const Failed = ({ what }: { what: string }) => <div className="py-6 text-center text-[13px] text-[var(--color-bad)]">Could not load {what}.</div>
