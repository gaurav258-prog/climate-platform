import { useState, useEffect } from 'react'
import { X } from 'lucide-react'
import { fetchSupplyPlot } from '../api/client'

export const HAZ_COLOR = {
  flood: '#2563eb', wildfire: '#c2410c', seismic: '#7c3aed', heat_acute: '#dc2626', drought: '#b45309',
  volcanic: '#7c2d12', storm: '#0e7490', pollution: '#78716c',
}
const mn = n => '€' + ((n || 0) / 1e6).toFixed(1) + 'm'

/** Slide-over: one sourcing plot → its projected hazard scores + full provenance. */
export default function SupplyPlotDrawer({ plotId, onClose, scenario, horizon }) {
  const [d, setD] = useState(null)
  useEffect(() => { setD(null); fetchSupplyPlot(plotId).then(setD).catch(() => setD(null)) }, [plotId])
  const risks = (d?.risks || []).filter(r => r.scenario === scenario && r.time_horizon === horizon)
  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-black/20" onClick={onClose}>
      <div className="h-full w-[420px] overflow-y-auto bg-white shadow-xl" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-gray-200 px-5 py-3">
          <span className="text-[13px] font-semibold text-[#1d1d1f]">Sourcing plot</span>
          <button onClick={onClose} className="text-gray-400 hover:text-[#1d1d1f]"><X size={18} /></button>
        </div>
        {!d ? <p className="p-5 text-gray-400">loading…</p> : d.error ? <p className="p-5 text-gray-400">{d.error}</p> : (
          <div className="p-5">
            <h3 className="text-lg font-semibold text-[#1d1d1f]">{d.plot.plot_name}</h3>
            <p className="text-[12px] text-gray-500">{d.plot.commodity} · {d.plot.supplier}</p>
            <dl className="mt-4 grid grid-cols-2 gap-3 text-[12px]">
              <Field k="Region" v={`${d.plot.region}, ${d.plot.country}`} />
              <Field k="Annual spend" v={mn(d.plot.spend_eur)} />
              <Field k="Volume share" v={`${Math.round((d.plot.volume_share || 0) * 100)}%`} />
              <Field k="EUDR" v={d.plot.eudr_status} />
              <Field k="H3 cell" v={d.plot.h3_cell} />
              <Field k="Coords" v={`${d.plot.lat?.toFixed(2)}, ${d.plot.lon?.toFixed(2)}`} />
            </dl>

            <h4 className="mt-5 text-[12px] font-semibold uppercase tracking-wide text-gray-400">Projected hazard · {scenario} / {horizon}</h4>
            {risks.length === 0 ? (
              <div className="mt-2 rounded-lg bg-gray-50 px-3 py-2 text-[12px] text-gray-500">
                No canonical score for this cell — <b>€ pending</b> (hazard scoring for this origin is on the roadmap).
              </div>
            ) : (
              <div className="mt-2 divide-y divide-gray-100">
                {risks.map((rk, i) => (
                  <div key={i} className="flex items-center justify-between py-2">
                    <span className="text-[13px] capitalize" style={{ color: HAZ_COLOR[rk.hazard_type] }}>{rk.hazard_type}</span>
                    <span className="text-right">
                      <span className="text-[14px] font-semibold text-[#1d1d1f]">{rk.score?.toFixed(1)}</span>
                      <span className="block text-[10px] text-gray-400">{rk.model_version} · {rk.scored_at?.slice(0, 10)}</span>
                    </span>
                  </div>
                ))}
              </div>
            )}
            <p className="mt-4 text-[10px] leading-relaxed text-gray-400">{d.note}</p>
          </div>
        )}
      </div>
    </div>
  )
}

function Field({ k, v }) {
  return <div><dt className="text-gray-400">{k}</dt><dd className="mt-0.5 font-medium text-[#1d1d1f] break-all">{v}</dd></div>
}
