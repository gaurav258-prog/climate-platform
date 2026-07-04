import { useState, useEffect, useMemo, useCallback } from 'react'
import { Table2, ArrowUpDown } from 'lucide-react'
import ContextBar from '../../components/ContextBar'
import SupplyPlotDrawer, { HAZ_COLOR } from '../../components/SupplyPlotDrawer'
import UploadPanel from '../../components/UploadPanel'
import { fetchSupplyPortfolio, uploadSupplyPlots } from '../../api/client'

const mn = n => '€' + ((n || 0) / 1e6).toFixed(1) + 'm'
const BUCKET = { VH: '#c81e1e', H: '#c2410c', M: '#b56a00', L: '#1a8a4a' }
const TEMPLATE_COLUMNS = ['plot_name', 'latitude', 'longitude', 'commodity', 'annual_spend_eur', 'region', 'country']

// The sourcing book — every plot as a row, scored per hazard, sortable. The
// agriculture analogue of the banking Portfolio screen.
export default function SourcingBook() {
  const [scenario, setScenario] = useState('baseline')
  const [horizon, setHorizon] = useState('current')
  const [port, setPort] = useState(null)
  const [sel, setSel] = useState(null)
  const [sort, setSort] = useState({ key: 'spend_eur', dir: -1 })

  const reload = useCallback(() => {
    fetchSupplyPortfolio({ scenario, horizon }).then(setPort).catch(() => setPort(null))
  }, [scenario, horizon])
  useEffect(() => { setPort(null); reload() }, [reload])

  const rows = useMemo(() => {
    const ps = [...(port?.plots || [])]
    ps.sort((a, b) => {
      const va = a[sort.key] ?? -1, vb = b[sort.key] ?? -1
      if (typeof va === 'string') return sort.dir * va.localeCompare(vb)
      return sort.dir * (va - vb)
    })
    return ps
  }, [port, sort])

  const th = (key, label, right) => (
    <th onClick={() => setSort(s => ({ key, dir: s.key === key ? -s.dir : -1 }))}
      className={`cursor-pointer select-none py-2 text-[11px] font-medium uppercase tracking-wide text-gray-400 hover:text-gray-600 ${right ? 'text-right' : 'text-left'}`}>
      <span className="inline-flex items-center gap-1">{label}<ArrowUpDown size={11} className="opacity-40" /></span>
    </th>
  )

  return (
    <div className="flex h-full flex-col bg-[#f5f5f7]">
      <ContextBar scenario={scenario} horizon={horizon} onScenario={setScenario} onHorizon={setHorizon}
        vintage="2024-10-29" label="Agriculture · Terra Foods (demo)" />
      <div className="flex-1 overflow-y-auto px-8 py-8">
        <header className="mb-5 flex items-end justify-between gap-4">
          <div>
            <div className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-[0.12em] text-gray-400">
              <Table2 size={13} /> Sourcing book
            </div>
            <h1 className="mt-2 text-3xl font-semibold tracking-tight text-[#1d1d1f]">Every plot, scored</h1>
            <p className="mt-2 max-w-2xl text-[15px] text-gray-500">
              Your whole sourcing book — each plot projected against its hazard and rolled into cost-of-goods.
              Click any row to trace it to the golden source.
            </p>
          </div>
          <UploadPanel uploadFn={uploadSupplyPlots} templateColumns={TEMPLATE_COLUMNS}
            templateFilename="sourcing_plots_template.csv" label="Import plots" onUploaded={reload} />
        </header>

        {!port ? <p className="text-gray-400">loading…</p> : (
          <div className="overflow-hidden rounded-2xl border border-gray-200/70 bg-white shadow-sm">
            <table className="w-full">
              <thead className="border-b border-gray-100 px-4">
                <tr className="px-4">
                  <th className="py-2 pl-5 text-left text-[11px] font-medium uppercase tracking-wide text-gray-400">Commodity</th>
                  {th('region', 'Region')}
                  {th('eudr_status', 'EUDR')}
                  {th('hazard_score', 'Hazard', true)}
                  {th('spend_eur', 'Spend', true)}
                  <th className="py-2 pr-5"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {rows.map(p => (
                  <tr key={p.plot_id} onClick={() => setSel(p.plot_id)} className="cursor-pointer hover:bg-gray-50">
                    <td className="py-2.5 pl-5">
                      <div className="flex items-center gap-2 text-[13px] font-medium text-[#1d1d1f]">
                        {p.commodity}
                        {p.eudr_covered && <span className="rounded-full bg-emerald-50 px-1.5 py-0.5 text-[9px] font-semibold text-emerald-600">EUDR</span>}
                      </div>
                    </td>
                    <td className="py-2.5 text-[12px] text-gray-500">{p.region} · {p.country}</td>
                    <td className="py-2.5 text-[11px] text-gray-500">{p.eudr_status}</td>
                    <td className="py-2.5 text-right">
                      {p.hazard_score != null ? (
                        <span className="inline-flex items-center gap-1.5">
                          <span className="text-[12px]" style={{ color: HAZ_COLOR[p.top_hazard] }}>{p.top_hazard}</span>
                          <span className="rounded px-1.5 py-0.5 text-[11px] font-semibold text-white" style={{ background: BUCKET[p.bucket] || '#9ca3af' }}>{p.hazard_score}</span>
                        </span>
                      ) : <span className="text-[11px] text-gray-400">no score</span>}
                    </td>
                    <td className="py-2.5 text-right text-[13px] font-medium text-[#1d1d1f]">{mn(p.spend_eur)}</td>
                    <td className="py-2.5 pr-5 text-right text-gray-300">›</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
      {sel && <SupplyPlotDrawer plotId={sel} onClose={() => setSel(null)} scenario={scenario} horizon={horizon} />}
    </div>
  )
}
