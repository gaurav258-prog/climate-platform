import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate, Link } from 'react-router-dom'
import { ShieldCheck, AlertTriangle, CheckCircle2, Clock, ChevronRight, ChevronDown, Scale, Eye, HelpCircle } from 'lucide-react'
import { api } from '../lib/api'
import { Card, SectionHead, PageHeader, HeroBanner } from '../components/ui'

// Supervisory view — two lenses on the same institution.
//   1) "How regulators read you" (default): for each supervisor of your applicable frameworks — its mission,
//      what it scrutinises, and the questions to expect, each answered by your OWN live figure. Prepares you
//      for supervisory questions before they're asked.
//   2) "Your posture": the inward rollup — every mandatory filing's status, coverage, KRI breaches, readiness
//      and open exceptions. Both are read-only and composed from the same services as the cockpit / KRI board.

// ── posture (inward) ──
interface Filed { period_label: string; status: string }
interface Fw { framework: string; label: string; regulator: string; due_label: string; last_filed: Filed | null; n_filings: number; coverage_pct: number | null; breaches: number | null; breach_kris: string[] }
interface Check { key: string; label: string; ok: boolean; hint: string | null }
interface Exc { rule?: string; message?: string; framework?: string; severity?: string; filings_affected?: number }
interface Posture {
  frameworks: Fw[]
  readiness: { passed: number; total: number; checks: Check[] }
  exceptions: { open: number; top: Exc[] }
  summary: { n_frameworks: number; never_filed: number; total_breaches: number; open_exceptions: number; readiness_pct: number }
}

// ── regulator (outward) ──
interface Answer { label: string; value: number | string | null; fmt: string; breached: boolean }
interface SQ { framework: string; question: string; focus: string; metric: string | null; answer: Answer | null; answered: boolean; review: boolean }
interface Focus { title: string; scrutiny: string; transparency: string }
interface RegChange { title: string; when: string; date: string | null; citation: string; url: string | null }
interface Review { needs_review: boolean; changes: RegChange[] }
interface Supervisor { id: string; name: string; jurisdiction: string; mission: string; reference: string; focus_areas: Focus[]; frameworks: string[]; questions: SQ[]; answered: number; total: number; review: Review }
interface SupResp { supervisors: Supervisor[]; library_reviewed: string; summary: { n_supervisors: number; n_questions: number; n_answered: number; n_review: number } }

const fmtVal = (v: number | string | null, fmt: string) => {
  if (v == null) return '—'
  if (fmt === 'pct') return `${v}%`
  if (fmt === 'eur') { const n = +v; return n >= 1e9 ? `€${(n / 1e9).toFixed(2)}bn` : n >= 1e6 ? `€${(n / 1e6).toFixed(1)}m` : n >= 1e3 ? `€${Math.round(n / 1e3)}k` : `€${n}` }
  return String(v)
}

export default function Oversight() {
  const nav = useNavigate()
  const [tab, setTab] = useState<'regulator' | 'posture'>('regulator')
  const sq = useQuery({ queryKey: ['supervisory'], queryFn: () => api.get<SupResp>('/v1/reg-tasks/supervisory') })
  const pq = useQuery({ queryKey: ['oversight'], queryFn: () => api.get<Posture>('/v1/reg-tasks/oversight'), enabled: tab === 'posture' })

  return (
    <div className="fadeup space-y-6">
      <PageHeader eyebrow="Governance · supervisory view" title="Supervisory view"
        lead="See your book the way your regulators will — what each supervisor scrutinises, the questions to expect, and your own figure that answers each one — then check your filing posture underneath." />

      {/* lens toggle */}
      <div className="flex gap-1 p-1 rounded-xl border border-[var(--color-line)] bg-[var(--color-bg-2)] w-fit">
        {([['regulator', 'How regulators read you', Eye], ['posture', 'Your posture', ShieldCheck]] as const).map(([k, l, Icon]) => (
          <button key={k} onClick={() => setTab(k)}
            className={`inline-flex items-center gap-2 px-3.5 py-2 rounded-lg text-[12.5px] transition ${tab === k ? 'bg-[var(--color-panel)] text-[var(--color-ink)] shadow-[0_0_0_1px_var(--color-line)]' : 'text-[var(--color-mute)] hover:text-[var(--color-ink)]'}`}>
            <Icon size={14} /> {l}
          </button>
        ))}
      </div>

      {tab === 'regulator' ? <RegulatorView q={sq} /> : <PostureView q={pq} nav={nav} />}
    </div>
  )
}

function RegulatorView({ q }: { q: ReturnType<typeof useQuery<SupResp>> }) {
  const d = q.data
  if (q.isLoading) return <Card className="p-10 text-center text-[var(--color-faint)] text-sm">loading…</Card>
  if (!d) return <div className="text-[12.5px] text-[var(--color-bad)]">Could not load the regulator view.</div>
  if (d.supervisors.length === 0) return <Card className="p-8 text-[13px] text-[var(--color-mute)]">No supervisors are wired for this sector yet.</Card>
  const su = d.summary
  return (
    <>
      <HeroBanner eyebrow="How regulators read you"
        title={`${su.n_supervisors} supervisor${su.n_supervisors === 1 ? '' : 's'} · ${su.n_questions} questions to expect`}
        lead="For every framework you file, the regulator that reviews it — its mission, what it scrutinises, and the questions to be ready for. Each is answered by the figure your engine already produces."
        stat={[
          { label: 'Supervisors', value: su.n_supervisors, icon: Scale, tone: 'var(--color-sky)' },
          { label: 'Questions to expect', value: su.n_questions, icon: HelpCircle, tone: 'var(--color-sky)' },
          { label: 'Answered by your data', value: `${su.n_answered} / ${su.n_questions}`, icon: CheckCircle2, tone: su.n_answered === su.n_questions ? '#4FA46E' : '#E8853C' },
        ]} />

      {/* provenance: the questions are a curated, cited library — answers are live; a regulatory change flags a review */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mono text-[10.5px] text-[var(--color-faint)] -mt-1">
        <span>Question library reviewed <b className="text-[var(--color-mute)]">{d.library_reviewed}</b> · answers are computed live from your book.</span>
        {su.n_review > 0 && <span className="inline-flex items-center gap-1" style={{ color: 'var(--color-warn)' }}><AlertTriangle size={11} /> {su.n_review} supervisor{su.n_review === 1 ? '' : 's'} flagged — a regulatory change may affect the questions.</span>}
      </div>

      <div className="space-y-5">
        {d.supervisors.map(s => <SupervisorCard key={s.id} s={s} />)}
      </div>
    </>
  )
}

function SupervisorCard({ s }: { s: Supervisor }) {
  const [showFocus, setShowFocus] = useState(false)
  const [showReview, setShowReview] = useState(false)
  return (
    <Card className="p-0 overflow-hidden">
      {/* header — name, coverage, mission; the dense detail sits behind the toggles below */}
      <div className="px-5 pt-4 pb-3.5 border-b border-[var(--color-line)] bg-[var(--color-bg-2)]">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2"><Scale size={16} className="text-[var(--color-sky)] shrink-0" /><span className="text-[15.5px] font-semibold text-[var(--color-ink)]">{s.name}</span></div>
            <div className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)] mt-1">{s.jurisdiction}</div>
          </div>
          <div className="shrink-0 text-right">
            <div className="text-[17px] font-semibold tabular-nums text-[var(--color-ink)] leading-none">{s.answered}<span className="text-[var(--color-faint)] text-[13px]">/{s.total}</span></div>
            <div className="mono text-[9px] uppercase tracking-wide text-[var(--color-faint)] mt-1">answered by you</div>
          </div>
        </div>
        <p className="text-[13px] text-[var(--color-mute)] mt-3 leading-relaxed max-w-2xl">{s.mission}</p>
        {/* compact controls — review flag + a toggle to reveal what they scrutinise (both collapsed by default) */}
        <div className="flex flex-wrap items-center gap-2 mt-3">
          {s.review.needs_review && (
            <button onClick={() => setShowReview(v => !v)} className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px]" style={{ color: 'var(--color-warn)', background: 'color-mix(in oklab, var(--color-warn) 13%, transparent)' }}>
              <AlertTriangle size={11} /> Review recommended · {s.review.changes.length} {showReview ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
            </button>
          )}
          <button onClick={() => setShowFocus(v => !v)} className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] text-[var(--color-mute)] border border-[var(--color-line-2)] hover:text-[var(--color-ink)] hover:border-[var(--color-sky)] transition">
            {showFocus ? <ChevronDown size={12} /> : <ChevronRight size={12} />} What they scrutinise · {s.focus_areas.length}
          </button>
          <span className="mono text-[9.5px] text-[var(--color-faint)] ml-auto truncate max-w-[46%] text-right" title={s.reference}>{s.reference}</span>
        </div>
        {showReview && s.review.needs_review && (
          <div className="mt-2.5 rounded-lg border border-[var(--color-line)] bg-[var(--color-panel)] px-3.5 py-2.5">
            <div className="text-[12px] text-[var(--color-mute)] leading-snug">These questions were verified against the rules as they stood; the change{s.review.changes.length === 1 ? '' : 's'} below may affect them.</div>
            <div className="flex flex-col gap-1.5 mt-2">
              {s.review.changes.map((c, i) => (
                <div key={i} className="text-[12px] flex flex-wrap items-center gap-x-2">
                  <span className="text-[var(--color-warn)]">▸</span><span className="text-[var(--color-ink)]">{c.title}</span>
                  <span className="mono text-[10px] text-[var(--color-faint)]">· {c.when}</span>
                </div>
              ))}
            </div>
            <Link to="/reg-changes" className="mono text-[10.5px] text-[var(--color-sky)] hover:underline inline-flex items-center gap-1 mt-2">See the regulatory outlook <ChevronRight size={11} /></Link>
          </div>
        )}
      </div>

      {/* what they scrutinise — collapsed by default so the page leads with the questions */}
      {showFocus && (
        <div className="px-5 py-3.5 border-b border-[var(--color-line)]">
          <div className="grid sm:grid-cols-2 gap-2.5">
            {s.focus_areas.map((f, i) => (
              <div key={i} className="rounded-lg border border-[var(--color-line)] px-3.5 py-3">
                <div className="text-[13px] font-medium text-[var(--color-ink)] mb-1">{f.title}</div>
                <div className="text-[12px] text-[var(--color-mute)] leading-snug">{f.scrutiny}</div>
                <div className="mono text-[10.5px] text-[var(--color-faint)] mt-1.5 leading-snug">Seeks: {f.transparency}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* the questions to expect — the hero of the card, answered by your figures */}
      <div className="px-5 py-4">
        <SectionHead icon={HelpCircle} hint="be ready for these — with your own number" className="mb-2.5">Questions to expect</SectionHead>
        <div className="divide-y divide-[var(--color-line)] rounded-lg border border-[var(--color-line)] overflow-hidden">
          {s.questions.map((qq, i) => (
            <div key={i} className="px-4 py-3.5 flex items-start justify-between gap-4">
              <div className="min-w-0">
                <div className="text-[13.5px] text-[var(--color-ink)] leading-snug">{qq.question}</div>
                <div className="flex items-center gap-2 mt-1.5">
                  <span className="mono text-[9.5px] uppercase tracking-wide text-[var(--color-faint)]">{qq.focus}</span>
                  {qq.review && <span className="mono text-[8.5px] uppercase tracking-wide px-1.5 py-0.5 rounded" style={{ color: 'var(--color-warn)', background: 'color-mix(in oklab, var(--color-warn) 15%, transparent)' }} title="A regulatory change may affect this question">review</span>}
                </div>
              </div>
              <div className="shrink-0 text-right">
                {qq.answer
                  ? <>
                      <div className="mono text-[15px] tabular-nums font-medium" style={{ color: qq.answer.breached ? '#fb7185' : 'var(--color-ink)' }}>
                        {fmtVal(qq.answer.value, qq.answer.fmt)}{qq.answer.breached && <AlertTriangle size={11} className="inline ml-1 -mt-0.5" />}
                      </div>
                      <div className="mono text-[9.5px] text-[var(--color-faint)] max-w-[160px] truncate">{qq.answer.label}</div>
                    </>
                  : <div className="mono text-[10.5px] text-[var(--color-mute)] max-w-[170px] leading-snug">{qq.metric ? `in your filing` : 'not produced yet'}</div>}
              </div>
            </div>
          ))}
        </div>
      </div>
    </Card>
  )
}

function PostureView({ q, nav }: { q: ReturnType<typeof useQuery<Posture>>; nav: ReturnType<typeof useNavigate> }) {
  const d = q.data
  const s = d?.summary
  const verdict = s && (
    `${s.n_frameworks} mandatory filing${s.n_frameworks === 1 ? '' : 's'}${s.never_filed > 0 ? `, ${s.never_filed} never filed` : ', all filed'}. `
    + `${s.total_breaches} KRI ${s.total_breaches === 1 ? 'breach' : 'breaches'} and ${s.open_exceptions} open exception${s.open_exceptions === 1 ? '' : 's'}`
    + `${(s.total_breaches + s.open_exceptions) > 0 ? ' need attention' : ' — nothing outstanding'}. Readiness ${s.readiness_pct}%.`
  )
  if (q.isLoading) return <Card className="p-10 text-center text-[var(--color-faint)] text-sm">loading…</Card>
  if (!d || !s) return <div className="text-[12.5px] text-[var(--color-bad)]">Could not load the supervisory view.</div>
  return (
    <>
      <HeroBanner
        eyebrow="Filing posture"
        title={s.total_breaches + s.open_exceptions + s.never_filed > 0 ? 'A few things need your attention.' : 'The house is in order.'}
        lead={verdict}
        stat={[
          { label: 'Mandatory filings', value: s.n_frameworks, icon: ShieldCheck, tone: 'var(--color-sky)' },
          { label: 'Never filed', value: s.never_filed, icon: Clock, tone: s.never_filed > 0 ? '#E8853C' : 'var(--color-good)' },
          { label: 'KRI breaches', value: s.total_breaches, icon: AlertTriangle, tone: s.total_breaches > 0 ? '#D23B3B' : '#4FA46E', pulse: s.total_breaches > 0 },
          { label: 'Open exceptions', value: s.open_exceptions, icon: AlertTriangle, tone: s.open_exceptions > 0 ? '#E8853C' : '#4FA46E' },
          { label: 'Readiness', value: `${s.readiness_pct}%`, icon: CheckCircle2, tone: s.readiness_pct >= 100 ? '#4FA46E' : '#E8853C' },
        ]} />

      <Card className="p-0 overflow-hidden">
        <div className="flex items-center gap-2 px-5 py-3 border-b border-[var(--color-line)]">
          <ShieldCheck size={15} className="text-[var(--color-sky)]" />
          <SectionHead hint="status · coverage · breaches">Mandatory filings</SectionHead>
        </div>
        <div className="hidden sm:grid grid-cols-[2fr_1fr_0.8fr_0.9fr_0.8fr] gap-3 px-5 py-2 border-b border-[var(--color-line)] mono text-[9px] uppercase tracking-wide text-[var(--color-faint)]">
          <span>Filing · regulator</span><span>Last filed</span><span>Produced</span><span>KRI breaches</span><span>Due</span>
        </div>
        <div className="divide-y divide-[var(--color-line)]">
          {d.frameworks.map(f => (
            <button key={f.framework} onClick={() => nav('/compliance')} className="w-full text-left grid grid-cols-2 sm:grid-cols-[2fr_1fr_0.8fr_0.9fr_0.8fr] gap-3 px-5 py-3 items-center hover:bg-[var(--color-bg-2)] transition text-[12.5px]">
              <div className="min-w-0">
                <div className="text-[var(--color-ink)] truncate">{f.label}</div>
                <div className="mono text-[10px] text-[var(--color-faint)] truncate">{f.regulator}</div>
              </div>
              <div className="mono text-[11px]">
                {f.last_filed
                  ? <span className="inline-flex items-center gap-1 text-[var(--color-good)]"><CheckCircle2 size={11} /> {f.last_filed.period_label}</span>
                  : <span className="inline-flex items-center gap-1 text-[var(--color-warn)]"><Clock size={11} /> never</span>}
              </div>
              <div className="mono text-[11.5px] tabular-nums" style={{ color: (f.coverage_pct ?? 0) >= 50 ? 'var(--color-good)' : 'var(--color-mute)' }}>{f.coverage_pct != null ? `${f.coverage_pct}%` : '—'}</div>
              <div className="mono text-[11.5px] tabular-nums" title={f.breach_kris.join(' · ')} style={{ color: (f.breaches ?? 0) > 0 ? '#fb7185' : 'var(--color-faint)' }}>
                {f.breaches == null ? '—' : f.breaches > 0 ? <span className="inline-flex items-center gap-1"><AlertTriangle size={11} /> {f.breaches}</span> : '0'}
              </div>
              <div className="mono text-[10px] text-[var(--color-faint)] flex items-center justify-between gap-1"><span className="truncate">{f.due_label}</span><ChevronRight size={13} className="text-[var(--color-faint)] shrink-0" /></div>
            </button>
          ))}
        </div>
      </Card>

      <div className="grid lg:grid-cols-2 gap-5">
        <div>
          <SectionHead icon={CheckCircle2} hint="is the house in order?" className="mb-2.5">Readiness controls</SectionHead>
          <Card className="p-0 overflow-hidden">
            <div className="divide-y divide-[var(--color-line)]">
              {d.readiness.checks.map(c => (
                <div key={c.key} className="flex items-start gap-2.5 px-5 py-2.5 text-[12.5px]">
                  {c.ok ? <CheckCircle2 size={14} className="text-[var(--color-good)] shrink-0 mt-0.5" /> : <AlertTriangle size={14} className="text-[var(--color-warn)] shrink-0 mt-0.5" />}
                  <div><div className="text-[var(--color-mute)]">{c.label}</div>{!c.ok && c.hint && <div className="mono text-[10px] text-[var(--color-faint)]">{c.hint}</div>}</div>
                </div>
              ))}
            </div>
          </Card>
        </div>
        <div>
          <SectionHead icon={AlertTriangle} hint="from live filings" className="mb-2.5">Open exceptions</SectionHead>
          <Card className="p-0 overflow-hidden">
            {d.exceptions.open === 0
              ? <div className="px-5 py-6 text-[13px] text-[var(--color-faint)]">No open exceptions.</div>
              : <div className="divide-y divide-[var(--color-line)]">
                  {d.exceptions.top.map((e, i) => (
                    <button key={i} onClick={() => nav('/exceptions')} className="w-full text-left flex items-start gap-2.5 px-5 py-2.5 text-[12.5px] hover:bg-[var(--color-bg-2)] transition">
                      <AlertTriangle size={13} className="text-[var(--color-warn)] shrink-0 mt-0.5" />
                      <span className="text-[var(--color-mute)]">
                        {e.message || e.rule || 'exception'}
                        {(e.filings_affected ?? 1) > 1 && <span className="mono text-[10.5px] text-[var(--color-faint)] ml-1.5">· affects {e.filings_affected} filings</span>}
                      </span>
                    </button>
                  ))}
                  {d.exceptions.open > d.exceptions.top.length && <button onClick={() => nav('/exceptions')} className="w-full text-left px-5 py-2 mono text-[10.5px] text-[var(--color-sky)] hover:underline">View all {d.exceptions.open} in the Control Tower →</button>}
                </div>}
          </Card>
        </div>
      </div>
    </>
  )
}
