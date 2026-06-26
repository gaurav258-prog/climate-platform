import { Waves, Flame, Thermometer, Radio, Map, FileText, Zap, Shield } from 'lucide-react'
import { HAZARDS } from '../mockData'

const HAZARD_ICONS = {
  flood:    <Waves size={13} strokeWidth={1.5} />,
  wildfire: <Flame size={13} strokeWidth={1.5} />,
  heat:     <Thermometer size={13} strokeWidth={1.5} />,
}

const VIEWS = [
  { id: 'map',        label: 'Risk Map',   icon: <Map      size={12} strokeWidth={1.5} /> },
  { id: 'operations', label: 'Operations', icon: <Shield   size={12} strokeWidth={1.5} /> },
  { id: 'parametric', label: 'Parametric', icon: <Zap      size={12} strokeWidth={1.5} /> },
  { id: 'compliance', label: 'Compliance', icon: <FileText size={12} strokeWidth={1.5} /> },
]

export default function Navbar({ activeHazard, onHazardChange, liveCount, activeView, onViewChange }) {
  return (
    <header className="flex items-center justify-between px-5 h-11 bg-slate-950 border-b border-slate-800 shrink-0 z-10">

      {/* Brand + view tabs */}
      <div className="flex items-center gap-5">
        <div className="flex items-center gap-3">
          <span className="text-white text-sm font-medium tracking-tight">Climate Intelligence</span>
          <div className="flex items-center gap-1.5">
            <Radio size={10} strokeWidth={1.5} className="text-emerald-500" />
            <span className="text-[10px] text-slate-500 uppercase tracking-widest">Live</span>
          </div>
        </div>

        <span className="w-px h-4 bg-slate-800" />

        {/* View switcher */}
        <div className="flex items-center gap-0.5">
          {VIEWS.map(v => (
            <button
              key={v.id}
              onClick={() => onViewChange(v.id)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-[11px] font-medium transition-all ${
                activeView === v.id
                  ? 'bg-slate-800 text-white'
                  : 'text-slate-500 hover:text-slate-300'
              }`}
            >
              {v.icon}
              {v.label}
            </button>
          ))}
        </div>
      </div>

      {/* Hazard tabs — only shown on map view */}
      {activeView === 'map' && (
        <div className="flex items-center gap-0.5">
          {HAZARDS.map(h => {
            const active = activeHazard === h.id
            return (
              <button
                key={h.id}
                onClick={() => onHazardChange(h.id)}
                className={`flex items-center gap-2 px-3.5 py-1.5 rounded text-xs font-medium transition-all ${
                  active ? 'bg-slate-800 text-white' : 'text-slate-500 hover:text-slate-300 hover:bg-slate-900'
                }`}
              >
                <span style={{ color: active ? h.color : undefined }}>{HAZARD_ICONS[h.id]}</span>
                <span className="tracking-wide">{h.label}</span>
              </button>
            )
          })}
        </div>
      )}

      {/* Meta */}
      <div className="flex items-center gap-5 text-[11px] text-slate-500">
        {liveCount > 0 && (
          <span>
            <span className="text-slate-300 tabular-nums">{liveCount.toLocaleString()}</span>
            <span className="ml-1">cells</span>
          </span>
        )}
        <span className="text-slate-700">Rhine Basin · Jul 2021</span>
      </div>
    </header>
  )
}
