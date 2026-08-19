import { useState, useEffect, useCallback } from 'react'
import { Briefcase, Building2, Flame, Layers, FileText, AlertTriangle } from 'lucide-react'
import ContextBar from '../../components/ContextBar'
import RiskAtom from '../../components/RiskAtom'
import IssuerDrawer from '../../components/IssuerDrawer'
import HelpLink from '../../components/HelpLink'
import { fetchFunds, fetchFund, fetchFundPositions } from '../../api/client'

const mn = n => n == null ? '—' : '€' + (n / 1e6).toFixed(1) + 'm'

export default function FundsOverview({ onGoto }) {
  const [scenario, setScenario] = useState('baseline')
  const [horizon, setHorizon] = useState('current')
  const [funds, setFunds] = useState(null)
  const [selFund, setSelFund] = useState(null)
  const [report, setReport] = useState(null)
  const [positions, setPositions] = useState([])
  const [selIssuer, setSelIssuer] = useState(null)

  const loadFunds = useCallback(() => {
    fetchFunds({ scenario, horizon }).then(d => {
      setFunds(d.funds || [])
      if (!selFund && d.funds?.length) setSelFund(d.funds[0].fund_id)
    }).catch(() => setFunds([]))
  }, [scenario, horizon, selFund])
  useEffect(() => { loadFunds() }, [loadFunds])

  useEffect(() => {
    if (!selFund) return
    setReport(null)
    fetchFund(selFund, { scenario, horizon }).then(setReport).catch(() => setReport(null))
    fetchFundPositions(selFund, { scenario, horizon }).then(d => setPositions(d.positions || [])).catch(() => setPositions([]))
  }, [selFund, scenario, horizon])

  const pai = report?.pai?.pai
  const gaps = report?.pai?.pai_gaps || []

  return (
    <div className="flex h-full flex-col bg-[#f5f5f7]">
      <ContextBar scenario={scenario} horizon={horizon} onScenario={setScenario} onHorizon={setHorizon}
        vintage="2024-10-29" label={`Asset management · ${report?.fund?.org_name || 'Nordkap Asset Management (demo)'}`} />

      <div className="flex-1 overflow-y-auto px-8 py-8">
        <header className="mb-5">
          <div className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-[0.12em] text-gray-400">
            <Briefcase size={13} /> Securities portfolio
          </div>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight text-[#1d1d1f]">Fund climate & SFDR</h1>
          <p className="mt-2 max-w-2xl text-[15px] text-gray-500">
            Every security rolls security → issuer → the issuer's physical <b>footprint</b> (many facilities, not one HQ) and
            its <b>transition</b> exposure, aggregated value-weighted to the fund. Two orthogonal risks, one book.
          </p>
        </header>

        {/* fund selector */}
        {funds && funds.length > 1 && (
          <div className="mb-4 flex flex-wrap gap-2">
            {funds.map(f => (
              <button key={f.fund_id} onClick={() => setSelFund(f.fund_id)}
                className={`rounded-full border px-3 py-1.5 text-[12px] font-medium transition ${
                  selFund === f.fund_id ? 'border-[#0071e3] bg-[#0071e3]/10 text-[#0071e3]' : 'border-gray-200 text-gray-600 hover:border-gray-300'}`}>
                {f.name}
              </button>
            ))}
          </div>
        )}

        {!report ? <p className="text-gray-400">loading…</p> : report.error ? (
          <p className="text-gray-400">No fund found.</p>
        ) : (
          <>
            {/* headline: the two dimensions side by side */}
            <div className="grid grid-cols-4 gap-4">
              <Stat icon={Layers} label="Fund book" value={mn(report.total_value_eur)}
                sub={`${report.positions} positions · ${report.fund.sfdr_classification?.replace('_', ' ') || '—'}`} />
              <Stat icon={Building2} label="Physical risk" value={report.physical.value_weighted_score ?? '—'}
                sub={`${report.physical.pct_at_high_plus}% at High+ · ${report.physical.coverage_pct}% covered`} accent="#c2410c" />
              <Stat icon={Flame} label="Transition risk" value={report.transition.value_weighted_score ?? '—'}
                sub={`${report.transition.pct_at_high_plus}% at High+ · ${report.transition.coverage_pct}% covered`} accent="#7c3aed" />
              <Stat icon={FileText} label="WACI (PAI 3)" value={pai?.pai_3_waci_tco2e_per_meur ?? '—'}
                sub="tCO₂e / €m revenue" accent="#0071e3" />
            </div>

            {/* SFDR PAI panel */}
            <section className="mt-6 rounded-2xl border border-gray-200/70 bg-white p-5 shadow-sm">
              <h2 className="text-[13px] font-semibold text-[#1d1d1f]">SFDR Principal Adverse Impact
                <span className="font-normal text-gray-400"> — value-weighted, {report.pai.emissions_coverage_pct}% emissions coverage</span></h2>
              <div className="mt-3 grid grid-cols-3 gap-4">
                <PaiCard label="PAI 3 · GHG intensity (WACI)" value={pai?.pai_3_waci_tco2e_per_meur ?? '—'} unit="tCO₂e/€m" />
                <PaiCard label="PAI 4 · Fossil-fuel exposure" value={pai?.pai_4_fossil_fuel_exposure_pct ?? '—'} unit="% of book" />
                <PaiCard label="PAI 1 · Investee GHG (S1/2/3)"
                  value={pai ? `${(pai.pai_1_investee_emissions_tco2e.scope_1/1e6).toFixed(1)}/${(pai.pai_1_investee_emissions_tco2e.scope_2/1e6).toFixed(1)}/${(pai.pai_1_investee_emissions_tco2e.scope_3/1e6).toFixed(1)}` : '—'}
                  unit="Mt CO₂e" />
              </div>
              {pai?.pai_1_investee_emissions_tco2e?.note && (
                <p className="mt-3 rounded-lg bg-blue-50 px-3 py-2 text-[11px] leading-snug text-blue-800">
                  {pai.pai_1_investee_emissions_tco2e.note}
                </p>
              )}
              {gaps.length > 0 && (
                <div className="mt-3 flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[11px] text-amber-800">
                  <AlertTriangle size={14} className="mt-0.5 shrink-0" />
                  <span>
                    <b>Input required to complete:</b>{' '}
                    {gaps.map((g, i) => <span key={i}>{i > 0 && ' · '}{g.indicator.split('—')[0].trim()} ({g.input_required})</span>)}
                    . Surfaced honestly — never a fabricated zero. See <HelpLink onGoto={onGoto} section="method">Methodology</HelpLink>.
                  </span>
                </div>
              )}
            </section>

            {/* positions — click to trace an issuer to its footprint */}
            <section className="mt-6 rounded-2xl border border-gray-200/70 bg-white p-5 shadow-sm">
              <h2 className="text-[13px] font-semibold text-[#1d1d1f]">Holdings
                <span className="font-normal text-gray-400"> — click an issuer to trace its footprint to the golden source</span></h2>
              <table className="mt-3 w-full text-[13px]">
                <thead><tr className="border-b border-gray-200 text-left text-[11px] uppercase tracking-wide text-gray-400">
                  <th className="py-2 font-medium">Issuer</th><th className="py-2 text-right font-medium">Value</th>
                  <th className="py-2 text-center font-medium">Physical</th><th className="py-2 text-center font-medium">Transition</th>
                  <th className="py-2 text-right font-medium">Coverage</th>
                </tr></thead>
                <tbody>
                  {positions.map(p => (
                    <tr key={p.position_id} onClick={() => setSelIssuer(p.issuer_id)}
                      className="cursor-pointer border-b border-gray-50 last:border-0 hover:bg-gray-50">
                      <td className="py-2.5">
                        <div className="font-medium text-[#1d1d1f]">{p.issuer_name}</div>
                        <div className="text-[11px] text-gray-400">{p.security_name} · {p.asset_class} · {p.country}</div>
                      </td>
                      <td className="py-2.5 text-right tabular-nums text-[#1d1d1f]">{mn(p.market_value_eur)}</td>
                      <td className="py-2.5 text-center"><RiskAtom score={p.physical.headline_score} bucket={p.physical.headline_bucket} size="sm" /></td>
                      <td className="py-2.5 text-center"><RiskAtom score={p.transition?.transition_risk_score} bucket={p.transition?.risk_bucket} size="sm" /></td>
                      <td className="py-2.5 text-right text-[11px] text-gray-400">{p.physical.scored_weight_pct}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          </>
        )}
      </div>

      <IssuerDrawer issuerId={selIssuer} scenario={scenario} horizon={horizon} onClose={() => setSelIssuer(null)} />
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

function PaiCard({ label, value, unit }) {
  return (
    <div className="rounded-xl bg-[#f5f5f7] px-3 py-2.5">
      <div className="text-[10px] uppercase tracking-wide text-gray-400">{label}</div>
      <div className="mt-1 text-[17px] font-semibold text-[#1d1d1f]">{value} <span className="text-[11px] font-normal text-gray-400">{unit}</span></div>
    </div>
  )
}
