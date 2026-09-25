import { CheckCircle2, AlertTriangle, XCircle, ShieldCheck } from 'lucide-react'

// The intake controls a customer sees between "file chosen" and "rows saved": did everything arrive (receipt), did
// every value keep its meaning (transformation), and is the batch fit to enter the engine (gate). Same panel for
// every sector — the backend runs one implementation (services/ingest/batch_controls.py).
export interface ControlCheck { check: string; label: string; status: 'pass' | 'fail' | 'info'; detail: string }
export interface Controls {
  batch_id?: string
  receipt: { status: string; n_rows: number; checks: ControlCheck[] }
  transformation: {
    status: string; n_form_violations: number; coordinates_usable_pct: number | null
    tie_outs: { field: string; raw_total: number; accepted_total: number; rejected_total: number; status: string }[]
    excluded: { n_rows: number; pct_rows: number; value_field: string | null; value: number | null; pct_value: number | null }
  }
  readiness?: { status: string; n_not_ready: number; value_staged: number }
  matching?: Matching
  gate: { status: 'pass' | 'needs_signoff' | 'blocked'; reasons: string[] }
  landing?: { status: string; n_validated: number; n_landed: number; n_dropped_after_validation: number; detail: string }
}

export interface Matching {
  new: number; update: number; unchanged: number; ambiguous: number; duplicate: number
  updates: { name: string; changes: Record<string, [unknown, unknown]> }[]
  large_changes: { name: string; reasons: string[] }[]
}

const TONE = { pass: 'var(--color-good)', fail: 'var(--color-warn)', attention: 'var(--color-warn)', blocked: 'var(--color-bad, #e0574a)', needs_signoff: 'var(--color-warn)' } as Record<string, string>
const num = (n?: number | null) => n == null ? '—' : Math.abs(n) >= 1e9 ? `${(n / 1e9).toFixed(2)}bn` : Math.abs(n) >= 1e6 ? `${(n / 1e6).toFixed(2)}m` : Math.round(n).toLocaleString()

function Pill({ status, children }: { status: string; children: React.ReactNode }) {
  const c = TONE[status] ?? 'var(--color-faint)'
  return <span className="mono text-[9.5px] px-2 py-0.5 rounded-full whitespace-nowrap" style={{ color: c, background: `color-mix(in oklab, ${c} 14%, transparent)` }}>{children}</span>
}

export function ControlsPanel({ controls, valueLabel, declRows, declTotal, setDeclRows, setDeclTotal, onRecheck, checking }: {
  controls: Controls; valueLabel?: string | null; declRows: string; declTotal: string
  setDeclRows: (v: string) => void; setDeclTotal: (v: string) => void; onRecheck: () => void; checking?: boolean
}) {
  const { receipt, transformation: tr, gate, readiness: rd, matching: m } = controls
  const failed = receipt.checks.filter(c => c.status === 'fail')
  return (
    <div className="border-t border-[var(--color-line)]">
      <div className="flex items-center gap-2 px-4 py-2.5 bg-[var(--color-bg-2)]">
        <ShieldCheck size={14} className="text-[var(--color-faint)]" />
        <span className="mono text-[10.5px] uppercase tracking-wide text-[var(--color-faint)]">Intake checks</span>
        <span className="ml-auto"><Pill status={gate.status}>{gate.status === 'pass' ? 'clear to import' : gate.status === 'blocked' ? 'blocked' : 'needs sign-off'}</Pill></span>
      </div>

      <div className="px-4 py-3 space-y-2.5 text-[12px]">
        <div className="flex items-start gap-2">
          {receipt.status === 'pass' ? <CheckCircle2 size={14} className="mt-0.5 shrink-0" style={{ color: TONE.pass }} /> : <XCircle size={14} className="mt-0.5 shrink-0" style={{ color: TONE.fail }} />}
          <div><b className="text-[var(--color-ink)]">Arrived complete</b> <span className="text-[var(--color-mute)]">— {receipt.n_rows} rows{receipt.checks.some(c => c.check.startsWith('declared')) ? ', matched to what you said you sent' : ''}, no duplicates, not a file already imported.</span>
            {failed.map(c => <div key={c.check} style={{ color: TONE.fail }}>{c.detail || c.label}</div>)}</div>
        </div>
        <div className="flex items-start gap-2">
          {tr.status === 'pass' ? <CheckCircle2 size={14} className="mt-0.5 shrink-0" style={{ color: TONE.pass }} /> : <XCircle size={14} className="mt-0.5 shrink-0" style={{ color: TONE.fail }} />}
          <div><b className="text-[var(--color-ink)]">Values kept their meaning</b> <span className="text-[var(--color-mute)]">— every total ties (raw = accepted + rejected){tr.coordinates_usable_pct != null ? `; ${tr.coordinates_usable_pct}% of rows have a usable location` : ''}.</span>
            {tr.excluded.n_rows > 0 && <div style={{ color: TONE.fail }}>{tr.excluded.n_rows} row{tr.excluded.n_rows === 1 ? '' : 's'} ({tr.excluded.pct_rows}%) will be left out{tr.excluded.value != null ? `, carrying ${num(tr.excluded.value)} (${tr.excluded.pct_value}%) of the ${valueLabel ?? tr.excluded.value_field}` : ''}.</div>}
            {tr.tie_outs.filter(t => t.status !== 'pass').map(t => <div key={t.field} style={{ color: TONE.fail }}>{t.field} does not tie.</div>)}</div>
        </div>
        {rd && (
          <div className="flex items-start gap-2">
            {rd.n_not_ready === 0 ? <CheckCircle2 size={14} className="mt-0.5 shrink-0" style={{ color: TONE.pass }} /> : <XCircle size={14} className="mt-0.5 shrink-0" style={{ color: TONE.fail }} />}
            <div><b className="text-[var(--color-ink)]">Ready for the engine</b> <span className="text-[var(--color-mute)]">— every accepted row has a real location, a positive value and plausible attributes.</span>
              {rd.n_not_ready > 0 && <div style={{ color: TONE.fail }}>{rd.n_not_ready} row{rd.n_not_ready === 1 ? '' : 's'} can’t be used by the engine (listed above with the reason).</div>}</div>
          </div>
        )}
        {m && <MatchRow m={m} />}
        {gate.reasons.length > 0 && (
          <div className="flex items-start gap-2 rounded-lg px-3 py-2" style={{ background: `color-mix(in oklab, ${TONE[gate.status]} 9%, transparent)` }}>
            <AlertTriangle size={14} className="mt-0.5 shrink-0" style={{ color: TONE[gate.status] }} />
            <ul className="space-y-0.5 text-[12px] text-[var(--color-ink)]">{gate.reasons.map((r, i) => <li key={i}>{r}</li>)}</ul>
          </div>
        )}
      </div>

      <div className="px-4 pb-3 flex items-end gap-2 flex-wrap">
        <div className="w-full mono text-[9.5px] text-[var(--color-faint)]">Optional — tell us what you sent and we will check it adds up:</div>
        <label className="text-[11px] text-[var(--color-mute)]">rows sent<input value={declRows} onChange={e => setDeclRows(e.target.value)} inputMode="numeric"
          className="block mt-0.5 w-28 rounded-md border border-[var(--color-line)] bg-[var(--color-bg)] px-2 py-1.5 mono text-[11.5px] text-[var(--color-ink)]" placeholder="e.g. 4200" /></label>
        {valueLabel && <label className="text-[11px] text-[var(--color-mute)]">total {valueLabel}<input value={declTotal} onChange={e => setDeclTotal(e.target.value)} inputMode="decimal"
          className="block mt-0.5 w-44 rounded-md border border-[var(--color-line)] bg-[var(--color-bg)] px-2 py-1.5 mono text-[11.5px] text-[var(--color-ink)]" placeholder="e.g. 1250000000" /></label>}
        <button onClick={onRecheck} disabled={checking || (!declRows && !declTotal)}
          className="mono text-[11px] px-3 py-1.5 rounded-lg border border-[var(--color-line)] text-[var(--color-mute)] hover:text-[var(--color-ink)] disabled:opacity-45">{checking ? 'checking…' : 'Re-check'}</button>
      </div>
    </div>
  )
}

const FIELD = (f: string) => f.replace(/_eur$/, '').replace(/^primary_value$/, 'value').replace(/^entity_name$|^plot_name$/, 'name').replaceAll('_', ' ')
const show = (v: unknown) => v == null ? 'blank' : typeof v === 'number' ? num(v) : String(v).length > 28 ? String(v).slice(0, 26) + '…' : String(v)

function MatchRow({ m }: { m: Matching }) {
  const held = m.update + m.unchanged
  return (
    <div className="flex items-start gap-2">
      <CheckCircle2 size={14} className="mt-0.5 shrink-0" style={{ color: m.large_changes.length ? TONE.fail : TONE.pass }} />
      <div className="min-w-0"><b className="text-[var(--color-ink)]">Matched to your book</b> <span className="text-[var(--color-mute)]">— {m.new} new, {m.update} updated, {m.unchanged} unchanged{held ? ' (matched on your asset ID, or name + location)' : ''}. A blank cell never clears a value we hold.</span>
        {(m.ambiguous > 0 || m.duplicate > 0) && <div style={{ color: TONE.fail }}>{m.ambiguous > 0 ? `${m.ambiguous} row${m.ambiguous === 1 ? '' : 's'} match more than one asset` : ''}{m.ambiguous && m.duplicate ? '; ' : ''}{m.duplicate > 0 ? `${m.duplicate} row${m.duplicate === 1 ? '' : 's'} repeat an asset already in this file` : ''} — left out, listed above.</div>}
        {m.updates.length > 0 && (
          <details className="mt-1"><summary className="cursor-pointer mono text-[10.5px] text-[var(--color-sky)]">what changes ({m.update})</summary>
            <div className="mt-1 space-y-0.5 text-[11.5px]">{m.updates.map((u, i) => (
              <div key={i}><span className="text-[var(--color-ink)]">{u.name}</span> <span className="text-[var(--color-mute)]">{Object.entries(u.changes).map(([f, [a, b]]) => `${FIELD(f)} ${show(a)} → ${show(b)}`).join(' · ')}</span></div>))}
              {m.update > m.updates.length && <div className="mono text-[10px] text-[var(--color-faint)]">…and {m.update - m.updates.length} more</div>}</div>
          </details>
        )}
        {m.large_changes.length > 0 && <div style={{ color: TONE.fail }}>Big changes: {m.large_changes.slice(0, 3).map(c => `${c.name} (${c.reasons.join(', ')})`).join('; ')}{m.large_changes.length > 3 ? '; …' : ''}</div>}
      </div>
    </div>
  )
}

export function LandingNote({ controls, notes }: { controls: Controls; notes?: Record<string, unknown> }) {
  const l = controls.landing
  if (!l) return null
  const split = notes && typeof notes.n_new === 'number' ? ` — ${notes.n_new} new, ${notes.n_updated} updated, ${notes.n_unchanged} unchanged` : ''
  return (
    <div className="mt-2 text-[12px]" style={{ color: l.status === 'pass' ? 'var(--color-mute)' : TONE.attention }}>
      {l.status === 'pass' ? `Reconciled: all ${l.n_landed} rows are in your book${split}.` : `Landing check: ${l.detail} (${l.n_landed} of ${l.n_validated} validated rows landed).`}
      {controls.batch_id && <span className="mono text-[10px] text-[var(--color-faint)] ml-2">batch {controls.batch_id.slice(0, 8)}</span>}
    </div>
  )
}
