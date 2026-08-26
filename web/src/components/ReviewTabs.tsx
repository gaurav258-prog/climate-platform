import { Link, useLocation } from 'react-router-dom'
import { useAuth } from '../lib/auth'

// One orienting "Review" hub over the Assess-stage surfaces — so the risk owner has a single entry that
// answers "how does my book look?" instead of guessing which of five overlapping views to open. Each tab is
// the existing page, unchanged behind it; tabs are sector-scoped exactly like the sidebar.
const FIN = ['bank', 'insurer', 'asset_manager', 'reit']
const TABS: { to: string; label: string; sectors?: string[] }[] = [
  { to: '/kri', label: 'KRI dashboard' },
  { to: '/analytics', label: 'Analytics', sectors: ['bank', 'asset_manager', 'reit'] },
  { to: '/track-record', label: 'Climate track record' },
  { to: '/underwriting', label: 'Underwriting review', sectors: ['insurer'] },
  { to: '/model-validation', label: 'Model validation' },
]

export default function ReviewTabs() {
  const { pathname } = useLocation()
  const { profile } = useAuth()
  const type = profile?.org?.type ?? ''
  const tabs = TABS.filter(t => !t.sectors || t.sectors.includes(type) || (t.sectors === FIN))
  return (
    <div className="flex gap-1 border-b border-[var(--color-line)] mb-5 overflow-x-auto">
      {tabs.map(t => {
        const active = pathname === t.to
        return (
          <Link key={t.to} to={t.to}
            className={`px-3.5 py-2 text-[13px] whitespace-nowrap -mb-px border-b-2 transition ${active
              ? 'border-[var(--color-sky)] text-[var(--color-ink)] font-medium'
              : 'border-transparent text-[var(--color-mute)] hover:text-[var(--color-ink)]'}`}>
            {t.label}
          </Link>
        )
      })}
    </div>
  )
}
