// The Confidence Grade (A–E) badge: a transparent summary of trust in a crop's €.
// It SHOWS ITS WORK on hover (the four checks) — it never hides the underlying stats.
const GRADE_STYLE = {
  A: 'bg-emerald-100 text-emerald-800', B: 'bg-blue-100 text-[#0071e3]',
  C: 'bg-amber-100 text-amber-800', D: 'bg-orange-100 text-orange-800', E: 'bg-gray-200 text-gray-600',
}
const CHECK_NAME = {
  predictive: 'Holds up on new years', evidence_depth: 'Depth of evidence',
  honest_range: 'Range is honest', directness: 'Proof type',
}

export default function GradeBadge({ grade, checks }) {
  if (!grade) return null
  const tip = (checks || []).map(c => `${CHECK_NAME[c.key] || c.key}: ${c.label} — ${c.detail}`).join('\n')
  return (
    <span title={`Confidence grade ${grade}\n${tip}`}
      className={`rounded-full px-1.5 py-0.5 text-[9px] font-bold ${GRADE_STYLE[grade] || GRADE_STYLE.E}`}>
      confidence&nbsp;{grade}
    </span>
  )
}
