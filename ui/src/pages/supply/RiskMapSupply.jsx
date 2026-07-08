import { useState, useEffect, useMemo, useCallback } from 'react'
import ContextBar from '../../components/ContextBar'
import RiskMap from '../../components/RiskMap'
import SupplyPlotDrawer from '../../components/SupplyPlotDrawer'
import { BUCKET } from '../../components/RiskAtom'
import { fetchSupplyPortfolio } from '../../api/client'

const BANDS = [['VH', 'Very High'], ['H', 'High'], ['M', 'Medium'], ['L', 'Low']]

export default function RiskMapSupply() {
  const [scenario, setScenario] = useState('baseline')
  const [horizon, setHorizon] = useState('current')
  const [plots, setPlots] = useState([])
  const [sel, setSel] = useState(null)

  useEffect(() => {
    fetchSupplyPortfolio({ scenario, horizon })
      .then(d => setPlots((d.plots || []).filter(p => p.lat != null)))
      .catch(() => setPlots([]))
  }, [scenario, horizon])

  // shape sourcing plots as the map's "assets"
  const assets = useMemo(() => plots.map(p => ({
    asset_id: p.plot_id, lat: p.lat, lon: p.lon,
    headline_bucket: p.bucket, headline_score: p.hazard_score,
    headline_hazard: p.top_hazard, asset_name: p.plot_name,
    sector: p.commodity, country: p.country, value_eur: p.spend_eur,
  })), [plots])

  const view = useMemo(() => {
    if (!assets.length) return null
    let lat = 0, lon = 0
    for (const a of assets) { lat += a.lat; lon += a.lon }
    // plots span Iberia + West Africa + Brazil — zoom out to show the whole sourcing footprint
    return { latitude: lat / assets.length, longitude: lon / assets.length, zoom: 2.4, pitch: 0, bearing: 0 }
  }, [assets])

  const atRisk = assets.filter(a => a.headline_bucket === 'H' || a.headline_bucket === 'VH').length

  return (
    <div className="flex h-full flex-col bg-[#f5f5f7]">
      <ContextBar scenario={scenario} horizon={horizon} onScenario={setScenario} onHorizon={setHorizon}
        vintage="2024-10-29" label="Agriculture · Risk map" />
      <div className="relative flex-1">
        <div className="absolute top-4 left-4 z-10 rounded-2xl bg-white/85 px-3.5 py-2.5 text-[11px] shadow-sm backdrop-blur border border-black/[0.06]">
          <div className="font-medium text-[#1d1d1f]">{assets.length} sourcing plots · {atRisk} at High+ hazard</div>
          <div className="mt-0.5 text-gray-500">your procurement footprint on the golden source</div>
        </div>
        <div className="absolute bottom-4 left-4 z-10 rounded-2xl bg-white/85 px-3.5 py-3 shadow-sm backdrop-blur border border-black/[0.06]">
          <p className="mb-2 text-[9px] uppercase tracking-[0.14em] text-gray-400">Plot hazard</p>
          {BANDS.map(([k, label]) => (
            <div key={k} className="flex items-center gap-2 text-[11px]">
              <span className="h-2.5 w-2.5 rounded-full border border-white" style={{ background: BUCKET[k].c }} />
              <span className="text-gray-600">{label}</span>
            </div>
          ))}
          <div className="mt-1 flex items-center gap-2 text-[11px]">
            <span className="h-2.5 w-2.5 rounded-full border border-white bg-[#787882]" />
            <span className="text-gray-400">Unscored (€ pending)</span>
          </div>
        </div>
        {view
          ? <RiskMap scores={[]} onCellClick={() => {}} hazard="heat_acute" viewOverride={view}
              assets={assets} onAssetClick={a => setSel(a.asset_id)} />
          : <div className="flex h-full items-center justify-center text-gray-400">loading map…</div>}
      </div>
      {sel && <SupplyPlotDrawer plotId={sel} onClose={() => setSel(null)} scenario={scenario} horizon={horizon} />}
    </div>
  )
}
