import { useState, useEffect } from 'react'
import { Radio, AlertTriangle } from 'lucide-react'
import ContextBar from '../../components/ContextBar'
import { HAZ_COLOR } from '../../components/SupplyPlotDrawer'
import SupplyPlotDrawer from '../../components/SupplyPlotDrawer'
import CommodityDrawer from '../../components/CommodityDrawer'
import { fetchSupplySignals } from '../../api/client'

const mn = n => '€' + ((n || 0) / 1e6).toFixed(1) + 'm'
const LEVEL = { VH: '#c81e1e', H: '#c2410c', M: '#b56a00', L: '#1a8a4a' }

// Early warning — commodities under elevated hazard right now, screened against the
// sourcing book. The agriculture analogue of the banking Signals screen.
export default function SupplySignals() {
  const [scenario, setScenario] = useState('baseline')
  const [horizon, setHorizon] = useState('current')
  const [data, setData] = useState(null)
  const [selCommodity, setSelCommodity] = useState(null)
  const [selPlot, setSelPlot] = useState(null)

  useEffect(() => {
    setData(null)
    fetchSupplySignals({ scenario, horizon }).then(setData).catch(() => setData(null))
  }, [scenario, horizon])

  const alerts = data?.alerts || []

  return (
    <div className="flex h-full flex-col bg-[#f5f5f7]">
      <ContextBar scenario={scenario} horizon={horizon} onScenario={setScenario} onHorizon={setHorizon}
        vintage="2024-10-29" label="Agriculture · Terra Foods (demo)" />
      <div className="flex-1 overflow-y-auto px-8 py-8">
        <header className="mb-5">
          <div className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-[0.12em] text-gray-400">
            <Radio size={13} /> Early warning
          </div>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight text-[#1d1d1f]">What's heating up in your supply</h1>
          <p className="mt-2 max-w-2xl text-[15px] text-gray-500">
            Commodities whose sourcing is under elevated hazard this season — ranked by severity, screened
            against your book. Act before the season turns.
          </p>
        </header>

        {!data ? <p className="text-gray-400">loading…</p> : alerts.length === 0 ? (
          <div className="rounded-2xl border border-gray-200/70 bg-white p-8 text-center text-[14px] text-gray-500 shadow-sm">
            No commodities above the alert threshold under {scenario} · {horizon}.
          </div>
        ) : (
          <div className="space-y-3">
            {alerts.map(a => (
              <button key={a.commodity} onClick={() => setSelCommodity(a.commodity)}
                className="flex w-full items-center gap-4 rounded-2xl border border-gray-200/70 bg-white p-4 text-left shadow-sm hover:border-gray-300">
                <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl text-[13px] font-bold text-white"
                  style={{ background: LEVEL[a.level] }}>{a.level}</span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 text-[15px] font-semibold text-[#1d1d1f]">
                    {a.commodity}
                    <span className="text-[11px] font-medium" style={{ color: HAZ_COLOR[a.hazard] }}>{a.hazard}</span>
                    {a.calibration === 'backtested'
                      ? <span className="rounded-full bg-blue-50 px-1.5 py-0.5 text-[9px] font-semibold text-[#0071e3]">backtested</span>
                      : <span className="rounded-full bg-gray-100 px-1.5 py-0.5 text-[9px] font-medium text-gray-500">indicative</span>}
                  </div>
                  <div className="text-[12px] text-gray-500">
                    hazard {a.avg_hazard} · spend {mn(a.spend_eur)} exposed
                  </div>
                </div>
                <div className="text-right">
                  <div className="text-[15px] font-semibold text-[#c2410c]">{mn(a.cogs_at_risk_p50)}</div>
                  <div className="text-[10px] text-gray-400">COGS-at-risk</div>
                </div>
              </button>
            ))}
          </div>
        )}

        {data?.pending?.length > 0 && (
          <div className="mt-6 flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 px-4 py-2.5 text-[12px] text-amber-800">
            <AlertTriangle size={15} className="mt-0.5 shrink-0" />
            <span><b>{data.pending.map(p => p.commodity).join(', ')}</b>: exposure mapped, hazard scoring pending — not yet screened.</span>
          </div>
        )}
      </div>

      {selCommodity && <CommodityDrawer commodity={selCommodity} scenario={scenario} horizon={horizon}
        onClose={() => setSelCommodity(null)} onSelectPlot={id => { setSelCommodity(null); setSelPlot(id) }} />}
      {selPlot && <SupplyPlotDrawer plotId={selPlot} onClose={() => setSelPlot(null)} scenario={scenario} horizon={horizon} />}
    </div>
  )
}
