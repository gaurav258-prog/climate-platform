import { ApiError, apiDetail, apiMessage } from '../../lib/api'
import type { Message } from '../../components/Details'

// The task board's shapes and words: its columns, criticality and sources in customer words, and the stage gate a card
// must clear to enter Doing or Review. 'done' is never a plain move: completing a task needs a real second person — a
// completion request a different colleague approves on Approvals (services/governance/tasks.request_completion).

export interface Task {
  task_id: string; title: string; description: string | null; status: string; criticality: string
  assignee_user_id: string | null; assignee: string | null; assignee_email: string | null
  filing_id: string | null; source: string; source_ref: string | null; due_date: string | null
  depends_on: string[]; created_by: string | null; pending_completion_request_id: string | null
}
export interface TaskEvent { kind: string; note: string | null; at: string; actor: string | null; words: Message }
export interface Attachment { attachment_id: string; filename: string; size_bytes: number; by: string | null; at: string }
export interface TaskDetail extends Task { events: TaskEvent[]; attachments: Attachment[] }
export interface Column { key: string; tasks: Task[] }
export interface Board { columns: Column[]; summary: { total: number; overdue: number; unassigned: number } }
export interface Member { user_id: string; email: string; name: string }
export interface Mention { mention_id: string; task_id: string; task_title: string; snippet: string | null; by: string | null; at: string }

export const COLS = ['icebox', 'todo', 'blocked', 'doing', 'review', 'done']
export const COL_LABEL: Record<string, string> = { icebox: 'Icebox', todo: 'To do', blocked: 'Blocked', doing: 'Doing', review: 'Review', done: 'Done' }
export const NEXT: Record<string, string> = { icebox: 'todo', todo: 'doing', blocked: 'doing', doing: 'review', review: 'done' }
export const PREV: Record<string, string> = { todo: 'icebox', blocked: 'todo', doing: 'todo', review: 'doing', done: 'review' }
export const CRIT = ['low', 'normal', 'high', 'critical']
export const CRIT_LABEL: Record<string, string> = { low: 'Low', normal: 'Normal', high: 'High', critical: 'Critical' }
export const CRIT_COLOR: Record<string, string> = { critical: 'var(--color-bad)', high: 'var(--color-warn)', normal: 'var(--color-sky)', low: 'var(--color-slate)' }
export const SRC_LABEL: Record<string, string> = { validation: 'From a check', exception: 'From an exception', obligation: 'From an obligation',
  regulatory_change: 'From a rule change', kri: 'From an indicator', supply: 'From a supply signal', supervisor: 'From the supervisor', decision: 'From a decision' }
export const COL_COLOR: Record<string, string> = { icebox: 'var(--color-slate)', todo: 'var(--color-sky)', blocked: 'var(--color-bad)', doing: 'var(--color-blue)', review: 'var(--color-warn)', done: 'var(--color-good)' }

// The stage gate: to enter a stage a card must satisfy its checklist. Items with `auto` are verified from the task's
// own state (an owner, the work recorded, no open dependencies) and cannot be ticked by hand; the server checks the same
// and, for a filing-linked task entering Review, reads the filing's own validation.
export interface GateItem { id: string; label: string; auto?: (t: Task) => boolean; onlyIfFiling?: boolean }
export const GATE: Record<string, GateItem[]> = {
  doing: [
    { id: 'assignee', label: 'An owner is assigned to this task', auto: t => !!t.assignee_user_id },
    { id: 'unblocked', label: 'No open dependencies remain', auto: t => (t.depends_on ?? []).length === 0 },
    { id: 'ready', label: 'The inputs needed to start are available' },
  ],
  review: [
    { id: 'documented', label: 'The work done is recorded in the task', auto: t => !!(t.description && t.description.trim()) },
    { id: 'complete', label: 'The deliverable is complete and self-checked' },
    { id: 'validation', label: 'The linked filing’s checks were run with no blocking errors', onlyIfFiling: true },
  ],
}
export const idx = (s: string) => COLS.indexOf(s)
export const gateItemsFor = (target: string, t: Task) => (GATE[target] ?? []).filter(i => !i.onlyIfFiling || !!t.filing_id)
export const isGatedForward = (t: Task, target: string) => target !== t.status && idx(target) > idx(t.status) && gateItemsFor(target, t).length > 0

// a refused move or edit: the catalogue's words the server sent
export const errText = (e: unknown, fallback: string) => e instanceof ApiError ? (apiDetail(e)?.what ?? apiMessage(e, fallback)) : fallback
export const fmtBytes = (n: number) => n < 1024 ? `${n} B` : n < 1048576 ? `${(n / 1024).toFixed(0)} KB` : `${(n / 1048576).toFixed(1)} MB`
export const stamp = (iso: string) => new Date(iso).toLocaleString('en-GB', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })
// a colleague's @handle — their name without a trailing "(Organisation)"
export const handleOf = (m: Member) => m.name.replace(/\s*\(.*\)$/, '').trim() || m.email.split('@')[0]
