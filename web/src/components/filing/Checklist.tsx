import { useState } from 'react'
import { CheckCircle2, AlertTriangle, XCircle, Info, ListChecks, ChevronDown, ChevronRight } from 'lucide-react'
import { Card, SectionHead } from '../ui'
import { HEADING, InfoButton, MESSAGE_HEADING, type Message, type DetailSection } from '../Details'
import { StatusChip } from '../StatusChip'
import { CHECK_FAMILY } from './words'

// The checklist a filing passes before it can be sent for approval (services/governance/filing_validation.py): one bar
// for where it stands, the open checks first — each a short line with its explanation and legal basis one click away —
// and the passed ones folded away.

export interface Finding { rule: string; category: string; severity: 'blocking' | 'warning' | 'info'; passed: boolean; message: string; msg?: Message | null; ref: string | null }
export interface Validation { filing_id: string; findings: Finding[]; blocking: number; warnings: number; checks: number; passed: boolean }

const COLOR = { pass: 'var(--color-good)', blocking: 'var(--color-bad)', warning: 'var(--color-warn)', info: 'var(--color-sky)' }
const tone = (f: Finding) => f.passed ? COLOR.pass : COLOR[f.severity]
const ICON = (f: Finding) => f.passed ? CheckCircle2 : f.severity === 'blocking' ? XCircle : f.severity === 'info' ? Info : AlertTriangle

// A check another rule set states in its own sentence (the ESRS statement, EUDR, a fund's documents, an insurer's
// documents) has no catalogue label yet: its family and outcome name it, the sentence is one click away.
const label = (f: Finding) => f.msg?.label ?? `${CHECK_FAMILY[f.category] ?? 'Check'}: ${f.passed ? 'passed' : f.severity === 'blocking' ? 'must be fixed' : f.severity === 'warning' ? 'to review' : 'for information'}`
function details(f: Finding): DetailSection[] {
  const d = f.msg?.detail ?? { what: f.message }
  return [
    ...(['what', 'why', 'next'] as const).filter(k => d[k]).map(k => ({ heading: MESSAGE_HEADING[k], body: d[k] })),
    ...(f.ref ? [{ heading: 'Legal basis', body: f.ref }] : []),
    { heading: 'Effect on the filing', body: f.severity === 'blocking' ? 'Blocking: the filing cannot be sent for approval while this check fails.'
      : f.severity === 'warning' ? 'To review: the filing can be sent for approval; the approver sees it.' : 'For information only.' },
  ]
}

export function Checklist({ v }: { v: Validation }) {
  const [showPassed, setShowPassed] = useState(false)
  const order = { blocking: 0, warning: 1, info: 2 } as const
  const open = v.findings.filter(f => !f.passed).sort((a, b) => order[a.severity] - order[b.severity])
  const passed = v.findings.filter(f => f.passed)
  const info = open.filter(f => f.severity === 'info').length
  const seg = [{ n: passed.length, c: COLOR.pass, l: 'passed' }, { n: v.warnings, c: COLOR.warning, l: 'to review' },
    { n: v.blocking, c: COLOR.blocking, l: 'blocking' }, { n: info, c: COLOR.info, l: 'for information' }].filter(s => s.n > 0)
  return (
    <Card className="p-4 space-y-3">
      <div className="flex items-center gap-2 flex-wrap">
        <SectionHead icon={ListChecks}>Checks before submission</SectionHead>
        <StatusChip tone={v.blocking ? 'bad' : v.warnings ? 'warn' : 'good'} label={v.blocking ? `${v.blocking} blocking` : v.warnings ? `${v.warnings} to review` : 'All clear'} />
        <InfoButton compact details={{ title: 'Checks before submission', sections: [
          { heading: HEADING.shows, body: 'Every check this report runs on its frozen figures: is everything in scope covered, are the figures plausible, do they add up, and does the report still match its fingerprint.' },
          { heading: HEADING.read, body: 'A blocking check stops the filing being sent for approval. A check to review does not block, but the approver sees it. Select a check for what it means and what to do.' }] }} />
      </div>
      <div className="flex h-2.5 rounded-full overflow-hidden bg-[var(--color-line)]" role="img"
        aria-label={seg.map(s => `${s.n} ${s.l}`).join(', ')}>
        {seg.map(s => <div key={s.l} title={`${s.n} ${s.l}`} style={{ width: `${(100 * s.n) / Math.max(1, v.checks)}%`, background: s.c }} />)}
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11.5px] text-[var(--color-mute)]">
        {seg.map(s => <span key={s.l} className="inline-flex items-center gap-1.5"><span className="w-2 h-2 rounded-full" style={{ background: s.c }} />{s.n} {s.l}</span>)}
      </div>
      {open.length > 0 && <div className="space-y-1.5">{open.map(f => <Row key={f.rule} f={f} />)}</div>}
      {passed.length > 0 && (
        <div>
          <button onClick={() => setShowPassed(o => !o)} aria-expanded={showPassed}
            className="inline-flex items-center gap-1 text-[12px] text-[var(--color-mute)] hover:text-[var(--color-ink)]">
            {showPassed ? <ChevronDown size={13} /> : <ChevronRight size={13} />} {passed.length} {passed.length === 1 ? 'check' : 'checks'} passed
          </button>
          {showPassed && <div className="mt-1.5 space-y-1.5">{passed.map(f => <Row key={f.rule} f={f} />)}</div>}
        </div>)}
    </Card>
  )
}

function Row({ f }: { f: Finding }) {
  const Icon = ICON(f)
  return (
    <div className="flex items-start gap-2">
      <Icon size={14} style={{ color: tone(f) }} className="mt-0.5 shrink-0" />
      <div className="min-w-0 flex-1 flex items-center gap-2 flex-wrap">
        <span className="text-[12.5px]" style={{ color: f.passed ? 'var(--color-mute)' : 'var(--color-ink)' }}>{label(f)}</span>
        <InfoButton compact details={{ title: label(f), sections: details(f) }} />
        <span className="text-[10.5px] text-[var(--color-faint)] ml-auto">{CHECK_FAMILY[f.category] ?? 'Other'}</span>
      </div>
    </div>
  )
}
