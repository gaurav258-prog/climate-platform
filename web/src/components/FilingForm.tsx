import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ExternalLink, FileSpreadsheet, Pencil, Check, X, Clock } from 'lucide-react'
import { api, ApiError } from '../lib/api'
import { useAuth } from '../lib/auth'
import { Card } from './ui'
import { hazardLabel } from '../lib/hazards'

// The final form — the frozen disclosure as the submittable datapoint form. Every line shows its value and
// source (book / calc). A preparer can propose a MANUAL override of a numeric cell (with a reason); it needs
// 4-eyes approval before it lands, and an approved cell is visually distinct from calculated ones with its
// full provenance (original value · who · when · why · who approved) on hover. The snapshot stays immutable.

interface Override { reason: string; by: string; at: string; approved_by: string; approved_at: string }
interface Pending { value: number; reason: string; by: string }
interface Dp {
  key: string; label: string; value: number | string | null; fmt: string; unit: string | null; source: string; note: string | null
  manual?: boolean; original_value?: number | null; override?: Override; pending?: Pending
}
interface Group { group: string; datapoints: Dp[] }
interface Form { framework: string; label: string; period_label: string; status: string; snapshot_version: number | null; official_form_url: string | null; n_manual: number; n_pending: number; groups: Group[] }

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
  const d = q.data
  if (!d || d.groups.length === 0) return null
  const canEdit = (profile?.permissions ?? []).includes('approvals.create') && EDITABLE_STATUS.includes(d.status)
  const refresh = () => { qc.invalidateQueries({ queryKey: ['filing-form', filingId] }); qc.invalidateQueries({ queryKey: ['approvals'] }) }

  return (
    <div>
      <div className="flex items-center justify-between gap-3 mb-2">
        <div className="mono text-[10px] uppercase tracking-widest text-[var(--color-faint)]">Final form · as it will be submitted
          {d.n_manual > 0 && <span className="ml-2" style={{ color: 'var(--color-warn)' }}>· {d.n_manual} manual</span>}
          {d.n_pending > 0 && <span className="ml-2" style={{ color: 'var(--color-sky)' }}>· {d.n_pending} pending 4-eyes</span>}
        </div>
        {d.official_form_url && <a href={d.official_form_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 mono text-[10px] text-[var(--color-mute)] hover:text-[var(--color-sky)]"><FileSpreadsheet size={11} /> official form <ExternalLink size={10} /></a>}
      </div>
      <Card className="p-0 overflow-hidden">
        {d.groups.map((g, gi) => (
          <div key={gi} className={gi > 0 ? 'border-t border-[var(--color-line)]' : ''}>
            <div className="px-4 py-2 bg-[var(--color-bg-2)] mono text-[9.5px] uppercase tracking-wide text-[var(--color-faint)]">{g.group}</div>
            <div className="divide-y divide-[var(--color-line)]">
              {g.datapoints.map(dp => {
                const editable = canEdit && dp.fmt !== 'text' && typeof dp.value === 'number'
                const isEditing = edit === dp.key
                return (
                  <div key={dp.key} className="px-4 py-2 text-[12.5px]" style={dp.manual ? { background: 'color-mix(in oklab, var(--color-warn) 8%, transparent)' } : undefined}>
                    <div className="flex items-center gap-3">
                      <div className="min-w-0 flex-1">
                        <span className="text-[var(--color-ink)]">{dpLabel(dp)}</span>
                        {dp.unit && <span className="mono text-[10px] text-[var(--color-faint)] ml-1.5">{dp.unit}</span>}
                        {dp.note && <span className="mono text-[10px] text-[var(--color-faint)] ml-1.5">· {dp.note}</span>}
                        {dp.pending && <span className="mono text-[9px] uppercase tracking-wide ml-2 px-1.5 py-0.5 rounded inline-flex items-center gap-1" style={{ color: 'var(--color-sky)', background: 'color-mix(in oklab, var(--color-sky) 14%, transparent)' }}><Clock size={9} /> pending 4-eyes → {fmt(dp.pending.value, dp.fmt)}</span>}
                      </div>
                      {dp.manual
                        ? <span title={`Manual override · was ${fmt(dp.original_value ?? null, dp.fmt)} · ${dp.override?.reason} · by ${dp.override?.by}, approved by ${dp.override?.approved_by}`}
                            className="mono text-[9px] uppercase tracking-wide px-1.5 py-0.5 rounded shrink-0" style={{ color: 'var(--color-warn)', background: 'color-mix(in oklab, var(--color-warn) 16%, transparent)' }}>manual ⓘ</span>
                        : <span className="mono text-[9px] uppercase tracking-wide px-1.5 py-0.5 rounded shrink-0" style={{ color: dp.source === 'book' ? 'var(--color-sky)' : 'var(--color-mute)', background: 'color-mix(in oklab, var(--color-line) 60%, transparent)' }}>{dp.source === 'book' ? 'book' : 'calc'}</span>}
                      <span className="mono text-[12.5px] tabular-nums text-right w-28 shrink-0" style={{ color: dp.manual ? 'var(--color-warn)' : 'var(--color-ink)' }}>{fmt(dp.value, dp.fmt)}</span>
                      {editable && !isEditing && <button onClick={() => setEdit(dp.key)} title="Propose a manual override (4-eyes)" className="text-[var(--color-faint)] hover:text-[var(--color-sky)] shrink-0"><Pencil size={12} /></button>}
                      {!editable && <span className="w-3 shrink-0" />}
                    </div>
                    {isEditing && <OverrideEditor filingId={filingId} dp={dp} onClose={() => setEdit(null)} onDone={() => { setEdit(null); refresh() }} />}
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
      <div className="mono text-[9.5px] text-[var(--color-faint)] mt-2"><span className="text-[var(--color-sky)]">book</span> = uploaded book · <span className="text-[var(--color-mute)]">calc</span> = golden source · <span style={{ color: 'var(--color-warn)' }}>manual</span> = analyst override (4-eyes, audited)</div>
    </div>
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
    <div className="mt-2 rounded-lg border border-[var(--color-line-2)] bg-[var(--color-bg-2)] p-2.5 space-y-2">
      {err && <div className="text-[11.5px] text-[var(--color-bad)]">{err}</div>}
      <div className="flex flex-wrap items-center gap-2">
        <span className="mono text-[10px] text-[var(--color-faint)]">override value ({dp.fmt}):</span>
        <input value={value} onChange={e => setValue(e.target.value)} className={`${box} w-40 mono`} placeholder="new value (raw)" />
        <input value={reason} onChange={e => setReason(e.target.value)} className={`${box} flex-1 min-w-[200px]`} placeholder="Reason (required · audited)" />
        <button onClick={save} disabled={busy} className="inline-flex items-center gap-1 rounded-lg bg-[var(--color-sky)] text-[var(--color-on-accent)] px-3 py-1.5 text-[12px] font-medium disabled:opacity-50"><Check size={13} /> Propose</button>
        <button onClick={onClose} className="inline-flex items-center gap-1 rounded-lg border border-[var(--color-line-2)] px-2.5 py-1.5 text-[12px] text-[var(--color-mute)]"><X size={13} /></button>
      </div>
      <div className="mono text-[9.5px] text-[var(--color-faint)]">This needs a second pair of eyes to approve before it lands on the form; the original stays on record.</div>
    </div>
  )
}
