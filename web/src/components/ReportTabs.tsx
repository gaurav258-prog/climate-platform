import { Link, useLocation } from 'react-router-dom'
import { useAuth } from '../lib/auth'

// One "Reports & filings" hub for agriculture — the report types (assemble, EUDR, CSRD, ESRS, prior) as tabs
// on one surface instead of five separate nav entries. Renders only for the agri workspace (manufacturer);
// financial sectors keep their own filing cockpit.
const TABS = [
  { to: '/filings', label: 'Reports & filings' },
  { to: '/disclosure', label: 'EUDR & supply' },
  { to: '/csrd', label: 'Climate (CSRD)' },
  { to: '/esrs', label: 'Nature (ESRS)' },
  { to: '/prior-filings', label: 'Prior filings' },
]

export default function ReportTabs() {
  const { profile } = useAuth()
  const { pathname } = useLocation()
  if (profile?.org?.type !== 'manufacturer') return null
  return (
    <div className="flex gap-1 flex-wrap border-b border-[var(--color-line)] mb-5 -mt-1">
      {TABS.map(t => {
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
