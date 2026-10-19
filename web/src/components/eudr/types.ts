// The shapes of the EUDR API (api/routers/eudr.py). Every explanation the server sends is a catalogue message (label for
// the screen, detail behind the ⓘ); every code it sends is named by the catalogue's names blocks (names.eudr.*, sent
// with the records as `names`). A plot's reading is what the forest dataset shows after the cut-off — a risk the
// operator weighs, never a verdict.
import type { Message } from '../Details'

export type Names = Record<'kind' | 'actor' | 'outcome' | 'event' | 'aspect' | 'size' | 'country_risk' | 'concern' | 'step'
  | 'conclusion' | 'path' | 'source' | 'commodity' | 'book', Record<string, string>>
// A code's customer name; never the code itself.
export const named = (names: Names | undefined, kind: keyof Names, key?: string | null): string =>
  (key ? names?.[kind]?.[key] : null) ?? '—'

export interface Reading { outcome: string; loss_ha: number | null; first_loss_year: number | null; assessed_at: string; msg: Message }
export interface Tally { plots: number; unread: number; no_loss_detected: number; loss_after_cutoff: number; not_assessable: number }
export interface UndertakingStatus { size_class: string; established_on: string | null; country: string; address: string; eori: string | null; effective_from: string
  primary_own_produce: boolean | null; other_system: string | null; is_registration: string | null }
export interface RecordsPlot { plot_id: string; plot_name: string | null; external_ref: string | null; commodity: string; country: string | null; area_ha: number | null; has_polygon: boolean; reading: Reading | null }
export interface Records {
  status: UndertakingStatus | null; on: string
  criteria: Record<string, string>; mitigation: Record<string, string>; aspects: string[]; size_classes: string[]
  plots: RecordsPlot[]; readings_tally: Tally
  entities: { entity_id: string; name: string; country: string | null }[]; entity_id: string | null
  pending: { request_id: string; request_type: string; title: string; movement_id: string | null }[]
  names: Names
}
export interface StatementFiling { filing_id: string; status: string; reference_number: string | null; verification_number: string | null }
export interface Movement {
  movement_id: string; external_ref: string | null; kind: string; actor_role: string; planned_on: string; hs_code: string
  description: string | null; customs_flow: boolean; net_mass_kg: number | null; supplier: string | null; customer: string | null
  n_plots: number; filings: StatementFiling[]
}
export interface Check { rule: string; category: string; severity: 'blocking' | 'warning' | 'info'; passed: boolean; message: string; msg: Message; ref: string | null }
export interface StatementPlot { plot_id: string; plot_name: string | null; external_ref: string | null; country: string | null; area_ha: number | null; has_polygon: boolean; coordinate_decimals: number | null; reading: Reading | null; country_risk: string | null; commodity: string | null }
export interface Party { name: string | null; address?: string | null; email?: string | null }
export interface Statement {
  movement: { movement_id: string; external_ref: string | null; kind: string; actor_role: string; planned_on: string; customs_flow: boolean; scope_in: boolean | null; scope_basis: string | null }
  scope: { in_scope: boolean | null; msg: Message }
  annex_ii: { '1': { name: string | null; address: string | null; eori: string | null; country: string | null }
    '2': { hs_code: string; description: string | null; trade_name: string | null; scientific_names: string[]; quantity: Record<string, number | string | null> }
    '3': { countries: string[] } }
  art9: { supplier: Party | null; customer: Party | null }
  plots: StatementPlot[]; countries: Record<string, string | null>
  legality_evidence: { evidence_id: string; aspect: string; document_kind: string; document_ref: string | null; issued_by: string | null; plot_id: string | null; movement_id: string | null }[]
  risk_assessment: { path: string; conclusion: string; recorded_at: string; requested_by: string | null; approved_by: string | null } | null
  concerns: Concern[]
  checks: Check[]
}
export interface Concern { concern_id: string; kind: string; received_on: string; detail: string
  steps: { kind: string; on_date: string; conclusion: string | null; detail: string | null }[] }
export interface Window { open: boolean; opened: string | null; closes: string | null; closed_by: string | null; msg: Message }
export interface DdsEvent { kind: string; at: string; until: string | null; detail: string | null; msg: Message }

export const inp = 'w-full bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-3 py-1.5 text-sm outline-none focus:border-[var(--color-sky)]'
export const lbl = 'block text-[11.5px] font-medium text-[var(--color-mute)] mb-1'
export const fmtDate = (s: string) => new Date(s).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })
export const fmtWhen = (s: string) => new Date(s).toLocaleString('en-GB', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })
export const kg = (n: number) => `${n.toLocaleString('en-GB', { maximumFractionDigits: 0 })} kg`
