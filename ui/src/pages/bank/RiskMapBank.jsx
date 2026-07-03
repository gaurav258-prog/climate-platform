import { useState, useEffect, useMemo, useCallback } from 'react'
import ContextBar from '../../components/ContextBar'
import RiskMap from '../../components/RiskMap'
import AssetDrawer from '../../components/AssetDrawer'
import { BUCKET } from '../../components/RiskAtom'
import { fetchGeoScores, fetchPortfolio } from '../../api/client'

const BANDS = [['VH', 'Very High'], ['H', 'High'], ['M', 'Medium'], ['L', 'Low']]
const HAZARDS = [['flood', 'Flood'], ['wildfire', 'Wildfire'], ['volcanic', 'Volcanic'], ['storm', 'Storm']]

export default function RiskMapBank() {
  const [scenario, setScenario] = useState('baseline')
  const [horizon, setHorizon] = useState('current')
  const [hazard, setHazard] = useState('flood')
  const [geo, setGeo] = useState(null)
  const [assets, setAssets] = useState([])
  const [sel, setSel] = useState(null)

  useEffect(() => {
    setGeo(null)
    fetchGeoScores(hazard).then(setGeo).catch(() => setGeo({ cells: [] }))
  }, [hazard])
  useEffect(() => {
    fetchPortfolio({ scenario, horizon })
      .then(d => setAssets((d.assets || []).filter(a => a.lat != null)))
      .catch(() => setAssets([]))
  }, [scenario, horizon])

  const assetView = useMemo(() => {
    if (!assets.length) return null
    let lat = 0, lon = 0
    for (const a of assets) { lat += a.lat; lon += a.lon }
    return { latitude: lat / assets.length, longitude: lon / assets.length, zoom: 5, pitch: 0, bearing: 0 }
  }, [assets])
  // Volcanic/storm exposure are each a small pocket (Guatemala, Puerto Rico) in an
  // otherwise-European book — centering on the whole book's average would bury them.
  // Let RiskMap's own per-hazard default view take over instead of the asset average.
  const view = (hazard === 'volcanic' || hazard === 'storm') ? null : assetView

  const onAsset = useCallback(a => setSel(a.asset_id), [])
  const atRisk = assets.filter(a => a.headline_bucket === 'H' || a.headline_bucket === 'VH').length

  return (
    <div className="flex h-full flex-col bg-[#f5f5f7]">
      <ContextBar scenario={scenario} horizon={horizon} onScenario={setScenario} onHorizon={setHorizon}
        vintage="2024-10-29" label="Banking · Risk Map" />
      <div className="relative flex-1">
        <div className="absolute top-4 left-4 z-10 rounded-2xl bg-white/85 px-3.5 py-2.5 text-[11px] shadow-sm backdrop-blur border border-black/[0.06]">
          <div className="font-medium text-[#1d1d1f]">{assets.length} assets · {atRisk} at High+ risk</div>
          <div className="mt-0.5 text-gray-500">{hazard} golden source + your loan book</div>
          <div className="mt-2 flex gap-1">
            {HAZARDS.map(([k, label]) => (
              <button key={k} onClick={() => setHazard(k)}
                className={`rounded-full px-2.5 py-1 text-[10px] font-medium transition ${
                  hazard === k ? 'bg-[#1d1d1f] text-white' : 'bg-gray-100 text-gray-500 hover:bg-gray-200'}`}>
                {label}
              </button>
            ))}
          </div>
        </div>
        <div className="absolute bottom-4 left-4 z-10 rounded-2xl bg-white/85 px-3.5 py-3 shadow-sm backdrop-blur border border-black/[0.06]">
          <p className="mb-2 text-[9px] uppercase tracking-[0.14em] text-gray-400">Asset risk</p>
          {BANDS.map(([k, label]) => (
            <div key={k} className="flex items-center gap-2 text-[11px]">
              <span className="h-2.5 w-2.5 rounded-full border border-white" style={{ background: BUCKET[k].c }} />
              <span className="text-gray-600">{label}</span>
            </div>
          ))}
          <div className="mt-1 flex items-center gap-2 text-[11px]">
            <span className="h-2.5 w-2.5 rounded-full border border-white bg-[#787882]" />
            <span className="text-gray-400">Unscored</span>
          </div>
        </div>
        {geo
          ? <RiskMap scores={geo.cells} onCellClick={() => {}} hazard={hazard} viewOverride={view}
              assets={assets} onAssetClick={onAsset} />
          : <div className="flex h-full items-center justify-center text-gray-400">loading map…</div>}
      </div>
      <AssetDrawer assetId={sel} onClose={() => setSel(null)} scenario={scenario} horizon={horizon} />
    </div>
  )
}
