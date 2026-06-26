import { useState } from 'react'
import { TrendingUp, TrendingDown, Minus } from 'lucide-react'

const RISK_DOT = {
  LOW:       'bg-emerald-500',
  MEDIUM:    'bg-amber-400',
  HIGH:      'bg-orange-500',
  VERY_HIGH: 'bg-red-500',
}

const RISK_TEXT = {
  LOW:       'text-emerald-500',
  MEDIUM:    'text-amber-400',
  HIGH:      'text-orange-500',
  VERY_HIGH: 'text-red-500',
}

function VelocityIcon({ v }) {
  if (!v || Math.abs(v) < 0.5) return <Minus size={11} strokeWidth={1.5} className="text-slate-600" />
  return v > 0
    ? <TrendingUp  size={11} strokeWidth={1.5} className="text-red-400" />
    : <TrendingDown size={11} strokeWidth={1.5} className="text-emerald-400" />
}

const FILTERS = ['All', 'VERY_HIGH', 'HIGH']

export default function AlertFeed({ alerts, selected, onSelect }) {
  const [filter, setFilter] = useState('All')

  const filtered = filter === 'All'
    ? alerts
    : alerts.filter(a => a.risk_level === filter)

  return (
    <aside className="w-68 shrink-0 flex flex-col border-l border-slate-800 bg-slate-950">

      {/* Header */}
      <div className="px-4 pt-4 pb-3 border-b border-slate-800">
        <div className="flex items-baseline justify-between mb-3">
          <span className="text-[11px] font-medium text-slate-300 uppercase tracking-widest">
            Alert Feed
          </span>
          <span className="text-[10px] text-slate-600 tabular-nums">{alerts.length} active</span>
        </div>
        <div className="flex gap-1">
          {FILTERS.map(f => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`text-[10px] px-2 py-0.5 rounded transition-all tracking-wide ${
                filter === f
                  ? 'bg-slate-800 text-slate-200'
                  : 'text-slate-600 hover:text-slate-400'
              }`}
            >
              {f === 'All' ? 'All' : f.replace('_', ' ')}
            </button>
          ))}
        </div>
      </div>

      {/* List */}
      <div className="flex-1 overflow-y-auto divide-y divide-slate-800/60">
        {filtered.length === 0 ? (
          <div className="px-4 py-8 text-center text-[11px] text-slate-600">No alerts</div>
        ) : (
          filtered.map((alert, i) => (
            <button
              key={alert.h3_cell ?? i}
              onClick={() => onSelect(alert)}
              className={`w-full text-left px-4 py-3 transition-colors group ${
                selected?.h3_cell === alert.h3_cell
                  ? 'bg-slate-900'
                  : 'hover:bg-slate-900/60'
              }`}
            >
              <div className="flex items-start justify-between gap-2 mb-1.5">
                <div className="flex items-center gap-2 min-w-0">
                  <span className={`w-1.5 h-1.5 rounded-full shrink-0 mt-px ${RISK_DOT[alert.risk_level]}`} />
                  <span className="text-[12px] text-slate-300 font-medium truncate leading-tight">
                    {alert.location || alert.h3_cell?.slice(0, 10) + '…'}
                  </span>
                </div>
                <span className={`text-[13px] font-semibold tabular-nums shrink-0 ${RISK_TEXT[alert.risk_level]}`}>
                  {alert.score}
                </span>
              </div>

              <div className="flex items-center justify-between pl-3.5">
                <span className={`text-[10px] uppercase tracking-wide ${RISK_TEXT[alert.risk_level]}`}>
                  {alert.risk_level?.replace('_', ' ')}
                </span>
                <div className="flex items-center gap-1 text-[10px] text-slate-500">
                  <VelocityIcon v={alert.velocity_24h} />
                  <span className="tabular-nums">{Math.abs(alert.velocity_24h ?? 0).toFixed(1)}</span>
                  <span className="text-slate-700">pts</span>
                </div>
              </div>
            </button>
          ))
        )}
      </div>

      {/* Footer */}
      <div className="px-4 py-2.5 border-t border-slate-800">
        <span className="text-[10px] text-slate-700 tracking-wide">
          Rhine Flood · 2021-07-14
        </span>
      </div>
    </aside>
  )
}
