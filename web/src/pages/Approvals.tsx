import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Check, X, Clock, ShieldCheck } from 'lucide-react'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { Eyebrow, Card } from '../components/ui'

interface Req {
  id: string; request_type: string; title: string | null; payload: Record<string, unknown>
  status: string; maker_email: string | null; checker_email: string | null; reason: string | null
  created_at: string | null; decided_at: string | null; is_own: boolean
}

const TYPE_LABEL: Record<string, string> = {
  'supply.site.update': 'Edit site', 'supply.site.delete': 'Delete site',
  'supply.plot.update': 'Edit plot', 'supply.plot.delete': 'Delete plot',
  'submission.release': 'Release submission',
}
const badge = (s: string) => s === 'approved' ? 'text-[var(--color-good)] bg-[color-mix(in_oklab,var(--color-good)_14%,transparent)]'
  : s === 'rejected' ? 'text-[var(--color-bad)] bg-[color-mix(in_oklab,var(--color-bad)_14%,transparent)]'
  : 'text-[var(--color-warn)] bg-[color-mix(in_oklab,var(--color-warn)_14%,transparent)]'

function summarize(p: Record<string, unknown>): string {
  const changes = p.changes as Record<string, unknown> | undefined
  if (changes && Object.keys(changes).length) return Object.entries(changes).map(([k, v]) => `${k} → ${v}`).join(' · ')
  if (p.commodity) return `commodity → ${p.commodity}`
  return p.target_id ? `target ${String(p.target_id).slice(0, 8)}` : '—'
}

export default function Approvals() {
  const { profile } = useAuth()
  const canDecide = profile?.permissions?.includes('approvals.decide')
  const [filter, setFilter] = useState<'pending' | 'all'>('pending')
  const [busy, setBusy] = useState<string | null>(null)
  const q = useQuery({ queryKey: ['approvals', filter], queryFn: () => api.get<Req[]>(`/v1/approvals${filter === 'pending' ? '?status=pending' : ''}`) })

  const decide = async (id: string, decision: 'approved' | 'rejected') => {
    const reason = decision === 'rejected' ? (prompt('Reason for rejection (optional):') ?? undefined) : undefined
    setBusy(id)
    try { await api.post(`/v1/approvals/${id}/decide`, { decision, reason }); await q.refetch() }
    catch (e) { alert((e as { body?: { detail?: { message?: string } } })?.body?.detail?.message || 'Could not decide.') }
    finally { setBusy(null) }
  }

  const rows = q.data ?? []
  return (
    <div className="fadeup space-y-6">
      <div>
        <Eyebrow>Governance · maker-checker</Eyebrow>
        <h1 className="display text-3xl font-semibold mt-2 mb-1">Approvals</h1>
        <p className="text-[var(--color-mute)] text-sm max-w-2xl">
          Changes that need a second pair of eyes land here. A different person from the one who requested the change
          approves or rejects it (4-eyes) — nothing sensitive applies on one person's say-so.
        </p>
      </div>

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
            <Card key={r.id} className="p-4">
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                <span className="text-[14px] font-semibold">{TYPE_LABEL[r.request_type] ?? r.request_type}</span>
                <span className={`mono text-[9px] px-2 py-0.5 rounded-full uppercase tracking-wide ${badge(r.status)}`}>{r.status}</span>
                <span className="text-[12px] text-[var(--color-mute)]">{summarize(r.payload)}</span>
                {r.status === 'pending' && canDecide && (
                  <div className="ml-auto flex items-center gap-2">
                    {r.is_own
                      ? <span className="text-[11px] text-[var(--color-faint)] flex items-center gap-1"><Clock size={12} /> your request — needs another approver</span>
                      : <>
                          <button disabled={busy === r.id} onClick={() => decide(r.id, 'approved')}
                            className="inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[12.5px] font-medium bg-[var(--color-good)] text-[#08210f] hover:opacity-90 disabled:opacity-50"><Check size={14} /> Approve</button>
                          <button disabled={busy === r.id} onClick={() => decide(r.id, 'rejected')}
                            className="inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[12.5px] font-medium border border-[var(--color-line-2)] text-[var(--color-mute)] hover:border-[var(--color-bad)] hover:text-[var(--color-bad)] disabled:opacity-50"><X size={14} /> Reject</button>
                        </>}
                  </div>
                )}
              </div>
              <div className="text-[11px] text-[var(--color-faint)] mt-2 flex flex-wrap gap-x-4">
                <span>maker: {r.maker_email ?? '—'}</span>
                {r.checker_email && <span>checker: {r.checker_email}</span>}
                {r.created_at && <span>requested {new Date(r.created_at).toLocaleString()}</span>}
                {r.reason && <span>reason: {r.reason}</span>}
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
const Center = ({ children }: { children: React.ReactNode }) => <div className="h-[40vh] grid place-items-center text-[var(--color-faint)] text-sm">{children}</div>
