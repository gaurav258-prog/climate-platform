import { useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { AlertTriangle, AtSign, Bell, ChevronLeft, ChevronRight, GripVertical, ListChecks, Plus, ShieldCheck } from 'lucide-react'
import clsx from 'clsx'
import { api } from '../lib/api'
import { toast } from '../lib/toast'
import { Button, Card, HeroBanner, PageHeader } from '../components/ui'
import { CloseButton } from '../components/Dialog'
import { Drawer } from '../components/Drawer'
import { HEADING } from '../components/Details'
import { TaskDrawer } from './tasks/TaskDrawer'
import { CompletionModal, GateModal } from './tasks/Gates'
import { COL_COLOR, COL_LABEL, CRIT, CRIT_COLOR, CRIT_LABEL, NEXT, PREV, SRC_LABEL, errText, gateItemsFor, idx, isGatedForward, stamp,
  type Board, type Member, type Mention, type Task } from './tasks/model'

// The task board, to the UI standard (2026-10-16): every task the team needs to get a filing out, as cards moved across
// the columns and assigned to a colleague. A forward move into Doing or Review passes its stage gate; Done needs a
// second person (a completion request approved on Approvals). Refusals and activity arrive in catalogue words.

const ABOUT = [
  { heading: HEADING.shows, body: 'Every task the team needs to get a filing out — where it sits on the board, what is slipping, and what has no owner yet.' },
  { heading: HEADING.read, body: 'Drag a card or use its arrows. Entering Doing needs an owner and no open dependencies; entering Review needs the work recorded and, for a filing’s task, its checks passed. A task reaches Done only when a different colleague approves its completion on Approvals.' },
]

export default function Tasks() {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['reg-tasks-board'], queryFn: () => api.get<Board>('/v1/reg-tasks/board') })
  const mq = useQuery({ queryKey: ['reg-task-members'], queryFn: () => api.get<Member[]>('/v1/reg-tasks/members') })
  const [title, setTitle] = useState('')
  const [crit, setCrit] = useState('normal')
  const [busy, setBusy] = useState(false)
  const [params, setParams] = useSearchParams()
  const [openId, setOpenId] = useState<string | null>(null)
  const [drag, setDrag] = useState<Task | null>(null)
  const [overCol, setOverCol] = useState<string | null>(null)
  const [gate, setGate] = useState<{ task: Task; target: string } | null>(null)
  const [completing, setCompleting] = useState<Task | null>(null)
  useEffect(() => { const t = params.get('task'); if (t) setOpenId(t) }, [params])
  const members = mq.data ?? []
  const refresh = () => qc.invalidateQueries({ queryKey: ['reg-tasks-board'] })
  const closeDrawer = () => { setOpenId(null); if (params.get('task')) { params.delete('task'); setParams(params, { replace: true }) } }

  const add = async () => {
    if (!title.trim()) return
    setBusy(true)
    try { await api.post('/v1/reg-tasks', { title: title.trim(), criticality: crit }); setTitle(''); refresh() }
    catch (e) { toast.error(errText(e, 'The task could not be created.')) } finally { setBusy(false) }
  }
  const move = async (t: Task, status: string, attestations?: string[]) => {
    try { await api.post(`/v1/reg-tasks/${t.task_id}/move`, { status, attestations }); refresh() }
    catch (e) { toast.error(errText(e, 'The task could not be moved.')) }
  }
  const requestCompletion = async (t: Task, note: string) => {
    try { await api.post(`/v1/reg-tasks/${t.task_id}/request-completion`, { note }); toast.success('Completion asked for — a different colleague approves it on Approvals.'); refresh() }
    catch (e) { toast.error(errText(e, 'Completion could not be asked for.')) }
  }
  // a forward move into a gated stage waits for its checklist; Done is never a plain move — it asks a second person
  const attemptMove = (t: Task, target: string) => {
    if (target === t.status) return
    if (target === 'done') {
      if (t.status !== 'review') { toast.error('Move this task to Review first.'); return }
      if (t.pending_completion_request_id) { toast.error('Already waiting for a colleague’s approval — see Approvals.'); return }
      setCompleting(t); return
    }
    if (isGatedForward(t, target)) { setGate({ task: t, target }); return }
    move(t, target)
  }
  const assign = async (t: Task, uid: string) => {
    try { await api.post(`/v1/reg-tasks/${t.task_id}/assign`, { assignee_user_id: uid || null }); refresh() }
    catch (e) { toast.error(errText(e, 'The task could not be assigned.')) }
  }

  const b = q.data
  const total = b ? b.columns.reduce((n, c) => n + c.tasks.length, 0) : 0
  return (
    <div className="fadeup space-y-5">
      <PageHeader eyebrow="Workflow" title="Tasks" lead="Everything the team needs to get a filing out." about={ABOUT} actions={<MentionsBell onOpen={setOpenId} />} />

      {b && (<>
        <HeroBanner eyebrow="Workflow"
          title={b.summary.overdue > 0 ? `${b.summary.overdue} tasks overdue.` : b.summary.unassigned > 0 ? 'Some tasks still need an owner.' : 'The board is under control.'}
          stat={[
            { label: 'Open', value: b.summary.total, icon: ListChecks, tone: 'var(--color-sky)' },
            { label: 'Overdue', value: b.summary.overdue, icon: AlertTriangle, tone: b.summary.overdue > 0 ? 'var(--color-bad)' : 'var(--color-good)', pulse: b.summary.overdue > 0 },
            { label: 'No owner', value: b.summary.unassigned, icon: AtSign, tone: b.summary.unassigned > 0 ? 'var(--color-warn)' : 'var(--color-good)' },
          ]} />
        {total > 0 && (
          <div>
            <div className="flex h-2.5 rounded-full overflow-hidden bg-[var(--color-panel-2)]" role="img" aria-label={b.columns.map(c => `${COL_LABEL[c.key]} ${c.tasks.length}`).join(', ')}>
              {b.columns.filter(c => c.tasks.length).map(c => <span key={c.key} style={{ width: `${(100 * c.tasks.length) / total}%`, background: COL_COLOR[c.key], opacity: 0.85 }} />)}
            </div>
            <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2 text-[12px]">
              {b.columns.map(c => <span key={c.key} className="inline-flex items-center gap-1.5 text-[var(--color-mute)]"><span className="w-2 h-2 rounded-full" style={{ background: COL_COLOR[c.key] }} />{COL_LABEL[c.key]} <b className="text-[var(--color-ink)] tabular-nums">{c.tasks.length}</b></span>)}
            </div>
          </div>
        )}
      </>)}

      <Card className="p-3 flex flex-wrap items-center gap-2">
        <Plus size={15} className="text-[var(--color-sky)]" />
        <input value={title} onChange={e => setTitle(e.target.value)} onKeyDown={e => e.key === 'Enter' && add()} aria-label="New task"
          placeholder="Add a task…" className="flex-1 min-w-[200px] bg-transparent outline-none text-[14px] text-[var(--color-ink)] placeholder:text-[var(--color-faint)]" />
        <select value={crit} onChange={e => setCrit(e.target.value)} aria-label="Criticality" className="bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-2 py-1.5 text-[12px] outline-none">
          {CRIT.map(c => <option key={c} value={c}>{CRIT_LABEL[c]}</option>)}
        </select>
        <Button variant="primary" onClick={add} disabled={busy || !title.trim()}>Add</Button>
      </Card>

      {q.isLoading ? <Card className="p-10 text-center text-[var(--color-faint)] text-sm">Loading the board…</Card>
        : !b ? <div className="text-[12.5px] text-[var(--color-bad)]">The board could not be loaded. Try again shortly.</div>
        : (
          <div className="overflow-x-auto pb-2">
            <div className="grid grid-cols-6 gap-3 min-w-[1050px]">
              {b.columns.map(c => {
                const isTarget = overCol === c.key && !!drag && drag.status !== c.key
                const gated = !!drag && idx(c.key) > idx(drag.status) && (c.key === 'done' || gateItemsFor(c.key, drag).length > 0)
                return (
                  <div key={c.key}
                    onDragOver={e => { if (drag) { e.preventDefault(); setOverCol(c.key) } }}
                    onDragLeave={() => setOverCol(o => o === c.key ? null : o)}
                    onDrop={e => { e.preventDefault(); if (drag) attemptMove(drag, c.key); setDrag(null); setOverCol(null) }}
                    className={clsx('rounded-xl border p-2 transition', isTarget ? 'border-[var(--color-sky)] bg-[color-mix(in_oklab,var(--color-sky)_8%,var(--color-panel))]' : 'border-[var(--color-line)] bg-[var(--color-panel)]')}>
                    <div className="flex items-center justify-between px-1.5 py-1.5">
                      <span className="inline-flex items-center gap-1.5 text-[12px] font-medium text-[var(--color-mute)]"><span className="w-2 h-2 rounded-full" style={{ background: COL_COLOR[c.key] }} />{COL_LABEL[c.key]}</span>
                      <span className="text-[11.5px] text-[var(--color-faint)] tabular-nums">{isTarget && gated ? <span className="text-[var(--color-sky)] inline-flex items-center gap-0.5"><ShieldCheck size={11} />Checks</span> : c.tasks.length}</span>
                    </div>
                    <div className="space-y-2 min-h-[40px]">
                      {c.tasks.map(t => (
                        <TaskCard key={t.task_id} t={t} members={members} onMove={attemptMove} onAssign={assign} onOpen={() => setOpenId(t.task_id)}
                          dragging={drag?.task_id === t.task_id} onDragStart={() => setDrag(t)} onDragEnd={() => { setDrag(null); setOverCol(null) }} />
                      ))}
                      {c.tasks.length === 0 && <div className="text-[11px] text-[var(--color-faint)] px-1.5 py-3 text-center">—</div>}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )}

      {openId && <TaskDrawer taskId={openId} members={members} onClose={closeDrawer} onChanged={refresh} />}
      {gate && <GateModal task={gate.task} target={gate.target} onClose={() => setGate(null)} onConfirm={atts => { const g = gate; setGate(null); move(g.task, g.target, atts) }} />}
      {completing && <CompletionModal task={completing} onClose={() => setCompleting(null)} onConfirm={note => { const t = completing; setCompleting(null); requestCompletion(t, note) }} />}
    </div>
  )
}

function TaskCard({ t, members, onMove, onAssign, onOpen, dragging, onDragStart, onDragEnd }: { t: Task; members: Member[]; onMove: (t: Task, s: string) => void; onAssign: (t: Task, u: string) => void; onOpen: () => void; dragging?: boolean; onDragStart?: () => void; onDragEnd?: () => void }) {
  const overdue = !!t.due_date && t.status !== 'done' && t.due_date < new Date().toISOString().slice(0, 10)
  const next = NEXT[t.status]
  const gatedNext = !!next && idx(next) > idx(t.status) && gateItemsFor(next, t).length > 0
  return (
    <div draggable onDragStart={e => { e.dataTransfer.effectAllowed = 'move'; onDragStart?.() }} onDragEnd={onDragEnd}
      className={clsx('group/card rounded-lg bg-[var(--color-bg-2)] border border-[var(--color-line)] p-2.5 cursor-grab active:cursor-grabbing transition', dragging && 'opacity-40 ring-1 ring-[var(--color-sky)]')}>
      <button onClick={onOpen} className="flex items-start gap-1.5 w-full text-left group">
        <GripVertical size={12} className="text-[var(--color-faint)] opacity-0 group-hover/card:opacity-100 transition shrink-0 mt-1" />
        <span className="w-1.5 h-1.5 rounded-full mt-1.5 shrink-0" style={{ background: CRIT_COLOR[t.criticality] }} title={CRIT_LABEL[t.criticality]} />
        <span className="text-[12.5px] text-[var(--color-ink)] group-hover:text-[var(--color-sky)] transition leading-snug flex-1">{t.title}</span>
      </button>
      <div className="flex items-center gap-1.5 mt-1.5 flex-wrap text-[10.5px]">
        {SRC_LABEL[t.source] && <span className="px-1.5 py-0.5 rounded bg-[var(--color-panel-2)] text-[var(--color-faint)]">{SRC_LABEL[t.source]}</span>}
        {t.filing_id && <span className="text-[var(--color-sky)]">Filing</span>}
        {t.pending_completion_request_id && <span className="inline-flex items-center gap-0.5 text-[var(--color-sky)]"><ShieldCheck size={10} />Awaiting approval</span>}
        {overdue && <span className="inline-flex items-center gap-0.5 text-[var(--color-bad)]"><AlertTriangle size={10} />Overdue</span>}
        {t.due_date && !overdue && <span className="text-[var(--color-faint)] tabular-nums">Due {t.due_date}</span>}
      </div>
      <div className="flex items-center justify-between gap-1 mt-2">
        <select value={t.assignee_user_id ?? ''} onChange={e => onAssign(t, e.target.value)} aria-label="Owner"
          className="max-w-[110px] bg-transparent text-[11px] text-[var(--color-mute)] outline-none border-b border-transparent hover:border-[var(--color-line-2)]">
          <option value="">No owner</option>
          {members.map(m => <option key={m.user_id} value={m.user_id}>{m.name || m.email.split('@')[0]}</option>)}
        </select>
        <div className="flex items-center gap-0.5">
          {PREV[t.status] && <button onClick={() => onMove(t, PREV[t.status])} aria-label={`Move back to ${COL_LABEL[PREV[t.status]]}`} className="text-[var(--color-faint)] hover:text-[var(--color-ink)]"><ChevronLeft size={14} /></button>}
          {next && (t.pending_completion_request_id
            ? <span title="Awaiting a different colleague’s approval — see Approvals" className="text-[var(--color-sky)] inline-flex items-center"><ShieldCheck size={13} /></span>
            : <button onClick={() => onMove(t, next)} aria-label={next === 'done' ? 'Ask a second person to approve completion' : `Move to ${COL_LABEL[next]}`}
                className="text-[var(--color-faint)] hover:text-[var(--color-sky)] inline-flex items-center">{(gatedNext || next === 'done') && <ShieldCheck size={11} />}<ChevronRight size={14} /></button>)}
        </div>
      </div>
    </div>
  )
}

// the mentions of you, in a side drawer (the shared overlay — never a hand-made screen cover)
function MentionsBell({ onOpen }: { onOpen: (taskId: string) => void }) {
  const [open, setOpen] = useState(false)
  const q = useQuery({ queryKey: ['reg-task-mentions'], queryFn: () => api.get<Mention[]>('/v1/reg-tasks/mentions'), refetchInterval: 30000 })
  const items = q.data ?? []
  return (
    <>
      <button onClick={() => setOpen(true)} aria-label={`Mentions of you: ${items.length}`} className="relative text-[var(--color-mute)] hover:text-[var(--color-ink)] p-1.5">
        <Bell size={19} />
        {items.length > 0 && <span className="absolute -top-0.5 -right-0.5 min-w-[16px] h-[16px] px-1 rounded-full text-[10px] font-semibold flex items-center justify-center bg-[var(--color-sky)] text-[var(--color-on-accent)]">{items.length}</span>}
      </button>
      {open && (
        <Drawer label="Mentions of you" onClose={() => setOpen(false)} className="w-full max-w-sm h-full overflow-y-auto bg-[var(--color-bg-2)] border-l border-[var(--color-line)]">
          <div className="sticky top-0 bg-[var(--color-bg-2)] border-b border-[var(--color-line)] px-4 py-3 flex items-center justify-between">
            <span className="text-[13.5px] font-semibold text-[var(--color-ink)]">Mentions of you</span><CloseButton onClick={() => setOpen(false)} />
          </div>
          {items.length === 0 ? <div className="px-4 py-6 text-[12.5px] text-[var(--color-faint)] text-center">No unread mentions.</div> : (
            <ul className="m-0 p-0 list-none divide-y divide-[var(--color-line)]">
              {items.map(m => (
                <li key={m.mention_id}>
                  <button onClick={() => { onOpen(m.task_id); setOpen(false) }} className="w-full text-left px-4 py-2.5 hover:bg-[var(--color-panel)]">
                    <div className="text-[12.5px] text-[var(--color-ink)] truncate">{m.task_title}</div>
                    {m.snippet && <div className="text-[12px] text-[var(--color-mute)] mt-0.5 line-clamp-2">{m.snippet}</div>}
                    <div className="text-[11px] text-[var(--color-faint)] mt-1">{m.by ?? 'A colleague'} · {stamp(m.at)}</div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Drawer>
      )}
    </>
  )
}
