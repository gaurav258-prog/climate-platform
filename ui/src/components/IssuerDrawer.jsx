import { useEffect, useState } from 'react'
import { Building2, Factory, Flame, Leaf } from 'lucide-react'
import { fetchIssuer } from '../api/client'
import { DrawerShell, Facts } from './EntityDrawerParts'
import RiskAtom from './RiskAtom'

const fmtT = n => n == null ? '—' : Math.round(n).toLocaleString() + ' tCO₂e'
const euro = n => n == null ? '—' : '€' + Math.round(n).toLocaleString()

/** The lowest level of the securities book: one issuer, its materiality-weighted
 * facility FOOTPRINT with each facility's raw golden-source scores, plus its
 * transition risk and emissions. This is what makes an issuer's headline score
 * traceable to real cells — the fix for "one lat/lon per holding". */
export default function IssuerDrawer({ issuerId, scenario = 'baseline', horizon = 'current', onClose }) {
  const [data, setData] = useState(null)

  useEffect(() => {
    if (!issuerId) return
    setData(null)
    fetchIssuer(issuerId, { scenario, horizon }).then(setData).catch(() => setData({ error: true }))
  }, [issuerId, scenario, horizon])

  if (!issuerId) return null
  const iss = data?.issuer
  const ph = data?.physical
  const tr = data?.transition
  const em = data?.emissions

  return (
    <DrawerShell title={iss?.name} subtitle={iss && `${iss.issuer_type} · ${iss.country || '—'} · NACE ${iss.nace_code || '—'}`}
      loading={!iss && !data?.error} onClose={onClose}>
      {data?.error && <p className="text-[13px] text-gray-400">This issuer could not be found in your holdings.</p>}
      {iss && (
        <>
          {/* Two-dimensional risk: physical footprint + transition */}
          <div className="grid grid-cols-2 gap-3">
            <section className="rounded-2xl bg-[#f5f5f7] p-3">
              <div className="flex items-center gap-1.5 text-[11px] uppercase tracking-wide text-gray-400"><Building2 size={13} /> Physical</div>
              <div className="mt-1.5 flex items-center justify-between">
                <div className="text-[12px] text-gray-500">{ph?.headline_hazard || 'no scored hazard'}</div>
                <RiskAtom score={ph?.headline_score} bucket={ph?.headline_bucket} size="md" showLabel />
              </div>
              <div className="mt-1 text-[10px] text-gray-400">
                {ph?.n_scored_facilities}/{ph?.n_facilities} facilities scored · {ph?.scored_weight_pct}% of materiality
              </div>
            </section>
            <section className="rounded-2xl bg-[#f5f5f7] p-3">
              <div className="flex items-center gap-1.5 text-[11px] uppercase tracking-wide text-gray-400"><Flame size={13} /> Transition</div>
              {tr ? (
                <>
                  <div className="mt-1.5 flex items-center justify-between">
                    <div className="text-[12px] text-gray-500">{tr.dominant_channel === 'carbon_cost' ? 'carbon cost' : 'stranded assets'}</div>
                    <RiskAtom score={tr.transition_risk_score} bucket={tr.risk_bucket} size="md" showLabel />
                  </div>
                  <div className="mt-1 text-[10px] text-gray-400">
                    {tr.carbon_intensity_tco2e_per_meur ?? '—'} tCO₂e/€m · strand {tr.stranded_asset_pct}%
                  </div>
                </>
              ) : <p className="mt-2 text-[12px] text-gray-400">No transition score — supply emissions to compute.</p>}
            </section>
          </div>

          {tr && tr.carbon_price_impact_eur != null && (
            <div className="rounded-xl bg-amber-50 px-3 py-2 text-[12px] text-amber-800">
              Modeled carbon cost at this scenario's price ({euro(tr.carbon_price_eur_per_tonne)}/t):
              <b> {euro(tr.carbon_price_impact_eur)}/yr</b>
              {tr.carbon_cost_pct_of_revenue != null && <> · {tr.carbon_cost_pct_of_revenue}% of revenue</>}
            </div>
          )}

          {em && (
            <Facts title="Disclosed emissions (latest)" rows={[
              ['Scope 1', fmtT(em.scope1)], ['Scope 2', fmtT(em.scope2)], ['Scope 3', fmtT(em.scope3)],
              ['Revenue', euro(em.revenue_eur)], ['Source', em.source],
            ]} />
          )}

          {/* The footprint: each facility with its raw golden-source scores */}
          <section>
            <h3 className="mb-2 flex items-center gap-1.5 text-[11px] uppercase tracking-wide text-gray-400">
              <Factory size={13} /> Facility footprint <span className="text-gray-300">— materiality-weighted</span>
            </h3>
            <div className="space-y-2">
              {(data.facilities || []).map(f => (
                <div key={f.facility_id} className="rounded-xl border border-gray-200 p-3">
                  <div className="flex items-center justify-between">
                    <div className="text-[13px] font-medium text-[#1d1d1f]">{f.name || f.facility_type}</div>
                    <span className="rounded-full bg-gray-100 px-2 py-0.5 text-[10px] font-medium text-gray-500">
                      w {(f.materiality_weight * 100).toFixed(0)}% · {f.weight_basis}
                    </span>
                  </div>
                  <div className="text-[10px] text-gray-400">{f.country || '—'} · {f.h3_cell}</div>
                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                    {f.scores.length ? f.scores.map(s => (
                      <span key={s.hazard} className="rounded-md bg-[#f5f5f7] px-1.5 py-0.5 text-[10px] text-gray-600">
                        {s.hazard} <b className="text-[#1d1d1f]">{s.score}</b> ({s.bucket})
                      </span>
                    )) : <span className="text-[10px] text-gray-400">not in golden source — excluded from the weighted score, not imputed</span>}
                  </div>
                </div>
              ))}
            </div>
          </section>

          <div className="flex items-center gap-1.5 rounded-xl border border-gray-200 px-3 py-2 text-[11px] text-gray-500">
            <Leaf size={13} className="text-gray-400" />
            <span>Issuer score = materiality-weighted roll-up of these facilities' cell scores (canonical_scores).</span>
          </div>
        </>
      )}
    </DrawerShell>
  )
}
