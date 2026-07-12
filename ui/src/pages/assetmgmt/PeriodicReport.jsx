import { useState, useEffect } from 'react'
import { FileText, CheckCircle2, CircleDashed } from 'lucide-react'
import { fetchFunds, fetchPeriodicReport } from '../../api/client'

const mn = n => n == null ? '—' : '€' + (n / 1e6).toFixed(1) + 'm'
const STATUS = {
  computed: { label: 'Computed', cls: 'bg-green-50 text-green-700', Icon: CheckCircle2 },
  partial: { label: 'Partial', cls: 'bg-amber-50 text-amber-700', Icon: CircleDashed },
  not_available: { label: 'Input required', cls: 'bg-gray-100 text-gray-500', Icon: CircleDashed },
}
const fmtVal = v => {
  if (v == null) return null
  if (typeof v === 'object') return Object.entries(v).filter(([, x]) => x != null)
    .map(([k, x]) => `${k.replace(/_/g, ' ')}: ${typeof x === 'number' ? x.toLocaleString() : x}`).join(' · ')
  return String(v)
}

export default function PeriodicReport() {
  const [funds, setFunds] = useState(null)
  const [fund, setFund] = useState(null)
  const [rep, setRep] = useState(null)

  useEffect(() => { fetchFunds().then(d => { setFunds(d.funds || []); if (d.funds?.length) setFund(d.funds[0].fund_id) }).catch(() => setFunds([])) }, [])
  useEffect(() => { if (!fund) return; setRep(null); fetchPeriodicReport(fund).then(setRep).catch(() => setRep({ error: true })) }, [fund])

  return (
    <div className="flex h-full flex-col overflow-y-auto bg-[#f5f5f7] px-8 py-8">
      <header className="mb-5">
        <div className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-[0.12em] text-gray-400">
          <FileText size={13} /> Regulatory filing
        </div>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight text-[#1d1d1f]">SFDR periodic report</h1>
        <p className="mt-2 max-w-2xl text-[15px] text-gray-500">
          The Article 8/9 periodic disclosure (RTS Annex IV/V) that accompanies the annual report. Quantitative
          sections are computed from the golden source; the sections needing the manager's own per-holding
          classification are flagged as inputs, never fabricated.
        </p>
      </header>

      {funds && funds.length > 1 && (
        <div className="mb-4 flex flex-wrap gap-2">
          {funds.map(f => (
            <button key={f.fund_id} onClick={() => setFund(f.fund_id)}
              className={`rounded-full border px-3 py-1.5 text-[12px] font-medium transition ${fund === f.fund_id ? 'border-[#0071e3] bg-[#0071e3]/10 text-[#0071e3]' : 'border-gray-200 text-gray-600 hover:border-gray-300'}`}>
              {f.name}
            </button>
          ))}
        </div>
      )}

      {!rep ? <p className="text-gray-400">loading…</p> : rep.error ? (
        <p className="rounded-xl border border-gray-200 bg-white px-4 py-3 text-[13px] text-gray-500">
          {rep.error === true ? 'No periodic report available.' : rep.error}
        </p>
      ) : (
        <>
          <div className="grid grid-cols-4 gap-4">
            <Stat label="Fund" value={rep.entity.fund_name} sub={`${mn(rep.entity.total_value_eur)} · ${rep.entity.positions} positions`} small />
            <Stat label="Classification" value={rep.entity.sfdr_classification?.replace('_', ' ')} sub={rep.regulatory_basis} small />
            <Stat label="Sections computed" value={`${rep.coverage_summary.computed}/${rep.coverage_summary.sections}`} sub="from the golden source" accent="#1C7A4B" />
            <Stat label="Manager LEI" value={rep.entity.manager_lei || '—'} sub={rep.entity.manager} small />
          </div>

          <section className="mt-5 rounded-2xl border border-gray-200/70 bg-white p-5 shadow-sm">
            <h2 className="text-[13px] font-semibold text-[#1d1d1f]">Periodic disclosure — <span className="font-normal text-gray-400">{rep.regulatory_basis}</span></h2>
            <div className="mt-3 divide-y divide-gray-50">
              {rep.sections.map((s, i) => {
                const m = STATUS[s.status] || STATUS.not_available
                return (
                  <div key={i} className="py-3">
                    <div className="flex items-start justify-between gap-3">
                      <div className="font-medium text-[13px] text-[#1d1d1f]">{s.section}</div>
                      <span className={`inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium ${m.cls}`}><m.Icon size={11} /> {m.label}</span>
                    </div>
                    {fmtVal(s.value) && <div className="mt-1 text-[12px] tabular-nums text-gray-600">{fmtVal(s.value)}</div>}
                    {s.input_required && <div className="mt-1 text-[11px] text-gray-400">needs: {s.input_required}</div>}
                    {s.note && <div className="mt-1 text-[11px] text-gray-400">{s.note}</div>}
                  </div>
                )
              })}
            </div>
          </section>

          <section className="mt-5 rounded-2xl border border-gray-200/70 bg-white p-5 shadow-sm">
            <h2 className="text-[13px] font-semibold text-[#1d1d1f]">Top investments</h2>
            <table className="mt-3 w-full text-[13px]">
              <thead><tr className="border-b border-gray-200 text-left text-[11px] uppercase tracking-wide text-gray-400">
                <th className="py-2 font-medium">Issuer</th><th className="py-2 font-medium">Sector (NACE)</th>
                <th className="py-2 text-right font-medium">Value</th><th className="py-2 text-right font-medium">Weight</th>
              </tr></thead>
              <tbody>
                {rep.top_investments.map((t, i) => (
                  <tr key={i} className="border-b border-gray-50 last:border-0">
                    <td className="py-2 font-medium text-[#1d1d1f]">{t.issuer}<span className="ml-1 text-[11px] font-normal text-gray-400">{t.country}</span></td>
                    <td className="py-2 text-gray-500">{t.sector_nace || '—'}</td>
                    <td className="py-2 text-right tabular-nums text-[#1d1d1f]">{mn(t.value_eur)}</td>
                    <td className="py-2 text-right tabular-nums text-gray-500">{t.weight_pct}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        </>
      )}
    </div>
  )
}

function Stat({ label, value, sub, accent, small }) {
  return (
    <div className="rounded-2xl border border-gray-200/70 bg-white p-4 shadow-sm">
      <div className="text-[11px] uppercase tracking-wide text-gray-400">{label}</div>
      <div className={`mt-1.5 font-semibold tracking-tight ${small ? 'text-base' : 'text-2xl'}`} style={{ color: accent || '#1d1d1f' }}>{value}</div>
      <div className="text-[11px] text-gray-400">{sub}</div>
    </div>
  )
}
