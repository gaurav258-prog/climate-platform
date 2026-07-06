import { useState, useEffect, useCallback } from 'react'
import { TrendingUp, ShieldAlert, Layers, Flag, Download, FileSpreadsheet, Leaf } from 'lucide-react'
import ContextBar from '../../components/ContextBar'
import RiskAtom, { BUCKET } from '../../components/RiskAtom'
import UploadPanel from '../../components/UploadPanel'
import {
  fetchAssetMgmtSummary, fetchAssetMgmtPortfolio, fetchAssetMgmtDisclosure,
  uploadAssetMgmtHoldings, downloadFile,
} from '../../api/client'

const mn = n => n == null ? '—' : '€' + (n / 1e6).toFixed(1) + 'm'
const ORDER = ['VH', 'H', 'M', 'L', 'none']
const HAZ_LABEL = { flood: 'Flood', wildfire: 'Wildfire', volcanic: 'Volcanic', storm: 'Storm', heat_acute: 'Heat', drought: 'Drought' }
const TAX_LABEL = { eligible: 'Eligible', not_eligible: 'Not eligible', not_assessed: 'Not assessed' }
const TAX_COLOR = { eligible: '#ff9500', not_eligible: '#86868b', not_assessed: '#d1d5db' }
const TEMPLATE_COLUMNS = ['holding_name', 'latitude', 'longitude', 'position_value_eur', 'sector', 'nace_code', 'region', 'country']

function exportCsv(holdings) {
  const head = ['holding_name', 'sector', 'region', 'country', 'position_value_eur',
    'headline_hazard', 'headline_score', 'risk_bucket', 'discounted_value_eur', 'flagged', 'taxonomy_status']
  const rows = [head, ...holdings.map(h => [
    h.holding_name, h.sector, h.region, h.country, h.position_value_eur,
    h.headline_hazard ?? '', h.headline_score ?? '', h.headline_bucket ?? 'unscored',
    h.climate_var?.discounted_value_eur ?? '', h.flagged ? 'yes' : 'no', h.taxonomy_status,
  ])]
  const csv = rows.map(r => r.map(x => `"${String(x ?? '').replace(/"/g, '""')}"`).join(',')).join('\n')
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }))
  const link = document.createElement('a')
  link.href = url; link.download = 'nordkap-portfolio-climate-var.csv'; link.click()
  URL.revokeObjectURL(url)
}

export default function PortfolioVaR() {
  const [scenario, setScenario] = useState('baseline')
  const [horizon, setHorizon] = useState('current')
  const [data, setData] = useState(null)
  const [holdings, setHoldings] = useState([])
  const [disclosure, setDisclosure] = useState(null)

  const reload = useCallback(() => {
    fetchAssetMgmtSummary({ scenario, horizon }).then(setData).catch(() => setData(null))
    fetchAssetMgmtPortfolio({ scenario, horizon }).then(x => setHoldings(x.holdings || [])).catch(() => {})
    fetchAssetMgmtDisclosure({ scenario, horizon }).then(setDisclosure).catch(() => setDisclosure(null))
  }, [scenario, horizon])
  useEffect(() => { setData(null); reload() }, [reload])

  const r = data?.rollup
  const totalValue = r ? Object.values(r.by_bucket).reduce((s, b) => s + b.value_eur, 0) : 0
  const taxTotal = disclosure ? Object.values(disclosure.taxonomy).reduce((s, t) => s + t.value_eur, 0) : 0

  return (
    <div className="flex h-full flex-col bg-[#f5f5f7]">
      <ContextBar scenario={scenario} horizon={horizon} onScenario={setScenario} onHorizon={setHorizon}
        vintage="2024-10-29" label={`Asset management · ${data?.org?.name || 'Nordkap Asset Management (demo)'}`} />

      <div className="flex-1 overflow-y-auto px-8 py-8">
        <header className="mb-6 flex items-end justify-between gap-4">
          <div>
            <div className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-[0.12em] text-gray-400">
              <TrendingUp size={13} /> Portfolio climate VaR
            </div>
            <h1 className="mt-2 text-3xl font-semibold tracking-tight text-[#1d1d1f]">Value-weighted climate risk, across the book</h1>
            <p className="mt-2 max-w-2xl text-[15px] text-gray-500">
              Same golden source as banking and real estate: risk score → the platform's existing
              risk-bucket discount schedule, applied to a holding's position value and reported as
              a portfolio-level climate exposure.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={() => downloadFile(`/v1/assetmgmt/portfolio.xlsx?scenario=${scenario}&horizon=${horizon}`, 'nordkap-portfolio-climate-var.xlsx')}
              className="flex items-center gap-2 rounded-full bg-[#0071e3] px-4 py-2 text-[13px] font-medium text-white hover:bg-[#0077ed]">
              <FileSpreadsheet size={15} /> Export Excel
            </button>
            <button onClick={() => exportCsv(holdings)}
              className="flex items-center gap-2 rounded-full border border-gray-200 bg-white px-4 py-2 text-[13px] font-medium text-[#1d1d1f] hover:border-gray-300">
              <Download size={15} /> Export CSV
            </button>
            <UploadPanel uploadFn={uploadAssetMgmtHoldings} templateColumns={TEMPLATE_COLUMNS}
              templateFilename="assetmgmt_holdings_template.csv"
              templateXlsxUrl="/v1/assetmgmt/holdings/template.xlsx" templateXlsxFilename="tellumen_holdings_template.xlsx"
              label="Import holdings" onUploaded={reload} />
          </div>
        </header>

        {!r ? <p className="text-gray-400">loading…</p> : (
          <>
            <div className="mb-4 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-[12px] text-amber-800">
              <strong>Climate VaR — disclosed methodology.</strong> "Climate VaR%" reuses the exact
              same risk-bucket discount schedule (0/5/15/30% by Low/Moderate/High/Very High) used
              for banking's collateral haircut and real estate's climate-adjusted value — not a
              statistically modeled Value-at-Risk with a defined confidence interval. See Trust &amp;
              assurance › Methodology for the full disclosure.
            </div>

            <div className="grid grid-cols-4 gap-4">
              <Stat icon={Layers} label="Portfolio value" value={mn(r.total_portfolio_value_eur)} sub={`${r.n_holdings} holdings`} />
              <Stat icon={ShieldAlert} label="Climate VaR" value={mn(r.total_climate_var_eur)}
                sub={`${r.portfolio_climate_var_pct}% of portfolio`} accent="#c2410c" />
              <Stat icon={Flag} label="Flagged (High+)" value={r.n_flagged} sub="holdings above the screen" accent="#c2410c" />
              <Stat icon={TrendingUp} label="Scored coverage" value={`${Math.round(100 * r.n_scored / r.n_holdings)}%`}
                sub={`${r.n_scored} in golden source`} />
            </div>

            <section className="mt-6 rounded-2xl border border-gray-200/70 bg-white p-5 shadow-sm">
              <h2 className="text-[13px] font-semibold text-[#1d1d1f]">Portfolio value by risk band <span className="font-normal text-gray-400">— value-weighted</span></h2>
              <div className="mt-3 flex h-4 overflow-hidden rounded-full">
                {ORDER.map(k => {
                  const seg = r.by_bucket[k]
                  if (!seg || !seg.value_eur) return null
                  const pct = (seg.value_eur / totalValue) * 100
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

            <section className="mt-6 rounded-2xl border border-gray-200/70 bg-white p-5 shadow-sm">
              <h2 className="text-[13px] font-semibold text-[#1d1d1f]">Most exposed holdings</h2>
              <div className="mt-3 divide-y divide-gray-100">
                {r.top_holdings.map(h => (
                  <div key={h.holding_id} className="flex w-full items-center justify-between py-2.5">
                    <div className="min-w-0">
                      <div className="flex items-center gap-1.5 truncate text-[13px] font-medium text-[#1d1d1f]">
                        {h.holding_name}
                        {h.flagged && <span className="rounded-full bg-red-50 px-1.5 py-0.5 text-[10px] font-semibold text-red-600">FLAGGED</span>}
                      </div>
                      <div className="text-[11px] text-gray-400">
                        {h.sector} · {h.region} · {h.country} · {mn(h.position_value_eur)} position · {h.headline_hazard}
                      </div>
                    </div>
                    <RiskAtom score={h.headline_score} bucket={h.headline_bucket} size="md" showLabel />
                  </div>
                ))}
              </div>
            </section>

            {disclosure && (
              <div className="mt-6 grid grid-cols-2 gap-5">
                <section className="rounded-2xl border border-gray-200/70 bg-white p-5 shadow-sm">
                  <h2 className="text-[13px] font-semibold text-[#1d1d1f]">Physical risk exposure <span className="font-normal text-gray-400">— by hazard</span></h2>
                  <table className="mt-3 w-full text-[12px]">
                    <thead><tr className="border-b border-gray-200 text-left text-[10px] uppercase tracking-wide text-gray-400">
                      <th className="py-1.5 font-medium">Hazard</th><th className="py-1.5 text-right font-medium">Exposed (H+)</th>
                      <th className="py-1.5 text-center font-medium">Holdings</th>
                    </tr></thead>
                    <tbody>
                      {Object.entries(disclosure.by_hazard).map(([h, v]) => (
                        <tr key={h} className="border-b border-gray-50 last:border-0">
                          <td className="py-2 text-[#1d1d1f]">{HAZ_LABEL[h] || h}</td>
                          <td className="py-2 text-right font-medium tabular-nums">{mn(v.exposed_value_eur)}</td>
                          <td className="py-2 text-center text-gray-500">{v.n_exposed}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <p className="mt-3 text-[10px] text-gray-400">
                    Value-weighted portfolio physical-risk exposure — the metric TCFD's asset-owner/
                    manager guidance recommends disclosing. Not framed as an SFDR Principal Adverse
                    Impact indicator: SFDR's mandatory PAI set has no direct physical-climate-risk
                    metric.
                  </p>
                </section>

                <section className="rounded-2xl border border-gray-200/70 bg-white p-5 shadow-sm">
                  <h2 className="flex items-center gap-1.5 text-[13px] font-semibold text-[#1d1d1f]">
                    <Leaf size={13} className="text-gray-400" /> EU Taxonomy <span className="font-normal text-gray-400">— Article 8, value-weighted</span>
                  </h2>
                  <div className="mt-3 flex h-4 overflow-hidden rounded-full">
                    {Object.entries(disclosure.taxonomy).map(([k, v]) => (
                      <div key={k} title={`${k}: ${mn(v.value_eur)}`} style={{ width: `${(v.value_eur / taxTotal) * 100}%`, background: TAX_COLOR[k] }} />
                    ))}
                  </div>
                  <div className="mt-3 space-y-1.5">
                    {Object.entries(disclosure.taxonomy).map(([k, v]) => (
                      <div key={k} className="flex items-center justify-between text-[12px]">
                        <span className="flex items-center gap-2 text-gray-600"><span className="h-2 w-2 rounded-full" style={{ background: TAX_COLOR[k] }} /> {TAX_LABEL[k] || k}</span>
                        <span className="tabular-nums text-gray-500">{v.count} holdings · {mn(v.value_eur)}</span>
                      </div>
                    ))}
                  </div>
                  <p className="mt-3 text-[10px] text-gray-400">
                    Classified by NACE code, where supplied — never "aligned" without verifying
                    substantial contribution and minimum safeguards. See Methodology.
                  </p>
                </section>
              </div>
            )}
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
