import { useMemo } from 'react'
import { latLngToCell } from 'h3-js'
import { generateMockScores, getDates } from '../mockData'
import { REGIONS, ACTION_TEMPLATES, PRIORITY_ORDER } from '../mockRegions'

const RISK_TEXT = { LOW: 'text-emerald-500', MEDIUM: 'text-amber-400', HIGH: 'text-orange-500', VERY_HIGH: 'text-red-500' }
const RISK_DOT  = { LOW: 'bg-emerald-500',   MEDIUM: 'bg-amber-400',   HIGH: 'bg-orange-500',   VERY_HIGH: 'bg-red-500' }
const RISK_LABEL= { LOW: 'Low',              MEDIUM: 'Medium',          HIGH: 'High',            VERY_HIGH: 'Very High' }

const PRIORITY_RING = {
  URGENT: 'w-5 h-5 rounded-full bg-red-950 text-red-400 text-[10px] font-bold flex items-center justify-center shrink-0',
  HIGH:   'w-5 h-5 rounded-full bg-orange-950 text-orange-400 text-[10px] font-bold flex items-center justify-center shrink-0',
  MEDIUM: 'w-5 h-5 rounded-full bg-slate-800 text-slate-400 text-[10px] font-bold flex items-center justify-center shrink-0',
}

const BTN_DISPATCH = {
  URGENT: 'text-[10px] px-2.5 py-1 rounded bg-red-950 border border-red-900/60 text-red-400 hover:bg-red-900/60 transition-colors whitespace-nowrap shrink-0',
  HIGH:   'text-[10px] px-2.5 py-1 rounded bg-orange-950/60 border border-orange-900/50 text-orange-400 hover:bg-orange-900/40 transition-colors whitespace-nowrap shrink-0',
  MEDIUM: 'text-[10px] px-2.5 py-1 rounded bg-slate-800 border border-slate-700 text-slate-400 hover:bg-slate-700 transition-colors whitespace-nowrap shrink-0',
}

export default function DashboardPage({ hazard, dayIndex, onViewChange, onHazardChange }) {
  const dates  = getDates(hazard)
  const date   = dates[dayIndex]
  const scores = useMemo(() => generateMockScores(hazard, dayIndex), [hazard, dayIndex])
  const scoreMap = useMemo(() => new Map(scores.map(s => [s.h3_cell, s])), [scores])

  const regions = useMemo(() => {
    return REGIONS.map(r => {
      const cell = latLngToCell(r.lat, r.lng, 8)
      const s = scoreMap.get(cell)
      return { ...r, score: s?.score ?? null, risk_level: s?.risk_level ?? null }
    }).sort((a, b) => (b.score ?? 0) - (a.score ?? 0))
  }, [scoreMap])

  const atRisk = regions.filter(r => r.risk_level === 'HIGH' || r.risk_level === 'VERY_HIGH')
  const popAtRisk = atRisk.reduce((s, r) => s + r.population, 0)
  const peakScore = scores.length ? Math.max(...scores.map(s => s.score)) : 0

  const actions = useMemo(() =>
    (ACTION_TEMPLATES[hazard] ?? [])
      .sort((a, b) => PRIORITY_ORDER[a.priority] - PRIORITY_ORDER[b.priority])
      .slice(0, 4),
    [hazard]
  )
  const urgentCount = actions.filter(a => a.priority === 'URGENT').length

  return (
    <div className="flex-1 overflow-y-auto bg-slate-950 p-6">

      {/* Greeting */}
      <div className="mb-6">
        <h1 className="text-[18px] font-semibold text-white tracking-tight">
          Rhine Basin &nbsp;—&nbsp;{' '}
          {urgentCount > 0
            ? <span className="text-red-400">{urgentCount} urgent alert{urgentCount > 1 ? 's' : ''} active.</span>
            : <span className="text-emerald-400">All clear.</span>
          }
        </h1>
        <p className="text-[11px] text-slate-600 mt-1 capitalize">
          {hazard} event · {date} · {scores.length.toLocaleString()} cells scored · data current
        </p>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-4 gap-3 mb-6">
        {[
          {
            label: 'Peak Risk Score',
            value: peakScore,
            valueClass: peakScore >= 75 ? 'text-red-400' : peakScore >= 50 ? 'text-orange-500' : 'text-amber-400',
            sub: 'Highest cell score',
            trend: peakScore >= 75 ? { dir: 'up', text: 'Very High zone' } : null,
          },
          {
            label: 'Population at Risk',
            value: popAtRisk > 0 ? (popAtRisk / 1000).toFixed(0) + 'K' : '—',
            valueClass: popAtRisk > 500_000 ? 'text-orange-500' : 'text-amber-400',
            sub: `${atRisk.length} region${atRisk.length !== 1 ? 's' : ''} High+`,
            trend: popAtRisk > 0 ? { dir: 'up', text: 'High risk zones' } : null,
          },
          {
            label: 'Cells Scored',
            value: scores.length.toLocaleString(),
            valueClass: 'text-white',
            sub: 'H3 resolution 8',
            trend: null,
          },
          {
            label: 'Urgent Actions',
            value: urgentCount,
            valueClass: urgentCount > 0 ? 'text-red-400' : 'text-white',
            sub: `${actions.length} total recommended`,
            trend: urgentCount > 0 ? { dir: 'up', text: 'Requires dispatch' } : null,
          },
        ].map(c => (
          <div key={c.label} className="bg-slate-900 border border-slate-800 rounded-lg px-4 py-3">
            <p className="text-[9px] text-slate-600 uppercase tracking-[0.12em] mb-1.5">{c.label}</p>
            <p className={`text-2xl font-semibold tabular-nums ${c.valueClass}`}>{c.value}</p>
            <p className="text-[10px] text-slate-600 mt-1">{c.sub}</p>
            {c.trend && (
              <p className={`text-[10px] mt-0.5 ${c.trend.dir === 'up' ? 'text-red-400/70' : 'text-emerald-400/70'}`}>
                {c.trend.dir === 'up' ? '↑' : '↓'} {c.trend.text}
              </p>
            )}
          </div>
        ))}
      </div>

      {/* Two-column: regions + actions */}
      <div className="grid grid-cols-2 gap-4">

        {/* Top regions */}
        <div className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden">
          <div className="flex items-center justify-between px-4 py-2.5 border-b border-slate-800">
            <p className="text-[9px] text-slate-600 uppercase tracking-[0.12em]">Top Regions</p>
            <button
              onClick={() => onViewChange('map')}
              className="text-[10px] text-slate-500 hover:text-slate-300 transition-colors"
            >
              View map →
            </button>
          </div>
          <div className="divide-y divide-slate-800/60">
            {regions.slice(0, 6).map(r => (
              <div key={r.id} className="flex items-center justify-between px-4 py-2.5">
                <div>
                  <p className="text-[12px] font-medium text-slate-200">{r.name}</p>
                  <p className="text-[10px] text-slate-600 mt-0.5">{(r.population / 1000).toFixed(0)}K pop.</p>
                </div>
                {r.risk_level ? (
                  <div className="flex items-center gap-2.5">
                    <span className={`text-[14px] font-semibold tabular-nums ${RISK_TEXT[r.risk_level]}`}>
                      {r.score}
                    </span>
                    <div className="flex items-center gap-1.5">
                      <span className={`w-1.5 h-1.5 rounded-full ${RISK_DOT[r.risk_level]}`} />
                      <span className={`text-[10px] ${RISK_TEXT[r.risk_level]}`}>{RISK_LABEL[r.risk_level]}</span>
                    </div>
                  </div>
                ) : <span className="text-[11px] text-slate-700">—</span>}
              </div>
            ))}
          </div>
        </div>

        {/* Top actions */}
        <div className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden">
          <div className="flex items-center justify-between px-4 py-2.5 border-b border-slate-800">
            <p className="text-[9px] text-slate-600 uppercase tracking-[0.12em]">Recommended Actions</p>
            <button
              onClick={() => onViewChange('operations')}
              className="text-[10px] text-slate-500 hover:text-slate-300 transition-colors"
            >
              Open Operations →
            </button>
          </div>
          <div className="divide-y divide-slate-800/60">
            {actions.map((a, i) => (
              <div key={a.id} className="flex items-start gap-3 px-4 py-3">
                <div className={PRIORITY_RING[a.priority]}>{i + 1}</div>
                <div className="flex-1 min-w-0">
                  <p className="text-[12px] font-medium text-slate-200 leading-snug">{a.action}</p>
                  <p className="text-[10px] text-slate-600 mt-0.5">{a.region} · {a.unit}</p>
                </div>
                <button className={BTN_DISPATCH[a.priority]}>Dispatch →</button>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
