import { useState, useEffect } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Send, CheckCircle2, Plus, FileText } from 'lucide-react'
import { api, ApiError } from '../lib/api'
import { toast } from '../lib/toast'
import { useAuth } from '../lib/auth'
import { filingLink } from '../lib/links'
import { frameworkLabel } from '../lib/hazards'
import { Card, Button, PageHeader, SectionHead } from '../components/ui'
import { useEffect as useEffect2 } from 'react'
import SectionTabs, { DATA_TABS } from '../components/SectionTabs'

// Transmission — submission cases & regulator communication. A five-stage tracker + an append-only message
// thread per submission. (The real transmission channel to a regulator portal is external; this records it.)

interface Msg { direction: 'outbound' | 'inbound'; author: string; body: string; attachment_ref: string | null; at: string }
interface CaseSummary { case_id: string; regulator: string; reference: string | null; stage: string; framework: string | null; period_label: string | null; n_messages: number; updated_at: string }
interface CaseDetail extends CaseSummary { created_at: string; filing_id: string | null; messages: Msg[] }

const STAGES = ['ready', 'submitted', 'query', 'answered', 'closed']
const STAGE_LABEL: Record<string, string> = { ready: 'Ready to submit', submitted: 'Submitted', query: 'Regulatory query', answered: 'Answer provided', closed: 'Closed' }

export default function Transmission() {
  const { profile } = useAuth()
  const qc = useQueryClient()
  const canAct = (profile?.permissions ?? []).includes('reports.publish')
  const q = useQuery({ queryKey: ['transmission-cases'], queryFn: () => api.get<{ cases: CaseSummary[] }>('/v1/transmission/cases') })
  const [sel, setSel] = useState<string | null>(null)
  // deep-link from a filing: /transmission?case=<id> preselects that case
  const [params] = useSearchParams()
  useEffect(() => { const c = params.get('case'); if (c) setSel(c) }, [params])
  const [opening, setOpening] = useState(false)
  const [reg, setReg] = useState('')
  const cases = q.data?.cases ?? []
  const active = sel ?? cases[0]?.case_id ?? null
  const refresh = () => qc.invalidateQueries({ queryKey: ['transmission-cases'] })

  const openCase = async () => {
    if (!reg.trim()) return
    try { const c = await api.post<CaseDetail>('/v1/transmission/cases', { regulator: reg.trim() }); setReg(''); setOpening(false); refresh(); setSel(c.case_id) }
    catch (e) { toast.error(e instanceof ApiError ? e.message : 'Could not open the case.') }
  }

  return (
    <div className="fadeup space-y-5">
      <SectionTabs tabs={DATA_TABS} />
      <PageHeader eyebrow="Regulator communication" title="Transmission"
        lead="Every submission and the correspondence around it — one tracker per filing, from ready-to-submit through the regulator's queries to closed."
        actions={canAct && <Button variant="ghost" onClick={() => setOpening(o => !o)}><Plus size={14} /> Open case</Button>} />

      {opening && (
        <Card className="p-3 flex items-center gap-2">
          <input value={reg} onChange={e => setReg(e.target.value)} onKeyDown={e => e.key === 'Enter' && openCase()}
            placeholder="Regulator (e.g. National Competent Authority / EBA)" className="flex-1 bg-transparent outline-none text-[14px]" />
          <Button variant="primary" onClick={openCase} disabled={!reg.trim()}>Open</Button>
        </Card>
      )}

      <SendPanel canAct={canAct} onSent={refresh} />

      <div className="grid lg:grid-cols-[300px_1fr] gap-5">
        {/* case list */}
        <Card className="p-0 overflow-hidden self-start">
          <div className="px-4 py-3 border-b border-[var(--color-line)]"><SectionHead>Cases</SectionHead></div>
          {cases.length === 0 ? <div className="px-4 py-6 text-[13px] text-[var(--color-faint)]">No cases yet.</div>
            : <div className="divide-y divide-[var(--color-line)]">
                {cases.map(c => (
                  <button key={c.case_id} onClick={() => setSel(c.case_id)} className={`w-full text-left px-4 py-3 transition ${active === c.case_id ? 'bg-[var(--color-panel)]' : 'hover:bg-[var(--color-panel)]'}`}>
                    <div className="text-[13px] text-[var(--color-ink)] truncate">{c.regulator}</div>
                    <div className="mono text-[10.5px] text-[var(--color-faint)]">{[c.framework ? frameworkLabel(c.framework) : null, c.period_label, `${c.n_messages} msgs`].filter(Boolean).join(' · ')}</div>
                    <div className="mt-1"><StagePill stage={c.stage} /></div>
                  </button>
                ))}
              </div>}
        </Card>

        {/* case detail */}
        {active ? <CaseView caseId={active} canAct={canAct} onChanged={refresh} /> : <Card className="p-10 text-center text-[var(--color-faint)] text-sm">Select or open a case.</Card>}
      </div>
    </div>
  )
}

function CaseView({ caseId, canAct, onChanged }: { caseId: string; canAct: boolean; onChanged: () => void }) {
  const qc = useQueryClient()
  const { profile } = useAuth()
  const nav = useNavigate()
  // the backend message endpoint requires approvals.create — gate the reply box on the same permission
  // so a read-only viewer isn't offered an action the server will reject.
  const canMessage = (profile?.permissions ?? []).includes('approvals.create')
  const q = useQuery({ queryKey: ['transmission-case', caseId], queryFn: () => api.get<CaseDetail>(`/v1/transmission/cases/${caseId}`) })
  const [reply, setReply] = useState('')
  const d = q.data
  const reload = () => { qc.invalidateQueries({ queryKey: ['transmission-case', caseId] }); onChanged() }
  if (!d) return <Card className="p-10 text-center text-[var(--color-faint)] text-sm">loading…</Card>
  const idx = STAGES.indexOf(d.stage)

  const post = async () => {
    if (!reply.trim()) return
    try { await api.post(`/v1/transmission/cases/${caseId}/message`, { direction: 'outbound', author: 'Us', body: reply.trim() }); setReply(''); reload() }
    catch (e) { toast.error(e instanceof ApiError ? e.message : 'Could not send.') }
  }
  const stage = async (s: string) => { try { await api.post(`/v1/transmission/cases/${caseId}/stage`, { stage: s }); reload() } catch (e) { toast.error(e instanceof ApiError ? e.message : 'Could not advance.') } }

  return (
    <Card className="p-0 overflow-hidden flex flex-col">
      <div className="px-5 py-3 border-b border-[var(--color-line)] flex items-start justify-between gap-3">
        <div>
          <div className="text-[14px] text-[var(--color-ink)]">{d.regulator}</div>
          <div className="mono text-[11px] text-[var(--color-faint)]">{[d.framework ? frameworkLabel(d.framework) : null, d.period_label, d.reference].filter(Boolean).join(' · ')}</div>
        </div>
        {d.filing_id && (
          <button onClick={() => nav(filingLink(profile?.org?.type, d.filing_id!))}
            className="shrink-0 inline-flex items-center gap-1.5 text-[12px] text-[var(--color-sky)] hover:underline" title="Open the filing this case is about">
            <FileText size={13} /> Open filing
          </button>
        )}
      </div>

      {/* five-stage tracker */}
      <div className="px-5 py-4 flex items-center gap-1 border-b border-[var(--color-line)] overflow-x-auto">
        {STAGES.map((s, i) => (
          <div key={s} className="flex items-center gap-1 shrink-0">
            <div className="flex flex-col items-center gap-1">
              <div className="w-6 h-6 rounded-full flex items-center justify-center text-[10px]" style={{ background: i < idx ? '#34d39922' : i === idx ? '#5cc8ff22' : 'var(--color-panel-2)', color: i < idx ? '#34d399' : i === idx ? '#5cc8ff' : 'var(--color-faint)', border: `1px solid ${i <= idx ? (i === idx ? '#5cc8ff' : '#34d399') : 'var(--color-line)'}` }}>
                {i < idx ? <CheckCircle2 size={12} /> : i + 1}
              </div>
              <span className="text-[9.5px] mono whitespace-nowrap" style={{ color: i === idx ? 'var(--color-ink)' : 'var(--color-faint)' }}>{STAGE_LABEL[s]}</span>
            </div>
            {i < STAGES.length - 1 && <div className="w-8 h-px mb-4" style={{ background: i < idx ? '#34d399' : 'var(--color-line)' }} />}
          </div>
        ))}
      </div>

      {/* thread */}
      <div className="px-5 py-4 space-y-2.5 flex-1 max-h-[360px] overflow-y-auto">
        {d.messages.map((m, i) => m.author === 'system'
          ? <div key={i} className="text-center text-[10.5px] mono text-[var(--color-faint)]">{m.body}</div>
          : <div key={i} className={`flex ${m.direction === 'outbound' ? 'justify-end' : 'justify-start'}`}>
              <div className="max-w-[75%] rounded-xl px-3 py-2" style={{ background: m.direction === 'outbound' ? '#0e749022' : 'var(--color-panel-2)' }}>
                <div className="mono text-[9.5px] text-[var(--color-faint)] mb-0.5">{m.author} · {new Date(m.at).toLocaleString('en-GB', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })}</div>
                <div className="text-[12.5px] text-[var(--color-ink)]">{m.body}</div>
              </div>
            </div>)}
      </div>

      {/* actions */}
      <div className="px-5 py-3 border-t border-[var(--color-line)] space-y-2">
        {canMessage
          ? <div className="flex items-center gap-2">
              <input value={reply} onChange={e => setReply(e.target.value)} onKeyDown={e => e.key === 'Enter' && post()} placeholder="Log a reply…" className="flex-1 bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-3 py-2 text-[13px] outline-none focus:border-[var(--color-sky)]" />
              <Button variant="primary" onClick={post} disabled={!reply.trim()}><Send size={14} /></Button>
            </div>
          : <div className="text-[11.5px] text-[var(--color-faint)]">You have read-only access to this case — logging a reply needs the <span className="mono">approvals.create</span> permission.</div>}
        {canAct && idx < STAGES.length - 1 && (
          <button onClick={() => stage(STAGES[idx + 1])} className="mono text-[11px] text-[var(--color-sky)] hover:underline">advance → {STAGE_LABEL[STAGES[idx + 1]]}</button>
        )}
        <div className="mono text-[9.5px] text-[var(--color-faint)]">Correspondence log — messages are append-only. Real portal transmission is handled outside the platform.</div>
      </div>
    </Card>
  )
}

function StagePill({ stage }: { stage: string }) {
  const tone = stage === 'closed' ? '#34d399' : stage === 'query' ? '#f0a860' : '#5cc8ff'
  return <span className="mono text-[9px] px-1.5 py-0.5 rounded" style={{ color: tone, background: `${tone}22` }}>{STAGE_LABEL[stage]}</span>
}

// ── Send to the authority: the channel the mandate prescribes, the Tellumen channel where the supervisor is on the
// platform, and every transmission with its receipt. Nothing is pretended: a portal without credentials says so.
interface Chan { channel_id: string; label: string; kind: string; authority: string; formats: string[]; receipt: string; configured: boolean; missing: string[]; prescribed: boolean }
interface ChanResp { on_tellumen: boolean; frameworks: { framework: string; label: string; mandate_id: string | null; formats: string[]; channels: Chan[] }[] }
interface Filing { filing_id: string; framework: string; period_label: string; status: string; submission_ref: string | null }
interface Tx { transmission_id: string; filing_id: string; framework: string; period_label: string; channel_id: string; channel_label: string; channel_kind: string; format: string; status: string; attempts: number
  payload_sha256: string | null; filename: string | null; sent_at: string | null; receipt_ref: string | null; receipt_at: string | null; error: string | null; created_at: string; created_by: string | null
  worker_state: 'alive' | 'unavailable' | null }   // set only while the transmission waits on the worker (queued / failed-retrying)
interface WorkerStatus { alive: boolean; last_seen: string | null; stale_after_s: number; executor: 'celery' | 'process' }
const TX_COLOR: Record<string, string> = { acknowledged: 'var(--color-good)', sent: 'var(--color-sky)', queued: 'var(--color-mute)', awaiting_receipt: 'var(--color-warn)', awaiting_credentials: 'var(--color-warn)', rejected: 'var(--color-bad)', failed: 'var(--color-bad)' }
const TX_LABEL: Record<string, string> = { acknowledged: 'Receipted', sent: 'Sent · awaiting receipt', queued: 'Queued', awaiting_receipt: 'Delivered outside the platform · record the reference', awaiting_credentials: 'Not sent · channel credentials missing', rejected: 'Rejected', failed: 'Failed · will retry' }
// Honest waiting state: a queued (or failed-retrying) transmission with no live executor is NOT "queued" — nobody will
// pick it up until the worker is back. The API decides `worker_state` from the executor heartbeat (stale after 90 s).
const stuck = (t: Tx) => t.worker_state === 'unavailable'
const txColor = (t: Tx) => (stuck(t) ? 'var(--color-bad)' : TX_COLOR[t.status])
const txLabel = (t: Tx) => {
  if (!stuck(t)) return TX_LABEL[t.status] ?? t.status
  const since = t.created_at.slice(0, 16).replace('T', ' ')
  return t.status === 'queued' ? `Worker unavailable — queued since ${since}` : `Worker unavailable — retry pending since ${since}`
}
function SendPanel({ canAct, onSent }: { canAct: boolean; onSent: () => void }) {
  const qc = useQueryClient()
  const ch = useQuery({ queryKey: ['tx-channels'], queryFn: () => api.get<ChanResp>('/v1/transmission/channels') })
  const fl = useQuery({ queryKey: ['filings-register'], queryFn: () => api.get<{ filings: Filing[] } | Filing[]>('/v1/filings') })
  const tx = useQuery({ queryKey: ['tx-sends'], queryFn: () => api.get<{ transmissions: Tx[]; worker: WorkerStatus }>('/v1/transmission/sends'), refetchInterval: (q) => (q.state.data?.transmissions.some(t => t.worker_state) ? 3000 : false) })
  const [pick, setPick] = useState<Record<string, string>>({})
  const [ref, setRef] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState(false)
  useEffect2(() => { onSent() }, [tx.data?.transmissions.length])   // eslint-disable-line react-hooks/exhaustive-deps
  const filings = (Array.isArray(fl.data) ? fl.data : fl.data?.filings ?? []).filter(f => ['attested', 'submitted', 'accepted'].includes(f.status))
  const send = async (f: Filing, channel_id: string) => {
    setBusy(true)
    try { await api.post(`/v1/transmission/filings/${f.filing_id}/send`, { channel_id }); toast.success('Transmission queued on the worker.'); await qc.invalidateQueries({ queryKey: ['tx-sends'] }) }
    catch (e) { toast.error(e instanceof ApiError ? e.message : 'Could not send.') } finally { setBusy(false) }
  }
  const record = async (t: Tx) => {
    setBusy(true)
    try { await api.post(`/v1/transmission/sends/${t.transmission_id}/receipt`, { receipt_ref: ref[t.transmission_id] }); toast.success('Receipt recorded.'); await qc.invalidateQueries({ queryKey: ['tx-sends'] }); await qc.invalidateQueries({ queryKey: ['filings-register'] }) }
    catch (e) { toast.error(e instanceof ApiError ? e.message : 'Could not record.') } finally { setBusy(false) }
  }
  const d = ch.data
  return (
    <Card className="p-5">
      <SectionHead hint={d?.on_tellumen ? 'your supervisor is on Tellumen — the platform channel delivers and receipts immediately; authority portals need their credentials' : 'authority portals need their credentials; channels outside the platform record the reference by hand'}>Send to the authority</SectionHead>
      {!d ? <div className="text-[12px] text-[var(--color-faint)]">loading channels…</div> : (
        <div className="grid md:grid-cols-2 gap-3 mb-4">
          {d.frameworks.map(f => (
            <div key={f.framework} className="rounded-lg border border-[var(--color-line)] px-3.5 py-2.5 text-[12.5px]">
              <div className="text-[var(--color-ink)]">{frameworkLabel(f.framework)}</div>
              <div className="mt-1 space-y-0.5">{f.channels.map(c => (
                <div key={c.channel_id} className="flex items-center gap-2 text-[11.5px]">
                  <span className="inline-block w-2 h-2 rounded-full shrink-0" style={{ background: c.configured ? 'var(--color-good)' : 'var(--color-warn)' }} />
                  <span className="text-[var(--color-mute)]">{c.label}{c.prescribed ? <span className="mono text-[9.5px] uppercase ml-1 text-[var(--color-sky)]">prescribed</span> : null}</span>
                  {!c.configured && <span className="mono text-[10px] text-[var(--color-warn)]">needs {c.missing.join(', ')}</span>}
                </div>))}</div>
            </div>))}
        </div>)}
      <div className="mono text-[10.5px] uppercase tracking-wide text-[var(--color-faint)] mb-1.5">Attested filings ready to send</div>
      {filings.length === 0 ? <div className="text-[12px] text-[var(--color-faint)] mb-4">No attested filing yet — approve and attest a filing in the register first.</div> : (
        <div className="divide-y divide-[var(--color-line)] mb-4">{filings.map(f => { const opts = d?.frameworks.find(x => x.framework === f.framework)?.channels ?? []; const chosen = pick[f.filing_id] ?? opts.find(o => o.prescribed && o.configured)?.channel_id ?? opts.find(o => o.configured)?.channel_id ?? ''; return (
          <div key={f.filing_id} className="py-2 flex items-center gap-3 flex-wrap text-[12.5px]">
            <span className="text-[var(--color-ink)] min-w-[240px]">{frameworkLabel(f.framework)} <span className="mono text-[10.5px] text-[var(--color-faint)]">{f.period_label} · {f.status}{f.submission_ref ? ` · ref ${f.submission_ref}` : ''}</span></span>
            {canAct && (<>
              <select value={chosen} onChange={e => setPick(p => ({ ...p, [f.filing_id]: e.target.value }))} className="bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-2 py-1 text-[12px] text-[var(--color-mute)]">
                {opts.map(o => <option key={o.channel_id} value={o.channel_id}>{o.label}{o.configured ? '' : ' (credentials missing)'}</option>)}</select>
              <Button variant="ghost" disabled={busy || !chosen} onClick={() => send(f, chosen)}><Send size={13} /> Send</Button></>)}
          </div>) })}</div>)}
      <div className="mono text-[10.5px] uppercase tracking-wide text-[var(--color-faint)] mb-1.5">Transmissions</div>
      {tx.data && !tx.data.worker.alive && tx.data.transmissions.some(stuck) && (
        <div className="text-[11.5px] text-[var(--color-bad)] mb-2">Job worker unavailable — no heartbeat {tx.data.worker.last_seen ? `since ${tx.data.worker.last_seen.slice(0, 16).replace('T', ' ')}` : 'on record'} (stale after {tx.data.worker.stale_after_s}s). Queued transmissions will not be sent until it is back.</div>)}
      {(tx.data?.transmissions ?? []).length === 0 ? <div className="text-[12px] text-[var(--color-faint)]">Nothing transmitted yet.</div> : (
        <div className="divide-y divide-[var(--color-line)]">{tx.data!.transmissions.map(t => (
          <div key={t.transmission_id} className="py-2 flex items-center gap-3 flex-wrap text-[12.5px]">
            <span className="text-[var(--color-ink)] min-w-[220px]">{frameworkLabel(t.framework)} <span className="mono text-[10.5px] text-[var(--color-faint)]">{t.period_label} · {t.format}</span></span>
            <span className="text-[var(--color-mute)]">{t.channel_label}</span>
            <span className="mono text-[10px] uppercase px-1.5 py-0.5 rounded" style={{ color: txColor(t), background: `color-mix(in oklab, ${txColor(t)} 14%, transparent)` }}>{txLabel(t)}</span>
            {t.receipt_ref && <span className="mono text-[11px] text-[var(--color-good)]">receipt {t.receipt_ref} · {t.receipt_at?.slice(0, 10)}</span>}
            {t.error && <span className="text-[11.5px] text-[var(--color-warn)]">{t.error}</span>}
            <span className="mono text-[10px] text-[var(--color-faint)] ml-auto" title={t.payload_sha256 ?? ''}>{t.filename} · {t.created_at.slice(0, 16).replace('T', ' ')} · attempt {t.attempts}</span>
            {t.status === 'awaiting_receipt' && canAct && <span className="flex items-center gap-1.5"><input value={ref[t.transmission_id] ?? ''} onChange={e => setRef(r => ({ ...r, [t.transmission_id]: e.target.value }))} placeholder="authority reference" className="bg-[var(--color-panel)] border border-[var(--color-line)] rounded px-2 py-1 text-[12px] w-44" /><Button variant="ghost" disabled={busy || !ref[t.transmission_id]} onClick={() => record(t)}><CheckCircle2 size={13} /> Record</Button></span>}
          </div>))}</div>)}
    </Card>
  )
}
