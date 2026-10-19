import { useState } from 'react'
import { ShieldCheck, ArrowRight, MapPin, TrendingUp, TrendingDown } from 'lucide-react'
import { HEADING, InfoButton, messageDetails, type Message } from './Details'
import { StatusChip } from './StatusChip'
import { Dialog } from './Dialog'
import { CheckLine, Said, Segments, TONE, plural } from './intake/parts'

// The intake checks a customer sees between "file chosen" and "rows saved" (services/ingest/batch_controls.py and
// services/intake/*: one implementation for every sector). The main screen carries the verdict, one chip per stage and
// only what needs attention — each a catalogue message with its explanation one click away; the full lists (what each
// update changes, the large changes) open in a dialog.
export interface ControlCheck { check: string; label: string; status: 'pass' | 'fail' | 'info'; detail: string; msg?: Message }
export interface Rate {
  currency: string; book_date: string; policy: 'closing' | 'average'; units_per_eur: number | null; source: string; basis: string
  rate_date: string | null; stale: boolean; note: string | null; outside_tolerance?: boolean; msg?: Message
}
export interface Controls {
  batch_id?: string
  receipt: { status: string; n_rows: number; checks: ControlCheck[] }
  transformation: {
    status: string; n_form_violations: number; coordinates_usable_pct: number | null
    tie_outs: { field: string; label?: string; raw_total: number; accepted_total: number; rejected_total: number; status: string; msg?: Message }[]
    excluded: { n_rows: number; pct_rows: number; value_field: string | null; value_label?: string | null; value: number | null; pct_value: number | null; msg?: Message | null }
  }
  currency?: { declared_currency: string | null; book_date: string | null; currencies: string[]; n_converted: number; warnings: string[]; rates: Rate[] }
  values?: Record<string, { label: string; required: boolean; n_recognised: number; n_unknown: number; n_unknown_values: number; unknown: Record<string, number>; msg?: Message }>
  readiness?: { status: string; n_not_ready: number; value_staged: number; msg?: Message | null }
  matching?: Matching
  gate: { status: 'pass' | 'needs_signoff' | 'blocked'; reasons: string[]; messages?: Message[] }
  landing?: { status: string; n_validated: number; n_landed: number; n_dropped_after_validation: number; detail: string; msg?: Message }
}

export interface Matching {
  new: number; update: number; unchanged: number; ambiguous: number; duplicate: number
  updates: { name: string; changes: Record<string, [unknown, unknown]> }[]
  large_changes: { name: string; reasons: string[]; value_change_pct?: number; move_km?: number }[]
  field_labels?: Record<string, string>
}

const GATE = {
  pass: { tone: 'good' as const, label: 'Clear to import' },
  needs_signoff: { tone: 'warn' as const, label: 'Needs a second person' },
  blocked: { tone: 'bad' as const, label: 'Nothing can be imported' },
}
const ABOUT = [
  { heading: HEADING.shows, body: 'Every check we run on your file before anything is saved: did everything arrive (no rows lost or repeated, not a file already imported), did every value keep its meaning, were amounts converted at the right rate, do the values match our lists, can the engine use each row, and how the rows match the assets you already hold.' },
  { heading: HEADING.read, body: 'Each stage shows a tick when it passed. Anything that needs attention is listed under it — select ⓘ for what it means and what to do. When every check passes the batch is imported at once; when one fails, a second person must approve it, with your reason.' },
  { heading: HEADING.limits, body: 'A blank cell never clears a value we already hold. Your values are used; a large change to an asset you hold needs a second person.' },
]

export function ControlsPanel({ controls, valueLabel, declRows, declTotal, setDeclRows, setDeclTotal, onRecheck, checking, onMapValues }: {
  controls: Controls; valueLabel?: string | null; declRows: string; declTotal: string
  setDeclRows: (v: string) => void; setDeclTotal: (v: string) => void; onRecheck: () => void; checking?: boolean
  onMapValues?: () => void
}) {
  const { receipt, transformation: tr, gate, readiness: rd, matching: m, values: vals, currency: cur } = controls
  const unknown = Object.values(vals ?? {}).filter(v => v.n_unknown > 0 && v.msg)
  const failed = receipt.checks.filter(c => c.status === 'fail' && c.msg)
  const ties = tr.tie_outs.filter(t => t.status !== 'pass' && t.msg)
  const rates = cur?.rates ?? []
  const looks = rates.filter(r => r.stale || r.outside_tolerance)
  const g = GATE[gate.status]
  const stages = [
    { label: 'Arrived complete', ok: receipt.status === 'pass' },
    { label: 'Values kept', ok: tr.status === 'pass' },
    ...(cur ? [{ label: 'Currency', ok: looks.length === 0 }] : []),
    ...(vals && Object.keys(vals).length ? [{ label: 'Lists matched', ok: unknown.length === 0 }] : []),
    ...(rd ? [{ label: 'Engine-ready', ok: rd.n_not_ready === 0 }] : []),
    ...(m ? [{ label: 'Matched to your book', ok: !m.large_changes.length && !m.ambiguous && !m.duplicate }] : []),
  ]
  return (
    <div className="border-t border-[var(--color-line)]">
      <div className="flex items-center gap-2 flex-wrap px-4 py-2.5 bg-[var(--color-bg-2)]">
        <ShieldCheck size={14} className="text-[var(--color-faint)]" />
        <span className="text-[12.5px] font-medium text-[var(--color-ink)]">Checks before import</span>
        <InfoButton compact details={{ title: 'Checks before import', sections: ABOUT }} />
        <StatusChip className="ml-auto" tone={g.tone} label={g.label} />
      </div>

      <div className="px-4 py-3 space-y-3">
        <div className="flex flex-wrap gap-1.5">
          {stages.map(s => <StatusChip key={s.label} tone={s.ok ? 'good' : 'warn'} label={s.label} />)}
        </div>

        {(failed.length > 0 || ties.length > 0 || tr.excluded.msg || unknown.length > 0 || rd?.msg) && (
          <div className="space-y-1.5">
            {failed.map(c => <CheckLine key={c.check} ok={false} warn m={c.msg!} />)}
            {ties.map(t => <CheckLine key={t.field} ok={false} warn m={t.msg!} />)}
            {tr.excluded.msg && <CheckLine ok={false} warn m={tr.excluded.msg} />}
            {unknown.map(v => (
              <CheckLine key={v.label} ok={false} warn m={v.msg!}>
                {onMapValues && <button onClick={onMapValues} className="text-[12px] text-[var(--color-sky)] hover:underline">Map these values</button>}
              </CheckLine>))}
            {rd?.msg && <CheckLine ok={false} warn m={rd.msg} />}
          </div>)}

        {rates.length > 0 && (
          <div className="flex flex-wrap items-center gap-1.5">
            {rates.map((r, i) => r.msg && (
              <span key={i} className="inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11.5px]"
                style={{ borderColor: r.stale || r.outside_tolerance ? TONE.warn : 'var(--color-line-2)', color: r.stale || r.outside_tolerance ? TONE.warn : 'var(--color-mute)' }}>
                {r.msg.label}<InfoButton compact details={messageDetails(r.msg)} />
              </span>))}
          </div>)}

        {m && <MatchSummary m={m} />}

        {(gate.messages?.length ?? 0) > 0 && (
          <div className="rounded-lg px-3 py-2.5 space-y-1" style={{ background: `color-mix(in oklab, ${TONE[g.tone]} 9%, transparent)` }}>
            <div className="text-[11.5px] font-medium" style={{ color: TONE[g.tone] }}>{gate.status === 'blocked' ? 'Why nothing can be imported' : 'Why a second person approves'}</div>
            {gate.messages!.map((r, i) => <div key={i} className="text-[12.5px] text-[var(--color-ink)]"><Said m={r} /></div>)}
          </div>)}
      </div>

      <Declared valueLabel={valueLabel} declRows={declRows} declTotal={declTotal} setDeclRows={setDeclRows} setDeclTotal={setDeclTotal}
        onRecheck={onRecheck} checking={checking} />
    </div>
  )
}

function MatchSummary({ m }: { m: Matching }) {
  const [open, setOpen] = useState(false)
  const labels = m.field_labels ?? {}
  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-2">
        <span className="text-[12px] text-[var(--color-ink)]">Against your book</span>
        <InfoButton compact details={{ title: 'Against your book', sections: [
          { heading: HEADING.shows, body: 'How the rows match the assets you already hold: by your own asset ID, or by name and location. A new row adds an asset; a matched row updates it or leaves it unchanged.' },
          { heading: HEADING.limits, body: 'A blank cell never clears a value we hold. A row that matches more than one asset, or repeats an asset already in this file, is left out and listed in the rows to fix.' }] }} />
        {(m.updates.length > 0 || m.large_changes.length > 0) && (
          <button onClick={() => setOpen(true)} className="ml-auto text-[12px] text-[var(--color-sky)] hover:underline">What changes</button>)}
      </div>
      <Segments parts={[{ n: m.new, tone: 'good', label: 'new' }, { n: m.update, tone: 'warn', label: 'updated' },
        { n: m.unchanged, tone: 'neutral', label: 'unchanged' }, { n: m.ambiguous + m.duplicate, tone: 'bad', label: 'left out' }]} />
      {open && (
        <Dialog title="What this file changes" onClose={() => setOpen(false)} className="sm:max-w-2xl">
          <div className="space-y-4 text-[12.5px]">
            {m.large_changes.length > 0 && (
              <section>
                <h4 className="text-[12px] font-semibold uppercase tracking-[0.08em] text-[var(--color-mute)] m-0 mb-1.5">Large changes — a second person approves</h4>
                <div className="space-y-1">{m.large_changes.map((c, i) => (
                  <div key={i} className="flex items-center gap-2 flex-wrap">
                    <span className="text-[var(--color-ink)]">{c.name}</span>
                    {c.value_change_pct != null && <StatusChip tone="warn" label={`Value ${c.value_change_pct > 0 ? '+' : ''}${c.value_change_pct}%`} />}
                    {c.move_km != null && <StatusChip tone="warn" label={`Moves ${c.move_km} km`} />}
                  </div>))}</div>
              </section>)}
            {m.updates.length > 0 && (
              <section>
                <h4 className="text-[12px] font-semibold uppercase tracking-[0.08em] text-[var(--color-mute)] m-0 mb-1.5">Updated assets</h4>
                <div className="space-y-2">{m.updates.map((u, i) => (
                  <div key={i}>
                    <div className="text-[var(--color-ink)]">{u.name}</div>
                    <div className="mt-0.5 space-y-0.5">{Object.entries(u.changes).map(([f, [a, b]]) => (
                      <div key={f} className="flex items-center gap-1.5 text-[var(--color-mute)]">
                        <span className="w-40 shrink-0 truncate">{labels[f] ?? 'Another field'}</span>
                        <span className="tabular-nums">{shown(a)}</span><ArrowRight size={11} /><span className="tabular-nums text-[var(--color-ink)]">{shown(b)}</span>
                        {typeof a === 'number' && typeof b === 'number' && a !== 0 && (b > a ? <TrendingUp size={11} /> : <TrendingDown size={11} />)}
                        {(f === 'latitude' || f === 'longitude' || f === 'h3_cell') && <MapPin size={11} />}
                      </div>))}</div>
                  </div>))}
                  {m.update > m.updates.length && <div className="text-[var(--color-faint)]">…and {plural(m.update - m.updates.length, 'more asset')}</div>}</div>
              </section>)}
          </div>
        </Dialog>)}
    </div>
  )
}

const shown = (v: unknown) => v == null ? 'blank' : typeof v === 'number' ? v.toLocaleString('en-GB', { maximumFractionDigits: 2 })
  : String(v).length > 28 ? String(v).slice(0, 26) + '…' : String(v)

// What the customer says they sent — optional; the receipt check compares it with the file.
function Declared({ valueLabel, declRows, declTotal, setDeclRows, setDeclTotal, onRecheck, checking }: {
  valueLabel?: string | null; declRows: string; declTotal: string; setDeclRows: (v: string) => void; setDeclTotal: (v: string) => void
  onRecheck: () => void; checking?: boolean
}) {
  const [open, setOpen] = useState(!!(declRows || declTotal))
  const box = 'block mt-0.5 rounded-md border border-[var(--color-line)] bg-[var(--color-bg)] px-2 py-1.5 text-[12px] tabular-nums text-[var(--color-ink)]'
  if (!open) return (
    <div className="px-4 pb-3"><button onClick={() => setOpen(true)} className="text-[12px] text-[var(--color-sky)] hover:underline">Check against what you sent</button></div>)
  return (
    <div className="px-4 pb-3 flex items-end gap-2 flex-wrap">
      <label className="text-[11.5px] text-[var(--color-mute)]">Rows you sent
        <input value={declRows} onChange={e => setDeclRows(e.target.value)} inputMode="numeric" className={`${box} w-28`} /></label>
      {valueLabel && <label className="text-[11.5px] text-[var(--color-mute)]">Total {valueLabel}
        <input value={declTotal} onChange={e => setDeclTotal(e.target.value)} inputMode="decimal" className={`${box} w-44`} /></label>}
      <button onClick={onRecheck} disabled={checking || (!declRows && !declTotal)}
        className="text-[12px] px-3 py-1.5 rounded-lg border border-[var(--color-line)] text-[var(--color-mute)] hover:text-[var(--color-ink)] disabled:opacity-45">{checking ? 'Checking…' : 'Check again'}</button>
      <InfoButton compact details={{ title: 'Check against what you sent', sections: [
        { heading: HEADING.shows, body: 'Enter the number of rows, and the total of the value column, your own system says it exported. We compare them with the file.' },
        { heading: HEADING.read, body: 'A difference means rows or amounts were lost or added on the way. It is listed with the checks, and the batch needs a second person to approve it.' }] }} />
    </div>
  )
}

export function LandingNote({ controls, notes }: { controls: Controls; notes?: Record<string, unknown> }) {
  const l = controls.landing
  if (!l?.msg) return null
  const split = notes && typeof notes.n_new === 'number'
  return (
    <div className="mt-2 space-y-1.5 text-[12.5px]">
      <Said m={l.msg} tone={l.status === 'pass' ? undefined : 'warn'} className={l.status === 'pass' ? 'text-[var(--color-mute)]' : ''} />
      {split && <Segments parts={[{ n: Number(notes!.n_new), tone: 'good', label: 'new' }, { n: Number(notes!.n_updated), tone: 'warn', label: 'updated' },
        { n: Number(notes!.n_unchanged), tone: 'neutral', label: 'unchanged' }]} />}
    </div>
  )
}
