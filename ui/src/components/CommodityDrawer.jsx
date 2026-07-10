import { useEffect, useState } from 'react'
import { Leaf } from 'lucide-react'
import { fetchSupplyPortfolio, fetchSupplyValidation } from '../api/client'
import { HAZ_COLOR } from './SupplyPlotDrawer'
import { DrawerShell, Facts } from './EntityDrawerParts'

const mn = n => n == null ? '—' : '€' + (n / 1e6).toFixed(1) + 'm'

/** The commodity-level drill-through CogsCommand's "by commodity" list,
 * SupplySignals' "alerts", and SupplyDisclosure's CSRD list all lacked -- a
 * commodity aggregate has no single entity_id, so this self-fetches the org's
 * full plot list + validation backtests and filters to this commodity, down
 * to the plots (each themselves clickable into SupplyPlotDrawer) and any
 * event backtest that grounds its calibration status. */
export default function CommodityDrawer({ commodity, scenario = 'baseline', horizon = 'current', onClose, onSelectPlot }) {
  const [plots, setPlots] = useState(null)
  const [events, setEvents] = useState([])

  useEffect(() => {
    if (!commodity) return
    setPlots(null)
    fetchSupplyPortfolio({ scenario, horizon }).then(d => setPlots((d.plots || []).filter(p => p.commodity === commodity)))
      .catch(() => setPlots([]))
    fetchSupplyValidation().then(d => setEvents((d.events || []).filter(e => e.commodity === commodity))).catch(() => {})
  }, [commodity, scenario, horizon])

  if (!commodity) return null
  const totalSpend = (plots || []).reduce((s, p) => s + (p.spend_eur || 0), 0)

  return (
    <DrawerShell title={commodity} subtitle={plots && `${plots.length} sourcing plot${plots.length === 1 ? '' : 's'} · ${mn(totalSpend)} spend`}
      loading={!plots} onClose={onClose}>
      {plots && (
        <>
          {events.length > 0 && (
            <section className="rounded-2xl bg-[#f5f5f7] p-4">
              <div className="text-[11px] uppercase tracking-wide text-gray-400">Event backtest</div>
              {events.map((e, i) => (
                <div key={i} className="mt-2 text-[12px]">
                  <div className="font-medium text-[#1d1d1f]">{e.event} · <span className="capitalize" style={{ color: HAZ_COLOR[e.hazard] }}>{e.hazard}</span></div>
                  <div className="mt-0.5 text-gray-500">
                    Model {e.model_price_move_pct}% vs. observed {e.observed_price_move_pct}% price move
                  </div>
                  {e.skill_note && <p className="mt-1 text-[11px] leading-snug text-gray-400">{e.skill_note}</p>}
                </div>
              ))}
            </section>
          )}

          <section>
            <h3 className="mb-2 text-[11px] uppercase tracking-wide text-gray-400">Sourcing plots</h3>
            {plots.length ? (
              <div className="divide-y divide-gray-100 rounded-2xl border border-gray-200">
                {plots.map(p => (
                  <button key={p.plot_id} onClick={() => onSelectPlot(p.plot_id)}
                    className="flex w-full items-center justify-between px-3 py-2.5 text-left hover:bg-gray-50">
                    <span className="min-w-0">
                      <span className="block truncate text-[13px] font-medium text-[#1d1d1f]">{p.plot_name}</span>
                      <span className="block truncate text-[11px] text-gray-400">{p.region}, {p.country} · {mn(p.spend_eur)}</span>
                    </span>
                    <span className="flex shrink-0 items-center gap-2">
                      {p.hazard_score != null && (
                        <span className="text-[12px] font-medium" style={{ color: HAZ_COLOR[p.top_hazard] }}>
                          {p.top_hazard} {p.hazard_score}
                        </span>
                      )}
                      <Leaf size={13} className="text-emerald-500" />
                    </span>
                  </button>
                ))}
              </div>
            ) : <p className="text-[12px] text-gray-400">No sourcing plots on record for this commodity.</p>}
          </section>
        </>
      )}
    </DrawerShell>
  )
}
