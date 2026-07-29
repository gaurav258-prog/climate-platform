import { type ReactNode } from 'react'
import { NavLink } from 'react-router-dom'
import { Home, Building2, Sprout, Map as MapIcon, BellRing, ShieldCheck, FileText, FlaskConical, Database, LogOut } from 'lucide-react'
import clsx from 'clsx'
import { useAuth } from '../lib/auth'
import { BrandMark } from './ui'

type Item = { to: string; label: string; icon: typeof Home; end?: boolean }
const GROUPS: { label: string | null; items: Item[] }[] = [
  { label: null, items: [{ to: '/', label: 'Home', icon: Home, end: true }] },
  { label: 'Your footprint', items: [
    { to: '/operations', label: 'Operations', icon: Building2 },
    { to: '/sourcing', label: 'Sourcing book', icon: Sprout },
  ] },
  { label: 'Risk', items: [
    { to: '/riskmap', label: 'Risk map', icon: MapIcon },
    { to: '/early-warning', label: 'Early warning', icon: BellRing },
  ] },
  { label: 'Compliance', items: [
    { to: '/disclosure', label: 'Disclosure & EUDR', icon: ShieldCheck },
    { to: '/csrd', label: 'CSRD · ESRS E1', icon: FileText },
  ] },
  { label: 'Assurance', items: [
    { to: '/models', label: 'Models & validation', icon: FlaskConical },
    { to: '/foundation', label: 'Data foundation', icon: Database },
  ] },
]

export default function Shell({ children }: { children: ReactNode }) {
  const { profile, logout } = useAuth()
  return (
    <div className="min-h-screen flex">
      {/* vertical grouped sidebar */}
      <aside className="w-60 shrink-0 sticky top-0 h-screen flex flex-col border-r border-[var(--color-line)] bg-[var(--color-bg-2)]">
        <div className="h-14 px-5 flex items-center gap-2 border-b border-[var(--color-line)]">
          <BrandMark size={24} />
          <span className="display font-semibold text-[15px]">Tel<span className="text-[var(--color-sky)]">lumen</span></span>
          <span className="mono text-[9px] text-[var(--color-faint)] tracking-widest ml-1">AGRI</span>
        </div>

        <nav className="flex-1 overflow-y-auto py-4 px-3 space-y-5">
          {GROUPS.map((g, gi) => (
            <div key={gi}>
              {g.label && <div className="px-2 mb-1.5 mono text-[9px] uppercase tracking-[0.18em] text-[var(--color-faint)]">{g.label}</div>}
              <div className="space-y-0.5">
                {g.items.map(it => (
                  <NavLink key={it.to} to={it.to} end={it.end} className={({ isActive }) => clsx(
                    'relative flex items-center gap-2.5 rounded-lg px-2.5 py-2.5 text-[14.5px] transition',
                    isActive ? 'bg-[var(--color-panel-2)] text-[var(--color-ink)] font-medium'
                             : 'text-[var(--color-mute)] hover:text-[var(--color-ink)] hover:bg-[var(--color-panel)]')}>
                    {({ isActive }) => (<>
                      {isActive && <span className="absolute left-0 top-2 bottom-2 w-0.5 rounded-full bg-[var(--color-sky)]" />}
                      <it.icon size={17} className={isActive ? 'text-[var(--color-sky)]' : ''} />
                      {it.label}
                    </>)}
                  </NavLink>
                ))}
              </div>
            </div>
          ))}
        </nav>

        <div className="border-t border-[var(--color-line)] px-4 py-3 flex items-center gap-2">
          <div className="min-w-0 flex-1 leading-tight">
            <div className="text-[12px] text-[var(--color-ink)] truncate">{profile?.org?.name}</div>
            <div className="text-[10px] text-[var(--color-faint)] mono truncate">{profile?.user?.email}</div>
          </div>
          <button onClick={logout} title="Log out" className="text-[var(--color-faint)] hover:text-[var(--color-bad)] transition shrink-0"><LogOut size={16} /></button>
        </div>
      </aside>

      {/* content */}
      <div className="flex-1 min-w-0">
        <main className="mx-auto max-w-[1200px] w-full px-8 py-7">{children}</main>
      </div>
    </div>
  )
}
