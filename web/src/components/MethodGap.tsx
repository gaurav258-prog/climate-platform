import { Link } from 'react-router-dom'
import { AlertTriangle } from 'lucide-react'
import { InfoButton, HEADING } from './Details'
import { gapMethodKeys, methodLabel, useLabels } from '../lib/labels'

// A money figure that is a gap: the institution has not stated a method choice the figure needs for the year (E69).
// The main screen names what is missing in customer words and links to where it is stated; the explanation, and any
// other reason a figure is missing, sit in the details pop-up — never a number in its place.
export default function MethodGap({ gap, what }: { gap?: string | null; what?: string }) {
  const labels = useLabels()
  if (!gap) return null
  const keys = gapMethodKeys(gap)
  const needs = keys.length ? [...new Set(keys.map(k => methodLabel(labels, k)))].join(', ') : null
  const details = {
    title: what ?? 'Why this figure is not shown',
    sections: [
      { heading: HEADING.shows, body: needs
        ? 'This figure depends on a choice only your institution makes for the year. Until it is stated, the figure is not shown — it is never estimated in its place.'
        : 'This figure cannot be computed yet.' },
      ...(needs ? [{ heading: 'What is needed', body: needs }] : [{ heading: 'Why', body: gap }]),
    ],
  }
  return (
    <div className="rounded-xl border border-[var(--color-warn)]/40 bg-[var(--color-panel)] px-4 py-2.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[12.5px]">
      <AlertTriangle size={14} className="text-[var(--color-warn)] shrink-0" />
      <span className="text-[var(--color-ink)] flex-1 min-w-0">
        {what ? <b>{what}: </b> : null}{needs ? <>needs your input — {needs}</> : 'not available yet'}
      </span>
      <InfoButton compact details={details} />
      {needs && <Link to="/admin?tab=Methodology" className="text-[var(--color-sky)] hover:underline whitespace-nowrap">Add it →</Link>}
    </div>
  )
}
