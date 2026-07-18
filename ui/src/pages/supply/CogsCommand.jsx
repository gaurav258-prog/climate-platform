import { useState, useEffect, useCallback } from 'react'
import { Package, TrendingDown, Percent, ShieldCheck, Leaf } from 'lucide-react'
import ContextBar from '../../components/ContextBar'
import SupplyPlotDrawer, { HAZ_COLOR } from '../../components/SupplyPlotDrawer'
import CommodityDrawer from '../../components/CommodityDrawer'
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
  const [selCommodity, setSelCommodity] = useState(null)

  const reload = useCallback(() => {
    setSum(null); setPort(null)
    fetchSupplySummary({ scenario, horizon }).then(setSum).catch(() => setSum(null))
    fetchSupplyPortfolio({ scenario, horizon }).then(setPort).catch(() => setPort(null))
  }, [scenario, horizon])
  useEffect(() => { reload() }, [reload])

  const r = sum?.rollup
  const scored = (sum?.commodities || []).filter(c => c.status === 'scored')
  // 'held' = scored but not event-backtested → € withheld by the publish gate.
  // 'pending' = not hazard-scored yet. Both show exposure, never a euro figure.
  const held = (sum?.commodities || []).filter(c => c.status === 'held')
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
            <h1 className="mt-2 text-3xl font-semibold tracking-tight text-[#1d1d1f]">The volume that won&apos;t arrive</h1>
            <p className="mt-2 max-w-2xl text-[15px] text-gray-500">
              Climate hazard on every sourcing plot, rolled up the bill of materials into the share of
              your volume that fails — valued at the price you already pay. Traceable to the golden
              source, with no price forecast anywhere in it.
            </p>
          </div>
          <UploadPanel uploadFn={uploadSupplyPlots} templateColumns={PLOT_TEMPLATE_COLUMNS}
            templateFilename="supply_plots_template.csv"
            templateXlsxUrl="/v1/supply/plots/template.xlsx" templateXlsxFilename="tellumen_sourcing_plot_template.xlsx"
            label="Import plots" onUploaded={reload} />
        </header>

        {/* publish gate — every € on this page is event-backtested */}
        <div className="mb-6 flex items-start gap-2 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-2.5 text-[12px] text-emerald-800">
          <ShieldCheck size={15} className="mt-0.5 shrink-0" />
          <span>
            <b>This is physical volume, not a price forecast.</b> Your plots lose this share of their
            yield, so this share of the volume you paid for doesn&apos;t arrive — priced at what you
            already pay. A commodity publishes a € only once its hazard→yield chain reproduces a real
            crop failure for every origin you source; anything unvalidated shows <b>exposure mapped,
            € withheld</b>. We deliberately do <b>not</b> predict price moves: tested on 440 real
            crop-years, supply shocks explain just 2% of them — the market prices the news long before
            the harvest is counted. Bring your own price view and we&apos;ll apply it as yours.
            {' '}<b>Scope: this is climate-physical risk only</b> — hazard on your plots, projected under
            warming scenarios. It does <b>not</b> include war, water-allocation policy, fuel or labour
            shocks, or trade disruption; those can dominate a real shortfall and are yours to overlay.
            See <HelpLink onGoto={onGoto} section="method">Methodology</HelpLink>.
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
              <Stat icon={TrendingDown} label="Volume at risk" value={mn(r.volume_at_risk_eur)}
                sub="physical — no price forecast" accent="#c2410c" />
              <Stat icon={Percent} label="Share of COGS" value={`${r.pct_cogs_at_risk}%`}
                sub={`of €${(r.total_cogs_eur / 1e6).toFixed(0)}m COGS`} accent="#c81e1e" />
              <Stat icon={ShieldCheck} label="EUDR plots" value={sum.eudr?.by_status?.compliant || 0}
                sub={`${(sum.eudr?.covered_commodities || []).length} covered commodities`} />
            </div>

            {/* COGS-at-risk by commodity */}
            <section className="mt-6 rounded-2xl border border-gray-200/70 bg-white p-5 shadow-sm">
              <h2 className="text-[13px] font-semibold text-[#1d1d1f]">Volume at risk by commodity
                <span className="font-normal text-gray-400"> — the volume you paid for that won&apos;t arrive · {scenario} · {horizon}</span></h2>
              <div className="mt-3 flex h-4 overflow-hidden rounded-full">
                {scored.map(c => (
                  <div key={c.commodity} title={`${c.commodity}: ${mn(c.cogs_at_risk_p50)}`}
                    style={{ width: `${(c.cogs_at_risk_p50 / totalRisk) * 100}%`, background: HAZ_COLOR[c.top_hazard] || '#6b7280' }} />
                ))}
              </div>
              <div className="mt-4 divide-y divide-gray-100">
                {scored.map(c => (
                  <button key={c.commodity} onClick={() => setSelCommodity(c.commodity)}
                    className="flex w-full items-center justify-between py-2.5 text-left hover:bg-gray-50">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 text-[13px] font-medium text-[#1d1d1f]">
                        {c.commodity}
                        {c.eudr_covered && <span className="rounded-full bg-emerald-50 px-1.5 py-0.5 text-[9px] font-semibold text-emerald-600">EUDR</span>}
                        {c.calibration === 'backtested'
                          ? <span title="Impact function reproduces a real event" className="rounded-full bg-blue-50 px-1.5 py-0.5 text-[9px] font-semibold text-[#0071e3]">backtested</span>
                          : c.calibration === 'ranged'
                            ? <span title={`A driver explains this crop partly (r²=${c.fit_r2}); the € is published as a range, not a point`} className="rounded-full bg-amber-50 px-1.5 py-0.5 text-[9px] font-semibold text-amber-700">ranged · r²&nbsp;{c.fit_r2}</span>
                            : <span title="v0 defaults — shown for exposure, not yet event-validated" className="rounded-full bg-gray-100 px-1.5 py-0.5 text-[9px] font-medium text-gray-500">indicative</span>}
                      </div>
                      <div className="text-[11px] text-gray-400">
                        spend {mn(c.annual_spend_eur)} · <span style={{ color: HAZ_COLOR[c.top_hazard] }}>{(c.top_hazard || '').replace(/_/g, ' ')}</span> hazard {c.avg_hazard}
                        {c.calibration === 'ranged'
                          ? <> · {(c.top_hazard || 'the driver').replace(/_/g, ' ')} explains ~{Math.round((c.fit_r2 || 0) * 100)}% of bad years — the rest we don't claim</>
                          : <> · {c.yield_shock_pct}% of yield at risk{c.global_shock_pct != null && <> · world crop −{c.global_shock_pct}%</>}</>}
                      </div>
                      {c.measured_basis && (
                        <div className="mt-0.5 text-[10px] italic text-gray-400">measures {c.measured_basis}</div>
                      )}
                    </div>
                    <div className="text-right">
                      {c.calibration === 'ranged' && c.volume_at_risk_high_eur != null
                        ? <>
                            <div className="text-[14px] font-semibold text-[#c2410c]">{mn(c.volume_at_risk_low_eur)}–{mn(c.volume_at_risk_high_eur)}</div>
                            <div className="text-[10px] text-gray-400">volume at risk · range</div>
                          </>
                        : <>
                            <div className="text-[14px] font-semibold text-[#c2410c]">{mn(c.volume_at_risk_eur)}</div>
                            <div className="text-[10px] text-gray-400">volume at risk</div>
                          </>}
                    </div>
                  </button>
                ))}
                {held.map(c => (
                  <button key={c.commodity} onClick={() => setSelCommodity(c.commodity)}
                    className="flex w-full items-center justify-between py-2.5 text-left hover:bg-gray-50">
                    <div>
                      <div className="flex items-center gap-2 text-[13px] font-medium text-[#1d1d1f]">
                        {c.commodity}
                        {c.eudr_covered && <span className="rounded-full bg-emerald-50 px-1.5 py-0.5 text-[9px] font-semibold text-emerald-600">EUDR</span>}
                      </div>
                      <div className="text-[11px] text-gray-400">
                        spend {mn(c.annual_spend_eur)} · <span style={{ color: HAZ_COLOR[c.top_hazard] }}>{(c.top_hazard || '').replace(/_/g, ' ')}</span> hazard {c.avg_hazard} ·{' '}
                        {c.fit_r2 != null
                          ? <>{(c.top_hazard || 'driver').replace(/_/g, ' ')} tested — explains {Math.floor(c.fit_r2 * 100)}% of bad years, below our 40% publish bar</>
                          : <>exposure mapped, hazard→yield not yet validated</>}
                      </div>
                      {c.measured_basis && (
                        <div className="mt-0.5 text-[10px] italic text-gray-400">measures {c.measured_basis}</div>
                      )}
                    </div>
                    <div title="Every plot is scored; we withhold the € until the hazard→yield chain clears our publish bar" className="rounded-full bg-amber-50 px-2.5 py-1 text-[10px] font-medium text-amber-700">
                      € withheld
                    </div>
                  </button>
                ))}
                {pending.map(c => (
                  <button key={c.commodity} onClick={() => setSelCommodity(c.commodity)}
                    className="flex w-full items-center justify-between py-2.5 text-left opacity-70 hover:bg-gray-50">
                    <div>
                      <div className="flex items-center gap-2 text-[13px] font-medium text-[#1d1d1f]">
                        {c.commodity}
                        {c.eudr_covered && <span className="rounded-full bg-emerald-50 px-1.5 py-0.5 text-[9px] font-semibold text-emerald-600">EUDR</span>}
                      </div>
                      <div className="text-[11px] text-gray-400">spend {mn(c.annual_spend_eur)} · plots not yet scored for hazards</div>
                    </div>
                    <div title="These plots are not yet in a scored hazard region — exposure is not mapped yet" className="rounded-full bg-gray-100 px-2.5 py-1 text-[10px] font-medium text-gray-500">
                      € pending
                    </div>
                  </button>
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
      {selCommodity && <CommodityDrawer commodity={selCommodity} scenario={scenario} horizon={horizon}
        onClose={() => setSelCommodity(null)} onSelectPlot={id => { setSelCommodity(null); setSelPlot(id) }} />}
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
