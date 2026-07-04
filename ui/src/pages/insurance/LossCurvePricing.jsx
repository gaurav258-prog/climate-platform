import { useState, useEffect } from 'react'
import { Umbrella, TrendingUp, ShieldAlert, Layers } from 'lucide-react'
import ContextBar from '../../components/ContextBar'
import RiskAtom, { BUCKET } from '../../components/RiskAtom'
import { fetchInsuranceSummary } from '../../api/client'

const mn = n => '€' + (n / 1e6).toFixed(1) + 'm'
const ORDER = ['VH', 'H', 'M', 'L', 'none']

export default function LossCurvePricing() {
  const [scenario, setScenario] = useState('baseline')
  const [horizon, setHorizon] = useState('current')
  const [data, setData] = useState(null)

  useEffect(() => {
    setData(null)
    fetchInsuranceSummary({ scenario, horizon }).then(setData).catch(() => setData(null))
  }, [scenario, horizon])

  const r = data?.rollup
  const totalInsured = r ? Object.values(r.by_bucket).reduce((s, b) => s + b.sum_insured_eur, 0) : 0

  return (
    <div className="flex h-full flex-col bg-[#f5f5f7]">
      <ContextBar scenario={scenario} horizon={horizon} onScenario={setScenario} onHorizon={setHorizon}
        vintage="2024-10-29" label={`Insurance · ${data?.org?.name || 'Iberia Mutual (demo)'}`} />

      <div className="flex-1 overflow-y-auto px-8 py-8">
        <header className="mb-6">
          <div className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-[0.12em] text-gray-400">
            <Umbrella size={13} /> Loss-curve pricing
          </div>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight text-[#1d1d1f]">Expected loss and premium from the score</h1>
          <p className="mt-2 max-w-2xl text-[15px] text-gray-500">
            Same golden source as banking and agriculture, priced through underwriting's own lens: risk score →
            damage ratio → expected annual loss → premium, one auditable number per policy.
          </p>
        </header>

        {!r ? <p className="text-gray-400">loading…</p> : (
          <>
            <div className="mb-4 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-[12px] text-amber-800">
              <strong>v0 pricing — disclosed assumptions.</strong> Damage ratio uses an Emanuel(2011)/CLIMADA-style
              vulnerability curve; annual occurrence probability is a flat return-period tier per risk bucket
              (200/50/20/10 years for L/M/H/VH), not hazard-specific frequency data. Expense ratio 25%, profit
              margin 5% (CAS loss-cost-multiplier method).
            </div>

            <div className="grid grid-cols-4 gap-4">
              <Stat icon={Layers} label="Property book" value={mn(r.total_sum_insured_eur)} sub={`${r.n_policies} policies`} />
              <Stat icon={ShieldAlert} label="Expected annual loss" value={mn(r.total_expected_annual_loss_eur)}
                sub="pure premium, across the book" accent="#c2410c" />
              <Stat icon={TrendingUp} label="Gross premium" value={mn(r.total_gross_premium_eur)}
                sub={`${r.portfolio_loss_ratio_pct}% loss ratio`} accent="#0071e3" />
              <Stat icon={Umbrella} label="Priced coverage" value={`${Math.round(100 * r.n_priced / r.n_policies)}%`}
                sub={`${r.n_priced} in golden source`} />
            </div>

            <section className="mt-6 rounded-2xl border border-gray-200/70 bg-white p-5 shadow-sm">
              <h2 className="text-[13px] font-semibold text-[#1d1d1f]">Sum insured by risk band <span className="font-normal text-gray-400">— value-weighted</span></h2>
              <div className="mt-3 flex h-4 overflow-hidden rounded-full">
                {ORDER.map(k => {
                  const seg = r.by_bucket[k]
                  if (!seg || !seg.sum_insured_eur) return null
                  const pct = (seg.sum_insured_eur / totalInsured) * 100
                  return <div key={k} title={`${k}: ${mn(seg.sum_insured_eur)}`} style={{ width: `${pct}%`, background: k === 'none' ? '#e5e7eb' : BUCKET[k].c }} />
                })}
              </div>
              <div className="mt-3 flex flex-wrap gap-4 text-[11px]">
                {ORDER.map(k => r.by_bucket[k] && (
                  <span key={k} className="flex items-center gap-1.5 text-gray-500">
                    <span className="h-2 w-2 rounded-full" style={{ background: k === 'none' ? '#e5e7eb' : BUCKET[k].c }} />
                    {k === 'none' ? 'Unscored' : BUCKET[k].label} · {r.by_bucket[k].count} · {mn(r.by_bucket[k].sum_insured_eur)}
                    {k !== 'none' && ` · EAL ${mn(r.by_bucket[k].eal_eur)}`}
                  </span>
                ))}
              </div>
            </section>

            <section className="mt-6 rounded-2xl border border-gray-200/70 bg-white p-5 shadow-sm">
              <h2 className="text-[13px] font-semibold text-[#1d1d1f]">Most exposed policies</h2>
              <div className="mt-3 divide-y divide-gray-100">
                {r.top_policies.map(p => (
                  <div key={p.policy_id} className="flex w-full items-center justify-between py-2.5">
                    <div className="min-w-0">
                      <div className="truncate text-[13px] font-medium text-[#1d1d1f]">{p.policy_name}</div>
                      <div className="text-[11px] text-gray-400">
                        {p.region} · {p.country} · {mn(p.sum_insured_eur)} insured · {p.headline_hazard}
                        {p.pricing && ` · premium ${mn(p.pricing.gross_premium_eur)} (${p.pricing.rate_on_line_pct}% ROL)`}
                      </div>
                    </div>
                    <RiskAtom score={p.headline_score} bucket={p.headline_bucket} size="md" showLabel />
                  </div>
                ))}
              </div>
            </section>
          </>
        )}
      </div>
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
