import { useState, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, FileText, ArrowRight, CalendarClock, Flame, ListChecks, Check } from 'lucide-react'
import { api } from '../lib/api'
import { statusLabel } from '../lib/hazards'
import { useAuth } from '../lib/auth'
import { pressable } from '../lib/pressable'
import { Card, SectionHead, HeroBanner } from './ui'
import { HEADING, InfoButton } from './Details'
import { StatusChip } from './StatusChip'
import FilingBasis from './FilingBasis'
import FilingPreflight from './FilingPreflight'
import FilingCoverage from './FilingCoverage'
import DisclosureFlags from './DisclosureFlags'
import ProvidedData from './ProvidedData'
import FilingDrawer from './filing/FilingDrawer'
import { ScopeChip } from './filing/ScopeChip'
import { NEXT_ACTION, STATUS_TONE, fmtDate, sentence, version, type Tone } from './filing/words'

// The reporting cockpit for every sector: what is due and how far along it is (one card per obligation, the
// deadlines on a time line), everything else behind four tabs, and a full-window filing that runs the controlled
// lifecycle — prepare → review (four eyes) → attest → submit → accept — over its frozen, fingerprinted report.

interface Obligation { obligation_id: string; framework: string; label: string; period_label: string; due_date: string; frequency: string; filing_id: string | null; filing_status: string; days_to_due: number; overdue: boolean; entity_id: string | null; entity_name: string | null; filing_role: string; period_end: string; fund_id?: string | null; fund_name?: string | null }
interface Framework { framework: string; label: string; frequency: string; regulator: string; basis: string }
interface FilingSummary { filing_id: string; framework: string; label: string; period_label: string; status: string; snapshot_version: number | null; submission_ref: string | null; created_by: string | null; created_at: string; entity_name?: string | null; scope?: string; filing_role?: string | null; fund_name?: string | null }
interface Validation { blocking: number; warnings: number; checks: number; passed: boolean }

const isFiled = (s: string) => s === 'submitted' || s === 'accepted'
const dueWords = (o: Obligation) => o.overdue ? `${Math.abs(o.days_to_due)} days overdue` : o.days_to_due === 0 ? 'due today' : `due in ${o.days_to_due} days`

export default function FilingCockpit() {
  const { profile } = useAuth()
  const qc = useQueryClient()
  const [params, setParams] = useSearchParams()
  const [openId, setOpenId] = useState<string | null>(null)
  const [prepare, setPrepare] = useState<Obligation | null>(null)
  // A filing opens as a full-window view from the ?filing=<id> URL param, so Back closes it and links land on it.
  useEffect(() => { setOpenId(params.get('filing')) }, [params])
  const openFiling = (id: string) => { const p = new URLSearchParams(params); p.set('filing', id); setParams(p) }
  const closeFiling = () => { const p = new URLSearchParams(params); p.delete('filing'); setParams(p, { replace: true }) }
  const canPrepare = (profile?.permissions ?? []).includes('approvals.create')

  const obl = useQuery({ queryKey: ['obligations'], queryFn: () => api.get<{ obligations: Obligation[] }>('/v1/obligations') })
  const fils = useQuery({ queryKey: ['filings'], queryFn: () => api.get<{ filings: FilingSummary[] }>('/v1/filings') })
  const fw = useQuery({ queryKey: ['frameworks'], queryFn: () => api.get<{ frameworks: Framework[] }>('/v1/filings/frameworks') })
  const refresh = () => { qc.invalidateQueries({ queryKey: ['obligations'] }); qc.invalidateQueries({ queryKey: ['filings'] }) }

  const obligations = obl.data?.obligations ?? []
  const frameworks = fw.data?.frameworks ?? []
  if (frameworks.length === 0 && !fw.isLoading) return null   // a sector with no filings wired yet — the cockpit is hidden

  const regulator: Record<string, string> = Object.fromEntries(frameworks.map(f => [f.framework, f.regulator]))
  const open = obligations.filter(o => !isFiled(o.filing_status))
  const overdue = open.filter(o => o.overdue).length
  const nextDue = [...open].sort((a, b) => a.days_to_due - b.days_to_due)[0]

  return (
    <div className="space-y-6">
      <HeroBanner eyebrow="Reporting"
        title={obligations.length > 0 && open.length === 0 ? 'Every filing is filed.' : overdue > 0 ? 'A filing needs you now.' : 'On top of every deadline.'}
        lead={nextDue ? `Next: ${nextDue.label}, ${dueWords(nextDue)}.` : undefined}
        stat={[
          { label: 'Due this period', value: obligations.length, tone: 'var(--color-sky)', icon: CalendarClock },
          { label: 'Need action', value: open.length, tone: open.length ? 'var(--color-warn)' : 'var(--color-good)', icon: ListChecks },
          { label: 'Overdue', value: overdue, tone: overdue ? 'var(--color-bad)' : 'var(--color-faint)', icon: Flame, pulse: overdue > 0 },
          { label: 'Filed', value: obligations.length - open.length, tone: 'var(--color-good)', icon: CheckCircle2 },
        ]} />

      {obligations.length > 0 && <DeadlineLine obligations={obligations} onPick={o => o.filing_id ? openFiling(o.filing_id) : canPrepare && setPrepare(o)} />}

      <div>
        <div className="flex items-center gap-3 mb-3 px-1">
          <SectionHead icon={FileText}>Your filings</SectionHead>
          <div className="h-px flex-1 bg-[var(--color-line)]" />
          <StatusChip tone={open.length ? 'warn' : 'good'} label={open.length ? `${open.length} need action` : 'All filed'} />
        </div>
        {obligations.length === 0
          ? <Card className="p-6 text-[13px] text-[var(--color-faint)]">Nothing is due for the current period.</Card>
          : <div className="space-y-3">
              {obligations.map(o => (
                <FilingCard key={o.obligation_id} o={o} regulator={regulator[o.framework]} canPrepare={canPrepare}
                  onOpen={() => o.filing_id && openFiling(o.filing_id)} onPrepare={() => setPrepare(o)} />
              ))}
            </div>}
      </div>

      <DetailsTabs filings={fils.data?.filings ?? []} onOpen={openFiling} />

      {openId && <FilingDrawer filingId={openId} onClose={closeFiling} onChanged={refresh} onOpen={openFiling} />}
      {prepare && <FilingPreflight framework={prepare.framework} obligation={prepare} onClose={() => setPrepare(null)}
        onGenerated={id => { setPrepare(null); refresh(); openFiling(id) }} />}
    </div>
  )
}

// The deadlines on one time line: today, and each due date as a dot coloured by where its reports stand (red if one is
// overdue, amber if one is open, green when all are filed) and sized by how many fall on it; the next one due is ringed.
// A dot opens its filing (or prepares it); a date with several reports scrolls to their cards.
function DeadlineLine({ obligations, onPick }: { obligations: Obligation[]; onPick: (o: Obligation) => void }) {
  const day = 86_400_000
  const today = new Date(new Date().toDateString()).getTime()
  const groups = Object.values(obligations.reduce<Record<string, Obligation[]>>((g, o) => ((g[o.due_date] ??= []).push(o), g), {}))
  const dues = groups.map(g => new Date(g[0].due_date).getTime())
  const from = Math.min(today, ...dues) - 7 * day, to = Math.max(today, ...dues) + 7 * day
  const x = (t: number) => `${(100 * (t - from)) / (to - from)}%`
  const tone = (g: Obligation[]) => g.some(o => o.overdue && !isFiled(o.filing_status)) ? 'var(--color-bad)'
    : g.some(o => !isFiled(o.filing_status)) ? 'var(--color-warn)' : 'var(--color-good)'
  const next = [...obligations].filter(o => !isFiled(o.filing_status)).sort((a, b) => a.days_to_due - b.days_to_due)[0]
  const pick = (g: Obligation[]) => g.length === 1 ? onPick(g[0]) : document.getElementById(`ob-${g[0].obligation_id}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  const months: number[] = []
  for (let d = new Date(new Date(from).getFullYear(), new Date(from).getMonth() + 1, 1); d.getTime() <= to; d.setMonth(d.getMonth() + 1)) months.push(d.getTime())
  const every = Math.max(1, Math.ceil(months.length / 8))
  return (
    <Card className="px-5 pt-4 pb-3">
      <div className="flex items-center gap-2 mb-1">
        <SectionHead icon={CalendarClock}>Deadlines</SectionHead>
        <InfoButton compact details={{ title: 'Deadlines', sections: [
          { heading: HEADING.shows, body: 'Each dot is a due date of a report due this period; a larger dot holds several reports. The blue line is today.' },
          { heading: HEADING.read, body: 'Red: a report on that date is overdue. Amber: one is still open. Green: all are filed. The ringed dot is the next one due. Select a dot to open its filing, or to see the reports due that day.' },
          { heading: HEADING.sources, body: "Your organisation's obligations: each report that applies to it, with the deadline its rules set." },
        ] }} />
      </div>
      <div className="relative h-16 mx-3">
        <div className="absolute left-0 right-0 top-7 h-px bg-[var(--color-line-2)]" />
        {months.filter((_, i) => i % every === 0).map(m => (
          <div key={m} className="absolute top-10 -translate-x-1/2 text-[10.5px] text-[var(--color-faint)] whitespace-nowrap" style={{ left: x(m) }}>
            {new Date(m).toLocaleDateString('en-GB', { month: 'short', year: '2-digit' })}
          </div>))}
        <div className="absolute top-3 bottom-6 w-px bg-[var(--color-sky)]" style={{ left: x(today) }} />
        <div className="absolute top-0 -translate-x-1/2 text-[10.5px] font-medium text-[var(--color-sky)]" style={{ left: x(today) }}>Today</div>
        {groups.map(g => {
          const size = 12 + 3 * Math.min(g.length - 1, 4), c = tone(g)
          const label = g.length === 1 ? `${g[0].label}, due ${fmtDate(g[0].due_date)}` : `${g.length} reports due ${fmtDate(g[0].due_date)}`
          return (
            <span key={g[0].due_date} {...pressable(() => pick(g), { label })} title={g.map(o => `${o.label} · ${statusLabel(o.filing_status)}`).join('\n')}
              className="absolute top-7 -translate-x-1/2 -translate-y-1/2 rounded-full cursor-pointer transition hover:scale-110 flex items-center justify-center text-[9.5px] font-semibold"
              style={{ left: x(new Date(g[0].due_date).getTime()), width: size, height: size, background: c, color: 'var(--color-on-accent)',
                boxShadow: next && g.includes(next) ? `0 0 0 3px var(--color-panel), 0 0 0 5px ${c}` : '0 0 0 2px var(--color-panel)' }}>
              {g.length > 1 ? g.length : null}
            </span>)
        })}
      </div>
    </Card>
  )
}

// One obligation as an action card: its due date, a lifecycle stepper, readiness from the checklist, the next action.
const CARD_STEPS = [{ key: 'draft', label: 'Draft' }, { key: 'in_review', label: 'Review' }, { key: 'approved', label: 'Approved' },
  { key: 'attested', label: 'Attested' }, { key: 'filed', label: 'Filed' }]

function FilingCard({ o, regulator, canPrepare, onOpen, onPrepare }:
  { o: Obligation; regulator?: string; canPrepare: boolean; onOpen: () => void; onPrepare: () => void }) {
  const val = useQuery({ queryKey: ['filing-validation-mini', o.filing_id], enabled: !!o.filing_id,
    queryFn: () => api.get<Validation>(`/v1/filings/${o.filing_id}/validation`) })
  const v = val.data
  const status = o.filing_status || 'not_started'
  const filed = isFiled(status)
  const stage = filed ? 4 : Math.max(0, CARD_STEPS.findIndex(s => s.key === (status === 'returned' ? 'draft' : status)))
  const ready = v && v.checks > 0 ? Math.round(100 * (v.checks - v.blocking - v.warnings) / v.checks) : null
  const urgency = filed ? 'var(--color-good)' : o.overdue ? 'var(--color-bad)' : 'var(--color-warn)'
  const dueTone: Tone = filed ? 'good' : o.overdue ? 'bad' : 'warn'
  return (
    <Card className="group relative p-0 overflow-hidden transition-all duration-300 hover:-translate-y-[2px] hover:border-[var(--color-sky)]">
      <div id={`ob-${o.obligation_id}`} className="relative px-5 py-4 flex items-center gap-4 scroll-mt-24">
        <div className="hidden sm:flex h-11 w-11 rounded-xl items-center justify-center shrink-0"
          style={{ background: `color-mix(in oklab, ${urgency} 15%, transparent)`, color: urgency }}>
          {filed ? <CheckCircle2 size={19} /> : <FileText size={19} />}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <span className="text-[15px] text-[var(--color-ink)] font-medium">{o.label}</span>
            <ScopeChip role={o.filing_role} name={o.fund_name ?? o.entity_name} />
          </div>
          <div className="flex items-center gap-2 flex-wrap mb-2.5 text-[12px] text-[var(--color-mute)]">
            <span>{[regulator, sentence(o.frequency), o.period_label].filter(Boolean).join(' · ')}</span>
            <StatusChip tone={dueTone} label={filed ? `Filed · was due ${fmtDate(o.due_date)}` : `${sentence(dueWords(o))} · ${fmtDate(o.due_date)}`} />
          </div>
          <CardStepper idx={stage} />
          <div className="text-[12px] mt-2.5 flex items-center gap-2">
            {status === 'not_started' ? <span className="text-[var(--color-faint)]">Not started</span>
              : v == null ? <span className="text-[var(--color-faint)]">{statusLabel(status)}</span>
              : v.blocking > 0 ? <span style={{ color: 'var(--color-warn)' }}>{v.blocking} to fix before review</span>
              : v.warnings > 0 ? <span className="text-[var(--color-mute)]">Clear · {v.warnings} to review</span>
              : <span className="inline-flex items-center gap-1.5" style={{ color: 'var(--color-good)' }}><Check size={12} /> All checks clear</span>}
          </div>
        </div>
        <div className="flex items-center gap-3 shrink-0">
          {ready != null && <ReadyRing pct={ready} tone={v!.blocking > 0 ? 'var(--color-warn)' : 'var(--color-good)'} />}
          {o.filing_id || canPrepare
            ? <button onClick={o.filing_id ? onOpen : onPrepare}
                className="group/btn inline-flex items-center gap-1.5 text-[12.5px] font-medium px-4 py-2.5 rounded-lg text-[var(--color-on-accent)] bg-[var(--color-sky)] hover:bg-[var(--color-blue)] transition whitespace-nowrap">
                {NEXT_ACTION[status] ?? 'Open'} <ArrowRight size={13} className="transition-transform group-hover/btn:translate-x-0.5" /></button>
            : <span className="text-[11.5px] text-[var(--color-faint)]">Awaiting a preparer</span>}
        </div>
      </div>
    </Card>
  )
}

// The share of checklist items already clear, as a ring.
function ReadyRing({ pct, tone }: { pct: number; tone: string }) {
  const r = 15.5, c = 2 * Math.PI * r
  return (
    <svg width="42" height="42" viewBox="0 0 42 42" className="hidden sm:block shrink-0" role="img" aria-label={`${pct}% of checks clear`}>
      <circle cx="21" cy="21" r={r} fill="none" stroke="var(--color-line-2)" strokeWidth="3.5" />
      <circle cx="21" cy="21" r={r} fill="none" stroke={tone} strokeWidth="3.5" strokeLinecap="round" strokeDasharray={c}
        strokeDashoffset={c * (1 - pct / 100)} transform="rotate(-90 21 21)" style={{ transition: 'stroke-dashoffset .7s cubic-bezier(.2,.8,.2,1)' }} />
      <text x="21" y="21" textAnchor="middle" dominantBaseline="central" style={{ fontSize: 10.5, fontWeight: 600, fill: 'var(--color-ink)' }}>{pct}</text>
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
                  : cur ? { width: 13, height: 13, background: 'var(--color-panel)', border: '2px solid var(--color-sky)' }
                  : { width: 11, height: 11, background: 'var(--color-line)' }}>
                {done && <Check size={8} strokeWidth={3.5} style={{ color: 'var(--color-on-accent)' }} />}
              </span>
            </span>
            <span className="text-[10px] whitespace-nowrap" style={{ color: (done || cur) ? 'var(--color-ink)' : 'var(--color-faint)' }}>{s.label}</span>
          </div>
        )
      })}
    </div>
  )
}

// Everything that is not acting on a filing, behind a tab strip.
function DetailsTabs({ filings, onOpen }: { filings: FilingSummary[]; onOpen: (id: string) => void }) {
  const [tab, setTab] = useState<'coverage' | 'data' | 'basis' | 'history'>('coverage')
  const flags = useQuery({ queryKey: ['disclosure-flags'], queryFn: () => api.get<{ flags: unknown[] }>('/v1/decisions/disclosure-flags') })
  const nFlags = flags.data?.flags?.length ?? 0
  const TABS: { k: typeof tab; label: string; badge?: number }[] = [
    { k: 'coverage', label: 'Coverage' }, { k: 'data', label: 'Your data', badge: nFlags }, { k: 'basis', label: 'Basis' }, { k: 'history', label: 'History' }]
  return (
    <Card className="p-0 overflow-hidden">
      <div className="flex gap-1 px-2.5 py-2 border-b border-[var(--color-line)] bg-[var(--color-bg-2)] flex-wrap" role="tablist">
        {TABS.map(t => (
          <button key={t.k} role="tab" aria-selected={tab === t.k} onClick={() => setTab(t.k)}
            className={`text-[12.5px] px-3 py-1.5 rounded-md transition flex items-center gap-1.5 ${tab === t.k ? 'bg-[var(--color-panel)] text-[var(--color-ink)] shadow-[0_0_0_1px_var(--color-line)]' : 'text-[var(--color-mute)] hover:text-[var(--color-ink)]'}`}>
            {t.label}{!!t.badge && <span className="text-[10px] px-1.5 rounded-full" style={{ color: 'var(--color-warn)', background: 'color-mix(in oklab, var(--color-warn) 14%, transparent)' }}>{t.badge}</span>}
          </button>
        ))}
      </div>
      <div className="p-4">
        {tab === 'coverage' && <FilingCoverage />}
        {tab === 'data' && <div className="space-y-4"><DisclosureFlags /><ProvidedData /></div>}
        {tab === 'basis' && <FilingBasis />}
        {tab === 'history' && (filings.length === 0
          ? <div className="px-1 py-5 text-[13px] text-[var(--color-faint)]">No filings yet.</div>
          : <div className="divide-y divide-[var(--color-line)]">
              {filings.map(f => (
                <button key={f.filing_id} onClick={() => onOpen(f.filing_id)}
                  className="w-full text-left px-1 py-3 flex items-center gap-4 hover:bg-[var(--color-panel)] transition rounded">
                  <div className="flex-1 min-w-0">
                    <div className="text-[13.5px] text-[var(--color-ink)] truncate flex items-center gap-2">{f.label} <span className="text-[var(--color-faint)]">· {f.period_label}</span><ScopeChip role={f.filing_role} scope={f.scope} name={f.fund_name ?? f.entity_name} /></div>
                    <div className="text-[11.5px] text-[var(--color-faint)]">{[version(f.snapshot_version), f.created_by, fmtDate(f.created_at)].filter(Boolean).join(' · ')}</div>
                  </div>
                  <StatusChip value={f.status} tone={STATUS_TONE[f.status]} />
                </button>
              ))}
            </div>)}
      </div>
    </Card>
  )
}
