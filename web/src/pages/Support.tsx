import { useMemo, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { LifeBuoy, Plus, Send, CheckCircle2, RotateCcw, MessageSquare, Search, Clock, AlertTriangle, Sparkles, BookOpen, ChevronRight, LayoutDashboard, Ticket } from 'lucide-react'
import { api } from '../lib/api'
import { toast } from '../lib/toast'
import { useAuth } from '../lib/auth'
import { Eyebrow, Card } from '../components/ui'
import { DOCS } from '../content/docs'

// Support Center — one place to find an answer, raise a ticket, and watch its SLA count down. The dashboard
// summarises open / at-risk / breached / resolved; the SLA clock is computed from priority + when it was
// raised. "Ask" and "Documentation" search the in-app guides directly (no LLM) — a human ticket is one click
// away when a guide isn't enough. Ticket data is the existing /v1/portal service-request thread.

interface SReq {
  id: string; category: string; subject: string; body: string | null; priority: string; status: string
  requester_email: string | null; message_count: number; awaiting_customer: boolean
  created_at: string | null; updated_at: string | null; first_response_at: string | null
  resolved_at: string | null; last_activity: string | null
}
interface SMsg { id: string; author_side: 'customer' | 'support'; author_email: string | null; author_name: string | null; body: string; created_at: string | null }
interface SDetail { request: SReq; messages: SMsg[] }
type Tab = 'dashboard' | 'file' | 'tickets' | 'docs' | 'ask'

const CATEGORIES: [string, string][] = [
  ['question', 'Question — how does it work?'], ['bug', 'Bug — something is wrong / incorrect'],
  ['data', 'Data — a feed or figure looks off'], ['report', 'Report / filing help'],
  ['onboarding', 'Onboarding / setup'], ['other', 'Something else'],
]
const CAT_LABEL: Record<string, string> = Object.fromEntries(CATEGORIES)
const PRIORITIES = ['low', 'normal', 'high', 'urgent']

// SLA target hours per priority, and the target table shown on the dashboard (Cerivio-parity labels).
const SLA_HOURS: Record<string, number> = { urgent: 4, high: 24, normal: 72, low: 168 }
const SLA_TARGETS: [string, string][] = [['Critical', '4 hours'], ['High', '24 hours'], ['Medium', '72 hours'], ['Low', '7 days']]

type SlaState = 'ok' | 'risk' | 'breached' | 'done'
function sla(r: SReq): { state: SlaState; hoursLeft: number | null } {
  if (r.status === 'resolved') return { state: 'done', hoursLeft: null }
  if (!r.created_at) return { state: 'ok', hoursLeft: null }
  const deadline = new Date(r.created_at).getTime() + (SLA_HOURS[r.priority] ?? 72) * 3600000
  const hoursLeft = (deadline - Date.now()) / 3600000
  return { state: hoursLeft < 0 ? 'breached' : hoursLeft < 2 ? 'risk' : 'ok', hoursLeft }
}
const slaLabel = (r: SReq) => {
  const s = sla(r)
  if (s.state === 'done' || s.hoursLeft == null) return null
  if (s.state === 'breached') return { text: `SLA breached ${fmtDur(-s.hoursLeft)} ago`, tone: 'var(--color-bad)' }
  if (s.state === 'risk') return { text: `SLA in ${fmtDur(s.hoursLeft)}`, tone: 'var(--color-warn)' }
  return { text: `SLA in ${fmtDur(s.hoursLeft)}`, tone: 'var(--color-faint)' }
}
const fmtDur = (h: number) => h >= 24 ? `${Math.floor(h / 24)}d` : h >= 1 ? `${Math.floor(h)}h` : `${Math.max(1, Math.round(h * 60))}m`

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
  const { profile } = useAuth()
  const [tab, setTab] = useState<Tab>('dashboard')
  const [sel, setSel] = useState<string | null>(null)
  const list = useQuery({ queryKey: ['portal-requests'], queryFn: () => api.get<SReq[]>('/v1/portal/requests') })
  const rows = list.data ?? []
  const refresh = () => qc.invalidateQueries({ queryKey: ['portal-requests'] })

  const open = rows.filter(r => r.status !== 'resolved').length
  const atRisk = rows.filter(r => sla(r).state === 'risk').length
  const breached = rows.filter(r => sla(r).state === 'breached').length
  const resolved = rows.filter(r => r.status === 'resolved').length
  const guides = useMemo(() => DOCS.filter(d => !d.sectors || d.sectors.includes(profile?.org?.type ?? '')), [profile])

  const TABS: [Tab, string, typeof LifeBuoy][] = [
    ['dashboard', 'Dashboard', LayoutDashboard], ['file', 'File a ticket', Plus],
    ['tickets', 'My tickets', Ticket], ['docs', 'Documentation', BookOpen], ['ask', 'Ask Tellumen', Sparkles],
  ]

  return (
    <div className="fadeup space-y-5">
      <div>
        <Eyebrow>Support · with Tellumen</Eyebrow>
        <h1 className="display text-3xl font-semibold mt-2 mb-1">Support Center</h1>
        <p className="text-[var(--color-mute)] text-sm">Documentation · file a ticket · track your requests · SLA countdown.</p>
      </div>

      {/* tab bar */}
      <div className="flex flex-wrap gap-1 border-b border-[var(--color-line)]">
        {TABS.map(([t, label, Icon]) => (
          <button key={t} onClick={() => setTab(t)}
            className={`inline-flex items-center gap-1.5 px-3.5 py-2.5 text-[13.5px] border-b-2 -mb-px transition ${tab === t
              ? 'border-[var(--stage,var(--color-sky))] text-[var(--color-ink)] font-medium'
              : 'border-transparent text-[var(--color-mute)] hover:text-[var(--color-ink)]'}`}>
            <Icon size={15} /> {label}
            {t === 'tickets' && open > 0 && <span className="mono text-[10px] px-1.5 py-0.5 rounded-full bg-[var(--color-panel-2)] text-[var(--color-mute)]">{open}</span>}
          </button>
        ))}
      </div>

      {tab === 'dashboard' && (
        <div className="space-y-5">
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <Tile label="Open" n={open} tone="var(--color-ink)" onClick={() => setTab('tickets')} />
            <Tile label="At risk (<2h left)" n={atRisk} tone="var(--color-warn)" ring={atRisk > 0} onClick={() => setTab('tickets')} />
            <Tile label="SLA breached" n={breached} tone="var(--color-bad)" ring={breached > 0} onClick={() => setTab('tickets')} />
            <Tile label="Resolved · lifetime" n={resolved} tone="var(--color-good)" />
          </div>
          <div className="grid lg:grid-cols-2 gap-4">
            <Card className="p-5">
              <div className="text-[15px] font-semibold mb-1.5">Get help fast</div>
              <p className="text-[13px] text-[var(--color-mute)] leading-relaxed mb-4">Search {guides.length} how-to guides · file a ticket if you need a human · track SLAs on tickets you already filed.</p>
              <div className="flex flex-wrap gap-2">
                <button onClick={() => setTab('ask')} className="inline-flex items-center gap-1.5 rounded-lg px-3.5 py-2 text-[13px] font-medium bg-[var(--color-good)] text-white hover:opacity-90"><Sparkles size={15} /> Ask Tellumen</button>
                <button onClick={() => setTab('file')} className="inline-flex items-center gap-1.5 rounded-lg px-3.5 py-2 text-[13px] font-medium border border-[var(--color-line-2)] text-[var(--color-mute)] hover:text-[var(--color-ink)] hover:border-[var(--color-sky)]"><Plus size={15} /> New ticket</button>
              </div>
            </Card>
            <Card className="p-5">
              <div className="text-[15px] font-semibold mb-3">SLA targets</div>
              <div className="space-y-2">
                {SLA_TARGETS.map(([p, t]) => (
                  <div key={p} className="flex items-center justify-between text-[13.5px] border-b border-[var(--color-line)] last:border-0 pb-2 last:pb-0">
                    <span className="text-[var(--color-mute)]">{p}</span><span className="font-medium tabular-nums">{t}</span>
                  </div>
                ))}
              </div>
              <p className="mono text-[10px] text-[var(--color-faint)] mt-3">first-response target, from when a ticket is raised · by its priority</p>
            </Card>
          </div>
        </div>
      )}

      {tab === 'file' && <div className="max-w-2xl"><Compose onDone={id => { refresh(); if (id) { setSel(id); setTab('tickets') } else setTab('dashboard') }} /></div>}

      {tab === 'tickets' && (
        <div className="grid lg:grid-cols-[minmax(0,360px)_1fr] gap-5 items-start">
          <div className="space-y-2">
            {list.isLoading ? <Card className="p-6 text-center text-[var(--color-faint)] text-sm">loading…</Card>
              : rows.length === 0 ? (
                <Card className="p-8 text-center text-[var(--color-faint)] text-sm flex flex-col items-center gap-2">
                  <LifeBuoy size={22} /> No tickets yet. <button onClick={() => setTab('file')} className="text-[var(--color-sky)] hover:underline">File one</button> and we'll pick it up.
                </Card>
              ) : rows.map(r => {
                const sl = slaLabel(r)
                return (
                  <button key={r.id} onClick={() => setSel(r.id)}
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
                      {sl && <span className="ml-auto inline-flex items-center gap-1" style={{ color: sl.tone }}><Clock size={10} /> {sl.text}</span>}
                    </div>
                  </button>
                )
              })}
          </div>
          <div>
            {sel ? <Thread id={sel} onChanged={refresh} /> : <Card className="p-10 text-center text-[var(--color-faint)] text-sm">Select a ticket to see the conversation and its SLA.</Card>}
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
      <div className="mono text-[9.5px] tracking-wide uppercase text-[var(--color-faint)] mt-2">{label}</div>
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
          placeholder={mode === 'ask' ? 'Ask a question — e.g. how do I file a TCFD report?' : 'Search the help guides…'}
          className="w-full bg-[var(--color-bg-2)] border border-[var(--color-line)] rounded-lg pl-9 pr-3 py-2.5 text-[13.5px] outline-none focus:border-[var(--color-sky)]" />
      </div>
      {mode === 'ask' && !s && <p className="text-[13px] text-[var(--color-mute)]">Type your question and we'll surface the matching how-to guides instantly — no waiting. Still stuck? <button onClick={onFile} className="text-[var(--color-sky)] hover:underline">File a ticket</button>.</p>}
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

function Compose({ onDone }: { onDone: (id?: string) => void }) {
  const [category, setCategory] = useState('question')
  const [subject, setSubject] = useState('')
  const [priority, setPriority] = useState('normal')
  const [body, setBody] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async () => {
    if (subject.trim().length < 3) { toast.error('Give the ticket a short subject.'); return }
    setBusy(true)
    try {
      const res = await api.post<{ id: string }>('/v1/portal/requests', { category, subject: subject.trim(), priority, body: body.trim() || undefined })
      toast.success('Ticket filed — we’ll respond within its SLA.')
      onDone(res.id)
    } catch (e) { toast.error((e as { body?: { message?: string } })?.body?.message || 'Could not file the ticket.'); setBusy(false) }
  }

  return (
    <Card className="p-5 space-y-4">
      <div className="mono text-[10px] uppercase tracking-widest text-[var(--color-faint)]">New ticket</div>
      <div className="grid sm:grid-cols-2 gap-3">
        <label className="block">
          <span className="text-[11.5px] text-[var(--color-mute)]">Type</span>
          <select value={category} onChange={e => setCategory(e.target.value)}
            className="mt-1 w-full bg-[var(--color-bg-2)] border border-[var(--color-line)] rounded-lg px-2.5 py-2 text-[13px] outline-none focus:border-[var(--color-sky)]">
            {CATEGORIES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </label>
        <label className="block">
          <span className="text-[11.5px] text-[var(--color-mute)]">Priority <span className="text-[var(--color-faint)]">· sets the SLA</span></span>
          <select value={priority} onChange={e => setPriority(e.target.value)}
            className="mt-1 w-full bg-[var(--color-bg-2)] border border-[var(--color-line)] rounded-lg px-2.5 py-2 text-[13px] outline-none focus:border-[var(--color-sky)] capitalize">
            {PRIORITIES.map(p => <option key={p} value={p}>{p} · {fmtDur(SLA_HOURS[p])} SLA</option>)}
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
    catch (e) { toast.error((e as { body?: { message?: string } })?.body?.message || 'Could not send.') }
    finally { setBusy(false) }
  }
  const setStatus = async (status: string) => {
    setBusy(true)
    try { await api.patch(`/v1/portal/requests/${id}`, { status }); refetchAll() }
    catch { toast.error('Could not update status.') }
    finally { setBusy(false) }
  }

  if (!q.data) return <Card className="p-8 text-center text-[var(--color-faint)] text-sm">loading…</Card>
  const { request: r, messages } = q.data
  const myEmail = profile?.user?.email
  const sl = slaLabel(r)

  return (
    <Card className="p-5 space-y-4">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <div className="flex items-center gap-2 flex-wrap">
            <span className={`mono text-[9px] px-2 py-0.5 rounded-full uppercase tracking-wide ${statusPill(r.status)}`}>{STATUS_LABEL[r.status]}</span>
            <span className="mono text-[10px] text-[var(--color-faint)] uppercase">{CAT_LABEL[r.category]?.split(' — ')[0] ?? r.category}</span>
            {r.priority !== 'normal' && <span className="mono text-[10px] text-[var(--color-faint)] uppercase">· {r.priority}</span>}
            {sl && <span className="mono text-[10px] inline-flex items-center gap-1" style={{ color: sl.tone }}>{sl.tone === 'var(--color-bad)' ? <AlertTriangle size={11} /> : <Clock size={11} />} {sl.text}</span>}
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
        {!r.body && messages.length === 0 && <div className="text-[12.5px] text-[var(--color-faint)]">No messages yet — add detail below and we'll respond.</div>}
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
