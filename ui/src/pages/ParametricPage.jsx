import { useState, useMemo } from 'react'
import { latLngToCell } from 'h3-js'
import { CheckCircle, Circle, AlertTriangle, Zap, Clock } from 'lucide-react'
import { generateMockScores, getDates } from '../mockData'

// Parametric policies — each tied to a lat/lng location and a trigger threshold
const POLICIES = [
  { id: 'P-001', name: 'Rhine Flood Shield',     lat: 50.529, lng: 6.993, hazard: 'flood',    threshold: 60, payout_eur: 2_500_000, insured: 'Kreis Ahrweiler' },
  { id: 'P-002', name: 'Cologne Logistics Cover', lat: 50.938, lng: 6.960, hazard: 'flood',    threshold: 55, payout_eur: 1_800_000, insured: 'DHL Logistics GmbH' },
  { id: 'P-003', name: 'Bonn Urban Flood',        lat: 50.733, lng: 7.100, hazard: 'flood',    threshold: 50, payout_eur: 4_200_000, insured: 'Stadt Bonn' },
  { id: 'P-004', name: 'Rhine Valley Parametric', lat: 50.937, lng: 6.961, hazard: 'flood',    threshold: 65, payout_eur: 6_000_000, insured: 'Munich Re Treaty 4A' },
  { id: 'P-005', name: 'Koblenz Industrial',      lat: 50.356, lng: 7.591, hazard: 'flood',    threshold: 58, payout_eur: 900_000,   insured: 'Koblenz Hafen AG' },
]

function formatEur(n) {
  if (n >= 1_000_000) return `€${(n / 1_000_000).toFixed(1)}M`
  return `€${(n / 1_000).toFixed(0)}K`
}

const TRIGGER_STYLES = {
  triggered: {
    icon:    <Zap size={12} strokeWidth={1.5} />,
    color:   'text-red-400',
    bg:      'bg-red-950/40 border-red-900/60',
    dot:     'bg-red-500',
    label:   'Triggered',
  },
  monitoring: {
    icon:    <Clock size={12} strokeWidth={1.5} />,
    color:   'text-amber-400',
    bg:      'bg-amber-950/30 border-amber-900/40',
    dot:     'bg-amber-400',
    label:   'Monitoring',
  },
  clear: {
    icon:    <CheckCircle size={12} strokeWidth={1.5} />,
    color:   'text-emerald-500',
    bg:      'bg-slate-900 border-slate-800',
    dot:     'bg-emerald-500',
    label:   'Clear',
  },
}

function triggerState(score, threshold) {
  if (score == null) return 'clear'
  if (score >= threshold) return 'triggered'
  if (score >= threshold * 0.85) return 'monitoring'
  return 'clear'
}

function usePolicyScores(dayIndex) {
  return useMemo(() => {
    const scores = generateMockScores('flood', dayIndex)
    const scoreMap = new Map(scores.map(s => [s.h3_cell, s]))
    return POLICIES.map(p => {
      const cell = latLngToCell(p.lat, p.lng, 8)
      const s = scoreMap.get(cell)
      const state = triggerState(s?.score ?? null, p.threshold)
      return { ...p, h3_cell: cell, score: s?.score ?? null, velocity: s?.velocity_24h ?? null, state }
    })
  }, [dayIndex])
}

function ThresholdBar({ score, threshold }) {
  if (score == null) return null
  const pct = Math.min(100, Math.round((score / 100) * 100))
  const tPct = Math.min(100, Math.round((threshold / 100) * 100))
  const color = score >= threshold ? '#ef4444' : score >= threshold * 0.85 ? '#f59e0b' : '#10b981'
  return (
    <div className="relative h-1 bg-slate-800 rounded-full overflow-visible mt-1">
      <div className="absolute h-full rounded-full transition-all duration-500" style={{ width: `${pct}%`, backgroundColor: color }} />
      <div className="absolute top-1/2 -translate-y-1/2 w-px h-3 bg-slate-500" style={{ left: `${tPct}%` }} />
    </div>
  )
}

export default function ParametricPage({ dayIndex, onDayChange }) {
  const policies = usePolicyScores(dayIndex)
  const dates = getDates('flood')

  const triggered  = policies.filter(p => p.state === 'triggered')
  const monitoring = policies.filter(p => p.state === 'monitoring')
  const totalPayout = triggered.reduce((s, p) => s + p.payout_eur, 0)

  return (
    <div className="flex flex-1 overflow-hidden bg-slate-950">
      <div className="flex-1 flex flex-col overflow-hidden">

        {/* Summary strip */}
        <div className="flex items-stretch gap-0 border-b border-slate-800 divide-x divide-slate-800">
          {[
            { label: 'Policies Active',   value: POLICIES.length,  accent: null },
            { label: 'Triggered',         value: triggered.length,  accent: triggered.length  ? 'text-red-400'   : null },
            { label: 'Monitoring',        value: monitoring.length, accent: monitoring.length ? 'text-amber-400' : null },
            { label: 'Payout Exposed',    value: formatEur(totalPayout), accent: totalPayout ? 'text-red-400' : null },
          ].map(s => (
            <div key={s.label} className="flex-1 px-5 py-3">
              <p className="text-[10px] text-slate-500 uppercase tracking-widest mb-0.5">{s.label}</p>
              <p className={`text-xl font-semibold tabular-nums ${s.accent ?? 'text-white'}`}>{s.value}</p>
            </div>
          ))}
        </div>

        {/* Policy cards */}
        <div className="flex-1 overflow-y-auto p-4 grid grid-cols-1 gap-3">
          {policies.map(p => {
            const st = TRIGGER_STYLES[p.state]
            return (
              <div key={p.id} className={`border rounded p-4 transition-all ${st.bg}`}>
                <div className="flex items-start justify-between mb-3">
                  <div>
                    <div className="flex items-center gap-2 mb-0.5">
                      <span className={`text-[11px] font-medium ${st.color}`}>{p.id}</span>
                      <span className="text-[10px] text-slate-600">{p.hazard}</span>
                    </div>
                    <p className="text-[13px] font-medium text-slate-200">{p.name}</p>
                    <p className="text-[11px] text-slate-500 mt-0.5">{p.insured}</p>
                  </div>
                  <div className={`flex items-center gap-1.5 text-[11px] font-medium ${st.color}`}>
                    {st.icon}
                    <span>{st.label}</span>
                  </div>
                </div>

                {/* Score vs threshold */}
                <div className="grid grid-cols-3 gap-4 mb-3">
                  <div>
                    <p className="text-[9px] text-slate-600 uppercase tracking-widest mb-0.5">Score</p>
                    <p className={`text-lg font-semibold tabular-nums ${st.color}`}>
                      {p.score ?? '—'}
                    </p>
                  </div>
                  <div>
                    <p className="text-[9px] text-slate-600 uppercase tracking-widest mb-0.5">Trigger</p>
                    <p className="text-lg font-semibold tabular-nums text-slate-400">{p.threshold}</p>
                  </div>
                  <div>
                    <p className="text-[9px] text-slate-600 uppercase tracking-widest mb-0.5">Payout</p>
                    <p className="text-lg font-semibold tabular-nums text-slate-200">{formatEur(p.payout_eur)}</p>
                  </div>
                </div>

                <ThresholdBar score={p.score} threshold={p.threshold} />

                <div className="flex items-center justify-between mt-2">
                  <p className="text-[10px] text-slate-600">
                    Threshold at {p.threshold} · {dates[dayIndex]}
                  </p>
                  {p.velocity != null && Math.abs(p.velocity) > 0.5 && (
                    <p className={`text-[10px] ${p.velocity > 0 ? 'text-red-400' : 'text-emerald-400'}`}>
                      {p.velocity > 0 ? '↑' : '↓'} {Math.abs(p.velocity).toFixed(1)} pts/24h
                    </p>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* Right — event log */}
      <div className="w-64 shrink-0 border-l border-slate-800 flex flex-col">
        <div className="px-4 pt-4 pb-3 border-b border-slate-800">
          <p className="text-[10px] text-slate-500 uppercase tracking-widest">Event Log</p>
        </div>
        <div className="flex-1 overflow-y-auto divide-y divide-slate-800/60">
          {dates.map((d, i) => {
            const dayScores = generateMockScores('flood', i)
            const scoreMap  = new Map(dayScores.map(s => [s.h3_cell, s]))
            const dayTriggered = POLICIES.filter(p => {
              const cell = latLngToCell(p.lat, p.lng, 8)
              const sc = scoreMap.get(cell)?.score ?? 0
              return sc >= p.threshold
            })
            const isActive = i === dayIndex
            return (
              <button
                key={d}
                onClick={() => onDayChange(i)}
                className={`w-full text-left px-4 py-2.5 transition-colors ${isActive ? 'bg-slate-900' : 'hover:bg-slate-900/50'}`}
              >
                <div className="flex items-center justify-between">
                  <span className={`text-[11px] tabular-nums ${isActive ? 'text-white font-medium' : 'text-slate-400'}`}>{d}</span>
                  {dayTriggered.length > 0 ? (
                    <span className="flex items-center gap-1 text-[10px] text-red-400">
                      <Zap size={9} strokeWidth={1.5} />
                      {dayTriggered.length}
                    </span>
                  ) : (
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-600" />
                  )}
                </div>
              </button>
            )
          })}
        </div>
      </div>
    </div>
  )
}
