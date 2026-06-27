// The universal "risk number" — one component rendered identically on the map,
// the portfolio table, the asset drawer and reports. This consistency is what
// makes the whole product feel like one thing. Score + bucket colour, traceable.

export const BUCKET = {
  L: { c: '#1a8a4a', bg: '#e8f8ee', label: 'Low' },
  M: { c: '#b56a00', bg: '#fff2e0', label: 'Medium' },
  H: { c: '#c2410c', bg: '#ffe9d6', label: 'High' },
  VH: { c: '#c81e1e', bg: '#ffe1df', label: 'Very High' },
}

const SIZES = {
  sm: 'text-[11px] px-1.5 py-0.5 rounded-md min-w-[26px]',
  md: 'text-[13px] px-2 py-0.5 rounded-lg min-w-[30px]',
  lg: 'text-2xl px-3 py-1 rounded-xl min-w-[52px]',
}

export default function RiskAtom({ score, bucket, size = 'md', showLabel = false, title }) {
  if (score == null || bucket == null) {
    return (
      <span className={`inline-flex items-center justify-center font-medium text-gray-400 bg-gray-100 ${SIZES[size]}`}
        title="no canonical score for this cell">—</span>
    )
  }
  const b = BUCKET[bucket] || BUCKET.L
  return (
    <span className={`inline-flex items-center justify-center gap-1.5 font-semibold tabular-nums ${SIZES[size]}`}
      style={{ background: b.bg, color: b.c }}
      title={title || `${b.label} · ${Math.round(score)}/100`}>
      {Math.round(score)}
      {showLabel && <span className="font-medium opacity-80">{b.label}</span>}
    </span>
  )
}
