import { useMemo, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { LifeBuoy, Plus, Send, CheckCircle2, RotateCcw, MessageSquare, Search, Clock, AlertTriangle, Sparkles, BookOpen, ChevronRight, LayoutDashboard, Ticket } from 'lucide-react'
import { api, apiMessage } from '../lib/api'
import { toast } from '../lib/toast'
import { useAuth } from '../lib/auth'
import { Card, PageHeader } from '../components/ui'
import { HEADING, InfoButton } from '../components/Details'
import { StatusChip } from '../components/StatusChip'
import { DOCS } from '../content/docs'
import SectionTabs, { HELP_TABS } from '../components/SectionTabs'
import { CATEGORIES, PRIORITIES, RISK_HOURS, categoryName, clock, clockWords, duration, priority, statusOf } from './support/words'

// Support Center — one place to find an answer, raise a ticket and follow it. The dashboard counts open tickets, those
// whose first reply is due soon or overdue, and those resolved; the clock runs from when a ticket is raised to its
// first reply, by priority (support/words.ts). "Ask a question" and "Documentation" search the in-app guides directly
// — a ticket for our team is one click away when a guide isn't enough. Ticket data is the /v1/portal request thread.

interface SReq {
  id: string; category: string; subject: string; body: string | null; priority: string; status: string
  requester_email: string | null; message_count: number; awaiting_customer: boolean
  created_at: string | null; updated_at: string | null; first_response_at: string | null
  resolved_at: string | null; last_activity: string | null
}
interface SMsg { id: string; author_side: 'customer' | 'support'; author_email: string | null; author_name: string | null; body: string; created_at: string | null }
interface SDetail { request: SReq; messages: SMsg[] }
type Tab = 'dashboard' | 'file' | 'tickets' | 'docs' | 'ask'

const ABOUT = [
  { heading: HEADING.shows, body: 'Your organisation’s tickets with our team, the guides, and how long a first reply should take.' },
  { heading: HEADING.read, body: 'Each ticket’s clock runs from when it is raised until our first reply, against the target for its priority. A ticket stays open until you or we mark it resolved.' },
]
const TARGETS = {
  title: 'Reply targets', sections: [
    { heading: HEADING.shows, body: 'The time we aim to give a first reply in, from when a ticket is raised, by the priority you choose.' },
    { heading: HEADING.read, body: `A ticket whose first reply is due within ${duration(RISK_HOURS)} is counted as due soon.` },
  ],
}
const Chip = ({ r }: { r: SReq }) => { const s = statusOf(r.status); return <StatusChip label={s.name} tone={s.tone} /> }

const ago = (iso: string | null) => {
  if (!iso) return ''
  const d = (Date.now() - new Date(iso).getTime()) / 86400000
  return d < 0.04 ? 'just now' : d < 1 ? 'today' : d < 2 ? 'yesterday' : `${Math.floor(d)}d ago`
}

export default function Support() {
  const qc = useQueryClient()
  const { profile } = useAuth()
  const [params] = useSearchParams()
  const preset = params.get('subject') ?? ''             // a link elsewhere (e.g. Billing → Enterprise) opens a new ticket
  const [tab, setTab] = useState<Tab>(preset ? 'file' : 'dashboard')
  const [sel, setSel] = useState<string | null>(null)
  const list = useQuery({ queryKey: ['portal-requests'], queryFn: () => api.get<SReq[]>('/v1/portal/requests') })
  const rows = list.data ?? []
  const refresh = () => qc.invalidateQueries({ queryKey: ['portal-requests'] })

  const open = rows.filter(r => r.status !== 'resolved').length
  const atRisk = rows.filter(r => clock(r).state === 'risk').length
  const breached = rows.filter(r => clock(r).state === 'breached').length
  const resolved = rows.filter(r => r.status === 'resolved').length
  const guides = useMemo(() => DOCS.filter(d => !d.sectors || d.sectors.includes(profile?.org?.type ?? '')), [profile])

  const TABS: [Tab, string, typeof LifeBuoy][] = [
    ['dashboard', 'Dashboard', LayoutDashboard], ['file', 'File a ticket', Plus],
    ['tickets', 'My tickets', Ticket], ['docs', 'Documentation', BookOpen], ['ask', 'Ask a question', Sparkles],
  ]

  return (
    <div className="fadeup space-y-5">
      <SectionTabs tabs={HELP_TABS} />
      <PageHeader eyebrow="Help" title="Support Center" lead="Find an answer, or raise a ticket and follow it." about={ABOUT} />

      {/* tab bar */}
      <div className="flex flex-wrap gap-1 border-b border-[var(--color-line)]">
        {TABS.map(([t, label, Icon]) => (
          <button key={t} onClick={() => setTab(t)}
            className={`inline-flex items-center gap-1.5 px-3.5 py-2.5 text-[13.5px] border-b-2 -mb-px transition ${tab === t
              ? 'border-[var(--stage,var(--color-sky))] text-[var(--color-ink)] font-medium'
              : 'border-transparent text-[var(--color-mute)] hover:text-[var(--color-ink)]'}`}>
            <Icon size={15} /> {label}
            {t === 'tickets' && open > 0 && <span className="text-[10.5px] px-1.5 py-0.5 rounded-full bg-[var(--color-panel-2)] text-[var(--color-mute)] tabular-nums">{open}</span>}
          </button>
        ))}
      </div>

      {tab === 'dashboard' && (
        <div className="space-y-5">
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <Tile label="Open" n={open} tone="var(--color-ink)" onClick={() => setTab('tickets')} />
            <Tile label="Reply due soon" n={atRisk} tone="var(--color-warn)" ring={atRisk > 0} onClick={() => setTab('tickets')} />
            <Tile label="Reply overdue" n={breached} tone="var(--color-bad)" ring={breached > 0} onClick={() => setTab('tickets')} />
            <Tile label="Resolved" n={resolved} tone="var(--color-good)" />
          </div>
          <div className="grid lg:grid-cols-2 gap-4">
            <Card className="p-5">
              <div className="text-[15px] font-semibold mb-1.5">Get help fast</div>
              <p className="text-[13px] text-[var(--color-mute)] leading-relaxed mb-4">Search the guides, or raise a ticket for our team.</p>
              <div className="flex flex-wrap gap-2">
                <button onClick={() => setTab('ask')} className="inline-flex items-center gap-1.5 rounded-lg px-3.5 py-2 text-[13px] font-medium bg-[var(--color-good)] text-white hover:opacity-90"><Sparkles size={15} /> Ask a question</button>
                <button onClick={() => setTab('file')} className="inline-flex items-center gap-1.5 rounded-lg px-3.5 py-2 text-[13px] font-medium border border-[var(--color-line-2)] text-[var(--color-mute)] hover:text-[var(--color-ink)] hover:border-[var(--color-sky)]"><Plus size={15} /> New ticket</button>
              </div>
            </Card>
            <Card className="p-5">
              <div className="text-[15px] font-semibold mb-3 inline-flex items-center gap-1.5">Reply targets <InfoButton compact details={TARGETS} /></div>
              <div className="space-y-2">
                {[...PRIORITIES].reverse().map(p => (
                  <div key={p.key} className="flex items-center gap-3 text-[13.5px] border-b border-[var(--color-line)] last:border-0 pb-2 last:pb-0">
                    <span className="w-16 text-[var(--color-mute)]">{p.name}</span>
                    <span className="flex-1 h-1.5 rounded-full bg-[var(--color-panel-2)] overflow-hidden">
                      <span className="block h-full rounded-full bg-[var(--color-sky)]" style={{ width: `${Math.max(4, (Math.log(p.hours) / Math.log(PRIORITIES[0].hours)) * 100)}%` }} />
                    </span>
                    <span className="font-medium tabular-nums w-20 text-right">{duration(p.hours)}</span>
                  </div>
                ))}
              </div>
            </Card>
          </div>
        </div>
      )}

      {tab === 'file' && <div className="max-w-2xl"><Compose subject={preset} onDone={id => { refresh(); if (id) { setSel(id); setTab('tickets') } else setTab('dashboard') }} /></div>}

      {tab === 'tickets' && (
        <div className="grid lg:grid-cols-[minmax(0,360px)_1fr] gap-5 items-start">
          <div className="space-y-2">
            {list.isLoading ? <Card className="p-6 text-center text-[var(--color-faint)] text-sm">Loading…</Card>
              : rows.length === 0 ? (
                <Card className="p-8 text-center text-[var(--color-faint)] text-sm flex flex-col items-center gap-2">
                  <LifeBuoy size={22} /> No tickets yet. <button onClick={() => setTab('file')} className="text-[var(--color-sky)] hover:underline">File one</button> and we'll pick it up.
                </Card>
              ) : rows.map(r => {
                const sl = clockWords(clock(r))
                return (
                  <button key={r.id} onClick={() => setSel(r.id)}
                    className={`w-full text-left rounded-xl border p-3.5 transition ${sel === r.id
                      ? 'border-[var(--color-sky)] bg-[var(--color-panel-2)]'
                      : 'border-[var(--color-line)] bg-[var(--color-panel)] hover:border-[var(--color-line-2)]'}`}>
                    <div className="flex flex-wrap items-center gap-1.5">
                      <Chip r={r} />
                      {r.awaiting_customer && <StatusChip label="Tellumen replied" tone="good" />}
                      {r.priority !== 'normal' && <StatusChip label={priority(r.priority).name} tone={r.priority === 'low' ? 'neutral' : 'warn'} />}
                      <span className="ml-auto text-[10.5px] text-[var(--color-faint)]">{ago(r.last_activity)}</span>
                    </div>
                    <div className="text-[13.5px] text-[var(--color-ink)] mt-1.5 leading-snug">{r.subject}</div>
                    <div className="flex items-center gap-2 mt-1 text-[11px] text-[var(--color-faint)]">
                      <span>{categoryName(r.category)}</span>
                      {r.message_count > 0 && <span className="inline-flex items-center gap-1"><MessageSquare size={11} /> {r.message_count}</span>}
                      {sl && <span className="ml-auto inline-flex items-center gap-1" style={{ color: sl.tone }}><Clock size={10} /> {sl.text}</span>}
                    </div>
                  </button>
                )
              })}
          </div>
          <div>
            {sel ? <Thread id={sel} onChanged={refresh} /> : <Card className="p-10 text-center text-[var(--color-faint)] text-sm">Select a ticket to see the conversation.</Card>}
          </div>
        </div>
      )}

      {tab === 'docs' && <DocSearch guides={guides} mode="browse" onFile={() => setTab('file')} />}
      {tab === 'ask' && <DocSearch guides={guides} mode="ask" onFile={() => setTab('file')} />}
    </div>
  )
}

function Tile({ label, n, tone, ring, onClick }: { label: string; n: number; tone: string; ring?: boolean; onClick?: () => void }) {
  const Comp = onClick ? 'button' : 'div'
  return (
    <Comp onClick={onClick} className={`text-left px-4 py-3.5 rounded-xl border transition ${ring ? '' : 'border-[var(--color-line)]'} ${onClick ? 'hover:border-[var(--color-line-2)]' : ''} bg-[var(--color-panel)]`}
      style={ring ? { borderColor: `color-mix(in oklab, ${tone} 45%, transparent)`, background: `color-mix(in oklab, ${tone} 7%, var(--color-panel))` } : undefined}>
      <div className="display text-[30px] leading-none tabular-nums" style={{ color: tone }}>{n}</div>
      <div className="text-[12px] text-[var(--color-mute)] mt-2">{label}</div>
    </Comp>
  )
}

function DocSearch({ guides, mode, onFile }: { guides: typeof DOCS; mode: 'browse' | 'ask'; onFile: () => void }) {
  const nav = useNavigate()
  const [q, setQ] = useState('')
  const s = q.trim().toLowerCase()
  const hits = useMemo(() => !s ? (mode === 'ask' ? [] : guides)
    : guides.filter(d => (d.title + ' ' + d.summary + ' ' + d.body).toLowerCase().includes(s)), [s, guides, mode])
  return (
    <div className="max-w-2xl space-y-4">
      <div className="relative">
        <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--color-faint)]" />
        <input autoFocus value={q} onChange={e => setQ(e.target.value)}
          placeholder={mode === 'ask' ? 'Ask a question — e.g. how do I file a Pillar 3 report?' : 'Search the help guides…'}
          className="w-full bg-[var(--color-bg-2)] border border-[var(--color-line)] rounded-lg pl-9 pr-3 py-2.5 text-[13.5px] outline-none focus:border-[var(--color-sky)]" />
      </div>
      {mode === 'ask' && !s && <p className="text-[13px] text-[var(--color-mute)]">Type a question to see the matching guides. Still stuck? <button onClick={onFile} className="text-[var(--color-sky)] hover:underline">File a ticket</button>.</p>}
      {s && hits.length === 0 && (
        <Card className="p-6 text-[13px] text-[var(--color-mute)]">
          No guide matched “{q}”. <button onClick={onFile} className="text-[var(--color-sky)] hover:underline font-medium">File a ticket</button> and a human will help.
        </Card>
      )}
      <div className="space-y-2">
        {hits.slice(0, 12).map(d => (
          <button key={d.slug} onClick={() => nav(`/docs?doc=${d.slug}`)} className="w-full text-left rounded-xl border border-[var(--color-line)] bg-[var(--color-panel)] p-3.5 hover:border-[var(--color-line-2)] transition group">
            <div className="flex items-center gap-2">
              <BookOpen size={14} className="text-[var(--color-faint)] shrink-0" />
              <span className="text-[13.5px] text-[var(--color-ink)] font-medium">{d.title}</span>
              <ChevronRight size={14} className="ml-auto text-[var(--color-faint)] opacity-0 group-hover:opacity-100 transition" />
            </div>
            <div className="text-[12px] text-[var(--color-mute)] mt-1 leading-snug pl-6">{d.summary}</div>
          </button>
        ))}
      </div>
    </div>
  )
}

function Compose({ onDone, subject: initial = '' }: { onDone: (id?: string) => void; subject?: string }) {
  const [category, setCategory] = useState(initial ? 'other' : 'question')
  const [subject, setSubject] = useState(initial)
  const [prio, setPrio] = useState('normal')
  const [body, setBody] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async () => {
    if (subject.trim().length < 3) { toast.error('Give the ticket a short subject.'); return }
    setBusy(true)
    try {
      const res = await api.post<{ id: string }>('/v1/portal/requests', { category, subject: subject.trim(), priority: prio, body: body.trim() || undefined })
      toast.success(`Ticket filed — a first reply within ${duration(priority(prio).hours)}.`)
      onDone(res.id)
    } catch (e) { toast.error(apiMessage(e, 'Could not file the ticket.')); setBusy(false) }
  }

  return (
    <Card className="p-5 space-y-4">
      <div className="text-[15px] font-semibold">New ticket</div>
      <div className="grid sm:grid-cols-2 gap-3">
        <label className="block">
          <span className="text-[11.5px] text-[var(--color-mute)]">Type</span>
          <select value={category} onChange={e => setCategory(e.target.value)}
            className="mt-1 w-full bg-[var(--color-bg-2)] border border-[var(--color-line)] rounded-lg px-2.5 py-2 text-[13px] outline-none focus:border-[var(--color-sky)]">
            {CATEGORIES.map(c => <option key={c.key} value={c.key}>{c.choice}</option>)}
          </select>
        </label>
        <label className="block">
          <span className="text-[11.5px] text-[var(--color-mute)]">Priority</span>
          <select value={prio} onChange={e => setPrio(e.target.value)}
            className="mt-1 w-full bg-[var(--color-bg-2)] border border-[var(--color-line)] rounded-lg px-2.5 py-2 text-[13px] outline-none focus:border-[var(--color-sky)]">
            {PRIORITIES.map(p => <option key={p.key} value={p.key}>{p.name} · first reply within {duration(p.hours)}</option>)}
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
          <Send size={14} /> {busy ? 'Filing…' : 'File ticket'}
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
    catch (e) { toast.error(apiMessage(e, 'Could not send.')) }
    finally { setBusy(false) }
  }
  const setStatus = async (status: string) => {
    setBusy(true)
    try { await api.patch(`/v1/portal/requests/${id}`, { status }); refetchAll() }
    catch (e) { toast.error(apiMessage(e, 'Could not update the ticket.')) }
    finally { setBusy(false) }
  }

  if (!q.data) return <Card className="p-8 text-center text-[var(--color-faint)] text-sm">Loading…</Card>
  const { request: r, messages } = q.data
  const myEmail = profile?.user?.email
  const sl = clockWords(clock(r))

  return (
    <Card className="p-5 space-y-4">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <div className="flex items-center gap-2 flex-wrap">
            <Chip r={r} />
            <span className="text-[11.5px] text-[var(--color-faint)]">{categoryName(r.category)}</span>
            {r.priority !== 'normal' && <StatusChip label={priority(r.priority).name} tone={r.priority === 'low' ? 'neutral' : 'warn'} />}
            {sl && <span className="text-[11.5px] inline-flex items-center gap-1" style={{ color: sl.tone }}>{sl.tone === 'var(--color-bad)' ? <AlertTriangle size={11} /> : <Clock size={11} />} {sl.text}</span>}
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

      <div className="space-y-3 border-t border-[var(--color-line)] pt-4">
        {r.body && <Bubble side="customer" who={r.requester_email ?? 'You'} when={r.created_at} body={r.body} mine={r.requester_email === myEmail} />}
        {messages.map(m => (
          <Bubble key={m.id} side={m.author_side}
            who={m.author_side === 'support' ? (m.author_name || 'Tellumen support') : (m.author_email ?? 'You')}
            when={m.created_at} body={m.body} mine={m.author_side === 'customer' && m.author_email === myEmail} />
        ))}
        {!r.body && messages.length === 0 && <div className="text-[12.5px] text-[var(--color-faint)]">No messages yet. Add detail below and we will reply.</div>}
      </div>

      <div className="border-t border-[var(--color-line)] pt-4">
        <textarea value={reply} onChange={e => setReply(e.target.value)} rows={3} maxLength={4000}
          placeholder={r.status === 'resolved' ? 'Reply to reopen this ticket…' : 'Reply to Tellumen…'}
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
