import { useState, useEffect, useCallback } from 'react'
import { Upload, CheckCircle2, AlertTriangle, MapPin, Building2, Loader2, ArrowRight, Info, FileCheck2 } from 'lucide-react'
import { fetchFunds, onboardHoldings, downloadHoldingsTemplate } from '../../api/client'

const mn = n => n == null ? '—' : '€' + (n / 1e6).toFixed(1) + 'm'

// A small, real, mixed sample so the coverage story is honest end-to-end:
// large caps that resolve, plus one deliberately-unmatched line.
// Columns after the value are OPTIONAL — supply the issuer data you already
// hold (NACE, revenue, scope 1/2/3) to fill more of the SFDR statement.
const SAMPLE = `US0378331005, 5000000, 26.20, 383000000000, 55000, 0, 16200000, 2900000000000
DE0007164600, 4000000, 62.01, 31200000000, 30000, 45000, 4300000, 210000000000
FR0000131104, 3000000, 64.19, 50000000000, 60000, 120000, 7000000, 95000000000
CH0038863350, 3500000
ZZ0000000000, 1000000`

const _num = s => { const n = Number((s || '').replace(/[€,_\s]/g, '')); return Number.isFinite(n) && s ? n : null }

// Every intake field, by kind, so a header-mapped column is coerced correctly.
const NUM_FIELDS = new Set(['market_value_eur', 'market_value', 'revenue_eur',
  'scope1_tco2e', 'scope2_tco2e', 'scope3_tco2e', 'evic_eur', 'reporting_year',
  'non_renewable_energy_pct', 'energy_intensity_gwh_per_meur', 'emissions_to_water_tonnes',
  'hazardous_waste_tonnes', 'gender_pay_gap_pct', 'board_female_pct',
  'taxonomy_eligible_pct', 'taxonomy_aligned_pct'])
const BOOL_FIELDS = new Set(['biodiversity_sensitive_ops', 'ungc_oecd_violation',
  'ungc_oecd_no_monitoring', 'controversial_weapons', 'taxonomy_dnsh_ok', 'taxonomy_min_safeguards_ok'])
const STR_FIELDS = new Set(['currency', 'nace_code', 'sector', 'asset_class'])
const KNOWN_FIELDS = new Set([...NUM_FIELDS, ...BOOL_FIELDS, ...STR_FIELDS, 'isin'])
const _bool = (s) => ['1', 'true', 'yes', 'y', 't'].includes(String(s).trim().toLowerCase())

/** Parse holdings from pasted text. Two modes:
 *  - HEADER mode: if the first non-comment line names columns (contains "isin"),
 *    map every known column by name — so ESG PAI 5-14, currency, EVIC, Taxonomy +
 *    DNSH, reporting_year etc. can all be supplied. Matches the CSV template.
 *  - LEGACY positional: "ISIN, value[, NACE, revenue, s1, s2, s3, evic]".
 *  A line needs an ISIN and either market_value_eur or market_value (+ currency). */
function parseHoldings(text) {
  const rows = [], errors = []
  const lines = text.split('\n').map(l => l.trim())
    .filter(l => l && !l.startsWith('#'))
  if (!lines.length) return { rows, errors }

  const firstCols = lines[0].split(/[,\t]/).map(s => s.trim().toLowerCase())
  const isHeader = firstCols.includes('isin')
  const header = isHeader ? firstCols : null
  const body = isHeader ? lines.slice(1) : lines

  body.forEach((line, i) => {
    const p = line.split(/[,\t]/).map(s => s.trim())
    const h = { asset_class: 'equity' }
    if (header) {
      header.forEach((col, idx) => {
        const raw = p[idx]
        if (raw == null || raw === '' || !KNOWN_FIELDS.has(col)) return
        if (col === 'isin') h.isin = raw.toUpperCase()
        else if (NUM_FIELDS.has(col)) { const n = _num(raw); if (n != null) h[col] = n }
        else if (BOOL_FIELDS.has(col)) h[col] = _bool(raw)
        else h[col] = raw
      })
    } else {
      h.isin = (p[0] || '').toUpperCase()
      if (_num(p[1]) != null) h.market_value_eur = _num(p[1])
      if (p[2]) h.nace_code = p[2]
      if (_num(p[3]) != null) h.revenue_eur = _num(p[3])
      if (_num(p[4]) != null) h.scope1_tco2e = _num(p[4])
      if (_num(p[5]) != null) h.scope2_tco2e = _num(p[5])
      if (_num(p[6]) != null) h.scope3_tco2e = _num(p[6])
      if (_num(p[7]) != null) h.evic_eur = _num(p[7])
    }
    const ln = (header ? i + 2 : i + 1)
    if (!h.isin || h.isin.length !== 12) { errors.push(`Line ${ln}: "${p[0]}" is not a 12-char ISIN`); return }
    if (!(h.market_value_eur > 0) && !(h.market_value > 0)) {
      errors.push(`Line ${ln}: ${h.isin} needs market_value_eur, or market_value + currency`); return
    }
    rows.push(h)
  })
  return { rows, errors }
}

export default function FundOnboarding({ onGoto }) {
  const [funds, setFunds] = useState(null)
  const [fund, setFund] = useState(null)
  const [raw, setRaw] = useState('')
  const [report, setReport] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  useEffect(() => {
    fetchFunds().then(d => {
      setFunds(d.funds || [])
      if (d.funds?.length) setFund(d.funds[0].fund_id)
    }).catch(() => setFunds([]))
  }, [])

  const { rows, errors } = parseHoldings(raw)

  const submit = useCallback(async () => {
    if (!fund || !rows.length) return
    setBusy(true); setErr(null); setReport(null)
    try {
      const r = await onboardHoldings(fund, { holdings: rows })
      setReport(r)
    } catch (e) {
      setErr(e.message || 'Upload failed')
    } finally { setBusy(false) }
  }, [fund, rows])

  const cov = report?.coverage
  const resolved = (report?.resolutions || []).filter(r => r.status === 'resolved' || r.status === 'cached')

  return (
    <div className="flex h-full flex-col overflow-y-auto bg-[#f5f5f7] px-8 py-8">
      <header className="mb-5">
        <div className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-[0.12em] text-gray-400">
          <Upload size={13} /> Onboarding
        </div>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight text-[#1d1d1f]">Upload holdings by ISIN</h1>
        <p className="mt-2 max-w-2xl text-[15px] text-gray-500">
          Give us only what you have — an <b>ISIN and a value</b> per position. We resolve each to its
          issuer from the open <b>GLEIF</b> LEI register, locate the issuer's footprint, score it against the
          golden source, and report <b>honest coverage</b> — what matched, what didn't, and which inputs are
          still needed. No paid data vendor underneath.
        </p>
      </header>

      <div className="grid grid-cols-5 gap-6">
        {/* ── input ── */}
        <section className="col-span-2 space-y-4">
          <div className="rounded-2xl border border-gray-200/70 bg-white p-5 shadow-sm">
            <label className="text-[11px] font-semibold uppercase tracking-wide text-gray-400">Fund</label>
            <div className="mt-2 flex flex-wrap gap-2">
              {(funds || []).map(f => (
                <button key={f.fund_id} onClick={() => setFund(f.fund_id)}
                  className={`rounded-full border px-3 py-1.5 text-[12px] font-medium transition ${
                    fund === f.fund_id ? 'border-[#0071e3] bg-[#0071e3]/10 text-[#0071e3]' : 'border-gray-200 text-gray-600 hover:border-gray-300'}`}>
                  {f.name}
                </button>
              ))}
              {funds && !funds.length && <span className="text-[12px] text-gray-400">No funds for this org.</span>}
            </div>

            <div className="mt-4 flex items-center justify-between">
              <label className="text-[11px] font-semibold uppercase tracking-wide text-gray-400">Holdings — one per line. <span className="font-normal normal-case text-gray-400">Quick: <span className="font-mono">ISIN, value €</span>. Full: paste the template's header row to supply currency, EVIC, ESG PAI 5–14, Taxonomy + DNSH.</span></label>
              <div className="flex items-center gap-3">
                <button onClick={() => downloadHoldingsTemplate()} className="text-[11px] font-medium text-[#0071e3] hover:underline">Download template</button>
                <button onClick={() => setRaw(SAMPLE)} className="text-[11px] font-medium text-[#0071e3] hover:underline">Load sample book</button>
              </div>
            </div>
            <textarea value={raw} onChange={e => setRaw(e.target.value)} rows={9} spellCheck={false}
              placeholder={'US0378331005, 5000000\nFR0000131104, 3000000\n\n— or with a header row (any subset of template columns) —\nisin,market_value,currency,revenue_eur,scope1_tco2e,evic_eur\nUS5949181045,6000000,USD,211900000000,290000,2700000000000'}
              className="mt-2 w-full resize-y rounded-xl border border-gray-200 bg-[#fafafa] p-3 font-mono text-[12px] text-[#1d1d1f] outline-none focus:border-[#0071e3]" />

            {errors.length > 0 && (
              <div className="mt-2 space-y-0.5 text-[11px] text-amber-700">
                {errors.map((e, i) => <div key={i}>• {e}</div>)}
              </div>
            )}

            <button onClick={submit} disabled={busy || !fund || !rows.length}
              className="mt-4 flex w-full items-center justify-center gap-2 rounded-xl bg-[#0071e3] px-4 py-2.5 text-[13px] font-medium text-white transition hover:bg-[#0077ed] disabled:cursor-not-allowed disabled:bg-gray-300">
              {busy ? <><Loader2 size={15} className="animate-spin" /> Resolving against GLEIF, locating footprints…</>
                    : <>Onboard {rows.length || ''} holding{rows.length === 1 ? '' : 's'} <ArrowRight size={15} /></>}
            </button>
            {busy && <p className="mt-2 text-center text-[11px] text-gray-400">New issuers are geocoded and scored live — this can take a few seconds each.</p>}
            {err && <p className="mt-2 text-[12px] text-red-600">{err}</p>}
          </div>

          <div className="flex items-start gap-2 rounded-xl border border-gray-200 bg-white px-3 py-2.5 text-[11px] leading-snug text-gray-500">
            <Info size={13} className="mt-0.5 shrink-0 text-gray-400" />
            <span>Every resolution is stamped with its source (GLEIF) and vintage, and logged — the audit trail an SFDR filing cites. Unmatched ISINs are excluded and surfaced, never fabricated.</span>
          </div>
        </section>

        {/* ── coverage report ── */}
        <section className="col-span-3">
          {!report ? (
            <div className="flex h-full min-h-[300px] items-center justify-center rounded-2xl border border-dashed border-gray-300 text-[13px] text-gray-400">
              Coverage report appears here after upload.
            </div>
          ) : (
            <div className="space-y-4">
              <div className="grid grid-cols-4 gap-3">
                <Stat icon={CheckCircle2} label="Match rate" value={`${cov.match_rate_pct}%`}
                  sub={`${cov.matched}/${report.distinct_isins} ISINs resolved`} accent="#1C7A4B" />
                <Stat icon={Building2} label="Positions" value={report.positions_created}
                  sub="value-weighted into the fund" />
                <Stat icon={MapPin} label="Footprints" value={cov.footprints.seeded + cov.footprints.already}
                  sub={cov.footprints.failed ? `${cov.footprints.failed} could not geocode` : 'HQ located & scored'} accent="#c2410c" />
                <Stat icon={FileCheck2} label="Issuer data" value={(cov.client_enriched?.sector || 0) + (cov.client_enriched?.emissions || 0) + (cov.client_enriched?.esg || 0)}
                  sub={`${cov.client_enriched?.emissions || 0} emissions · ${cov.client_enriched?.estimated || 0} est · ${cov.client_enriched?.esg || 0} ESG`} accent="#0071e3" />
              </div>

              {/* matched issuers */}
              <div className="rounded-2xl border border-gray-200/70 bg-white p-5 shadow-sm">
                <h2 className="text-[13px] font-semibold text-[#1d1d1f]">Resolved issuers
                  <span className="font-normal text-gray-400"> — from ISIN, via GLEIF</span></h2>
                <table className="mt-3 w-full text-[13px]">
                  <thead><tr className="border-b border-gray-200 text-left text-[11px] uppercase tracking-wide text-gray-400">
                    <th className="py-2 font-medium">ISIN</th><th className="py-2 font-medium">Issuer</th>
                    <th className="py-2 font-medium">LEI</th><th className="py-2 text-right font-medium">Status</th>
                  </tr></thead>
                  <tbody>
                    {resolved.map(r => (
                      <tr key={r.isin} className="border-b border-gray-50 last:border-0">
                        <td className="py-2 font-mono text-[11px] text-gray-500">{r.isin}</td>
                        <td className="py-2 font-medium text-[#1d1d1f]">{r.issuer_name}<span className="ml-1 text-[11px] font-normal text-gray-400">{r.country}</span></td>
                        <td className="py-2 font-mono text-[10px] text-gray-400">{r.lei}</td>
                        <td className="py-2 text-right">
                          <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${r.status === 'resolved' ? 'bg-green-50 text-green-700' : 'bg-gray-100 text-gray-500'}`}>
                            {r.status === 'resolved' ? 'new · resolved' : 'cached'}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* honest gaps */}
              {(cov.unmatched.length > 0 || cov.errored.length > 0) && (
                <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4">
                  <div className="flex items-center gap-1.5 text-[12px] font-semibold text-amber-800"><AlertTriangle size={14} /> Excluded — surfaced, not fabricated</div>
                  {cov.unmatched.length > 0 && <p className="mt-1.5 text-[12px] text-amber-800"><b>No GLEIF match:</b> {cov.unmatched.join(', ')} — these ISINs have no issuer mapping and are excluded from the book.</p>}
                  {cov.errored.length > 0 && <p className="mt-1.5 text-[12px] text-amber-800"><b>Source error:</b> {cov.errored.join(', ')} — GLEIF was unreachable; retry (kept distinct from "unmatched" so coverage isn't understated).</p>}
                </div>
              )}

              {cov.sector_gap_isins.length > 0 && (
                <div className="rounded-2xl border border-blue-200 bg-blue-50 p-4 text-[12px] text-blue-800">
                  <b>Input still required — sector / NACE ({cov.sector_gap_isins.length}):</b> GLEIF does not carry industry classification,
                  so EU Taxonomy eligibility and transition tiers need each issuer's NACE code. Supply it (or a fundamentals file)
                  to complete alignment — we never guess it.
                </div>
              )}

              <button onClick={() => onGoto && onGoto('assetmgmt-funds')}
                className="flex items-center gap-2 rounded-xl border border-gray-200 bg-white px-4 py-2.5 text-[13px] font-medium text-[#0071e3] shadow-sm transition hover:border-[#0071e3]">
                View the fund climate & SFDR report <ArrowRight size={15} />
              </button>
            </div>
          )}
        </section>
      </div>
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
