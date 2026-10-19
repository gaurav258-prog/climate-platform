// The shapes /v1/esrs/statement returns (services.governance.esrs_document.freeze + esrs_checks). Explanations arrive as
// catalogue messages (msg, *_msg, gap_msgs): a label for the screen, the detail behind its ⓘ.
import type { Message } from '../Details'

export interface Datapoint {
  key: string; lane: 'computed' | 'provided' | 'derived' | 'same_as'; concept: string | string[]; label?: string
  value?: any; by_horizon?: Record<string, number | null> | null; unit?: string | null; currency?: string | null
  status: string; gap?: string | null; gap_msgs?: Message[]; previous?: any
}
export interface CmpRow {
  concept: string; item: string; standard: string; label?: string; current: any; reported: any; comparative: any; source: string | null
  status: string; relief?: string; relief_msg?: Message | null; difference?: any; answer?: { reason?: string; significant?: boolean; impracticable?: string } | null
}
export interface Comparatives {
  previous_period_end: string; reported: { source: string | null; filing_id: string | null; source_msg?: Message }
  reliefs: { all: string | null; not_same_as_first_set: string | null; all_msg?: Message | null }; needs: string[]; needs_msg?: Message | null
  rows: CmpRow[]; missing: string[]; topics_first_time: Record<string, any>
}
export interface Omission { reason: 'not_material' | 'condition_not_applicable' | 'phase_in'; phase_in?: string; statement?: string; scope?: string }
export interface Item {
  id: string; kind: string; label: string; parent: string | null; note: string | null; obligation: string | null
  conditional: string | null; narrative: boolean | null
  status: 'printed' | 'filled' | 'missing' | 'omitted'; answer?: any; omission?: Omission; datapoints?: Datapoint[]
}
export interface Section { standard: string; title: string; topic: { material: boolean; explanation?: string } | null; items: Item[] }
export interface Role { role: string; parent_name?: string | null; parent_report_ref?: string | null; status?: string }
export interface Scope {
  required: boolean | null; point: string | null; ref?: string; quote?: string; reason?: string; fy_start: string; msg?: Message
  conditions?: { fact: string; met: boolean | null; label?: string; msg?: Message }[]; missing?: string[]
  derogation?: { ref: string; quote: string; stated: string }
}
export interface Check { rule: string; category: string; severity: 'blocking' | 'warning' | 'info'; passed: boolean; message: string; msg?: Message; ref?: string | null }
export interface Statement {
  document_report: {
    esrs_version: string; period_end: string; reporting_entity_id: string | null; org_has_entities: boolean
    role: Role | null; scope_check: Scope; period_closed: boolean
    statement: { sites: { site_id: string; name: string; weight: number }[]; scope: { basis: string; gaps: string[]; basis_msg?: Message; gap_msgs?: Message[] } }
    comparatives: Comparatives
    sections: Section[]
  }
  spec: { version: string; act: string }
  checks: Check[]
  phase_ins: { id: string; ref: string; quote: string }[]
}
