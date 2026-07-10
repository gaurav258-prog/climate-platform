import { useEffect, useState } from 'react'
import { TrendingUp } from 'lucide-react'
import { fetchAssetMgmtHolding, fetchModels, overrideAssetMgmtValuation, clearAssetMgmtValuationOverride } from '../api/client'
import ValuationOverrideSection, { euro } from './ValuationOverrideSection'
import { DrawerShell, RiskSection, TaxonomySection, Facts, ProvenanceFooter } from './EntityDrawerParts'

// The asset management drill-through — same drawer pattern as banking's
// AssetDrawer and real estate's RealEstateDrawer. Was previously missing
// entirely: the holding valuation-override endpoints existed on the backend
// with no UI path to reach them (PortfolioVaR.jsx's table had no
// click-to-detail at all). This closes that gap.
export default function AssetMgmtDrawer({ holdingId, onClose, auth, scenario = 'baseline', horizon = 'current', onGoto }) {
  const [data, setData] = useState(null)
  const [models, setModels] = useState([])

  function reload() { fetchAssetMgmtHolding(holdingId).then(setData).catch(() => setData({ error: true })) }
  useEffect(() => {
    if (!holdingId) return
    setData(null)
    reload()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [holdingId])
  useEffect(() => { fetchModels().then(d => setModels(d.models || [])).catch(() => {}) }, [])

  if (!holdingId) return null
  const h = data?.holding
  // holding_detail scores every scenario x horizon this holding has ever seen -- filter
  // to what the page has selected, same as RealEstateDrawer/AssetDrawer.
  const risks = (data?.risks || []).filter(r => r.scenario === scenario && r.time_horizon === horizon)
  const canOverride = new Set(auth?.permissions || []).has('pricing.approve')

  return (
    <DrawerShell title={h?.holding_name} subtitle={h && `${h.sector} · ${h.country} · ${h.region}`} loading={!h} onClose={onClose}>
      {h && (
        <>
          <RiskSection risks={risks} models={models} emptyNote="This holding's cell has not been scored — surfaced honestly, never a silent zero." />

          {/* climate VaR: system-recommended, human-overridable, audited */}
          {data.climate_var && (
            <ValuationOverrideSection entityId={h.holding_id} valuation={data.climate_var} audit={data.valuation_audit}
              canOverride={canOverride} onChanged={reload}
              overrideFn={overrideAssetMgmtValuation} clearFn={clearAssetMgmtValuationOverride}
              icon={TrendingUp} label="Portfolio climate VaR" discountLabel="Recommended climate-VaR discount" />
          )}

          <Facts title="Exposure" rows={[
            ['Position value', euro(h.position_value_eur)],
            ['Sector · NACE', `${h.sector || '—'} · ${h.nace_code || '—'}`],
            ['Screening flag', h.flagged ? 'High / Very-High' : 'Below threshold'],
          ]} />
          <TaxonomySection onGoto={onGoto} status={h.taxonomy_status} activityRef={h.taxonomy_activity_ref} />
          <ProvenanceFooter h3Cell={h.h3_cell} />
        </>
      )}
    </DrawerShell>
  )
}
