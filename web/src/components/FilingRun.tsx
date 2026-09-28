import { CheckCircle2, AlertTriangle, Cpu } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'
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
const VIEW: Record<string, string> = { joint: 'Joint — your values; ours only where you chose ours', client: 'Your values only', tellumen: 'Tellumen’s value wherever we derive one' }
const TONE = { pass: 'var(--color-good,#34d399)', warn: 'var(--color-warn)', fail: 'var(--color-bad,#fb7185)' }
const day = (s: string | null | undefined) => s ? s.slice(0, 10) : '—'

interface Revisions {
  pinned: boolean; changed: boolean | null; message: string
  books?: { book: string; changed: boolean; then: { n_assets: number; total_value_eur: number }; now: { n_assets: number; total_value_eur: number } | null }[]
  facts?: { n: number; by_field: Record<string, number>; by_path: Record<string, number> }
  batches?: { batch_id: string; template: string; imported_at: string; n_assets: number }[]
  decisions?: number; scores?: { then: string | null; now: string | null; newer: boolean }
}
const PATH: Record<string, string> = { intake_batch: 'data files', manual_edit: 'edits', manual_entry: 'entries', book: 'other changes to the book' }

// Intake phase 6 — new data since the filing was frozen. The filing is never touched; it is flagged.
function SinceFrozen({ filingId }: { filingId: string }) {
  const q = useQuery({ queryKey: ['data-revisions', filingId], queryFn: () => api.get<Revisions>(`/v1/filings/${filingId}/data-revisions`) })
  const r = q.data
  if (q.isLoading) return <div className="mt-3 mono text-[10.5px] text-[var(--color-faint)]">checking the book against this filing…</div>
  if (!r) return null
  if (!r.changed) return <div className="mt-3 flex items-center gap-1.5 text-[11.5px] text-[var(--color-mute)]"><CheckCircle2 size={12} style={{ color: TONE.pass }} /> {r.message}</div>
  const facts = Object.entries(r.facts?.by_field ?? {})
  const paths = Object.entries(r.facts?.by_path ?? {})
  return (
    <div className="mt-3 rounded-lg p-2.5 text-[11.5px]" style={{ color: 'var(--color-warn)', background: 'color-mix(in oklab, var(--color-warn) 10%, transparent)' }} role="status">
      <div className="flex items-start gap-1.5 font-medium"><AlertTriangle size={12} className="mt-0.5 shrink-0" /> {r.message}</div>
      <ul className="mt-1 space-y-0.5 text-[var(--color-mute)]">
        {(r.books ?? []).filter(b => b.changed).map(b => (
          <li key={b.book}>{BOOK[b.book] ?? b.book}: {b.then.n_assets} → {b.now?.n_assets ?? 0} assets · {money(b.then.total_value_eur, 'EUR')} → {money(b.now?.total_value_eur ?? 0, 'EUR')}</li>))}
        {facts.length > 0 && <li>{r.facts!.n} fact statement(s) since: {facts.map(([f, n]) => `${f.replace(/_/g, ' ')} ${n}`).join(', ')}{paths.length ? ` — from ${paths.map(([p, n]) => `${PATH[p] ?? p} (${n})`).join(', ')}` : ''}</li>}
        {(r.batches ?? []).map(b => <li key={b.batch_id}>data file {b.batch_id.slice(0, 8)} · {day(b.imported_at)} · {b.n_assets} asset(s) in scope</li>)}
        {(r.decisions ?? 0) > 0 && <li>{r.decisions} difference(s) between your values and ours decided since</li>}
        {r.scores?.newer && <li>hazard scores updated: {day(r.scores.then)} → {day(r.scores.now)}</li>}
      </ul>
    </div>
  )
}

export default function FilingRun({ run, filingId }: { run: EngineRun; filingId: string }) {
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
      <SinceFrozen filingId={filingId} />
      <div className="mono text-[9.5px] text-[var(--color-faint)] mt-2 break-all">input fingerprint {run.inputs_sha256.slice(0, 32)}… · run {run.run_id.slice(0, 8)} · {day(run.created_at)}</div>
    </Card>
  )
}
