import { useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Upload, Download, FileSpreadsheet, CheckCircle2, AlertTriangle, ArrowRight, Plug } from 'lucide-react'
import { api, upload as uploadFile, download } from '../lib/api'
import { useAuth } from '../lib/auth'
import { Card, PageHeader } from '../components/ui'
import ProvidedData from '../components/ProvidedData'
import GlRecon from '../components/GlRecon'
import SeasonalArrears from '../components/SeasonalArrears'
import SectionTabs, { DATA_TABS } from '../components/SectionTabs'

// One place a customer feeds the engine and sees what it made of their book: upload the book (checked before
// anything saves), read the scores, then fill the regulatory gaps. Financial sectors; the book differs by sector.
const SECTORS: Record<string, { prefix: string; listKey: string; bookNoun: string; rowNoun: string }> = {
  bank:          { prefix: 'bank', listKey: 'assets', bookNoun: 'loan tape', rowNoun: 'exposure' },
  insurer:       { prefix: 'insurance', listKey: 'policies', bookNoun: 'Statement of Values', rowNoun: 'location' },
  asset_manager: { prefix: 'assetmgmt', listKey: 'holdings', bookNoun: 'holdings book', rowNoun: 'holding' },
  reit:          { prefix: 'realestate', listKey: 'properties', bookNoun: 'property schedule', rowNoun: 'property' },
}
const eur = (n?: number | null) => n == null ? '—' : Math.abs(n) >= 1e9 ? `€${(n / 1e9).toFixed(2)}bn` : Math.abs(n) >= 1e6 ? `€${(n / 1e6).toFixed(1)}m` : `€${Math.round((n || 0) / 1e3)}k`

interface ValRep { filename: string; n_total: number; n_valid: number; n_error: number; errors: { row: number; problems: string[] }[] }
interface Rollup { n_scored?: number; total_value_eur?: number; value_at_risk_eur?: number; pct_value_at_risk?: number; n_high?: number; by_hazard?: { hazard: string }[] }

export default function DataHub() {
  const { profile } = useAuth()
  const type = profile?.org?.type ?? ''
  const cfg = SECTORS[type]
  const qc = useQueryClient()
  const summary = useQuery({ enabled: !!cfg, queryKey: ['data-summary', cfg?.prefix],
    queryFn: () => api.get<{ rollup: Rollup }>(`/v1/${cfg!.prefix}/summary?scenario=baseline&horizon=current`) })

  // Agri book = geolocated sites + sourcing plots (not a single loan-tape). "Your data" is still the one
  // canonical entry — it routes to the two management surfaces so the loading home is consistent per sector.
  if (!cfg) return (
    <div className="fadeup space-y-6">
      <SectionTabs tabs={DATA_TABS} />
      <PageHeader eyebrow="Sense · your data" title="Your data"
        lead="Everything the engine scores comes from your book — your operational sites and your sourcing plots. Load them here; each is located, scored, and ready for reporting." />
      <div className="grid sm:grid-cols-2 gap-3">
        <Link to="/operations" className="group rounded-xl border border-[var(--color-line)] bg-[var(--color-bg-2)] p-5 hover:border-[var(--color-sky)] transition">
          <div className="flex items-center gap-2 text-[var(--color-sky)] mb-1.5"><Upload size={18} /><span className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)]">Own operations</span></div>
          <div className="text-[15px] font-semibold text-[var(--color-ink)]">Your sites</div>
          <div className="text-[12.5px] text-[var(--color-mute)] mt-0.5">Add or upload your facilities — each geolocated and scored across hazards.</div>
          <div className="mt-3 inline-flex items-center gap-1 text-[12px] text-[var(--color-sky)]">Open <ArrowRight size={13} className="group-hover:translate-x-0.5 transition" /></div>
        </Link>
        <Link to="/sourcing" className="group rounded-xl border border-[var(--color-line)] bg-[var(--color-bg-2)] p-5 hover:border-[var(--color-sky)] transition">
          <div className="flex items-center gap-2 text-[var(--color-sky)] mb-1.5"><FileSpreadsheet size={18} /><span className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)]">Supply chain</span></div>
          <div className="text-[15px] font-semibold text-[var(--color-ink)]">Suppliers &amp; crops</div>
          <div className="text-[12.5px] text-[var(--color-mute)] mt-0.5">Add sourcing plots by commodity &amp; origin — scored, and checked for EUDR deforestation-free status.</div>
          <div className="mt-3 inline-flex items-center gap-1 text-[12px] text-[var(--color-sky)]">Open <ArrowRight size={13} className="group-hover:translate-x-0.5 transition" /></div>
        </Link>
      </div>
      <div className="mono text-[10px] text-[var(--color-faint)]">Bringing a figure calculated on your side (a certified footprint, an audited number)? Provide it under “Provided &amp; reconciled data” inside your reports.</div>
    </div>
  )
  const r = summary.data?.rollup
  const refresh = () => { qc.invalidateQueries({ queryKey: ['data-summary'] }); qc.invalidateQueries({ queryKey: ['fin-portfolio'] }) }

  return (
    <div className="fadeup space-y-4 max-w-4xl">
      <SectionTabs tabs={DATA_TABS} />
      <PageHeader eyebrow={`${profile?.org?.name} · your data`} title="Your data"
        lead={`Feed the engine and see what it made of your book — upload your ${cfg.rowNoun}s (we check every row before anything is saved), read the scores, then fill any regulatory gaps.`} />

      {/* general-ledger reconciliation — tie the reported book total back to the ledger (gate 4) */}
      <GlRecon />
      {/* seasonal-arrears overlay — harvest carry-over vs genuine deterioration (renders once arrears are uploaded) */}
      <SeasonalArrears />

      <Step n={1} title="Upload your book" tone="you">
        <ValidatedUpload
          intro={<>Your {cfg.bookNoun} is the source every climate score starts from — one row per {cfg.rowNoun}. We validate every row <b className="text-[var(--color-ink)]">before</b> anything is saved.</>}
          dropLabel={cfg.bookNoun}
          endpoints={{ validate: `/v1/${cfg.prefix}/${cfg.listKey}/validate`, upload: `/v1/${cfg.prefix}/${cfg.listKey}/upload`, template: `/v1/${cfg.prefix}/${cfg.listKey}/template.xlsx`, templateFile: `tellumen_${cfg.listKey}_template.xlsx` }}
          onDone={refresh}
          renderDone={res => <>Imported <b>{Number(res.n_uploaded) || 0}</b> {cfg.rowNoun}{Number(res.n_uploaded) === 1 ? '' : 's'} — scored and ready below.</>}
        />
      </Step>

      <Flow>the engine scores every {cfg.rowNoun} against verified EU &amp; US climate data</Flow>

      <Step n={2} title="What the engine made" tone="engine">
        <div className="flex flex-wrap gap-x-8 gap-y-3 mb-3">
          <Metric label="assets scored" value={r?.n_scored != null ? String(r.n_scored) : '—'} />
          <Metric label="money at high risk" value={eur(r?.value_at_risk_eur)} accent />
          <Metric label="share of book at risk" value={r?.pct_value_at_risk != null ? `${r.pct_value_at_risk}%` : '—'} />
          <Metric label="total book value" value={eur(r?.total_value_eur)} />
        </div>
        <div className="flex flex-wrap gap-2">
          <NavBtn to="/portfolio">Open Portfolio</NavBtn>
          <NavBtn to="/analytics">Analytics</NavBtn>
          <NavBtn to="/kri">KRI dashboard</NavBtn>
        </div>
      </Step>

      <Flow>some regulatory figures aren&rsquo;t in a book — add them here</Flow>

      <Step n={3} title="Add &amp; provide data" tone="bank" flush>
        <ProvidedData />
        {type === 'bank' && (
          <div className="px-5 pt-2 pb-5 border-t border-[var(--color-line)] mt-2">
            <div className="text-[13px] text-[var(--color-ink)] font-medium mb-0.5">Per-loan data by Excel</div>
            <ValidatedUpload
              intro={<>Bulk-provide the per-loan figures the engine can&rsquo;t derive from location — <b className="text-[var(--color-ink)]">EPC label, IFRS-9 stage, residual maturity</b> — in one file, matched to your book by asset name. Reconciled and audited like any provided figure.</>}
              dropLabel="per-loan attributes file"
              endpoints={{ validate: '/v1/bank/assets/attributes/validate', upload: '/v1/bank/assets/attributes/upload', template: '/v1/bank/assets/attributes/template.xlsx', templateFile: 'tellumen_loan_attributes_template.xlsx' }}
              onDone={refresh}
              renderDone={res => <>Matched <b>{Number(res.n_matched) || 0}</b> {Number(res.n_matched) === 1 ? 'loan' : 'loans'}{Number(res.n_unmatched) ? <> · <span style={{ color: 'var(--color-warn)' }}>{Number(res.n_unmatched)} not found in your book</span></> : ''} — saved.</>}
            />
          </div>
        )}
      </Step>

      {/* integration lives in the technical settings area, not the everyday workflow */}
      <Link to="/admin" className="flex items-center gap-3 rounded-xl border border-[var(--color-line)] bg-[var(--color-panel)] px-4 py-3 hover:border-[var(--color-line-2)] transition">
        <span className="w-8 h-8 rounded-lg bg-[var(--color-bg-2)] border border-[var(--color-line)] flex items-center justify-center shrink-0"><Plug size={15} className="text-[var(--color-mute)]" /></span>
        <span className="min-w-0">
          <span className="text-[13.5px] text-[var(--color-ink)]">Integrations &amp; API <span className="mono text-[9.5px] text-[var(--color-faint)]">· technical</span></span>
          <span className="block text-[12px] text-[var(--color-mute)]">Pipe your book &amp; feeds straight from your own systems — tokens and endpoints live with Settings.</span>
        </span>
        <span className="ml-auto mono text-[11px] text-[var(--color-sky)] shrink-0">Open →</span>
      </Link>
    </div>
  )
}

// ── the validated upload: drop → we check every row → you confirm the import ─────────────────────────────────
interface UploadEndpoints { validate: string; upload: string; template: string; templateFile: string }
function ValidatedUpload({ intro, dropLabel, endpoints, onDone, renderDone }: {
  intro: React.ReactNode; dropLabel: string; endpoints: UploadEndpoints; onDone: () => void
  renderDone: (res: Record<string, unknown>) => React.ReactNode
}) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [rep, setRep] = useState<ValRep | null>(null)
  const [phase, setPhase] = useState<'idle' | 'checking' | 'checked' | 'importing' | 'done' | 'error'>('idle')
  const [msg, setMsg] = useState<string | null>(null)
  const [result, setResult] = useState<Record<string, unknown> | null>(null)

  const pick = async (f: File) => {
    setFile(f); setResult(null); setMsg(null); setRep(null); setPhase('checking')
    try {
      const v = await uploadFile<ValRep>(endpoints.validate, f)
      setRep(v); setPhase('checked')
    } catch (e: unknown) {
      const d = (e as { data?: { detail?: unknown } })?.data?.detail
      setMsg(missingMsg(d) ?? `We couldn’t read that file — please upload a CSV or Excel ${dropLabel}.`)
      setPhase('error')
    }
  }
  const doImport = async () => {
    if (!file) return
    setPhase('importing'); setMsg(null)
    try {
      const res = await uploadFile<Record<string, unknown>>(endpoints.upload, file)
      setResult(res); setPhase('done'); onDone()
    } catch {
      setMsg('Something went wrong saving — please try again.'); setPhase('error')
    }
  }
  const reset = () => { setFile(null); setRep(null); setResult(null); setMsg(null); setPhase('idle'); if (inputRef.current) inputRef.current.value = '' }
  const downloadFixList = () => {
    if (!rep) return
    const rows = [['row', 'what to fix'], ...rep.errors.map(e => [String(e.row), e.problems.join('; ')])]
    const csv = rows.map(r => r.map(c => `"${c.replace(/"/g, '""')}"`).join(',')).join('\n')
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }))
    const a = document.createElement('a'); a.href = url; a.download = 'rows-to-fix.csv'; a.click(); URL.revokeObjectURL(url)
  }

  return (
    <div>
      <p className="text-[13px] text-[var(--color-mute)] mb-3">{intro}</p>
      <input ref={inputRef} type="file" accept=".csv,.xlsx,.xls" className="hidden" onChange={e => { const f = e.target.files?.[0]; if (f) pick(f) }} />

      {phase !== 'done' && (
        <div onClick={() => inputRef.current?.click()}
          onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); const f = e.dataTransfer.files?.[0]; if (f) pick(f) }}
          className="rounded-xl border border-dashed border-[var(--color-line-2)] bg-[var(--color-bg-2)] px-4 py-6 text-center cursor-pointer hover:border-[var(--color-sky)] transition">
          <Upload size={18} className="mx-auto text-[var(--color-faint)] mb-2" />
          <div className="text-[13px] text-[var(--color-ink)]">Drop your {dropLabel} here <span className="text-[var(--color-faint)]">— CSV or Excel —</span> or <span className="text-[var(--color-sky)]">browse</span></div>
          <button onClick={e => { e.stopPropagation(); download(endpoints.template, endpoints.templateFile) }}
            className="mt-2 inline-flex items-center gap-1.5 mono text-[10.5px] text-[var(--color-mute)] hover:text-[var(--color-sky)]"><Download size={12} /> download the template</button>
        </div>
      )}

      {phase === 'checking' && <div className="mono text-[11px] text-[var(--color-faint)] mt-3">checking every row…</div>}
      {phase === 'error' && msg && <div className="mt-3 text-[12.5px] flex items-center gap-2" style={{ color: 'var(--color-warn)' }}><AlertTriangle size={14} /> {msg} <button onClick={reset} className="mono text-[10.5px] text-[var(--color-sky)] hover:underline ml-1">try another file</button></div>}

      {/* preview: what's ready vs what needs fixing — nothing saved yet */}
      {(phase === 'checked' || phase === 'importing') && rep && (
        <div className="mt-3 rounded-xl border border-[var(--color-line)] overflow-hidden">
          <div className="flex items-center gap-2.5 flex-wrap px-4 py-2.5 bg-[var(--color-bg-2)] border-b border-[var(--color-line)]">
            <FileSpreadsheet size={14} className="text-[var(--color-faint)]" />
            <span className="mono text-[11.5px] text-[var(--color-ink)] truncate max-w-[240px]">{rep.filename}</span>
            <span className="mono text-[10px] text-[var(--color-faint)]">{rep.n_total} rows</span>
            <span className="mono text-[9.5px] px-2 py-0.5 rounded-full" style={{ color: 'var(--color-good)', background: 'color-mix(in oklab,var(--color-good) 14%,transparent)' }}>{rep.n_valid} ready</span>
            {rep.n_error > 0 && <span className="mono text-[9.5px] px-2 py-0.5 rounded-full" style={{ color: 'var(--color-warn)', background: 'color-mix(in oklab,var(--color-warn) 14%,transparent)' }}>{rep.n_error} need fixing</span>}
          </div>
          {rep.errors.slice(0, 6).map(e => (
            <div key={e.row} className="flex gap-3 px-4 py-2 border-b border-[var(--color-line-2)] text-[12px]">
              <span className="mono text-[10px] text-[var(--color-faint)] w-14 shrink-0">row {e.row}</span>
              <span style={{ color: 'var(--color-bad, #e0574a)' }}>{e.problems.join(' · ')}</span>
            </div>
          ))}
          {rep.n_error > 6 && <div className="px-4 py-2 border-b border-[var(--color-line-2)] mono text-[10.5px] text-[var(--color-faint)]">…and {rep.n_error - 6} more</div>}
          <div className="flex items-center gap-2.5 flex-wrap px-4 py-3">
            <button disabled={rep.n_valid === 0 || phase === 'importing'} onClick={doImport}
              className="mono text-[11.5px] px-3.5 py-2 rounded-lg bg-[var(--color-sky)] text-white hover:brightness-110 transition disabled:opacity-45">
              {phase === 'importing' ? 'importing…' : `Import ${rep.n_valid} ready ${rep.n_valid === 1 ? 'row' : 'rows'}`}</button>
            {rep.n_error > 0 && <button onClick={downloadFixList} className="mono text-[11px] px-3 py-2 rounded-lg border border-[var(--color-line)] text-[var(--color-mute)] hover:text-[var(--color-ink)]"><Download size={12} className="inline mr-1" />Download rows to fix</button>}
            <button onClick={reset} className="mono text-[10.5px] text-[var(--color-faint)] hover:text-[var(--color-ink)] ml-auto">choose a different file</button>
            <span className="mono text-[9.5px] text-[var(--color-faint)] w-full">Nothing is saved until you import.</span>
          </div>
        </div>
      )}

      {phase === 'done' && result && (
        <div className="mt-3 flex items-center gap-2 rounded-xl border border-[var(--color-line)] px-4 py-3" style={{ background: 'color-mix(in oklab,var(--color-good) 8%,transparent)' }}>
          <CheckCircle2 size={16} style={{ color: 'var(--color-good)' }} />
          <span className="text-[13px] text-[var(--color-ink)]">{renderDone(result)}</span>
          <button onClick={reset} className="mono text-[10.5px] text-[var(--color-sky)] hover:underline ml-auto">upload another file</button>
        </div>
      )}
    </div>
  )
}

function missingMsg(detail: unknown): string | null {
  const m = (detail as { missing_columns?: string[] })?.missing_columns
  if (Array.isArray(m) && m.length) return `Your file is missing required column${m.length === 1 ? '' : 's'}: ${m.join(', ')}. Start from the template.`
  if (typeof detail === 'string') return detail
  return null
}

// ── small presentational helpers ────────────────────────────────────────────────────────────────────────────
const TONE: Record<string, { c: string; label: string }> = {
  you: { c: 'var(--color-viz,#a78bfa)', label: 'you provide' },
  engine: { c: 'var(--color-sky)', label: 'Tellumen computes' },
  bank: { c: 'var(--color-warn)', label: 'your systems / manual' },
}
function Step({ n, title, tone, flush, children }: { n: number; title: string; tone: string; flush?: boolean; children: React.ReactNode }) {
  const t = TONE[tone]
  return (
    <Card className={flush ? 'p-0 overflow-hidden' : 'p-5'}>
      <div className={`flex items-center gap-2.5 ${flush ? 'px-5 pt-4 pb-1' : 'mb-3'}`}>
        <span className="w-6 h-6 rounded-full flex items-center justify-center mono text-[11px] font-semibold shrink-0" style={{ color: t.c, background: `color-mix(in oklab, ${t.c} 14%, transparent)` }}>{n}</span>
        <span className="text-[15px] font-semibold text-[var(--color-ink)]">{title}</span>
        <span className="mono text-[8.5px] uppercase tracking-wide px-2 py-0.5 rounded-full ml-1" style={{ color: t.c, background: `color-mix(in oklab, ${t.c} 12%, transparent)` }}>{t.label}</span>
      </div>
      <div className={flush ? '' : ''}>{children}</div>
    </Card>
  )
}
function Flow({ children }: { children: React.ReactNode }) {
  return <div className="mono text-[10px] text-[var(--color-faint)] pl-5 flex items-center gap-2"><span>↓</span><span>{children}</span></div>
}
function Metric({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return <div><div className="display text-[24px] leading-none" style={accent ? { color: 'var(--color-warn)' } : undefined}>{value}</div><div className="text-[12px] text-[var(--color-mute)] mt-1.5">{label}</div></div>
}
function NavBtn({ to, children }: { to: string; children: React.ReactNode }) {
  return <Link to={to} className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-line-2)] px-3 py-1.5 text-[12px] text-[var(--color-mute)] hover:border-[var(--color-sky)] hover:text-[var(--color-ink)] transition">{children} <ArrowRight size={12} /></Link>
}
