import { useState, useEffect, useRef, type ReactNode } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useSearchParams, useNavigate } from 'react-router-dom'
import { Plus, ChevronRight, ChevronLeft, AlertTriangle, X, Clock, FileText, Send, Check, GripVertical, ShieldCheck, Paperclip, Download, Trash2, AtSign, Bell } from 'lucide-react'
import { api, ApiError, upload, download } from '../lib/api'
import { toast } from '../lib/toast'
import { useAuth } from '../lib/auth'
import { Card, Button, PageHeader, HeroStrip, HeroMetric } from '../components/ui'
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
interface Attachment { attachment_id: string; filename: string; content_type: string | null; size_bytes: number; by: string | null; at: string }
interface TaskDetail extends Task { events: TaskEvent[]; attachments: Attachment[] }
interface Column { key: string; tasks: Task[] }
interface Board { columns: Column[]; summary: { total: number; overdue: number; unassigned: number } }
interface Member { user_id: string; email: string; name: string }
interface Mention { mention_id: string; task_id: string; task_title: string; snippet: string | null; by: string | null; at: string }
const fmtBytes = (n: number) => n < 1024 ? `${n} B` : n < 1048576 ? `${(n / 1024).toFixed(0)} KB` : `${(n / 1048576).toFixed(1)} MB`
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
    catch (e) { toast.error(e instanceof ApiError ? e.message : 'Could not create the task.') }
    finally { setBusy(false) }
  }
  const move = async (t: Task, status: string, attestations?: string[]) => {
    try { await api.post(`/v1/reg-tasks/${t.task_id}/move`, { status, attestations }); refresh() }
    catch (e) { toast.error(errMsg(e, 'Could not move the task.')) }
  }
  // a forward move into a gated stage is held for its checklist; backward / same-column moves go straight through
  const attemptMove = (t: Task, target: string) => {
    if (target === t.status) return
    if (isGatedForward(t, target)) { setGate({ task: t, target }); return }
    move(t, target)
  }
  const assign = async (t: Task, uid: string) => {
    try { await api.post(`/v1/reg-tasks/${t.task_id}/assign`, { assignee_user_id: uid || null }); refresh() }
    catch (e) { toast.error(e instanceof ApiError ? e.message : 'Could not assign the task.') }
  }

  const b = q.data
  return (
    <div className="fadeup space-y-5">
      <PageHeader eyebrow="Workflow" title="Tasks"
        lead="Everything the team needs to do to get a filing out — move a card across the board, or assign it to a colleague."
        actions={<MentionsBell onOpen={setOpenId} />} />

      {b && (
        <HeroStrip>
          <HeroMetric value={b.summary.total} label="Open" />
          <HeroMetric value={b.summary.overdue} label="Overdue" tone={b.summary.overdue > 0 ? '#D23B3B' : undefined} />
          <HeroMetric value={b.summary.unassigned} label="Unassigned" tone={b.summary.unassigned > 0 ? '#E8853C' : undefined} />
        </HeroStrip>
      )}

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

const box = 'w-full bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-3 py-2 text-[13px] outline-none focus:border-[var(--color-sky)]'

function TaskDrawer({ taskId, members, onClose, onChanged }: { taskId: string; members: Member[]; onClose: () => void; onChanged: () => void }) {
  const qc = useQueryClient()
  const nav = useNavigate()
  const { profile } = useAuth()
  const q = useQuery({ queryKey: ['reg-task', taskId], queryFn: () => api.get<TaskDetail>(`/v1/reg-tasks/${taskId}`) })
  const t = q.data
  const [gate, setGate] = useState<string | null>(null)   // target stage awaiting its checklist
  const reload = () => { qc.invalidateQueries({ queryKey: ['reg-task', taskId] }); onChanged() }
  const call = async (fn: () => Promise<unknown>) => { try { await fn(); reload() } catch (e) { toast.error(errMsg(e, 'Action failed.')) } }
  // opening a task clears my unread @mentions on it (drives the header bell)
  useEffect(() => { api.post(`/v1/reg-tasks/${taskId}/seen`, {}).then(() => qc.invalidateQueries({ queryKey: ['reg-task-mentions'] })).catch(() => {}) }, [taskId, qc])
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

            {/* attachments */}
            <Attachments taskId={taskId} items={t.attachments} onChanged={reload} />

            {/* activity log */}
            <div>
              <div className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)] mb-2 flex items-center gap-1"><Clock size={11} /> Activity</div>
              <div className="space-y-2">
                {t.events.map((e, i) => (
                  <div key={i} className="text-[11.5px]">
                    <span className="text-[var(--color-ink)]">{e.kind === 'commented'
                      ? renderMentions(e.note ?? '', members)
                      : e.kind === 'moved' ? `moved ${e.from} → ${e.to}` : e.kind === 'assigned' ? 'assignment changed'
                      : e.kind === 'attached' ? <>attached <span className="text-[var(--color-mute)]">{e.note}</span></>
                      : e.kind === 'removed_attachment' ? <>removed attachment <span className="text-[var(--color-mute)]">{e.note}</span></>
                      : e.kind === 'created' ? 'created' : e.note || e.kind}</span>
                    <span className="mono text-[9.5px] text-[var(--color-faint)] ml-1.5">{e.actor ?? 'system'} · {new Date(e.at).toLocaleString('en-GB', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })}</span>
                  </div>
                ))}
              </div>
              <CommentComposer taskId={taskId} members={members} onDone={reload} />
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

// a colleague's @handle — their name without the trailing "(Org)" qualifier
const handleOf = (m: Member) => m.name.replace(/\s*\(.*\)$/, '').trim() || m.email.split('@')[0]

// render a comment, highlighting @mentions that match a colleague
function renderMentions(text: string, members: Member[]): ReactNode {
  const handles = [...new Set(members.map(handleOf))].filter(Boolean).sort((a, b) => b.length - a.length)
  if (!handles.length) return text
  const re = new RegExp(`@(${handles.map(h => h.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')})`, 'g')
  const out: ReactNode[] = []
  let last = 0, m: RegExpExecArray | null
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index))
    out.push(<span key={m.index} className="text-[var(--color-sky)] font-medium">@{m[1]}</span>)
    last = m.index + m[0].length
  }
  if (last < text.length) out.push(text.slice(last))
  return out.length ? out : text
}

// ── task attachments ─────────────────────────────────────────────────────────────────────────────────────
function Attachments({ taskId, items, onChanged }: { taskId: string; items: Attachment[]; onChanged: () => void }) {
  const ref = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState(false)
  const pick = async (file: File) => {
    setBusy(true)
    try { await upload(`/v1/reg-tasks/${taskId}/attachments`, file); onChanged() }
    catch (e) { toast.error(errMsg(e, 'Could not attach the file.')) }
    finally { setBusy(false); if (ref.current) ref.current.value = '' }
  }
  const remove = async (a: Attachment) => {
    if (!confirm(`Remove “${a.filename}”?`)) return
    try { await api.del(`/v1/reg-tasks/${taskId}/attachments/${a.attachment_id}`); onChanged() }
    catch (e) { toast.error(errMsg(e, 'Could not remove the attachment.')) }
  }
  return (
    <div>
      <div className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)] mb-2 flex items-center justify-between">
        <span className="flex items-center gap-1"><Paperclip size={11} /> Attachments</span>
        <button onClick={() => ref.current?.click()} disabled={busy} className="text-[var(--color-sky)] hover:underline normal-case tracking-normal disabled:opacity-50">{busy ? 'uploading…' : '+ attach file'}</button>
        <input ref={ref} type="file" className="hidden" onChange={e => { const f = e.target.files?.[0]; if (f) pick(f) }} />
      </div>
      {items.length === 0
        ? <div className="text-[11.5px] text-[var(--color-faint)]">No files attached. Attach supporting evidence, a source file, or a screenshot.</div>
        : <div className="space-y-1.5">
            {items.map(a => (
              <div key={a.attachment_id} className="flex items-center gap-2 rounded-lg border border-[var(--color-line)] bg-[var(--color-panel)] px-2.5 py-1.5">
                <Paperclip size={13} className="text-[var(--color-faint)] shrink-0" />
                <button onClick={() => download(`/v1/reg-tasks/${taskId}/attachments/${a.attachment_id}`, a.filename).catch(() => toast.error('Could not download the file.'))}
                  className="text-[12.5px] text-[var(--color-ink)] hover:text-[var(--color-sky)] truncate flex-1 text-left" title={a.filename}>{a.filename}</button>
                <span className="mono text-[9.5px] text-[var(--color-faint)] shrink-0">{fmtBytes(a.size_bytes)}{a.by ? ` · ${a.by.split(' ')[0]}` : ''}</span>
                <button onClick={() => download(`/v1/reg-tasks/${taskId}/attachments/${a.attachment_id}`, a.filename).catch(() => {})} title="Download" className="text-[var(--color-faint)] hover:text-[var(--color-sky)] shrink-0"><Download size={13} /></button>
                <button onClick={() => remove(a)} title="Remove" className="text-[var(--color-faint)] hover:text-[var(--color-bad)] shrink-0"><Trash2 size={13} /></button>
              </div>
            ))}
          </div>}
    </div>
  )
}

// ── comment composer with @mention autocomplete ──────────────────────────────────────────────────────────
function CommentComposer({ taskId, members, onDone }: { taskId: string; members: Member[]; onDone: () => void }) {
  const [val, setVal] = useState('')
  const [query, setQuery] = useState<string | null>(null)   // active @… token, or null
  const [busy, setBusy] = useState(false)
  const ref = useRef<HTMLTextAreaElement>(null)
  const box = 'w-full bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-3 py-2 text-[13px] outline-none focus:border-[var(--color-sky)] resize-none'

  const onChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const v = e.target.value; setVal(v)
    const before = v.slice(0, e.target.selectionStart ?? v.length)
    const m = before.match(/@([^@]*)$/)   // text after the last @ up to the caret
    setQuery(m && m[1].length <= 40 ? m[1] : null)
  }
  const suggestions = query != null ? members.filter(m => handleOf(m).toLowerCase().includes(query.toLowerCase())).slice(0, 6) : []
  const pick = (m: Member) => {
    const el = ref.current, caret = el?.selectionStart ?? val.length
    const before = val.slice(0, caret).replace(/@([^@]*)$/, `@${handleOf(m)} `)
    const nv = before + val.slice(caret)
    setVal(nv); setQuery(null)
    requestAnimationFrame(() => { el?.focus(); el?.setSelectionRange(before.length, before.length) })
  }
  const mentionIds = () => members.filter(m => val.includes(`@${handleOf(m)}`)).map(m => m.user_id)
  const submit = async () => {
    const body = val.trim(); if (!body) return
    setBusy(true)
    try { await api.post(`/v1/reg-tasks/${taskId}/comment`, { body, mentions: mentionIds() }); setVal(''); setQuery(null); onDone() }
    catch (e) { toast.error(errMsg(e, 'Could not add the comment.')) }
    finally { setBusy(false) }
  }
  return (
    <div className="mt-3 relative">
      {query != null && suggestions.length > 0 && (
        <div className="absolute bottom-full mb-1 left-0 w-64 rounded-lg border border-[var(--color-line-2)] bg-[var(--color-bg-2)] shadow-xl overflow-hidden z-20">
          {suggestions.map(m => (
            <button key={m.user_id} onMouseDown={e => { e.preventDefault(); pick(m) }}
              className="w-full text-left px-3 py-1.5 hover:bg-[var(--color-panel)] flex items-center gap-2">
              <AtSign size={12} className="text-[var(--color-sky)]" />
              <span className="text-[12.5px] text-[var(--color-ink)]">{handleOf(m)}</span>
              <span className="mono text-[9.5px] text-[var(--color-faint)] ml-auto">{m.email}</span>
            </button>
          ))}
        </div>
      )}
      <div className="flex items-end gap-2">
        <textarea ref={ref} rows={2} value={val} onChange={onChange}
          onKeyDown={e => {
            if (e.key === 'Enter' && !e.shiftKey) {
              if (query != null && suggestions.length) { e.preventDefault(); pick(suggestions[0]) }
              else { e.preventDefault(); submit() }
            }
            if (e.key === 'Escape') setQuery(null)
          }}
          placeholder="Comment…  type @ to mention a colleague" className={box} />
        <Button variant="primary" disabled={busy || !val.trim()} onClick={submit}><Send size={14} /></Button>
      </div>
      <div className="mono text-[9px] text-[var(--color-faint)] mt-1 flex items-center gap-1"><AtSign size={9} /> mention a colleague to ping them — in their mentions and by email. Enter to send, Shift+Enter for a new line.</div>
    </div>
  )
}

// ── the mentions inbox (header bell) ─────────────────────────────────────────────────────────────────────
function MentionsBell({ onOpen }: { onOpen: (taskId: string) => void }) {
  const [open, setOpen] = useState(false)
  const q = useQuery({ queryKey: ['reg-task-mentions'], queryFn: () => api.get<Mention[]>('/v1/reg-tasks/mentions'), refetchInterval: 30000 })
  const items = q.data ?? []
  return (
    <div className="relative">
      <button onClick={() => setOpen(o => !o)} title="Mentions of you" className="relative text-[var(--color-mute)] hover:text-[var(--color-ink)] p-1.5">
        <Bell size={19} />
        {items.length > 0 && <span className="absolute -top-0.5 -right-0.5 min-w-[16px] h-[16px] px-1 rounded-full text-[9.5px] font-semibold flex items-center justify-center" style={{ background: 'var(--color-sky)', color: 'var(--color-on-accent)' }}>{items.length}</span>}
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div className="absolute right-0 top-full mt-2 w-80 rounded-xl border border-[var(--color-line-2)] bg-[var(--color-bg-2)] shadow-2xl overflow-hidden z-50">
            <div className="px-4 py-2.5 border-b border-[var(--color-line)] mono text-[10px] uppercase tracking-widest text-[var(--color-faint)]">Mentions of you</div>
            {items.length === 0
              ? <div className="px-4 py-6 text-[12px] text-[var(--color-faint)] text-center">No unread mentions.</div>
              : <div className="max-h-96 overflow-y-auto divide-y divide-[var(--color-line)]">
                  {items.map(m => (
                    <button key={m.mention_id} onClick={() => { onOpen(m.task_id); setOpen(false) }} className="w-full text-left px-4 py-2.5 hover:bg-[var(--color-panel)]">
                      <div className="text-[12.5px] text-[var(--color-ink)] truncate">{m.task_title}</div>
                      {m.snippet && <div className="text-[11.5px] text-[var(--color-mute)] mt-0.5 line-clamp-2">{m.snippet}</div>}
                      <div className="mono text-[9.5px] text-[var(--color-faint)] mt-1">{m.by ?? 'someone'} · {new Date(m.at).toLocaleString('en-GB', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })}</div>
                    </button>
                  ))}
                </div>}
          </div>
        </>
      )}
    </div>
  )
}
