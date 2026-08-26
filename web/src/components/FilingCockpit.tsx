import { useState, useEffect } from 'react'
import { useSearchParams, useNavigate, Link } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ShieldCheck, X, CheckCircle2, AlertTriangle, Clock, PenLine, Send, Stamp, XCircle, Info, GitCompareArrows, Download, RadioTower, ChevronLeft, RefreshCw, FileText, ArrowRight, CalendarClock, Flame, ListChecks, Check } from 'lucide-react'
import { api, ApiError, download } from '../lib/api'
import { toast } from '../lib/toast'
import { frameworkLabel } from '../lib/hazards'
import { useAuth } from '../lib/auth'
import { Card, Button, SectionHead } from './ui'
import FilingLineage from './FilingLineage'
import FilingVariance from './FilingVariance'
import FilingBasis from './FilingBasis'
import FilingPreflight from './FilingPreflight'
import FilingCoverage from './FilingCoverage'
import DisclosureFlags from './DisclosureFlags'
import ProvidedData from './ProvidedData'
import FilingForm from './FilingForm'

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
  export_formats?: string[]; superseded_by?: string | null
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
  // A filing opens as a FULL-WINDOW view, driven by the ?filing=<id> URL param so the browser Back button
  // closes it and links (Control Tower, KRI history) land straight on the full page. openId mirrors the URL.
  useEffect(() => { setOpenId(params.get('filing')) }, [params])
  const openFiling = (id: string) => { const p = new URLSearchParams(params); p.set('filing', id); setParams(p) }
  const closeDrawer = () => { const p = new URLSearchParams(params); p.delete('filing'); setParams(p, { replace: true }) }

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

  const regByFw: Record<string, string> = {}
  frameworks.forEach(f => { regByFw[f.framework] = f.regulator })
  const filedC = (o: Obligation) => ['submitted', 'accepted'].includes(o.filing_status)
  const needAction = obligations.filter(o => !filedC(o)).length
  const overdueCount = obligations.filter(o => o.overdue && !filedC(o)).length
  const filedCount = obligations.filter(filedC).length
  // the single most-pressing thing: the soonest deadline still needing action
  const nextDue = obligations.filter(o => !filedC(o)).sort((a, b) => a.days_to_due - b.days_to_due)[0]

  return (
    <div className="space-y-6">
      {/* ── COCKPIT HERO — the reporting posture at a glance: what's live, what's pressing, where you stand ── */}
      <CockpitHero total={obligations.length} needAction={needAction} overdue={overdueCount} filed={filedCount} nextDue={nextDue} />

      {/* ── YOUR FILINGS — the one thing most users touch: what's due and how far along it is ── */}
      <div>
        <div className="flex items-center gap-3 mb-3 px-1">
          <SectionHead icon={FileText}>Your filings</SectionHead>
          <div className="h-px flex-1 bg-[var(--color-line)]" />
          <span className="mono text-[10.5px] text-[var(--color-faint)]">{needAction ? `${needAction} need action` : 'all filed'}</span>
        </div>
        {obligations.length === 0
          ? <Card className="p-6 text-[13px] text-[var(--color-faint)]">No obligations for the current period.</Card>
          : <div className="space-y-3">
              {obligations.map(o => (
                <FilingCard key={o.obligation_id} o={o} regulator={regByFw[o.framework]} canPrepare={canPrepare}
                  onOpen={() => o.filing_id && openFiling(o.filing_id)} onPrepare={() => setPreflightFw(o.framework)} />
              ))}
            </div>}
      </div>

      {/* ── DETAILS — everything else, one click away instead of stacked open ── */}
      <DetailsTabs filings={filings} onOpen={openFiling} />

      {openId && <FilingDrawer filingId={openId} onClose={closeDrawer} onChanged={refresh} onOpen={openFiling} />}
      {preflightFw && <FilingPreflight framework={preflightFw} onClose={() => setPreflightFw(null)}
        onGenerated={(id) => { setPreflightFw(null); refresh(); setOpenId(id) }} />}
    </div>
  )
}

// The hero: a calm, wide status band that answers "how are my filings doing?" before any detail. An ambient
// disclose-hued glow, a Fraunces headline, and four live counters (due · to action · overdue · filed).
function CockpitHero({ total, needAction, overdue, filed, nextDue }:
  { total: number; needAction: number; overdue: number; filed: number; nextDue?: Obligation }) {
  const allClear = needAction === 0 && total > 0
  const dueLine = nextDue
    ? nextDue.overdue
      ? `${Math.abs(nextDue.days_to_due)} days overdue`
      : nextDue.days_to_due === 0 ? 'due today' : `in ${nextDue.days_to_due} days`
    : '—'
  const tiles: { label: string; value: string | number; tone: string; icon: React.ComponentType<{ size?: number }>; pulse?: boolean }[] = [
    { label: 'Due this period', value: total, tone: 'var(--color-sky)', icon: CalendarClock },
    { label: 'Need action', value: needAction, tone: needAction ? 'var(--color-warn)' : 'var(--color-good)', icon: ListChecks },
    { label: 'Overdue', value: overdue, tone: overdue ? 'var(--color-bad)' : 'var(--color-faint)', icon: Flame, pulse: overdue > 0 },
    { label: 'Filed', value: filed, tone: 'var(--color-good)', icon: CheckCircle2 },
  ]
  return (
    <div className="relative overflow-hidden rounded-[18px] border border-[var(--color-line)]"
      style={{ background: 'linear-gradient(135deg, var(--color-panel-2) 0%, var(--color-panel) 46%, var(--color-bg-2) 100%)' }}>
      {/* ambient glows — disclose teal top-right, brand blue bottom-left */}
      <div aria-hidden className="pointer-events-none absolute -top-28 -right-16 h-72 w-72 rounded-full drift"
        style={{ background: 'radial-gradient(circle, color-mix(in oklab, var(--stage-disclose, #0f7a5f) 42%, transparent), transparent 68%)' }} />
      <div aria-hidden className="pointer-events-none absolute -bottom-32 -left-10 h-72 w-72 rounded-full"
        style={{ background: 'radial-gradient(circle, color-mix(in oklab, var(--color-blue) 24%, transparent), transparent 70%)' }} />
      <div className="relative px-6 py-6 grid gap-6 lg:grid-cols-[1.1fr_1.4fr] items-center">
        <div>
          <p className="mono text-[11px] uppercase tracking-[0.22em] m-0" style={{ color: 'var(--stage-disclose, var(--color-blue))' }}>Disclose · Reporting cockpit</p>
          <h2 className="display text-[27px] leading-[1.12] font-semibold mt-2 mb-2 text-[var(--color-ink)]" style={{ textWrap: 'balance' } as React.CSSProperties}>
            {allClear ? 'Every filing is on track.' : overdue > 0 ? 'A filing needs you now.' : 'On top of every deadline.'}
          </h2>
          <p className="text-[13px] text-[var(--color-mute)] max-w-md leading-relaxed">
            Prepare, review with four eyes, attest and submit — each number frozen and hash-verified behind the filing.
            {nextDue && <> Next up: <span className="text-[var(--color-ink)]">{nextDue.label}</span> · <span style={{ color: nextDue.overdue ? 'var(--color-bad)' : 'var(--color-warn)' }}>{dueLine}</span>.</>}
          </p>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {tiles.map(t => (
            <div key={t.label} className="rounded-2xl border border-[var(--color-line)] bg-[color-mix(in_oklab,var(--color-panel)_70%,transparent)] backdrop-blur px-3.5 py-3.5">
              <div className="flex items-center gap-1.5 mb-2">
                <span className="relative inline-flex items-center justify-center h-6 w-6 rounded-lg" style={{ background: `color-mix(in oklab, ${t.tone} 16%, transparent)`, color: t.tone }}>
                  {t.pulse && <span className="absolute inline-flex h-full w-full rounded-lg animate-ping" style={{ background: t.tone, opacity: 0.35 }} />}
                  <t.icon size={13} />
                </span>
                <span className="mono text-[9px] uppercase tracking-wide text-[var(--color-faint)] leading-tight">{t.label}</span>
              </div>
              <div className="display text-[30px] leading-none font-semibold tabular-nums" style={{ color: t.tone }}>{t.value}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

// One obligation as an action card: deadline, a compact lifecycle stepper, readiness (from validation), and the
// single next action. Replaces the old requirements + calendar sections (which listed the same obligations twice).
const CARD_STEPS: { key: string; label: string }[] = [
  { key: 'draft', label: 'Draft' }, { key: 'in_review', label: 'Review' }, { key: 'approved', label: 'Approved' },
  { key: 'attested', label: 'Attested' }, { key: 'filed', label: 'Filed' },
]
// which action the next button offers, by current status
const ACTION: Record<string, string> = {
  not_started: 'Prepare', draft: 'Continue', returned: 'Revise', in_review: 'Review',
  approved: 'Attest', attested: 'Submit', submitted: 'Track', accepted: 'View', rejected: 'Revise', superseded: 'View',
}

function FilingCard({ o, regulator, canPrepare, onOpen, onPrepare }:
  { o: Obligation; regulator?: string; canPrepare: boolean; onOpen: () => void; onPrepare: () => void }) {
  const val = useQuery({
    queryKey: ['filing-validation-mini', o.filing_id],
    queryFn: () => api.get<Validation>(`/v1/filings/${o.filing_id}/validation`),
    enabled: !!o.filing_id,
  })
  const v = val.data
  const status = o.filing_status || 'not_started'
  const filed = ['submitted', 'accepted'].includes(status)
  // stepper progress: index of the current stage (submitted/accepted → the last "Filed" step)
  const stageIdx = filed ? 4 : Math.max(0, CARD_STEPS.findIndex(s => s.key === (status === 'returned' ? 'draft' : status)))
  const readyPct = v && v.checks > 0 ? Math.round(100 * (v.checks - v.blocking - v.warnings) / v.checks) : null
  const act = ACTION[status] ?? 'Open'
  const canGo = o.filing_id ? true : canPrepare

  // one accent hue per card, keyed to urgency — drives the medallion, the ring and the hover glow
  const urgency = filed ? 'var(--color-good)' : o.overdue ? 'var(--color-bad)' : 'var(--color-warn)'
  const ringTone = v && v.blocking > 0 ? 'var(--color-warn)' : 'var(--color-good)'

  return (
    <Card className="group relative p-0 overflow-hidden transition-all duration-300 hover:-translate-y-[2px] hover:border-[var(--color-sky)]"
      style={{ boxShadow: 'none' }}
      onClick={undefined}>
      {/* hover glow, tinted by urgency — fades in only on hover */}
      <div aria-hidden className="pointer-events-none absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-300"
        style={{ boxShadow: `inset 0 1px 0 0 color-mix(in oklab, ${urgency} 40%, transparent), 0 12px 44px -20px color-mix(in oklab, var(--color-blue) 60%, transparent)` }} />
      <div className="relative px-5 py-4 flex items-center gap-4">
        {/* framework medallion */}
        <div className="hidden sm:flex h-11 w-11 rounded-xl items-center justify-center shrink-0 transition-transform duration-300 group-hover:scale-105"
          style={{ background: `color-mix(in oklab, ${urgency} 15%, transparent)`, color: urgency }}>
          {filed ? <CheckCircle2 size={19} /> : <FileText size={19} />}
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap mb-2.5">
            <span className="text-[15px] text-[var(--color-ink)] font-medium">{o.label}</span>
            <span className="mono text-[9.5px] uppercase tracking-wide text-[var(--color-faint)]">{regulator ?? 'EBA'} · {o.frequency}</span>
            {filed
              ? <span className="mono text-[9.5px] uppercase px-2 py-0.5 rounded-full" style={{ color: 'var(--color-good)', background: 'color-mix(in oklab, var(--color-good) 16%, transparent)' }}>filed</span>
              : <span className="mono text-[9.5px] uppercase px-2 py-0.5 rounded-full whitespace-nowrap inline-flex items-center gap-1"
                  style={o.overdue ? { color: 'var(--color-bad)', background: 'color-mix(in oklab, var(--color-bad) 16%, transparent)' } : { color: 'var(--color-warn)', background: 'color-mix(in oklab, var(--color-warn) 16%, transparent)' }}>
                  {o.overdue && <span className="inline-block h-1.5 w-1.5 rounded-full animate-pulse" style={{ background: 'var(--color-bad)' }} />}
                  {o.overdue ? `${Math.abs(o.days_to_due)}d overdue · due ${fmtDate(o.due_date)}` : `due ${fmtDate(o.due_date)}`}</span>}
          </div>
          <CardStepper idx={stageIdx} />
          <div className="mono text-[11px] mt-2.5 flex items-center gap-2">
            {status === 'not_started'
              ? <span className="text-[var(--color-faint)]">Not started</span>
              : readyPct != null
                ? (v!.blocking > 0
                    ? <span style={{ color: 'var(--color-warn)' }}>{v!.blocking} to fix before review</span>
                    : v!.warnings > 0 ? <span className="text-[var(--color-mute)]">clear · {v!.warnings} to review</span>
                      : <span className="inline-flex items-center gap-1.5" style={{ color: 'var(--color-good)' }}><Check size={12} /> all checks clear</span>)
                : <span className="text-[var(--color-faint)]">{ST[status]?.label ?? status}</span>}
          </div>
        </div>

        <div className="flex items-center gap-3 shrink-0">
          {readyPct != null && <ReadyRing pct={readyPct} tone={ringTone} />}
          {canGo
            ? <button onClick={o.filing_id ? onOpen : onPrepare}
                className="group/btn inline-flex items-center gap-1.5 mono text-[12px] font-medium px-4 py-2.5 rounded-lg text-[var(--color-on-accent)] bg-[var(--color-sky)] hover:bg-[var(--color-blue)] transition whitespace-nowrap">
                {act} <ArrowRight size={13} className="transition-transform group-hover/btn:translate-x-0.5" /></button>
            : <span className="mono text-[10.5px] text-[var(--color-faint)]">awaiting preparer</span>}
        </div>
      </div>
    </Card>
  )
}

// A small circular readiness gauge — the % of validation checks already clear, at a glance.
function ReadyRing({ pct, tone }: { pct: number; tone: string }) {
  const r = 15.5, c = 2 * Math.PI * r
  return (
    <svg width="42" height="42" viewBox="0 0 42 42" className="hidden sm:block shrink-0" role="img" aria-label={`${pct}% ready`}>
      <circle cx="21" cy="21" r={r} fill="none" stroke="var(--color-line-2)" strokeWidth="3.5" />
      <circle cx="21" cy="21" r={r} fill="none" stroke={tone} strokeWidth="3.5" strokeLinecap="round"
        strokeDasharray={c} strokeDashoffset={c * (1 - pct / 100)} transform="rotate(-90 21 21)"
        style={{ transition: 'stroke-dashoffset .7s cubic-bezier(.2,.8,.2,1)' }} />
      <text x="21" y="21" textAnchor="middle" dominantBaseline="central" className="mono"
        style={{ fontSize: 10.5, fontWeight: 600, fill: 'var(--color-ink)' }}>{pct}</text>
    </svg>
  )
}

function CardStepper({ idx }: { idx: number }) {
  return (
    <div className="flex items-center" style={{ maxWidth: 440 }}>
      {CARD_STEPS.map((s, i) => {
        const done = i < idx, cur = i === idx
        return (
          <div key={s.key} className="flex flex-col items-center gap-1.5 relative flex-1">
            {i < CARD_STEPS.length - 1 && <div className="absolute top-[6px] left-1/2 w-full h-[2px] rounded-full" style={{ background: done ? 'var(--color-sky)' : 'var(--color-line)' }} />}
            <span className="relative z-10 flex items-center justify-center" style={{ width: 13, height: 13 }}>
              {cur && <span className="absolute inline-flex h-full w-full rounded-full animate-ping" style={{ background: 'var(--color-sky)', opacity: 0.55 }} />}
              <span className="rounded-full flex items-center justify-center"
                style={done ? { width: 13, height: 13, background: 'var(--color-sky)' }
                  : cur ? { width: 13, height: 13, background: 'var(--color-panel)', border: '2px solid var(--color-sky)', boxShadow: '0 0 0 3px color-mix(in oklab, var(--color-sky) 22%, transparent)' }
                    : { width: 11, height: 11, background: 'var(--color-line)' }}>
                {done && <Check size={8} strokeWidth={3.5} style={{ color: 'var(--color-on-accent)' }} />}
              </span>
            </span>
            <span className="mono text-[8px] uppercase tracking-wide whitespace-nowrap" style={{ color: (done || cur) ? 'var(--color-ink)' : 'var(--color-faint)' }}>{s.label}</span>
          </div>
        )
      })}
    </div>
  )
}

// Everything that isn't "act on a filing" — collapsed behind a tab strip instead of stacked open on the landing.
function DetailsTabs({ filings, onOpen }: { filings: FilingSummary[]; onOpen: (id: string) => void }) {
  const [tab, setTab] = useState<'coverage' | 'data' | 'basis' | 'history'>('coverage')
  const flags = useQuery({ queryKey: ['disclosure-flags'], queryFn: () => api.get<{ flags: unknown[] }>('/v1/decisions/disclosure-flags') })
  const nFlags = flags.data?.flags?.length ?? 0
  const TABS: { k: typeof tab; label: string; badge?: number }[] = [
    { k: 'coverage', label: 'Coverage' }, { k: 'data', label: 'Your data', badge: nFlags },
    { k: 'basis', label: 'Basis' }, { k: 'history', label: 'History' },
  ]
  return (
    <Card className="p-0 overflow-hidden">
      <div className="flex gap-1 px-2.5 py-2 border-b border-[var(--color-line)] bg-[var(--color-bg-2)] flex-wrap">
        {TABS.map(t => (
          <button key={t.k} onClick={() => setTab(t.k)}
            className={`mono text-[11px] uppercase tracking-wide px-3 py-1.5 rounded-md transition flex items-center gap-1.5 ${tab === t.k ? 'bg-[var(--color-panel)] text-[var(--color-ink)] shadow-[0_0_0_1px_var(--color-line)]' : 'text-[var(--color-mute)] hover:text-[var(--color-ink)]'}`}>
            {t.label}{!!t.badge && <span className="text-[9px] px-1.5 rounded-full" style={{ color: '#e8b24c', background: '#e8b24c22' }}>{t.badge}</span>}
          </button>
        ))}
      </div>
      <div className="p-4">
        {tab === 'coverage' && <FilingCoverage />}
        {tab === 'data' && <div className="space-y-4"><DisclosureFlags /><ProvidedData /></div>}
        {tab === 'basis' && <FilingBasis />}
        {tab === 'history' && (
          filings.length === 0
            ? <div className="px-1 py-5 text-[13px] text-[var(--color-faint)]">No filings yet.</div>
            : <div className="divide-y divide-[var(--color-line)]">
                {filings.map(f => (
                  <button key={f.filing_id} onClick={() => onOpen(f.filing_id)}
                    className="w-full text-left px-1 py-3 flex items-center gap-4 hover:bg-[var(--color-panel)] transition rounded">
                    <div className="flex-1 min-w-0">
                      <div className="text-[13.5px] text-[var(--color-ink)] truncate flex items-center gap-2">{f.label} <span className="text-[var(--color-faint)]">· {f.period_label}</span>{f.scope && f.scope !== 'organisation' && <ScopeChip scope={f.scope} name={f.entity_name} />}</div>
                      <div className="mono text-[10.5px] text-[var(--color-faint)]">v{f.snapshot_version ?? '—'} · {f.created_by ?? '—'} · {fmtDate(f.created_at)}{f.submission_ref ? ` · ref ${f.submission_ref}` : ''}</div>
                    </div>
                    <Chip status={f.status} />
                  </button>
                ))}
              </div>
        )}
      </div>
    </Card>
  )
}

// The onward hand-off from a filing to the surfaces where its remaining work lives — turns the cockpit from a
// dead-end into a conveyor. Each chip deep-links to that surface, pre-filtered to this filing where supported.
function SubmitReadiness({ filingId, status, blocking }: { filingId: string; status: string; blocking: number }) {
  if (['submitted', 'accepted'].includes(status)) return null   // filed — nothing left to submit
  const inReview = status === 'in_review'
  const chip = (tone: string) => `inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[12px] transition hover:border-[var(--color-sky)] hover:text-[var(--color-sky)] ${tone}`
  const neutral = 'border-[var(--color-line-2)] text-[var(--color-mute)]'
  return (
    <Card className="p-3">
      <div className="flex items-center flex-wrap gap-2">
        <span className="mono text-[10px] uppercase tracking-widest text-[var(--color-faint)] mr-1">To submit</span>
        <Link to={`/exceptions?filing=${filingId}`}
          className={chip(blocking > 0 ? 'border-[var(--color-warn)] text-[var(--color-warn)]' : 'border-[var(--color-line-2)] text-[var(--color-good)]')}>
          <AlertTriangle size={12} /> {blocking > 0 ? `${blocking} blocking exception${blocking === 1 ? '' : 's'} to clear` : 'exceptions clear'} <ArrowRight size={12} />
        </Link>
        <Link to="/approvals" className={chip(inReview ? 'border-[var(--color-sky)] text-[var(--color-sky)]' : neutral)}>
          <ListChecks size={12} /> {inReview ? 'Awaiting 2nd-eyes' : 'Four-eyes sign-off'} <ArrowRight size={12} />
        </Link>
        <Link to={`/tasks?filing=${filingId}`} className={chip(neutral)}>
          <Flame size={12} /> Team tasks <ArrowRight size={12} />
        </Link>
      </div>
    </Card>
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
    <div className="fixed inset-0 z-50 overflow-y-auto bg-[var(--color-bg)]">
      <div className="relative w-full max-w-6xl mx-auto min-h-full pb-16">
        <div className="sticky top-0 z-10 flex items-center justify-between px-6 py-3 border-b border-[var(--color-line)] bg-[var(--color-bg)]/95 backdrop-blur">
          <button onClick={onClose} className="inline-flex items-center gap-1.5 mono text-[11px] uppercase tracking-wide text-[var(--color-mute)] hover:text-[var(--color-ink)]"><ChevronLeft size={15} /> Back to reports</button>
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

            {/* submit-readiness — thread the Disclose stage onward so the drawer is never a dead-end:
                the concrete blockers, sign-off and team work for THIS filing, each one click away */}
            <SubmitReadiness filingId={filingId} status={f.status} blocking={val.data?.blocking ?? 0} />

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
                          onClick={() => download(`/v1/filings/${f.filing_id}/export?format=${fmt}`, `${f.framework}-${f.period_label}-v${f.snapshot!.version}.${fmt}`).catch(() => toast.error('Could not download the export.'))}
                          className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-line-2)] px-2.5 py-1 text-[11.5px] text-[var(--color-mute)] hover:border-[var(--color-sky)] hover:text-[var(--color-sky)] transition">
                          <Download size={12} /> {fmt.toUpperCase()}
                        </button>
                      ))}
                      {/* auditor / supervisor evidence bundle — methodology, validation record, 4-eyes, provenance, hashed manifest */}
                      <button onClick={() => download(`/v1/filings/${f.filing_id}/assurance-pack`, `assurance-${f.framework}-${f.period_label}.zip`).catch(() => toast.error('Could not download the assurance pack.'))}
                        title="Auditor-ready evidence bundle: methodology, validation record, 4-eyes approvals, provenance, hashed manifest"
                        className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-line-2)] px-2.5 py-1 text-[11.5px] text-[var(--color-mute)] hover:border-[var(--color-sky)] hover:text-[var(--color-sky)] transition">
                        <ShieldCheck size={12} /> Assurance pack
                      </button>
                    </div>
                  </div>
                )}
              </Card>
            )}

            {/* the final form — the frozen disclosure as the submittable datapoint form */}
            <FilingForm filingId={filingId} />

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
    } catch (e) { toast.error(e instanceof ApiError ? e.message : 'Could not open the transmission case.') }
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
      {STAGES.map((s, i) => {
        const done = i < idx, cur = i === idx
        return (
          <div key={s} className="flex items-center flex-1 last:flex-none">
            <div className="flex flex-col items-center gap-1.5">
              <span className="relative flex items-center justify-center">
                {cur && <span className="absolute inline-flex h-6 w-6 rounded-full animate-ping" style={{ background: ST[s].fg, opacity: 0.4 }} />}
                <span className="w-6 h-6 rounded-full flex items-center justify-center text-[10px] mono relative z-10"
                  style={{ background: i <= idx ? ST[s].fg : 'var(--color-panel-2)', color: i <= idx ? 'var(--color-on-accent)' : 'var(--color-faint)',
                    boxShadow: cur ? `0 0 0 3px color-mix(in oklab, ${ST[s].fg} 22%, transparent)` : 'none' }}>
                  {done ? <Check size={12} strokeWidth={3} /> : i + 1}
                </span>
              </span>
              <span className="text-[9px] mono uppercase tracking-wide" style={{ color: i <= idx ? ST[s].fg : 'var(--color-faint)' }}>{ST[s].label}</span>
            </div>
            {i < STAGES.length - 1 && <div className="flex-1 h-0.5 mx-1 mb-4 rounded" style={{ background: i < idx ? ST[STAGES[i + 1]].fg : 'var(--color-panel-2)' }} />}
          </div>
        )
      })}
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

      {(f.status === 'draft' || f.status === 'returned') && (
        <div className="flex items-center gap-2 mb-2">
          <Button variant="ghost" onClick={() => call(() => api.post(`/v1/filings/${f.filing_id}/refresh`, {}))} disabled={busy}>
            <RefreshCw size={13} /> Refresh data
          </Button>
          <span className="text-[11px] text-[var(--color-faint)]">Re-freeze this draft from the current book — pulls in newly provided inputs (e.g. EPC / IFRS-9 / maturity).</span>
        </div>
      )}

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
