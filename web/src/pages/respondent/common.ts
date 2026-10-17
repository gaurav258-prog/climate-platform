// Shared bits of the supervisory portal's panels (pages/respondent/*): the page a supervised entity uses to answer
// its supervisor, and the same panels a full tenant sees under Settings & team → Entities.
import { useAuth } from '../../lib/auth'

// '2026-04-30' → '30 Apr 2026'; a timestamp gives its day.
export function day(s?: string | null): string {
  if (!s) return '—'
  const d = new Date(s.length === 10 ? `${s}T00:00:00` : s)
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
}

// Whole days from a to b (both ISO dates or timestamps).
export const daysBetween = (a: string, b: string): number =>
  Math.round((Date.parse(b.slice(0, 10)) - Date.parse(a.slice(0, 10))) / 86400000)

export const field = 'rounded-lg border border-[var(--color-line-2)] bg-[var(--color-panel)] px-2.5 py-1.5 text-[12.5px] text-[var(--color-ink)] outline-none focus:border-[var(--color-sky)]'

export function useCan(...perms: string[]): boolean {
  const { profile } = useAuth()
  return (profile?.permissions ?? []).some(p => perms.includes(p))
}
