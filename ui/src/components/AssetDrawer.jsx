import { useEffect, useState } from 'react'
import { Landmark } from 'lucide-react'
import { fetchAsset, fetchModels, overrideValuation, clearValuationOverride } from '../api/client'
import ValuationOverrideSection, { euro, euroM } from './ValuationOverrideSection'
import { DrawerShell, RiskSection, TaxonomySection, Facts, ProvenanceFooter } from './EntityDrawerParts'

const fmt = n => n == null ? '—' : Math.round(n).toLocaleString()

// The drill-through. Opened from the table OR the map — same component, so an
// asset reads identically wherever you click it. Every hazard score carries the
// model version + scored date that produced it (defensible disclosure).
export default function AssetDrawer({ assetId, onClose, scenario = 'baseline', horizon = 'current', auth }) {
  const [data, setData] = useState(null)
  const [models, setModels] = useState([])

  function reload() { fetchAsset(assetId).then(setData).catch(() => setData({ error: true })) }
  useEffect(() => {
    if (!assetId) return
    setData(null)
    reload()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [assetId])
  useEffect(() => { fetchModels().then(d => setModels(d.models || [])).catch(() => {}) }, [])

  if (!assetId) return null
  const a = data?.asset
  const risks = (data?.risks || []).filter(r => r.scenario === scenario && r.time_horizon === horizon)
  const headline = risks.slice().sort((x, y) => y.score - x.score)[0]
  const canOverride = new Set(auth?.permissions || []).has('pricing.approve')

  return (
    <DrawerShell title={a?.asset_name} subtitle={a && `${a.sector} · ${a.country} · ${a.region}`} loading={!a} onClose={onClose}>
      {a && (
        <>
          <RiskSection risks={risks} models={models} emptyNote="This asset's cell has not been scored — surfaced honestly, never a silent zero." />

          {/* lending decision: system-recommended, human-overridable, audited */}
          {data.valuation && (
            <ValuationOverrideSection entityId={a.asset_id} valuation={data.valuation} audit={data.valuation_audit}
              canOverride={canOverride} onChanged={reload}
              overrideFn={overrideValuation} clearFn={clearValuationOverride}
              icon={Landmark} label="Lending decision" discountLabel="Recommended valuation discount"
              extra={data.valuation.original_ltv_pct != null && (
                <div className="mt-3 flex items-center justify-between rounded-xl bg-gray-50 px-3 py-2">
                  <div>
                    <div className="text-[11px] text-gray-500">Loan-to-value</div>
                    <div className="text-[13px] font-medium text-[#1d1d1f]">{euro(data.valuation.outstanding_loan_balance_eur)} outstanding</div>
                  </div>
                  <div className="text-right">
                    <span className="text-[13px] text-gray-500">{data.valuation.original_ltv_pct}%</span>
                    <span className="mx-1.5 text-gray-300">→</span>
                    <span className={`text-[13px] font-semibold ${data.valuation.climate_adjusted_ltv_pct >= 100 ? 'text-red-600' : 'text-[#1d1d1f]'}`}>
                      {data.valuation.climate_adjusted_ltv_pct}% climate-adjusted
                    </span>
                  </div>
                </div>
              )} />
          )}

          <Facts title="Exposure" rows={[
            ['Loan / asset value', euro(a.value_eur)],
            ['Annual revenue', euro(a.revenue_eur)],
            ['Value at this risk', headline && (headline.risk_bucket === 'H' || headline.risk_bucket === 'VH') ? euroM(a.value_eur) : '—'],
          ]} />
          <TaxonomySection status={a.taxonomy_status} activityRef={a.dnsh_assessment?.activity_ref}
            dnshFlag={a.dnsh_assessment?.dnsh_climate_adaptation_flag} />
          <Facts title="Disclosure (TCFD / EU Taxonomy)" rows={[
            ['NACE · GICS', `${a.nace_code || '—'} · ${a.gics_code || '—'}`],
            ['Construction year', a.construction_year || '—'],
            ['GHG scope 1 / 2 / 3 (tCO₂e)', `${fmt(a.ghg_scope1)} / ${fmt(a.ghg_scope2)} / ${fmt(a.ghg_scope3)}`],
          ]} />
          <ProvenanceFooter h3Cell={a.h3_cell} />
        </>
      )}
    </DrawerShell>
  )
}
