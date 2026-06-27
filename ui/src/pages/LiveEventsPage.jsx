import { useState, useEffect, useMemo, useCallback } from 'react'
import { cellToLatLng } from 'h3-js'
import { Activity, MapPin, Radio } from 'lucide-react'
import RiskMap from '../components/RiskMap'
import ScoreLegend from '../components/ScoreLegend'
import { fetchGeoScores, fetchSeismicEvents, fetchVerification } from '../api/client'

const HAZARDS = [
  { id: 'seismic', label: 'Seismic', zoom: 6.5 },
  { id: 'flood', label: 'Flood', zoom: 7.5 },
  { id: 'wildfire', label: 'Wildfire', zoom: 4.5 },
]

const bucketColor = b => ({ L: '#10b981', M: '#f59e0b', H: '#f97316', VH: '#ef4444' }[b] || '#64748b')

function centroidView(cells, zoom) {
  if (!cells?.length) return null
  let lat = 0, lon = 0
  for (const c of cells) { const [la, lo] = cellToLatLng(c.h3_cell); lat += la; lon += lo }
  return { latitude: lat / cells.length, longitude: lon / cells.length, zoom, pitch: 35, bearing: 0 }
}

export default function LiveEventsPage() {
  const [hazard, setHazard] = useState('seismic')
  const [geo, setGeo] = useState(null)
  const [events, setEvents] = useState([])
  const [verif, setVerif] = useState(null)
  const [selected, setSelected] = useState(null)

  useEffect(() => {
    let live = true
    setGeo(null)
    fetchGeoScores(hazard).then(d => live && setGeo(d)).catch(() => live && setGeo({ cells: [] }))
    return () => { live = false }
  }, [hazard])

  useEffect(() => {
    fetchSeismicEvents(14, 4.5).then(d => setEvents(d.events || [])).catch(() => {})
    fetchVerification('Venezuela M7.5').then(d => setVerif(d.points?.[d.points.length - 1] || null)).catch(() => {})
  }, [])

  const view = useMemo(() => geo && centroidView(geo.cells, HAZARDS.find(h => h.id === hazard)?.zoom || 6), [geo, hazard])
  const stats = useMemo(() => {
    const cells = geo?.cells || []
    const b = { L: 0, M: 0, H: 0, VH: 0 }
    cells.forEach(c => { b[c.bucket] = (b[c.bucket] || 0) + 1 })
    return { n: cells.length, b, max: cells.reduce((m, c) => Math.max(m, c.score), 0) }
  }, [geo])

  const onCell = useCallback(c => setSelected(c), [])

  return (
    <div className="flex h-full bg-slate-950 text-slate-100">
      {/* Map */}
      <div className="relative flex-1">
        {/* hazard tabs */}
        <div className="absolute top-3 left-3 z-10 flex gap-1 rounded-lg bg-slate-900/90 p-1 backdrop-blur border border-slate-700">
          {HAZARDS.map(h => (
            <button key={h.id} onClick={() => { setHazard(h.id); setSelected(null) }}
              className={`px-3 py-1.5 text-xs font-medium rounded-md transition ${
                hazard === h.id ? 'bg-slate-100 text-slate-900' : 'text-slate-300 hover:bg-slate-800'}`}>
              {h.label}
            </button>
          ))}
        </div>
        {/* meta badge */}
        <div className="absolute top-3 right-3 z-10 rounded-lg bg-slate-900/90 px-3 py-2 text-[11px] backdrop-blur border border-slate-700">
          {geo ? (
            <>
              <div className="flex items-center gap-1.5 text-emerald-400"><Radio size={12} /> live canonical_scores</div>
              <div className="mt-1 text-slate-400">{stats.n.toLocaleString()} cells · H3 res {geo.resolution} · peak {Math.round(stats.max)}</div>
            </>
          ) : <span className="text-slate-400">loading…</span>}
        </div>
        {/* legend */}
        <div className="absolute bottom-3 left-3 z-10"><ScoreLegend /></div>
        {/* cell detail */}
        {selected && (
          <div className="absolute bottom-3 right-3 z-10 rounded-lg bg-slate-900/95 px-3 py-2 text-[11px] backdrop-blur border border-slate-700">
            <div className="font-mono text-slate-400">{selected.h3_cell}</div>
            <div className="mt-1 flex items-center gap-2">
              <span className="font-semibold" style={{ color: bucketColor(selected.bucket) }}>{Math.round(selected.score)}</span>
              <span className="text-slate-400">/ 100 · {selected.bucket}</span>
            </div>
          </div>
        )}
        {geo?.cells?.length
          ? <RiskMap scores={geo.cells} onCellClick={onCell} hazard={hazard} viewOverride={view} />
          : <div className="flex h-full items-center justify-center text-slate-500">loading map…</div>}
      </div>

      {/* Right rail */}
      <aside className="w-80 shrink-0 overflow-y-auto border-l border-slate-800 p-4 space-y-4">
        {/* Verification card */}
        <section className="rounded-xl border border-slate-800 bg-slate-900/40 p-4">
          <h3 className="flex items-center gap-2 text-sm font-semibold"><Activity size={15} className="text-amber-400" /> Forecast vs reality</h3>
          <p className="mt-0.5 text-[11px] text-slate-400">Venezuela M7.5 aftershocks — Omori-Utsu model checked daily</p>
          {verif ? <VerificationPanel v={verif} /> : <p className="mt-3 text-xs text-slate-500">no verification data yet</p>}
        </section>

        {/* Live seismic feed */}
        <section className="rounded-xl border border-slate-800 bg-slate-900/40 p-4">
          <h3 className="flex items-center gap-2 text-sm font-semibold"><Radio size={15} className="text-emerald-400" /> Live seismic feed</h3>
          <p className="mt-0.5 text-[11px] text-slate-400">USGS global · M≥4.5 · last 14 days</p>
          <ul className="mt-3 space-y-1.5">
            {events.slice(0, 12).map(e => (
              <li key={e.event_id} className="flex items-center gap-2 text-[11px]">
                <span className="w-9 shrink-0 text-center font-semibold rounded px-1 py-0.5"
                  style={{ background: e.magnitude >= 6 ? '#7f1d1d' : e.magnitude >= 5 ? '#9a3412' : '#334155',
                           color: e.magnitude >= 5 ? '#fecaca' : '#cbd5e1' }}>
                  {e.magnitude.toFixed(1)}
                </span>
                <span className="flex-1 truncate text-slate-300">{e.region_name}</span>
                <span className="shrink-0 text-slate-500">{e.origin_time?.slice(5, 10)}</span>
              </li>
            ))}
            {!events.length && <li className="text-xs text-slate-500">no recent events</li>}
          </ul>
        </section>
      </aside>
    </div>
  )
}

function VerificationPanel({ v }) {
  // band: 0 .. predicted + 3σ, shaded ±2σ, predicted line, observed marker
  const hi = Math.max(v.predicted_count + 3 * v.sigma, v.observed_count + 1, 1)
  const pct = x => `${Math.min(100, Math.max(0, (x / hi) * 100))}%`
  const lo2 = Math.max(0, v.predicted_count - 2 * v.sigma)
  const hi2 = v.predicted_count + 2 * v.sigma
  const outOfBand = !v.within_2sigma
  return (
    <div className="mt-3 space-y-3">
      <div className="flex items-end gap-2">
        <span className="text-3xl font-bold tabular-nums" style={{ color: outOfBand ? '#ef4444' : '#10b981' }}>
          {v.z_score > 0 ? '+' : ''}{v.z_score.toFixed(1)}σ
        </span>
        <span className={`mb-1 rounded px-1.5 py-0.5 text-[10px] font-semibold ${outOfBand ? 'bg-red-950 text-red-300' : 'bg-emerald-950 text-emerald-300'}`}>
          {outOfBand ? 'OUT OF BAND' : 'within band'}
        </span>
      </div>
      {/* band track */}
      <div className="relative h-6 rounded bg-slate-800">
        <div className="absolute top-0 bottom-0 rounded bg-emerald-500/25"
          style={{ left: pct(lo2), width: `calc(${pct(hi2)} - ${pct(lo2)})` }} />
        <div className="absolute top-0 bottom-0 w-px bg-emerald-300" style={{ left: pct(v.predicted_count) }} />
        <div className="absolute -top-0.5 h-7 w-1 rounded bg-red-500" style={{ left: pct(v.observed_count) }} title="observed" />
      </div>
      <div className="grid grid-cols-2 gap-2 text-[11px]">
        <Stat label="Predicted M≥4.5" value={`${v.predicted_count.toFixed(0)} ± ${v.sigma.toFixed(0)}`} />
        <Stat label="Observed" value={v.observed_count} accent={outOfBand ? '#ef4444' : '#10b981'} />
        <Stat label="P(M≥5) forecast" value={(v.m5_forecast * 100).toFixed(0) + '%'} />
        <Stat label="M≥5 occurred" value={v.m5_occurred ? 'yes' : `no (max M${v.largest_obs_mag?.toFixed(1)})`}
          accent={v.m5_occurred ? '#ef4444' : '#94a3b8'} />
      </div>
      <p className="text-[10px] leading-snug text-slate-500">
        Day {v.elapsed_days?.toFixed(1)}. Generic California (Reasenberg-Jones) parameters over-predict this
        sequence; the daily series accrues until we recalibrate decay to the observed aftershocks.
      </p>
    </div>
  )
}

const Stat = ({ label, value, accent }) => (
  <div className="rounded-lg bg-slate-800/40 px-2 py-1.5">
    <div className="text-[9px] uppercase tracking-wide text-slate-500">{label}</div>
    <div className="font-semibold tabular-nums" style={{ color: accent || '#e2e8f0' }}>{value}</div>
  </div>
)
