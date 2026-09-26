import { Link } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Upload, FileSpreadsheet, ArrowRight, Plug } from 'lucide-react'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { Card, PageHeader } from '../components/ui'
import ProvidedData from '../components/ProvidedData'
import GlRecon from '../components/GlRecon'
import SeasonalArrears from '../components/SeasonalArrears'
import SectionTabs, { DATA_TABS } from '../components/SectionTabs'
import ValidatedUpload from '../components/ValidatedUpload'

// One place a customer feeds the engine and sees what it made of their book: upload the book (checked before
// anything saves), read the scores, then fill the regulatory gaps. Financial sectors; the book differs by sector.
const SECTORS: Record<string, { prefix: string; listKey: string; bookNoun: string; rowNoun: string }> = {
  bank:          { prefix: 'bank', listKey: 'assets', bookNoun: 'loan tape', rowNoun: 'exposure' },
  insurer:       { prefix: 'insurance', listKey: 'policies', bookNoun: 'Statement of Values', rowNoun: 'location' },
  asset_manager: { prefix: 'assetmgmt', listKey: 'holdings', bookNoun: 'holdings book', rowNoun: 'holding' },
  reit:          { prefix: 'realestate', listKey: 'properties', bookNoun: 'property schedule', rowNoun: 'property' },
}
const eur = (n?: number | null) => n == null ? '—' : Math.abs(n) >= 1e9 ? `€${(n / 1e9).toFixed(2)}bn` : Math.abs(n) >= 1e6 ? `€${(n / 1e6).toFixed(1)}m` : `€${Math.round((n || 0) / 1e3)}k`

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
          dropLabel={cfg.bookNoun} template={`${cfg.prefix}_${cfg.listKey}`}
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
              intro={<>Bulk-provide the per-loan figures the engine can&rsquo;t derive from location — <b className="text-[var(--color-ink)]">EPC label, IFRS-9 stage, residual maturity</b> — in one file, matched to your book by your asset ID (or a name that identifies exactly one loan). EVIC converts to EUR at the book date’s rate. Reconciled and audited like any provided figure.</>}
              dropLabel="per-loan attributes file" declareMoney
              endpoints={{ validate: '/v1/bank/assets/attributes/validate', upload: '/v1/bank/assets/attributes/upload', template: '/v1/bank/assets/attributes/template.xlsx', templateFile: 'tellumen_loan_attributes_template.xlsx' }}
              onDone={refresh}
              renderDone={res => <>Matched <b>{Number(res.n_matched) || 0}</b> {Number(res.n_matched) === 1 ? 'loan' : 'loans'}{Number(res.n_unmatched) ? <> · <span style={{ color: 'var(--color-warn)' }}>{Number(res.n_unmatched)} not found in your book</span></> : ''}{Number(res.n_ambiguous) ? <> · <span style={{ color: 'var(--color-warn)' }}>{Number(res.n_ambiguous)} name(s) match several loans — add your asset ID</span></> : ''}{Number(res.n_refused) ? <> · <span style={{ color: 'var(--color-warn)' }}>{Number(res.n_refused)} refused (currency / date)</span></> : ''} — saved.</>}
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
