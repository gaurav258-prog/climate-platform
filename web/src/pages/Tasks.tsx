import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Plus, ChevronRight, ChevronLeft, AlertTriangle } from 'lucide-react'
import { api, ApiError } from '../lib/api'
import { Eyebrow, Card, Button } from '../components/ui'

// Kanban board for the regulatory workflow — every task (import a file, investigate a failed validation,
// generate the XBRL, run the 4-eyes approval) as a card you move across columns and assign to a colleague.
// Cards created from validation exceptions carry their source so nothing is invented or duplicated.

interface Task {
  task_id: string; title: string; description: string | null; status: string; criticality: string
  assignee_user_id: string | null; assignee: string | null; assignee_email: string | null
  filing_id: string | null; source: string; source_ref: string | null; due_date: string | null
  depends_on: string[]; created_by: string | null
}
interface Column { key: string; tasks: Task[] }
interface Board { columns: Column[]; summary: { total: number; overdue: number; unassigned: number } }
interface Member { user_id: string; email: string; name: string }

const COL_LABEL: Record<string, string> = { icebox: 'Icebox', todo: 'To do', blocked: 'Blocked', doing: 'Doing', review: 'Review', done: 'Done' }
const NEXT: Record<string, string> = { icebox: 'todo', todo: 'doing', blocked: 'doing', doing: 'review', review: 'done' }
const PREV: Record<string, string> = { todo: 'icebox', blocked: 'todo', doing: 'todo', review: 'doing', done: 'review' }
const CRIT: Record<string, string> = { critical: '#fb7185', high: '#f0a860', normal: '#5cc8ff', low: '#64748b' }
const SRC_LABEL: Record<string, string> = { manual: 'manual', validation: 'validation', exception: 'exception', obligation: 'obligation', regulatory_change: 'reg change' }

export default function Tasks() {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['reg-tasks-board'], queryFn: () => api.get<Board>('/v1/reg-tasks/board') })
  const mq = useQuery({ queryKey: ['reg-task-members'], queryFn: () => api.get<Member[]>('/v1/reg-tasks/members') })
  const [title, setTitle] = useState('')
  const [crit, setCrit] = useState('normal')
  const [busy, setBusy] = useState(false)
  const members = mq.data ?? []
  const refresh = () => qc.invalidateQueries({ queryKey: ['reg-tasks-board'] })

  const add = async () => {
    if (!title.trim()) return
    setBusy(true)
    try { await api.post('/v1/reg-tasks', { title: title.trim(), criticality: crit }); setTitle(''); refresh() }
    catch (e) { alert(e instanceof ApiError ? e.message : 'Could not create the task.') }
    finally { setBusy(false) }
  }
  const move = async (t: Task, status: string) => {
    try { await api.post(`/v1/reg-tasks/${t.task_id}/move`, { status }); refresh() }
    catch (e) { alert(e instanceof ApiError ? e.message : 'Could not move the task.') }
  }
  const assign = async (t: Task, uid: string) => {
    try { await api.post(`/v1/reg-tasks/${t.task_id}/assign`, { assignee_user_id: uid || null }); refresh() }
    catch (e) { alert(e instanceof ApiError ? e.message : 'Could not assign the task.') }
  }

  const b = q.data
  return (
    <div className="fadeup space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <Eyebrow>Workflow</Eyebrow>
          <h1 className="display text-3xl font-semibold mt-2 mb-1">Tasks</h1>
          <p className="text-[var(--color-mute)] text-sm max-w-2xl">Everything the team needs to do to get a filing out — move a card across the board, or assign it to a colleague.</p>
        </div>
        {b && <div className="flex gap-4 text-right">
          <Stat n={b.summary.total} label="open" />
          <Stat n={b.summary.overdue} label="overdue" tone={b.summary.overdue > 0 ? '#fb7185' : undefined} />
          <Stat n={b.summary.unassigned} label="unassigned" tone={b.summary.unassigned > 0 ? '#f0a860' : undefined} />
        </div>}
      </div>

      {/* quick add */}
      <Card className="p-3 flex flex-wrap items-center gap-2">
        <Plus size={15} className="text-[var(--color-sky)]" />
        <input value={title} onChange={e => setTitle(e.target.value)} onKeyDown={e => e.key === 'Enter' && add()}
          placeholder="Add a task…" className="flex-1 min-w-[200px] bg-transparent outline-none text-[14px] text-[var(--color-ink)] placeholder:text-[var(--color-faint)]" />
        <select value={crit} onChange={e => setCrit(e.target.value)} className="bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-2 py-1.5 text-[12px] outline-none">
          {['low', 'normal', 'high', 'critical'].map(c => <option key={c} value={c}>{c}</option>)}
        </select>
        <Button variant="primary" onClick={add} disabled={busy || !title.trim()}>Add</Button>
      </Card>

      {q.isLoading ? <Card className="p-10 text-center text-[var(--color-faint)] text-sm">loading the board…</Card>
        : !b ? <div className="text-[12.5px] text-[var(--color-bad)]">Could not load the board.</div>
        : (
        <div className="overflow-x-auto pb-2">
          <div className="grid grid-cols-6 gap-3 min-w-[1050px]">
            {b.columns.map(c => (
              <div key={c.key} className="rounded-xl bg-[var(--color-panel)] border border-[var(--color-line)] p-2">
                <div className="flex items-center justify-between px-1.5 py-1.5">
                  <span className="mono text-[10.5px] uppercase tracking-wide text-[var(--color-mute)]">{COL_LABEL[c.key]}</span>
                  <span className="mono text-[10.5px] text-[var(--color-faint)]">{c.tasks.length}</span>
                </div>
                <div className="space-y-2">
                  {c.tasks.map(t => (
                    <TaskCard key={t.task_id} t={t} members={members} onMove={move} onAssign={assign} />
                  ))}
                  {c.tasks.length === 0 && <div className="text-[11px] text-[var(--color-faint)] px-1.5 py-3 text-center">—</div>}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function TaskCard({ t, members, onMove, onAssign }: { t: Task; members: Member[]; onMove: (t: Task, s: string) => void; onAssign: (t: Task, u: string) => void }) {
  const overdue = t.due_date && t.status !== 'done' && t.due_date < new Date().toISOString().slice(0, 10)
  return (
    <div className="rounded-lg bg-[var(--color-bg-2)] border border-[var(--color-line)] p-2.5">
      <div className="flex items-start gap-1.5">
        <span className="w-1.5 h-1.5 rounded-full mt-1.5 shrink-0" style={{ background: CRIT[t.criticality] }} title={t.criticality} />
        <div className="text-[12.5px] text-[var(--color-ink)] leading-snug flex-1">{t.title}</div>
      </div>
      <div className="flex items-center gap-1.5 mt-1.5 flex-wrap">
        {t.source !== 'manual' && <span className="mono text-[9px] px-1.5 py-0.5 rounded bg-[var(--color-panel-2)] text-[var(--color-faint)]">{SRC_LABEL[t.source]}</span>}
        {t.filing_id && <span className="mono text-[9px] text-[var(--color-sky)]">filing-linked</span>}
        {overdue && <span className="inline-flex items-center gap-0.5 text-[9.5px] text-[var(--color-bad)]"><AlertTriangle size={9} />overdue</span>}
        {t.due_date && !overdue && <span className="mono text-[9px] text-[var(--color-faint)]">due {t.due_date.slice(5)}</span>}
      </div>
      <div className="flex items-center justify-between gap-1 mt-2">
        <select value={t.assignee_user_id ?? ''} onChange={e => onAssign(t, e.target.value)}
          className="max-w-[110px] bg-transparent text-[10.5px] text-[var(--color-mute)] outline-none border-b border-transparent hover:border-[var(--color-line-2)]">
          <option value="">unassigned</option>
          {members.map(m => <option key={m.user_id} value={m.user_id}>{m.name || m.email.split('@')[0]}</option>)}
        </select>
        <div className="flex items-center gap-0.5">
          {PREV[t.status] && <button onClick={() => onMove(t, PREV[t.status])} title="move back" className="text-[var(--color-faint)] hover:text-[var(--color-ink)]"><ChevronLeft size={14} /></button>}
          {NEXT[t.status] && <button onClick={() => onMove(t, NEXT[t.status])} title="move forward" className="text-[var(--color-faint)] hover:text-[var(--color-sky)]"><ChevronRight size={14} /></button>}
        </div>
      </div>
    </div>
  )
}

function Stat({ n, label, tone }: { n: number; label: string; tone?: string }) {
  return <div><div className="display text-2xl leading-none" style={tone ? { color: tone } : undefined}>{n}</div><div className="mono text-[9.5px] uppercase tracking-wide text-[var(--color-faint)] mt-1">{label}</div></div>
}
