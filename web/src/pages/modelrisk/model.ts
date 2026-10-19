import type { Message } from '../../components/Details'

// The model-risk register as /v1/model-risk sends it (services/governance/model_risk.py): each card's facts — the
// codes, numbers and dates its review is bound to — and their words from the message catalogue.

export type ReviewState = 'none' | 'stale' | 'overdue' | 'current'
export type Standing = 'calibrated' | 'screening' | 'by_nature' | 'reference' | 'roadmap' | 'ranged' | 'backtested' | 'indicative'
export interface Feed { key: string; name: string; status: string | null; last_refresh: string | null }
export interface Review { review_id: string; reviewer: string; conclusion: string; conclusion_label: string; comment: string | null; next_review_by: string | null; reviewed_at: string }
export interface Fidelity { family_label: string; value: number | null; band: string; band_label: string; published: boolean; floor: number }
export interface Validation {
  level: 'model' | 'hazard'; kind: string; design: string | null; record?: string | null; n_samples?: number | null; skill_grade?: string | null
  passed_gate?: boolean | null; at?: string; n_years?: number | null; baseline?: [number | null, number | null]
  challenger?: { verdict: string; method: string; divergence_pp: number | null; at: string } | null
}
export interface Card {
  ref: string; kind: 'score' | 'impact'; hazard: string; model: string; lifecycle: string; active: boolean; standing: Standing | null
  r2_oos: number | null; gate: number; fidelity: Fidelity | null; validation: Validation | null
  data: { training_vintage?: string | null; training_cells?: number | null; region?: string | null; season_months?: string | number[] | null }
  governance: { approved_at?: string | null; activated_at?: string | null; registered_at?: string | null; events: { from: string | null; to: string; reason: string | null; at: string }[] }
  controls: string[]; card_sha256: string; review: Review | null; review_state: ReviewState
  // the words
  name: string; hazard_name: string | null; kind_name: string; lifecycle_name: string | null; method_name: string | null; method_message: Message | null
  standing_name: string | null; standing_message: Message | null; claim: Message; use: Message; evidence: Message; basis: Message | null; limits: Message[]
  feeds: Feed[]; validation_names: { design: string | null; skill: string | null; verdict: string | null } | null
  governance_names: { approved_by: string | null; activated_by: string | null; events: { who: string | null; to: string | null; from: string | null }[] }
}
export interface Register {
  cards: Card[]; conclusions: Record<string, string>; about: Message; can_review: boolean
  summary: { models: number; in_use: number; carries_figure: number; screens_only: number; unvalidated: number; reviewed_current: number; review_stale: number; review_overdue: number; unreviewed: number }
}

export const REVIEW: Record<ReviewState, { label: string; tone: 'good' | 'warn' | 'bad' | 'neutral' }> = {
  current: { label: 'Reviewed', tone: 'good' }, stale: { label: 'Review stale', tone: 'warn' },
  overdue: { label: 'Review overdue', tone: 'bad' }, none: { label: 'Not reviewed', tone: 'neutral' },
}
// a standing's colour: may carry a figure (green), screens (amber), context or held (grey)
export const STANDING_TONE: Record<Standing, 'good' | 'warn' | 'neutral'> = {
  calibrated: 'good', ranged: 'good', backtested: 'good', screening: 'warn', indicative: 'neutral',
  by_nature: 'neutral', reference: 'neutral', roadmap: 'neutral',
}
export const FEED_TONE: Record<string, 'good' | 'warn' | 'bad' | 'neutral'> = { fresh: 'good', due_soon: 'warn', overdue: 'bad', failed: 'bad', untracked: 'neutral' }
export const FEED_WORD: Record<string, string> = { fresh: 'Fresh', due_soon: 'Due soon', overdue: 'Overdue', failed: 'Failed', untracked: 'Not tracked' }
export const day = (iso?: string | null) => iso ? new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' }) : '—'
