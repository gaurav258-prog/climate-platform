import { useState, useEffect } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { CalendarClock, FileText, ShieldCheck, X, CheckCircle2, AlertTriangle, Clock, PenLine, Send, Stamp, XCircle, Info, GitCompareArrows, Download, RadioTower } from 'lucide-react'
import { api, ApiError, download } from '../lib/api'
import { frameworkLabel } from '../lib/hazards'
import { useAuth } from '../lib/auth'
import { Card, Button } from './ui'
import FilingLineage from './FilingLineage'
import FilingVariance from './FilingVariance'
import FilingBasis from './FilingBasis'
import FilingPreflight from './FilingPreflight'
import FilingRequirements from './FilingRequirements'

// The reporting cockpit for a financial institution: the filing calendar (what's due), the filing register
// (every filing and where it is in its lifecycle), and a drawer that runs the controlled lifecycle —
// prepare → review (4-eyes) → attest → submit → accept — with the full append-only history and the
// hash-verified frozen snapshot behind each number.

interface Obligation { obligation_id: string; framework: string; label: string; period_label: string; due_date: string; frequency: string; filing_id: string | null; filing_status: string; days_to_due: number; overdue: boolean }
interface Framework { framework: string; label: string; frequency: string; regulator: string; basis: string }
interface FilingSummary { filing_id: string; framework: string; label: string; period_label: string; status: string; snapshot_version: number | null; submission_ref: string | null; note: string | null; created_by: string | null; created_at: string; updated_at: string; entity_name?: string | null; scope?: string }
interface FilingEvent { from: string | null; to: string; action: string; detail: Record<string, unknown>; at: string; actor: string | null; actor_email: string | null }
interface FilingDetail extends FilingSummary {
  approval_request_id: string | null; regulator?: string; basis?: string; events: FilingEvent[]
  export_formats?: string[]
  snapshot?: { version: number; reporting_basis: Record<string, unknown>; payload: Record<string, unknown>; payload_sha256: string; hash_verified: boolean; created_at: string }
}
interface CaseLink { case_id: string; regulator: string; reference: string | null; stage: string; n_messages: number }
interface Finding { rule: string; category: string; severity: 'blocking' | 'warning' | 'info'; passed: boolean; message: string; ref: string | null }
interface Validation { filing_id: string; framework: string; findings: Finding[]; blocking: number; warnings: number; checks: number; passed: boolean }

// status → label + colour. One vocabulary the whole cockpit speaks.
const ST: Record<string, { label: string; fg: string; bg: string }> = {
  not_started: { label: 'Not started', fg: '#94a3b8', bg: '#94a3b820' },
  draft:       { label: 'Draft', fg: '#94a3b8', bg: '#94a3b820' },
  in_review:   { label: 'In review', fg: '#e8b24c', bg: '#e8b24c20' },
  returned:    { label: 'Returned', fg: '#e8b24c', bg: '#e8b24c20' },
  approved:    { label: 'Approved', fg: '#5cc8ff', bg: '#5cc8ff20' },
  attested:    { label: 'Attested', fg: '#a78bfa', bg: '#a78bfa20' },
  submitted:   { label: 'Submitted', fg: '#2dd4bf', bg: '#2dd4bf20' },
  accepted:    { label: 'Accepted', fg: '#34d399', bg: '#34d39920' },
  rejected:    { label: 'Rejected', fg: '#fb7185', bg: '#fb718520' },
  superseded:  { label: 'Superseded', fg: '#64748b', bg: '#64748b20' },
}
const Chip = ({ status }: { status: string }) => {
  const s = ST[status] ?? ST.not_started
  return <span className="mono text-[10.5px] font-medium px-2.5 py-1 rounded-full whitespace-nowrap" style={{ color: s.fg, background: s.bg }}>{s.label}</span>
}
// scope of a filing: a specific legal entity, or a consolidated group (the whole subtree, ownership-weighted)
const ScopeChip = ({ scope, name }: { scope: string; name?: string | null }) => {
  const consolidated = scope === 'consolidated'
  const c = consolidated ? '#a78bfa' : '#5cc8ff'
  return <span className="mono text-[9.5px] font-medium px-1.5 py-0.5 rounded whitespace-nowrap" style={{ color: c, background: `${c}22` }} title={name ?? undefined}>{consolidated ? '⤳ consolidated' : 'entity'}{name ? ` · ${name}` : ''}</span>
}
const fmtDate = (s: string) => new Date(s).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })
// the six lifecycle stages, in order — used to draw the progress rail
const STAGES = ['draft', 'in_review', 'approved', 'attested', 'submitted', 'accepted'] as const

export default function FilingCockpit() {
  const { profile } = useAuth()
  const qc = useQueryClient()
  const [params, setParams] = useSearchParams()
  const [openId, setOpenId] = useState<string | null>(null)
  const [preflightFw, setPreflightFw] = useState<string | null>(null)
  // deep-link: /compliance?filing=<id> (or /filings?filing=) opens that filing's drawer — used by the
  // calendar, Control Tower and KRI history to drill straight into a filing's full detail.
  useEffect(() => { const f = params.get('filing'); if (f) setOpenId(f) }, [params])
  const closeDrawer = () => { setOpenId(null); if (params.get('filing')) { params.delete('filing'); setParams(params, { replace: true }) } }

  const perms = profile?.permissions ?? []
  const canPrepare = perms.includes('approvals.create')

  const obl = useQuery({ queryKey: ['obligations'], queryFn: () => api.get<{ obligations: Obligation[] }>('/v1/obligations') })
  const fils = useQuery({ queryKey: ['filings'], queryFn: () => api.get<{ filings: FilingSummary[] }>('/v1/filings') })
  const fw = useQuery({ queryKey: ['frameworks'], queryFn: () => api.get<{ frameworks: Framework[] }>('/v1/filings/frameworks') })

  const refresh = () => { qc.invalidateQueries({ queryKey: ['obligations'] }); qc.invalidateQueries({ queryKey: ['filings'] }) }

  const obligations = obl.data?.obligations ?? []
  const filings = fils.data?.filings ?? []
  const frameworks = fw.data?.frameworks ?? []

  if (frameworks.length === 0 && !fw.isLoading) return null   // sector with no filings wired yet — cockpit hidden

  return (
    <div className="space-y-6">
      {/* ── reporting requirements — what must be filed, to whom, by when, with the regulation + prior reports ── */}
      <FilingRequirements onOpen={setOpenId} />

      {/* ── reporting basis (the parameters new filings freeze) ── */}
      <FilingBasis />

      {/* ── filing calendar ── */}
      <Card className="p-0 overflow-hidden">
        <div className="flex items-center gap-2 px-5 py-3 border-b border-[var(--color-line)]">
          <CalendarClock size={15} className="text-[var(--color-sky)]" />
          <span className="mono text-[10.5px] tracking-[0.16em] uppercase text-[var(--color-faint)]">Filing calendar · what's due</span>
        </div>
        {obligations.length === 0
          ? <div className="px-5 py-6 text-[13px] text-[var(--color-faint)]">No obligations for the current period.</div>
          : <div className="divide-y divide-[var(--color-line)]">
              {obligations.map(o => (
                <div key={o.obligation_id} className="px-5 py-3.5 flex items-center gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="text-[14px] text-[var(--color-ink)] truncate">{o.label}</div>
                    <div className="mono text-[11px] text-[var(--color-faint)]">{o.period_label} · {o.frequency}</div>
                  </div>
                  <div className="text-right w-40">
                    <div className={`mono text-[12px] ${o.overdue ? 'text-[var(--color-bad)]' : 'text-[var(--color-mute)]'}`}>due {fmtDate(o.due_date)}</div>
                    <div className="mono text-[10.5px] text-[var(--color-faint)]">
                      {o.filing_status === 'accepted' || o.filing_status === 'submitted' ? 'filed'
                        : o.overdue ? `${Math.abs(o.days_to_due)}d overdue` : `${o.days_to_due}d left`}
                    </div>
                  </div>
                  <div className="w-28 flex justify-end"><Chip status={o.filing_status} /></div>
                  <div className="w-32 flex justify-end">
                    {o.filing_id
                      ? <button onClick={() => setOpenId(o.filing_id)} className="mono text-[11px] text-[var(--color-sky)] hover:underline">open filing →</button>
                      : canPrepare
                        ? <button onClick={() => setPreflightFw(o.framework)} className="mono text-[11px] text-[var(--color-sky)] hover:underline">prepare filing →</button>
                        : <span className="mono text-[10.5px] text-[var(--color-faint)]">awaiting preparer</span>}
                  </div>
                </div>
              ))}
            </div>}
      </Card>

      {/* ── filing register ── */}
      <Card className="p-0 overflow-hidden">
        <div className="flex items-center gap-2 px-5 py-3 border-b border-[var(--color-line)]">
          <FileText size={15} className="text-[var(--color-sky)]" />
          <span className="mono text-[10.5px] tracking-[0.16em] uppercase text-[var(--color-faint)]">Filing register · past & in-flight</span>
        </div>
        {filings.length === 0
          ? <div className="px-5 py-6 text-[13px] text-[var(--color-faint)]">No filings yet. Prepare one from the calendar above.</div>
          : <div className="divide-y divide-[var(--color-line)]">
              {filings.map(f => (
                <button key={f.filing_id} onClick={() => setOpenId(f.filing_id)}
                  className="w-full text-left px-5 py-3.5 flex items-center gap-4 hover:bg-[var(--color-panel)] transition">
                  <div className="flex-1 min-w-0">
                    <div className="text-[14px] text-[var(--color-ink)] truncate flex items-center gap-2">{f.label} <span className="text-[var(--color-faint)]">· {f.period_label}</span>{f.scope && f.scope !== 'organisation' && <ScopeChip scope={f.scope} name={f.entity_name} />}</div>
                    <div className="mono text-[11px] text-[var(--color-faint)]">v{f.snapshot_version ?? '—'} · prepared by {f.created_by ?? '—'} · {fmtDate(f.created_at)}{f.submission_ref ? ` · ref ${f.submission_ref}` : ''}</div>
                  </div>
                  <Chip status={f.status} />
                </button>
              ))}
            </div>}
      </Card>

      {openId && <FilingDrawer filingId={openId} onClose={closeDrawer} onChanged={refresh} onOpen={setOpenId} />}
      {preflightFw && <FilingPreflight framework={preflightFw} onClose={() => setPreflightFw(null)}
        onGenerated={(id) => { setPreflightFw(null); refresh(); setOpenId(id) }} />}
    </div>
  )
}

function FilingDrawer({ filingId, onClose, onChanged, onOpen }: { filingId: string; onClose: () => void; onChanged: () => void; onOpen: (id: string) => void }) {
  const { profile } = useAuth()
  const qc = useQueryClient()
  const perms = profile?.permissions ?? []
  const q = useQuery({ queryKey: ['filing', filingId], queryFn: () => api.get<FilingDetail>(`/v1/filings/${filingId}`) })
  const val = useQuery({ queryKey: ['filing-validation', filingId], queryFn: () => api.get<Validation>(`/v1/filings/${filingId}/validation`) })
  const f = q.data
  const reload = () => { q.refetch(); val.refetch(); qc.invalidateQueries({ queryKey: ['filings'] }); qc.invalidateQueries({ queryKey: ['obligations'] }); onChanged() }

  return (
    <div className="fixed inset-0 z-50 flex justify-end" onClick={onClose}>
      <div className="absolute inset-0 bg-black/50" />
      <div className="relative w-full max-w-xl h-full overflow-y-auto bg-[var(--color-bg-2)] border-l border-[var(--color-line)] shadow-2xl" onClick={e => e.stopPropagation()}>
        <div className="sticky top-0 z-10 flex items-center justify-between px-6 py-4 border-b border-[var(--color-line)] bg-[var(--color-bg-2)]">
          <div className="mono text-[10.5px] tracking-[0.16em] uppercase text-[var(--color-faint)]">Filing</div>
          <button onClick={onClose} className="text-[var(--color-faint)] hover:text-[var(--color-ink)]"><X size={18} /></button>
        </div>

        {!f ? <div className="p-8 text-[13px] text-[var(--color-faint)]">loading…</div> : (
          <div className="p-6 space-y-6">
            <div>
              <div className="flex items-center gap-3 mb-1 flex-wrap">
                <h2 className="display text-xl font-semibold">{f.label}</h2><Chip status={f.status} />
                {f.scope && f.scope !== 'organisation' && <ScopeChip scope={f.scope} name={f.entity_name} />}
              </div>
              <div className="mono text-[11px] text-[var(--color-faint)]">{f.period_label} · {f.basis ?? frameworkLabel(f.framework)}{f.regulator ? ` · ${f.regulator}` : ''}{f.scope === 'organisation' ? ' · whole organisation' : ''}</div>
            </div>

            {/* lifecycle rail */}
            <StageRail status={f.status} />

            {/* frozen snapshot */}
            {f.snapshot && (
              <Card className="p-4">
                <div className="flex items-center justify-between mb-2">
                  <div className="mono text-[10px] uppercase tracking-widest text-[var(--color-faint)]">Frozen report · v{f.snapshot.version}</div>
                  <span className="inline-flex items-center gap-1 mono text-[10.5px]" style={{ color: f.snapshot.hash_verified ? '#34d399' : '#fb7185' }}>
                    {f.snapshot.hash_verified ? <CheckCircle2 size={12} /> : <AlertTriangle size={12} />}{f.snapshot.hash_verified ? 'hash verified' : 'hash mismatch'}
                  </span>
                </div>
                <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-[12px]">
                  {Object.entries(f.snapshot.reporting_basis).map(([k, v]) => (
                    <div key={k} className="flex justify-between border-b border-[var(--color-line)] pb-1">
                      <span className="text-[var(--color-mute)]">{k.replace(/_/g, ' ')}</span><span className="text-[var(--color-ink)] mono">{String(v)}</span>
                    </div>
                  ))}
                </div>
                <div className="mono text-[9.5px] text-[var(--color-faint)] mt-2 break-all">sha256 {f.snapshot.payload_sha256.slice(0, 32)}…</div>
                {(f.export_formats?.length ?? 0) > 0 && (
                  <div className="mt-3 pt-3 border-t border-[var(--color-line)]">
                    <div className="mono text-[9.5px] uppercase tracking-wide text-[var(--color-faint)] mb-2">Download · rendered from these frozen bytes</div>
                    <div className="flex flex-wrap gap-2">
                      {f.export_formats!.map(fmt => (
                        <button key={fmt}
                          onClick={() => download(`/v1/filings/${f.filing_id}/export?format=${fmt}`, `${f.framework}-${f.period_label}-v${f.snapshot!.version}.${fmt}`).catch(() => alert('Could not download the export.'))}
                          className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-line-2)] px-2.5 py-1 text-[11.5px] text-[var(--color-mute)] hover:border-[var(--color-sky)] hover:text-[var(--color-sky)] transition">
                          <Download size={12} /> {fmt.toUpperCase()}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </Card>
            )}

            {/* change vs the prior version (restatement / prior period) */}
            <FilingVariance filingId={filingId} />

            {/* bidirectional data lineage — trace each reported figure to its source feed and back */}
            <FilingLineage filingId={filingId} />

            {/* validation checklist */}
            {val.data && <ValidationCard v={val.data} />}

            {/* action panel — gated by status + permission + open blockers */}
            <ActionPanel f={f} perms={perms} onDone={reload} blocking={val.data?.blocking ?? 0} onOpen={onOpen} />

            {/* regulator transmission — link this filing to its submission case (Transmission module) */}
            <FilingTransmission f={f} />

            {/* lifecycle history */}
            <div>
              <div className="mono text-[10px] uppercase tracking-widest text-[var(--color-faint)] mb-3">Lifecycle history</div>
              <div className="space-y-3">
                {f.events.map((e, i) => (
                  <div key={i} className="flex gap-3">
                    <div className="mt-1"><Clock size={13} className="text-[var(--color-faint)]" /></div>
                    <div className="flex-1 min-w-0">
                      <div className="text-[13px] text-[var(--color-ink)]"><Chip status={e.to} /> <span className="text-[var(--color-mute)] ml-1">{e.action.replace(/_/g, ' ')}</span></div>
                      <div className="mono text-[10.5px] text-[var(--color-faint)] mt-0.5">{e.actor ?? '—'} · {new Date(e.at).toLocaleString('en-GB')}</div>
                      {typeof e.detail?.reason === 'string' && <div className="text-[12px] text-[var(--color-mute)] mt-1 italic">“{e.detail.reason}”</div>}
                      {typeof e.detail?.statement === 'string' && <div className="text-[12px] text-[var(--color-mute)] mt-1">✍ {e.detail.attestor_name as string}: “{e.detail.statement}”</div>}
                      {typeof e.detail?.submission_ref === 'string' && <div className="mono text-[11px] text-[var(--color-mute)] mt-1">ref {e.detail.submission_ref}</div>}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// Links a filing to its regulator submission case in Transmission — jump to an existing case, or (once the
// filing is far enough to actually transmit) open one linked to this filing so the two modules stay joined.
const CASE_STAGE: Record<string, string> = { ready: 'Ready to submit', submitted: 'Submitted', query: 'Regulatory query', answered: 'Answer provided', closed: 'Closed' }
function FilingTransmission({ f }: { f: FilingDetail }) {
  const { profile } = useAuth()
  const nav = useNavigate()
  const qc = useQueryClient()
  const [busy, setBusy] = useState(false)
  const canPublish = (profile?.permissions ?? []).includes('reports.publish')
  const q = useQuery({ queryKey: ['filing-case', f.filing_id], queryFn: () => api.get<{ case: CaseLink | null }>(`/v1/transmission/cases/for-filing/${f.filing_id}`) })
  const c = q.data?.case
  const canOpen = canPublish && ['attested', 'submitted', 'accepted'].includes(f.status)
  if (!c && !canOpen) return null   // too early to transmit and no case yet — show nothing

  const openCase = async () => {
    setBusy(true)
    try {
      const nc = await api.post<{ case_id: string }>('/v1/transmission/cases', { regulator: f.regulator || 'Regulator', filing_id: f.filing_id })
      qc.invalidateQueries({ queryKey: ['transmission-cases'] })
      nav(`/transmission?case=${nc.case_id}`)
    } catch (e) { alert(e instanceof ApiError ? e.message : 'Could not open the transmission case.') }
    finally { setBusy(false) }
  }

  return (
    <Card className="p-4">
      <div className="flex items-center justify-between">
        <div className="mono text-[10px] uppercase tracking-widest text-[var(--color-faint)]">Regulator transmission</div>
        {c && <span className="mono text-[10px] px-1.5 py-0.5 rounded" style={{ color: '#5cc8ff', background: '#5cc8ff22' }}>{CASE_STAGE[c.stage] ?? c.stage}</span>}
      </div>
      {c
        ? <button onClick={() => nav(`/transmission?case=${c.case_id}`)} className="mt-2 inline-flex items-center gap-1.5 text-[12.5px] text-[var(--color-sky)] hover:underline">
            <RadioTower size={13} /> Open the regulator case · {c.regulator}{c.n_messages ? ` · ${c.n_messages} msg${c.n_messages === 1 ? '' : 's'}` : ''} →
          </button>
        : <div className="mt-2 space-y-2">
            <p className="text-[11.5px] text-[var(--color-mute)]">Track the submission and the regulator's correspondence for this filing in Transmission.</p>
            <Button variant="ghost" onClick={openCase} disabled={busy}><RadioTower size={13} /> Open transmission case</Button>
          </div>}
    </Card>
  )
}

function ValidationCard({ v }: { v: Validation }) {
  const [open, setOpen] = useState(!v.passed)   // auto-expand when something needs attention
  const order = { blocking: 0, warning: 1, info: 2 } as const
  const rows = [...v.findings].sort((a, b) =>
    (Number(a.passed) - Number(b.passed)) || (order[a.severity] - order[b.severity]))
  const headFg = v.blocking > 0 ? '#fb7185' : v.warnings > 0 ? '#e8b24c' : '#34d399'
  return (
    <Card className="p-4">
      <button onClick={() => setOpen(o => !o)} className="w-full flex items-center justify-between">
        <span className="mono text-[10px] uppercase tracking-widest text-[var(--color-faint)]">Validation · {v.checks} checks</span>
        <span className="mono text-[11px]" style={{ color: headFg }}>
          {v.blocking > 0 ? `${v.blocking} blocking` : v.warnings > 0 ? `${v.warnings} to review` : 'all clear'}
        </span>
      </button>
      {open && (
        <div className="mt-3 space-y-1.5">
          {rows.map(r => {
            const fg = r.passed ? '#34d399' : r.severity === 'blocking' ? '#fb7185' : r.severity === 'warning' ? '#e8b24c' : '#5cc8ff'
            const Icon = r.passed ? CheckCircle2 : r.severity === 'blocking' ? XCircle : r.severity === 'info' ? Info : AlertTriangle
            return (
              <div key={r.rule} className="flex items-start gap-2">
                <Icon size={13} style={{ color: fg }} className="mt-0.5 shrink-0" />
                <div className="min-w-0">
                  <span className="text-[12.5px]" style={{ color: r.passed ? 'var(--color-mute)' : 'var(--color-ink)' }}>{r.message}</span>
                  <span className="mono text-[9.5px] text-[var(--color-faint)] ml-1.5">{r.category}</span>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </Card>
  )
}

function StageRail({ status }: { status: string }) {
  if (status === 'rejected' || status === 'superseded') {
    return <div className="mono text-[11px]" style={{ color: ST[status].fg }}>This filing is {ST[status].label.toLowerCase()}.</div>
  }
  const idx = STAGES.indexOf(status as typeof STAGES[number])
  return (
    <div className="flex items-center">
      {STAGES.map((s, i) => (
        <div key={s} className="flex items-center flex-1 last:flex-none">
          <div className="flex flex-col items-center gap-1">
            <div className="w-6 h-6 rounded-full flex items-center justify-center text-[10px] mono"
              style={{ background: i <= idx ? ST[s].fg : 'var(--color-panel-2)', color: i <= idx ? '#08111f' : 'var(--color-faint)' }}>
              {i < idx ? '✓' : i + 1}
            </div>
            <span className="text-[9px] mono uppercase tracking-wide" style={{ color: i <= idx ? ST[s].fg : 'var(--color-faint)' }}>{ST[s].label}</span>
          </div>
          {i < STAGES.length - 1 && <div className="flex-1 h-0.5 mx-1 mb-4 rounded" style={{ background: i < idx ? ST[STAGES[i + 1]].fg : 'var(--color-panel-2)' }} />}
        </div>
      ))}
    </div>
  )
}

function ActionPanel({ f, perms, onDone, blocking, onOpen }: { f: FilingDetail; perms: string[]; onDone: () => void; blocking: number; onOpen: (id: string) => void }) {
  const { profile } = useAuth()
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const canReview = perms.includes('approvals.create')
  const canDecide = perms.includes('approvals.decide')
  const canPublish = perms.includes('reports.publish')

  const call = async (fn: () => Promise<unknown>) => {
    setBusy(true); setErr(null)
    try { await fn(); onDone() }
    catch (e) { setErr(e instanceof ApiError ? e.message : 'Action failed.') }
    finally { setBusy(false) }
  }

  // approve/return from the drawer — reuses the generic approvals endpoint (checker ≠ maker enforced server-side)
  const decideApproval = (decision: 'approved' | 'returned') =>
    call(() => api.post(`/v1/approvals/${f.approval_request_id}/decide`, { decision, reason: reason || undefined }))

  const [reason, setReason] = useState('')
  const [attName, setAttName] = useState(profile?.user?.name ?? '')
  const [attStmt, setAttStmt] = useState('I certify these figures are complete and accurate to the best of my knowledge.')
  const [subRef, setSubRef] = useState('')
  const [ackRef, setAckRef] = useState('')

  const box = 'w-full bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-3 py-2 text-[13px] outline-none focus:border-[var(--color-sky)]'

  return (
    <Card className="p-4 space-y-3">
      <div className="mono text-[10px] uppercase tracking-widest text-[var(--color-faint)]">Next step</div>
      {err && <div className="text-[12px] text-[var(--color-bad)]">{err}</div>}

      {(f.status === 'draft' || f.status === 'returned') && (canReview
        ? <div className="space-y-2">
            {blocking > 0 && <p className="text-[12px] text-[var(--color-bad)]">Resolve {blocking} blocking validation issue{blocking === 1 ? '' : 's'} before submitting.</p>}
            <Button variant="primary" onClick={() => call(() => api.post(`/v1/filings/${f.filing_id}/submit-for-review`, {}))} disabled={busy || blocking > 0}><Send size={14} /> Submit for approval</Button>
          </div>
        : <p className="text-[12px] text-[var(--color-mute)]">Ready to prepare; a colleague with maker rights submits it for approval.</p>)}

      {f.status === 'in_review' && (canDecide
        ? <div className="space-y-2">
            <p className="text-[12px] text-[var(--color-mute)]">A second pair of eyes (not the preparer) approves or returns this filing.</p>
            <textarea className={box} rows={2} placeholder="Reviewer note (optional)…" value={reason} onChange={e => setReason(e.target.value)} />
            <div className="flex gap-2">
              <Button variant="primary" onClick={() => decideApproval('approved')} disabled={busy}><ShieldCheck size={14} /> Approve</Button>
              <Button variant="ghost" onClick={() => decideApproval('returned')} disabled={busy}>Return to preparer</Button>
            </div>
          </div>
        : <p className="text-[12px] text-[var(--color-mute)]">Waiting for an approver to clear the 4-eyes review.</p>)}

      {f.status === 'approved' && (canPublish
        ? <div className="space-y-2">
            <p className="text-[12px] text-[var(--color-mute)]">Attest — the accountable person certifies the frozen numbers.</p>
            <input className={box} placeholder="Accountable person & role" value={attName} onChange={e => setAttName(e.target.value)} />
            <textarea className={box} rows={2} value={attStmt} onChange={e => setAttStmt(e.target.value)} />
            <Button variant="primary" onClick={() => call(() => api.post(`/v1/filings/${f.filing_id}/attest`, { attestor_name: attName, statement: attStmt }))} disabled={busy || !attName || !attStmt}><Stamp size={14} /> Attest filing</Button>
          </div>
        : <p className="text-[12px] text-[var(--color-mute)]">Approved. Awaiting attestation by an accountable person.</p>)}

      {f.status === 'attested' && (canPublish
        ? <div className="space-y-2">
            <p className="text-[12px] text-[var(--color-mute)]">Submit to the regulator (via the download/portal), then record the submission reference here. The platform doesn't transmit to the regulator itself — this logs the manual submission of record.</p>
            <input className={box} placeholder="Submission / filing reference" value={subRef} onChange={e => setSubRef(e.target.value)} />
            <Button variant="primary" onClick={() => call(() => api.post(`/v1/filings/${f.filing_id}/submit`, { submission_ref: subRef || undefined }))} disabled={busy}><PenLine size={14} /> Record submission</Button>
          </div>
        : <p className="text-[12px] text-[var(--color-mute)]">Attested. Awaiting submission to the regulator.</p>)}

      {f.status === 'submitted' && (canPublish
        ? <div className="space-y-2">
            <p className="text-[12px] text-[var(--color-mute)]">Record the regulator's acknowledgement.</p>
            <input className={box} placeholder="Acknowledgement reference (optional)" value={ackRef} onChange={e => setAckRef(e.target.value)} />
            <Button variant="primary" onClick={() => call(() => api.post(`/v1/filings/${f.filing_id}/accept`, { ack_ref: ackRef || undefined }))} disabled={busy}><CheckCircle2 size={14} /> Mark accepted</Button>
          </div>
        : <p className="text-[12px] text-[var(--color-mute)]">Submitted. Awaiting the regulator's acknowledgement.</p>)}

      {f.status === 'accepted' && <p className="text-[12px]" style={{ color: ST.accepted.fg }}>✓ Accepted by the regulator. This filing is complete.</p>}

      {/* restatement — reopen a filed record as a new version (the old is preserved, superseded) */}
      {(f.status === 'submitted' || f.status === 'accepted') && canPublish && (
        <div className="pt-2 border-t border-[var(--color-line)] space-y-2">
          <p className="text-[11.5px] text-[var(--color-mute)]">Need to correct a filed figure? Restate it — a new version is frozen and this one is preserved as superseded.</p>
          <input className={box} placeholder="Reason for the restatement" value={reason} onChange={e => setReason(e.target.value)} />
          <Button variant="ghost" disabled={busy || !reason}
            onClick={() => call(async () => { const r = await api.post<{ filing_id: string }>(`/v1/filings/${f.filing_id}/restate`, { reason }); onDone(); onOpen(r.filing_id) })}>
            <GitCompareArrows size={14} /> Restate filing
          </Button>
        </div>
      )}

      {f.status === 'superseded' && f.superseded_by && (
        <button onClick={() => onOpen(f.superseded_by!)} className="text-[12px] text-[var(--color-sky)] hover:underline">
          Superseded by a restatement → open it
        </button>
      )}
    </Card>
  )
}
