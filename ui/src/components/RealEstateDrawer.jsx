import { useEffect, useState } from 'react'
import { Building2 } from 'lucide-react'
import { fetchRealEstateProperty, fetchModels, overrideRealEstateValuation, clearRealEstateValuationOverride } from '../api/client'
import ValuationOverrideSection, { euro, euroM } from './ValuationOverrideSection'
import { DrawerShell, RiskSection, TaxonomySection, Facts, ProvenanceFooter } from './EntityDrawerParts'

// The real estate drill-through — same drawer pattern as banking's AssetDrawer,
// reusing the same shared pieces. Was previously missing entirely: the
// property valuation-override endpoints existed on the backend with no UI
// path to reach them (PortfolioImpact.jsx's table had no click-to-detail at
// all). This closes that gap.
export default function RealEstateDrawer({ propertyId, onClose, auth, scenario = 'baseline', horizon = 'current', onGoto }) {
  const [data, setData] = useState(null)
  const [models, setModels] = useState([])

  function reload() { fetchRealEstateProperty(propertyId).then(setData).catch(() => setData({ error: true })) }
  useEffect(() => {
    if (!propertyId) return
    setData(null)
    reload()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [propertyId])
  useEffect(() => { fetchModels().then(d => setModels(d.models || [])).catch(() => {}) }, [])

  if (!propertyId) return null
  const p = data?.property
  // property_detail scores every scenario x horizon this property has ever seen (same
  // "no scoped params" quirk as banking's asset_detail) -- filter to what the page has
  // selected, or every hazard would render once per scenario/horizon combination.
  const risks = (data?.risks || []).filter(r => r.scenario === scenario && r.time_horizon === horizon)
  const canOverride = new Set(auth?.permissions || []).has('pricing.approve')

  return (
    <DrawerShell title={p?.property_name} subtitle={p && `${p.property_type} · ${p.country} · ${p.region}`} loading={!p} onClose={onClose}>
      {p && (
        <>
          <RiskSection risks={risks} models={models} emptyNote="This property's cell has not been scored — surfaced honestly, never a silent zero." />

          {/* climate-adjusted value: system-recommended, human-overridable, audited */}
          {data.valuation && (
            <ValuationOverrideSection entityId={p.property_id} valuation={data.valuation} audit={data.valuation_audit}
              canOverride={canOverride} onChanged={reload}
              overrideFn={overrideRealEstateValuation} clearFn={clearRealEstateValuationOverride}
              icon={Building2} label="Climate-adjusted valuation" discountLabel="Recommended valuation discount"
              extra={data.noi_impact && (
                <div className="mt-3 flex items-center justify-between rounded-xl bg-gray-50 px-3 py-2">
                  <div>
                    <div className="text-[11px] text-gray-500">Annual NOI</div>
                    <div className="text-[13px] font-medium text-[#1d1d1f]">{euro(p.annual_noi_eur)}</div>
                  </div>
                  <div className="text-right">
                    <span className="text-[13px] font-semibold text-[#c2410c]">
                      {data.noi_impact.noi_impact_pct}% NOI impact
                    </span>
                    <div className="text-[11px] text-gray-500">{euro(data.noi_impact.expected_insurance_premium_eur)} expected premium</div>
                  </div>
                </div>
              )} />
          )}

          <Facts title="Exposure" rows={[
            ['Property value', euro(p.property_value_eur)],
            ['Annual NOI', euro(p.annual_noi_eur)],
            ['Construction', `${p.construction_type || '—'} · built ${p.year_built || '—'}`],
          ]} />
          <TaxonomySection onGoto={onGoto} status={p.taxonomy_status} activityRef={p.taxonomy_activity_ref}
            reasoning={p.taxonomy_reasoning} />
          <ProvenanceFooter h3Cell={p.h3_cell} />
        </>
      )}
    </DrawerShell>
  )
}
