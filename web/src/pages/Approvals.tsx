import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Check, Clock, FileText, ShieldCheck, Undo2, X } from 'lucide-react'
import clsx from 'clsx'
import { api } from '../lib/api'
import { toast } from '../lib/toast'
import { useAuth } from '../lib/auth'
import { actionLabel } from '../lib/actionLabels'
import { Card, PageHeader } from '../components/ui'
import { Drawer } from '../components/Drawer'
import { CloseButton } from '../components/Dialog'
import { HEADING, MessageLine, type Message } from '../components/Details'
import { StatusChip } from '../components/StatusChip'
import { refused } from './admin/parts'

// The four-eyes queue, to the UI standard (2026-10-16). A change that needs a second person waits here; a different
// person from the one who asked approves, rejects or sends it back. The rules are unchanged: the person who asked
// cannot decide (the server refuses it too), rejecting or sending back needs a note, routing never decides. The server
// names every field of a request (services/governance/approval_view.py) and every refusal is a catalogue error.

interface Req {
  id: string; request_type: string; title_label: string | null; status: string; status_label: string
  maker_email: string | null; checker_email: string | null; reason: string | null
  assignee_email: string | null; assignee_user_id: string | null; assigned_to_me?: boolean
  created_at: string | null; decided_at: string | null; is_own: boolean
  policy_off: boolean; policy_off_message: Message | null; details: { label: string; value: string }[]
}
interface Decider { user_id: string; email: string; name: string | null }
type Tone = 'good' | 'warn' | 'bad' | 'neutral'
const TONE: Record<string, Tone> = { approved: 'good', rejected: 'bad', returned: 'neutral', withdrawn: 'neutral', pending: 'warn' }
const NOTE: Record<string, string> = { returned: 'Why it was sent back', rejected: 'Why it was rejected', withdrawn: 'Why it was withdrawn', approved: 'Approver’s note' }
const when = (iso: string | null) => iso ? new Date(iso).toLocaleString('en-GB', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—'
const ABOUT = [
  { heading: HEADING.shows, body: 'Changes that need a second person land here. A different person from the one who asked approves, rejects or sends them back — nothing sensitive applies on one person’s say-so.' },
  { heading: HEADING.read, body: 'Route a request to a named approver, or leave it for any approver. Rejecting or sending back needs a note saying why. Every decision is recorded in the audit trail.' },
]

export default function Approvals({ embedded = false }: { embedded?: boolean }) {
  const { profile } = useAuth()
  const canDecide = !!profile?.permissions?.includes('approvals.decide')
  const [filter, setFilter] = useState<'pending' | 'all'>('pending')
  const [busy, setBusy] = useState<string | null>(null)
  const [note, setNote] = useState<Record<string, string>>({})   // a request's decision note
  const [pick, setPick] = useState<Record<string, string>>({})   // a request's chosen approver, before Send
  const [open, setOpen] = useState<Req | null>(null)
  const q = useQuery({ queryKey: ['approvals', filter], queryFn: () => api.get<Req[]>(`/v1/approvals${filter === 'pending' ? '?status=pending' : ''}`) })
  const dq = useQuery({ queryKey: ['approval-deciders'], queryFn: () => api.get<Decider[]>('/v1/approvals/deciders') })

  const assign = async (id: string, userId: string | null) => {
    setBusy(id)
    try { await api.post(`/v1/approvals/${id}/assign`, { assignee_user_id: userId }); await q.refetch() }
    catch (e) { refused(e, 'The request could not be routed.') } finally { setBusy(null) }
  }
  const decide = async (id: string, decision: 'approved' | 'rejected' | 'returned') => {
    const reason = (note[id] ?? '').trim()
    if ((decision === 'rejected' || decision === 'returned') && !reason) {
      toast.error(decision === 'rejected' ? 'Add a note saying why before rejecting.' : 'Add a note saying what more is needed before sending it back.')
      return
    }
    setBusy(id)
    try { await api.post(`/v1/approvals/${id}/decide`, { decision, reason: reason || undefined }); setNote(n => ({ ...n, [id]: '' })); await q.refetch() }
    catch (e) { refused(e, 'The decision could not be recorded.') } finally { setBusy(null) }
  }

  const rows = q.data ?? []
  const waiting = rows.filter(r => r.status === 'pending')
  return (
    <div className={embedded ? 'space-y-5' : 'fadeup space-y-6'}>
      {!embedded && <PageHeader eyebrow="Governance · four eyes" title="Approvals" lead="Changes waiting for a second person." about={ABOUT} />}
      <div className="flex flex-wrap items-center gap-2">
        {(['pending', 'all'] as const).map(f => (
          <button key={f} onClick={() => setFilter(f)} aria-pressed={filter === f}
            className={clsx('px-3 py-1.5 rounded-lg text-[13px] border transition', filter === f ? 'border-[var(--color-sky)] text-[var(--color-sky)]' : 'border-[var(--color-line-2)] text-[var(--color-mute)] hover:text-[var(--color-ink)]')}>
            {f === 'pending' ? 'Waiting' : 'All'}
          </button>
        ))}
        {rows.length > 0 && <span className="ml-auto flex flex-wrap gap-1.5">
          <StatusChip tone="warn" label={`${waiting.length} waiting`} />
          {waiting.some(r => r.assigned_to_me) && <StatusChip tone="good" label={`${waiting.filter(r => r.assigned_to_me).length} for you`} />}
        </span>}
      </div>

      {q.isLoading ? <div className="py-16 text-center text-[var(--color-faint)] text-sm">Loading…</div> : rows.length === 0 ? (
        <Card className="p-10 text-center text-[var(--color-faint)] text-sm flex flex-col items-center gap-2"><ShieldCheck size={22} /> Nothing {filter === 'pending' ? 'waiting' : 'here'}.</Card>
      ) : (
        <div className="space-y-3">
          {rows.map(r => {
            const pending = r.status === 'pending'
            const canAct = canDecide && !r.is_own
            const current = r.assignee_user_id ?? ''
            const chosen = pick[r.id] ?? current
            return (
              <Card key={r.id} className="p-5">
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
                  <span className="text-[15px] font-semibold text-[var(--color-ink)]">{actionLabel(r.request_type)}</span>
                  <StatusChip tone={TONE[r.status] ?? 'neutral'} label={r.status_label} />
                  {r.policy_off_message && <MessageLine m={r.policy_off_message} className="text-[12px] text-[var(--color-warn)]" />}
                  {r.assigned_to_me && pending && <StatusChip tone="good" label="Yours to decide" />}
                  <button onClick={() => setOpen(r)} className="ml-auto inline-flex items-center gap-1.5 text-[12.5px] text-[var(--color-sky)] hover:underline"><FileText size={13} /> Request details</button>
                </div>
                {r.title_label && <div className="text-[13px] text-[var(--color-mute)] mt-1">{r.title_label}</div>}
                <Lifecycle r={r} />

                {pending && (r.is_own || canDecide) && (
                  <div className="mt-3 flex items-center gap-2 flex-wrap">
                    <span className="text-[12px] text-[var(--color-mute)]">{r.is_own ? 'Send to an approver' : 'Route to'}</span>
                    <select value={chosen} disabled={busy === r.id} aria-label="Approver" onChange={e => setPick(p => ({ ...p, [r.id]: e.target.value }))}
                      className="bg-[var(--color-bg-2)] border border-[var(--color-line)] rounded-lg px-2.5 py-1.5 text-[12.5px] outline-none focus:border-[var(--color-sky)] disabled:opacity-50">
                      <option value="">{r.is_own ? 'Choose an approver…' : 'Any approver'}</option>
                      {(dq.data ?? []).filter(d => d.email !== r.maker_email).map(d => <option key={d.user_id} value={d.user_id}>{d.name || d.email}</option>)}
                    </select>
                    <button disabled={chosen === current || busy === r.id}
                      onClick={() => assign(r.id, chosen || null).then(() => setPick(p => { const n = { ...p }; delete n[r.id]; return n }))}
                      className="inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[12px] font-medium bg-[var(--color-sky)] text-[var(--color-on-accent)] hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed">
                      {chosen ? 'Send' : 'Unassign'}
                    </button>
                  </div>
                )}

                {pending && (
                  <div className="mt-4 pt-4 border-t border-[var(--color-line)]">
                    <textarea value={note[r.id] ?? ''} onChange={e => setNote(n => ({ ...n, [r.id]: e.target.value }))} disabled={!canAct} aria-label="Note"
                      placeholder={canAct ? 'A note — needed to reject or send back, optional to approve' : 'Note'} rows={2}
                      className="w-full bg-[var(--color-bg-2)] border border-[var(--color-line)] rounded-lg px-3 py-2 text-[13px] outline-none focus:border-[var(--color-sky)] resize-y disabled:opacity-40 disabled:cursor-not-allowed" />
                    <div className="flex flex-wrap gap-2 mt-2">
                      <button disabled={!canAct || busy === r.id} onClick={() => decide(r.id, 'approved')}
                        className="inline-flex items-center gap-1.5 rounded-lg px-3.5 py-2 text-[12.5px] font-medium bg-[var(--color-good)] text-[var(--color-on-accent)] hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed"><Check size={14} /> Approve</button>
                      <button disabled={!canAct || busy === r.id} onClick={() => decide(r.id, 'returned')}
                        className="inline-flex items-center gap-1.5 rounded-lg px-3.5 py-2 text-[12.5px] font-medium border border-[var(--color-line-2)] text-[var(--color-sky)] hover:border-[var(--color-sky)] disabled:opacity-40 disabled:cursor-not-allowed"><Undo2 size={14} /> Send back</button>
                      <button disabled={!canAct || busy === r.id} onClick={() => decide(r.id, 'rejected')}
                        className="inline-flex items-center gap-1.5 rounded-lg px-3.5 py-2 text-[12.5px] font-medium border border-[var(--color-line-2)] text-[var(--color-mute)] hover:border-[var(--color-bad)] hover:text-[var(--color-bad)] disabled:opacity-40 disabled:cursor-not-allowed"><X size={14} /> Reject</button>
                    </div>
                    {!canAct && (
                      <div className="mt-2 text-[12px] text-[var(--color-faint)] flex items-start gap-1.5"><Clock size={12} className="mt-0.5 shrink-0" />
                        <span>{r.is_own ? (r.assignee_email ? `With ${r.assignee_email} to decide — you cannot approve your own request.` : 'Your request — send it to an approver; you cannot approve your own.') : 'Deciding approvals is not part of your roles.'}</span>
                      </div>
                    )}
                  </div>
                )}
              </Card>
            )
          })}
        </div>
      )}
      {open && <DetailsDrawer r={open} onClose={() => setOpen(null)} />}
    </div>
  )
}

// asked → routed → decided, as three steps (the routed step only when it was routed)
function Lifecycle({ r }: { r: Req }) {
  const steps = [
    { label: 'Asked', who: r.maker_email, at: r.created_at, done: true },
    ...(r.assignee_email ? [{ label: 'Routed', who: r.assignee_email, at: null, done: true }] : []),
    { label: r.status === 'pending' ? 'Decision' : r.status_label.charAt(0).toUpperCase() + r.status_label.slice(1), who: r.checker_email, at: r.decided_at, done: r.status !== 'pending' },
  ]
  return (
    <ol className="mt-3 flex flex-wrap items-start gap-x-2 gap-y-2 m-0 p-0 list-none">
      {steps.map((s, i) => (
        <li key={i} className="flex items-start gap-2">
          {i > 0 && <span className="mt-2 w-6 h-px bg-[var(--color-line-2)]" aria-hidden />}
          <span className="mt-1 w-2.5 h-2.5 rounded-full shrink-0" style={{ background: s.done ? 'var(--color-good)' : 'var(--color-line-2)' }} />
          <span className="text-[12px] leading-snug">
            <span className="text-[var(--color-ink)]">{s.label}</span>
            {s.who && <span className="block text-[var(--color-faint)]">{s.who}</span>}
            {s.at && <span className="block text-[var(--color-faint)]">{when(s.at)}</span>}
          </span>
        </li>
      ))}
    </ol>
  )
}

function DetailsDrawer({ r, onClose }: { r: Req; onClose: () => void }) {
  const note = r.reason              // the approver's own note, or the platform's withdrawal record — one click away
  return (
    <Drawer label="Request details" onClose={onClose} className="w-full max-w-lg h-full overflow-y-auto bg-[var(--color-bg-2)] border-l border-[var(--color-line)] p-6 space-y-4">
      <div className="flex items-center justify-between"><span className="text-[15px] font-semibold text-[var(--color-ink)]">{actionLabel(r.request_type)}</span><CloseButton onClick={onClose} /></div>
      {r.title_label && <p className="m-0 text-[13px] text-[var(--color-mute)]">{r.title_label}</p>}
      {r.details.length === 0 ? <p className="m-0 text-[13px] text-[var(--color-faint)]">The request holds nothing more than its title.</p> : (
        <dl className="m-0 grid grid-cols-[minmax(0,10rem)_minmax(0,1fr)] gap-x-4 gap-y-2.5 text-[13px]">
          {r.details.map((d, i) => (
            <div key={i} className="contents"><dt className="text-[var(--color-mute)]">{d.label}</dt><dd className="m-0 text-[var(--color-ink)] break-words">{d.value}</dd></div>
          ))}
        </dl>
      )}
      {note && (
        <section className="border-t border-[var(--color-line)] pt-3">
          <h4 className="text-[12px] font-semibold uppercase tracking-[0.08em] text-[var(--color-mute)] m-0 mb-1.5">{NOTE[r.status] ?? 'Note'}</h4>
          <p className="m-0 text-[13px] text-[var(--color-ink)] whitespace-pre-wrap">{note}</p>
        </section>
      )}
    </Drawer>
  )
}
