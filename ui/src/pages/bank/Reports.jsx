import { useState, useEffect } from 'react'
import { FileText, Download, Waves, Flame, ShieldCheck, Loader2, CheckCircle2 } from 'lucide-react'
import ContextBar from '../../components/ContextBar'
import RiskAtom, { BUCKET } from '../../components/RiskAtom'
import { fetchDisclosure, fetchPortfolio, createApproval } from '../../api/client'

const mn = n => '€' + (n / 1e6).toFixed(1) + 'm'
const bn = n => '€' + (n / 1e9).toFixed(2) + 'bn'
const num = n => Math.round(n).toLocaleString()
const HAZ_ICON = { flood: Waves, wildfire: Flame }
const TAX = [['aligned', 'Aligned', '#34c759'], ['eligible', 'Eligible', '#ff9500'], ['not_eligible', 'Not eligible', '#86868b']]

function exportCsv(assets) {
  const head = ['asset_name', 'sector', 'country', 'value_eur', 'headline_score', 'risk_bucket', 'taxonomy_status', 'h3_cell']
  const rows = [head, ...assets.map(a => [
    a.asset_name, a.sector, a.country, a.value_eur, a.headline_score ?? '',
    a.headline_bucket ?? 'unscored', a.taxonomy_status ?? '', a.h3_cell,
  ])]
  const csv = rows.map(r => r.map(x => `"${String(x ?? '').replace(/"/g, '""')}"`).join(',')).join('\n')
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }))
  const link = document.createElement('a')
  link.href = url; link.download = 'meridian-physical-risk-disclosure.csv'; link.click()
  URL.revokeObjectURL(url)
}

export default function Reports({ auth }) {
  const [scenario, setScenario] = useState('baseline')
  const [horizon, setHorizon] = useState('current')
  const [d, setD] = useState(null)
  const [assets, setAssets] = useState([])
  const [publish, setPublish] = useState({ state: 'idle' })   // idle | submitting | submitted | error

  useEffect(() => {
    setD(null)
    fetchDisclosure({ scenario, horizon }).then(setD).catch(() => setD(null))
    fetchPortfolio({ scenario, horizon }).then(x => setAssets(x.assets || [])).catch(() => {})
  }, [scenario, horizon])

  const r = d?.rollup
  const taxTotal = d ? Object.values(d.taxonomy).reduce((s, t) => s + t.value_eur, 0) : 0

  const canSubmit = new Set(auth?.permissions || []).has('approvals.create')
  async function submitForApproval() {
    setPublish({ state: 'submitting' })
    try {
      await createApproval({
        request_type: 'report.publish',
        title: `Publish disclosure — ${scenario} / ${horizon}`,
        payload: { scenario, horizon, value_at_risk_eur: r?.value_at_risk_eur, n_assets: r?.n_assets },
      })
      setPublish({ state: 'submitted' })
    } catch (e) {
      setPublish({ state: 'error', msg: e.message || 'Could not submit for approval.' })
    }
  }

  return (
    <div className="flex h-full flex-col bg-[#f5f5f7]">
      <ContextBar scenario={scenario} horizon={horizon} onScenario={setScenario} onHorizon={setHorizon}
        vintage="2024-10-29" label="Banking · Reports & Actions" />
      <div className="flex-1 overflow-y-auto px-8 py-8">
        <header className="mb-6 flex items-end justify-between">
          <div>
            <div className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-[0.12em] text-gray-400">
              <FileText size={13} /> Reports & Actions
            </div>
            <h1 className="mt-2 text-3xl font-semibold tracking-tight text-[#1d1d1f]">Climate risk disclosure</h1>
            <p className="mt-2 max-w-2xl text-[15px] text-gray-500">
              TCFD physical risk &amp; EU-Taxonomy alignment, built straight from the projected book — every figure
              traces to a model version and data vintage.
            </p>
          </div>
          <div className="flex items-center gap-2">
            {canSubmit && (
              publish.state === 'submitted' ? (
                <span className="flex items-center gap-1.5 rounded-full bg-emerald-50 px-4 py-2 text-[13px] font-medium text-emerald-700">
                  <CheckCircle2 size={15} /> Submitted — awaiting approver
                </span>
              ) : (
                <button onClick={submitForApproval} disabled={publish.state === 'submitting' || !d}
                  className="flex items-center gap-2 rounded-full border border-gray-200 bg-white px-4 py-2 text-[13px] font-medium text-[#1d1d1f] hover:border-gray-300 disabled:opacity-50">
                  {publish.state === 'submitting'
                    ? <><Loader2 size={15} className="animate-spin" /> Submitting…</>
                    : <><ShieldCheck size={15} /> Publish disclosure</>}
                </button>
              )
            )}
            <button onClick={() => exportCsv(assets)}
              className="flex items-center gap-2 rounded-full bg-[#0071e3] px-4 py-2 text-[13px] font-medium text-white hover:bg-[#0077ed]">
              <Download size={15} /> Export disclosure
            </button>
          </div>
        </header>
        {publish.state === 'submitted' && (
          <p className="mb-4 rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-[13px] text-emerald-800">
            Sent to the four-eyes queue. A different user with approval rights must sign off in <b>Admin › Approvals</b> before it’s published.
          </p>
        )}
        {publish.state === 'error' && (
          <p className="mb-4 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-[13px] text-red-700">{publish.msg}</p>
        )}

        {!d ? <p className="text-gray-400">loading…</p> : (
          <div className="space-y-5">
            {/* TCFD physical risk */}
            <section className="rounded-2xl border border-gray-200/70 bg-white p-5 shadow-sm">
              <h2 className="text-[14px] font-semibold text-[#1d1d1f]">Physical risk <span className="font-normal text-gray-400">— TCFD / IFRS S2</span></h2>
              <p className="mt-1 text-[13px] text-gray-500">{bn(r.total_value_eur)} book · <span className="font-medium text-[#c2410c]">{mn(r.value_at_risk_eur)} ({r.pct_value_at_risk}%) exposed at High+ physical risk</span></p>
              <table className="mt-3 w-full text-[13px]">
                <thead><tr className="border-b border-gray-200 text-left text-[11px] uppercase tracking-wide text-gray-400">
                  <th className="py-2 font-medium">Hazard</th><th className="py-2 text-right font-medium">Value at risk (H+)</th>
                  <th className="py-2 text-center font-medium">Assets</th><th className="py-2 text-center font-medium">Peak</th>
                  <th className="py-2 font-medium">Model · vintage</th>
                </tr></thead>
                <tbody>
                  {Object.entries(d.by_hazard).map(([h, v]) => {
                    const Icon = HAZ_ICON[h] || Waves
                    return (
                      <tr key={h} className="border-b border-gray-50 last:border-0">
                        <td className="py-2.5"><span className="flex items-center gap-2 capitalize text-[#1d1d1f]"><Icon size={15} className="text-gray-400" /> {h}</span></td>
                        <td className="py-2.5 text-right font-medium tabular-nums">{mn(v.exposed_value_eur)}</td>
                        <td className="py-2.5 text-center text-gray-600">{v.n_exposed}</td>
                        <td className="py-2.5 text-center"><RiskAtom score={v.max_score} bucket={v.max_score >= 75 ? 'VH' : v.max_score >= 50 ? 'H' : v.max_score >= 25 ? 'M' : 'L'} size="sm" /></td>
                        <td className="py-2.5 font-mono text-[10px] text-gray-400">{v.model_version} · {String(v.scored_at).slice(0, 10)}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </section>

            <div className="grid grid-cols-2 gap-5">
              {/* EU Taxonomy */}
              <section className="rounded-2xl border border-gray-200/70 bg-white p-5 shadow-sm">
                <h2 className="text-[14px] font-semibold text-[#1d1d1f]">EU Taxonomy <span className="font-normal text-gray-400">— Article 8, value-weighted</span></h2>
                <div className="mt-3 flex h-4 overflow-hidden rounded-full">
                  {TAX.map(([k, , c]) => d.taxonomy[k] && <div key={k} title={`${k}: ${mn(d.taxonomy[k].value_eur)}`} style={{ width: `${(d.taxonomy[k].value_eur / taxTotal) * 100}%`, background: c }} />)}
                </div>
                <div className="mt-3 space-y-1.5">
                  {TAX.map(([k, label, c]) => d.taxonomy[k] && (
                    <div key={k} className="flex items-center justify-between text-[12px]">
                      <span className="flex items-center gap-2 text-gray-600"><span className="h-2 w-2 rounded-full" style={{ background: c }} /> {label}</span>
                      <span className="tabular-nums text-gray-500">{d.taxonomy[k].count} assets · {mn(d.taxonomy[k].value_eur)}</span>
                    </div>
                  ))}
                </div>
              </section>

              {/* Financed emissions */}
              <section className="rounded-2xl border border-gray-200/70 bg-white p-5 shadow-sm">
                <h2 className="text-[14px] font-semibold text-[#1d1d1f]">Financed emissions <span className="font-normal text-gray-400">— tCO₂e (PCAF)</span></h2>
                <div className="mt-3 grid grid-cols-3 gap-3">
                  {[['Scope 1', 'scope1'], ['Scope 2', 'scope2'], ['Scope 3', 'scope3']].map(([label, k]) => (
                    <div key={k} className="rounded-xl bg-[#f5f5f7] px-3 py-3 text-center">
                      <div className="text-lg font-semibold tabular-nums text-[#1d1d1f]">{num(d.financed_emissions_tco2e[k])}</div>
                      <div className="text-[10px] uppercase tracking-wide text-gray-400">{label}</div>
                    </div>
                  ))}
                </div>
                <p className="mt-3 text-[11px] text-gray-400">Aggregated across {r.n_assets} financed assets.</p>
              </section>
            </div>

            <p className="rounded-2xl border border-gray-200 px-4 py-3 text-[11px] text-gray-500">
              Every figure is projected from <span className="font-mono">canonical_scores</span> by H3 cell — never a
              stored or uploaded value — and carries the model version + data vintage shown, so the disclosure is
              auditable end to end. Maps to TCFD, IFRS S2, EU Taxonomy (Art. 8) and PCAF.
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
