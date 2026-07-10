import { useState, useEffect, useCallback } from 'react'
import { Building2, TrendingDown, Layers, ShieldAlert, Download, FileSpreadsheet, Leaf } from 'lucide-react'
import ContextBar from '../../components/ContextBar'
import RiskAtom, { BUCKET } from '../../components/RiskAtom'
import UploadPanel from '../../components/UploadPanel'
import RealEstateDrawer from '../../components/RealEstateDrawer'
import EmptyState from '../../components/EmptyState'
import HelpLink from '../../components/HelpLink'
import {
  fetchRealEstateSummary, fetchRealEstatePortfolio, fetchRealEstateDisclosure,
  uploadRealEstateProperties, downloadFile,
} from '../../api/client'

const mn = n => n == null ? '—' : '€' + (n / 1e6).toFixed(1) + 'm'
const ORDER = ['VH', 'H', 'M', 'L', 'none']
const HAZ_LABEL = { flood: 'Flood', wildfire: 'Wildfire', volcanic: 'Volcanic', storm: 'Storm', heat_acute: 'Heat', drought: 'Drought' }
const TAX_LABEL = { eligible: 'Eligible', not_eligible: 'Not eligible', not_assessed: 'Not assessed' }
const TAX_COLOR = { eligible: '#ff9500', not_eligible: '#86868b', not_assessed: '#d1d5db' }
const TEMPLATE_COLUMNS = ['property_name', 'latitude', 'longitude', 'property_value_eur', 'annual_noi_eur',
  'property_type', 'construction_type', 'year_built', 'number_of_stories', 'region', 'country',
  'epc_rating', 'borrower_entity_id', 'minimum_safeguards_status']

function exportCsv(properties) {
  const head = ['property_name', 'property_type', 'region', 'country', 'property_value_eur', 'annual_noi_eur',
    'headline_hazard', 'headline_score', 'risk_bucket', 'discounted_value_eur', 'expected_insurance_premium_eur',
    'noi_impact_pct', 'taxonomy_status']
  const rows = [head, ...properties.map(p => [
    p.property_name, p.property_type, p.region, p.country, p.property_value_eur, p.annual_noi_eur,
    p.headline_hazard ?? '', p.headline_score ?? '', p.headline_bucket ?? 'unscored',
    p.valuation?.discounted_value_eur ?? '', p.noi_impact?.expected_insurance_premium_eur ?? '',
    p.noi_impact?.noi_impact_pct ?? '', p.taxonomy_status,
  ])]
  const csv = rows.map(r => r.map(x => `"${String(x ?? '').replace(/"/g, '""')}"`).join(',')).join('\n')
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }))
  const link = document.createElement('a')
  link.href = url; link.download = 'stellar-portfolio-noi-impact.csv'; link.click()
  URL.revokeObjectURL(url)
}

export default function PortfolioImpact({ auth, onGoto }) {
  const [scenario, setScenario] = useState('baseline')
  const [horizon, setHorizon] = useState('current')
  const [data, setData] = useState(null)
  const [properties, setProperties] = useState([])
  const [disclosure, setDisclosure] = useState(null)
  const [sel, setSel] = useState(null)

  const reload = useCallback(() => {
    fetchRealEstateSummary({ scenario, horizon }).then(setData).catch(() => setData(null))
    fetchRealEstatePortfolio({ scenario, horizon }).then(x => setProperties(x.properties || [])).catch(() => {})
    fetchRealEstateDisclosure({ scenario, horizon }).then(setDisclosure).catch(() => setDisclosure(null))
  }, [scenario, horizon])
  useEffect(() => { setData(null); reload() }, [reload])

  const r = data?.rollup
  const totalValue = r ? Object.values(r.by_bucket).reduce((s, b) => s + b.value_eur, 0) : 0
  const taxTotal = disclosure ? Object.values(disclosure.taxonomy).reduce((s, t) => s + t.value_eur, 0) : 0

  return (
    <div className="flex h-full flex-col bg-[#f5f5f7]">
      <ContextBar scenario={scenario} horizon={horizon} onScenario={setScenario} onHorizon={setHorizon}
        vintage="2024-10-29" label={`Real estate · ${data?.org?.name || 'Stellar Logistics REIT (demo)'}`} />

      <div className="flex-1 overflow-y-auto px-8 py-8">
        <header className="mb-6 flex items-end justify-between gap-4">
          <div>
            <div className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-[0.12em] text-gray-400">
              <Building2 size={13} /> Portfolio & NOI impact
            </div>
            <h1 className="mt-2 text-3xl font-semibold tracking-tight text-[#1d1d1f]">Where climate hits NOI</h1>
            <p className="mt-2 max-w-2xl text-[15px] text-gray-500">
              Same golden source as banking and insurance: risk score → collateral haircut on owned property value,
              and → expected insurance cost as a share of net operating income.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={() => downloadFile(`/v1/realestate/portfolio.xlsx?scenario=${scenario}&horizon=${horizon}`, 'stellar-portfolio-noi-impact.xlsx')}
              className="flex items-center gap-2 rounded-full bg-[#0071e3] px-4 py-2 text-[13px] font-medium text-white hover:bg-[#0077ed]">
              <FileSpreadsheet size={15} /> Export Excel
            </button>
            <button onClick={() => exportCsv(properties)}
              className="flex items-center gap-2 rounded-full border border-gray-200 bg-white px-4 py-2 text-[13px] font-medium text-[#1d1d1f] hover:border-gray-300">
              <Download size={15} /> Export CSV
            </button>
            <UploadPanel uploadFn={uploadRealEstateProperties} templateColumns={TEMPLATE_COLUMNS}
              templateFilename="realestate_properties_template.csv"
              templateXlsxUrl="/v1/realestate/properties/template.xlsx" templateXlsxFilename="tellumen_property_schedule_template.xlsx"
              label="Import properties" onUploaded={reload} />
          </div>
        </header>

        {!r ? <p className="text-gray-400">loading…</p> : r.n_properties === 0 ? (
          <EmptyState icon={Building2} title="No properties in your portfolio yet"
            description="Import your property schedule (CSV or Excel) and every property gets scored against the golden source automatically, with climate-adjusted valuation and NOI impact."
            action={<UploadPanel uploadFn={uploadRealEstateProperties} templateColumns={TEMPLATE_COLUMNS}
              templateFilename="realestate_properties_template.csv"
              templateXlsxUrl="/v1/realestate/properties/template.xlsx" templateXlsxFilename="tellumen_property_schedule_template.xlsx"
              label="Import properties" onUploaded={reload} startOpen />} />
        ) : (
          <>
            <div className="mb-4 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-[12px] text-amber-800">
              <strong>NOI impact — disclosed methodology.</strong> Reuses the same Emanuel(2011)/CLIMADA-style
              damage curve and CAS ratemaking chain built for insurance underwriting: "what would this property
              cost to insure at this hazard exposure," expressed as a share of NOI — not a fitted operating-cost
              model. See <HelpLink onGoto={onGoto} section="method">Methodology</HelpLink> for the full disclosure.
            </div>

            <div className="grid grid-cols-4 gap-4">
              <Stat icon={Layers} label="Portfolio value" value={mn(r.total_value_eur)} sub={`${r.n_properties} properties`} />
              <Stat icon={TrendingDown} label="Climate-adjusted value" value={mn(r.total_discounted_value_eur)}
                sub="after risk-bucket haircut" accent="#c2410c" />
              <Stat icon={ShieldAlert} label="Expected insurance cost" value={mn(r.total_expected_insurance_premium_eur)}
                sub={`${r.portfolio_noi_impact_pct}% of portfolio NOI`} accent="#c2410c" />
              <Stat icon={Building2} label="Scored coverage" value={`${Math.round(100 * r.n_scored / r.n_properties)}%`}
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
              <h2 className="text-[13px] font-semibold text-[#1d1d1f]">Most exposed properties</h2>
              <div className="mt-3 divide-y divide-gray-100">
                {r.top_properties.map(p => (
                  <button key={p.property_id} onClick={() => setSel(p.property_id)}
                    className="flex w-full items-center justify-between py-2.5 text-left hover:bg-gray-50">
                    <div className="min-w-0">
                      <div className="truncate text-[13px] font-medium text-[#1d1d1f]">{p.property_name}</div>
                      <div className="text-[11px] text-gray-400">
                        {p.property_type} · {p.region} · {p.country} · {mn(p.property_value_eur)} value · {p.headline_hazard}
                        {p.noi_impact && ` · ${p.noi_impact.noi_impact_pct}% of this property's NOI`}
                      </div>
                    </div>
                    <RiskAtom score={p.headline_score} bucket={p.headline_bucket} size="md" showLabel />
                  </button>
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
                      <th className="py-1.5 text-center font-medium">Properties</th>
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
                    The same data GRESB's Resilience module and CSRD physical-risk disclosure ask for — not a
                    fabricated GRESB score.
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
                        <span className="tabular-nums text-gray-500">{v.count} properties · {mn(v.value_eur)}</span>
                      </div>
                    ))}
                  </div>
                  <p className="mt-3 text-[10px] text-gray-400">
                    Annex I §7.7 (acquisition and ownership of buildings) — never "aligned" without verifying
                    substantial contribution and minimum safeguards. See <HelpLink onGoto={onGoto} section="method">Methodology</HelpLink>.
                  </p>
                </section>
              </div>
            )}
          </>
        )}
      </div>

      <RealEstateDrawer propertyId={sel} onClose={() => setSel(null)} auth={auth} scenario={scenario} horizon={horizon} onGoto={onGoto} />
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
