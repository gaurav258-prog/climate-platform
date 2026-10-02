// The shapes of the EUDR API (api/routers/eudr.py). A plot's reading is what the forest dataset shows after the cut-off —
// a risk the operator weighs (Art. 10), never a verdict.
export interface Reading { outcome: string; loss_ha: number | null; first_loss_year: number | null; reason: string | null; assessed_at: string }
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
}
export interface StatementFiling { filing_id: string; status: string; reference_number: string | null; verification_number: string | null }
export interface Movement {
  movement_id: string; external_ref: string | null; kind: string; actor_role: string; planned_on: string; hs_code: string
  description: string | null; customs_flow: boolean; net_mass_kg: number | null; supplier: string | null; customer: string | null
  n_plots: number; filings: StatementFiling[]
}
export interface Check { rule: string; severity: 'blocking' | 'warning' | 'info'; passed: boolean; message: string; ref: string | null }
export interface StatementPlot { plot_id: string; plot_name: string | null; country: string | null; area_ha: number | null; has_polygon: boolean; coordinate_decimals: number | null; reading: Reading | null; country_risk: string | null }
export interface Statement {
  movement: { movement_id: string; external_ref: string | null; kind: string; actor_role: string; planned_on: string; customs_flow: boolean; scope_in: boolean | null; scope_basis: string | null }
  scope: { in_scope: boolean | null; why: string | null }
  annex_ii: { '1': { name: string | null; address: string | null; eori: string | null; country: string | null }; '2': { hs_code: string; description: string | null; quantity: Record<string, number | string | null> }; '3': { countries: string[] } }
  art9: { supplier: { name: string; address: string | null; email: string | null } | null; customer: { name: string } | null }
  plots: StatementPlot[]; legality_evidence: { evidence_id: string; aspect: string; document_kind: string; document_ref: string | null; plot_id: string | null; movement_id: string | null }[]
  risk_assessment: { path: string; conclusion: string; recorded_at: string } | null
  concerns: { concern_id: string; kind: string; received_on: string; detail: string; steps: { kind: string; on_date: string; conclusion: string | null; detail: string | null }[] }[]
  checks: Check[]
}
export interface Window { open: boolean; closes?: string; why?: string }
export interface DdsEvent { kind: string; at: string; until: string | null; detail: string | null }

export const KIND_LABEL: Record<string, string> = { placing: 'Placing on the market', making_available: 'Making available', export: 'Export' }
export const EVENT_LABEL: Record<string, string> = {
  reference_received: 'Reference number made available', grouped: 'Used for grouping (Art. 5(2))',
  check_notified: 'Check notified (Art. 5(3)(a))', check_ended: 'Check ended', placed_or_exported: 'Placed on the market or exported (Art. 5(3)(b))',
  given_to_customs: 'Reference given to customs (Art. 5(3)(c))', window_extended: 'Window extended by the authority (Art. 5(4))',
  rejected: 'Rejected by the authority (Art. 8)',
}
export const ASPECT_LABEL: Record<string, string> = {
  land_use_rights: 'Land-use rights', environmental_protection: 'Environmental protection', forest_rules: 'Forest-related rules',
  third_party_rights: 'Third parties’ rights', labour_rights: 'Labour rights', human_rights: 'Human rights',
  fpic: 'Free, prior and informed consent', tax_anticorruption_trade_customs: 'Tax, anti-corruption, trade and customs',
  flegt_licence: 'FLEGT licence (Art. 10(3))',
}
export const inp = 'w-full bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-3 py-1.5 text-sm outline-none focus:border-[var(--color-sky)]'
export const lbl = 'block mono text-[10px] uppercase tracking-wide text-[var(--color-faint)] mb-1'
