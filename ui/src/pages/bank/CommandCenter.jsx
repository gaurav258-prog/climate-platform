import { useState, useEffect } from 'react'
import { Building2, TrendingUp, ShieldAlert, Layers } from 'lucide-react'
import ContextBar from '../../components/ContextBar'
import RiskAtom, { BUCKET } from '../../components/RiskAtom'
import AssetDrawer from '../../components/AssetDrawer'
import { fetchBankSummary } from '../../api/client'

const bn = n => '€' + (n / 1e9).toFixed(2) + 'bn'
const mn = n => '€' + (n / 1e6).toFixed(0) + 'm'
const ORDER = ['VH', 'H', 'M', 'L', 'none']

export default function CommandCenter({ onGoto }) {
  const [scenario, setScenario] = useState('baseline')
  const [horizon, setHorizon] = useState('current')
  const [data, setData] = useState(null)
  const [sel, setSel] = useState(null)

  useEffect(() => {
    setData(null)
    fetchBankSummary({ scenario, horizon }).then(setData).catch(() => setData(null))
  }, [scenario, horizon])

  const r = data?.rollup
  const totalVal = r ? Object.values(r.by_bucket).reduce((s, b) => s + b.value_eur, 0) : 0

  return (
    <div className="flex h-full flex-col bg-[#f5f5f7]">
      <ContextBar scenario={scenario} horizon={horizon} onScenario={setScenario} onHorizon={setHorizon}
        vintage="2024-10-29" label={`Banking · ${data?.org?.name || 'Meridian Bank (demo)'}`} />

      <div className="flex-1 overflow-y-auto px-8 py-8">
        <header className="mb-6">
          <div className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-[0.12em] text-gray-400">
            <Building2 size={13} /> Command Center
          </div>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight text-[#1d1d1f]">Your loan book, right now</h1>
          <p className="mt-2 max-w-2xl text-[15px] text-gray-500">
            Every asset's physical-climate risk projected live from the golden source — one number per location,
            traceable to a model version and data vintage.
          </p>
        </header>

        {!r ? <p className="text-gray-400">loading…</p> : (
          <>
            {/* headline stats */}
            <div className="grid grid-cols-4 gap-4">
              <Stat icon={Layers} label="Loan book" value={bn(r.total_value_eur)} sub={`${r.n_assets} assets`} />
              <Stat icon={ShieldAlert} label="Value at risk (High+)" value={mn(r.value_at_risk_eur)}
                sub={`${r.pct_value_at_risk}% of book`} accent="#c2410c" />
              <Stat icon={TrendingUp} label="High-risk assets" value={r.n_high} sub={`of ${r.n_assets}`} accent="#c81e1e" />
              <Stat icon={Building2} label="Scored coverage" value={`${Math.round(100 * r.n_scored / r.n_assets)}%`}
                sub={`${r.n_scored} in golden source`} />
            </div>

            {/* exposure distribution (value-weighted) */}
            <section className="mt-6 rounded-2xl border border-gray-200/70 bg-white p-5 shadow-sm">
              <h2 className="text-[13px] font-semibold text-[#1d1d1f]">Exposure by risk band <span className="font-normal text-gray-400">— value-weighted</span></h2>
              <div className="mt-3 flex h-4 overflow-hidden rounded-full">
                {ORDER.map(k => {
                  const seg = r.by_bucket[k]
                  if (!seg || !seg.value_eur) return null
                  const pct = (seg.value_eur / totalVal) * 100
                  return <div key={k} title={`${k}: ${mn(seg.value_eur)}`} style={{ width: `${pct}%`, background: k === 'none' ? '#e5e7eb' : BUCKET[k].c }} />
                })}
              </div>
              <div className="mt-3 flex flex-wrap gap-4 text-[11px]">
                {ORDER.map(k => r.by_bucket[k] && (
                  <span key={k} className="flex items-center gap-1.5 text-gray-500">
                    <span className="h-2 w-2 rounded-full" style={{ background: k === 'none' ? '#e5e7eb' : BUCKET[k].c }} />
                    {k === 'none' ? 'Unscored' : BUCKET[k].label} · {r.by_bucket[k].count} · {mn(r.by_bucket[k].value_eur)}
                  </span>
                ))}
              </div>
            </section>

            {/* most exposed assets */}
            <section className="mt-6 rounded-2xl border border-gray-200/70 bg-white p-5 shadow-sm">
              <div className="flex items-center justify-between">
                <h2 className="text-[13px] font-semibold text-[#1d1d1f]">Most exposed assets</h2>
                <button onClick={() => onGoto?.('bank-portfolio')} className="text-[12px] font-medium text-[#0071e3] hover:underline">
                  View full portfolio →
                </button>
              </div>
              <div className="mt-3 divide-y divide-gray-100">
                {r.top_assets.map(a => (
                  <button key={a.asset_id} onClick={() => setSel(a.asset_id)}
                    className="flex w-full items-center justify-between py-2.5 text-left hover:bg-gray-50">
                    <div className="min-w-0">
                      <div className="truncate text-[13px] font-medium text-[#1d1d1f]">{a.asset_name}</div>
                      <div className="text-[11px] text-gray-400">{a.sector} · {a.country} · {mn(a.value_eur)} · {a.headline_hazard}</div>
                    </div>
                    <RiskAtom score={a.headline_score} bucket={a.headline_bucket} size="md" showLabel />
                  </button>
                ))}
              </div>
            </section>
          </>
        )}
      </div>

      <AssetDrawer assetId={sel} onClose={() => setSel(null)} />
    </div>
  )
}

function Stat({ icon: Icon, label, value, sub, accent }) {
  return (
    <div className="rounded-2xl border border-gray-200/70 bg-white p-4 shadow-sm">
      <div className="flex items-center gap-1.5 text-[11px] uppercase tracking-wide text-gray-400"><Icon size={13} /> {label}</div>
      <div className="mt-1.5 text-2xl font-semibold tracking-tight" style={{ color: accent || '#1d1d1f' }}>{value}</div>
      <div className="text-[11px] text-gray-400">{sub}</div>
    </div>
  )
}
