import { CheckCircle2, AlertTriangle, Cpu } from 'lucide-react'
import { Card } from './ui'
import { money } from '../lib/money'

// Intake phase 4 — the engine run a frozen filing came from: exactly what it read (the book, a fingerprint of every
// fact, the last data batch, the hazard scores' vintage) and the checks its output passed.

export interface RunCheck { key: string; label: string; status: 'pass' | 'warn' | 'fail'; detail: string }
export interface EngineRun {
  run_id: string; view: string; status: 'pass' | 'warn'; created_at: string; inputs_sha256: string
  checks: RunCheck[]
  inputs: { books: { book: string; n_assets: number; total_value_eur: number; facts_sha256: string }[]
            scores: { n_cells: number; latest_scored_at: string | null }
            last_batch: { batch_id: string; template: string; imported_at: string | null } | null
            open_differences: number }
  outputs: { n_assets?: number; n_scored?: number; total?: number; currency?: string }
}

const BOOK: Record<string, string> = { bank_assets: 'loan book', insurance_policies: 'underwriting book', realestate_properties: 'property book',
  assetmgmt_holdings: 'holdings book', company_sites: 'own sites', supply_plots: 'sourcing plots', fund_positions: 'fund positions' }
const VIEW: Record<string, string> = { joint: 'Joint — your values, ours where you gave none', client: 'Your values only', tellumen: 'Tellumen values where we have one' }
const TONE = { pass: 'var(--color-good,#34d399)', warn: 'var(--color-warn)', fail: 'var(--color-bad,#fb7185)' }
const day = (s: string | null | undefined) => s ? s.slice(0, 10) : '—'

export default function FilingRun({ run }: { run: EngineRun }) {
  const i = run.inputs
  return (
    <Card className="p-4">
      <div className="flex items-center justify-between mb-2 gap-2 flex-wrap">
        <div className="mono text-[10px] uppercase tracking-widest text-[var(--color-faint)] flex items-center gap-1.5"><Cpu size={12} /> Computed from</div>
        <span className="inline-flex items-center gap-1 mono text-[10.5px]" style={{ color: TONE[run.status] }}>
          {run.status === 'pass' ? <CheckCircle2 size={12} /> : <AlertTriangle size={12} />}{run.status === 'pass' ? 'all checks passed' : 'passed, with points to note'}
        </span>
      </div>
      <div className="grid sm:grid-cols-2 gap-x-4 gap-y-1.5 text-[12px]">
        {i.books.map(b => (
          <div key={b.book} className="flex justify-between gap-2 border-b border-[var(--color-line)] pb-1">
            <span className="text-[var(--color-mute)]">{BOOK[b.book] ?? b.book}</span>
            <span className="mono text-[var(--color-ink)] text-right">{b.n_assets.toLocaleString('en-GB')} · {money(b.total_value_eur, 'EUR')}</span>
          </div>))}
        <div className="flex justify-between gap-2 border-b border-[var(--color-line)] pb-1"><span className="text-[var(--color-mute)]">view</span><span className="text-[var(--color-ink)] text-right">{VIEW[run.view] ?? run.view}</span></div>
        <div className="flex justify-between gap-2 border-b border-[var(--color-line)] pb-1"><span className="text-[var(--color-mute)]">hazard scores</span><span className="mono text-[var(--color-ink)]">{i.scores.n_cells} cells · to {day(i.scores.latest_scored_at)}</span></div>
        <div className="flex justify-between gap-2 border-b border-[var(--color-line)] pb-1"><span className="text-[var(--color-mute)]">last data batch</span><span className="mono text-[var(--color-ink)]">{i.last_batch ? `${day(i.last_batch.imported_at)} · ${i.last_batch.batch_id.slice(0, 8)}` : 'none'}</span></div>
      </div>
      <ul className="mt-3 space-y-1">
        {run.checks.map(c => (
          <li key={c.key} className="flex items-start gap-2 text-[12px]">
            {c.status === 'pass' ? <CheckCircle2 size={13} className="mt-0.5 shrink-0" style={{ color: TONE.pass }} /> : <AlertTriangle size={13} className="mt-0.5 shrink-0" style={{ color: TONE[c.status] }} />}
            <span><span className="text-[var(--color-ink)]">{c.label}</span> <span className="text-[var(--color-mute)]">— {c.detail}</span></span>
          </li>))}
      </ul>
      <div className="mono text-[9.5px] text-[var(--color-faint)] mt-2 break-all">input fingerprint {run.inputs_sha256.slice(0, 32)}… · run {run.run_id.slice(0, 8)} · {day(run.created_at)}</div>
    </Card>
  )
}
