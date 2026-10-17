// What the supervisory portal reads from the server, and the shared queries (one cache entry each, so the page's
// figures, the timeline and the panels read the same answer).
import { useQuery } from '@tanstack/react-query'
import { api } from '../../lib/api'
import type { Message } from '../../components/Details'

// ── deadlines (the filing calendar's reports) ──
export interface CalEvent { date: string; kind: string; title: string; status: string | null; overdue: boolean
  period?: string | null; frequency?: string | null; entity?: string | null; set_by?: string | null }
export interface Calendar { events: CalEvent[]; today: string }
export const useCalendar = () => useQuery({ queryKey: ['portal-calendar'], queryFn: () => api.get<Calendar>('/v1/reg-tasks/calendar') })

// ── requests from the supervisor ──
export interface DueRequest { request_id: string; title: string; reference?: string | null; kind_label: string; due_date: string | null; overdue: boolean; status: string }
export interface InReq extends DueRequest { regulator: string; body: string | null; status_label: string; severity: string | null; raised_at: string
  legal_basis?: { act?: string; ref: string; url?: string | null; text?: string | null } | null; response_days?: number | null
  signatory?: string | null; has_letter?: boolean; receipt_at?: string | null; raised_by?: string | null }
export interface InDetail extends InReq { messages: { message_id: string; side: string; body: string | null; status_label: string | null; created_at: string; author: string | null }[]; can_set: { key: string; label: string }[] }
export interface RequestList { requests: InReq[]; can_respond: boolean; summary: { open: number; overdue: number } }
export const useRequests = () => useQuery({ queryKey: ['my-supervisor-requests'], queryFn: () => api.get<RequestList>('/v1/me/supervisors/requests') })

// ── what applies, and why ──
export interface Check { label: string; attribute: string; result: boolean | null; tier?: string }
export interface Mandate { id: string; title: string; act: { name: string; url: string }; article: { ref: string; excerpt?: string }; status: string
  tier: { label: string } | null; missing: string[]; checks: Check[]
  deliverable: { label: string | null; channel: string | null; due: string | null; due_rule?: { label?: string } | null } }
export interface Mandates { mandates: Mandate[]; summary: { applies: number; cannot_determine: number; not_applicable: number }; about: Message
  definitions: Record<string, { label: string }> }
export const useMandates = (enabled = true) => useQuery({ queryKey: ['my-mandates'], enabled, queryFn: () => api.get<Mandates>('/v1/me/supervisors/mandates') })
