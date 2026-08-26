import { Link, useLocation } from 'react-router-dom'

// One operator "Clients" console, two tabs — the cross-tenant Tenants list and the Client-intake queue —
// so provisioning a new client and supervising existing ones are one surface, not two nav entries.
const TABS = [
  { to: '/platform', label: 'Tenants' },
  { to: '/intake', label: 'Client intake' },
]

export default function OperatorTabs() {
  const { pathname } = useLocation()
  return (
    <div className="flex gap-1 border-b border-[var(--color-line)] mb-5">
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
