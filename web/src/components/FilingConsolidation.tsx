// What a group filing froze about its consolidation (E75/E78): the rule its entities were weighted on, the governing
// text quoted, where the text sets no scope of its own the reading Tellumen declares, and the sign-off of the exact rule
// file the filing was computed on (two people sign its sha on the regulatory-change route; an edit voids it).

interface Ref { ref: string; quote: string }
interface Declaration { declared_by: string; declared: string; reading: string }
interface Signoff { sha256: string; approved: boolean; one_person: boolean; signed: { role: string; by: string; signed_at: string; sole_reviewer: boolean }[] }
export interface Consolidation {
  framework: string; regime: string; label: string; basis: 'text' | 'declared'
  factors: { full: string; proportional: string; equity: string }; refs: Ref[]; declaration?: Declaration
  rule_file?: { framework: string; version: string; sha256: string }; signoff: Signoff | null
}

const td = 'py-1 pr-3 text-[11.5px] border-t border-[var(--color-line)] align-top'

export default function FilingConsolidation({ c }: { c: Consolidation }) {
  const d = c.declaration
  return (
    <div className="rounded-xl border border-[var(--color-line-2)] p-3 mb-3">
      <div className="flex items-baseline justify-between gap-3 flex-wrap mb-1">
        <div className="mono text-[10px] uppercase tracking-widest text-[var(--color-faint)]">Consolidation · <span className="text-[var(--color-ink)]">{c.label}</span></div>
        <div className="text-[11px] text-[var(--color-mute)]">{c.basis === 'text' ? 'Set by the governing text' : 'Declared reading'}</div>
      </div>
      <div className="text-[11.5px] mb-2 text-[var(--color-mute)]">
        Subsidiaries: {c.factors.full === 'full' ? 'in full' : c.factors.full} · joint holdings: {c.factors.proportional === 'proportional' ? 'by share held' : c.factors.proportional} · equity-method holdings: {c.factors.equity === 'excluded' ? 'not consolidated' : c.factors.equity}
      </div>
      <table className="w-full"><tbody>{c.refs.map(r => (
        <tr key={r.ref}><td className={`${td} mono whitespace-nowrap`}>{r.ref}</td><td className={`${td} text-[var(--color-mute)]`}>“{r.quote}”</td></tr>
      ))}</tbody></table>
      {d && (
        <div className="text-[11.5px] mt-2">
          {d.reading} <span className="text-[var(--color-faint)]">Declared by {d.declared_by}, {d.declared}.</span>
        </div>
      )}
      <div className="mono text-[10.5px] mt-2" style={{ color: c.signoff?.approved && !c.signoff.one_person ? 'var(--color-good)' : 'var(--color-warn)' }}>
        {!c.signoff ? 'Frozen before the consolidation rules were signed on the change route.'
          : !c.signoff.signed.length ? `Rule file ${c.signoff.sha256.slice(0, 10)} — not signed yet (needs a regulatory reviewer and an engineer).`
          : <>Rule file {c.signoff.sha256.slice(0, 10)} — {c.signoff.signed.map(g => `${g.role} ${g.by} ${g.signed_at.slice(0, 10)}`).join(' · ')}
              {c.signoff.one_person ? ' · one person signed both roles — not a four-eyes review' : !c.signoff.approved ? ' · second sign-off outstanding' : ''}</>}
      </div>
    </div>
  )
}
