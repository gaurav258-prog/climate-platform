import { useState, useEffect } from 'react'
import { FileText, Download, FileSpreadsheet, Check, X, AlertTriangle } from 'lucide-react'
import ContextBar from '../../components/ContextBar'
import { HAZ_COLOR } from '../../components/SupplyPlotDrawer'
import { fetchSupplyDisclosure, downloadFile } from '../../api/client'

const mn = n => '€' + ((n || 0) / 1e6).toFixed(1) + 'm'

// EUDR overlay ("deforestation-free AND climate-viable?") + CSRD physical-risk pack,
// generated from the procurement book. The agriculture analogue of banking Reports.
export default function SupplyDisclosure() {
  const [scenario, setScenario] = useState('baseline')
  const [horizon, setHorizon] = useState('current')
  const [d, setD] = useState(null)

  useEffect(() => {
    setD(null)
    fetchSupplyDisclosure({ scenario, horizon }).then(setD).catch(() => setD(null))
  }, [scenario, horizon])

  const exportCsv = () => {
    if (!d) return
    const rows = [['commodity', 'hazard', 'avg_hazard', 'spend_eur', 'cogs_at_risk_p50', 'cogs_at_risk_p90', 'calibration', 'status'],
      ...d.csrd.map(c => [c.commodity, c.hazard || '', c.avg_hazard ?? '', c.spend_eur, c.cogs_at_risk_p50 ?? '', c.cogs_at_risk_p90 ?? '', c.calibration, c.status])]
    const csv = rows.map(r => r.join(',')).join('\n')
    const a = document.createElement('a')
    a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }))
    a.download = `tellumen-csrd-supply-${scenario}-${horizon}.csv`; a.click()
  }

  const s = d?.eudr?.summary

  return (
    <div className="flex h-full flex-col bg-[#f5f5f7]">
      <ContextBar scenario={scenario} horizon={horizon} onScenario={setScenario} onHorizon={setHorizon}
        vintage="2024-10-29" label="Agriculture · Terra Foods (demo)" />
      <div className="flex-1 overflow-y-auto px-8 py-8">
        <header className="mb-5 flex items-start justify-between">
          <div>
            <div className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-[0.12em] text-gray-400">
              <FileText size={13} /> Disclosure
            </div>
            <h1 className="mt-2 text-3xl font-semibold tracking-tight text-[#1d1d1f]">EUDR + CSRD, from the book</h1>
            <p className="mt-2 max-w-2xl text-[15px] text-gray-500">
              Two compliance headaches, one record: every plot's deforestation-free status <b>and</b> its
              forward climate-viability, plus a CSRD physical-risk pack — straight from the golden source.
            </p>
          </div>
          <div className="mt-6 flex shrink-0 items-center gap-2">
            <button onClick={() => downloadFile(`/v1/supply/disclosure.xlsx?scenario=${scenario}&horizon=${horizon}`, `tellumen-csrd-supply-${scenario}-${horizon}.xlsx`)}
              className="inline-flex items-center gap-2 rounded-full bg-[#0071e3] px-4 py-2 text-[13px] font-medium text-white">
              <FileSpreadsheet size={15} /> Export Excel
            </button>
            <button onClick={exportCsv} className="inline-flex items-center gap-2 rounded-full border border-gray-200 bg-white px-4 py-2 text-[13px] font-medium text-[#1d1d1f] hover:border-gray-300">
              <Download size={15} /> Export CSV
            </button>
          </div>
        </header>

        {!d ? <p className="text-gray-400">loading…</p> : (
          <>
            {/* EUDR overlay */}
            <section className="rounded-2xl border border-gray-200/70 bg-white p-5 shadow-sm">
              <h2 className="text-[13px] font-semibold text-[#1d1d1f]">EUDR overlay <span className="font-normal text-gray-400">— deforestation-free ✓ and climate-viable?</span></h2>
              <div className="mt-3 grid grid-cols-4 gap-4">
                <Stat label="Covered plots" value={s.covered_plots} />
                <Stat label="Deforestation-free" value={s.deforestation_free} accent="#1a8a4a" />
                <Stat label="Climate-at-risk" value={s.climate_at_risk} accent="#c2410c" />
                <Stat label="Unscored" value={s.unscored} accent="#b56a00" />
              </div>
              <div className="mt-4 divide-y divide-gray-100">
                {d.eudr.plots.filter(p => p.eudr_covered).map((p, i) => (
                  <div key={i} className="flex items-center justify-between py-2 text-[12px]">
                    <span className="text-[#1d1d1f]">{p.commodity} · <span className="text-gray-400">{p.region}, {p.country}</span></span>
                    <span className="flex items-center gap-4">
                      <span className="inline-flex items-center gap-1 text-gray-500">
                        {p.eudr_status === 'compliant' ? <Check size={13} className="text-emerald-600" /> : <X size={13} className="text-red-500" />} deforestation-free
                      </span>
                      <span className="inline-flex items-center gap-1 font-medium" style={{ color: p.scored ? (p.climate_viable ? '#1a8a4a' : '#c2410c') : '#9ca3af' }}>
                        {p.scored ? (p.climate_viable ? <Check size={13} /> : <AlertTriangle size={13} />) : '—'}
                        {p.scored ? (p.climate_viable ? 'climate-viable' : `climate-at-risk (${p.hazard_score})`) : 'not scored'}
                      </span>
                    </span>
                  </div>
                ))}
              </div>
            </section>

            {/* CSRD physical risk */}
            <section className="mt-6 rounded-2xl border border-gray-200/70 bg-white p-5 shadow-sm">
              <h2 className="text-[13px] font-semibold text-[#1d1d1f]">CSRD physical-risk — COGS-at-risk by commodity
                <span className="font-normal text-gray-400"> · {scenario} · {horizon}</span></h2>
              <div className="mt-3 divide-y divide-gray-100">
                {d.csrd.map(c => (
                  <div key={c.commodity} className="flex items-center justify-between py-2 text-[12px]">
                    <span className="flex items-center gap-2 text-[#1d1d1f]">
                      {c.commodity}
                      {c.hazard && <span style={{ color: HAZ_COLOR[c.hazard] }}>{c.hazard}</span>}
                      {c.status === 'scored' && (c.calibration === 'backtested'
                        ? <span className="rounded-full bg-blue-50 px-1.5 py-0.5 text-[9px] font-semibold text-[#0071e3]">backtested</span>
                        : <span className="rounded-full bg-gray-100 px-1.5 py-0.5 text-[9px] font-medium text-gray-500">indicative</span>)}
                    </span>
                    <span className="text-right">
                      {c.status === 'scored'
                        ? <><b className="text-[#c2410c]">{mn(c.cogs_at_risk_p50)}</b> <span className="text-gray-400">P90 {mn(c.cogs_at_risk_p90)}</span></>
                        : <span className="rounded-full bg-gray-100 px-2 py-0.5 text-[10px] text-gray-500">€ pending</span>}
                    </span>
                  </div>
                ))}
              </div>
              <p className="mt-4 border-t border-gray-100 pt-3 text-[11px] text-gray-400">
                Every figure carries its impact-function version and hazard model vintage.
                <b> Backtested</b> commodities reproduce a real event; <b>indicative</b> use v0 defaults.
                Frost (a coffee driver) is pending the CDS daily-min data fix.
              </p>
            </section>
          </>
        )}
      </div>
    </div>
  )
}

function Stat({ label, value, accent }) {
  return (
    <div className="rounded-xl border border-gray-200/70 p-3">
      <div className="text-[11px] uppercase tracking-wide text-gray-400">{label}</div>
      <div className="mt-1 text-2xl font-semibold" style={{ color: accent || '#1d1d1f' }}>{value}</div>
    </div>
  )
}
