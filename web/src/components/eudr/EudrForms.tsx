import { useState, type ReactNode } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Dialog } from '../Dialog'
import { Button } from '../ui'
import { api, apiMessage } from '../../lib/api'
import { toast } from '../../lib/toast'
import { ASPECT_LABEL, EVENT_LABEL, inp, lbl, type Records, type RecordsPlot, type StatementPlot } from './types'

// The operator's EUDR records, each a governed request (services/eudr/records.py): the server says what is missing, the
// form never fills a choice in for the operator. Status and risk assessment go to a second person for approval.

function Form({ title, onClose, busy, ready = true, onSubmit, submit, children }: {
  title: string; onClose: () => void; busy: boolean; ready?: boolean; onSubmit: () => void; submit: string; children: ReactNode
}) {
  return (
    <Dialog title={title} onClose={onClose} className="max-w-xl">
      <div className="space-y-3 max-h-[70vh] overflow-y-auto pr-1">{children}</div>
      <div className="flex justify-end gap-2 mt-4">
        <Button variant="ghost" onClick={onClose}>Cancel</Button>
        <Button onClick={onSubmit} disabled={busy || !ready}>{busy ? 'Sending…' : submit}</Button>
      </div>
    </Dialog>
  )
}

function useSend<T>(fn: () => Promise<T>, done: string, onDone: () => void) {
  return useMutation({
    mutationFn: fn,
    onSuccess: () => { toast.success(done); onDone() },
    onError: (e) => toast.error(apiMessage(e, 'Not saved.')),
  })
}

export function StatusForm({ rec, onClose, onDone }: { rec: Records; onClose: () => void; onDone: () => void }) {
  const s = rec.status
  const [f, setF] = useState({ effective_from: '', size_class: s?.size_class ?? '', country: s?.country ?? '', address: s?.address ?? '',
    eori: s?.eori ?? '', established_on: s?.established_on ?? '', basis: '' })
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value })
  const m = useSend(() => api.post('/v1/eudr/status', { ...f, eori: f.eori || null, established_on: f.established_on || null, basis: f.basis || null }),
    'Sent for approval.', onDone)
  return (
    <Form title="The undertaking's EUDR status" onClose={onClose} busy={m.isPending} onSubmit={() => m.mutate()} submit="Send for approval">
      <p className="text-[12px] text-[var(--color-mute)]">Annex II point 1: name, address and — for goods entering or leaving the market — the EORI number. The size class decides the application date (Art. 38(3)).</p>
      <div className="grid grid-cols-2 gap-3">
        <div><label className={lbl}>In force from *</label><input type="date" className={inp} value={f.effective_from} onChange={set('effective_from')} /></div>
        <div><label className={lbl}>Size class *</label>
          <select className={inp} value={f.size_class} onChange={set('size_class')}>
            <option value="">— state it —</option>{rec.size_classes.map(c => <option key={c} value={c}>{c}</option>)}
          </select></div>
        <div><label className={lbl}>Country (ISO) *</label><input className={inp} maxLength={2} value={f.country} onChange={set('country')} /></div>
        <div><label className={lbl}>EORI</label><input className={inp} maxLength={17} value={f.eori} onChange={set('eori')} /></div>
      </div>
      <div><label className={lbl}>Address *</label><input className={inp} value={f.address} onChange={set('address')} /></div>
      {(f.size_class === 'micro' || f.size_class === 'small') &&
        <div><label className={lbl}>Established as micro / small on</label><input type="date" className={inp} value={f.established_on} onChange={set('established_on')} /></div>}
      <div><label className={lbl}>Basis</label><textarea className={inp} rows={2} value={f.basis} onChange={set('basis')} /></div>
    </Form>
  )
}

export function ReadForm({ plots, onClose, onDone }: { plots: RecordsPlot[]; onClose: () => void; onDone: () => void }) {
  const [pct, setPct] = useState('')
  const [radius, setRadius] = useState('')
  const points = plots.filter(p => !p.has_polygon).length
  const m = useSend(() => api.post('/v1/eudr/plots/read', { plot_ids: plots.map(p => p.plot_id),
    treecover_min_pct: pct ? Number(pct) : null, point_radius_m: radius ? Number(radius) : null }),
    `Reading ${plots.length} plot${plots.length === 1 ? '' : 's'} — refresh in a moment.`, onDone)
  return (
    <Form title={`Read ${plots.length} plot${plots.length === 1 ? '' : 's'}`} onClose={onClose} busy={m.isPending} onSubmit={() => m.mutate()} submit="Read">
      <p className="text-[12px] text-[var(--color-mute)]">Tree-cover loss after 31 December 2020 inside each plot is always recorded. The platform sets no forest threshold: state one to also read loss only where tree cover in 2000 was at least that percentage.</p>
      <div className="grid grid-cols-2 gap-3">
        <div><label className={lbl}>Tree cover in 2000, at least (%)</label><input className={inp} inputMode="numeric" value={pct} onChange={e => setPct(e.target.value)} placeholder="not stated" /></div>
        <div><label className={lbl}>Radius around a point plot (m)</label><input className={inp} inputMode="decimal" value={radius} onChange={e => setRadius(e.target.value)} placeholder="not stated" /></div>
      </div>
      {points > 0 && !radius && <p className="text-[12px] text-[var(--color-warn)]">{points} plot{points === 1 ? ' is' : 's are'} a point with no area: without a radius {points === 1 ? 'its' : 'their'} reading is "not assessable".</p>}
    </Form>
  )
}

export function EvidenceForm({ rec, movementId, plots, onClose, onDone }: {
  rec: Records; movementId: string; plots: StatementPlot[]; onClose: () => void; onDone: () => void
}) {
  const [f, setF] = useState({ subject: 'movement', aspect: '', document_kind: '', document_ref: '', issued_by: '', valid_from: '', valid_until: '' })
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value })
  const subj = f.subject === 'movement' ? { movement_id: movementId } : { plot_id: f.subject }
  const m = useSend(() => api.post('/v1/eudr/evidence', { ...subj, aspect: f.aspect, document_kind: f.document_kind,
    document_ref: f.document_ref || null, issued_by: f.issued_by || null, valid_from: f.valid_from || null, valid_until: f.valid_until || null }),
    'Evidence recorded.', onDone)
  return (
    <Form title="Legality evidence" onClose={onClose} busy={m.isPending} onSubmit={() => m.mutate()} submit="Record">
      <p className="text-[12px] text-[var(--color-mute)]">Production in accordance with the relevant legislation of the country of production (Art. 3(b), 2(40)). Evidence is kept; a correction withdraws it, never edits it.</p>
      <div className="grid grid-cols-2 gap-3">
        <div><label className={lbl}>For *</label>
          <select className={inp} value={f.subject} onChange={set('subject')}>
            <option value="movement">this shipment</option>
            {plots.map(p => <option key={p.plot_id} value={p.plot_id}>plot · {p.plot_name ?? p.plot_id.slice(0, 8)}</option>)}
          </select></div>
        <div><label className={lbl}>Aspect *</label>
          <select className={inp} value={f.aspect} onChange={set('aspect')}>
            <option value="">— choose —</option>{rec.aspects.map(a => <option key={a} value={a}>{ASPECT_LABEL[a] ?? a}</option>)}
          </select></div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div><label className={lbl}>Document *</label><input className={inp} value={f.document_kind} onChange={set('document_kind')} placeholder="e.g. land title" /></div>
        <div><label className={lbl}>Reference</label><input className={inp} value={f.document_ref} onChange={set('document_ref')} /></div>
        <div className="col-span-2"><label className={lbl}>Issued by</label><input className={inp} value={f.issued_by} onChange={set('issued_by')} /></div>
        <div><label className={lbl}>Valid from</label><input type="date" className={inp} value={f.valid_from} onChange={set('valid_from')} /></div>
        <div><label className={lbl}>Valid until</label><input type="date" className={inp} value={f.valid_until} onChange={set('valid_until')} /></div>
      </div>
    </Form>
  )
}

export function RiskForm({ rec, movementId, onClose, onDone }: { rec: Records; movementId: string; onClose: () => void; onDone: () => void }) {
  const [path, setPath] = useState<'full' | 'simplified'>('full')
  const [conclusion, setConclusion] = useState('')
  const [crit, setCrit] = useState<Record<string, string>>({})
  const [mit, setMit] = useState<Record<string, string>>({})
  const [mixing, setMixing] = useState('')
  const m = useSend(() => api.post(`/v1/eudr/movements/${movementId}/risk-assessment`, { path, conclusion,
    criteria: path === 'full' ? crit : {}, mitigation: Object.fromEntries(Object.entries(mit).filter(([, v]) => v.trim())),
    circumvention_mixing: mixing || null }), 'Sent for approval.', onDone)
  return (
    <Form title="Risk assessment" onClose={onClose} busy={m.isPending} onSubmit={() => m.mutate()} submit="Send for approval">
      <div className="grid grid-cols-2 gap-3">
        <div><label className={lbl}>Path *</label>
          <select className={inp} value={path} onChange={e => setPath(e.target.value as 'full' | 'simplified')}>
            <option value="full">full (Art. 10–11)</option><option value="simplified">simplified — all low-risk countries (Art. 13)</option>
          </select></div>
        <div><label className={lbl}>Conclusion *</label>
          <select className={inp} value={conclusion} onChange={e => setConclusion(e.target.value)}>
            <option value="">— state it —</option><option value="negligible">no or only a negligible risk</option><option value="not_negligible">not negligible</option>
          </select></div>
      </div>
      {path === 'full' ? <>
        <div className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)] pt-1">Art. 10(2) — every criterion, in your words</div>
        {Object.entries(rec.criteria).map(([k, t]) => (
          <div key={k}><label className="block text-[12px] text-[var(--color-mute)] mb-1">({k}) {t}</label>
            <textarea className={inp} rows={1} value={crit[k] ?? ''} onChange={e => setCrit({ ...crit, [k]: e.target.value })} /></div>
        ))}
        <div className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)] pt-1">Art. 11(1) — mitigation adopted (if any)</div>
        {Object.entries(rec.mitigation).map(([k, t]) => (
          <div key={k}><label className="block text-[12px] text-[var(--color-mute)] mb-1">({k}) {t}</label>
            <textarea className={inp} rows={1} value={mit[k] ?? ''} onChange={e => setMit({ ...mit, [k]: e.target.value })} /></div>
        ))}
      </> : (
        <div><label className={lbl}>Circumvention and mixing (Art. 13(1)) *</label><textarea className={inp} rows={3} value={mixing} onChange={e => setMixing(e.target.value)} /></div>
      )}
    </Form>
  )
}

export function ScopeForm({ movementId, why, onClose, onDone }: { movementId: string; why: string | null; onClose: () => void; onDone: () => void }) {
  const [inScope, setInScope] = useState('')
  const [basis, setBasis] = useState('')
  const m = useSend(() => api.put(`/v1/eudr/movements/${movementId}/scope`, { in_scope: inScope === 'yes', basis }), 'Scope stated.', onDone)
  return (
    <Form title="Is the product in Annex I?" onClose={onClose} busy={m.isPending} ready={!!inScope} onSubmit={() => m.mutate()} submit="State">
      <p className="text-[12px] text-[var(--color-mute)]">Annex I leaves this product's scope open: {why ?? '—'}. Your statement and its basis go into the record.</p>
      <div><label className={lbl}>In scope *</label>
        <select className={inp} value={inScope} onChange={e => setInScope(e.target.value)}><option value="">— state it —</option><option value="yes">yes</option><option value="no">no</option></select></div>
      <div><label className={lbl}>Why *</label><textarea className={inp} rows={3} value={basis} onChange={e => setBasis(e.target.value)} /></div>
    </Form>
  )
}

export function ReferenceForm({ filingId, onClose, onDone }: { filingId: string; onClose: () => void; onDone: () => void }) {
  const [ref, setRef] = useState('')
  const [ver, setVer] = useState('')
  const [source, setSource] = useState('manual_entry')
  const m = useSend(() => api.post(`/v1/eudr/filings/${filingId}/reference`, { reference_number: ref.trim(), verification_number: ver.trim() || null, source }),
    'Reference recorded — the 72-hour window is open.', onDone)
  return (
    <Form title="Reference number made available" onClose={onClose} busy={m.isPending} ready={!!ref.trim()} onSubmit={() => m.mutate()} submit="Record">
      <p className="text-[12px] text-[var(--color-mute)]">The reference and verification numbers the information system made available for this statement (Art. 4(2), 33).</p>
      <div className="grid grid-cols-2 gap-3">
        <div><label className={lbl}>Reference number *</label><input className={inp} value={ref} onChange={e => setRef(e.target.value)} /></div>
        <div><label className={lbl}>Verification number</label><input className={inp} value={ver} onChange={e => setVer(e.target.value)} /></div>
      </div>
      <div><label className={lbl}>How it was received</label>
        <select className={inp} value={source} onChange={e => setSource(e.target.value)}>
          <option value="manual_entry">entered in the information system by hand</option><option value="information_system">from the information system</option><option value="contingency">contingency procedure</option>
        </select></div>
    </Form>
  )
}

const EVENT_KINDS = ['grouped', 'check_notified', 'check_ended', 'placed_or_exported', 'given_to_customs', 'window_extended', 'rejected']

export function EventForm({ filingId, status, onClose, onDone }: { filingId: string; status: string; onClose: () => void; onDone: () => void }) {
  const kinds = EVENT_KINDS.filter(k => status === 'submitted' ? k === 'rejected' : k !== 'rejected')
  const [kind, setKind] = useState('')
  const [until, setUntil] = useState('')
  const [detail, setDetail] = useState('')
  const m = useSend(() => api.post(`/v1/eudr/filings/${filingId}/events`, { kind, detail: detail || null,
    until: kind === 'window_extended' && until ? new Date(until).toISOString() : null }), 'Recorded.', onDone)
  return (
    <Form title="What happened to the statement" onClose={onClose} busy={m.isPending} ready={!!kind} onSubmit={() => m.mutate()} submit="Record">
      <div><label className={lbl}>Event *</label>
        <select className={inp} value={kind} onChange={e => setKind(e.target.value)}>
          <option value="">— choose —</option>{kinds.map(k => <option key={k} value={k}>{EVENT_LABEL[k]}</option>)}
        </select></div>
      {kind === 'window_extended' && <div><label className={lbl}>Extended until * (no later than 8 days after the reference)</label>
        <input type="datetime-local" className={inp} value={until} onChange={e => setUntil(e.target.value)} /></div>}
      <div><label className={lbl}>Detail</label><textarea className={inp} rows={2} value={detail} onChange={e => setDetail(e.target.value)} /></div>
    </Form>
  )
}

export function WithdrawForm({ filingId, onClose, onDone }: { filingId: string; onClose: () => void; onDone: () => void }) {
  const [reason, setReason] = useState('')
  const m = useSend(() => api.post(`/v1/eudr/filings/${filingId}/withdraw`, { reason }), 'Statement withdrawn.', onDone)
  return (
    <Form title="Withdraw the statement" onClose={onClose} busy={m.isPending} ready={reason.trim().length >= 10} onSubmit={() => m.mutate()} submit="Withdraw">
      <p className="text-[12px] text-[var(--color-mute)]">Within 72 hours after the reference was made available, unless the window has closed (IR 2024/3084 Art. 5). Withdraw it in the information system too.</p>
      <div><label className={lbl}>Why * (at least 10 characters)</label><textarea className={inp} rows={3} value={reason} onChange={e => setReason(e.target.value)} /></div>
    </Form>
  )
}
