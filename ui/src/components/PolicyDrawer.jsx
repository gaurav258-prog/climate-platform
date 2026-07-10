import { useEffect, useState } from 'react'
import { Umbrella, Zap } from 'lucide-react'
import { fetchInsurancePolicy, fetchModels } from '../api/client'
import { DrawerShell, RiskSection, Facts } from './EntityDrawerParts'

const euro = n => n == null ? '—' : '€' + Math.round(n).toLocaleString()

/** The per-policy drill-through insurance was missing entirely -- no
 * valuation-override concept here (unlike banking/real-estate/asset-mgmt),
 * since pricing is a computed premium, not a human-overridable discount, so
 * this is read-only: pricing chain + parametric trigger status + provenance. */
export default function PolicyDrawer({ policyId, onClose, scenario = 'baseline', horizon = 'current' }) {
  const [data, setData] = useState(null)
  const [models, setModels] = useState([])

  useEffect(() => {
    if (!policyId) return
    setData(null)
    fetchInsurancePolicy(policyId).then(setData).catch(() => setData({ error: true }))
  }, [policyId])
  useEffect(() => { fetchModels().then(d => setModels(d.models || [])).catch(() => {}) }, [])

  if (!policyId) return null
  const p = data?.policy
  // policy_detail scores every scenario x horizon this policy has ever seen (same
  // "no scoped params" quirk as banking's asset_detail) -- filter to what the page
  // has selected, or every hazard would render once per scenario/horizon combination.
  const risks = (data?.risks || []).filter(r => r.scenario === scenario && r.time_horizon === horizon)

  return (
    <DrawerShell title={p?.policy_name} subtitle={p && `${p.policy_type} · ${p.country} · ${p.region}`} loading={!p} onClose={onClose}>
      {p && (
        <>
          <RiskSection risks={risks} models={models} emptyNote="This policy's cell has not been scored — surfaced honestly, never a silent zero." />

          {p.pricing ? (
            <section className="rounded-2xl bg-[#f5f5f7] p-4">
              <div className="flex items-center gap-1.5 text-[11px] uppercase tracking-wide text-gray-400">
                <Umbrella size={13} /> Loss-curve pricing
              </div>
              <div className="mt-2 flex items-end justify-between">
                <div>
                  <div className="text-[11px] text-gray-500">Gross premium</div>
                  <div className="text-xl font-semibold text-[#1d1d1f]">{euro(p.pricing.gross_premium_eur)}</div>
                </div>
                <div className="text-right text-[12px] text-gray-500">{p.pricing.rate_on_line_pct}% rate on line</div>
              </div>
              <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-1.5 text-[12px]">
                <Row k="MDR (damage ratio)" v={`${(p.pricing.mdr * 100).toFixed(1)}%`} />
                <Row k="Return period" v={`1-in-${p.pricing.return_period_years}yr (${p.pricing.return_period_model})`} />
                <Row k="Scenario loss" v={euro(p.pricing.scenario_loss_eur)} />
                <Row k="Deductible retained" v={euro(p.pricing.retained_loss_eur)} />
                <Row k="Net scenario loss" v={euro(p.pricing.net_scenario_loss_eur)} />
                <Row k="Expected annual loss" v={euro(p.pricing.expected_annual_loss_eur)} />
              </dl>
            </section>
          ) : (
            <p className="text-[12px] text-gray-400">No premium computed — this policy's cell has no priceable headline score.</p>
          )}

          {p.trigger && (
            <section className="rounded-2xl bg-[#f5f5f7] p-4">
              <div className="flex items-center gap-1.5 text-[11px] uppercase tracking-wide text-gray-400">
                <Zap size={13} /> Parametric trigger
              </div>
              <div className="mt-2 flex items-end justify-between">
                <div>
                  <div className="text-[11px] text-gray-500 capitalize">{p.trigger.hazard_type.replace('_', ' ')} band</div>
                  <div className="text-[13px] font-medium text-[#1d1d1f]">
                    {p.trigger.attachment_score} → {p.trigger.exhaustion_score}
                  </div>
                </div>
                <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${
                  p.trigger.is_triggered ? 'bg-red-50 text-red-600' : 'bg-gray-100 text-gray-500'}`}>
                  {p.trigger.is_triggered ? 'TRIGGERED' : 'not triggered'}
                </span>
              </div>
              <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-1.5 text-[12px]">
                <Row k="Current score" v={p.trigger.current_score?.toFixed(1) ?? '—'} />
                <Row k="Payout" v={`${p.trigger.payout_pct}% · ${euro(p.trigger.payout_eur)}`} />
              </dl>
            </section>
          )}

          <Facts title="Exposure" rows={[
            ['Sum insured (TIV)', euro(p.sum_insured_eur)],
            ['Building / contents / BI', `${euro(p.building_value_eur)} / ${euro(p.contents_value_eur)} / ${euro(p.business_interruption_value_eur)}`],
            ['Deductible', p.deductible_pct != null ? `${(p.deductible_pct * 100).toFixed(1)}%` : '—'],
            ['Construction', `${p.construction_type || '—'} · built ${p.year_built || '—'}`],
          ]} />
        </>
      )}
    </DrawerShell>
  )
}

function Row({ k, v }) {
  return <><dt className="text-gray-500">{k}</dt><dd className="text-right font-medium text-[#1d1d1f]">{v}</dd></>
}
