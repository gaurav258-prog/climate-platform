import { useState, useEffect, useMemo, useCallback } from 'react'
import { cellToLatLng } from 'h3-js'
import { Activity, Radio } from 'lucide-react'
import RiskMap from '../components/RiskMap'
import { fetchGeoScores, fetchSeismicEvents, fetchVerification } from '../api/client'

const HAZARDS = [
  { id: 'seismic', label: 'Seismic', zoom: 8 },
  { id: 'flood', label: 'Flood', zoom: 8.5 },
  { id: 'wildfire', label: 'Wildfire', zoom: 4.5 },
]

const BANDS = [
  { label: 'Low', range: '0–25', color: '#34c759' },
  { label: 'Medium', range: '25–50', color: '#ff9500' },
  { label: 'High', range: '50–75', color: '#ff6a00' },
  { label: 'Very High', range: '75–100', color: '#ff3b30' },
]
const bucketColor = b => ({ L: '#34c759', M: '#ff9500', H: '#ff6a00', VH: '#ff3b30' }[b] || '#86868b')

function centroidView(cells, zoom) {
  if (!cells?.length) return null
  let lat = 0, lon = 0
  for (const c of cells) { const [la, lo] = cellToLatLng(c.h3_cell); lat += la; lon += lo }
  return { latitude: lat / cells.length, longitude: lon / cells.length, zoom, pitch: 20, bearing: 0 }
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
    return { n: cells.length, max: cells.reduce((m, c) => Math.max(m, c.score), 0) }
  }, [geo])
  const onCell = useCallback(c => setSelected(c), [])

  return (
    <div className="flex h-full bg-[#f5f5f7] text-[#1d1d1f]">
      {/* Map */}
      <div className="relative flex-1">
        {/* hazard segmented control */}
        <div className="absolute top-4 left-4 z-10 flex gap-0.5 rounded-full bg-white/85 p-1 shadow-sm backdrop-blur border border-black/[0.06]">
          {HAZARDS.map(h => (
            <button key={h.id} onClick={() => { setHazard(h.id); setSelected(null) }}
              className={`px-3.5 py-1.5 text-[13px] font-medium rounded-full transition ${
                hazard === h.id ? 'bg-[#1d1d1f] text-white' : 'text-gray-600 hover:text-[#1d1d1f]'}`}>
              {h.label}
            </button>
          ))}
        </div>
        {/* meta badge */}
        <div className="absolute top-4 right-4 z-10 rounded-2xl bg-white/85 px-3.5 py-2.5 text-[11px] shadow-sm backdrop-blur border border-black/[0.06]">
          {geo ? (
            <>
              <div className="flex items-center gap-1.5 font-medium text-emerald-600"><Radio size={12} /> live canonical_scores</div>
              <div className="mt-1 text-gray-500">{stats.n.toLocaleString()} cells · H3 res {geo.resolution} · peak {Math.round(stats.max)}</div>
            </>
          ) : <span className="text-gray-400">loading…</span>}
        </div>
        {/* legend */}
        <div className="absolute bottom-4 left-4 z-10 rounded-2xl bg-white/85 px-3.5 py-3 shadow-sm backdrop-blur border border-black/[0.06]">
          <p className="mb-2 text-[9px] uppercase tracking-[0.14em] text-gray-400">Risk score</p>
          <div className="flex flex-col gap-1.5">
            {BANDS.map(b => (
              <div key={b.label} className="flex items-center gap-2.5">
                <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: b.color }} />
                <span className="w-16 text-[11px] text-gray-600">{b.label}</span>
                <span className="text-[10px] tabular-nums text-gray-400">{b.range}</span>
              </div>
            ))}
          </div>
          <p className="mt-2 border-t border-gray-200 pt-2 text-[9px] text-gray-400">H3 res 8 · ≈ 0.7 km² / cell</p>
        </div>
        {/* cell detail */}
        {selected && (
          <div className="absolute bottom-4 right-4 z-10 rounded-2xl bg-white/90 px-3.5 py-2.5 text-[11px] shadow-sm backdrop-blur border border-black/[0.06]">
            <div className="font-mono text-gray-400">{selected.h3_cell}</div>
            <div className="mt-1 flex items-center gap-2">
              <span className="text-base font-semibold" style={{ color: bucketColor(selected.bucket) }}>{Math.round(selected.score)}</span>
              <span className="text-gray-400">/ 100 · {selected.bucket}</span>
            </div>
          </div>
        )}
        {geo?.cells?.length
          ? <RiskMap scores={geo.cells} onCellClick={onCell} hazard={hazard} viewOverride={view} />
          : <div className="flex h-full items-center justify-center text-gray-400">loading map…</div>}
      </div>

      {/* Right rail */}
      <aside className="w-80 shrink-0 overflow-y-auto border-l border-gray-200 bg-white p-4 space-y-4">
        <section className="rounded-2xl bg-[#f5f5f7] p-4">
          <h3 className="flex items-center gap-2 text-[15px] font-semibold"><Activity size={15} className="text-[#ff9500]" /> Forecast vs reality</h3>
          <p className="mt-0.5 text-[11px] text-gray-500">Venezuela M7.5 aftershocks — Omori-Utsu model checked daily</p>
          {verif ? <VerificationPanel v={verif} /> : <p className="mt-3 text-xs text-gray-400">no verification data yet</p>}
        </section>

        <section className="rounded-2xl bg-[#f5f5f7] p-4">
          <h3 className="flex items-center gap-2 text-[15px] font-semibold"><Radio size={15} className="text-emerald-600" /> Live seismic feed</h3>
          <p className="mt-0.5 text-[11px] text-gray-500">USGS global · M≥4.5 · last 14 days</p>
          <ul className="mt-3 space-y-1">
            {events.slice(0, 12).map(e => {
              const big = e.magnitude >= 6, mid = e.magnitude >= 5
              return (
                <li key={e.event_id} className="flex items-center gap-2 rounded-lg bg-white px-2 py-1.5 text-[11px]">
                  <span className="w-9 shrink-0 rounded-md px-1 py-0.5 text-center font-semibold"
                    style={{ background: big ? '#ffe5e3' : mid ? '#fff0e0' : '#f0f0f2',
                             color: big ? '#ff3b30' : mid ? '#ff9500' : '#6e6e73' }}>
                    {e.magnitude.toFixed(1)}
                  </span>
                  <span className="flex-1 truncate text-gray-700">{e.region_name}</span>
                  <span className="shrink-0 text-gray-400">{e.origin_time?.slice(5, 10)}</span>
                </li>
              )
            })}
            {!events.length && <li className="text-xs text-gray-400">no recent events</li>}
          </ul>
        </section>
      </aside>
    </div>
  )
}

function VerificationPanel({ v }) {
  const hi = Math.max(v.predicted_count + 3 * v.sigma, v.observed_count + 1, 1)
  const pct = x => `${Math.min(100, Math.max(0, (x / hi) * 100))}%`
  const lo2 = Math.max(0, v.predicted_count - 2 * v.sigma)
  const hi2 = v.predicted_count + 2 * v.sigma
  const outOfBand = !v.within_2sigma
  return (
    <div className="mt-3 space-y-3">
      <div className="flex items-end gap-2">
        <span className="text-3xl font-semibold tabular-nums tracking-tight" style={{ color: outOfBand ? '#ff3b30' : '#34c759' }}>
          {v.z_score > 0 ? '+' : ''}{v.z_score.toFixed(1)}σ
        </span>
        <span className="mb-1.5 rounded-full px-2 py-0.5 text-[10px] font-semibold"
          style={{ background: outOfBand ? '#ffe5e3' : '#e3f9e9', color: outOfBand ? '#ff3b30' : '#34c759' }}>
          {outOfBand ? 'OUT OF BAND' : 'within band'}
        </span>
      </div>
      <div className="relative h-6 rounded-lg bg-gray-200">
        <div className="absolute top-0 bottom-0 rounded-lg" style={{ left: pct(lo2), width: `calc(${pct(hi2)} - ${pct(lo2)})`, background: 'rgba(52,199,89,0.25)' }} />
        <div className="absolute top-0 bottom-0 w-px bg-[#34c759]" style={{ left: pct(v.predicted_count) }} />
        <div className="absolute -top-0.5 h-7 w-1 rounded bg-[#ff3b30]" style={{ left: pct(v.observed_count) }} title="observed" />
      </div>
      <div className="grid grid-cols-2 gap-2 text-[11px]">
        <Stat label="Predicted M≥4.5" value={`${v.predicted_count.toFixed(0)} ± ${v.sigma.toFixed(0)}`} />
        <Stat label="Observed" value={v.observed_count} accent={outOfBand ? '#ff3b30' : '#34c759'} />
        <Stat label="P(M≥5) forecast" value={(v.m5_forecast * 100).toFixed(0) + '%'} />
        <Stat label="M≥5 occurred" value={v.m5_occurred ? 'yes' : `no (max M${v.largest_obs_mag?.toFixed(1)})`}
          accent={v.m5_occurred ? '#ff3b30' : '#6e6e73'} />
      </div>
      <p className="text-[10px] leading-snug text-gray-400">
        Day {v.elapsed_days?.toFixed(1)}. Generic California (Reasenberg-Jones) parameters over-predict this
        sequence; the daily series accrues until we recalibrate decay to the observed aftershocks.
      </p>
    </div>
  )
}

const Stat = ({ label, value, accent }) => (
  <div className="rounded-lg bg-white px-2.5 py-1.5">
    <div className="text-[9px] uppercase tracking-wide text-gray-400">{label}</div>
    <div className="font-semibold tabular-nums" style={{ color: accent || '#1d1d1f' }}>{value}</div>
  </div>
)
