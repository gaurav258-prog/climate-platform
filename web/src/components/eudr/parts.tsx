import { useState, type ReactNode } from 'react'
import { AlertTriangle, Check as Tick, CheckCircle2, ChevronDown, ChevronRight, Circle, Info, XCircle } from 'lucide-react'
import clsx from 'clsx'
import { SectionHead } from '../ui'
import { HEADING, InfoButton, MessageLine, type DetailSection } from '../Details'
import { StatusChip } from '../StatusChip'
import { fmtDate, fmtWhen, named, type Check, type DdsEvent, type Names, type Reading, type Window } from './types'
import { OUTCOME_TONE, TONE, checkDetails, messageSections, type Refusal } from './words'

// The EUDR journey's visual parts: the checks as a bar with each open check one click from its meaning, a reading as a
// chip, a count split as a bar, a statement's lifecycle as a stepper, the window to amend or withdraw as a countdown, the events as
// a timeline, and a record's state as a tile. Every word on them is the catalogue's (a check's label, a code's name).

// ── the checks ──

const tone = (c: Check) => c.passed ? TONE.good : c.severity === 'blocking' ? TONE.bad : c.severity === 'warning' ? TONE.warn : TONE.info
const ICON = (c: Check) => c.passed ? CheckCircle2 : c.severity === 'blocking' ? XCircle : c.severity === 'info' ? Info : AlertTriangle

export function Checks({ checks, about }: { checks: Check[]; about: string }) {
  const [showPassed, setShowPassed] = useState(false)
  const order = { blocking: 0, warning: 1, info: 2 } as const
  const open = checks.filter(c => !c.passed).sort((a, b) => order[a.severity] - order[b.severity])
  const passed = checks.filter(c => c.passed)
  const blocking = open.filter(c => c.severity === 'blocking').length
  const review = open.filter(c => c.severity === 'warning').length
  const seg = [{ n: passed.length, c: TONE.good, l: 'passed' }, { n: review, c: TONE.warn, l: 'to review' },
    { n: blocking, c: TONE.bad, l: 'blocking' }, { n: open.length - blocking - review, c: TONE.info, l: 'for information' }]
  return (
    <div className="space-y-2.5">
      <div className="flex items-center gap-2 flex-wrap">
        <SectionHead>Checks</SectionHead>
        <StatusChip tone={blocking ? 'bad' : review ? 'warn' : 'good'} label={blocking ? `${blocking} blocking` : review ? `${review} to review` : 'All clear'} />
        <InfoButton compact details={{ title: 'Checks', sections: [
          { heading: HEADING.shows, body: about },
          { heading: HEADING.read, body: 'A blocking check must be cleared first. A check to review does not block: you decide, and the approver sees it. Select a check for what it means, why, what to do and its legal basis.' }] }} />
      </div>
      <Segments parts={seg} />
      {open.length > 0 && <div className="space-y-1.5">{open.map(c => <CheckRow key={c.rule} c={c} />)}</div>}
      {passed.length > 0 && (
        <div>
          <button type="button" onClick={() => setShowPassed(o => !o)} aria-expanded={showPassed}
            className="inline-flex items-center gap-1 text-[12px] text-[var(--color-mute)] hover:text-[var(--color-ink)]">
            {showPassed ? <ChevronDown size={13} /> : <ChevronRight size={13} />} {passed.length} passed
          </button>
          {showPassed && <div className="mt-1.5 space-y-1.5">{passed.map(c => <CheckRow key={c.rule} c={c} />)}</div>}
        </div>)}
    </div>
  )
}

function CheckRow({ c }: { c: Check }) {
  const Icon = ICON(c)
  return (
    <div className="flex items-start gap-2">
      <Icon size={14} style={{ color: tone(c) }} className="mt-0.5 shrink-0" />
      <span className="text-[12.5px] min-w-0" style={{ color: c.passed ? 'var(--color-mute)' : 'var(--color-ink)' }}>{c.msg.label}</span>
      <InfoButton compact details={{ title: c.msg.label, sections: checkDetails(c) }} />
    </div>
  )
}

// ── a count split as one bar, with its legend ──

export function Segments({ parts, label, empty }: { parts: { n: number; c: string; l: string }[]; label?: string; empty?: string }) {
  const shown = parts.filter(p => p.n > 0)
  const total = shown.reduce((a, p) => a + p.n, 0)
  if (total === 0 && empty) return <p className="text-[12.5px] text-[var(--color-mute)] m-0">{empty}</p>
  return (
    <div className="space-y-1.5">
      <div className="flex h-2.5 rounded-full overflow-hidden bg-[var(--color-line)]" role="img" aria-label={label ?? shown.map(p => `${p.n} ${p.l}`).join(', ')}>
        {shown.map(p => <div key={p.l} title={`${p.n} ${p.l}`} style={{ width: `${(100 * p.n) / Math.max(1, total)}%`, background: p.c }} />)}
      </div>
      <div className="flex flex-wrap gap-x-3.5 gap-y-1 text-[11.5px] text-[var(--color-mute)]">
        {shown.map(p => <span key={p.l} className="inline-flex items-center gap-1.5"><span className="w-2 h-2 rounded-full" style={{ background: p.c }} />{p.n} {p.l}</span>)}
      </div>
    </div>
  )
}

// ── a plot's reading ──

export function ReadingChip({ r, names }: { r: Reading | null; names: Names }) {
  const key = r?.outcome ?? 'unread'
  const c = OUTCOME_TONE[key] ?? TONE.none
  return (
    <span className="inline-flex items-center gap-1">
      <span className="inline-flex items-center gap-1.5 text-[11.5px] font-medium px-2 py-0.5 rounded-full whitespace-nowrap"
        style={{ color: c, background: `color-mix(in oklab, ${c} 13%, transparent)` }}>
        <span className="w-1.5 h-1.5 rounded-full" style={{ background: c }} />{named(names, 'outcome', key)}
      </span>
      {r && <InfoButton compact details={{ title: r.msg.label, sections: [
        ...messageSections(r.msg),
        { heading: 'Read on', body: fmtDate(r.assessed_at) },
        { heading: HEADING.sources, body: 'Global Forest Change tree-cover loss (Hansen et al.), read inside the plot as last drawn.' }] }} />}
    </span>
  )
}

// ── a statement's lifecycle ──

const STAGES = ['draft', 'in_review', 'approved', 'attested', 'submitted', 'accepted'] as const
export function Stepper({ status, last }: { status: string; last: string }) {
  const word: Record<string, string> = { draft: 'Draft', in_review: 'In review', approved: 'Approved', attested: 'Attested', submitted: 'Submitted', accepted: last }
  const at = STAGES.indexOf((status === 'returned' ? 'draft' : status) as typeof STAGES[number])
  if (at < 0) return null
  return (
    <div className="flex items-center" role="list" aria-label="Where it stands">
      {STAGES.map((s, i) => (
        <div key={s} role="listitem" className="flex items-center flex-1 last:flex-none">
          <div className="flex flex-col items-center gap-1">
            <span className="w-5 h-5 rounded-full flex items-center justify-center text-[10px]"
              style={{ background: i <= at ? 'var(--color-sky)' : 'var(--color-panel-2)', color: i <= at ? 'var(--color-on-accent)' : 'var(--color-faint)' }}>
              {i < at || at === STAGES.length - 1 ? <Tick size={11} strokeWidth={3} /> : i + 1}
            </span>
            <span className="text-[10px] whitespace-nowrap hidden sm:block" style={{ color: i <= at ? 'var(--color-ink)' : 'var(--color-faint)' }}>{word[s]}</span>
          </div>
          {i < STAGES.length - 1 && <div className="flex-1 h-0.5 mx-1 sm:mb-4 rounded" style={{ background: i < at ? 'var(--color-sky)' : 'var(--color-panel-2)' }} />}
        </div>))}
    </div>
  )
}

// ── the window to amend or withdraw, as a countdown ──

export function WindowBar({ w }: { w: Window }) {
  const sections = messageSections(w.msg)
  if (!w.opened || !w.closes) return <MessageLine m={w.msg} className="text-[12px] text-[var(--color-mute)]" />
  const a = Date.parse(w.opened), b = Date.parse(w.closes), now = Date.now()
  const used = Math.min(1, Math.max(0, (now - a) / Math.max(1, b - a)))
  const c = w.open ? TONE.good : TONE.none
  return (
    <div className="space-y-1">
      <div className="flex items-center gap-2 text-[12px]">
        <span style={{ color: w.open ? 'var(--color-ink)' : 'var(--color-mute)' }}>{w.msg.label}</span>
        <InfoButton compact details={{ title: w.msg.label, sections }} />
        <span className="ml-auto text-[11.5px] text-[var(--color-mute)] tabular-nums">{w.open ? `until ${fmtWhen(w.closes)}` : fmtWhen(w.closes)}</span>
      </div>
      <div className="h-1.5 rounded-full bg-[var(--color-line)] overflow-hidden" role="img" aria-label={w.msg.label}>
        <div className="h-full rounded-full" style={{ width: `${Math.round(used * 100)}%`, background: c }} />
      </div>
    </div>
  )
}

// ── what happened, as a timeline ──

export function Timeline({ events }: { events: DdsEvent[] }) {
  if (!events.length) return null
  return (
    <ol className="relative ml-1.5 border-l border-[var(--color-line)] space-y-1.5 pl-3">
      {events.map((e, i) => (
        <li key={i} className="relative text-[12px]">
          <span className="absolute -left-[17px] top-1.5 w-2 h-2 rounded-full bg-[var(--color-sky)]" />
          <span className="text-[var(--color-mute)] tabular-nums mr-2">{fmtWhen(e.at)}</span>
          <span className="text-[var(--color-ink)]">{e.msg.label}</span>
          <InfoButton compact className="ml-1" details={{ title: e.msg.label, sections: [
            ...messageSections(e.msg), ...(e.detail ? [{ heading: 'Your note', body: e.detail }] : [])] }} />
        </li>))}
    </ol>
  )
}

// ── a record's state, as a tile ──

export function Tile({ title, state, value, details, action }: {
  title: string; state: 'good' | 'warn' | 'bad' | 'none'; value: ReactNode; details?: DetailSection[]; action?: ReactNode
}) {
  const c = state === 'good' ? TONE.good : state === 'warn' ? TONE.warn : state === 'bad' ? TONE.bad : TONE.none
  const Icon = state === 'good' ? CheckCircle2 : state === 'bad' ? XCircle : state === 'warn' ? AlertTriangle : Circle
  return (
    <div className="rounded-lg border px-3 py-2.5 flex flex-col gap-1.5 min-w-0" style={{ borderColor: `color-mix(in oklab, ${c} 35%, var(--color-line))` }}>
      <div className="flex items-center gap-1.5">
        <Icon size={14} style={{ color: c }} className="shrink-0" />
        <span className="text-[12px] text-[var(--color-mute)]">{title}</span>
        {details && details.length > 0 && <InfoButton compact className="ml-auto" details={{ title, sections: details }} />}
      </div>
      <div className="text-[13px] text-[var(--color-ink)] leading-snug min-w-0 break-words">{value}</div>
      {action && <div className="mt-auto pt-0.5">{action}</div>}
    </div>
  )
}

// ── a refused request, in the catalogue's words ──

export function RefusalLine({ m, className }: { m: Refusal; className?: string }) {
  if (!m) return null
  return <MessageLine m={m} className={clsx('text-[12.5px] text-[var(--color-bad)]', className)} />
}
