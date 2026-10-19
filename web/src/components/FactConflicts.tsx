import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Scale, RefreshCw } from 'lucide-react'
import { api } from '../lib/api'
import { toast } from '../lib/toast'
import { useAuth } from '../lib/auth'
import { Card, SectionHead } from './ui'
import { HEADING, InfoButton, type Message } from './Details'
import { StatusChip } from './StatusChip'
import { Said, Segments, errMessage } from './intake/parts'

// Intake phase 3 — facts about an asset where your value and ours differ. Your value stays in use until a person
// decides (principle 1: the client wins on facts about their own assets). Using ours needs a second person. Each
// difference says why in the catalogue's words (services/intake/conflicts.py), its explanation one click away.

interface Conflict {
  conflict_id: string; asset_table: string; asset_id: string; asset_name: string | null; field: string; field_label: string
  client_value: unknown; tellumen_value: unknown; status: string; resolution: string | null
  note: string | null; created_at: string; resolved_at: string | null; msg: Message | null
}
interface Check { field: string; label: string; msg: Message }
interface Resp { conflicts: Conflict[]; counts: Record<string, number>; tellumen_checks: Check[] }

const RESOLVED: Record<string, string> = { client: 'Kept yours', tellumen: 'Uses ours', explained: 'Explained', agreed: 'Now agree' }
const show = (v: unknown) => v == null ? '—' : String(v)

export default function FactConflicts() {
  const { profile } = useAuth()
  const canAct = (profile?.permissions ?? []).includes('approvals.create')
  const qc = useQueryClient()
  const [status, setStatus] = useState<'open' | 'resolved'>('open')
  const [busy, setBusy] = useState<string | null>(null)
  const [explain, setExplain] = useState<{ id: string; note: string } | null>(null)
  const q = useQuery({ queryKey: ['fact-conflicts', status], queryFn: () => api.get<Resp>(`/v1/intake/conflicts?status=${status}`) })
  const d = q.data
  const nOpen = d?.counts.open ?? 0, nWaiting = d?.counts.awaiting_approval ?? 0, nDone = d?.counts.resolved ?? 0
  const refresh = () => qc.invalidateQueries({ queryKey: ['fact-conflicts'] })

  const decide = async (c: Conflict, decision: 'client' | 'tellumen' | 'explained', note?: string) => {
    setBusy(c.conflict_id)
    try {
      const r = await api.post<{ status: string }>(`/v1/intake/conflicts/${c.conflict_id}/resolve`, { decision, note })
      toast.success(r.status === 'awaiting_approval' ? 'Sent to a second person to approve using our value.' : decision === 'client' ? 'Kept your value.' : 'Explanation recorded.')
      setExplain(null); refresh()
    } catch (e) { toast.error(errMessage(e, 'Could not record the decision').label) } finally { setBusy(null) }
  }
  const check = async () => {
    setBusy('sync')
    try {
      const r = await api.post<{ opened: number; agreed: number }>('/v1/intake/facts/sync', {})
      toast.success(r.opened || r.agreed ? `Checked: ${r.opened} new difference(s), ${r.agreed} now agree.` : 'Checked — nothing new.')
      refresh()
    } catch (e) { toast.error(errMessage(e, 'Could not run the check').label) } finally { setBusy(null) }
  }

  const about = [
    { heading: HEADING.shows, body: 'Facts about your assets where your value and our own reading differ. Your values are what the engine uses; we keep ours beside yours where we can derive one independently.' },
    { heading: HEADING.read, body: 'Keep yours, explain the difference (for example an asset on a border), or use ours. Using ours changes your book only after a second person approves it. A decision stands: the same pair of values is not raised again.' },
    ...(d?.tellumen_checks ?? []).map(t => ({ heading: `How we read ${t.label.toLowerCase()}`, body: t.msg.detail?.what ?? t.msg.label })),
    { heading: HEADING.limits, body: 'The check runs every hour, and when you select Check now.' },
  ]

  return (
    <Card className="p-0 overflow-hidden">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-2 px-5 py-3 border-b border-[var(--color-line)]">
        <Scale size={15} className="text-[var(--color-sky)] shrink-0" />
        <SectionHead>Your value vs ours</SectionHead>
        <InfoButton compact details={{ title: 'Your value vs ours', sections: about }} />
        {d && <StatusChip tone={nOpen ? 'warn' : 'good'} label={nOpen ? `${nOpen} to decide` : 'Nothing to decide'} />}
        <div className="ml-auto flex items-center gap-1 text-[12px] whitespace-nowrap">
          {(['open', 'resolved'] as const).map(s => (
            <button key={s} onClick={() => setStatus(s)} aria-pressed={status === s}
              className={`px-2.5 py-1 rounded-md ${status === s ? 'bg-[var(--color-bg-2)] text-[var(--color-ink)]' : 'text-[var(--color-mute)] hover:text-[var(--color-ink)]'}`}>
              {s === 'open' ? 'To decide' : 'Decided'}</button>))}
          {canAct && <button onClick={check} disabled={busy === 'sync'}
            className="ml-1 inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-[var(--color-sky)] hover:bg-[var(--color-bg-2)] disabled:opacity-50">
            <RefreshCw size={12} className={busy === 'sync' ? 'animate-spin' : ''} /> Check now</button>}
        </div>
      </div>
      {d && (nOpen + nWaiting + nDone) > 0 && (
        <div className="px-5 pt-3">
          <Segments parts={[{ n: nOpen, tone: 'warn', label: 'to decide' }, { n: nWaiting, tone: 'neutral', label: 'awaiting a second person' },
            { n: nDone, tone: 'good', label: 'decided' }]} />
        </div>)}
      {q.isLoading ? <div className="px-5 py-4 text-[12.5px] text-[var(--color-faint)]">Loading…</div>
        : !d?.conflicts.length ? <div className="px-5 py-4 text-[12.5px] text-[var(--color-faint)]">{status === 'open' ? 'No differences to decide.' : 'Nothing decided yet.'}</div>
        : (
          <div className="overflow-x-auto mt-2">
            <table className="w-full text-[12.5px]">
              <thead><tr className="text-left text-[11.5px] text-[var(--color-faint)] border-b border-[var(--color-line)]">
                <th className="px-5 py-2 font-normal">Asset</th><th className="px-2 py-2 font-normal">Fact</th>
                <th className="px-2 py-2 font-normal">Yours</th><th className="px-2 py-2 font-normal">Ours</th>
                <th className="px-2 py-2 font-normal">Why</th><th className="px-5 py-2 font-normal text-right">{status === 'open' ? 'Decide' : 'Decision'}</th></tr></thead>
              <tbody>{d.conflicts.map(c => (
                <tr key={c.conflict_id} className="border-b border-[var(--color-line)] last:border-0 align-top">
                  <td className="px-5 py-2 text-[var(--color-ink)]">{c.asset_name ?? 'Unnamed asset'}</td>
                  <td className="px-2 py-2 text-[var(--color-mute)]">{c.field_label}</td>
                  <td className="px-2 py-2 tabular-nums">{show(c.client_value)}</td>
                  <td className="px-2 py-2 tabular-nums">{show(c.tellumen_value)}</td>
                  <td className="px-2 py-2 text-[var(--color-mute)] max-w-[280px]">{c.msg ? <Said m={c.msg} /> : '—'}</td>
                  <td className="px-5 py-2 text-right whitespace-nowrap">
                    {status === 'resolved' ? <span className="inline-flex items-center gap-1 text-[var(--color-mute)]">{RESOLVED[c.resolution ?? ''] ?? 'Decided'}
                        {/* a pop-up takes its parent's text styles (the dialog is not portaled): left-aligned, wrapping */}
                        {c.note && <span className="whitespace-normal text-left"><InfoButton compact details={{ title: 'The explanation recorded', sections: [{ heading: HEADING.shows, body: c.note }] }} /></span>}</span>
                      : c.status === 'awaiting_approval' ? <StatusChip tone="warn" label="Awaiting a second person" />
                      : !canAct ? <span className="text-[var(--color-faint)]">—</span>
                      : explain?.id === c.conflict_id ? (
                        <span className="inline-flex items-center gap-1">
                          <input autoFocus value={explain.note} onChange={e => setExplain({ id: c.conflict_id, note: e.target.value })} placeholder="What explains it?"
                            aria-label="Explanation" className="w-44 rounded border border-[var(--color-line)] bg-[var(--color-panel)] px-2 py-1 text-[12px]" />
                          <button disabled={!explain.note.trim() || busy === c.conflict_id} onClick={() => decide(c, 'explained', explain.note)} className="px-2 py-1 rounded-md bg-[var(--color-sky)] text-[var(--color-on-accent)] disabled:opacity-50">Save</button>
                          <button onClick={() => setExplain(null)} className="px-2 py-1 text-[var(--color-mute)]">Cancel</button>
                        </span>)
                      : (
                        <span className="inline-flex items-center gap-1">
                          <button disabled={busy === c.conflict_id} onClick={() => decide(c, 'client')} className="px-2 py-1 rounded-md border border-[var(--color-line-2)] hover:border-[var(--color-sky)] disabled:opacity-50">Keep yours</button>
                          <button disabled={busy === c.conflict_id} onClick={() => decide(c, 'tellumen')} className="px-2 py-1 rounded-md border border-[var(--color-line-2)] hover:border-[var(--color-sky)] disabled:opacity-50">Use ours</button>
                          <button disabled={busy === c.conflict_id} onClick={() => setExplain({ id: c.conflict_id, note: '' })} className="px-2 py-1 text-[var(--color-mute)] hover:text-[var(--color-ink)]">Explain</button>
                        </span>)}
                  </td>
                </tr>))}</tbody>
            </table>
          </div>)}
    </Card>
  )
}
