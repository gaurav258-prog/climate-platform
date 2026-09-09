import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'
import { toast } from '../lib/toast'
import { Button, Card, PageHeader, StatGrid } from '../components/ui'

// Requests & findings: the supervisor's engagement with an entity, tracked to closure on one thread both sides
// read. Kinds and status flows come from the supervision profile; the page never assumes a flow.
interface Req { request_id: string; supervised_org_id: string; entity: string; regulator: string; kind: string; kind_label: string; title: string; body: string | null
  status: string; status_label: string; severity: string | null; due_date: string | null; overdue: boolean; raised_at: string; updated_at: string; raised_by: string | null
  source: { type?: string; geography?: string; sector?: string; stage?: string; period_label?: string } | null; n_messages?: number; automatic?: boolean }
interface Msg { message_id: string; side: 'supervisor' | 'entity'; body: string | null; status_to: string | null; status_label: string | null; created_at: string; author: string | null }
interface Detail extends Req { messages: Msg[]; can_set: { key: string; label: string }[] }
interface ListResp { requests: Req[]; entities: { org_id: string; name: string }[]
  kinds: Record<string, { label: string; statuses: { key: string; label: string }[]; supervisor_sets: string[]; severities: string[] }>
  summary: { open: number; overdue: number; findings_open: number } }
const SEV: Record<string, string> = { low: 'var(--color-mute)', medium: 'var(--color-warn)', high: 'var(--color-bad)' }

export default function SupervisorRequests() {
  const [params, setParams] = useSearchParams()
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['supervisor-requests'], queryFn: () => api.get<ListResp>('/v1/supervisor/requests') })
  const [sel, setSel] = useState<string | null>(null)
  const [creating, setCreating] = useState(params.get('new') === '1')
  const fEntity = params.get('entity') ?? ''; const fKind = params.get('kind') ?? ''; const fStatus = params.get('status') ?? ''
  const setF = (k: string, v: string) => { const p = new URLSearchParams(params); if (v) p.set(k, v); else p.delete(k); p.delete('new'); setParams(p) }
  const d = q.data
  const rows = useMemo(() => (d?.requests ?? []).filter(r => (!fEntity || r.supervised_org_id === fEntity) && (!fKind || r.kind === fKind) && (!fStatus || (fStatus === 'open' ? r.status !== 'closed' : r.status === fStatus))), [d, fEntity, fKind, fStatus])
  const refresh = () => Promise.all([qc.invalidateQueries({ queryKey: ['supervisor-requests'] }), qc.invalidateQueries({ queryKey: ['supervisor-workflow'] })])
  useEffect(() => { if (params.get('new') === '1') setCreating(true) }, [params])
  return (
    <div className="fadeup space-y-6">
      <PageHeader eyebrow="Requests & findings" title="Engage and follow up"
        lead="Information requests, site-access requests and findings you raise with an entity. Each one is a thread both sides read: the entity responds and reports remediation in its own workspace, you close. Every step is recorded in both organisations' audit trails."
        actions={<Button onClick={() => setCreating(true)}>New request or finding</Button>} />
      {q.isLoading ? <div className="py-10 text-center text-[var(--color-faint)] text-sm">loading…</div> : !d ? <div className="text-[13px] text-[var(--color-bad)]">Could not load requests.</div> : (<>
        <StatGrid cols={3} items={[
          { label: 'Open', value: String(d.summary.open), sub: 'awaiting the entity or your closure', accent: d.summary.open ? 'var(--color-warn)' : undefined },
          { label: 'Overdue', value: String(d.summary.overdue), sub: 'past their due date', accent: d.summary.overdue ? 'var(--color-bad)' : undefined },
          { label: 'Findings open', value: String(d.summary.findings_open), sub: 'remediation not yet closed' },
        ]} />
        {creating && <NewRequest d={d} params={params} onDone={async (id) => { setCreating(false); setF('new', ''); await refresh(); if (id) setSel(id) }} onCancel={() => { setCreating(false); setF('new', '') }} />}
        <Card className="p-5">
          <div className="flex flex-wrap items-center gap-2 mb-3">
            <select value={fEntity} onChange={e => setF('entity', e.target.value)} className="bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-2.5 py-1.5 text-[12.5px] text-[var(--color-mute)] outline-none">
              <option value="">All entities</option>{d.entities.map(e => <option key={e.org_id} value={e.org_id}>{e.name}</option>)}</select>
            <select value={fKind} onChange={e => setF('kind', e.target.value)} className="bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-2.5 py-1.5 text-[12.5px] text-[var(--color-mute)] outline-none">
              <option value="">All kinds</option>{Object.entries(d.kinds).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}</select>
            <select value={fStatus} onChange={e => setF('status', e.target.value)} className="bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-2.5 py-1.5 text-[12.5px] text-[var(--color-mute)] outline-none">
              <option value="">Any status</option><option value="open">Not closed</option>
              {Array.from(new Map(Object.values(d.kinds).flatMap(k => k.statuses).map(s => [s.key, s])).values()).map(s => <option key={s.key} value={s.key}>{s.label}</option>)}</select>
            <span className="mono text-[10.5px] text-[var(--color-faint)] ml-auto">{rows.length} of {d.requests.length}</span>
          </div>
          <div className="overflow-x-auto">
            <table className="data-table w-full text-[12.5px]">
              <thead><tr className="text-[var(--color-faint)] mono text-[10px] uppercase tracking-wide text-left">
                <th className="">Entity</th><th className="">Kind</th><th className="">Title</th><th className="">Severity</th>
                <th className="">Status</th><th className="">Due</th><th className="num">Thread</th></tr></thead>
              <tbody>{rows.map(r => (
                <tr key={r.request_id} onClick={() => setSel(sel === r.request_id ? null : r.request_id)} className={`border-t border-[var(--color-line)] cursor-pointer hover:bg-[var(--color-bg-2)] ${sel === r.request_id ? 'bg-[var(--color-bg-2)]' : ''}`}>
                  <td className="text-[var(--color-ink)] whitespace-nowrap">{r.entity}</td>
                  <td className="text-[var(--color-mute)] whitespace-nowrap">{r.kind_label}</td>
                  <td className="text-[var(--color-ink)]">{r.title}{r.source?.type === 'lens_cell' && <span className="mono text-[10px] text-[var(--color-faint)] ml-2">lens · {r.source.geography} · {r.source.sector}</span>}{r.source?.type === 'deadline' && <span className="mono text-[10px] text-[var(--color-faint)] ml-2">automatic · {r.source.stage} · {r.source.period_label}</span>}{r.source?.type === 'mandate_attributes' && <span className="mono text-[10px] text-[var(--color-faint)] ml-2">attributes for the mandate criteria</span>}</td>
                  <td className="mono text-[11px]" style={{ color: SEV[r.severity ?? ''] ?? 'var(--color-faint)' }}>{r.severity ?? '—'}</td>
                  <td><span className={`mono text-[10px] uppercase px-1.5 py-0.5 rounded ${r.status === 'closed' ? 'bg-[var(--color-good)]/15 text-[var(--color-good)]' : 'bg-[var(--color-warn)]/15 text-[var(--color-warn)]'}`}>{r.status_label}</span></td>
                  <td className="mono text-[11px]" style={{ color: r.overdue ? 'var(--color-bad)' : 'var(--color-mute)' }}>{r.due_date ?? '—'}{r.overdue ? ' · overdue' : ''}</td>
                  <td className="num mono text-[var(--color-faint)]">{r.n_messages ?? '—'}</td>
                </tr>))}</tbody>
            </table>
            {rows.length === 0 && <div className="py-8 text-center text-[13px] text-[var(--color-faint)]">{d.requests.length ? 'Nothing matches these filters.' : 'Nothing raised yet. Start from a flagged cell on an entity\'s independent lens, or raise one here.'}</div>}
          </div>
        </Card>
        {sel && <Thread id={sel} onChange={refresh} onClose={() => setSel(null)} />}
      </>)}
    </div>
  )
}

function NewRequest({ d, params, onDone, onCancel }: { d: ListResp; params: URLSearchParams; onDone: (id: string | null) => void; onCancel: () => void }) {
  const [entity, setEntity] = useState(params.get('entity') ?? d.entities[0]?.org_id ?? '')
  const [kind, setKind] = useState(params.get('kind') ?? 'information_request')
  const [title, setTitle] = useState(params.get('title') ?? '')
  const [body, setBody] = useState(params.get('body') ?? '')
  const [severity, setSeverity] = useState('')
  const [due, setDue] = useState('')
  const [busy, setBusy] = useState(false)
  const k = d.kinds[kind]
  const source = params.get('geography') ? { type: 'lens_cell', geography: params.get('geography'), sector: params.get('sector') } : undefined
  const submit = async () => {
    if (!title.trim()) { toast.error('Give the request a title.'); return }
    if (k?.severities.length && !severity) { toast.error('Choose a severity for the finding.'); return }
    setBusy(true)
    try {
      const r = await api.post<Req>('/v1/supervisor/requests', { supervised_org_id: entity, kind, title, body: body || null, severity: severity || null, due_date: due || null, source })
      toast.success(`${r.kind_label} raised with ${r.entity}. The entity has a task and an e-mail.`); onDone(r.request_id)
    } catch (e) { toast.error((e as Error).message || 'Could not raise it.') } finally { setBusy(false) }
  }
  const inp = 'w-full bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-3 py-2 text-[13px] outline-none focus:border-[var(--color-sky)]'
  return (
    <Card className="p-5">
      <div className="mono text-[10.5px] uppercase tracking-wide text-[var(--color-faint)] mb-3">New request or finding{source ? ` · from lens cell ${source.geography} · ${source.sector}` : ''}</div>
      <div className="grid md:grid-cols-3 gap-3 mb-3">
        <label className="text-[12px] text-[var(--color-mute)]">Entity<select value={entity} onChange={e => setEntity(e.target.value)} className={inp + ' mt-1'}>{d.entities.map(e => <option key={e.org_id} value={e.org_id}>{e.name}</option>)}</select></label>
        <label className="text-[12px] text-[var(--color-mute)]">Kind<select value={kind} onChange={e => setKind(e.target.value)} className={inp + ' mt-1'}>{Object.entries(d.kinds).map(([kk, v]) => <option key={kk} value={kk}>{v.label}</option>)}</select></label>
        <label className="text-[12px] text-[var(--color-mute)]">Due date<input type="date" value={due} onChange={e => setDue(e.target.value)} className={inp + ' mt-1'} /></label>
      </div>
      <label className="block text-[12px] text-[var(--color-mute)] mb-3">Title<input value={title} onChange={e => setTitle(e.target.value)} className={inp + ' mt-1'} placeholder="What you need from the entity, in one line" /></label>
      <label className="block text-[12px] text-[var(--color-mute)] mb-3">Detail<textarea value={body} onChange={e => setBody(e.target.value)} rows={3} className={inp + ' mt-1'} placeholder="What you observed, what you expect, by when." /></label>
      {k?.severities.length ? <div className="flex items-center gap-2 mb-3 text-[12px] text-[var(--color-mute)]">Severity {k.severities.map(s => <button key={s} onClick={() => setSeverity(s)} className={`mono text-[11px] px-2 py-1 rounded border ${severity === s ? 'border-[var(--color-sky)] text-[var(--color-sky)]' : 'border-[var(--color-line)]'}`}>{s}</button>)}</div> : null}
      <div className="flex gap-2"><Button onClick={submit} disabled={busy}>{busy ? 'Raising…' : 'Raise with the entity'}</Button><Button variant="ghost" onClick={onCancel} disabled={busy}>Cancel</Button></div>
    </Card>
  )
}

function Thread({ id, onChange, onClose }: { id: string; onChange: () => Promise<unknown>; onClose: () => void }) {
  const q = useQuery({ queryKey: ['supervisor-request', id], queryFn: () => api.get<Detail>(`/v1/supervisor/requests/${id}`) })
  const [body, setBody] = useState(''); const [busy, setBusy] = useState(false)
  const qc = useQueryClient()
  const d = q.data
  if (!d) return null
  const send = async (status_to?: string) => {
    setBusy(true)
    try { await api.post(`/v1/supervisor/requests/${id}/messages`, { body: body || null, status_to: status_to ?? null }); setBody(''); await qc.invalidateQueries({ queryKey: ['supervisor-request', id] }); await onChange() }
    catch (e) { toast.error((e as Error).message || 'Could not update.') } finally { setBusy(false) }
  }
  return (
    <Card className="p-5">
      <div className="flex items-start justify-between gap-3 mb-2">
        <div>
          <div className="mono text-[10.5px] uppercase tracking-wide text-[var(--color-faint)]">{d.kind_label} · {d.entity} · raised {d.raised_at.slice(0, 10)} by {d.raised_by ?? '—'} · due {d.due_date ?? '—'}</div>
          <div className="display text-lg text-[var(--color-ink)]">{d.title}</div>
          {d.source?.type === 'lens_cell' && <Link to={`/supervised/${d.supervised_org_id}/lens`} className="text-[12px] text-[var(--color-sky)] hover:underline">Open the lens cell {d.source.geography} · {d.source.sector} →</Link>}
        </div>
        <button onClick={onClose} className="mono text-[11px] text-[var(--color-faint)] hover:text-[var(--color-ink)]">close</button>
      </div>
      <div className="space-y-2 mb-4">
        {d.messages.map(m => (
          <div key={m.message_id} className={`rounded-lg px-3 py-2 text-[12.5px] ${m.side === 'entity' ? 'bg-[var(--color-panel-2)] ml-8' : 'bg-[var(--color-bg-2)] mr-8'}`}>
            <div className="mono text-[10px] text-[var(--color-faint)] mb-0.5">{m.side === 'entity' ? d.entity : d.regulator} · {m.author ?? '—'} · {m.created_at.slice(0, 16).replace('T', ' ')}{m.status_to ? ` · set to ${m.status_label}` : ''}</div>
            {m.body && <div className="text-[var(--color-ink)] whitespace-pre-wrap">{m.body}</div>}
          </div>))}
      </div>
      <textarea value={body} onChange={e => setBody(e.target.value)} rows={2} placeholder="Add to the thread…" className="w-full bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-3 py-2 text-[13px] outline-none focus:border-[var(--color-sky)] mb-2" />
      <div className="flex flex-wrap gap-2 items-center">
        <Button variant="ghost" onClick={() => send()} disabled={busy || !body.trim()}>Send</Button>
        {d.can_set.map(s => <Button key={s.key} onClick={() => send(s.key)} disabled={busy}>{s.key === 'closed' ? 'Close' : s.key === 'open' ? 'Reopen' : `Set ${s.label}`}</Button>)}
        <span className="mono text-[10.5px] text-[var(--color-faint)] ml-auto">status: {d.status_label}{d.overdue ? ' · overdue' : ''}</span>
      </div>
    </Card>
  )
}
