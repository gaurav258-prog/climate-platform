import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Check, X, Clock, ShieldCheck, Undo2 } from 'lucide-react'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { Eyebrow, Card } from '../components/ui'

interface Req {
  id: string; request_type: string; title: string | null; payload: Record<string, unknown>
  status: string; maker_email: string | null; checker_email: string | null; reason: string | null
  assignee_email: string | null; assignee_user_id: string | null; assigned_to_me?: boolean
  created_at: string | null; decided_at: string | null; is_own: boolean
}
interface Decider { user_id: string; email: string; name: string | null }

const TYPE_LABEL: Record<string, string> = {
  'supply.site.update': 'Edit site', 'supply.site.delete': 'Delete site',
  'supply.plot.update': 'Edit plot', 'supply.plot.delete': 'Delete plot',
  'submission.release': 'Release submission', 'report.publish': 'Publish report',
  'config.reporting_settings': 'Change reporting basis', 'supply.eudr.determine': 'Run EUDR determination',
}
const badge = (s: string) => s === 'approved' ? 'text-[var(--color-good)] bg-[color-mix(in_oklab,var(--color-good)_14%,transparent)]'
  : s === 'rejected' ? 'text-[var(--color-bad)] bg-[color-mix(in_oklab,var(--color-bad)_14%,transparent)]'
  : s === 'returned' ? 'text-[var(--color-sky)] bg-[color-mix(in_oklab,var(--color-sky)_14%,transparent)]'
  : 'text-[var(--color-warn)] bg-[color-mix(in_oklab,var(--color-warn)_14%,transparent)]'

function summarize(p: Record<string, unknown>): string {
  const changes = p.changes as Record<string, unknown> | undefined
  if (changes && Object.keys(changes).length) return Object.entries(changes).map(([k, v]) => `${k} → ${v}`).join(' · ')
  if (p.commodity) return `commodity → ${p.commodity}`
  return p.target_id ? `target ${String(p.target_id).slice(0, 8)}` : 'No structured payload on this request.'
}

// Flatten the request payload into readable key → value rows (one level of nesting expanded).
function payloadRows(p: Record<string, unknown>): [string, string][] {
  const out: [string, string][] = []
  for (const [k, v] of Object.entries(p || {})) {
    if (v && typeof v === 'object' && !Array.isArray(v)) {
      for (const [k2, v2] of Object.entries(v as Record<string, unknown>)) out.push([`${k}.${k2}`, String(v2)])
    } else out.push([k, Array.isArray(v) ? v.join(', ') : String(v)])
  }
  return out
}

export default function Approvals({ embedded = false }: { embedded?: boolean }) {
  const { profile } = useAuth()
  const canDecide = profile?.permissions?.includes('approvals.decide')
  const [filter, setFilter] = useState<'pending' | 'all'>('pending')
  const [busy, setBusy] = useState<string | null>(null)
  const [note, setNote] = useState<Record<string, string>>({})   // per-request comment for the decision
  const q = useQuery({ queryKey: ['approvals', filter], queryFn: () => api.get<Req[]>(`/v1/approvals${filter === 'pending' ? '?status=pending' : ''}`) })
  const dq = useQuery({ queryKey: ['approval-deciders'], queryFn: () => api.get<Decider[]>('/v1/approvals/deciders') })

  const assign = async (id: string, userId: string | null) => {
    setBusy(id)
    try { await api.post(`/v1/approvals/${id}/assign`, { assignee_user_id: userId }); await q.refetch() }
    catch (e) { alert((e as { body?: { detail?: { message?: string } } })?.body?.detail?.message || 'Could not assign.') }
    finally { setBusy(null) }
  }

  const decide = async (id: string, decision: 'approved' | 'rejected' | 'returned') => {
    const reason = (note[id] ?? '').trim()
    if ((decision === 'rejected' || decision === 'returned') && !reason) {
      alert(decision === 'rejected' ? 'Add a reason before rejecting.' : 'Add a note saying what more is needed before sending back.')
      return
    }
    setBusy(id)
    try {
      await api.post(`/v1/approvals/${id}/decide`, { decision, reason: reason || undefined })
      setNote(n => ({ ...n, [id]: '' })); await q.refetch()
    } catch (e) { alert((e as { body?: { detail?: { message?: string } } })?.body?.detail?.message || 'Could not record the decision.') }
    finally { setBusy(null) }
  }

  const rows = q.data ?? []
  return (
    <div className={embedded ? 'space-y-6' : 'fadeup space-y-6'}>
      {!embedded && (
      <div>
        <Eyebrow>Governance · maker-checker</Eyebrow>
        <h1 className="display text-3xl font-semibold mt-2 mb-1">Approvals</h1>
        <p className="text-[var(--color-mute)] text-sm max-w-2xl">
          Changes that need a second pair of eyes land here. A different person from the one who requested the change
          approves or rejects it (4-eyes) — nothing sensitive applies on one person's say-so.
        </p>
      </div>
      )}

      <div className="flex gap-2">
        {(['pending', 'all'] as const).map(f => (
          <button key={f} onClick={() => setFilter(f)}
            className={`px-3 py-1.5 rounded-lg text-[13px] border transition ${filter === f ? 'border-[var(--color-sky)] text-[var(--color-sky)]' : 'border-[var(--color-line-2)] text-[var(--color-mute)] hover:text-[var(--color-ink)]'}`}>
            {f === 'pending' ? 'Pending' : 'All'}
          </button>
        ))}
      </div>

      {q.isLoading ? <Center>loading…</Center> : rows.length === 0 ? (
        <Card className="p-10 text-center text-[var(--color-faint)] text-sm flex flex-col items-center gap-2"><ShieldCheck size={22} /> Nothing {filter === 'pending' ? 'pending' : 'here'}.</Card>
      ) : (
        <div className="space-y-3">
          {rows.map(r => (
            <Card key={r.id} className="p-5">
              {/* header */}
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                <span className="text-[15px] font-semibold">{TYPE_LABEL[r.request_type] ?? r.request_type}</span>
                <span className="mono text-[10px] text-[var(--color-faint)]">{r.request_type}</span>
                <span className={`mono text-[9px] px-2 py-0.5 rounded-full uppercase tracking-wide ${badge(r.status)}`}>{r.status}</span>
              </div>
              {r.title && <div className="text-[13px] text-[var(--color-mute)] mt-1">{r.title}</div>}

              {/* who / when */}
              <div className="text-[11.5px] text-[var(--color-faint)] mt-2 flex flex-wrap gap-x-4 gap-y-0.5">
                <span>maker: {r.maker_email ?? '—'}</span>
                {r.created_at && <span>requested {new Date(r.created_at).toLocaleString()}</span>}
                {r.assignee_email && <span className="text-[var(--color-sky)]">assigned to {r.assignee_email}</span>}
                {r.checker_email && <span>decided by {r.checker_email}{r.decided_at ? ` · ${new Date(r.decided_at).toLocaleString()}` : ''}</span>}
              </div>

              {/* the actual request — full payload */}
              <div className="mt-3 rounded-lg border border-[var(--color-line)] bg-[var(--color-bg-2)] p-3">
                <div className="mono text-[9.5px] tracking-[0.16em] uppercase text-[var(--color-faint)] mb-2">Request details</div>
                {payloadRows(r.payload).length === 0
                  ? <div className="text-[12.5px] text-[var(--color-mute)]">{summarize(r.payload)}</div>
                  : <div className="flex flex-col gap-1">
                      {payloadRows(r.payload).map(([k, v]) => (
                        <div key={k} className="flex gap-3 text-[12.5px]">
                          <div className="mono text-[11px] text-[var(--color-faint)] min-w-[130px] shrink-0">{k}</div>
                          <div className="text-[var(--color-ink)] break-words">{v}</div>
                        </div>
                      ))}
                    </div>}
              </div>

              {/* the decision note (reason for reject / send-back / approve comment) */}
              {r.reason && (
                <div className="mt-2 text-[12.5px] text-[var(--color-mute)]">
                  <span className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)]">{r.status === 'returned' ? 'sent back' : r.status === 'rejected' ? 'rejected' : 'note'}:</span> {r.reason}
                </div>
              )}

              {/* assign / route — the maker or any approver can hand a pending request to a named approver */}
              {r.status === 'pending' && (r.is_own || canDecide) && (
                <div className="mt-3 flex items-center gap-2 flex-wrap">
                  <span className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)]">Assign to</span>
                  <select value={r.assignee_user_id ?? ''} disabled={busy === r.id}
                    onChange={e => assign(r.id, e.target.value || null)}
                    className="bg-[var(--color-bg-2)] border border-[var(--color-line)] rounded-lg px-2.5 py-1.5 text-[12.5px] outline-none focus:border-[var(--color-sky)] disabled:opacity-50">
                    <option value="">Anyone (unassigned)</option>
                    {(dq.data ?? []).map(d => <option key={d.user_id} value={d.user_id}>{d.name || d.email}</option>)}
                  </select>
                  {r.assigned_to_me && <span className="mono text-[10.5px] text-[var(--color-sky)]">· yours to action</span>}
                </div>
              )}

              {/* actions */}
              {r.status === 'pending' && (
                r.is_own
                  ? <div className="mt-3 text-[12px] text-[var(--color-faint)] flex items-center gap-1.5"><Clock size={13} /> Your request — a different approver must action it (4-eyes).</div>
                  : canDecide
                    ? <div className="mt-4 pt-4 border-t border-[var(--color-line)]">
                        <textarea value={note[r.id] ?? ''} onChange={e => setNote(n => ({ ...n, [r.id]: e.target.value }))}
                          placeholder="Add a comment — required to reject or send back, optional to approve"
                          rows={2} className="w-full bg-[var(--color-bg-2)] border border-[var(--color-line)] rounded-lg px-3 py-2 text-[13px] outline-none focus:border-[var(--color-sky)] resize-y" />
                        <div className="flex flex-wrap gap-2 mt-2">
                          <button disabled={busy === r.id} onClick={() => decide(r.id, 'approved')}
                            className="inline-flex items-center gap-1.5 rounded-lg px-3.5 py-2 text-[12.5px] font-medium bg-[var(--color-good)] text-[#08210f] hover:opacity-90 disabled:opacity-50"><Check size={14} /> Approve</button>
                          <button disabled={busy === r.id} onClick={() => decide(r.id, 'returned')}
                            className="inline-flex items-center gap-1.5 rounded-lg px-3.5 py-2 text-[12.5px] font-medium border border-[var(--color-line-2)] text-[var(--color-sky)] hover:border-[var(--color-sky)] disabled:opacity-50"><Undo2 size={14} /> Send back</button>
                          <button disabled={busy === r.id} onClick={() => decide(r.id, 'rejected')}
                            className="inline-flex items-center gap-1.5 rounded-lg px-3.5 py-2 text-[12.5px] font-medium border border-[var(--color-line-2)] text-[var(--color-mute)] hover:border-[var(--color-bad)] hover:text-[var(--color-bad)] disabled:opacity-50"><X size={14} /> Reject</button>
                        </div>
                      </div>
                    : <div className="mt-3 text-[12px] text-[var(--color-faint)]">You don't have permission to decide approvals.</div>
              )}
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
const Center = ({ children }: { children: React.ReactNode }) => <div className="h-[40vh] grid place-items-center text-[var(--color-faint)] text-sm">{children}</div>
