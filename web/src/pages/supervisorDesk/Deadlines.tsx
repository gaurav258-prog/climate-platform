import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api, apiMessage } from '../../lib/api'
import { toast } from '../../lib/toast'
import { useAuth } from '../../lib/auth'
import { Button, Card, StatGrid } from '../../components/ui'
import { StatusChip } from '../../components/StatusChip'
import { CloseButton, Dialog } from '../../components/Dialog'
import { Drawer } from '../../components/Drawer'
import { InfoButton, messageDetails, type Message } from '../../components/Details'
import { pressable } from '../../lib/pressable'
import { Facts, Failed, Loading, Meter, day, field } from './common'

// The authority's filing deadlines for a year (UI standard, 2026-10-16): figures, then one line per deadline with how many
// entities have filed; a deadline opens in a side drawer to set its date, publish it and see who is still outstanding.
// How the follow-up works is one click away, in the server's words.
interface Deadline { deadline_id: string; short: string; title: string | null; due_date: string; due_source: string; due_source_label: string | null
  registry_due: string | null; registry_rule: string | null; registry_message: Message | null; note: string | null; status: string; status_label: string | null
  published_at: string | null; published_by: string | null; n_applicable: number; n_cannot: number; n_filed: number; n_reminders: number; n_overdue: number
  outstanding: { org_id: string; name: string; reminded: boolean; overdue_notified: boolean }[] }
interface DlResp { period_label: string; deadlines: Deadline[]; note: Message }
interface Swept { n: number; raised: { entity: string; stage: string; stage_label: string | null; deadline: string; period: string }[] }

export function Deadlines() {
  const { profile } = useAuth()
  const qc = useQueryClient()
  const can = (profile?.permissions ?? []).includes('supervisor.deadlines.manage')
  const years = [1, 2, 3].map(i => `FY${new Date().getFullYear() - i + 1}`)
  const [period, setPeriod] = useState(years[1])
  const q = useQuery({ queryKey: ['sup-deadlines', period], queryFn: () => api.get<DlResp>(`/v1/supervisor/deadlines?period_label=${period}`) })
  const [busy, setBusy] = useState(false)
  const [sel, setSel] = useState<string | null>(null)
  const [swept, setSwept] = useState<Swept | null>(null)
  const d = q.data
  const refresh = () => Promise.all([qc.invalidateQueries({ queryKey: ['sup-deadlines', period] }), qc.invalidateQueries({ queryKey: ['sup-timeliness'] }),
    qc.invalidateQueries({ queryKey: ['supervisor-requests'] })])
  const run = async (fn: () => Promise<unknown>, ok?: string) => {
    setBusy(true)
    try { await fn(); if (ok) toast.success(ok); await refresh() } catch (e) { toast.error(apiMessage(e, 'Could not save.')) } finally { setBusy(false) }
  }
  const sweep = () => run(async () => { const r = await api.post<Swept>('/v1/supervisor/deadlines/sweep', {}); if (r.n) setSwept(r); else toast.success('Nothing new to send: every applicable entity has filed or was told.') })
  const x = d?.deadlines.find(y => y.deadline_id === sel)
  const out = d?.deadlines.reduce((a, y) => a + y.outstanding.length, 0) ?? 0
  return (<>
    <div className="flex flex-wrap items-center gap-3">
      <select aria-label="Financial year" value={period} onChange={e => setPeriod(e.target.value)} className={field}>{years.map(y => <option key={y} value={y}>{y}</option>)}</select>
      {d && <InfoButton label={d.note.label} details={messageDetails(d.note)} />}
      {can && <span className="ml-auto flex gap-2">
        <Button variant="ghost" disabled={busy} onClick={() => run(() => api.post(`/v1/supervisor/deadlines/generate?period_label=${period}`, {}), `Deadlines for ${period} drafted from the acts' rules.`)}>Draft from the acts</Button>
        <Button variant="ghost" disabled={busy} onClick={sweep}>Run the follow-up now</Button></span>}
    </div>
    {q.isLoading ? <Loading what="the deadlines" /> : !d ? <Failed what="the deadlines" /> : (<>
      <StatGrid cols={4} items={[
        { label: 'Deadlines', value: String(d.deadlines.length), sub: d.period_label },
        { label: 'Published', value: String(d.deadlines.filter(y => y.status === 'published').length), sub: 'on the entities’ calendars' },
        { label: 'Entities outstanding', value: String(out), sub: 'not yet filed', accent: out ? 'var(--color-warn)' : undefined },
        { label: 'Follow-ups sent', value: String(d.deadlines.reduce((a, y) => a + y.n_reminders + y.n_overdue, 0)), sub: 'reminders and overdue notices' },
      ]} />
      <Card className="p-5">
        {d.deadlines.length === 0 ? <div className="text-[12.5px] text-[var(--color-faint)]">No deadlines drafted for {d.period_label} yet.</div> : (
          <div className="divide-y divide-[var(--color-line)]">{d.deadlines.map(y => (
            <div key={y.deadline_id} {...pressable(() => setSel(y.deadline_id), { row: true })} className="py-3 flex items-center gap-4 flex-wrap cursor-pointer hover:bg-[var(--color-bg-2)] rounded-lg px-2 -mx-2">
              <div className="w-28 shrink-0"><div className="text-[14px] font-semibold tabular-nums text-[var(--color-ink)]">{day(y.due_date)}</div>
                <div className="text-[11px] text-[var(--color-faint)]">{y.due_source_label}</div></div>
              <div className="min-w-[12rem] mr-auto"><div className="text-[13px] text-[var(--color-ink)]">{y.short}</div>
                <div className="text-[11.5px] text-[var(--color-faint)]">{y.title}</div></div>
              <Meter value={y.n_filed} total={y.n_applicable} label={`${y.n_filed} of ${y.n_applicable} applicable entities filed`} late={y.n_overdue > 0} />
              <StatusChip value={y.status} label={y.status_label ?? undefined} />
            </div>))}</div>)}
      </Card>
      {x && <DeadlineDrawer x={x} can={can} busy={busy} run={run} onClose={() => setSel(null)} />}
      {swept && <Dialog title="Follow-up sent" onClose={() => setSwept(null)}>
        <div className="divide-y divide-[var(--color-line)]">{swept.raised.map((r, i) => (
          <div key={i} className="py-2 flex items-center gap-3 flex-wrap text-[12.5px]"><span className="text-[var(--color-ink)] mr-auto">{r.entity}</span>
            <span className="text-[var(--color-mute)]">{r.deadline} {r.period}</span><StatusChip label={r.stage_label ?? 'Follow-up'} tone={r.stage === 'overdue' ? 'bad' : 'warn'} /></div>))}</div>
      </Dialog>}
    </>)}
  </>)
}

function DeadlineDrawer({ x, can, busy, run, onClose }: { x: Deadline; can: boolean; busy: boolean; run: (fn: () => Promise<unknown>, ok?: string) => Promise<void>; onClose: () => void }) {
  const [due, setDue] = useState(x.due_date)
  const state = (o: Deadline['outstanding'][number]) => o.overdue_notified ? { label: 'Overdue notice sent', tone: 'bad' as const }
    : o.reminded ? { label: 'Reminded', tone: 'warn' as const } : x.status === 'published' ? { label: 'Not yet told', tone: 'neutral' as const } : { label: 'Not published', tone: 'neutral' as const }
  return (
    <Drawer label={x.short} onClose={onClose} className="w-full max-w-lg h-full overflow-y-auto bg-[var(--color-bg-2)] border-l border-[var(--color-line)] p-5">
      <div className="flex items-start justify-between gap-3 mb-4">
        <div className="min-w-0"><div className="text-[12px] text-[var(--color-mute)]">{x.title}</div>
          <div className="text-[16px] font-semibold text-[var(--color-ink)]">{x.short}</div></div>
        <CloseButton onClick={onClose} />
      </div>
      <div className="flex flex-wrap gap-2 mb-4"><StatusChip value={x.status} label={x.status_label ?? undefined} />
        {x.n_cannot > 0 && <StatusChip label={`${x.n_cannot} undetermined`} tone="warn" />}</div>
      <Facts rows={[
        ['Due date', <span>{day(x.due_date)} <span className="text-[var(--color-faint)]">· {x.due_source_label}</span></span>],
        ["The act's date", x.registry_due ? day(x.registry_due) : x.registry_message ? <span className="inline-flex items-center gap-1.5">{x.registry_message.label}<InfoButton compact details={messageDetails(x.registry_message)} /></span> : '—'],
        ["The act's rule", x.registry_rule ?? '—'],
        ['Published', x.published_at ? `${day(x.published_at)} · ${x.published_by ?? 'your authority'}` : 'Not yet'],
        ...(x.note ? [['Your note', x.note] as [string, string]] : []),
        ['Filed', <Meter value={x.n_filed} total={x.n_applicable} late={x.n_overdue > 0} />],
      ]} />
      {can && <div className="mt-4 space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <input type="date" aria-label="Due date" value={due} onChange={e => setDue(e.target.value)} className={field} />
          <Button variant="ghost" disabled={busy || due === x.due_date} onClick={() => run(() => api.put(`/v1/supervisor/deadlines/${x.deadline_id}`, { due_date: due }), 'Deadline set.')}>Set the date</Button>
          {x.due_source === 'set' && <Button variant="ghost" disabled={busy} onClick={() => run(() => api.put(`/v1/supervisor/deadlines/${x.deadline_id}`, { due_date: null }), "Back to the act's date.")}>Back to the act’s date</Button>}
        </div>
        {x.status !== 'published' && <Button disabled={busy} onClick={() => run(() => api.post(`/v1/supervisor/deadlines/${x.deadline_id}/publish`, {}), 'Published: on every applicable entity’s calendar, and the entities are told.')}>Publish</Button>}
      </div>}
      <div className="text-[12px] text-[var(--color-mute)] mt-6 mb-2">Outstanding · {x.outstanding.length}</div>
      {x.outstanding.length === 0 ? <div className="text-[12.5px] text-[var(--color-faint)]">{x.n_applicable ? 'Every applicable entity has filed.' : 'No entity is known to be in scope yet.'}</div> : (
        <div className="divide-y divide-[var(--color-line)]">{x.outstanding.map(o => { const s = state(o); return (
          <div key={o.org_id} className="py-2 flex items-center gap-3 text-[12.5px]">
            <Link to={`/supervised/${o.org_id}`} className="mr-auto text-[var(--color-ink)] hover:text-[var(--color-sky)] hover:underline">{o.name}</Link>
            <StatusChip label={s.label} tone={s.tone} /></div>) })}</div>)}
    </Drawer>
  )
}
