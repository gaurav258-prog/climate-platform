import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { LifeBuoy, Plus, Send, CheckCircle2, RotateCcw, MessageSquare } from 'lucide-react'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { Eyebrow, Card } from '../components/ui'

interface SReq {
  id: string; category: string; subject: string; body: string | null; priority: string; status: string
  requester_email: string | null; message_count: number; awaiting_customer: boolean
  created_at: string | null; updated_at: string | null; first_response_at: string | null
  resolved_at: string | null; last_activity: string | null
}
interface SMsg { id: string; author_side: 'customer' | 'support'; author_email: string | null; author_name: string | null; body: string; created_at: string | null }
interface SDetail { request: SReq; messages: SMsg[] }

const CATEGORIES: [string, string][] = [
  ['question', 'Question — how does it work?'], ['bug', 'Bug — something is wrong / incorrect'],
  ['data', 'Data — a feed or figure looks off'], ['report', 'Report / filing help'],
  ['onboarding', 'Onboarding / setup'], ['other', 'Something else'],
]
const CAT_LABEL: Record<string, string> = Object.fromEntries(CATEGORIES)
const PRIORITIES = ['low', 'normal', 'high', 'urgent']

const statusPill = (s: string) => s === 'resolved'
  ? 'text-[var(--color-good)] bg-[color-mix(in_oklab,var(--color-good)_14%,transparent)]'
  : s === 'in_progress' ? 'text-[var(--color-sky)] bg-[color-mix(in_oklab,var(--color-sky)_14%,transparent)]'
  : 'text-[var(--color-warn)] bg-[color-mix(in_oklab,var(--color-warn)_14%,transparent)]'
const STATUS_LABEL: Record<string, string> = { open: 'open', in_progress: 'in progress', resolved: 'resolved' }

const ago = (iso: string | null) => {
  if (!iso) return ''
  const d = (Date.now() - new Date(iso).getTime()) / 86400000
  return d < 0.04 ? 'just now' : d < 1 ? 'today' : d < 2 ? 'yesterday' : `${Math.floor(d)}d ago`
}

export default function Support() {
  const qc = useQueryClient()
  const [sel, setSel] = useState<string | null>(null)
  const [composing, setComposing] = useState(false)
  const list = useQuery({ queryKey: ['portal-requests'], queryFn: () => api.get<SReq[]>('/v1/portal/requests') })

  const rows = list.data ?? []
  const refresh = () => qc.invalidateQueries({ queryKey: ['portal-requests'] })

  return (
    <div className="fadeup space-y-6">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <Eyebrow>Support · with Tellumen</Eyebrow>
          <h1 className="display text-3xl font-semibold mt-2 mb-1">Support</h1>
          <p className="text-[var(--color-mute)] text-sm max-w-2xl">
            Something wrong, a figure that looks off, or a question on how the software works? Raise a request and
            talk to the Tellumen team here. Every request and reply is recorded in your audit log.
          </p>
        </div>
        <button onClick={() => { setComposing(true); setSel(null) }}
          className="inline-flex items-center gap-1.5 rounded-lg px-3.5 py-2 text-[13px] font-medium bg-[var(--color-sky)] text-[#0b1206] hover:opacity-90 shrink-0">
          <Plus size={15} /> New request
        </button>
      </div>

      <div className="grid lg:grid-cols-[minmax(0,360px)_1fr] gap-5 items-start">
        {/* list */}
        <div className="space-y-2">
          {list.isLoading ? <Card className="p-6 text-center text-[var(--color-faint)] text-sm">loading…</Card>
            : rows.length === 0 ? (
              <Card className="p-8 text-center text-[var(--color-faint)] text-sm flex flex-col items-center gap-2">
                <LifeBuoy size={22} /> No requests yet. Raise one and we'll pick it up.
              </Card>
            ) : rows.map(r => (
              <button key={r.id} onClick={() => { setSel(r.id); setComposing(false) }}
                className={`w-full text-left rounded-xl border p-3.5 transition ${sel === r.id
                  ? 'border-[var(--color-sky)] bg-[var(--color-panel-2)]'
                  : 'border-[var(--color-line)] bg-[var(--color-panel)] hover:border-[var(--color-line-2)]'}`}>
                <div className="flex items-center gap-2">
                  <span className={`mono text-[8.5px] px-1.5 py-0.5 rounded-full uppercase tracking-wide ${statusPill(r.status)}`}>{STATUS_LABEL[r.status]}</span>
                  {r.awaiting_customer && <span className="mono text-[8.5px] px-1.5 py-0.5 rounded-full uppercase tracking-wide text-[var(--color-sky)] bg-[color-mix(in_oklab,var(--color-sky)_14%,transparent)]">Tellumen replied</span>}
                  {r.priority !== 'normal' && <span className="mono text-[9px] text-[var(--color-faint)] uppercase">{r.priority}</span>}
                  <span className="ml-auto text-[10.5px] text-[var(--color-faint)]">{ago(r.last_activity)}</span>
                </div>
                <div className="text-[13.5px] text-[var(--color-ink)] mt-1.5 leading-snug">{r.subject}</div>
                <div className="flex items-center gap-2 mt-1 text-[11px] text-[var(--color-faint)]">
                  <span>{CAT_LABEL[r.category]?.split(' — ')[0] ?? r.category}</span>
                  {r.message_count > 0 && <span className="inline-flex items-center gap-1"><MessageSquare size={11} /> {r.message_count}</span>}
                </div>
              </button>
            ))}
        </div>

        {/* detail / compose */}
        <div>
          {composing ? <Compose onDone={(id) => { setComposing(false); refresh(); if (id) setSel(id) }} />
            : sel ? <Thread id={sel} onChanged={refresh} />
            : <Card className="p-10 text-center text-[var(--color-faint)] text-sm">Select a request, or raise a new one.</Card>}
        </div>
      </div>
    </div>
  )
}

function Compose({ onDone }: { onDone: (id?: string) => void }) {
  const [category, setCategory] = useState('question')
  const [subject, setSubject] = useState('')
  const [priority, setPriority] = useState('normal')
  const [body, setBody] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async () => {
    if (subject.trim().length < 3) { alert('Give the request a short subject.'); return }
    setBusy(true)
    try {
      const res = await api.post<{ id: string }>('/v1/portal/requests', { category, subject: subject.trim(), priority, body: body.trim() || undefined })
      onDone(res.id)
    } catch (e) { alert((e as { body?: { message?: string } })?.body?.message || 'Could not raise the request.'); setBusy(false) }
  }

  return (
    <Card className="p-5 space-y-4">
      <div className="mono text-[10px] uppercase tracking-widest text-[var(--color-faint)]">New request</div>
      <div className="grid sm:grid-cols-2 gap-3">
        <label className="block">
          <span className="text-[11.5px] text-[var(--color-mute)]">Type</span>
          <select value={category} onChange={e => setCategory(e.target.value)}
            className="mt-1 w-full bg-[var(--color-bg-2)] border border-[var(--color-line)] rounded-lg px-2.5 py-2 text-[13px] outline-none focus:border-[var(--color-sky)]">
            {CATEGORIES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </label>
        <label className="block">
          <span className="text-[11.5px] text-[var(--color-mute)]">Priority</span>
          <select value={priority} onChange={e => setPriority(e.target.value)}
            className="mt-1 w-full bg-[var(--color-bg-2)] border border-[var(--color-line)] rounded-lg px-2.5 py-2 text-[13px] outline-none focus:border-[var(--color-sky)] capitalize">
            {PRIORITIES.map(p => <option key={p} value={p}>{p}</option>)}
          </select>
        </label>
      </div>
      <label className="block">
        <span className="text-[11.5px] text-[var(--color-mute)]">Subject</span>
        <input value={subject} onChange={e => setSubject(e.target.value)} maxLength={200} placeholder="One line — what's the issue or question?"
          className="mt-1 w-full bg-[var(--color-bg-2)] border border-[var(--color-line)] rounded-lg px-3 py-2 text-[13.5px] outline-none focus:border-[var(--color-sky)]" />
      </label>
      <label className="block">
        <span className="text-[11.5px] text-[var(--color-mute)]">Details <span className="text-[var(--color-faint)]">(optional)</span></span>
        <textarea value={body} onChange={e => setBody(e.target.value)} rows={5} maxLength={4000} placeholder="What did you expect, what happened, where — a screen name or a figure helps us help you."
          className="mt-1 w-full bg-[var(--color-bg-2)] border border-[var(--color-line)] rounded-lg px-3 py-2 text-[13px] outline-none focus:border-[var(--color-sky)] resize-y" />
      </label>
      <div className="flex gap-2">
        <button disabled={busy} onClick={submit}
          className="inline-flex items-center gap-1.5 rounded-lg px-3.5 py-2 text-[13px] font-medium bg-[var(--color-sky)] text-[#0b1206] hover:opacity-90 disabled:opacity-40">
          <Send size={14} /> {busy ? 'Sending…' : 'Send to Tellumen'}
        </button>
        <button disabled={busy} onClick={() => onDone()} className="rounded-lg px-3.5 py-2 text-[13px] text-[var(--color-mute)] hover:text-[var(--color-ink)] border border-[var(--color-line-2)]">Cancel</button>
      </div>
    </Card>
  )
}

function Thread({ id, onChanged }: { id: string; onChanged: () => void }) {
  const qc = useQueryClient()
  const { profile } = useAuth()
  const q = useQuery({ queryKey: ['portal-request', id], queryFn: () => api.get<SDetail>(`/v1/portal/requests/${id}`) })
  const [reply, setReply] = useState('')
  const [busy, setBusy] = useState(false)

  const refetchAll = () => { q.refetch(); qc.invalidateQueries({ queryKey: ['portal-requests'] }); onChanged() }

  const send = async () => {
    if (!reply.trim()) return
    setBusy(true)
    try { await api.post(`/v1/portal/requests/${id}/messages`, { body: reply.trim() }); setReply(''); refetchAll() }
    catch (e) { alert((e as { body?: { message?: string } })?.body?.message || 'Could not send.') }
    finally { setBusy(false) }
  }
  const setStatus = async (status: string) => {
    setBusy(true)
    try { await api.patch(`/v1/portal/requests/${id}`, { status }); refetchAll() }
    catch { alert('Could not update status.') }
    finally { setBusy(false) }
  }

  if (!q.data) return <Card className="p-8 text-center text-[var(--color-faint)] text-sm">loading…</Card>
  const { request: r, messages } = q.data
  const myEmail = profile?.user?.email

  return (
    <Card className="p-5 space-y-4">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <div className="flex items-center gap-2">
            <span className={`mono text-[9px] px-2 py-0.5 rounded-full uppercase tracking-wide ${statusPill(r.status)}`}>{STATUS_LABEL[r.status]}</span>
            <span className="mono text-[10px] text-[var(--color-faint)] uppercase">{CAT_LABEL[r.category]?.split(' — ')[0] ?? r.category}</span>
            {r.priority !== 'normal' && <span className="mono text-[10px] text-[var(--color-faint)] uppercase">· {r.priority}</span>}
          </div>
          <h2 className="text-[17px] font-semibold mt-1.5 leading-snug">{r.subject}</h2>
          <div className="text-[11px] text-[var(--color-faint)] mt-1">
            raised by {r.requester_email ?? '—'} · {ago(r.created_at)}
            {r.first_response_at && <> · first reply {ago(r.first_response_at)}</>}
          </div>
        </div>
        {r.status !== 'resolved'
          ? <button disabled={busy} onClick={() => setStatus('resolved')} className="inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[12px] font-medium border border-[var(--color-line-2)] text-[var(--color-good)] hover:border-[var(--color-good)] disabled:opacity-40 shrink-0"><CheckCircle2 size={14} /> Mark resolved</button>
          : <button disabled={busy} onClick={() => setStatus('open')} className="inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[12px] font-medium border border-[var(--color-line-2)] text-[var(--color-mute)] hover:text-[var(--color-ink)] disabled:opacity-40 shrink-0"><RotateCcw size={14} /> Reopen</button>}
      </div>

      {/* original body as the first bubble, then the thread */}
      <div className="space-y-3 border-t border-[var(--color-line)] pt-4">
        {r.body && <Bubble side="customer" who={r.requester_email ?? 'You'} when={r.created_at} body={r.body} mine={r.requester_email === myEmail} />}
        {messages.map(m => (
          <Bubble key={m.id} side={m.author_side}
            who={m.author_side === 'support' ? (m.author_name || 'Tellumen support') : (m.author_email ?? 'You')}
            when={m.created_at} body={m.body} mine={m.author_side === 'customer' && m.author_email === myEmail} />
        ))}
        {!r.body && messages.length === 0 && <div className="text-[12.5px] text-[var(--color-faint)]">No messages yet — add detail below and we'll respond.</div>}
      </div>

      {/* reply box */}
      <div className="border-t border-[var(--color-line)] pt-4">
        <textarea value={reply} onChange={e => setReply(e.target.value)} rows={3} maxLength={4000}
          placeholder={r.status === 'resolved' ? 'Reply to reopen this request…' : 'Reply to Tellumen…'}
          className="w-full bg-[var(--color-bg-2)] border border-[var(--color-line)] rounded-lg px-3 py-2 text-[13px] outline-none focus:border-[var(--color-sky)] resize-y" />
        <div className="flex justify-end mt-2">
          <button disabled={busy || !reply.trim()} onClick={send}
            className="inline-flex items-center gap-1.5 rounded-lg px-3.5 py-2 text-[13px] font-medium bg-[var(--color-sky)] text-[#0b1206] hover:opacity-90 disabled:opacity-40">
            <Send size={14} /> Send reply
          </button>
        </div>
      </div>
    </Card>
  )
}

function Bubble({ side, who, when, body, mine }: { side: 'customer' | 'support'; who: string; when: string | null; body: string; mine: boolean }) {
  const isSupport = side === 'support'
  return (
    <div className={`flex ${isSupport ? 'justify-start' : 'justify-end'}`}>
      <div className={`max-w-[85%] rounded-xl px-3.5 py-2.5 ${isSupport
        ? 'bg-[color-mix(in_oklab,var(--color-sky)_10%,var(--color-bg-2))] border border-[color-mix(in_oklab,var(--color-sky)_28%,var(--color-line))]'
        : 'bg-[var(--color-panel-2)] border border-[var(--color-line)]'}`}>
        <div className="flex items-center gap-2 mb-1">
          <span className={`mono text-[9px] uppercase tracking-wide ${isSupport ? 'text-[var(--color-sky)]' : 'text-[var(--color-faint)]'}`}>{isSupport ? 'Tellumen' : (mine ? 'You' : who)}</span>
          <span className="text-[10px] text-[var(--color-faint)]">{ago(when)}</span>
        </div>
        <div className="text-[13px] text-[var(--color-ink)] whitespace-pre-wrap leading-relaxed">{body}</div>
      </div>
    </div>
  )
}
