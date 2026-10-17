import { Scale } from 'lucide-react'
import { Card, SectionHead } from '../../components/ui'
import { StatusChip } from '../../components/StatusChip'
import { InfoButton, messageDetails } from '../../components/Details'
import { day } from './common'
import { useMandates } from './data'

// Which supervisory requirements apply to us, and why: each judged against our regulatory attributes. The main screen
// is a status bar and one line per requirement; the criteria, the legal basis and what is owed open behind 'Why'.

const STATUS: Record<string, { label: string; tone: 'good' | 'warn' | 'neutral'; color: string }> = {
  applies: { label: 'Applies', tone: 'good', color: 'var(--color-good)' },
  cannot_determine: { label: 'Cannot determine', tone: 'warn', color: 'var(--color-warn)' },
  not_applicable: { label: 'Not applicable', tone: 'neutral', color: 'var(--color-slate)' },
}
const GLYPH = (r: boolean | null) => r === true ? ['✓', 'var(--color-good)'] : r === false ? ['✗', 'var(--color-bad)'] : ['?', 'var(--color-warn)']

export function WhatApplies() {
  const q = useMandates()
  const d = q.data
  if (!d || d.mandates.length === 0) return null
  const total = d.mandates.length
  const name = (a: string) => d.definitions[a]?.label ?? 'An attribute'
  return (
    <Card className="p-5 space-y-3">
      <div className="flex items-center gap-2">
        <SectionHead icon={Scale}>What applies to you</SectionHead>
        {d.about && <InfoButton compact details={messageDetails(d.about)} />}
      </div>
      <div>
        <div className="h-2.5 rounded-full overflow-hidden flex bg-[var(--color-panel-2)]">
          {(['applies', 'cannot_determine', 'not_applicable'] as const).map(k => d.summary[k] > 0 &&
            <div key={k} style={{ width: `${(d.summary[k] / total) * 100}%`, background: STATUS[k].color }} />)}
        </div>
        <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2 text-[12px] text-[var(--color-mute)]">
          {(['applies', 'cannot_determine', 'not_applicable'] as const).map(k => (
            <span key={k} className="inline-flex items-center gap-1.5"><span className="w-2 h-2 rounded-full" style={{ background: STATUS[k].color }} />{STATUS[k].label} · {d.summary[k]}</span>))}
        </div>
      </div>
      <div className="divide-y divide-[var(--color-line)]">
        {d.mandates.map(m => {
          const st = STATUS[m.status] ?? STATUS.not_applicable
          return (
            <div key={m.id} className="py-2.5 text-[12.5px] space-y-1">
              <div className="grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-2">
                <StatusChip label={st.label} tone={st.tone} />
                <span className="text-[var(--color-ink)]">{m.title}</span>
                <InfoButton label="Why" details={{ title: m.title, sections: [
                  { heading: 'Criteria', body: <ul className="m-0 p-0 list-none space-y-0.5">{m.checks.map((c, i) => { const [g, col] = GLYPH(c.result); return (
                    <li key={i}><span style={{ color: col }} className="font-semibold mr-1.5">{g}</span>{[c.label, c.tier].filter(Boolean).join(' · ')}</li>) })}</ul> },
                  ...(m.missing.length ? [{ heading: 'Still to state', body: m.missing.map(name).join('; ') }] : []),
                  { heading: 'What is owed', body: [m.deliverable.label, m.deliverable.channel ? `Sent through: ${m.deliverable.channel}` : null,
                    m.deliverable.due ? `Due ${day(m.deliverable.due)}` : m.deliverable.due_rule?.label ? `Due ${m.deliverable.due_rule.label}` : null].filter(Boolean).join('. ') || '—' },
                  { heading: 'Legal basis', body: <a href={m.act.url} target="_blank" rel="noreferrer" className="text-[var(--color-sky)] hover:underline">{m.article.ref} ↗</a> },
                  ...(m.article.excerpt ? [{ heading: 'What the act says', body: <span className="italic">“{m.article.excerpt}”</span> }] : []),
                ] }} />
              </div>
              <div className="flex items-center gap-2 flex-wrap text-[11.5px] text-[var(--color-faint)]">
                {m.tier && <span>{m.tier.label}</span>}
                {m.deliverable.due && <span>Due {day(m.deliverable.due)}</span>}
                {m.missing.map(a => <StatusChip key={a} label={`Needs: ${name(a)}`} tone="warn" />)}
              </div>
            </div>
          )
        })}
      </div>
    </Card>
  )
}
