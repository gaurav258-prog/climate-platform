import { useMemo } from 'react'

const BANDS = [
  { key: 'LOW',       label: 'Low',       color: '#10b981' },
  { key: 'MEDIUM',    label: 'Medium',    color: '#f59e0b' },
  { key: 'HIGH',      label: 'High',      color: '#f97316' },
  { key: 'VERY_HIGH', label: 'V.High',    color: '#ef4444' },
]

export default function StatsBar({ scores }) {
  const stats = useMemo(() => {
    if (!scores.length) return null
    const counts = { LOW: 0, MEDIUM: 0, HIGH: 0, VERY_HIGH: 0 }
    let sum = 0, peak = 0
    for (const s of scores) {
      counts[s.risk_level] = (counts[s.risk_level] ?? 0) + 1
      sum += s.score
      if (s.score > peak) peak = s.score
    }
    return { counts, peak, mean: Math.round(sum / scores.length) }
  }, [scores])

  if (!stats) return null

  return (
    <div className="flex items-center gap-6 px-5 h-9 bg-slate-950 border-b border-slate-800 shrink-0">
      {/* Risk level counts */}
      <div className="flex items-center gap-5">
        {BANDS.map(b => (
          <div key={b.key} className="flex items-center gap-2">
            <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: b.color }} />
            <span className="text-[11px] text-slate-500 whitespace-nowrap">{b.label}</span>
            <span
              className="text-[12px] font-medium tabular-nums"
              style={{ color: b.color }}
            >
              {(stats.counts[b.key] ?? 0).toLocaleString()}
            </span>
          </div>
        ))}
      </div>

      <span className="w-px h-4 bg-slate-800" />

      {/* Aggregate stats */}
      <div className="flex items-center gap-5">
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-slate-600 uppercase tracking-widest">Peak</span>
          <span className="text-[12px] font-semibold tabular-nums text-slate-200">{stats.peak}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-slate-600 uppercase tracking-widest">Mean</span>
          <span className="text-[12px] font-semibold tabular-nums text-slate-200">{stats.mean}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-slate-600 uppercase tracking-widest">Cells</span>
          <span className="text-[12px] font-semibold tabular-nums text-slate-200">
            {scores.length.toLocaleString()}
          </span>
        </div>
      </div>
    </div>
  )
}
