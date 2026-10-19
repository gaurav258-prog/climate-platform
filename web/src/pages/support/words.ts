// The support centre's words and its response clock — one source for the form, the ticket list and the targets.
// The names are those the platform's support queue uses for the same codes (the server catalogue's
// admin.support_category / admin.support_priority / admin.support_status names; web/tests/supportWords.test.ts
// keeps the two the same).

// `name` on a ticket; `choice` in the form's list, saying what the type is for
export const CATEGORIES: { key: string; name: string; choice: string }[] = [
  { key: 'question', name: 'Question', choice: 'Question — how does something work?' },
  { key: 'bug', name: 'Something is wrong', choice: 'Something is wrong — a screen or a result is not right' },
  { key: 'data', name: 'Data', choice: 'Data — a source or a figure looks off' },
  { key: 'report', name: 'Report', choice: 'Report — help with a report or a filing' },
  { key: 'onboarding', name: 'Onboarding', choice: 'Onboarding — setting up your workspace' },
  { key: 'other', name: 'Other', choice: 'Other — anything else' },
]

// Each priority with the time we aim to give a first reply in.
export const PRIORITIES: { key: string; name: string; hours: number }[] = [
  { key: 'low', name: 'Low', hours: 168 },
  { key: 'normal', name: 'Normal', hours: 72 },
  { key: 'high', name: 'High', hours: 24 },
  { key: 'urgent', name: 'Urgent', hours: 4 },
]

export const STATUSES: Record<string, { name: string; tone: 'good' | 'warn' | 'neutral' }> = {
  open: { name: 'Open', tone: 'warn' }, in_progress: { name: 'In progress', tone: 'neutral' }, resolved: { name: 'Resolved', tone: 'good' },
}

export const categoryName = (k: string) => CATEGORIES.find(c => c.key === k)?.name ?? 'Other'
export const priority = (k: string) => PRIORITIES.find(p => p.key === k) ?? PRIORITIES[1]
export const statusOf = (k: string) => STATUSES[k] ?? STATUSES.open

// A ticket is at risk when its first reply is due within this many hours.
export const RISK_HOURS = 2

export type Clock = { state: 'ok' | 'risk' | 'breached' | 'met'; hoursLeft: number | null }
interface Ticket { status: string; priority: string; created_at: string | null; first_response_at: string | null }

// The target is a first reply: the clock runs from when the ticket is raised and stops at the first reply (or when
// the ticket is resolved) — a ticket answered in time is never shown as late, however long it stays open.
export function clock(t: Ticket, now = Date.now()): Clock {
  if (t.first_response_at || t.status === 'resolved') return { state: 'met', hoursLeft: null }
  if (!t.created_at) return { state: 'ok', hoursLeft: null }
  const hoursLeft = (new Date(t.created_at).getTime() + priority(t.priority).hours * 3600000 - now) / 3600000
  return { state: hoursLeft < 0 ? 'breached' : hoursLeft < RISK_HOURS ? 'risk' : 'ok', hoursLeft }
}

export const duration = (h: number) =>
  h >= 48 ? `${Math.floor(h / 24)} days` : h >= 24 ? '1 day' : h >= 2 ? `${Math.floor(h)} hours` : h >= 1 ? '1 hour' : `${Math.max(1, Math.round(h * 60))} minutes`

// The clock in words for a ticket still waiting for its first reply.
export function clockWords(c: Clock): { text: string; tone: string } | null {
  if (c.state === 'met' || c.hoursLeft == null) return null
  if (c.state === 'breached') return { text: `Reply overdue by ${duration(-c.hoursLeft)}`, tone: 'var(--color-bad)' }
  return { text: `Reply due in ${duration(c.hoursLeft)}`, tone: c.state === 'risk' ? 'var(--color-warn)' : 'var(--color-faint)' }
}
