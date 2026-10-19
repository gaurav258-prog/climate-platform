import { type ReactNode, useEffect, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { AtSign, Clock, Download, FileText, Paperclip, Send, ShieldCheck, Trash2 } from 'lucide-react'
import { api, download, upload } from '../../lib/api'
import { toast } from '../../lib/toast'
import { useAuth } from '../../lib/auth'
import { filingLink } from '../../lib/links'
import { Button } from '../../components/ui'
import { CloseButton } from '../../components/Dialog'
import { Drawer } from '../../components/Drawer'
import { InfoButton, messageDetails } from '../../components/Details'
import { StatusChip } from '../../components/StatusChip'
import { CompletionModal, GateModal } from './Gates'
import { COLS, COL_LABEL, CRIT, CRIT_LABEL, SRC_LABEL, errText, fmtBytes, handleOf, isGatedForward, stamp, type Attachment, type Member, type TaskDetail } from './model'

// One task: its controls (status through the same stage gate as the board, criticality, owner, due date), its link to a
// filing, its description, files and activity — each event in catalogue words (services/governance/tasks.event_words);
// a comment is a person's own words, with @mentions highlighted.

const box = 'w-full bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-3 py-2 text-[13px] outline-none focus:border-[var(--color-sky)]'

export function TaskDrawer({ taskId, members, onClose, onChanged }: { taskId: string; members: Member[]; onClose: () => void; onChanged: () => void }) {
  const qc = useQueryClient()
  const nav = useNavigate()
  const { profile } = useAuth()
  const q = useQuery({ queryKey: ['reg-task', taskId], queryFn: () => api.get<TaskDetail>(`/v1/reg-tasks/${taskId}`) })
  const t = q.data
  const [gate, setGate] = useState<string | null>(null)
  const [completing, setCompleting] = useState(false)
  const reload = () => { qc.invalidateQueries({ queryKey: ['reg-task', taskId] }); onChanged() }
  const call = async (fn: () => Promise<unknown>) => { try { await fn(); reload() } catch (e) { toast.error(errText(e, 'The change could not be saved.')) } }
  // opening a task clears my unread @mentions on it (the header bell)
  useEffect(() => { api.post(`/v1/reg-tasks/${taskId}/seen`, {}).then(() => qc.invalidateQueries({ queryKey: ['reg-task-mentions'] })).catch(() => {}) }, [taskId, qc])
  const doMove = (target: string, attestations?: string[]) => call(() => api.post(`/v1/reg-tasks/${taskId}/move`, { status: target, attestations }))
  const requestCompletion = (note: string) => call(() => api.post(`/v1/reg-tasks/${taskId}/request-completion`, { note }))
    .then(() => toast.success('Completion asked for — a different colleague approves it on Approvals.'))
  const changeStatus = (target: string) => {
    if (!t || target === t.status) return
    if (target === 'done') {
      if (t.status !== 'review') { toast.error('Move this task to Review first.'); return }
      if (t.pending_completion_request_id) { toast.error('Already waiting for a colleague’s approval — see Approvals.'); return }
      setCompleting(true); return
    }
    if (isGatedForward(t, target)) setGate(target); else doMove(target)
  }

  return (
    <Drawer label="Task" onClose={onClose} className="w-full max-w-md h-full bg-[var(--color-bg-2)] border-l border-[var(--color-line)] overflow-y-auto">
      <div className="sticky top-0 bg-[var(--color-bg-2)] border-b border-[var(--color-line)] px-5 py-3 flex items-center justify-between">
        <span className="text-[13.5px] font-semibold text-[var(--color-ink)]">Task</span>
        <CloseButton onClick={onClose} size={17} />
      </div>
      {!t ? <div className="p-8 text-center text-[var(--color-faint)] text-sm">Loading…</div> : (
        <div className="p-5 space-y-4">
          <input defaultValue={t.title} aria-label="Title" onBlur={e => e.target.value.trim() && e.target.value !== t.title && call(() => api.patch(`/v1/reg-tasks/${taskId}`, { title: e.target.value.trim() }))}
            className="w-full bg-transparent outline-none display text-lg font-semibold" />
          <div className="flex flex-wrap items-center gap-2">
            {SRC_LABEL[t.source] && <StatusChip tone="neutral" label={SRC_LABEL[t.source]} />}
            {t.pending_completion_request_id && (
              <button onClick={() => nav('/approvals')} className="inline-flex items-center gap-1.5 text-[12px] text-[var(--color-sky)] hover:underline"><ShieldCheck size={13} /> Awaiting a second person — see Approvals</button>
            )}
          </div>
          <div className="grid grid-cols-2 gap-3 text-[12px]">
            <Field label="Status">
              <select value={t.status} onChange={e => changeStatus(e.target.value)} className={box}>{COLS.map(c => <option key={c} value={c}>{COL_LABEL[c]}</option>)}</select>
            </Field>
            <Field label="Criticality">
              <select value={t.criticality} onChange={e => call(() => api.patch(`/v1/reg-tasks/${taskId}`, { criticality: e.target.value }))} className={box}>
                {CRIT.map(c => <option key={c} value={c}>{CRIT_LABEL[c]}</option>)}
              </select>
            </Field>
            <Field label="Owner">
              <select value={t.assignee_user_id ?? ''} onChange={e => call(() => api.post(`/v1/reg-tasks/${taskId}/assign`, { assignee_user_id: e.target.value || null }))} className={box}>
                <option value="">No owner</option>
                {members.map(m => <option key={m.user_id} value={m.user_id}>{m.name || m.email}</option>)}
              </select>
            </Field>
            <Field label="Due date">
              <input type="date" defaultValue={t.due_date ?? ''} onChange={e => call(() => api.patch(`/v1/reg-tasks/${taskId}`, e.target.value ? { due_date: e.target.value } : { clear_due: true }))} className={box} />
            </Field>
          </div>
          {t.filing_id && <button onClick={() => nav(filingLink(profile?.org?.type, t.filing_id!))} className="inline-flex items-center gap-1.5 text-[12.5px] text-[var(--color-sky)] hover:underline"><FileText size={13} /> Open the linked filing</button>}
          <Field label="Description">
            <textarea defaultValue={t.description ?? ''} placeholder="Add detail…" rows={3} onBlur={e => e.target.value !== (t.description ?? '') && call(() => api.patch(`/v1/reg-tasks/${taskId}`, { description: e.target.value }))} className={box} />
          </Field>
          <Attachments taskId={taskId} items={t.attachments} onChanged={reload} />
          <section>
            <h4 className="text-[12.5px] font-semibold text-[var(--color-ink)] m-0 mb-2 flex items-center gap-1.5"><Clock size={13} className="text-[var(--color-faint)]" /> Activity</h4>
            <ul className="m-0 p-0 list-none space-y-2">
              {t.events.map((e, i) => (
                <li key={i} className="text-[12.5px]">
                  <div className="flex items-start gap-1.5">
                    <span className="text-[var(--color-ink)] flex-1">{e.kind === 'commented' ? renderMentions(e.note ?? '', members) : e.words.label}</span>
                    {e.kind !== 'commented' && <InfoButton compact details={messageDetails(e.words)} />}
                  </div>
                  <div className="text-[11px] text-[var(--color-faint)]">{e.actor ?? 'The platform'} · {stamp(e.at)}</div>
                </li>
              ))}
            </ul>
            <CommentComposer taskId={taskId} members={members} onDone={reload} />
          </section>
        </div>
      )}
      {t && gate && <GateModal task={t} target={gate} onClose={() => setGate(null)} onConfirm={atts => { const target = gate; setGate(null); doMove(target, atts) }} />}
      {t && completing && <CompletionModal task={t} onClose={() => setCompleting(false)} onConfirm={note => { setCompleting(false); requestCompletion(note) }} />}
    </Drawer>
  )
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return <label className="block"><span className="text-[11.5px] text-[var(--color-mute)]">{label}</span><div className="mt-1">{children}</div></label>
}

// a comment with the @mentions of colleagues highlighted
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

function Attachments({ taskId, items, onChanged }: { taskId: string; items: Attachment[]; onChanged: () => void }) {
  const ref = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState(false)
  const pick = async (file: File) => {
    setBusy(true)
    try { await upload(`/v1/reg-tasks/${taskId}/attachments`, file); onChanged() }
    catch (e) { toast.error(errText(e, 'The file could not be attached.')) }
    finally { setBusy(false); if (ref.current) ref.current.value = '' }
  }
  const remove = async (a: Attachment) => {
    if (!confirm(`Remove “${a.filename}”?`)) return
    try { await api.del(`/v1/reg-tasks/${taskId}/attachments/${a.attachment_id}`); onChanged() }
    catch (e) { toast.error(errText(e, 'The file could not be removed.')) }
  }
  const get = (a: Attachment) => download(`/v1/reg-tasks/${taskId}/attachments/${a.attachment_id}`, a.filename).catch(() => toast.error('The file could not be downloaded.'))
  return (
    <section>
      <div className="flex items-center justify-between mb-2">
        <h4 className="text-[12.5px] font-semibold text-[var(--color-ink)] m-0 flex items-center gap-1.5"><Paperclip size={13} className="text-[var(--color-faint)]" /> Files</h4>
        <button onClick={() => ref.current?.click()} disabled={busy} className="text-[12px] text-[var(--color-sky)] hover:underline disabled:opacity-50">{busy ? 'Uploading…' : 'Attach a file'}</button>
        <input ref={ref} type="file" className="hidden" onChange={e => { const f = e.target.files?.[0]; if (f) pick(f) }} />
      </div>
      {items.length === 0 ? <div className="text-[12px] text-[var(--color-faint)]">No files. Attach evidence, a source file or a screenshot.</div> : (
        <ul className="m-0 p-0 list-none space-y-1.5">
          {items.map(a => (
            <li key={a.attachment_id} className="flex items-center gap-2 rounded-lg border border-[var(--color-line)] bg-[var(--color-panel)] px-2.5 py-1.5">
              <Paperclip size={13} className="text-[var(--color-faint)] shrink-0" />
              <button onClick={() => get(a)} className="text-[12.5px] text-[var(--color-ink)] hover:text-[var(--color-sky)] truncate flex-1 text-left" title={a.filename}>{a.filename}</button>
              <span className="text-[11px] text-[var(--color-faint)] shrink-0 tabular-nums">{fmtBytes(a.size_bytes)}{a.by ? ` · ${a.by.split(' ')[0]}` : ''}</span>
              <button onClick={() => get(a)} aria-label={`Download ${a.filename}`} className="text-[var(--color-faint)] hover:text-[var(--color-sky)] shrink-0"><Download size={13} /></button>
              <button onClick={() => remove(a)} aria-label={`Remove ${a.filename}`} className="text-[var(--color-faint)] hover:text-[var(--color-bad)] shrink-0"><Trash2 size={13} /></button>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

// a comment, with @ to mention a colleague (they see it in their mentions and by e-mail)
function CommentComposer({ taskId, members, onDone }: { taskId: string; members: Member[]; onDone: () => void }) {
  const [val, setVal] = useState('')
  const [query, setQuery] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const ref = useRef<HTMLTextAreaElement>(null)
  const onChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const v = e.target.value; setVal(v)
    const m = v.slice(0, e.target.selectionStart ?? v.length).match(/@([^@]*)$/)
    setQuery(m && m[1].length <= 40 ? m[1] : null)
  }
  const suggestions = query != null ? members.filter(m => handleOf(m).toLowerCase().includes(query.toLowerCase())).slice(0, 6) : []
  const pick = (m: Member) => {
    const el = ref.current, caret = el?.selectionStart ?? val.length
    const before = val.slice(0, caret).replace(/@([^@]*)$/, `@${handleOf(m)} `)
    setVal(before + val.slice(caret)); setQuery(null)
    requestAnimationFrame(() => { el?.focus(); el?.setSelectionRange(before.length, before.length) })
  }
  const submit = async () => {
    const body = val.trim(); if (!body) return
    setBusy(true)
    try { await api.post(`/v1/reg-tasks/${taskId}/comment`, { body, mentions: members.filter(m => val.includes(`@${handleOf(m)}`)).map(m => m.user_id) }); setVal(''); setQuery(null); onDone() }
    catch (e) { toast.error(errText(e, 'The comment could not be added.')) } finally { setBusy(false) }
  }
  return (
    <div className="mt-3 relative">
      {query != null && suggestions.length > 0 && (
        <div className="absolute bottom-full mb-1 left-0 w-64 rounded-lg border border-[var(--color-line-2)] bg-[var(--color-bg-2)] shadow-xl overflow-hidden z-20" role="listbox">
          {suggestions.map(m => (
            <button key={m.user_id} role="option" onMouseDown={e => { e.preventDefault(); pick(m) }} className="w-full text-left px-3 py-1.5 hover:bg-[var(--color-panel)] flex items-center gap-2">
              <AtSign size={12} className="text-[var(--color-sky)]" /><span className="text-[12.5px] text-[var(--color-ink)]">{handleOf(m)}</span>
              <span className="text-[11px] text-[var(--color-faint)] ml-auto truncate">{m.email}</span>
            </button>
          ))}
        </div>
      )}
      <div className="flex items-end gap-2">
        <textarea ref={ref} rows={2} value={val} onChange={onChange} aria-label="Comment"
          onKeyDown={e => {
            if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); if (query != null && suggestions.length) pick(suggestions[0]); else submit() }
            if (e.key === 'Escape') setQuery(null)
          }}
          placeholder="Comment… type @ to mention a colleague" className={`${box} resize-none`} />
        <Button variant="primary" disabled={busy || !val.trim()} onClick={submit} className="px-3"><Send size={14} /></Button>
      </div>
    </div>
  )
}
