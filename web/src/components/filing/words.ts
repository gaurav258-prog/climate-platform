// The filing journey's words for its own codes (UI standard, 2026-10-16): a code never reaches a screen as-is. Shared by
// the cockpit, its drawer, the checklist and the actions; statuses themselves are lib/hazards statusLabel.

// a filing's lifecycle, in order — the rail and the card stepper
export const STAGES = ['draft', 'in_review', 'approved', 'attested', 'submitted', 'accepted'] as const

// the colour a status reads in (StatusChip tones)
export type Tone = 'good' | 'warn' | 'bad' | 'neutral'
export const STATUS_TONE: Record<string, Tone> = {
  not_started: 'neutral', draft: 'neutral', in_review: 'warn', returned: 'warn', approved: 'good', attested: 'good',
  submitted: 'good', accepted: 'good', rejected: 'bad', superseded: 'neutral', withdrawn: 'neutral',
}

// what happened, for the lifecycle history (services/governance/filings.py _TRANSITIONS and generate/refresh)
export const EVENT: Record<string, string> = {
  generate: 'Prepared', refresh: 'Data refreshed', submit_for_review: 'Sent for approval', approve: 'Approved',
  return: 'Returned to the preparer', reject: 'Rejected', attest: 'Attested', submit: 'Submission recorded',
  accept: 'Accepted by the regulator', supersede: 'Superseded by a restatement', withdraw: 'Withdrawn',
}

// the next action a card offers, by status
export const NEXT_ACTION: Record<string, string> = {
  not_started: 'Prepare', draft: 'Continue', returned: 'Revise', in_review: 'Review', approved: 'Attest',
  attested: 'Submit', submitted: 'Track', accepted: 'View', rejected: 'Revise', superseded: 'View', withdrawn: 'View',
}

// the reporting basis a report was frozen on (report_snapshots reporting_basis): each field's name
export const BASIS_FIELD: Record<string, string> = {
  scenario: 'Scenario', horizon: 'Horizon', reporting_period_end: 'Period end', materiality_threshold: 'Materiality threshold',
  presentation_currency: 'Presented in', regulation_status: 'Rules applied', view: 'Asset facts', shipment: 'Shipment',
  declaration: 'Declaration',
}
export const RULES_IN_FORCE: Record<string, string> = {
  current: 'In force for the period', successor_in_force: 'A replacing act is in force — review', superseded: 'Superseded for the period',
}
export const FACTS_VIEW: Record<string, string> = { joint: 'Yours and ours together', client: 'Your values only', tellumen: 'Ours where we derive them' }

// a check's family (services/governance/filing_validation.py categories)
export const CHECK_FAMILY: Record<string, string> = {
  completeness: 'Completeness', plausibility: 'Plausibility', tie_out: 'Reconciliation', integrity: 'Integrity',
  currency: 'Currency', cross_report: 'Against other filings', scope: 'Scope',
}

// a regulator case's stage (Transmission)
export const CASE_STAGE: Record<string, string> = {
  ready: 'Ready to submit', submitted: 'Submitted', query: 'Regulatory query', answered: 'Answer provided', closed: 'Closed',
}

// who a filing or obligation is for: one legal entity (solo), a group over its subtree (consolidated), or a fund
export function scopeOf(role?: string | null, scope?: string): 'solo' | 'consolidated' | 'product' | 'whole_org' {
  const r = role ?? (scope === 'consolidated' ? 'consolidated' : scope === 'entity' ? 'solo' : 'whole_org')
  return r === 'solo' || r === 'consolidated' || r === 'product' ? r : 'whole_org'
}
export const SCOPE_WORD = { solo: 'Solo', consolidated: 'Consolidated', product: 'Fund', whole_org: 'Whole organisation' } as const

// The Pillar 3 form's tabs, by the template a section prints — its specification's template id (TAB1-3 the qualitative
// tables, T1-T4 transition risk, T5 physical risk, T6-T10 and T9_1-T9_3 the Taxonomy and green asset ratio). Read from
// the id, never from words in the title: 'Template 9.3 - Summary table' is a Taxonomy template, not a qualitative table.
// A section frozen under the report's earlier shape names no template and sits on its own tab.
export type P3Group = 'qual' | 'trans' | 'phys' | 'tax' | 'earlier'
export const EARLIER = 'Earlier report shape'
export function p3Group(templateId: string | null | undefined, title: string): P3Group {
  if (title.startsWith(EARLIER)) return 'earlier'
  const id = templateId ?? (/^\s*Table\s+(\d+)/i.exec(title) ? 'TAB' : `T${/^\s*Template\s+(\d+)/i.exec(title)?.[1] ?? ''}`)
  if (id.startsWith('TAB')) return 'qual'
  const n = parseInt(id.slice(1), 10)
  return n >= 1 && n <= 4 ? 'trans' : n === 5 ? 'phys' : 'tax'
}

export const fmtDate = (s: string) => new Date(s).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })
export const version = (n: number | null | undefined) => (n == null ? '—' : `Version ${n}`)
export const sentence = (s: string) => (s ? s[0].toUpperCase() + s.slice(1) : s)
