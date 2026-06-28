import { useEffect, useState } from 'react'
import { X, MapPin, ChevronDown } from 'lucide-react'
import RiskAtom, { BUCKET } from './RiskAtom'
import { fetchAsset, fetchModels } from '../api/client'

const euro = n => n == null ? '—' : '€' + Math.round(n).toLocaleString()
const euroM = n => n == null ? '—' : '€' + (n / 1e6).toFixed(1) + 'm'

// The drill-through. Opened from the table OR the map — same component, so an
// asset reads identically wherever you click it. Every hazard score carries the
// model version + scored date that produced it (defensible disclosure).
export default function AssetDrawer({ assetId, onClose, scenario = 'baseline', horizon = 'current' }) {
  const [data, setData] = useState(null)
  const [models, setModels] = useState([])
  const [openHz, setOpenHz] = useState(null)
  useEffect(() => {
    if (!assetId) return
    setData(null); setOpenHz(null)
    fetchAsset(assetId).then(setData).catch(() => setData({ error: true }))
  }, [assetId])
  useEffect(() => { fetchModels().then(d => setModels(d.models || [])).catch(() => {}) }, [])

  if (!assetId) return null
  const a = data?.asset
  const risks = (data?.risks || []).filter(r => r.scenario === scenario && r.time_horizon === horizon)
  const headline = risks.slice().sort((x, y) => y.score - x.score)[0]

  return (
    <>
      <div className="fixed inset-0 z-40 bg-black/20" onClick={onClose} />
      <aside className="fixed right-0 top-0 z-50 flex h-full w-[420px] flex-col overflow-y-auto bg-white shadow-2xl">
        <header className="sticky top-0 flex items-start justify-between border-b border-gray-200 bg-white/90 px-5 py-4 backdrop-blur">
          <div className="min-w-0">
            {a ? (
              <>
                <h2 className="truncate text-[17px] font-semibold text-[#1d1d1f]">{a.asset_name}</h2>
                <p className="mt-0.5 text-[12px] text-gray-500">{a.sector} · {a.country} · {a.region}</p>
              </>
            ) : <h2 className="text-[15px] text-gray-400">loading…</h2>}
          </div>
          <button onClick={onClose} className="rounded-full p-1.5 text-gray-400 hover:bg-gray-100 hover:text-gray-700"><X size={18} /></button>
        </header>

        {a && (
          <div className="space-y-5 px-5 py-5">
            {/* headline risk */}
            <section className="rounded-2xl bg-[#f5f5f7] p-4">
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-[11px] uppercase tracking-wide text-gray-400">Physical risk</div>
                  <div className="text-[13px] text-gray-600">{headline ? `driven by ${headline.hazard_type}` : 'no scored hazard'}</div>
                </div>
                {headline
                  ? <RiskAtom score={headline.score} bucket={headline.risk_bucket} size="lg" showLabel />
                  : <RiskAtom score={null} bucket={null} size="lg" />}
              </div>
              {/* per-hazard rows — the same RiskAtom as the table & map */}
              <div className="mt-4 space-y-2">
                {risks.length ? risks.map(r => {
                  const m = models.find(x => x.model_version === r.model_version)
                  const open = openHz === r.hazard_type
                  return (
                    <div key={r.hazard_type} className="overflow-hidden rounded-lg bg-white">
                      <button onClick={() => setOpenHz(open ? null : r.hazard_type)}
                        className="flex w-full items-center justify-between px-3 py-2 text-left hover:bg-gray-50">
                        <div>
                          <div className="flex items-center gap-1 text-[13px] font-medium capitalize text-[#1d1d1f]">
                            {r.hazard_type.replace('_', ' ')}
                            <ChevronDown size={13} className={`text-gray-400 transition ${open ? 'rotate-180' : ''}`} />
                          </div>
                          <div className="font-mono text-[10px] text-gray-400">{r.model_version} · {String(r.scored_at).slice(0, 10)}</div>
                        </div>
                        <RiskAtom score={r.score} bucket={r.risk_bucket} size="md" />
                      </button>
                      {open && (
                        <div className="border-t border-gray-100 px-3 py-2.5 text-[11px]">
                          {m ? (
                            <>
                              <div className="text-gray-500">Out-of-sample skill:{' '}
                                <span className="font-semibold text-[#1d1d1f]">{m.auc != null ? `LOEO AUC ${m.auc.toFixed(3)}` : 'physics-based'}</span>
                                {m.avg_precision != null ? ` · AP ${m.avg_precision.toFixed(3)}` : ''}
                                {m.training_cell_count ? ` · ${m.training_cell_count.toLocaleString()} cells` : ''}
                              </div>
                              {m.validation_note && <p className="mt-1.5 leading-snug text-gray-500">{m.validation_note}</p>}
                            </>
                          ) : <p className="text-gray-400">model metadata unavailable</p>}
                        </div>
                      )}
                    </div>
                  )
                }) : <p className="text-[12px] text-gray-400">This asset's cell has not been scored — surfaced honestly, never a silent zero.</p>}
              </div>
            </section>

            {/* exposure & disclosure facts */}
            <Facts title="Exposure" rows={[
              ['Loan / asset value', euro(a.value_eur)],
              ['Annual revenue', euro(a.revenue_eur)],
              ['Value at this risk', headline && (headline.risk_bucket === 'H' || headline.risk_bucket === 'VH') ? euroM(a.value_eur) : '—'],
            ]} />
            <Facts title="Disclosure (TCFD / EU Taxonomy)" rows={[
              ['Taxonomy status', a.taxonomy_status || '—'],
              ['NACE · GICS', `${a.nace_code || '—'} · ${a.gics_code || '—'}`],
              ['Construction year', a.construction_year || '—'],
              ['GHG scope 1 / 2 / 3 (tCO₂e)', `${fmt(a.ghg_scope1)} / ${fmt(a.ghg_scope2)} / ${fmt(a.ghg_scope3)}`],
            ]} />

            {/* provenance footer */}
            <div className="flex items-center gap-1.5 rounded-xl border border-gray-200 px-3 py-2 text-[11px] text-gray-500">
              <MapPin size={13} className="text-gray-400" />
              <span className="font-mono">{a.h3_cell}</span>
              <span className="text-gray-300">·</span>
              <span>projected from canonical_scores</span>
            </div>
          </div>
        )}
      </aside>
    </>
  )
}

const fmt = n => n == null ? '—' : Math.round(n).toLocaleString()

function Facts({ title, rows }) {
  return (
    <section>
      <h3 className="mb-2 text-[11px] uppercase tracking-wide text-gray-400">{title}</h3>
      <div className="divide-y divide-gray-100 rounded-2xl border border-gray-200">
        {rows.map(([k, v]) => (
          <div key={k} className="flex items-center justify-between px-3 py-2 text-[13px]">
            <span className="text-gray-500">{k}</span>
            <span className="font-medium text-[#1d1d1f]">{v}</span>
          </div>
        ))}
      </div>
    </section>
  )
}
