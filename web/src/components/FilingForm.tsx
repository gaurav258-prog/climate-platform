import { useState, Fragment } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ExternalLink, FileSpreadsheet, Pencil, Check, X, Clock } from 'lucide-react'
import { api, ApiError } from '../lib/api'
import { useAuth } from '../lib/auth'
import { Card } from './ui'
import { hazardLabel } from '../lib/hazards'

// The final form — the frozen disclosure, shown two ways over ONE set of figures:
//   • Official form — the regulator's actual Annex / template layout (SFDR RTS Annex I Table 1, EU-Taxonomy
//     Art.8 GAR summary, ESRS E1 …) as it will be submitted.
//   • Datapoints — the flat labelled list, each cell showing its source (book / calc).
// A preparer can propose a MANUAL override of a numeric cell (with a reason) from either view; it needs
// 4-eyes approval before it lands, and an approved cell is visually distinct with its full provenance. The
// frozen snapshot itself is never mutated — overrides are a separate audited layer merged at read time.

interface Override { reason: string; by: string; at: string; approved_by: string; approved_at: string }
interface Pending { value: number; reason: string; by: string }
interface Dp {
  key: string; label: string; value: number | string | null; fmt: string; unit: string | null; source: string; note: string | null
  manual?: boolean; original_value?: number | null; override?: Override; pending?: Pending
}
interface Group { group: string; datapoints: Dp[] }
interface AnnexCell { text?: string; dp?: Dp; num?: boolean }
interface AnnexRow { type: 'row' | 'subheader'; label?: string; cells?: AnnexCell[] }
interface AnnexSection { title: string; note: string | null; columns: string[]; rows: AnnexRow[] }
interface Annex { official_name: string; authority: string | null; official_form: string | null; legal_basis: string | null; form_url: string | null; sections: AnnexSection[] }
interface Form { framework: string; label: string; period_label: string; status: string; snapshot_version: number | null; official_form_url: string | null; n_manual: number; n_pending: number; groups: Group[]; annex: Annex | null }

const eur = (n: number) => n >= 1e9 ? `€${(n / 1e9).toFixed(2)}bn` : n >= 1e6 ? `€${(n / 1e6).toFixed(1)}m` : `€${Math.round(n / 1e3)}k`
function fmt(v: number | string | null, f: string): string {
  if (v == null) return '—'
  if (typeof v === 'string') return v
  switch (f) {
    case 'eur': return eur(v)
    case 'pct': return `${v}%`
    case 'tco2e': return Math.round(v).toLocaleString('en-GB')
    default: return Number.isInteger(v) ? v.toLocaleString('en-GB') : v.toLocaleString('en-GB', { maximumFractionDigits: 2 })
  }
}
const dpLabel = (d: Dp) => d.key.startsWith('hazard.') ? hazardLabel(d.label) : d.label
const EDITABLE_STATUS = ['draft', 'returned', 'in_review', 'approved']  // never edit a submitted/accepted/superseded filing

export default function FilingForm({ filingId }: { filingId: string }) {
  const { profile } = useAuth()
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['filing-form', filingId], queryFn: () => api.get<Form>(`/v1/filings/${filingId}/form`) })
  const [edit, setEdit] = useState<string | null>(null)
  const [view, setView] = useState<'official' | 'datapoints'>('official')
  const d = q.data
  if (!d || d.groups.length === 0) return null
  const canEdit = (profile?.permissions ?? []).includes('approvals.create') && EDITABLE_STATUS.includes(d.status)
  const refresh = () => { qc.invalidateQueries({ queryKey: ['filing-form', filingId] }); qc.invalidateQueries({ queryKey: ['approvals'] }) }
  const editProps = { filingId, canEdit, edit, setEdit, onDone: () => { setEdit(null); refresh() } }
  const hasAnnex = !!d.annex && d.annex.sections.length > 0

  return (
    <div>
      <div className="flex items-center justify-between gap-3 mb-2 flex-wrap">
        <div className="mono text-[10px] uppercase tracking-widest text-[var(--color-faint)]">Final form · as it will be submitted
          {d.n_manual > 0 && <span className="ml-2" style={{ color: 'var(--color-warn)' }}>· {d.n_manual} manual</span>}
          {d.n_pending > 0 && <span className="ml-2" style={{ color: 'var(--color-sky)' }}>· {d.n_pending} pending 4-eyes</span>}
        </div>
        <div className="flex items-center gap-2">
          {hasAnnex && (
            <div className="flex gap-0.5 p-0.5 rounded-lg border border-[var(--color-line-2)]">
              {(['official', 'datapoints'] as const).map(v => (
                <button key={v} onClick={() => setView(v)} className={`px-2 py-0.5 rounded-md mono text-[10px] uppercase tracking-wide transition ${view === v ? 'bg-[var(--color-bg-2)] text-[var(--color-ink)]' : 'text-[var(--color-faint)] hover:text-[var(--color-ink)]'}`}>{v === 'official' ? 'Official form' : 'Datapoints'}</button>
              ))}
            </div>
          )}
          {d.official_form_url && <a href={d.official_form_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 mono text-[10px] text-[var(--color-mute)] hover:text-[var(--color-sky)]"><FileSpreadsheet size={11} /> official form <ExternalLink size={10} /></a>}
        </div>
      </div>

      {hasAnnex && view === 'official'
        ? <AnnexView annex={d.annex!} {...editProps} />
        : <DatapointList groups={d.groups} {...editProps} />}

      <div className="mono text-[9.5px] text-[var(--color-faint)] mt-2"><span className="text-[var(--color-sky)]">book</span> = uploaded book · <span className="text-[var(--color-mute)]">calc</span> = golden source · <span style={{ color: 'var(--color-warn)' }}>manual</span> = analyst override (4-eyes, audited)</div>
    </div>
  )
}

type EditProps = { filingId: string; canEdit: boolean; edit: string | null; setEdit: (k: string | null) => void; onDone: () => void }

// ── the regulator's official Annex / template layout ──────────────────────────────────────────────────────
function AnnexView({ annex, ...ep }: { annex: Annex } & EditProps) {
  return (
    <Card className="p-0 overflow-hidden">
      <div className="px-4 py-3 border-b border-[var(--color-line)]">
        <div className="text-[13px] text-[var(--color-ink)]">{annex.official_name}</div>
        <div className="mono text-[9.5px] text-[var(--color-faint)] mt-0.5">{[annex.official_form, annex.authority].filter(Boolean).join(' · ')}</div>
      </div>
      {annex.sections.map((s, si) => (
        <div key={si} className={si > 0 ? 'border-t border-[var(--color-line)]' : ''}>
          <div className="px-4 py-2 bg-[var(--color-bg-2)] mono text-[9.5px] uppercase tracking-wide text-[var(--color-faint)]">{s.title}</div>
          <div className="overflow-x-auto">
            <table className="w-full text-[12px]">
              <thead>
                <tr className="text-left">
                  {s.columns.map((c, ci) => (
                    <th key={ci} className={`px-4 py-1.5 mono text-[9px] uppercase tracking-wide text-[var(--color-faint)] font-medium ${ci >= s.columns.length - 1 ? 'text-right' : ''}`}>{c}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {s.rows.map((r, ri) => {
                  if (r.type === 'subheader') return (
                    <tr key={ri}><td colSpan={s.columns.length} className="px-4 pt-3 pb-1 mono text-[10px] uppercase tracking-wide text-[var(--color-sky)]">{r.label}</td></tr>
                  )
                  const cells = r.cells ?? []
                  const dpCell = cells.find(c => c.dp)?.dp
                  const editingHere = !!dpCell && ep.edit === dpCell.key
                  return (
                    <Fragment key={ri}>
                      <tr className="border-t border-[var(--color-line)]" style={dpCell?.manual ? { background: 'color-mix(in oklab, var(--color-warn) 8%, transparent)' } : undefined}>
                        {cells.map((c, ci) => {
                          const last = ci === cells.length - 1
                          if (c.dp) return <td key={ci} className="px-4 py-1.5 text-right align-top"><CellValue dp={c.dp} {...ep} /></td>
                          return <td key={ci} className={`px-4 py-1.5 align-top ${c.num ? 'text-right mono tabular-nums text-[11.5px] text-[var(--color-ink)]' : last ? 'text-right mono text-[11px] text-[var(--color-faint)]' : 'text-[var(--color-ink)]'}`}>{c.text}</td>
                        })}
                      </tr>
                      {editingHere && dpCell && (
                        <tr><td colSpan={s.columns.length} className="px-4 pb-2"><OverrideEditor filingId={ep.filingId} dp={dpCell} onClose={() => ep.setEdit(null)} onDone={ep.onDone} /></td></tr>
                      )}
                    </Fragment>
                  )
                })}
              </tbody>
            </table>
          </div>
          {s.note && <div className="px-4 py-2 mono text-[9.5px] text-[var(--color-faint)] leading-relaxed border-t border-[var(--color-line)]">{s.note}</div>}
        </div>
      ))}
    </Card>
  )
}

// a value cell — the merged datapoint with its source/manual badge, a pending marker, and (when editable) the
// override pencil. Shared by the official form and the datapoint list.
function CellValue({ dp, canEdit, edit, setEdit }: { dp: Dp } & EditProps) {
  const editable = canEdit && dp.fmt !== 'text' && typeof dp.value === 'number'
  return (
    <span className="inline-flex items-center gap-1.5 justify-end">
      {dp.pending && <span className="mono text-[9px] uppercase tracking-wide px-1.5 py-0.5 rounded inline-flex items-center gap-1" style={{ color: 'var(--color-sky)', background: 'color-mix(in oklab, var(--color-sky) 14%, transparent)' }}><Clock size={9} /> pending → {fmt(dp.pending.value, dp.fmt)}</span>}
      {dp.manual
        ? <span title={`Manual override · was ${fmt(dp.original_value ?? null, dp.fmt)} · ${dp.override?.reason} · by ${dp.override?.by}, approved by ${dp.override?.approved_by}`}
            className="mono text-[9px] uppercase tracking-wide px-1.5 py-0.5 rounded" style={{ color: 'var(--color-warn)', background: 'color-mix(in oklab, var(--color-warn) 16%, transparent)' }}>manual ⓘ</span>
        : dp.value != null && <span className="mono text-[9px] uppercase tracking-wide px-1.5 py-0.5 rounded" style={{ color: dp.source === 'book' ? 'var(--color-sky)' : 'var(--color-mute)', background: 'color-mix(in oklab, var(--color-line) 60%, transparent)' }}>{dp.source === 'book' ? 'book' : 'calc'}</span>}
      <span className="mono text-[12.5px] tabular-nums" style={{ color: dp.manual ? 'var(--color-warn)' : 'var(--color-ink)' }}>{fmt(dp.value, dp.fmt)}</span>
      {dp.unit && <span className="mono text-[9px] text-[var(--color-faint)]">{dp.unit}</span>}
      {editable && edit !== dp.key && <button onClick={() => setEdit(dp.key)} title="Propose a manual override (4-eyes)" className="text-[var(--color-faint)] hover:text-[var(--color-sky)]"><Pencil size={11} /></button>}
    </span>
  )
}

// ── the flat labelled datapoint list ──────────────────────────────────────────────────────────────────────
function DatapointList({ groups, ...ep }: { groups: Group[] } & EditProps) {
  return (
    <Card className="p-0 overflow-hidden">
      {groups.map((g, gi) => (
        <div key={gi} className={gi > 0 ? 'border-t border-[var(--color-line)]' : ''}>
          <div className="px-4 py-2 bg-[var(--color-bg-2)] mono text-[9.5px] uppercase tracking-wide text-[var(--color-faint)]">{g.group}</div>
          <div className="divide-y divide-[var(--color-line)]">
            {g.datapoints.map(dp => {
              const isEditing = ep.edit === dp.key
              return (
                <div key={dp.key} className="px-4 py-2 text-[12.5px]" style={dp.manual ? { background: 'color-mix(in oklab, var(--color-warn) 8%, transparent)' } : undefined}>
                  <div className="flex items-center gap-3">
                    <div className="min-w-0 flex-1">
                      <span className="text-[var(--color-ink)]">{dpLabel(dp)}</span>
                      {dp.note && <span className="mono text-[10px] text-[var(--color-faint)] ml-1.5">· {dp.note}</span>}
                    </div>
                    <CellValue dp={dp} {...ep} />
                  </div>
                  {isEditing && <OverrideEditor filingId={ep.filingId} dp={dp} onClose={() => ep.setEdit(null)} onDone={ep.onDone} />}
                  {dp.manual && dp.override && (
                    <div className="mono text-[10px] text-[var(--color-faint)] mt-1">was {fmt(dp.original_value ?? null, dp.fmt)} · “{dp.override.reason}” · {dp.override.by} → approved {dp.override.approved_by}</div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      ))}
    </Card>
  )
}

function OverrideEditor({ filingId, dp, onClose, onDone }: { filingId: string; dp: Dp; onClose: () => void; onDone: () => void }) {
  const [value, setValue] = useState(String(typeof dp.value === 'number' ? dp.value : ''))
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const save = async () => {
    const v = Number(value)
    if (!isFinite(v)) { setErr('Enter a number.'); return }
    if (!reason.trim()) { setErr('A reason is required.'); return }
    setBusy(true); setErr(null)
    try {
      await api.post(`/v1/filings/${filingId}/overrides`, { datapoint_key: dp.key, value: v, reason: reason.trim() })
      onDone()
    } catch (e) { setErr(e instanceof ApiError ? String((e.body as { message?: string })?.message ?? e.message) : 'Could not propose the override.') }
    finally { setBusy(false) }
  }
  const box = 'bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-2.5 py-1.5 text-[12.5px] outline-none focus:border-[var(--color-sky)]'
  return (
    <div className="mt-2 rounded-lg border border-[var(--color-line-2)] bg-[var(--color-bg-2)] p-2.5 space-y-2 text-left">
      {err && <div className="text-[11.5px] text-[var(--color-bad)]">{err}</div>}
      <div className="mono text-[10px] text-[var(--color-faint)]">Override · {dpLabel(dp)}</div>
      <div className="flex flex-wrap items-center gap-2">
        <span className="mono text-[10px] text-[var(--color-faint)]">value ({dp.fmt}):</span>
        <input value={value} onChange={e => setValue(e.target.value)} className={`${box} w-40 mono`} placeholder="new value (raw)" />
        <input value={reason} onChange={e => setReason(e.target.value)} className={`${box} flex-1 min-w-[200px]`} placeholder="Reason (required · audited)" />
        <button onClick={save} disabled={busy} className="inline-flex items-center gap-1 rounded-lg bg-[var(--color-sky)] text-[var(--color-on-accent)] px-3 py-1.5 text-[12px] font-medium disabled:opacity-50"><Check size={13} /> Propose</button>
        <button onClick={onClose} className="inline-flex items-center gap-1 rounded-lg border border-[var(--color-line-2)] px-2.5 py-1.5 text-[12px] text-[var(--color-mute)]"><X size={13} /></button>
      </div>
      <div className="mono text-[9.5px] text-[var(--color-faint)]">This needs a second pair of eyes to approve before it lands on the form; the original stays on record.</div>
    </div>
  )
}
