import { Link, useLocation } from 'react-router-dom'
import { useAuth } from '../lib/auth'

// A hub tab-strip: several related pages presented as tabs on one surface, so the sidebar carries ONE entry
// instead of many. Sector- and permission-aware — a tab only shows if the org's sector and the user's
// permissions allow it (same gates as the sidebar). Renders nothing if only one tab would show.
export type HubTab = { to: string; label: string; sectors?: string[]; perm?: string }

export default function SectionTabs({ tabs }: { tabs: HubTab[] }) {
  const { profile } = useAuth()
  const { pathname } = useLocation()
  const sector = profile?.org?.type ?? ''
  const perms = profile?.permissions ?? []
  const shown = tabs.filter(t => (!t.sectors || t.sectors.includes(sector)) && (!t.perm || perms.includes(t.perm)))
  if (shown.length <= 1) return null
  return (
    <div className="flex gap-1 flex-wrap border-b border-[var(--color-line)] mb-5 -mt-1">
      {shown.map(t => {
        const active = pathname === t.to
        return (
          <Link key={t.to} to={t.to}
            className={`px-3.5 py-2 text-[13px] -mb-px border-b-2 transition ${active
              ? 'border-[var(--color-sky)] text-[var(--color-ink)] font-medium'
              : 'border-transparent text-[var(--color-mute)] hover:text-[var(--color-ink)]'}`}>
            {t.label}
          </Link>
        )
      })}
    </div>
  )
}

// ── hub definitions — the single source of truth for which pages tab together ──────────────────────
const AGRI = ['manufacturer']

export const DATA_TABS: HubTab[] = [
  { to: '/data', label: 'Your data' },
  { to: '/operations', label: 'Our sites', sectors: AGRI },
  { to: '/sourcing', label: 'Suppliers & crops', sectors: AGRI },
  { to: '/data-dictionary', label: 'Data dictionary' },
  { to: '/foundation', label: 'Data sources', sectors: AGRI },
  { to: '/transmission', label: 'Transmission', perm: 'modules.view' },
]

// Note: the Assess-stage "Risk & analysis" hub is ReviewTabs.tsx (already wired into 5 pages) — not duplicated here.

export const ADMIN_TABS: HubTab[] = [
  { to: '/admin', label: 'Settings & team' },
  { to: '/onboarding', label: 'Get started' },
  { to: '/sso', label: 'Single sign-on' },
  { to: '/billing', label: 'Plan & billing' },
]

export const HELP_TABS: HubTab[] = [
  { to: '/docs', label: 'Help & guides' },
  { to: '/support', label: 'Support' },
]
