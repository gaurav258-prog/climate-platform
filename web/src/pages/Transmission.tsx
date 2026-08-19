import { useState, useEffect } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Send, CheckCircle2, Plus, FileText } from 'lucide-react'
import { api, ApiError } from '../lib/api'
import { toast } from '../lib/toast'
import { useAuth } from '../lib/auth'
import { filingLink } from '../lib/links'
import { frameworkLabel } from '../lib/hazards'
import { Eyebrow, Card, Button } from '../components/ui'

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
      <div className="flex items-end justify-between gap-4">
        <div>
          <Eyebrow>Regulator communication</Eyebrow>
          <h1 className="display text-3xl font-semibold mt-2 mb-1">Transmission</h1>
          <p className="text-[var(--color-mute)] text-sm max-w-2xl">Every submission and the correspondence around it — one tracker per filing, from ready-to-submit through the regulator's queries to closed.</p>
        </div>
        {canAct && <Button variant="ghost" onClick={() => setOpening(o => !o)}><Plus size={14} /> Open case</Button>}
      </div>

      {opening && (
        <Card className="p-3 flex items-center gap-2">
          <input value={reg} onChange={e => setReg(e.target.value)} onKeyDown={e => e.key === 'Enter' && openCase()}
            placeholder="Regulator (e.g. National Competent Authority / EBA)" className="flex-1 bg-transparent outline-none text-[14px]" />
          <Button variant="primary" onClick={openCase} disabled={!reg.trim()}>Open</Button>
        </Card>
      )}

      <div className="grid lg:grid-cols-[300px_1fr] gap-5">
        {/* case list */}
        <Card className="p-0 overflow-hidden self-start">
          <div className="px-4 py-2.5 border-b border-[var(--color-line)] mono text-[10px] uppercase tracking-wide text-[var(--color-faint)]">Cases</div>
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
