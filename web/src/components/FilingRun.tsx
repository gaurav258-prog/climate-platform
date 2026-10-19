import { useState } from 'react'
import { Cpu, ChevronDown, ChevronRight, ArrowRight } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'
import { Card, SectionHead } from './ui'
import { money } from '../lib/money'
import { HEADING, InfoButton, type Message } from './Details'
import { StatusChip } from './StatusChip'
import { FACTS_VIEW, fmtDate } from './filing/words'
import { CheckLine, Said, Segments, plural } from './intake/parts'

// Intake phase 4 — the calculation run a frozen filing came from: what it read (each book, the hazard scores' date, the
// last data batch) and the checks its output passed, each in the catalogue's words (services/governance/engine_runs.py);
// then phase 6 — whether anything it read has changed since (services/governance/data_revisions.py). The run's
// fingerprint and reference sit one click away.

export interface RunCheck { key: string; label: string; status: 'pass' | 'warn' | 'fail'; detail: string; msg?: Message }
export interface EngineRun {
  run_id: string; view: string; status: 'pass' | 'warn'; created_at: string; inputs_sha256: string
  checks: RunCheck[]
  inputs: { books: { book: string; label?: string; n_assets: number; total_value_eur: number; facts_sha256: string }[]
            scores: { n_cells: number; latest_scored_at: string | null }
            last_batch: { batch_id: string; template: string; imported_at: string | null } | null
            open_differences: number }
  outputs: { n_assets?: number; n_scored?: number; total?: number; currency?: string }
}

interface Revisions {
  pinned: boolean; changed: boolean | null; msg: Message
  books?: { book: string; label: string; changed: boolean; then: { n_assets: number; total_value_eur: number }; now: { n_assets: number; total_value_eur: number } | null }[]
  facts?: { n: number; fields: { field: string; label: string; n: number }[]; paths: { path: string; label: string; n: number }[] }
  batches?: { batch_id: string; book: string; imported_at: string; n_assets: number }[]
  decisions?: number; scores?: { then: string | null; now: string | null; newer: boolean }
}

const when = (s: string | null | undefined) => s ? fmtDate(s) : '—'

// New data since the filing was frozen. The filing is never touched; it is flagged.
function SinceFrozen({ filingId }: { filingId: string }) {
  const q = useQuery({ queryKey: ['data-revisions', filingId], queryFn: () => api.get<Revisions>(`/v1/filings/${filingId}/data-revisions`) })
  const r = q.data
  if (q.isLoading) return <div className="mt-3 text-[12px] text-[var(--color-faint)]">Comparing your book with this filing…</div>
  if (!r) return null
  if (!r.changed) return <div className="mt-3"><CheckLine ok m={r.msg} /></div>
  const books = (r.books ?? []).filter(b => b.changed)
  return (
    <div className="mt-3 rounded-lg p-3 space-y-2" style={{ background: 'color-mix(in oklab, var(--color-warn) 9%, transparent)' }} role="status">
      <Said m={r.msg} tone="warn" className="text-[12.5px] font-medium" />
      {books.map(b => (
        <div key={b.book} className="flex items-center gap-2 flex-wrap text-[12px] text-[var(--color-mute)]">
          <span className="text-[var(--color-ink)] w-32 shrink-0">{b.label}</span>
          <span className="tabular-nums">{plural(b.then.n_assets, 'asset')}</span><ArrowRight size={11} /><span className="tabular-nums text-[var(--color-ink)]">{plural(b.now?.n_assets ?? 0, 'asset')}</span>
          <span className="text-[var(--color-faint)]">·</span>
          <span className="tabular-nums">{money(b.then.total_value_eur, 'EUR')}</span><ArrowRight size={11} /><span className="tabular-nums text-[var(--color-ink)]">{money(b.now?.total_value_eur ?? 0, 'EUR')}</span>
        </div>))}
      {(r.facts?.n ?? 0) > 0 && (
        <div className="flex items-center gap-1.5 flex-wrap text-[11.5px]">
          <span className="text-[var(--color-mute)]">{plural(r.facts!.n, 'new fact')}:</span>
          {r.facts!.fields.map(f => <StatusChip key={f.field} tone="neutral" label={`${f.label} ${f.n}`} />)}
          {r.facts!.paths.length > 0 && <InfoButton compact details={{ title: 'Where the new facts came from', sections:
            r.facts!.paths.map(p => ({ heading: p.label, body: plural(p.n, 'fact') })) }} />}
        </div>)}
      <div className="flex items-center gap-1.5 flex-wrap text-[11.5px]">
        {(r.batches ?? []).length > 0 && <StatusChip tone="neutral" label={`${plural(r.batches!.length, 'data file')} since`} />}
        {(r.decisions ?? 0) > 0 && <StatusChip tone="neutral" label={`${plural(r.decisions!, 'difference')} decided since`} />}
        {r.scores?.newer && <StatusChip tone="neutral" label={`Scores ${when(r.scores.then)} → ${when(r.scores.now)}`} />}
      </div>
    </div>
  )
}

export default function FilingRun({ run, filingId }: { run: EngineRun; filingId: string }) {
  const [showPassed, setShowPassed] = useState(false)
  const i = run.inputs
  const toNote = run.checks.filter(c => c.status !== 'pass')
  const passed = run.checks.filter(c => c.status === 'pass')
  const record = [
    { heading: 'Input fingerprint', body: run.inputs_sha256 },
    { heading: 'Run reference', body: run.run_id },
    { heading: 'Computed on', body: when(run.created_at) },
    { heading: 'Facts used', body: FACTS_VIEW[run.view] ?? 'Yours and ours together' },
  ]
  return (
    <Card className="p-4 space-y-3">
      <div className="flex items-center gap-2 flex-wrap">
        <SectionHead icon={Cpu}>Computed from</SectionHead>
        <InfoButton compact details={{ title: 'Computed from', sections: [
          { heading: HEADING.shows, body: 'The calculation run this filing was frozen from: what it read — each book, the hazard scores, the last data file — and the checks its output passed before it could be frozen.' },
          { heading: HEADING.read, body: 'A check that passed with a point to note did not stop the freeze. Below the checks: whether anything the run read has changed since — the filing itself never changes.' },
          ...record] }} />
        <StatusChip className="ml-auto" tone={run.status === 'pass' ? 'good' : 'warn'} label={run.status === 'pass' ? 'All checks passed' : 'Passed, with points to note'} />
      </div>
      <div className="grid sm:grid-cols-2 gap-x-4 gap-y-1.5 text-[12.5px]">
        {i.books.map(b => (
          <div key={b.book} className="flex justify-between gap-2 border-b border-[var(--color-line)] pb-1">
            <span className="text-[var(--color-mute)]">{b.label ?? 'Book'}</span>
            <span className="tabular-nums text-[var(--color-ink)] text-right">{plural(b.n_assets, 'asset')} · {money(b.total_value_eur, 'EUR')}</span>
          </div>))}
        <div className="flex justify-between gap-2 border-b border-[var(--color-line)] pb-1"><span className="text-[var(--color-mute)]">Hazard scores</span><span className="tabular-nums text-[var(--color-ink)]">to {when(i.scores.latest_scored_at)}</span></div>
        <div className="flex justify-between gap-2 border-b border-[var(--color-line)] pb-1"><span className="text-[var(--color-mute)]">Last data file</span><span className="tabular-nums text-[var(--color-ink)]">{i.last_batch ? when(i.last_batch.imported_at) : 'None'}</span></div>
      </div>
      <Segments parts={[{ n: passed.length, tone: 'good', label: 'passed' }, { n: toNote.length, tone: 'warn', label: 'to note' }]} />
      {toNote.length > 0 && <div className="space-y-1.5">{toNote.map((c, n) => c.msg && <CheckLine key={`${c.key}-${n}`} ok={false} warn m={c.msg} />)}</div>}
      {passed.length > 0 && (
        <div>
          <button onClick={() => setShowPassed(o => !o)} aria-expanded={showPassed} className="inline-flex items-center gap-1 text-[12px] text-[var(--color-mute)] hover:text-[var(--color-ink)]">
            {showPassed ? <ChevronDown size={13} /> : <ChevronRight size={13} />} {plural(passed.length, 'check')} passed</button>
          {showPassed && <div className="mt-1.5 space-y-1.5">{passed.map((c, n) => c.msg && <CheckLine key={`${c.key}-${n}`} ok m={c.msg} />)}</div>}
        </div>)}
      <SinceFrozen filingId={filingId} />
    </Card>
  )
}
