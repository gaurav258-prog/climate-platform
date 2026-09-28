import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Scale, RefreshCw } from 'lucide-react'
import { api, ApiError } from '../lib/api'
import { toast } from '../lib/toast'
import { useAuth } from '../lib/auth'
import { Card, SectionHead } from './ui'

// Intake phase 3 — facts about an asset where your value and ours differ. Your value stays in use until a person
// decides (principle 1: the client wins on facts about their own assets). Using ours needs a second person.

interface Conflict {
  conflict_id: string; asset_table: string; asset_id: string; asset_name: string | null; field: string
  client_value: unknown; tellumen_value: unknown; rule: string; status: string; resolution: string | null
  note: string | null; created_at: string; resolved_at: string | null; why_ours: string | null
}
interface Resp { conflicts: Conflict[]; counts: Record<string, number>; tellumen_checks: { field: string; method: string; source: string }[] }

const FIELD: Record<string, string> = { country: 'Country' }
const RESOLVED: Record<string, string> = { client: 'kept yours', tellumen: 'uses ours', explained: 'explained', agreed: 'now agree' }
const show = (v: unknown) => v == null ? '—' : String(v)
function msg(e: unknown, f: string) { return e instanceof ApiError ? (e.body as { error?: { message?: string } })?.error?.message ?? f : f }

export default function FactConflicts() {
  const { profile } = useAuth()
  const canAct = (profile?.permissions ?? []).includes('approvals.create')
  const qc = useQueryClient()
  const [status, setStatus] = useState<'open' | 'resolved'>('open')
  const [busy, setBusy] = useState<string | null>(null)
  const [explain, setExplain] = useState<{ id: string; note: string } | null>(null)
  const q = useQuery({ queryKey: ['fact-conflicts', status], queryFn: () => api.get<Resp>(`/v1/intake/conflicts?status=${status}`) })
  const d = q.data
  const nOpen = (d?.counts.open ?? 0) + (d?.counts.awaiting_approval ?? 0)
  const refresh = () => qc.invalidateQueries({ queryKey: ['fact-conflicts'] })

  const decide = async (c: Conflict, decision: 'client' | 'tellumen' | 'explained', note?: string) => {
    setBusy(c.conflict_id)
    try {
      const r = await api.post<{ status: string }>(`/v1/intake/conflicts/${c.conflict_id}/resolve`, { decision, note })
      toast.success(r.status === 'awaiting_approval' ? 'Sent to a second person to approve using our value.' : decision === 'client' ? 'Kept your value.' : 'Explanation recorded.')
      setExplain(null); refresh()
    } catch (e) { toast.error(msg(e, 'Could not record the decision.')) } finally { setBusy(null) }
  }
  const check = async () => {
    setBusy('sync')
    try {
      const r = await api.post<{ opened: number; agreed: number }>('/v1/intake/facts/sync', {})
      toast.success(r.opened || r.agreed ? `Checked: ${r.opened} new difference(s), ${r.agreed} now agree.` : 'Checked — nothing new.')
      refresh()
    } catch (e) { toast.error(msg(e, 'Could not run the check.')) } finally { setBusy(null) }
  }

  return (
    <Card className="p-0 overflow-hidden">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-2 px-5 py-3 border-b border-[var(--color-line)]">
        <Scale size={15} className="text-[var(--color-sky)] shrink-0" />
        <SectionHead hint={nOpen ? `${nOpen} to look at` : 'nothing to look at'}>Your value vs ours</SectionHead>
        <div className="ml-auto flex items-center gap-1 text-[11.5px] whitespace-nowrap">
          {(['open', 'resolved'] as const).map(s => (
            <button key={s} onClick={() => setStatus(s)} aria-pressed={status === s}
              className={`px-2.5 py-1 rounded-md ${status === s ? 'bg-[var(--color-bg-2)] text-[var(--color-ink)]' : 'text-[var(--color-mute)] hover:text-[var(--color-ink)]'}`}>
              {s === 'open' ? 'To decide' : 'Decided'}</button>))}
          {canAct && <button onClick={check} disabled={busy === 'sync'} title="Record your book as it stands and run our checks now (they also run every hour)"
            className="ml-1 inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-[var(--color-sky)] hover:bg-[var(--color-bg-2)] disabled:opacity-50">
            <RefreshCw size={12} className={busy === 'sync' ? 'animate-spin' : ''} /> Check now</button>}
        </div>
      </div>
      <p className="px-5 pt-3 text-[12px] text-[var(--color-mute)] leading-relaxed">
        Your values are what the engine uses. We keep our own value beside yours where we can derive one independently
        {d?.tellumen_checks?.length ? <> — today: {d.tellumen_checks.map(t => `${(FIELD[t.field] ?? t.field).toLowerCase()} from the coordinates (${t.source})`).join('; ')}</> : ''}.
        A difference waits here until someone decides. Using our value needs a second person.
      </p>
      {q.isLoading ? <div className="px-5 py-4 text-[12.5px] text-[var(--color-faint)]">loading…</div>
        : !d?.conflicts.length ? <div className="px-5 py-4 text-[12.5px] text-[var(--color-faint)]">{status === 'open' ? 'No differences to decide.' : 'Nothing decided yet.'}</div>
        : (
          <div className="overflow-x-auto mt-2">
            <table className="w-full text-[12.5px]">
              <thead><tr className="text-left mono text-[9.5px] uppercase tracking-wide text-[var(--color-faint)] border-b border-[var(--color-line)]">
                <th className="px-5 py-2 font-normal">Asset</th><th className="px-2 py-2 font-normal">Fact</th>
                <th className="px-2 py-2 font-normal">Yours</th><th className="px-2 py-2 font-normal">Ours</th>
                <th className="px-2 py-2 font-normal">Why</th><th className="px-5 py-2 font-normal text-right">{status === 'open' ? 'Decide' : 'Decision'}</th></tr></thead>
              <tbody>{d.conflicts.map(c => (
                <tr key={c.conflict_id} className="border-b border-[var(--color-line)] last:border-0 align-top">
                  <td className="px-5 py-2 text-[var(--color-ink)]">{c.asset_name ?? c.asset_id.slice(0, 8)}</td>
                  <td className="px-2 py-2 text-[var(--color-mute)]">{FIELD[c.field] ?? c.field}</td>
                  <td className="px-2 py-2 mono">{show(c.client_value)}</td>
                  <td className="px-2 py-2 mono" title={c.why_ours ?? undefined}>{show(c.tellumen_value)}</td>
                  <td className="px-2 py-2 text-[var(--color-mute)] max-w-[260px]">{c.rule}{c.note && <div className="text-[var(--color-faint)] mt-0.5">“{c.note}”</div>}</td>
                  <td className="px-5 py-2 text-right whitespace-nowrap">
                    {status === 'resolved' ? <span className="text-[var(--color-mute)]">{RESOLVED[c.resolution ?? ''] ?? c.resolution}</span>
                      : c.status === 'awaiting_approval' ? <span className="text-[var(--color-warn)]">awaiting second person</span>
                      : !canAct ? <span className="text-[var(--color-faint)]">—</span>
                      : explain?.id === c.conflict_id ? (
                        <span className="inline-flex items-center gap-1">
                          <input autoFocus value={explain.note} onChange={e => setExplain({ id: c.conflict_id, note: e.target.value })} placeholder="What explains it?"
                            aria-label="Explanation" className="w-44 rounded border border-[var(--color-line)] bg-[var(--color-panel)] px-2 py-1 text-[12px]" />
                          <button disabled={!explain.note.trim() || busy === c.conflict_id} onClick={() => decide(c, 'explained', explain.note)} className="px-2 py-1 rounded-md bg-[var(--color-sky)] text-white disabled:opacity-50">Save</button>
                          <button onClick={() => setExplain(null)} className="px-2 py-1 text-[var(--color-mute)]">Cancel</button>
                        </span>)
                      : (
                        <span className="inline-flex items-center gap-1">
                          <button disabled={busy === c.conflict_id} onClick={() => decide(c, 'client')} className="px-2 py-1 rounded-md border border-[var(--color-line-2)] hover:border-[var(--color-sky)] disabled:opacity-50">Keep yours</button>
                          <button disabled={busy === c.conflict_id} onClick={() => decide(c, 'tellumen')} className="px-2 py-1 rounded-md border border-[var(--color-line-2)] hover:border-[var(--color-sky)] disabled:opacity-50" title="A second person approves before your book changes">Use ours</button>
                          <button disabled={busy === c.conflict_id} onClick={() => setExplain({ id: c.conflict_id, note: '' })} className="px-2 py-1 text-[var(--color-mute)] hover:text-[var(--color-ink)]">Explain</button>
                        </span>)}
                  </td>
                </tr>))}</tbody>
            </table>
          </div>)}
    </Card>
  )
}
