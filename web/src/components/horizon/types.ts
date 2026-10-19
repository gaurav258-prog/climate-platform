import type { Message } from '../Details'

// What GET /v1/me/globe sends (services/intelligence/front_door.py): every figure, name and explanation is the server's.
export interface Fact { label: string; money?: number; flow?: boolean; text?: string }
export interface Asset {
  id: string; ref: string; name: string; kind: string; kind_name: string; lat: number; lon: number; region: string
  value_eur: number
  score: (number | null)[]            // headline score at each stop (aligned with GlobeResp.stops)
  hazard: (string | null)[]           // the hazard that leads it at each stop
  at_risk: (boolean | null)[]         // at or above the stated at-risk level at each stop; null = no level stated
  facts: Fact[]; adaptations: string[]; notice: Message | null; decide: boolean; record_href: string
}
export interface Stop { key: string; year: number; scenario: string; label: string }
export interface Check { key: string; ok: boolean; message: Message; fix_href: string | null; fix_label: string | null }
export interface AtRisk { level: number | null; by_stop: { n: number; value_eur: number }[] | null; message: Message; gap: string | null }
export interface Supervision { entities: number; filings_expected: number; filings_outstanding: number; open_requests: number }
export interface GlobeResp {
  audience: 'book' | 'supervisor'; sector: string; noun: string
  scenario: { key: string; name: string }; scenarios: { key: string; name: string }[]; stops: Stop[]
  assets: Asset[]; n_assets: number; book_value_eur: number; n_unscored: number; at_risk: AtRisk
  readiness: { passed: number; total: number; checks: Check[] }
  my_scope: { roles: { key: string; name: string }[]; raised_pending: number }
  supervisor: Supervision | null
}
export interface Task {
  key: string; message: Message; severity: string; bucket: string; due: Message | null
  action: { label: string; href: string }
}
export interface Ent { entity_id: string; name: string; kind: string; kind_name: string; n_assets: number }
