import { HEADING, InfoButton, type Details } from './Details'
import { StatusChip } from './StatusChip'

// What a group filing froze about its consolidation (E75/E78): the rule its entities were weighted on as chips, whether
// the governing text sets it or Tellumen declares a reading, and whether the exact rule file was signed by two people on
// the regulatory-change route (an edit voids it). The governing text, quoted, the declaration and who signed when are
// one click away.

interface Ref { ref: string; quote: string }
interface Declaration { declared_by: string; declared: string; reading: string }
interface Signoff { sha256: string; approved: boolean; one_person: boolean; signed: { role: string; role_label?: string; by: string; signed_at: string; sole_reviewer: boolean }[] }
export interface Consolidation {
  framework: string; regime: string; label: string; basis: 'text' | 'declared'
  factors: { full: string; proportional: string; equity: string }; refs: Ref[]; declaration?: Declaration
  rule_file?: { framework: string; version: string; sha256: string }; signoff: Signoff | null
}

// how a holding counts (data/reference/consolidation/regimes.json factors)
const HOW: Record<string, string> = { full: 'in full', proportional: 'by share held', equity: 'by the equity method', excluded: 'not consolidated' }
const day = (s: string) => new Date(s).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })

function signoffChip(s: Signoff | null): { label: string; tone: 'good' | 'warn' } {
  if (!s) return { label: 'Frozen before the rules were signed', tone: 'warn' }
  if (!s.signed.length) return { label: 'Rules not signed yet', tone: 'warn' }
  if (s.one_person) return { label: 'Signed by one person', tone: 'warn' }
  return s.approved ? { label: 'Rules signed by two people', tone: 'good' } : { label: 'Second sign-off outstanding', tone: 'warn' }
}

export default function FilingConsolidation({ c }: { c: Consolidation }) {
  const d = c.declaration, s = c.signoff, chip = signoffChip(s)
  const law: Details = { title: c.label, sections: [
    { heading: HEADING.shows, body: c.basis === 'text' ? 'The governing text sets how the group is consolidated for this report.' : 'The governing text sets no scope of its own, so Tellumen declares the reading below.' },
    ...c.refs.map(r => ({ heading: r.ref, body: `“${r.quote}”` })),
    ...(d ? [{ heading: 'Declared reading', body: `${d.reading} Declared by ${d.declared_by}, ${d.declared}.` }] : []),
  ] }
  const signed: Details = { title: 'Sign-off of the consolidation rules', sections: [
    { heading: HEADING.shows, body: 'The rules this filing was computed on are signed by a regulatory reviewer and an engineer, two different people. Any edit to the rules voids their sign-off.' },
    ...(s ? s.signed.map(g => ({ heading: g.role_label ?? 'Sign-off', body: `${g.by}, ${day(g.signed_at)}` })) : []),
    ...(s?.one_person ? [{ heading: 'Not a four-eyes review', body: 'One person signed both roles.' }] : []),
    ...(s ? [{ heading: 'Fingerprint of the rules', body: s.sha256 }] : []),
  ] }
  return (
    <div className="rounded-xl border border-[var(--color-line-2)] p-3 mb-3">
      <div className="flex items-center justify-between gap-3 flex-wrap mb-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-[10.5px] uppercase tracking-widest text-[var(--color-faint)]">Consolidation</span>
          <span className="text-[12.5px] text-[var(--color-ink)]">{c.label}</span>
          <InfoButton compact details={law} />
        </div>
        <StatusChip label={c.basis === 'text' ? 'Set by the governing text' : 'Declared reading'} tone="neutral" />
      </div>
      <div className="flex flex-wrap gap-2 text-[11.5px]">
        {([['Subsidiaries', c.factors.full], ['Joint holdings', c.factors.proportional], ['Equity-method holdings', c.factors.equity]] as const).map(([who, how]) => (
          <span key={who} className="rounded-md border border-[var(--color-line)] px-2 py-1 text-[var(--color-mute)]">{who}: <span className="text-[var(--color-ink)]">{HOW[how] ?? 'as the rule sets'}</span></span>
        ))}
      </div>
      <div className="flex items-center gap-1.5 mt-2"><StatusChip label={chip.label} tone={chip.tone} /><InfoButton compact details={signed} /></div>
    </div>
  )
}
