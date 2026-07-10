import { useState, useEffect, useCallback, Fragment } from 'react'
import { FileText, Download, FileSpreadsheet, Waves, Flame, Mountain, Wind, CloudFog, ShieldCheck, Loader2, CheckCircle2, History, X, ChevronDown } from 'lucide-react'
import ContextBar from '../../components/ContextBar'
import RiskAtom, { BUCKET } from '../../components/RiskAtom'
import AssetDrawer from '../../components/AssetDrawer'
import { fetchDisclosure, fetchPortfolio, downloadFile, createSubmission, fetchSubmissions, fetchSubmission } from '../../api/client'

const mn = n => '€' + (n / 1e6).toFixed(1) + 'm'
const bn = n => '€' + (n / 1e9).toFixed(2) + 'bn'
const num = n => Math.round(n).toLocaleString()
const HAZ_ICON = { flood: Waves, wildfire: Flame, volcanic: Mountain, storm: Wind, pollution: CloudFog }
const TAX = [['aligned', 'Aligned', '#34c759'], ['eligible', 'Eligible', '#ff9500'],
  ['not_eligible', 'Not eligible', '#86868b'], ['not_assessed', 'Not assessed', '#d1d5db']]
const STATUS_BADGE = {
  draft: 'bg-gray-100 text-gray-500', pending: 'bg-amber-50 text-amber-700',
  released: 'bg-emerald-50 text-emerald-700', rejected: 'bg-red-50 text-red-700',
}

function exportCsv(assets) {
  const head = ['asset_name', 'sector', 'country', 'value_eur', 'headline_score', 'risk_bucket', 'taxonomy_status', 'h3_cell',
    'recommended_discount_pct', 'effective_discount_pct', 'discounted_value_eur', 'overridden']
  const rows = [head, ...assets.map(a => [
    a.asset_name, a.sector, a.country, a.value_eur, a.headline_score ?? '',
    a.headline_bucket ?? 'unscored', a.taxonomy_status ?? '', a.h3_cell,
    a.valuation?.recommended_discount_pct ?? '', a.valuation?.effective_discount_pct ?? '',
    a.valuation?.discounted_value_eur ?? '', a.valuation?.is_overridden ? 'yes' : 'no',
  ])]
  const csv = rows.map(r => r.map(x => `"${String(x ?? '').replace(/"/g, '""')}"`).join(',')).join('\n')
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }))
  const link = document.createElement('a')
  link.href = url; link.download = 'meridian-physical-risk-disclosure.csv'; link.click()
  URL.revokeObjectURL(url)
}

/** Quarter bounds, UTC so period_start/period_end don't drift with the viewer's timezone. */
function quarterBounds(year, q) {
  const startMonth = (q - 1) * 3
  const start = new Date(Date.UTC(year, startMonth, 1))
  const end = new Date(Date.UTC(year, startMonth + 3, 0))
  return { period_start: start.toISOString().slice(0, 10), period_end: end.toISOString().slice(0, 10) }
}

/** Current quarter + the 3 before it — enough choice for a real reporting cadence
 * without a free-text date picker that would let dates fall outside a quarter. */
function recentQuarters(n = 4) {
  const now = new Date()
  let y = now.getUTCFullYear(), q = Math.floor(now.getUTCMonth() / 3) + 1
  const list = []
  for (let i = 0; i < n; i++) {
    list.push({ label: `Q${q} ${y}`, ...quarterBounds(y, q) })
    q -= 1; if (q === 0) { q = 4; y -= 1 }
  }
  return list
}

/** The disclosure body — reused for the LIVE view and for a frozen historical
 * submission's snapshot, so a past period renders through the exact same code
 * a bank sees today. */
export function DisclosureSummary({ d, assets, onSelectAsset }) {
  const r = d.rollup
  const taxTotal = Object.values(d.taxonomy).reduce((s, t) => s + t.value_eur, 0)
  const [openHazard, setOpenHazard] = useState(null)
  const drillable = Boolean(assets)   // live view only -- a frozen snapshot has no per-asset list
  return (
    <div className="space-y-5">
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
              const open = openHazard === h
              const topAssets = open && drillable
                ? assets.filter(a => a.hazards?.some(hz => hz.hazard === h && (hz.bucket === 'H' || hz.bucket === 'VH')))
                    .sort((x, y) => (y.hazards.find(hz => hz.hazard === h)?.score || 0) - (x.hazards.find(hz => hz.hazard === h)?.score || 0))
                    .slice(0, 8)
                : []
              return (
                <Fragment key={h}>
                  <tr className={`border-b border-gray-50 last:border-0 ${drillable ? 'cursor-pointer hover:bg-gray-50' : ''}`}
                    onClick={() => drillable && setOpenHazard(open ? null : h)}>
                    <td className="py-2.5">
                      <span className="flex items-center gap-2 capitalize text-[#1d1d1f]">
                        <Icon size={15} className="text-gray-400" /> {h}
                        {drillable && <ChevronDown size={12} className={`text-gray-300 transition ${open ? 'rotate-180' : ''}`} />}
                      </span>
                    </td>
                    <td className="py-2.5 text-right font-medium tabular-nums">{mn(v.exposed_value_eur)}</td>
                    <td className="py-2.5 text-center text-gray-600">{v.n_exposed}</td>
                    <td className="py-2.5 text-center"><RiskAtom score={v.max_score} bucket={v.max_score >= 75 ? 'VH' : v.max_score >= 50 ? 'H' : v.max_score >= 25 ? 'M' : 'L'} size="sm" /></td>
                    <td className="py-2.5 font-mono text-[10px] text-gray-400">{v.model_version} · {String(v.scored_at).slice(0, 10)}</td>
                  </tr>
                  {open && drillable && (
                    <tr>
                      <td colSpan={5} className="bg-[#f5f5f7] px-3 py-2">
                        {topAssets.length ? (
                          <div className="divide-y divide-gray-200/70">
                            {topAssets.map(a => (
                              <button key={a.asset_id} onClick={e => { e.stopPropagation(); onSelectAsset(a.asset_id) }}
                                className="flex w-full items-center justify-between py-1.5 text-left hover:opacity-70">
                                <span className="text-[12px] text-[#1d1d1f]">{a.asset_name} <span className="text-gray-400">· {a.sector}</span></span>
                                <span className="text-[11px] font-medium text-gray-500">
                                  {a.hazards.find(hz => hz.hazard === h)?.score?.toFixed(1)}
                                </span>
                              </button>
                            ))}
                          </div>
                        ) : <p className="py-1.5 text-[12px] text-gray-400">No High+ assets for this hazard.</p>}
                      </td>
                    </tr>
                  )}
                </Fragment>
              )
            })}
          </tbody>
        </table>
      </section>

      <div className="grid grid-cols-2 gap-5">
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
  )
}

export default function Reports({ auth }) {
  const [scenario, setScenario] = useState('baseline')
  const [horizon, setHorizon] = useState('current')
  const [d, setD] = useState(null)
  const [assets, setAssets] = useState([])
  const [publish, setPublish] = useState({ state: 'idle' })   // idle | submitting | submitted | error
  const [quarters] = useState(() => recentQuarters())
  const [periodIdx, setPeriodIdx] = useState(0)
  const [submissions, setSubmissions] = useState([])
  const [viewing, setViewing] = useState(null)   // { loading } | { submission } | null
  const [selAsset, setSelAsset] = useState(null)

  useEffect(() => {
    setD(null)
    fetchDisclosure({ scenario, horizon }).then(setD).catch(() => setD(null))
    fetchPortfolio({ scenario, horizon }).then(x => setAssets(x.assets || [])).catch(() => {})
  }, [scenario, horizon])

  const loadSubmissions = useCallback(() => {
    fetchSubmissions().then(setSubmissions).catch(() => setSubmissions([]))
  }, [])
  useEffect(() => { loadSubmissions() }, [loadSubmissions])

  const r = d?.rollup

  const canSubmit = new Set(auth?.permissions || []).has('reports.publish')
  async function submitForApproval() {
    setPublish({ state: 'submitting' })
    try {
      const period = quarters[periodIdx]
      await createSubmission({
        framework: 'TCFD_EU_TAXONOMY', period_label: period.label,
        period_start: period.period_start, period_end: period.period_end,
        scenario, horizon,
      })
      setPublish({ state: 'submitted' })
      loadSubmissions()
    } catch (e) {
      setPublish({ state: 'error', msg: e.message || 'Could not submit for approval.' })
    }
  }

  async function openSubmission(id) {
    setViewing({ loading: true })
    try {
      const full = await fetchSubmission(id)
      setViewing({ submission: full })
    } catch (e) {
      setViewing(null)
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
              <select value={periodIdx} onChange={e => setPeriodIdx(Number(e.target.value))}
                className="rounded-full border border-gray-200 bg-white px-3 py-2 text-[13px] font-medium text-[#1d1d1f]">
                {quarters.map((q, i) => <option key={q.label} value={i}>{q.label}</option>)}
              </select>
            )}
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
                    : <><ShieldCheck size={15} /> Submit for approval</>}
                </button>
              )
            )}
            <button onClick={() => downloadFile(`/v1/bank/disclosure.xlsx?scenario=${scenario}&horizon=${horizon}`, 'meridian-physical-risk-disclosure.xlsx')}
              className="flex items-center gap-2 rounded-full bg-[#0071e3] px-4 py-2 text-[13px] font-medium text-white hover:bg-[#0077ed]">
              <FileSpreadsheet size={15} /> Export Excel
            </button>
            <button onClick={() => exportCsv(assets)}
              className="flex items-center gap-2 rounded-full border border-gray-200 bg-white px-4 py-2 text-[13px] font-medium text-[#1d1d1f] hover:border-gray-300">
              <Download size={15} /> Export CSV
            </button>
          </div>
        </header>
        {publish.state === 'submitted' && (
          <p className="mb-4 rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-[13px] text-emerald-800">
            Sent to the four-eyes queue for <b>{quarters[periodIdx].label}</b>. A different user with approval rights
            must sign off in <b>Admin › Approvals</b> before it's released.
          </p>
        )}
        {publish.state === 'error' && (
          <p className="mb-4 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-[13px] text-red-700">{publish.msg}</p>
        )}

        {!d ? <p className="text-gray-400">loading…</p> : <DisclosureSummary d={d} assets={assets} onSelectAsset={setSelAsset} />}

        <section className="mt-5 rounded-2xl border border-gray-200/70 bg-white p-5 shadow-sm">
          <h2 className="flex items-center gap-2 text-[14px] font-semibold text-[#1d1d1f]">
            <History size={15} className="text-gray-400" /> Submission history
          </h2>
          <p className="mt-1 text-[13px] text-gray-500">Every disclosure ever prepared for a reporting period — drafts, releases and rejections all persist.</p>
          {submissions.length === 0 ? (
            <p className="mt-3 text-[13px] text-gray-400">No submissions yet.</p>
          ) : (
            <table className="mt-3 w-full text-[13px]">
              <thead><tr className="border-b border-gray-200 text-left text-[11px] uppercase tracking-wide text-gray-400">
                <th className="py-2 font-medium">Period</th><th className="py-2 font-medium">Framework</th>
                <th className="py-2 font-medium">Status</th><th className="py-2 font-medium">Maker</th>
                <th className="py-2 font-medium">Checker</th><th className="py-2 font-medium">Created</th>
              </tr></thead>
              <tbody>
                {submissions.map(s => (
                  <tr key={s.id} onClick={() => openSubmission(s.id)}
                    className="cursor-pointer border-b border-gray-50 last:border-0 hover:bg-gray-50">
                    <td className="py-2.5 font-medium text-[#1d1d1f]">{s.period_label}</td>
                    <td className="py-2.5 text-gray-500">{s.framework}</td>
                    <td className="py-2.5"><span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${STATUS_BADGE[s.status]}`}>{s.status}</span></td>
                    <td className="py-2.5 text-gray-500">{s.maker_email || '—'}</td>
                    <td className="py-2.5 text-gray-500">{s.checker_email || '—'}</td>
                    <td className="py-2.5 text-gray-400">{s.created_at ? new Date(s.created_at).toLocaleDateString() : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      </div>

      {viewing && (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/30 p-8" onClick={() => setViewing(null)}>
          <div className="max-h-full w-full max-w-3xl overflow-y-auto rounded-2xl bg-[#f5f5f7] p-6" onClick={e => e.stopPropagation()}>
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-lg font-semibold text-[#1d1d1f]">
                {viewing.submission ? `${viewing.submission.period_label} — frozen snapshot` : 'Loading…'}
              </h2>
              <button onClick={() => setViewing(null)} className="rounded-full p-1.5 hover:bg-gray-200"><X size={18} /></button>
            </div>
            {viewing.loading ? <p className="text-gray-400">loading…</p> : <DisclosureSummary d={viewing.submission.snapshot} />}
          </div>
        </div>
      )}

      <AssetDrawer assetId={selAsset} onClose={() => setSelAsset(null)} scenario={scenario} horizon={horizon} auth={auth} />
    </div>
  )
}
