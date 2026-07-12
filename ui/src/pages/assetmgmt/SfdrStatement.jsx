import { useState, useEffect } from 'react'
import { FileCheck2, Download, CheckCircle2, CircleDashed, AlertTriangle, Scale, ShieldCheck } from 'lucide-react'
import { fetchFunds, fetchSfdrStatement, downloadSfdrStatement, saveFilingProfile, fileSfdrStatement } from '../../api/client'

const mn = n => n == null ? '—' : '€' + (n / 1e6).toFixed(1) + 'm'

/** The gate between a computed statement and a submittable one: the reporting
 *  entity's LEI + contact. The LEI is validated server-side against GLEIF. */
function FilingReadiness({ readiness, onSaved }) {
  const [lei, setLei] = useState('')
  const [email, setEmail] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  if (!readiness) return null

  if (readiness.ready_to_file) {
    return (
      <div className="mt-3 flex items-center gap-2 rounded-xl border border-green-200 bg-green-50 px-4 py-3 text-[13px] font-medium text-green-800">
        <ShieldCheck size={16} /> Ready to file — reporting entity identified and the statement is complete.
      </div>
    )
  }

  const save = async () => {
    setBusy(true); setErr(null)
    try {
      const r = await saveFilingProfile({ lei: lei.trim().toUpperCase(), filing_contact_email: email || undefined })
      if (r.error) { setErr(r.detail || 'Could not validate LEI'); return }
      onSaved?.()
    } catch (e) { setErr(e.message || 'Save failed') } finally { setBusy(false) }
  }

  return (
    <div className="mt-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3">
      <div className="flex items-center gap-1.5 text-[12px] font-semibold text-amber-800">
        <AlertTriangle size={14} /> Not yet submittable — supply the reporting entity to file: {readiness.missing.join(' · ')}
      </div>
      <div className="mt-2 flex flex-wrap items-end gap-2">
        <div>
          <label className="text-[10px] uppercase tracking-wide text-amber-700">Manager LEI (20 chars)</label>
          <input value={lei} onChange={e => setLei(e.target.value)} placeholder="9695003YCOLOMW6OMD54" maxLength={20}
            className="mt-0.5 block w-[220px] rounded-lg border border-amber-300 bg-white px-2.5 py-1.5 font-mono text-[12px] outline-none focus:border-amber-500" />
        </div>
        <div>
          <label className="text-[10px] uppercase tracking-wide text-amber-700">Filing contact email</label>
          <input value={email} onChange={e => setEmail(e.target.value)} placeholder="compliance@firm.com"
            className="mt-0.5 block w-[200px] rounded-lg border border-amber-300 bg-white px-2.5 py-1.5 text-[12px] outline-none focus:border-amber-500" />
        </div>
        <button onClick={save} disabled={busy || lei.trim().length !== 20}
          className="rounded-lg bg-amber-700 px-3 py-1.5 text-[12px] font-medium text-white transition hover:bg-amber-800 disabled:bg-amber-300">
          {busy ? 'Validating…' : 'Validate & save'}
        </button>
      </div>
      {err && <p className="mt-1.5 text-[11px] text-red-600">{err}</p>}
      <p className="mt-1.5 text-[11px] text-amber-700">The LEI is checked against the GLEIF register; the legal name is pulled from it automatically.</p>
    </div>
  )
}

const METHOD = {
  computed: { label: 'Computed', cls: 'bg-green-50 text-green-700', Icon: CheckCircle2 },
  estimated: { label: 'Estimated', cls: 'bg-blue-50 text-blue-700', Icon: CircleDashed },
  partial: { label: 'Partial', cls: 'bg-amber-50 text-amber-700', Icon: CircleDashed },
  not_available: { label: 'Input required', cls: 'bg-gray-100 text-gray-500', Icon: CircleDashed },
  not_applicable: { label: 'Not applicable', cls: 'bg-gray-50 text-gray-400', Icon: CircleDashed },
}

function IndicatorRows({ items }) {
  return items.map(ind => {
    const m = METHOD[ind.method] || METHOD.not_available
    return (
      <tr key={ind.number} className="border-b border-gray-50 last:border-0 align-top">
        <td className="py-2.5 text-gray-400">{ind.number}</td>
        <td className="py-2.5"><div className="font-medium text-[#1d1d1f]">{ind.metric}</div>
          <div className="text-[11px] text-gray-400">{ind.area} · {ind.unit}</div></td>
        <td className="py-2.5 text-right tabular-nums text-[#1d1d1f]">{fmtVal(ind.value)}
          {ind.change_pct != null && (
            <div className={`text-[10px] font-medium ${ind.change_pct <= 0 ? 'text-green-600' : 'text-red-600'}`}>
              {ind.change_pct <= 0 ? '▼' : '▲'} {Math.abs(ind.change_pct)}% vs prior
            </div>)}
        </td>
        <td className="py-2.5 text-right text-[11px] text-gray-400">{ind.coverage_pct == null ? '—' : `${ind.coverage_pct}%`}</td>
        <td className="py-2.5">
          <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium ${m.cls}`}><m.Icon size={11} /> {m.label}</span>
          {ind.input_required && <div className="mt-1 text-[11px] text-gray-400">{ind.method === 'not_applicable' ? '' : 'needs: '}{ind.input_required}</div>}
        </td>
      </tr>
    )
  })
}

const fmtVal = v => {
  if (v == null) return '—'
  if (typeof v === 'object') return Object.entries(v).map(([k, x]) => `${k.replace(/_/g, ' ')}: ${typeof x === 'number' ? x.toLocaleString() : x}`).join(' · ')
  if (typeof v === 'number') return v.toLocaleString()
  return String(v)
}

export default function SfdrStatement({ onGoto }) {
  const [funds, setFunds] = useState(null)
  const [fund, setFund] = useState(null)
  const [st, setSt] = useState(null)
  const [fileMsg, setFileMsg] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => { fetchFunds().then(d => { setFunds(d.funds || []); if (d.funds?.length) setFund(d.funds[0].fund_id) }).catch(() => setFunds([])) }, [])
  useEffect(() => { if (!fund) return; setSt(null); fetchSfdrStatement(fund).then(setSt).catch(() => setSt({ error: true })) }, [fund])

  const cov = st?.coverage_summary
  const fundName = funds?.find(f => f.fund_id === fund)?.name

  return (
    <div className="flex h-full flex-col overflow-y-auto bg-[#f5f5f7] px-8 py-8">
      <header className="mb-5 flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-[0.12em] text-gray-400">
            <FileCheck2 size={13} /> Regulatory filing
          </div>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight text-[#1d1d1f]">SFDR PAI statement</h1>
          <p className="mt-2 max-w-2xl text-[15px] text-gray-500">
            The mandatory Principal Adverse Impact statement, in the shape the regulation defines
            (<span className="text-gray-600">SFDR RTS, Annex I, Table 1</span>). Every required line is shown — the ones
            we can compute are filled with their coverage and source; the rest are flagged with the exact input still
            needed. Nothing is invented, nothing is silently dropped.
          </p>
        </div>
        {st && !st.error && (
          <div className="flex shrink-0 items-center gap-2">
            <button onClick={async () => { setBusy(true); setFileMsg(null); try { const r = await fileSfdrStatement(fund); setFileMsg(r.filed || 'Filed'); fetchSfdrStatement(fund).then(setSt) } catch (e) { setFileMsg(e.message) } finally { setBusy(false) } }}
              disabled={busy || !st.filing_readiness?.ready_to_file}
              title={st.filing_readiness?.ready_to_file ? 'Freeze this as the official filing for its reference year' : 'Complete the reporting-entity identity first'}
              className="flex items-center gap-2 rounded-xl border border-gray-300 bg-white px-4 py-2.5 text-[13px] font-medium text-[#1d1d1f] shadow-sm transition hover:border-gray-400 disabled:opacity-40">
              <FileCheck2 size={15} /> File statement
            </button>
            <button onClick={async () => { setBusy(true); try { await downloadSfdrStatement(fund, fundName) } finally { setBusy(false) } }}
              className="flex items-center gap-2 rounded-xl bg-[#0071e3] px-4 py-2.5 text-[13px] font-medium text-white shadow-sm transition hover:bg-[#0077ed] disabled:bg-gray-300">
              <Download size={15} /> {busy ? '…' : 'Download filing (.xlsx)'}
            </button>
          </div>
        )}
      </header>
      {fileMsg && <p className="mb-3 rounded-lg bg-green-50 px-3 py-2 text-[12px] text-green-800">{fileMsg}</p>}

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

      {!st ? <p className="text-gray-400">loading…</p> : st.error ? <p className="text-gray-400">No statement available for this fund.</p> : (
        <>
          <div className="grid grid-cols-4 gap-4">
            <Stat label="Fund" value={st.entity.fund_name} sub={`${mn(st.entity.total_value_eur)} · ${st.entity.positions} positions`} small />
            <Stat label="Computed" value={`${cov.computed}/${cov.mandatory_indicators}`} sub="mandatory indicators" accent="#1C7A4B" />
            <Stat label="Awaiting input" value={cov.not_available + cov.partial} sub="surfaced, not faked" accent="#9A5B08" />
            <Stat label="Emissions coverage" value={cov.emissions_coverage_pct == null ? '—' : `${cov.emissions_coverage_pct}%`}
              sub={cov.emissions_estimated_pct ? `${cov.emissions_estimated_pct}% of it estimated` : 'all reported, none estimated'} accent="#0071e3" />
          </div>

          <p className="mt-3 rounded-xl border border-gray-200 bg-white px-4 py-3 text-[12px] text-gray-600">{cov.filing_readiness}</p>

          {/* filing header: reference period + declaration + what the download contains */}
          <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-1 rounded-xl border border-gray-200 bg-white px-4 py-3 text-[12px] text-gray-600">
            <span><b className="text-[#1d1d1f]">Reference period:</b> {st.summary?.reference_period}</span>
            <span><b className="text-[#1d1d1f]">PAI considered:</b> Yes</span>
            {st.entity.manager_lei && <span><b className="text-[#1d1d1f]">Manager LEI:</b> {st.entity.manager_lei} · {st.entity.manager_legal_name}</span>}
            <span className="text-gray-400">Download = Summary + PAI statement (RTS Table 1) + Provenance appendix</span>
          </div>

          {/* filing readiness — the gate between "computed" and "submittable" */}
          <FilingReadiness readiness={st.filing_readiness} onSaved={() => fetchSfdrStatement(fund).then(setSt)} />

          {/* the mandated indicator table */}
          <section className="mt-5 rounded-2xl border border-gray-200/70 bg-white p-5 shadow-sm">
            <h2 className="text-[13px] font-semibold text-[#1d1d1f]">Principal Adverse Impact indicators
              <span className="font-normal text-gray-400"> — {st.regulatory_basis}</span>
              {st.comparison?.available && <span className="ml-2 rounded-full bg-gray-100 px-2 py-0.5 text-[10px] font-medium text-gray-500">vs FY{st.comparison.prior_reference_year}</span>}</h2>
            <table className="mt-3 w-full text-[13px]">
              <thead><tr className="border-b border-gray-200 text-left text-[11px] uppercase tracking-wide text-gray-400">
                <th className="py-2 font-medium">#</th><th className="py-2 font-medium">Adverse impact indicator</th>
                <th className="py-2 text-right font-medium">Value</th><th className="py-2 text-right font-medium">Coverage</th>
                <th className="py-2 font-medium">Status / input required</th>
              </tr></thead>
              <tbody>
                <tr><td colSpan={5} className="pt-2 pb-1 text-[10px] font-semibold uppercase tracking-wide text-gray-400">Investee companies (1–14)</td></tr>
                <IndicatorRows items={st.indicators} />
                {st.sovereign_indicators?.length > 0 && <>
                  <tr><td colSpan={5} className="pt-4 pb-1 text-[10px] font-semibold uppercase tracking-wide text-gray-400">Sovereign & supranational (15–16){st.sovereign_countries?.length ? ` · ${st.sovereign_countries.join(', ')}` : ''}</td></tr>
                  <IndicatorRows items={st.sovereign_indicators} />
                </>}
                {st.real_estate_indicators?.length > 0 && <>
                  <tr><td colSpan={5} className="pt-4 pb-1 text-[10px] font-semibold uppercase tracking-wide text-gray-400">Real estate (17–18)</td></tr>
                  <IndicatorRows items={st.real_estate_indicators} />
                </>}
              </tbody>
            </table>
          </section>

          {/* taxonomy */}
          <section className="mt-5 rounded-2xl border border-gray-200/70 bg-white p-5 shadow-sm">
            <h2 className="flex items-center gap-1.5 text-[13px] font-semibold text-[#1d1d1f]"><Scale size={14} /> EU Taxonomy</h2>
            <div className="mt-3 grid grid-cols-3 gap-4">
              <Mini label="Assessable (has NACE)" value={`${st.taxonomy.assessable_pct}%`} />
              <Mini label="Taxonomy-eligible" value={fmtVal(st.taxonomy.taxonomy_eligible_pct)} />
              <Mini label="Taxonomy-aligned" value="Not asserted" />
            </div>
            <p className="mt-3 flex items-start gap-2 rounded-lg bg-blue-50 px-3 py-2 text-[11px] leading-snug text-blue-800">
              <AlertTriangle size={13} className="mt-0.5 shrink-0" /> {st.taxonomy.alignment_note} Input required: {st.taxonomy.input_required}.
            </p>
          </section>

          <p className="mt-4 text-[11px] text-gray-400">
            {st.provenance.scope_note} Generated {new Date(st.provenance.generated_at).toLocaleString()} · source: {st.provenance.source}.
          </p>
        </>
      )}
    </div>
  )
}

function Stat({ label, value, sub, accent, small }) {
  return (
    <div className="rounded-2xl border border-gray-200/70 bg-white p-4 shadow-sm">
      <div className="text-[11px] uppercase tracking-wide text-gray-400">{label}</div>
      <div className={`mt-1.5 font-semibold tracking-tight ${small ? 'text-lg' : 'text-2xl'}`} style={{ color: accent || '#1d1d1f' }}>{value}</div>
      <div className="text-[11px] text-gray-400">{sub}</div>
    </div>
  )
}

function Mini({ label, value }) {
  return (
    <div className="rounded-xl bg-[#f5f5f7] px-3 py-2.5">
      <div className="text-[10px] uppercase tracking-wide text-gray-400">{label}</div>
      <div className="mt-1 text-[15px] font-semibold text-[#1d1d1f]">{value}</div>
    </div>
  )
}
