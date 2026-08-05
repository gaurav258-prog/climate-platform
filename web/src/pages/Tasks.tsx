import { useState, useEffect } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useSearchParams, useNavigate } from 'react-router-dom'
import { Plus, ChevronRight, ChevronLeft, AlertTriangle, X, Clock, FileText, Send, Check, GripVertical, ShieldCheck } from 'lucide-react'
import { api, ApiError } from '../lib/api'
import { useAuth } from '../lib/auth'
import { Eyebrow, Card, Button } from '../components/ui'
import { filingLink } from '../lib/links'
import { prettify } from '../lib/hazards'

// Kanban board for the regulatory workflow — every task (import a file, investigate a failed validation,
// generate the XBRL, run the 4-eyes approval) as a card you move across columns and assign to a colleague.
// Cards created from validation exceptions carry their source so nothing is invented or duplicated.

interface Task {
  task_id: string; title: string; description: string | null; status: string; criticality: string
  assignee_user_id: string | null; assignee: string | null; assignee_email: string | null
  filing_id: string | null; source: string; source_ref: string | null; due_date: string | null
  depends_on: string[]; created_by: string | null
}
interface TaskEvent { kind: string; from: string | null; to: string | null; note: string | null; at: string; actor: string | null }
interface TaskDetail extends Task { events: TaskEvent[] }
interface Column { key: string; tasks: Task[] }
interface Board { columns: Column[]; summary: { total: number; overdue: number; unassigned: number } }
interface Member { user_id: string; email: string; name: string }
const COLS = ['icebox', 'todo', 'blocked', 'doing', 'review', 'done']

const COL_LABEL: Record<string, string> = { icebox: 'Icebox', todo: 'To do', blocked: 'Blocked', doing: 'Doing', review: 'Review', done: 'Done' }
const NEXT: Record<string, string> = { icebox: 'todo', todo: 'doing', blocked: 'doing', doing: 'review', review: 'done' }
const PREV: Record<string, string> = { todo: 'icebox', blocked: 'todo', doing: 'todo', review: 'doing', done: 'review' }
const CRIT: Record<string, string> = { critical: '#fb7185', high: '#f0a860', normal: '#5cc8ff', low: '#64748b' }
const SRC_LABEL: Record<string, string> = { manual: 'manual', validation: 'validation', exception: 'exception', obligation: 'obligation', regulatory_change: 'reg change' }

// Mandatory stage-gate: to ENTER a stage a card must satisfy that stage's checklist. `auto` items are
// verified from the task's own state (assignee set, work documented, no open dependencies) and can't be
// faked; the rest are attestations the mover confirms. A forward move — by drag OR arrow — is held until
// every item is satisfied. Only the meaningful "you must have done X to be here" stages are gated.
interface GateItem { id: string; label: string; auto?: (t: Task) => boolean; onlyIfFiling?: boolean }
const GATE: Record<string, GateItem[]> = {
  doing: [
    { id: 'assignee', label: 'An owner is assigned to this task', auto: t => !!t.assignee_user_id },
    { id: 'unblocked', label: 'No open dependencies remain', auto: t => (t.depends_on ?? []).length === 0 },
    { id: 'ready', label: 'The inputs / source data needed to start are available' },
  ],
  review: [
    { id: 'documented', label: 'The work done is recorded in the task', auto: t => !!(t.description && t.description.trim()) },
    { id: 'complete', label: 'The deliverable is complete and self-checked' },
    { id: 'validation', label: 'The linked filing’s validation was run with no blocking errors', onlyIfFiling: true },
  ],
  done: [
    { id: 'foureyes', label: 'Reviewed by a second person (4-eyes)' },
    { id: 'recorded', label: 'The outcome is recorded / the filing is submitted' },
  ],
}
const idx = (s: string) => COLS.indexOf(s)
const gateItemsFor = (target: string, t: Task) => (GATE[target] ?? []).filter(i => !i.onlyIfFiling || !!t.filing_id)
// the server rejects a gated move it doesn't like (owner missing, dependency open, checklist absent) with a
// 409 carrying { message }; surface that so the mover sees exactly what's required.
const errMsg = (e: unknown, fallback: string) => e instanceof ApiError ? String((e.body as { message?: string })?.message ?? e.message) : fallback
// is a move into `target` a gated forward move for this task?
const isGatedForward = (t: Task, target: string) => target !== t.status && idx(target) > idx(t.status) && gateItemsFor(target, t).length > 0

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
  useEffect(() => { const t = params.get('task'); if (t) setOpenId(t) }, [params])
  const members = mq.data ?? []
  const refresh = () => qc.invalidateQueries({ queryKey: ['reg-tasks-board'] })
  const closeDrawer = () => { setOpenId(null); if (params.get('task')) { params.delete('task'); setParams(params, { replace: true }) } }

  const add = async () => {
    if (!title.trim()) return
    setBusy(true)
    try { await api.post('/v1/reg-tasks', { title: title.trim(), criticality: crit }); setTitle(''); refresh() }
    catch (e) { alert(e instanceof ApiError ? e.message : 'Could not create the task.') }
    finally { setBusy(false) }
  }
  const move = async (t: Task, status: string, attestations?: string[]) => {
    try { await api.post(`/v1/reg-tasks/${t.task_id}/move`, { status, attestations }); refresh() }
    catch (e) { alert(errMsg(e, 'Could not move the task.')) }
  }
  // a forward move into a gated stage is held for its checklist; backward / same-column moves go straight through
  const attemptMove = (t: Task, target: string) => {
    if (target === t.status) return
    if (isGatedForward(t, target)) { setGate({ task: t, target }); return }
    move(t, target)
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
            {b.columns.map(c => {
              const isTarget = overCol === c.key && !!drag && drag.status !== c.key
              const gated = !!drag && idx(c.key) > idx(drag.status) && gateItemsFor(c.key, drag).length > 0
              return (
              <div key={c.key}
                onDragOver={e => { if (drag) { e.preventDefault(); setOverCol(c.key) } }}
                onDragLeave={() => setOverCol(o => o === c.key ? null : o)}
                onDrop={e => { e.preventDefault(); if (drag) attemptMove(drag, c.key); setDrag(null); setOverCol(null) }}
                className={`rounded-xl border p-2 transition ${isTarget ? 'border-[var(--color-sky)] bg-[color-mix(in_oklab,var(--color-sky)_8%,var(--color-panel))]' : 'border-[var(--color-line)] bg-[var(--color-panel)]'}`}>
                <div className="flex items-center justify-between px-1.5 py-1.5">
                  <span className="mono text-[10.5px] uppercase tracking-wide text-[var(--color-mute)]">{COL_LABEL[c.key]}</span>
                  <span className="mono text-[10.5px] text-[var(--color-faint)]">{isTarget && gated ? <span className="text-[var(--color-sky)] inline-flex items-center gap-0.5"><ShieldCheck size={11} />gate</span> : c.tasks.length}</span>
                </div>
                <div className="space-y-2 min-h-[40px]">
                  {c.tasks.map(t => (
                    <TaskCard key={t.task_id} t={t} members={members} onMove={attemptMove} onAssign={assign} onOpen={() => setOpenId(t.task_id)}
                      dragging={drag?.task_id === t.task_id} onDragStart={() => setDrag(t)} onDragEnd={() => { setDrag(null); setOverCol(null) }} />
                  ))}
                  {c.tasks.length === 0 && <div className="text-[11px] text-[var(--color-faint)] px-1.5 py-3 text-center">—</div>}
                </div>
              </div>
            )})}
          </div>
        </div>
      )}

      {openId && <TaskDrawer taskId={openId} members={members} onClose={closeDrawer} onChanged={refresh} />}
      {gate && <GateModal task={gate.task} target={gate.target} onClose={() => setGate(null)}
        onConfirm={atts => { const g = gate; setGate(null); move(g.task, g.target, atts) }} />}
    </div>
  )
}

// The stage-gate dialog — the mandatory checklist a card must clear to enter a stage. Auto items are
// pre-satisfied from the task's own state and locked; attestations must be ticked. Confirm unlocks only when
// every item is satisfied, then the move goes through.
function GateModal({ task, target, onClose, onConfirm }: { task: Task; target: string; onClose: () => void; onConfirm: (attestations: string[]) => void }) {
  const items = gateItemsFor(target, task)
  const autoOk = (i: GateItem) => (i.auto ? i.auto(task) : false)
  const [checked, setChecked] = useState<Record<string, boolean>>(() => Object.fromEntries(items.map(i => [i.id, autoOk(i)])))
  const allOk = items.every(i => (i.auto ? autoOk(i) : checked[i.id]))
  const confirm = () => onConfirm(items.map(i => i.label))
  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4" onClick={onClose}>
      <div className="absolute inset-0 bg-black/50" />
      <div className="relative w-full max-w-md rounded-2xl bg-[var(--color-bg-2)] border border-[var(--color-line)] shadow-2xl p-5" onClick={e => e.stopPropagation()}>
        <div className="flex items-start justify-between gap-3 mb-1">
          <div>
            <div className="mono text-[10px] uppercase tracking-widest text-[var(--color-sky)] flex items-center gap-1.5"><ShieldCheck size={12} /> Stage gate</div>
            <h3 className="display text-lg font-semibold mt-1">Move to “{COL_LABEL[target]}”</h3>
          </div>
          <button onClick={onClose} className="text-[var(--color-faint)] hover:text-[var(--color-ink)]"><X size={18} /></button>
        </div>
        <p className="text-[12.5px] text-[var(--color-mute)] mb-3">Complete these mandatory checks before the card can enter this stage.</p>
        <div className="space-y-2">
          {items.map(i => {
            const auto = !!i.auto, ok = auto ? autoOk(i) : !!checked[i.id]
            return (
              <button key={i.id} disabled={auto} onClick={() => !auto && setChecked(c => ({ ...c, [i.id]: !c[i.id] }))}
                className={`w-full flex items-start gap-2.5 text-left rounded-lg border p-2.5 transition ${ok ? 'border-[var(--color-good)] bg-[color-mix(in_oklab,var(--color-good)_8%,transparent)]' : 'border-[var(--color-line-2)] hover:border-[var(--color-sky)]'} ${auto ? 'cursor-default' : ''}`}>
                <span className={`mt-0.5 w-4 h-4 rounded flex items-center justify-center shrink-0 ${ok ? 'bg-[var(--color-good)] text-[var(--color-on-accent)]' : 'border border-[var(--color-line-2)]'}`}>{ok && <Check size={12} />}</span>
                <span className="text-[12.5px] text-[var(--color-ink)] leading-snug flex-1">{i.label}{auto && <span className="mono text-[9.5px] ml-1.5" style={{ color: ok ? 'var(--color-good)' : 'var(--color-bad)' }}>{ok ? 'verified' : 'not met'}</span>}</span>
              </button>
            )
          })}
        </div>
        {items.some(i => i.auto && !autoOk(i)) && <p className="text-[11px] text-[var(--color-bad)] mt-2">A verified check isn’t met yet — resolve it on the task (assign an owner, clear dependencies, or add detail) before moving.</p>}
        <div className="flex items-center justify-end gap-2 mt-4">
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button variant="primary" disabled={!allOk} onClick={confirm}><Check size={14} /> Confirm move</Button>
        </div>
      </div>
    </div>
  )
}

function TaskCard({ t, members, onMove, onAssign, onOpen, dragging, onDragStart, onDragEnd }: { t: Task; members: Member[]; onMove: (t: Task, s: string) => void; onAssign: (t: Task, u: string) => void; onOpen: () => void; dragging?: boolean; onDragStart?: () => void; onDragEnd?: () => void }) {
  const overdue = t.due_date && t.status !== 'done' && t.due_date < new Date().toISOString().slice(0, 10)
  const gatedNext = NEXT[t.status] && idx(NEXT[t.status]) > idx(t.status) && gateItemsFor(NEXT[t.status], t).length > 0
  return (
    <div draggable onDragStart={e => { e.dataTransfer.effectAllowed = 'move'; onDragStart?.() }} onDragEnd={onDragEnd}
      className={`group/card rounded-lg bg-[var(--color-bg-2)] border border-[var(--color-line)] p-2.5 cursor-grab active:cursor-grabbing transition ${dragging ? 'opacity-40 ring-1 ring-[var(--color-sky)]' : ''}`}>
      <button onClick={onOpen} className="flex items-start gap-1.5 w-full text-left group">
        <GripVertical size={12} className="text-[var(--color-faint)] opacity-0 group-hover/card:opacity-100 transition shrink-0 mt-1" />
        <span className="w-1.5 h-1.5 rounded-full mt-1.5 shrink-0" style={{ background: CRIT[t.criticality] }} title={t.criticality} />
        <div className="text-[12.5px] text-[var(--color-ink)] group-hover:text-[var(--color-sky)] transition leading-snug flex-1">{t.title}</div>
      </button>
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
          {NEXT[t.status] && <button onClick={() => onMove(t, NEXT[t.status])} title={gatedNext ? `move to ${COL_LABEL[NEXT[t.status]]} — passes a stage gate` : 'move forward'} className="text-[var(--color-faint)] hover:text-[var(--color-sky)] inline-flex items-center">{gatedNext && <ShieldCheck size={11} className="text-[var(--color-faint)] group-hover/card:text-[var(--color-sky)]" />}<ChevronRight size={14} /></button>}
        </div>
      </div>
    </div>
  )
}

function Stat({ n, label, tone }: { n: number; label: string; tone?: string }) {
  return <div><div className="display text-2xl leading-none" style={tone ? { color: tone } : undefined}>{n}</div><div className="mono text-[9.5px] uppercase tracking-wide text-[var(--color-faint)] mt-1">{label}</div></div>
}

const box = 'w-full bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-3 py-2 text-[13px] outline-none focus:border-[var(--color-sky)]'

function TaskDrawer({ taskId, members, onClose, onChanged }: { taskId: string; members: Member[]; onClose: () => void; onChanged: () => void }) {
  const qc = useQueryClient()
  const nav = useNavigate()
  const { profile } = useAuth()
  const q = useQuery({ queryKey: ['reg-task', taskId], queryFn: () => api.get<TaskDetail>(`/v1/reg-tasks/${taskId}`) })
  const t = q.data
  const [comment, setComment] = useState('')
  const [gate, setGate] = useState<string | null>(null)   // target stage awaiting its checklist
  const reload = () => { qc.invalidateQueries({ queryKey: ['reg-task', taskId] }); onChanged() }
  const call = async (fn: () => Promise<unknown>) => { try { await fn(); reload() } catch (e) { alert(errMsg(e, 'Action failed.')) } }
  // changing status here obeys the same stage gate as the board — a gated forward move opens the checklist
  const doMove = (target: string, attestations?: string[]) => call(() => api.post(`/v1/reg-tasks/${taskId}/move`, { status: target, attestations }))
  const changeStatus = (target: string) => { if (!t || target === t.status) return; if (isGatedForward(t, target)) setGate(target); else doMove(target) }

  return (
    <div className="fixed inset-0 z-50 flex justify-end" onClick={onClose}>
      <div className="absolute inset-0 bg-black/40" />
      <div className="relative w-full max-w-md h-full bg-[var(--color-bg-2)] border-l border-[var(--color-line)] overflow-y-auto" onClick={e => e.stopPropagation()}>
        <div className="sticky top-0 bg-[var(--color-bg-2)] border-b border-[var(--color-line)] px-5 py-3 flex items-center justify-between">
          <span className="mono text-[10px] uppercase tracking-widest text-[var(--color-faint)]">Task</span>
          <button onClick={onClose} className="text-[var(--color-faint)] hover:text-[var(--color-ink)]"><X size={17} /></button>
        </div>
        {!t ? <div className="p-8 text-center text-[var(--color-faint)] text-sm">loading…</div> : (
          <div className="p-5 space-y-4">
            {/* title + criticality */}
            <input defaultValue={t.title} onBlur={e => e.target.value.trim() && e.target.value !== t.title && call(() => api.patch(`/v1/reg-tasks/${taskId}`, { title: e.target.value.trim() }))}
              className="w-full bg-transparent outline-none display text-lg font-semibold" />

            {/* quick facts + controls */}
            <div className="grid grid-cols-2 gap-3 text-[12px]">
              <Field label="Status">
                <select value={t.status} onChange={e => changeStatus(e.target.value)} className={box}>
                  {COLS.map(c => <option key={c} value={c}>{COL_LABEL[c]}</option>)}
                </select>
              </Field>
              <Field label="Criticality">
                <select value={t.criticality} onChange={e => call(() => api.patch(`/v1/reg-tasks/${taskId}`, { criticality: e.target.value }))} className={box}>
                  {['low', 'normal', 'high', 'critical'].map(c => <option key={c} value={c}>{c}</option>)}
                </select>
              </Field>
              <Field label="Assignee">
                <select value={t.assignee_user_id ?? ''} onChange={e => call(() => api.post(`/v1/reg-tasks/${taskId}/assign`, { assignee_user_id: e.target.value || null }))} className={box}>
                  <option value="">unassigned</option>
                  {members.map(m => <option key={m.user_id} value={m.user_id}>{m.name || m.email}</option>)}
                </select>
              </Field>
              <Field label="Due date">
                <input type="date" defaultValue={t.due_date ?? ''} onChange={e => call(() => api.patch(`/v1/reg-tasks/${taskId}`, e.target.value ? { due_date: e.target.value } : { clear_due: true }))} className={box} />
              </Field>
            </div>

            {t.source !== 'manual' && <div className="text-[11px] text-[var(--color-faint)]">created from a <b className="text-[var(--color-mute)]">{SRC_LABEL[t.source]}</b>{t.source_ref ? ` · ${prettify(t.source_ref.split(':').pop())}` : ''}</div>}
            {t.filing_id && <button onClick={() => nav(filingLink(profile?.org?.type, t.filing_id!))} className="inline-flex items-center gap-1.5 text-[12px] text-[var(--color-sky)] hover:underline"><FileText size={13} /> Open the linked filing</button>}

            {/* description */}
            <Field label="Description">
              <textarea defaultValue={t.description ?? ''} placeholder="Add detail…" rows={3}
                onBlur={e => e.target.value !== (t.description ?? '') && call(() => api.patch(`/v1/reg-tasks/${taskId}`, { description: e.target.value }))} className={box} />
            </Field>

            {/* activity log */}
            <div>
              <div className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)] mb-2 flex items-center gap-1"><Clock size={11} /> Activity</div>
              <div className="space-y-2">
                {t.events.map((e, i) => (
                  <div key={i} className="text-[11.5px]">
                    <span className="text-[var(--color-ink)]">{e.kind === 'moved' ? `moved ${e.from} → ${e.to}` : e.kind === 'assigned' ? 'assignment changed' : e.kind === 'commented' ? e.note : e.kind === 'created' ? 'created' : e.note || e.kind}</span>
                    <span className="mono text-[9.5px] text-[var(--color-faint)] ml-1.5">{e.actor ?? 'system'} · {new Date(e.at).toLocaleString('en-GB', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })}</span>
                  </div>
                ))}
              </div>
              <div className="flex items-center gap-2 mt-3">
                <input value={comment} onChange={e => setComment(e.target.value)} onKeyDown={e => e.key === 'Enter' && comment.trim() && call(() => api.post(`/v1/reg-tasks/${taskId}/comment`, { body: comment.trim() }).then(() => setComment('')))} placeholder="Comment…" className={box} />
                <Button variant="primary" disabled={!comment.trim()} onClick={() => call(() => api.post(`/v1/reg-tasks/${taskId}/comment`, { body: comment.trim() }).then(() => setComment('')))}><Send size={14} /></Button>
              </div>
            </div>
          </div>
        )}
      </div>
      {t && gate && <GateModal task={t} target={gate} onClose={() => setGate(null)}
        onConfirm={atts => { const target = gate; setGate(null); doMove(target, atts) }} />}
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <label className="block"><span className="mono text-[9.5px] uppercase tracking-wide text-[var(--color-faint)]">{label}</span><div className="mt-1">{children}</div></label>
}
