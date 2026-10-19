import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, FileText, Plus, Send } from 'lucide-react'
import clsx from 'clsx'
import { api } from '../lib/api'
import { toast } from '../lib/toast'
import { useAuth } from '../lib/auth'
import { filingLink } from '../lib/links'
import { statusLabel } from '../lib/labels'
import { Button, Card, PageHeader, SectionHead, StatGrid } from '../components/ui'
import { HEADING, InfoButton, MessageLine, messageDetails, type Message } from '../components/Details'
import { StatusChip } from '../components/StatusChip'
import SectionTabs, { DATA_TABS } from '../components/SectionTabs'
import { refused } from './admin/parts'

// Transmission, to the UI standard (2026-10-16): sending attested filings to the authority through the channel its
// mandate prescribes, every transmission with its receipt, and one case per submission with its correspondence. The
// server names every report, status and channel detail (services/transmission/service.py) and words the platform's own
// thread entries; a person's message stays as written.

interface Msg { direction: 'outbound' | 'inbound'; author: string; body: string; words: Message | null; at: string }
interface CaseSummary { case_id: string; regulator: string; reference: string | null; stage: string; framework_name: string | null; period_label: string | null; n_messages: number }
interface CaseDetail extends CaseSummary { filing_id: string | null; messages: Msg[] }
const STAGES = ['ready', 'submitted', 'query', 'answered', 'closed']
const STAGE_LABEL: Record<string, string> = { ready: 'Ready to submit', submitted: 'Submitted', query: 'Authority’s query', answered: 'Answer given', closed: 'Closed' }
const ABOUT = [
  { heading: HEADING.shows, body: 'Sending your attested filings to the authority, each transmission with its receipt, and a case per submission holding the correspondence around it — from ready to submit through the authority’s queries to closed.' },
  { heading: HEADING.read, body: 'A channel with a green dot is ready. The prescribed channel is the one the reporting mandate names; where your supervisor is on the platform, its own channel delivers and receipts at once. A portal needs its sign-in details before anything is sent.' },
  { heading: HEADING.limits, body: 'Messages on a case are kept as written and never changed. Delivery outside the platform is recorded by the reference the authority gives you.' },
]

export default function Transmission() {
  const { profile } = useAuth()
  const qc = useQueryClient()
  const canAct = (profile?.permissions ?? []).includes('reports.publish')
  const q = useQuery({ queryKey: ['transmission-cases'], queryFn: () => api.get<{ cases: CaseSummary[] }>('/v1/transmission/cases') })
  const tx = useQuery({ queryKey: ['tx-sends'], queryFn: () => api.get<{ transmissions: Tx[] }>('/v1/transmission/sends'),
    refetchInterval: (s) => (s.state.data?.transmissions.some(t => t.worker_state) ? 3000 : false) })
  const [sel, setSel] = useState<string | null>(null)
  const [params] = useSearchParams()
  useEffect(() => { const c = params.get('case'); if (c) setSel(c) }, [params])   // a filing's link: /transmission?case=<id>
  const [opening, setOpening] = useState(false)
  const [reg, setReg] = useState('')
  const cases = q.data?.cases ?? []
  const active = sel ?? cases[0]?.case_id ?? null
  const refresh = () => qc.invalidateQueries({ queryKey: ['transmission-cases'] })
  const openCase = async () => {
    try { const c = await api.post<CaseDetail>('/v1/transmission/cases', { regulator: reg.trim() }); setReg(''); setOpening(false); refresh(); setSel(c.case_id) }
    catch (e) { refused(e, 'The case could not be opened.') }
  }
  const sends = tx.data?.transmissions ?? []
  const attention = sends.filter(t => t.worker_state === 'unavailable' || ['failed', 'rejected', 'awaiting_credentials', 'awaiting_receipt'].includes(t.status)).length

  return (
    <div className="fadeup space-y-5">
      <SectionTabs tabs={DATA_TABS} />
      <PageHeader eyebrow="Regulator communication" title="Transmission" lead="Your filings to the authority, and what it said back." about={ABOUT}
        actions={canAct && <Button variant="ghost" onClick={() => setOpening(o => !o)}><Plus size={14} /> Open a case</Button>} />
      <StatGrid cols={4} items={[
        { label: 'Cases open', value: cases.filter(c => c.stage !== 'closed').length },
        { label: 'Authority’s queries', value: cases.filter(c => c.stage === 'query').length, accent: cases.some(c => c.stage === 'query') ? 'var(--color-warn)' : undefined },
        { label: 'Receipted', value: sends.filter(t => t.status === 'acknowledged').length, accent: 'var(--color-good)' },
        { label: 'Need attention', value: attention, accent: attention ? 'var(--color-bad)' : 'var(--color-good)' },
      ]} />
      {opening && (
        <Card className="p-3 flex items-center gap-2">
          <input value={reg} onChange={e => setReg(e.target.value)} onKeyDown={e => e.key === 'Enter' && reg.trim() && openCase()} aria-label="Authority"
            placeholder="The authority, such as your national competent authority" className="flex-1 bg-transparent outline-none text-[14px]" />
          <Button variant="primary" onClick={openCase} disabled={!reg.trim()}>Open</Button>
        </Card>
      )}
      <SendPanel canAct={canAct} sends={sends} onSent={() => { refresh(); qc.invalidateQueries({ queryKey: ['tx-sends'] }) }} />
      <div className="grid lg:grid-cols-[300px_1fr] gap-5">
        <Card className="p-0 overflow-hidden self-start">
          <div className="px-4 py-3 border-b border-[var(--color-line)]"><SectionHead>Cases</SectionHead></div>
          {cases.length === 0 ? <div className="px-4 py-6 text-[13px] text-[var(--color-faint)]">No cases yet.</div> : (
            <ul className="m-0 p-0 list-none divide-y divide-[var(--color-line)]">
              {cases.map(c => (
                <li key={c.case_id}>
                  <button onClick={() => setSel(c.case_id)} aria-pressed={active === c.case_id} className={clsx('w-full text-left px-4 py-3 transition', active === c.case_id ? 'bg-[var(--color-panel)]' : 'hover:bg-[var(--color-panel)]')}>
                    <div className="text-[13px] text-[var(--color-ink)] truncate">{c.regulator}</div>
                    <div className="text-[11.5px] text-[var(--color-faint)]">{[c.framework_name, c.period_label, `${c.n_messages} messages`].filter(Boolean).join(' · ')}</div>
                    <div className="mt-1"><StatusChip tone={c.stage === 'closed' ? 'good' : c.stage === 'query' ? 'warn' : 'neutral'} label={STAGE_LABEL[c.stage]} /></div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Card>
        {active ? <CaseView caseId={active} canAct={canAct} onChanged={refresh} /> : <Card className="p-10 text-center text-[var(--color-faint)] text-sm">Select or open a case.</Card>}
      </div>
    </div>
  )
}

function CaseView({ caseId, canAct, onChanged }: { caseId: string; canAct: boolean; onChanged: () => void }) {
  const qc = useQueryClient()
  const { profile } = useAuth()
  const nav = useNavigate()
  // logging a reply needs the same permission the server asks for (asking for approval)
  const canMessage = (profile?.permissions ?? []).includes('approvals.create')
  const q = useQuery({ queryKey: ['transmission-case', caseId], queryFn: () => api.get<CaseDetail>(`/v1/transmission/cases/${caseId}`) })
  const [reply, setReply] = useState('')
  const d = q.data
  const reload = () => { qc.invalidateQueries({ queryKey: ['transmission-case', caseId] }); onChanged() }
  if (!d) return <Card className="p-10 text-center text-[var(--color-faint)] text-sm">Loading…</Card>
  const at = STAGES.indexOf(d.stage)
  const post = async () => {
    try { await api.post(`/v1/transmission/cases/${caseId}/message`, { direction: 'outbound', author: 'Us', body: reply.trim() }); setReply(''); reload() }
    catch (e) { refused(e, 'The reply could not be logged.') }
  }
  const advance = async (s: string) => { try { await api.post(`/v1/transmission/cases/${caseId}/stage`, { stage: s }); reload() } catch (e) { refused(e, 'The case could not be moved on.') } }
  return (
    <Card className="p-0 overflow-hidden flex flex-col">
      <div className="px-5 py-3 border-b border-[var(--color-line)] flex items-start justify-between gap-3">
        <div>
          <div className="text-[14px] text-[var(--color-ink)]">{d.regulator}</div>
          <div className="text-[12px] text-[var(--color-faint)]">{[d.framework_name, d.period_label, d.reference].filter(Boolean).join(' · ')}</div>
        </div>
        {d.filing_id && <button onClick={() => nav(filingLink(profile?.org?.type, d.filing_id!))} className="shrink-0 inline-flex items-center gap-1.5 text-[12.5px] text-[var(--color-sky)] hover:underline"><FileText size={13} /> Open the filing</button>}
      </div>
      <ol className="px-5 py-4 flex items-center gap-1 border-b border-[var(--color-line)] overflow-x-auto m-0 list-none" aria-label="Stages of the case">
        {STAGES.map((s, i) => (
          <li key={s} className="flex items-center gap-1 shrink-0">
            <div className="flex flex-col items-center gap-1">
              <div className="w-6 h-6 rounded-full flex items-center justify-center text-[10px] border"
                style={{ background: i < at ? 'color-mix(in oklab, var(--color-good) 15%, transparent)' : i === at ? 'color-mix(in oklab, var(--color-sky) 15%, transparent)' : 'var(--color-panel-2)',
                  color: i < at ? 'var(--color-good)' : i === at ? 'var(--color-sky)' : 'var(--color-faint)', borderColor: i < at ? 'var(--color-good)' : i === at ? 'var(--color-sky)' : 'var(--color-line)' }}>
                {i < at ? <CheckCircle2 size={12} /> : i + 1}
              </div>
              <span className="text-[11px] whitespace-nowrap" style={{ color: i === at ? 'var(--color-ink)' : 'var(--color-faint)' }}>{STAGE_LABEL[s]}</span>
            </div>
            {i < STAGES.length - 1 && <div className="w-8 h-px mb-4" style={{ background: i < at ? 'var(--color-good)' : 'var(--color-line)' }} />}
          </li>
        ))}
      </ol>
      <div className="px-5 py-4 space-y-2.5 flex-1 max-h-[360px] overflow-y-auto">
        {d.messages.map((m, i) => m.words
          ? <div key={i} className="flex justify-center"><MessageLine m={m.words} className="text-[11.5px] text-[var(--color-faint)]" /></div>
          : <div key={i} className={clsx('flex', m.direction === 'outbound' ? 'justify-end' : 'justify-start')}>
              <div className="max-w-[75%] rounded-xl px-3 py-2" style={{ background: m.direction === 'outbound' ? 'color-mix(in oklab, var(--color-sky) 12%, transparent)' : 'var(--color-panel-2)' }}>
                <div className="text-[11px] text-[var(--color-faint)] mb-0.5">{m.author} · {new Date(m.at).toLocaleString('en-GB', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })}</div>
                <div className="text-[12.5px] text-[var(--color-ink)] whitespace-pre-wrap">{m.body}</div>
              </div>
            </div>)}
      </div>
      <div className="px-5 py-3 border-t border-[var(--color-line)] space-y-2">
        {canMessage
          ? <div className="flex items-center gap-2">
              <input value={reply} onChange={e => setReply(e.target.value)} onKeyDown={e => e.key === 'Enter' && reply.trim() && post()} placeholder="Log a reply…" aria-label="Reply"
                className="flex-1 bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-3 py-2 text-[13px] outline-none focus:border-[var(--color-sky)]" />
              <Button variant="primary" onClick={post} disabled={!reply.trim()} className="px-3"><Send size={14} /></Button>
            </div>
          : <div className="text-[12px] text-[var(--color-faint)]">You can read this case. Logging a reply needs a role that can ask for approval.</div>}
        {canAct && at < STAGES.length - 1 && (
          <button onClick={() => advance(STAGES[at + 1])} className="text-[12.5px] text-[var(--color-sky)] hover:underline">Move to {STAGE_LABEL[STAGES[at + 1]]}</button>
        )}
      </div>
    </Card>
  )
}

// ── sending to the authority ─────────────────────────────────────────────────────────────────────────────────
interface Chan { channel_id: string; label: string; configured: boolean; missing_labels: string[]; prescribed: boolean }
interface ChanResp { on_tellumen: boolean; frameworks: { framework: string; name: string; channels: Chan[] }[] }
interface Filing { filing_id: string; framework: string; period_label: string; status: string; submission_ref: string | null }
interface Tx { transmission_id: string; framework_name: string | null; period_label: string; channel_label: string; format_label: string; status: string
  receipt_ref: string | null; receipt_at: string | null; created_at: string; attempts: number; worker_state: 'alive' | 'unavailable' | null; status_message: Message }
const TX_TONE: Record<string, 'good' | 'warn' | 'bad' | 'neutral'> = { acknowledged: 'good', sent: 'neutral', queued: 'neutral', awaiting_receipt: 'warn', awaiting_credentials: 'warn', rejected: 'bad', failed: 'bad' }
const SEND = {
  title: 'Send to the authority', sections: [
    { heading: HEADING.shows, body: 'For each report you file: the channels to its authority, the attested filings ready to send, and every transmission with its receipt.' },
    { heading: HEADING.read, body: 'Where your supervisor is on the platform, its channel delivers and receipts at once. A portal needs its sign-in details; a channel outside the platform is recorded by the reference the authority gives you.' },
  ],
}

function SendPanel({ canAct, sends, onSent }: { canAct: boolean; sends: Tx[]; onSent: () => void }) {
  const qc = useQueryClient()
  const ch = useQuery({ queryKey: ['tx-channels'], queryFn: () => api.get<ChanResp>('/v1/transmission/channels') })
  const fl = useQuery({ queryKey: ['filings-register'], queryFn: () => api.get<{ filings: Filing[] } | Filing[]>('/v1/filings') })
  const [pick, setPick] = useState<Record<string, string>>({})
  const [ref, setRef] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState(false)
  const filings = (Array.isArray(fl.data) ? fl.data : fl.data?.filings ?? []).filter(f => ['attested', 'submitted', 'accepted'].includes(f.status))
  const d = ch.data
  const nameOf = (fw: string) => d?.frameworks.find(x => x.framework === fw)?.name ?? 'A report'
  const send = async (f: Filing, channel_id: string) => {
    setBusy(true)
    try { await api.post(`/v1/transmission/filings/${f.filing_id}/send`, { channel_id }); toast.success('Transmission queued.'); onSent() }
    catch (e) { refused(e, 'The filing could not be sent.') } finally { setBusy(false) }
  }
  const record = async (t: Tx) => {
    setBusy(true)
    try { await api.post(`/v1/transmission/sends/${t.transmission_id}/receipt`, { receipt_ref: ref[t.transmission_id] }); toast.success('Reference recorded.'); onSent(); await qc.invalidateQueries({ queryKey: ['filings-register'] }) }
    catch (e) { refused(e, 'The reference could not be recorded.') } finally { setBusy(false) }
  }
  return (
    <Card className="p-5 space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <SectionHead icon={Send} className="gap-1.5">Send to the authority <InfoButton compact details={SEND} /></SectionHead>
        {d?.on_tellumen && <StatusChip tone="good" label="Your supervisor is on the platform" />}
      </div>
      {!d ? <div className="text-[12.5px] text-[var(--color-faint)]">Loading the channels…</div> : (
        <div className="grid md:grid-cols-2 gap-3">
          {d.frameworks.map(f => (
            <div key={f.framework} className="rounded-lg border border-[var(--color-line)] px-3.5 py-2.5">
              <div className="text-[13px] text-[var(--color-ink)]">{f.name}</div>
              <ul className="mt-1.5 space-y-1 m-0 p-0 list-none">{f.channels.map(c => (
                <li key={c.channel_id} className="flex flex-wrap items-center gap-2 text-[12px]">
                  <span className="inline-block w-2 h-2 rounded-full shrink-0" style={{ background: c.configured ? 'var(--color-good)' : 'var(--color-warn)' }} />
                  <span className="text-[var(--color-mute)]">{c.label}</span>
                  {c.prescribed && <StatusChip tone="neutral" label="Prescribed" />}
                  {!c.configured && <StatusChip tone="warn" label={`Needs ${c.missing_labels.join(', ').toLowerCase()}`} />}
                </li>))}</ul>
            </div>
          ))}
        </div>
      )}
      <div>
        <div className="text-[12.5px] text-[var(--color-ink)] mb-1.5">Attested filings ready to send</div>
        {filings.length === 0 ? <div className="text-[12.5px] text-[var(--color-faint)]">No attested filing yet — approve and attest a filing in the register first.</div> : (
          <ul className="m-0 p-0 list-none divide-y divide-[var(--color-line)]">{filings.map(f => {
            const opts = d?.frameworks.find(x => x.framework === f.framework)?.channels ?? []
            const chosen = pick[f.filing_id] ?? opts.find(o => o.prescribed && o.configured)?.channel_id ?? opts.find(o => o.configured)?.channel_id ?? ''
            return (
              <li key={f.filing_id} className="py-2 flex items-center gap-3 flex-wrap text-[12.5px]">
                <span className="min-w-[220px]"><span className="text-[var(--color-ink)]">{nameOf(f.framework)}</span> <span className="text-[11.5px] text-[var(--color-faint)]">{f.period_label}</span></span>
                <StatusChip value={f.status} label={statusLabel(f.status)} />
                {canAct && (<>
                  <select value={chosen} onChange={e => setPick(p => ({ ...p, [f.filing_id]: e.target.value }))} aria-label="Channel" className="bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-2 py-1 text-[12px] text-[var(--color-mute)]">
                    {opts.map(o => <option key={o.channel_id} value={o.channel_id}>{o.label}{o.configured ? '' : ' — sign-in details missing'}</option>)}
                  </select>
                  <Button variant="ghost" disabled={busy || !chosen} onClick={() => send(f, chosen)}><Send size={13} /> Send</Button>
                </>)}
              </li>
            )
          })}</ul>
        )}
      </div>
      <div>
        <div className="text-[12.5px] text-[var(--color-ink)] mb-1.5">Transmissions</div>
        {sends.length === 0 ? <div className="text-[12.5px] text-[var(--color-faint)]">Nothing sent yet.</div> : (
          <ul className="m-0 p-0 list-none divide-y divide-[var(--color-line)]">{sends.map(t => (
            <li key={t.transmission_id} className="py-2 flex items-center gap-3 flex-wrap text-[12.5px]">
              <span className="min-w-[200px]"><span className="text-[var(--color-ink)]">{t.framework_name}</span> <span className="text-[11.5px] text-[var(--color-faint)]">{t.period_label}</span></span>
              <span className="text-[11px] px-1.5 py-0.5 rounded bg-[var(--color-panel-2)] text-[var(--color-mute)]">{t.format_label}</span>
              <span className="text-[var(--color-mute)]">{t.channel_label}</span>
              <span className="inline-flex items-center gap-1">
                <StatusChip tone={t.worker_state === 'unavailable' ? 'bad' : TX_TONE[t.status] ?? 'neutral'} label={t.status_message.label} />
                <InfoButton compact details={messageDetails(t.status_message)} />
              </span>
              {t.receipt_ref && <span className="text-[12px] text-[var(--color-good)] tabular-nums">Receipt {t.receipt_ref}{t.receipt_at ? ` · ${t.receipt_at.slice(0, 10)}` : ''}</span>}
              <span className="ml-auto text-[11.5px] text-[var(--color-faint)] tabular-nums">{t.created_at.slice(0, 16).replace('T', ' ')}{t.attempts > 1 ? ` · ${t.attempts} attempts` : ''}</span>
              {t.status === 'awaiting_receipt' && canAct && (
                <span className="flex items-center gap-1.5">
                  <input value={ref[t.transmission_id] ?? ''} onChange={e => setRef(r => ({ ...r, [t.transmission_id]: e.target.value }))} placeholder="The authority’s reference" aria-label="The authority’s reference"
                    className="bg-[var(--color-panel)] border border-[var(--color-line)] rounded px-2 py-1 text-[12px] w-48" />
                  <Button variant="ghost" disabled={busy || !ref[t.transmission_id]} onClick={() => record(t)}><CheckCircle2 size={13} /> Record</Button>
                </span>
              )}
            </li>))}</ul>
        )}
      </div>
    </Card>
  )
}
