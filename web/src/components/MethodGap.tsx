import { Link } from 'react-router-dom'
import { AlertTriangle } from 'lucide-react'

// A money figure that is a gap: the institution has not stated the method it needs for the year (E69). Names what is
// missing ('not stated: <key>' or a sentence) and where it is stated — never a number in its place.
export default function MethodGap({ gap, what }: { gap?: string | null; what?: string }) {
  if (!gap) return null
  return (
    <div className="rounded-xl border border-[var(--color-warn)]/40 bg-[var(--color-panel)] px-4 py-2.5 flex flex-wrap items-start gap-x-3 gap-y-1 text-[12.5px]">
      <AlertTriangle size={14} className="text-[var(--color-warn)] mt-0.5 shrink-0" />
      <span className="text-[var(--color-mute)] flex-1 min-w-0">
        {what ? <b className="text-[var(--color-ink)]">{what}: </b> : null}
        {gap.startsWith('not stated: ')
          ? <>not computed — it rests on your own method, and {gap.replace(/^not stated: /, '')} {gap.includes(',') ? 'are' : 'is'} not stated for this year.</>
          : <>not computed — {gap}.</>}
      </span>
      <Link to="/admin?tab=Methodology" className="text-[var(--color-sky)] hover:underline whitespace-nowrap">State your method →</Link>
    </div>
  )
}
