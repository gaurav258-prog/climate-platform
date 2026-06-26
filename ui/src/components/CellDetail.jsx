import { X, TrendingUp, TrendingDown, Minus } from 'lucide-react'

const RISK_COLOR = {
  LOW:       '#10b981',
  MEDIUM:    '#f59e0b',
  HIGH:      '#f97316',
  VERY_HIGH: '#ef4444',
}

const RISK_LABEL = {
  LOW:       'Low',
  MEDIUM:    'Medium',
  HIGH:      'High',
  VERY_HIGH: 'Very High',
}

function VelocityRow({ v }) {
  if (v == null) return null
  const abs = Math.abs(v).toFixed(1)
  if (Math.abs(v) < 0.5) return (
    <div className="flex items-center gap-1.5 text-[11px] text-slate-600">
      <Minus size={11} strokeWidth={1.5} />
      <span>Stable</span>
    </div>
  )
  return v > 0 ? (
    <div className="flex items-center gap-1.5 text-[11px] text-red-400">
      <TrendingUp size={11} strokeWidth={1.5} />
      <span>+{abs} pts / 24 h</span>
    </div>
  ) : (
    <div className="flex items-center gap-1.5 text-[11px] text-emerald-400">
      <TrendingDown size={11} strokeWidth={1.5} />
      <span>−{abs} pts / 24 h</span>
    </div>
  )
}

export default function CellDetail({ cell, onClose }) {
  if (!cell) return null

  const color  = RISK_COLOR[cell.risk_level] ?? '#64748b'
  const label  = RISK_LABEL[cell.risk_level] ?? cell.risk_level

  return (
    <div className="absolute bottom-6 right-4 z-10 w-60">
      <div className="bg-slate-950/95 backdrop-blur border border-slate-800 rounded overflow-hidden shadow-xl">

        {/* Score bar */}
        <div className="h-0.5 w-full" style={{ backgroundColor: color }} />

        {/* Header */}
        <div className="flex items-start justify-between px-4 pt-3 pb-2">
          <div className="min-w-0 pr-2">
            <p className="text-[13px] font-medium text-white leading-tight truncate">
              {cell.location || 'Cell Detail'}
            </p>
            <p className="text-[10px] text-slate-600 font-mono mt-0.5 truncate">
              {cell.h3_cell}
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-slate-600 hover:text-slate-400 transition-colors shrink-0 mt-0.5"
          >
            <X size={13} strokeWidth={1.5} />
          </button>
        </div>

        {/* Score */}
        <div className="px-4 pb-3 flex items-baseline gap-3">
          <span className="text-4xl font-semibold tabular-nums" style={{ color }}>
            {cell.score}
          </span>
          <div>
            <p className="text-[11px] font-medium" style={{ color }}>{label}</p>
            <VelocityRow v={cell.velocity_24h} />
          </div>
        </div>

        {/* Meta grid */}
        <div className="border-t border-slate-800 grid grid-cols-2 divide-x divide-slate-800">
          <div className="px-4 py-2.5">
            <p className="text-[9px] text-slate-600 uppercase tracking-widest mb-0.5">Hazard</p>
            <p className="text-[11px] text-slate-300 capitalize">{cell.hazard_type}</p>
          </div>
          <div className="px-4 py-2.5">
            <p className="text-[9px] text-slate-600 uppercase tracking-widest mb-0.5">Date</p>
            <p className="text-[11px] text-slate-300 tabular-nums">{cell.scored_at?.slice(0, 10) ?? '—'}</p>
          </div>
        </div>
      </div>
    </div>
  )
}
