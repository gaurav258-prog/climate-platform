import { useState, useEffect, useCallback } from 'react'
import { Package, TrendingDown, Percent, ShieldCheck, AlertTriangle, Leaf } from 'lucide-react'
import ContextBar from '../../components/ContextBar'
import SupplyPlotDrawer, { HAZ_COLOR } from '../../components/SupplyPlotDrawer'
import UploadPanel from '../../components/UploadPanel'
import EmptyState from '../../components/EmptyState'
import HelpLink from '../../components/HelpLink'
import { fetchSupplySummary, fetchSupplyPortfolio, uploadSupplyPlots } from '../../api/client'

const mn = n => '€' + (n / 1e6).toFixed(1) + 'm'
const PLOT_TEMPLATE_COLUMNS = ['plot_name', 'latitude', 'longitude', 'commodity', 'annual_spend_eur', 'plot_area_ha', 'region', 'country']

export default function CogsCommand({ onGoto }) {
  const [scenario, setScenario] = useState('baseline')
  const [horizon, setHorizon] = useState('current')
  const [sum, setSum] = useState(null)
  const [port, setPort] = useState(null)
  const [selPlot, setSelPlot] = useState(null)

  const reload = useCallback(() => {
    setSum(null); setPort(null)
    fetchSupplySummary({ scenario, horizon }).then(setSum).catch(() => setSum(null))
    fetchSupplyPortfolio({ scenario, horizon }).then(setPort).catch(() => setPort(null))
  }, [scenario, horizon])
  useEffect(() => { reload() }, [reload])

  const r = sum?.rollup
  const scored = (sum?.commodities || []).filter(c => c.status === 'scored')
  const pending = (sum?.commodities || []).filter(c => c.status === 'pending')
  const totalRisk = scored.reduce((s, c) => s + (c.cogs_at_risk_p50 || 0), 0) || 1

  return (
    <div className="flex h-full flex-col bg-[#f5f5f7]">
      <ContextBar scenario={scenario} horizon={horizon} onScenario={setScenario} onHorizon={setHorizon}
        vintage="2024-10-29" label={`Agriculture · ${sum?.org?.name || 'Terra Foods (demo)'}`} />

      <div className="flex-1 overflow-y-auto px-8 py-8">
        <header className="mb-5 flex items-end justify-between gap-4">
          <div>
            <div className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-[0.12em] text-gray-400">
              <Package size={13} /> COGS-at-Risk
            </div>
            <h1 className="mt-2 text-3xl font-semibold tracking-tight text-[#1d1d1f]">Your procurement book, projected</h1>
            <p className="mt-2 max-w-2xl text-[15px] text-gray-500">
              Climate hazard on every sourcing plot, rolled up the bill of materials into cost-of-goods —
              one auditable number per commodity, traceable to the golden source.
            </p>
          </div>
          <UploadPanel uploadFn={uploadSupplyPlots} templateColumns={PLOT_TEMPLATE_COLUMNS}
            templateFilename="supply_plots_template.csv"
            templateXlsxUrl="/v1/supply/plots/template.xlsx" templateXlsxFilename="tellumen_sourcing_plot_template.xlsx"
            label="Import plots" onUploaded={reload} />
        </header>

        {/* honest v0 banner */}
        <div className="mb-6 flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 px-4 py-2.5 text-[12px] text-amber-800">
          <AlertTriangle size={15} className="mt-0.5 shrink-0" />
          <span>
            <b>v0 impact functions — uncalibrated.</b> Euro figures are illustrative pending event backtests
            (cocoa 2023/24, coffee 2021). Commodities without matured hazard scoring show <b>exposure mapped, € pending</b>.
            See <HelpLink onGoto={onGoto} section="method">Methodology</HelpLink> for the full disclosure.
          </span>
        </div>

        {!r ? <p className="text-gray-400">loading…</p> : r.n_commodities === 0 ? (
          <EmptyState icon={Package} title="No sourcing plots in your book yet"
            description="Import your sourcing plots (CSV or Excel) and every plot gets scored against the golden source automatically, rolled up into COGS-at-risk per commodity."
            action={<UploadPanel uploadFn={uploadSupplyPlots} templateColumns={PLOT_TEMPLATE_COLUMNS}
              templateFilename="supply_plots_template.csv"
              templateXlsxUrl="/v1/supply/plots/template.xlsx" templateXlsxFilename="tellumen_sourcing_plot_template.xlsx"
              label="Import plots" onUploaded={reload} startOpen />} />
        ) : (
          <>
            <div className="grid grid-cols-4 gap-4">
              <Stat icon={Package} label="Ingredient spend" value={mn(r.ingredient_spend_eur)}
                sub={`${r.n_commodities} commodities`} />
              <Stat icon={TrendingDown} label="COGS-at-risk (P50)" value={mn(r.cogs_at_risk_p50_eur)}
                sub={`P90 ${mn(r.cogs_at_risk_p90_eur)}`} accent="#c2410c" />
              <Stat icon={Percent} label="Share of COGS" value={`${r.pct_cogs_at_risk}%`}
                sub={`of €${(r.total_cogs_eur / 1e6).toFixed(0)}m COGS`} accent="#c81e1e" />
              <Stat icon={ShieldCheck} label="EUDR plots" value={sum.eudr?.by_status?.compliant || 0}
                sub={`${(sum.eudr?.covered_commodities || []).length} covered commodities`} />
            </div>

            {/* COGS-at-risk by commodity */}
            <section className="mt-6 rounded-2xl border border-gray-200/70 bg-white p-5 shadow-sm">
              <h2 className="text-[13px] font-semibold text-[#1d1d1f]">COGS-at-risk by commodity
                <span className="font-normal text-gray-400"> — P50, {scenario} · {horizon}</span></h2>
              <div className="mt-3 flex h-4 overflow-hidden rounded-full">
                {scored.map(c => (
                  <div key={c.commodity} title={`${c.commodity}: ${mn(c.cogs_at_risk_p50)}`}
                    style={{ width: `${(c.cogs_at_risk_p50 / totalRisk) * 100}%`, background: HAZ_COLOR[c.top_hazard] || '#6b7280' }} />
                ))}
              </div>
              <div className="mt-4 divide-y divide-gray-100">
                {scored.map(c => (
                  <div key={c.commodity} className="flex items-center justify-between py-2.5">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 text-[13px] font-medium text-[#1d1d1f]">
                        {c.commodity}
                        {c.eudr_covered && <span className="rounded-full bg-emerald-50 px-1.5 py-0.5 text-[9px] font-semibold text-emerald-600">EUDR</span>}
                        {c.calibration === 'backtested'
                          ? <span title="Impact function reproduces a real event" className="rounded-full bg-blue-50 px-1.5 py-0.5 text-[9px] font-semibold text-[#0071e3]">backtested</span>
                          : <span title="v0 defaults — shown for exposure, not yet event-validated" className="rounded-full bg-gray-100 px-1.5 py-0.5 text-[9px] font-medium text-gray-500">indicative</span>}
                      </div>
                      <div className="text-[11px] text-gray-400">
                        spend {mn(c.annual_spend_eur)} · <span style={{ color: HAZ_COLOR[c.top_hazard] }}>{c.top_hazard}</span> hazard {c.avg_hazard}
                        · yield-shock {c.yield_shock_pct}% · price +{c.price_move_pct}%
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="text-[14px] font-semibold text-[#c2410c]">{mn(c.cogs_at_risk_p50)}</div>
                      <div className="text-[10px] text-gray-400">P90 {mn(c.cogs_at_risk_p90)}</div>
                    </div>
                  </div>
                ))}
                {pending.map(c => (
                  <div key={c.commodity} className="flex items-center justify-between py-2.5 opacity-70">
                    <div>
                      <div className="flex items-center gap-2 text-[13px] font-medium text-[#1d1d1f]">
                        {c.commodity}
                        {c.eudr_covered && <span className="rounded-full bg-emerald-50 px-1.5 py-0.5 text-[9px] font-semibold text-emerald-600">EUDR</span>}
                      </div>
                      <div className="text-[11px] text-gray-400">spend {mn(c.annual_spend_eur)} · exposure mapped</div>
                    </div>
                    <div className="rounded-full bg-gray-100 px-2.5 py-1 text-[10px] font-medium text-gray-500">
                      € pending · drought/heat
                    </div>
                  </div>
                ))}
              </div>
            </section>

            {/* sourcing plots */}
            <section className="mt-6 rounded-2xl border border-gray-200/70 bg-white p-5 shadow-sm">
              <h2 className="text-[13px] font-semibold text-[#1d1d1f]">Sourcing plots
                <span className="font-normal text-gray-400"> — click to trace a plot to its score</span></h2>
              <div className="mt-3 grid grid-cols-2 gap-x-8 gap-y-1 md:grid-cols-3">
                {(port?.plots || []).map(p => (
                  <button key={p.plot_id} onClick={() => setSelPlot(p.plot_id)}
                    className="flex items-center justify-between gap-2 rounded-lg px-2 py-1.5 text-left hover:bg-gray-50">
                    <span className="min-w-0">
                      <span className="block truncate text-[12px] font-medium text-[#1d1d1f]">{p.commodity}</span>
                      <span className="block truncate text-[10px] text-gray-400">{p.region} · {p.country} · {mn(p.spend_eur)}</span>
                    </span>
                    <Leaf size={13} className="shrink-0 text-emerald-500" />
                  </button>
                ))}
              </div>
            </section>
          </>
        )}
      </div>

      {selPlot && <SupplyPlotDrawer plotId={selPlot} onClose={() => setSelPlot(null)} scenario={scenario} horizon={horizon} />}
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
