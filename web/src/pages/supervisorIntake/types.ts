import type { Message } from '../../components/Details'

// The supervisor intake API (api/routers/supervisor.py, services/supervision/intake.py).
export type Kind = 'submission' | 'granular'
export interface Field { id: string; label: string; required?: boolean; type?: string }
export interface Spec {
  submission: { framework: string; template: string; label: string; cell_fields: Field[]; basis_fields: Field[] }
  granular: { label: string; row_fields: Field[]; location_rule: string; precision_label: string }
}
export interface Submission {
  framework: string; template: string; period_label: string; n_cells: number; source_file: string | null; created_at: string
  basis: { scenario?: string; horizon?: string; method_note?: string; at_risk_level?: number } | null
  channel: string | null; submitted_by: string | null
}
export interface Projection { cells: number; anchors_total: number; anchors_covered_mean: number; cells_complete?: number; complete: boolean }
export interface Status {
  entity: string; entity_name: string | null; sector_type: string; intake: Spec
  shadow_book: { n_rows: number; n_located: number; value_eur: number; coverage_value_pct: number | null; projection: Projection }
  submissions: Submission[]
}
export interface Issue { code: string; field: string; label: string; value: string | null }
export interface ProblemType { code: string; field: string; label: string; detail: Message['detail']; count: number; rows: number[] }
export interface Report {
  kind: Kind; fields: Field[]; mapping: Record<string, string | null>; columns: string[]
  n_total: number; n_valid: number; n_error: number; ok: boolean; missing_required: string[]
  errors: { row: number; problems: string[]; issues: Issue[] }[]; problem_types: ProblemType[]
  status_message: Message | null
}
export interface Saved { n_valid: number; n_error: number; period_label: string; message: Message }
