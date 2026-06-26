import { useState, useMemo } from 'react'
import { latLngToCell } from 'h3-js'
import { Shield, CheckCircle, Clock, Radio, Users, Zap, AlertTriangle, ChevronRight } from 'lucide-react'
import { REGIONS, ACTION_TEMPLATES, PRIORITY_ORDER } from '../mockRegions'
import { generateMockScores, getDates } from '../mockData'

const PRIORITY_STYLES = {
  URGENT: { color: 'text-red-400',    bg: 'bg-red-950/50 border-red-900/60',   dot: 'bg-red-500' },
  HIGH:   { color: 'text-orange-400', bg: 'bg-orange-950/40 border-orange-900/50', dot: 'bg-orange-500' },
  MEDIUM: { color: 'text-amber-400',  bg: 'bg-slate-900 border-slate-800',     dot: 'bg-amber-400' },
}

const STATUS_STYLES = {
  pending:    { icon: <Clock       size={10} strokeWidth={1.5} />, color: 'text-slate-500',   label: 'Pending' },
  dispatched: { icon: <Radio       size={10} strokeWidth={1.5} />, color: 'text-amber-400',   label: 'Dispatched' },
  complete:   { icon: <CheckCircle size={10} strokeWidth={1.5} />, color: 'text-emerald-500', label: 'Complete' },
}

const CATEGORY_ICONS = {
  Resource:   <Shield     size={11} strokeWidth={1.5} />,
  Shelter:    <Users      size={11} strokeWidth={1.5} />,
  Alert:      <Radio      size={11} strokeWidth={1.5} />,
  Medical:    <Zap        size={11} strokeWidth={1.5} />,
  Transport:  <AlertTriangle size={11} strokeWidth={1.5} />,
  Evacuation: <ChevronRight  size={11} strokeWidth={1.5} />,
  Regulation: <Shield     size={11} strokeWidth={1.5} />,
  Support:    <Users      size={11} strokeWidth={1.5} />,
}

const RISK_TEXT  = { LOW: 'text-emerald-500', MEDIUM: 'text-amber-400', HIGH: 'text-orange-500', VERY_HIGH: 'text-red-500' }
const RISK_DOT   = { LOW: 'bg-emerald-500',   MEDIUM: 'bg-amber-400',   HIGH: 'bg-orange-500',   VERY_HIGH: 'bg-red-500' }
const RISK_LABEL = { LOW: 'Low',              MEDIUM: 'Medium',          HIGH: 'High',            VERY_HIGH: 'Very High' }

function useRegionScores(hazard, dayIndex) {
  return useMemo(() => {
    const scores = generateMockScores(hazard, dayIndex)
    const scoreMap = new Map(scores.map(s => [s.h3_cell, s]))
    return REGIONS.map(r => {
      const cell = latLngToCell(r.lat, r.lng, 8)
      const s = scoreMap.get(cell)
      return { ...r, score: s?.score ?? null, risk_level: s?.risk_level ?? null }
    }).sort((a, b) => (b.score ?? 0) - (a.score ?? 0))
  }, [hazard, dayIndex])
}

export default function OperationsPage({ hazard, dayIndex }) {
  const regions = useRegionScores(hazard, dayIndex)
  const dates   = getDates(hazard)
  const date    = dates[dayIndex]

  const actions = useMemo(() =>
    (ACTION_TEMPLATES[hazard] ?? [])
      .sort((a, b) => PRIORITY_ORDER[a.priority] - PRIORITY_ORDER[b.priority])
      .map(a => ({ ...a, status: 'pending' })),
    [hazard]
  )

  const [statuses, setStatuses] = useState({})
  const [log, setLog] = useState([])

  function dispatch(actionId) {
    setStatuses(s => ({ ...s, [actionId]: 'dispatched' }))
    const action = actions.find(a => a.id === actionId)
    setLog(prev => [{
      id:       actionId,
      text:     action.action,
      region:   action.region,
      time:     new Date().toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' }),
      priority: action.priority,
    }, ...prev])
  }

  function complete(actionId) {
    setStatuses(s => ({ ...s, [actionId]: 'complete' }))
  }

  // Summary stats
  const atRisk = regions.filter(r => r.risk_level === 'HIGH' || r.risk_level === 'VERY_HIGH')
  const popAtRisk = atRisk.reduce((s, r) => s + r.population, 0)
  const dispatched = Object.values(statuses).filter(v => v === 'dispatched').length
  const urgent = actions.filter(a => a.priority === 'URGENT').length

  return (
    <div className="flex flex-1 overflow-hidden bg-slate-950">
      <div className="flex flex-1 flex-col overflow-hidden">

        {/* Summary strip */}
        <div className="flex items-stretch divide-x divide-slate-800 border-b border-slate-800 shrink-0">
          {[
            { label: 'Regions Monitored',  value: regions.length,                   accent: null },
            { label: 'Population at Risk', value: (popAtRisk / 1000).toFixed(0) + 'K', accent: popAtRisk > 0 ? 'text-orange-400' : null },
            { label: 'Urgent Actions',     value: urgent,                            accent: urgent > 0 ? 'text-red-400' : null },
            { label: 'Dispatched',         value: dispatched,                        accent: dispatched > 0 ? 'text-amber-400' : null },
          ].map(s => (
            <div key={s.label} className="flex-1 px-5 py-3">
              <p className="text-[10px] text-slate-500 uppercase tracking-widest mb-0.5">{s.label}</p>
              <p className={`text-xl font-semibold tabular-nums ${s.accent ?? 'text-white'}`}>{s.value}</p>
            </div>
          ))}
          <div className="px-5 py-3 flex items-center">
            <span className="text-[11px] text-slate-600 tabular-nums">{date}</span>
          </div>
        </div>

        {/* Main two-panel */}
        <div className="flex flex-1 overflow-hidden">

          {/* Left — region table */}
          <div className="w-64 shrink-0 border-r border-slate-800 flex flex-col overflow-hidden">
            <div className="px-4 pt-3 pb-2 border-b border-slate-800">
              <p className="text-[10px] text-slate-500 uppercase tracking-widest">Regions</p>
            </div>
            <div className="flex-1 overflow-y-auto divide-y divide-slate-800/60">
              {regions.map(r => (
                <div key={r.id} className="px-4 py-3 hover:bg-slate-900/50 transition-colors">
                  <div className="flex items-start justify-between mb-1">
                    <span className="text-[12px] font-medium text-slate-200">{r.name}</span>
                    {r.score != null && (
                      <span className={`text-[13px] font-semibold tabular-nums ${RISK_TEXT[r.risk_level]}`}>
                        {r.score}
                      </span>
                    )}
                  </div>
                  <div className="flex items-center justify-between">
                    {r.risk_level ? (
                      <div className="flex items-center gap-1.5">
                        <span className={`w-1.5 h-1.5 rounded-full ${RISK_DOT[r.risk_level]}`} />
                        <span className={`text-[10px] ${RISK_TEXT[r.risk_level]}`}>{RISK_LABEL[r.risk_level]}</span>
                      </div>
                    ) : <span />}
                    <span className="text-[10px] text-slate-600 tabular-nums">
                      {(r.population / 1000).toFixed(0)}K pop.
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Center — action board */}
          <div className="flex-1 flex flex-col overflow-hidden">
            <div className="px-4 pt-3 pb-2 border-b border-slate-800 flex items-center justify-between shrink-0">
              <p className="text-[10px] text-slate-500 uppercase tracking-widest">Action Board</p>
              <p className="text-[10px] text-slate-600">{actions.length} recommended actions</p>
            </div>
            <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-2">
              {actions.map(action => {
                const status = statuses[action.id] ?? 'pending'
                const p = PRIORITY_STYLES[action.priority]
                const st = STATUS_STYLES[status]
                return (
                  <div key={action.id} className={`border rounded px-4 py-3 transition-all ${p.bg} ${status === 'complete' ? 'opacity-50' : ''}`}>
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex items-start gap-3 min-w-0">
                        {/* Priority dot */}
                        <div className="flex items-center gap-1.5 mt-0.5 shrink-0">
                          <span className={`w-1.5 h-1.5 rounded-full ${p.dot}`} />
                          <span className={`text-[9px] font-semibold uppercase tracking-widest ${p.color}`}>
                            {action.priority}
                          </span>
                        </div>
                        <div className="min-w-0">
                          <p className="text-[12px] font-medium text-slate-200 leading-snug">{action.action}</p>
                          <div className="flex items-center gap-2 mt-1 flex-wrap">
                            <span className="text-[10px] text-slate-500">{action.region}</span>
                            <span className="text-slate-700 text-[10px]">·</span>
                            <span className="text-[10px] text-slate-600">{action.unit}</span>
                          </div>
                        </div>
                      </div>

                      {/* Actions */}
                      <div className="flex items-center gap-2 shrink-0">
                        <div className={`flex items-center gap-1 text-[10px] ${st.color}`}>
                          {st.icon}
                          <span>{st.label}</span>
                        </div>
                        {status === 'pending' && (
                          <button
                            onClick={() => dispatch(action.id)}
                            className="text-[10px] px-2 py-0.5 rounded bg-slate-700 hover:bg-slate-600 text-slate-200 transition-colors whitespace-nowrap"
                          >
                            Dispatch
                          </button>
                        )}
                        {status === 'dispatched' && (
                          <button
                            onClick={() => complete(action.id)}
                            className="text-[10px] px-2 py-0.5 rounded border border-emerald-800 hover:bg-emerald-950 text-emerald-500 transition-colors whitespace-nowrap"
                          >
                            Complete
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      </div>

      {/* Right — dispatch log */}
      <div className="w-60 shrink-0 border-l border-slate-800 flex flex-col">
        <div className="px-4 pt-3 pb-2 border-b border-slate-800">
          <p className="text-[10px] text-slate-500 uppercase tracking-widest">Dispatch Log</p>
        </div>
        <div className="flex-1 overflow-y-auto">
          {log.length === 0 ? (
            <div className="px-4 py-8 text-center text-[11px] text-slate-700">
              No actions dispatched
            </div>
          ) : (
            <div className="divide-y divide-slate-800/60">
              {log.map((entry, i) => (
                <div key={i} className="px-4 py-3">
                  <div className="flex items-center justify-between mb-1">
                    <span className={`text-[9px] font-semibold uppercase tracking-wide ${PRIORITY_STYLES[entry.priority].color}`}>
                      {entry.priority}
                    </span>
                    <span className="text-[10px] text-slate-600 tabular-nums">{entry.time}</span>
                  </div>
                  <p className="text-[11px] text-slate-300 leading-snug">{entry.text}</p>
                  <p className="text-[10px] text-slate-600 mt-0.5">{entry.region}</p>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
