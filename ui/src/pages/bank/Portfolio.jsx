import { useState, useEffect, useMemo } from 'react'
import { ArrowUpDown } from 'lucide-react'
import ContextBar from '../../components/ContextBar'
import RiskAtom from '../../components/RiskAtom'
import AssetDrawer from '../../components/AssetDrawer'
import { fetchPortfolio } from '../../api/client'

const euroM = n => n == null ? '—' : '€' + (n / 1e6).toFixed(1) + 'm'
const HAZ_COLS = ['flood', 'wildfire']

export default function Portfolio() {
  const [scenario, setScenario] = useState('baseline')
  const [horizon, setHorizon] = useState('current')
  const [data, setData] = useState(null)
  const [sel, setSel] = useState(null)
  const [sort, setSort] = useState({ key: 'risk', dir: -1 })

  useEffect(() => {
    setData(null)
    fetchPortfolio({ scenario, horizon }).then(setData).catch(() => setData({ assets: [], rollup: {} }))
  }, [scenario, horizon])

  const assets = useMemo(() => {
    const list = [...(data?.assets || [])]
    const get = a => sort.key === 'value' ? (a.value_eur || 0)
      : sort.key === 'name' ? a.asset_name
      : (a.headline_score ?? -1)
    return list.sort((x, y) => {
      const a = get(x), b = get(y)
      return (a < b ? -1 : a > b ? 1 : 0) * sort.dir
    })
  }, [data, sort])

  const r = data?.rollup || {}
  const toggle = key => setSort(s => ({ key, dir: s.key === key ? -s.dir : -1 }))

  const hazScore = (a, h) => a.hazards?.find(x => x.hazard === h)

  return (
    <div className="flex h-full flex-col bg-[#f5f5f7]">
      <ContextBar scenario={scenario} horizon={horizon} onScenario={setScenario} onHorizon={setHorizon}
        vintage="2024-10-29" label="Banking · Meridian Bank (demo)" />

      <div className="flex-1 overflow-y-auto px-8 py-6">
        <header className="mb-5 flex items-end justify-between">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight text-[#1d1d1f]">Portfolio</h1>
            <p className="mt-1 text-sm text-gray-500">
              {r.n_assets} assets · {r.n_scored} scored · book {euroM(r.total_value_eur)} ·
              <span className="font-medium text-[#c2410c]"> {euroM(r.value_at_risk_eur)} ({r.pct_value_at_risk}%) at High+ risk</span>
            </p>
          </div>
        </header>

        <div className="overflow-hidden rounded-2xl border border-gray-200/70 bg-white shadow-sm">
          <table className="w-full text-[13px]">
            <thead>
              <tr className="border-b border-gray-200 text-left text-[11px] uppercase tracking-wide text-gray-400">
                <Th onClick={() => toggle('name')}>Asset</Th>
                <th className="px-3 py-2.5 font-medium">Sector</th>
                <Th onClick={() => toggle('value')} right>Value</Th>
                {HAZ_COLS.map(h => <th key={h} className="px-3 py-2.5 text-center font-medium capitalize">{h}</th>)}
                <Th onClick={() => toggle('risk')} center>Risk</Th>
                <th className="px-3 py-2.5 font-medium">Taxonomy</th>
              </tr>
            </thead>
            <tbody>
              {!data && <tr><td colSpan={7} className="px-3 py-8 text-center text-gray-400">loading…</td></tr>}
              {assets.map(a => (
                <tr key={a.asset_id} onClick={() => setSel(a.asset_id)}
                  className="cursor-pointer border-b border-gray-50 last:border-0 hover:bg-gray-50">
                  <td className="px-3 py-2.5">
                    <div className="font-medium text-[#1d1d1f]">{a.asset_name}</div>
                    <div className="text-[11px] text-gray-400">{a.country} · {a.region}</div>
                  </td>
                  <td className="px-3 py-2.5 text-gray-500">{a.sector}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums text-[#1d1d1f]">{euroM(a.value_eur)}</td>
                  {HAZ_COLS.map(h => {
                    const hz = hazScore(a, h)
                    return <td key={h} className="px-3 py-2.5 text-center">
                      <RiskAtom score={hz?.score} bucket={hz?.bucket} size="sm" />
                    </td>
                  })}
                  <td className="px-3 py-2.5 text-center"><RiskAtom score={a.headline_score} bucket={a.headline_bucket} size="md" /></td>
                  <td className="px-3 py-2.5 text-[12px] text-gray-500 capitalize">{(a.taxonomy_status || '').replace('_', ' ')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <AssetDrawer assetId={sel} onClose={() => setSel(null)} scenario={scenario} horizon={horizon} />
    </div>
  )
}

function Th({ children, onClick, right, center }) {
  return (
    <th className={`px-3 py-2.5 font-medium ${right ? 'text-right' : center ? 'text-center' : 'text-left'}`}>
      <button onClick={onClick} className="inline-flex items-center gap-1 hover:text-gray-600">
        {children} <ArrowUpDown size={11} className="opacity-40" />
      </button>
    </th>
  )
}
